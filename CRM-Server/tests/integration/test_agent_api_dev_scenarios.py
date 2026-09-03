"""Scenario-driven Agent HTTP acceptance tests against the development MySQL data.

This suite is deliberately opt-in because it connects to the configured development
DB.  By default it uses transaction rollback.  Set
``RUN_AGENT_API_DEV_SCENARIOS_PERSIST=1`` to run through the real password-login
route as the dev account and keep the generated sessions, activities, and durable
work visible in the CRM UI.

Run:

    RUN_AGENT_API_DEV_SCENARIOS=1 uv run pytest \
      tests/integration/test_agent_api_dev_scenarios.py -q --no-cov

Persistent dev-data run:

    AGENT_API_DEV_TEST_PASSWORD='...' \
    RUN_AGENT_API_DEV_SCENARIOS=1 \
    RUN_AGENT_API_DEV_SCENARIOS_PERSIST=1 \
    uv run pytest tests/integration/test_agent_api_dev_scenarios.py -q --no-cov

The Root orchestration seam is replaced with a deterministic typed result so the
test does not call a real LLM.  The real AgentApplicationService, turn repository,
message persistence, public FastAPI routes, ORM, permission/customer resolution,
and durable-work registration remain in the path.
"""

# ruff: noqa: RUF001

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import agent as agent_api
from app.api import auth as auth_api
from app.api import customer_activities as customer_activities_api
from app.core import database, deps
from app.services.agent.application import AgentApplicationService
from app.services.agent.orchestrator import (
    ContextPolicy,
    RootDecision,
    RootTurnInput,
    WorkflowDispatchResult,
)
from app.services.agent.semantic_plan import AgentSemanticPlan
from app.services.agent.workflow import (
    WorkflowCompletedResult,
    WorkflowProgress,
    WorkflowProgressStep,
    WorkflowRef,
)
from app.services.customer_activity_contracts import (
    CustomerActivityEffectivenessStatus,
    CustomerActivityProcessingStatus,
    CustomerActivitySubmissionSource,
)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_AGENT_API_DEV_SCENARIOS") != "1",
    reason="requires RUN_AGENT_API_DEV_SCENARIOS=1 and the configured development MySQL",
)

_PERSIST = os.getenv("RUN_AGENT_API_DEV_SCENARIOS_PERSIST") == "1"
_TEST_EMAIL = os.getenv("AGENT_API_DEV_TEST_EMAIL", "eddie@apifox.com")
_RUN_LABEL = os.getenv("AGENT_API_DEV_RUN_LABEL", "local")
if _PERSIST:
    # Persistent runs must be safely re-runnable: every invocation gets a fresh
    # visible suffix instead of colliding with a previous retained dataset.
    _RUN_LABEL = f"{_RUN_LABEL}-{uuid4().hex[:8]}"


@dataclass(frozen=True)
class DevCustomer:
    internal_id: int
    public_id: str
    account_name: str
    owner_id: str
    activity_count: int
    opportunity_count: int


@dataclass(frozen=True)
class ApiScenario:
    case_id: str
    capability: str
    customer: DevCustomer
    content: str
    activity_kind: str = "PHONE_FOLLOW_UP"
    score: int = 85
    next_action: str | None = "下周三确认预算并发送正式报价"
    next_follow_time: str | None = "2026-09-09T10:00:00"


class RollbackSession(Session):
    """Keep route-level commits inside the case transaction."""

    def commit(self) -> None:
        self.flush()


class _DeterministicRootOrchestrator:
    """Deterministic root seam while retaining the real turn persistence adapter."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def dispatch(
        self,
        turn: RootTurnInput,
        *,
        runtime: Any,
        on_progress: Any = None,
    ) -> WorkflowDispatchResult:
        self.calls.append(
            {
                "turn": turn,
                "authorization": runtime.authorization,
                "client_request_id": UUID(turn.client_request_id),
            }
        )
        input_text = turn.input.text if getattr(turn.input, "type", None) == "text" else "已提交 Agent 页面交互"
        workflow_ref = WorkflowRef(workflow_id=f"wf_{uuid4().hex}")
        progress = WorkflowProgress(
            steps=[
                WorkflowProgressStep(
                    key="agent_test",
                    title="Agent 测试处理",
                    status="COMPLETED",
                    description="使用确定性根编排验证真实消息持久化链路。",
                )
            ]
        )
        decision = RootDecision(
            task_relation="NEW_TASK",
            route="WORKFLOW",
            risk="WRITE",
            context_policy=ContextPolicy(
                selected_entity="IGNORE",
                previous_query="IGNORE",
                result_set="IGNORE",
                active_workflow="NONE",
            ),
            confidence=1.0,
            reason_code="DEV_DETERMINISTIC_ACCEPTANCE",
            evidence=["真实 AgentApplicationService 持久化验收"],
            semantic_plan=AgentSemanticPlan(
                speech_act="REQUEST_ACTION",
                business_object="CUSTOMER_ACTIVITY",
                operation="CREATE",
                confidence=1.0,
            ),
        )
        return WorkflowDispatchResult(
            decision=decision,
            workflow_result=WorkflowCompletedResult(
                workflow_ref=workflow_ref,
                assistant_text=f"已收到并完成处理：{input_text}",
                progress=progress,
            ),
        )


def _load_dev_customers(db: Session) -> list[DevCustomer]:
    rows = db.execute(
        text(
            """
            SELECT c.id, c.public_id, c.account_name, c.owner_id,
                   (SELECT COUNT(*) FROM crm_customer_activities a
                    WHERE a.customer_id = c.id AND a.team_id = c.team_id) AS activity_count,
                   (SELECT COUNT(*) FROM crm_opportunities o
                    WHERE o.customer_id = c.id AND o.team_id = c.team_id) AS opportunity_count
            FROM crm_customers c
            WHERE c.team_id = 1
            ORDER BY (SELECT COUNT(*) FROM crm_customer_activities a2
                      WHERE a2.customer_id = c.id AND a2.team_id = c.team_id) DESC,
                     c.id ASC
            LIMIT 20
            """
        )
    ).mappings()
    return [
        DevCustomer(
            internal_id=int(row["id"]),
            public_id=str(row["public_id"]),
            account_name=str(row["account_name"]),
            owner_id=str(row["owner_id"]),
            activity_count=int(row["activity_count"] or 0),
            opportunity_count=int(row["opportunity_count"] or 0),
        )
        for row in rows
    ]


@pytest.fixture(scope="session")
def dev_data_snapshot() -> dict[str, Any]:
    if database.engine.dialect.name != "mysql":
        pytest.skip("development scenario suite requires MySQL")
    with database.engine.connect() as connection:
        counts = {}
        for name, table in {
            "users": "users",
            "customers": "crm_customers",
            "activities": "crm_customer_activities",
            "opportunities": "crm_opportunities",
            "agent_sessions": "crm_agent_sessions",
            "activity_ai_jobs": "crm_customer_activity_ai_jobs",
        }.items():
            counts[name] = int(connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)
        customers = _load_dev_customers(Session(bind=connection))
    if not customers:
        pytest.skip("development database has no team 1 customers")
    return {"counts": counts, "customers": customers}


@pytest.fixture
def api_case(dev_data_snapshot, monkeypatch):
    connection = None
    transaction = None
    if _PERSIST:
        db = Session(bind=database.engine, autoflush=False, expire_on_commit=False)
    else:
        connection = database.engine.connect()
        transaction = connection.begin()
        db = RollbackSession(bind=connection, autoflush=False, expire_on_commit=False)
    customer = dev_data_snapshot["customers"][0]
    app = FastAPI()
    app.include_router(agent_api.router, prefix="/api")
    app.include_router(customer_activities_api.router, prefix="/api")
    if _PERSIST:
        app.include_router(auth_api.router, prefix="/api/v1")

    def get_test_db():
        yield db

    if not _PERSIST:
        user = SimpleNamespace(id=1, name="开发环境销售", status="active")
        permissions = [
            SimpleNamespace(code=code)
            for code in (
                "customer:view:all",
                "customer:view:own",
                "customer:create",
                "customer:edit:all",
                "customer_activity:create",
                "customer_activity:delete:own",
            )
        ]
        app.dependency_overrides[database.get_db] = get_test_db
        app.dependency_overrides[deps.get_db] = get_test_db
        app.dependency_overrides[agent_api.get_current_user_team] = lambda: 1
        app.dependency_overrides[agent_api.get_current_active_user] = lambda: user
        app.dependency_overrides[customer_activities_api.get_current_user_team] = lambda: 1
        app.dependency_overrides[customer_activities_api.get_current_active_user] = lambda: user
        monkeypatch.setattr(agent_api.permission_crud, "get_user_permissions", lambda *a, **k: permissions)
        monkeypatch.setattr(deps.permission_crud, "get_user_permissions", lambda *a, **k: permissions)
    monkeypatch.setattr(customer_activities_api.customer_activity_write_service, "kick", lambda *a, **k: None)
    monkeypatch.setattr(customer_activities_api.customer_activity_write_service, "kick_delete", lambda *a, **k: None)
    monkeypatch.setattr(customer_activities_api, "_load_user_info", lambda *a, **k: None)

    deterministic = _DeterministicRootOrchestrator()
    service = AgentApplicationService(
        root_orchestrator=deterministic,
        session_factory=lambda: db,
    )
    monkeypatch.setattr(agent_api, "agent_application_service", service)

    try:
        with TestClient(app) as client:
            if _PERSIST:
                password = os.getenv("AGENT_API_DEV_TEST_PASSWORD")
                if not password:
                    pytest.fail("persistent run requires AGENT_API_DEV_TEST_PASSWORD")
                login = client.post(
                    "/api/v1/auth/login-password",
                    json={"email": _TEST_EMAIL, "password": password},
                )
                assert login.status_code == 200, login.text
                login_payload = login.json()
                assert login_payload["user"]["email"] == _TEST_EMAIL
                client.headers.update(
                    {"Authorization": f"Bearer {login_payload['access_token']}"}
                )
            yield client, db, customer, deterministic
    finally:
        if not _PERSIST:
            db.rollback()
        db.close()
        if transaction is not None:
            transaction.rollback()
        if connection is not None:
            connection.close()
        app.dependency_overrides.clear()


def _scenario_rows(snapshot: dict[str, Any], *, count: int = 30) -> list[ApiScenario]:
    customers: list[DevCustomer] = snapshot["customers"]
    activity_kinds = ["PHONE_FOLLOW_UP", "WECHAT_FOLLOW_UP", "EMAIL_FOLLOW_UP", "MEETING", "OTHER_FOLLOW_UP"]
    templates = [
        "已与{customer}采购负责人电话沟通，确认本周完成试用反馈，客户认可权限管理方案。",
        "在{customer}会议中完成需求澄清，客户计划下周组织技术评审。",
        "通过微信跟进{customer}项目，客户提出需要补充报价和部署说明。",
        "向{customer}发送方案邮件，客户确认周五前反馈预算区间。",
        "与{customer}复盘 POC 结果，客户同意安排下一次验收会议。",
        "联系{customer}项目负责人，当前仍在内部比较供应商。",
    ]
    rows: list[ApiScenario] = []
    for i in range(count):
        customer = customers[i % len(customers)]
        rows.append(
            ApiScenario(
                case_id=f"DEV-{_RUN_LABEL}-ACT-{i + 1:03d}",
                capability="customer_activity_api",
                customer=customer,
                content=(
                    f"【Agent API dev验收 {_RUN_LABEL}】"
                    f"{templates[i % len(templates)].format(customer=customer.account_name)}"
                ),
                activity_kind=activity_kinds[i % len(activity_kinds)],
                score=60 + (i * 7) % 41,
                next_action=(
                    None
                    if i % 11 == 0
                    else (
                        "客户内部预算确认后再联系"
                        if i % 13 == 0
                        else "下周三确认预算并发送正式报价"
                    )
                ),
                next_follow_time=(None if i % 7 == 0 else "2026-09-09T10:00:00"),
            )
        )
    return rows


@pytest.mark.parametrize("case_index", list(range(30)), ids=lambda i: f"session-create-{i + 1:03d}")
def test_agent_api_session_creation_cases(api_case, case_index: int) -> None:
    client, _db, _customer, _runtime = api_case
    title = f"Agent API dev验收-{_RUN_LABEL}-会话-{case_index + 1:03d}"
    response = client.post("/api/v1/agent/sessions", json={"title": title})
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["team_id"] == 1
    assert payload["user_id"] == 1
    assert payload["title"] == title
    assert payload["status"] == "ACTIVE"
    assert payload["session_key"].startswith("agent_")


@pytest.mark.parametrize(
    "query",
    [
        {},
        {"page": 1, "page_size": 1},
        {"page": 1, "page_size": 5},
        {"page": 1, "page_size": 20},
        {"page": 2, "page_size": 5},
        {"page": 3, "page_size": 10},
        {"page": 1, "page_size": 50},
        {"page": 1, "page_size": 100},
        {"session_status": "ACTIVE"},
        {"session_status": "CLOSED"},
        {"page": 1, "page_size": 2, "session_status": "ACTIVE"},
        {"page": 2, "page_size": 2, "session_status": "ACTIVE"},
        {"page": 1, "page_size": 10, "session_status": "ARCHIVED"},
        {"page": 1, "page_size": 20, "session_status": "PENDING"},
        {"page": 4, "page_size": 20},
        {"page": 5, "page_size": 20},
        {"page": 1, "page_size": 3},
        {"page": 2, "page_size": 3},
        {"page": 1, "page_size": 7},
        {"page": 2, "page_size": 7},
    ],
    ids=lambda query: "sessions-" + ("default" if not query else "-".join(f"{k}-{v}" for k, v in query.items())),
)
def test_agent_api_session_list_cases(api_case, query: dict[str, Any]) -> None:
    client, _db, _customer, _runtime = api_case
    response = client.get("/api/v1/agent/sessions", params=query)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload) >= {"items", "total", "page", "page_size", "total_pages"}
    assert payload["page"] == query.get("page", 1)
    assert payload["page_size"] == query.get("page_size", 20)
    assert len(payload["items"]) <= payload["page_size"]
    assert all(item["team_id"] == 1 and item["user_id"] == 1 for item in payload["items"])


@pytest.mark.parametrize(
    "case_index",
    list(range(20)),
    ids=lambda i: f"stream-contract-{i + 1:03d}",
)
def test_agent_api_chat_stream_contract_cases(api_case, case_index: int) -> None:
    client, _db, _customer, runtime = api_case
    session = client.post(
        "/api/v1/agent/sessions",
        json={"title": f"Agent API dev验收-{_RUN_LABEL}-SSE-{case_index}"},
    ).json()
    request_id = str(uuid4())
    authorization = (
        client.headers["Authorization"]
        if _PERSIST
        else "Bearer dev-scenario-token"
    )
    response = client.post(
        "/api/v1/agent/chat/stream",
        headers={"Authorization": authorization},
        json={
            "session_id": session["id"],
            "client_request_id": request_id,
            "input": {"type": "text", "text": f"请处理第 {case_index + 1} 个客户跟进场景"},
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [event["event"] for event in events] == ["session", "agent_ui", "done"]
    assert events[1]["phase"] == "final"
    assert events[1]["message"]["schema_version"] == "crm.agent.ui.v1"
    assert events[2]["session_id"] == session["id"]
    assert runtime.calls[-1]["authorization"] == authorization
    assert runtime.calls[-1]["client_request_id"] == UUID(request_id)

    history = client.get(
        f"/api/v1/agent/sessions/{session['id']}/messages",
        headers={"Authorization": authorization},
    )
    assert history.status_code == 200, history.text
    history_payload = history.json()
    assert history_payload["total"] == 2
    assert [item["role"] for item in history_payload["items"]] == ["user", "assistant"]
    assert history_payload["items"][0]["blocks"][0]["text"].startswith("请处理第")
    assert any(
        "已收到并完成处理" in block.get("text", "")
        for block in history_payload["items"][1]["blocks"]
        if block.get("type") == "text"
    )


def test_agent_api_visible_single_session_multi_turn(api_case) -> None:
    """Keep one real Agent session so the CRM UI can inspect a continuous dialogue."""
    client, _db, _customer, runtime = api_case
    session = client.post(
        "/api/v1/agent/sessions",
        json={"title": f"Agent API dev验收-{_RUN_LABEL}-可视化连续对话"},
    )
    assert session.status_code == 201, session.text
    session_payload = session.json()
    session_id = session_payload["id"]
    authorization = (
        client.headers["Authorization"]
        if _PERSIST
        else "Bearer dev-scenario-token"
    )

    for turn_index in range(20):
        request_id = str(uuid4())
        response = client.post(
            "/api/v1/agent/chat/stream",
            headers={"Authorization": authorization},
            json={
                "session_id": session_id,
                "client_request_id": request_id,
                "input": {
                    "type": "text",
                    "text": f"可视化连续对话第 {turn_index + 1} 轮：请处理客户跟进场景",
                },
            },
        )
        assert response.status_code == 200, response.text
        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        assert [event["event"] for event in events] == ["session", "agent_ui", "done"]
        assert events[1]["phase"] == "final"
        assert events[2]["session_id"] == session_id
        assert runtime.calls[-1]["client_request_id"] == UUID(request_id)

    history = client.get(
        f"/api/v1/agent/sessions/{session_id}/messages",
        headers={"Authorization": authorization},
    )
    assert history.status_code == 200, history.text
    history_payload = history.json()
    assert history_payload["total"] == 40
    assert [item["role"] for item in history_payload["items"]] == [
        role
        for _ in range(20)
        for role in ("user", "assistant")
    ]
    user_messages = [
        item["blocks"][0]["text"]
        for item in history_payload["items"]
        if item["role"] == "user"
    ]
    assert user_messages == [
        f"可视化连续对话第 {turn_index + 1} 轮：请处理客户跟进场景"
        for turn_index in range(20)
    ]


@pytest.mark.parametrize("case_index", list(range(30)), ids=lambda i: f"form-activity-{i + 1:03d}")
def test_agent_api_form_activity_durable_pipeline_cases(api_case, dev_data_snapshot, case_index: int) -> None:
    client, db, _customer, _runtime = api_case
    scenario = _scenario_rows(dev_data_snapshot, count=30)[case_index]
    response = client.post(
        f"/api/v1/customer-activities/{scenario.customer.public_id}",
        json={
            "activity_kind": scenario.activity_kind,
            "source_content": scenario.content,
            "next_action": scenario.next_action,
            "next_follow_time": scenario.next_follow_time,
            "occurred_at": "2026-09-02T09:30:00",
            "submission_id": f"{scenario.case_id}-FORM",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["customer_id"] == scenario.customer.public_id
    assert payload["submission_source"] == CustomerActivitySubmissionSource.FORM.value
    assert payload["processing_status"] == CustomerActivityProcessingStatus.PENDING.value
    assert payload["effectiveness_status"] == CustomerActivityEffectivenessStatus.PENDING.value
    assert payload["effectiveness_score"] is None
    durable = payload["durable_work"]
    assert durable["ai_job_public_id"].startswith("caij_")
    assert durable["post_commit_job_public_id"] is None
    assert durable["opportunity_suggestion_job_public_id"] is None
    activity = db.execute(
        text("SELECT source_content FROM crm_customer_activities WHERE id=:id"),
        {"id": payload["id"]},
    ).scalar_one()
    assert activity == scenario.content


@pytest.mark.parametrize("case_index", list(range(30)), ids=lambda i: f"agent-finalized-{i + 1:03d}")
def test_agent_api_finalized_activity_quality_gate_cases(api_case, dev_data_snapshot, case_index: int) -> None:
    client, db, _customer, _runtime = api_case
    scenario = _scenario_rows(dev_data_snapshot, count=30)[case_index]
    score = max(60, scenario.score)
    response = client.post(
        f"/api/v1/customer-activities/{scenario.customer.public_id}/agent-finalized",
        json={
            "activity_kind": scenario.activity_kind,
            "source_content": scenario.content,
            "title": f"{scenario.customer.account_name}跟进",
            "summary": scenario.content[:80],
            "content_json": {"customer": scenario.customer.account_name, "facts": ["需求已确认"]},
            "next_action": scenario.next_action,
            "next_follow_time": scenario.next_follow_time,
            "effectiveness_score": score,
            "effectiveness_is_valid": True,
            "effectiveness_reason": "事实、结果和下一步行动均已明确",
            "effectiveness_detail_json": {"facts": 20, "result": 20, "action": 20, "context": 20, "clarity": 15},
            "occurred_at": "2026-09-02T09:30:00",
            "submission_id": f"{scenario.case_id}-AGENT",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["submission_source"] == CustomerActivitySubmissionSource.AGENT.value
    assert payload["processing_status"] == CustomerActivityProcessingStatus.COMPLETED.value
    assert payload["effectiveness_status"] == CustomerActivityEffectivenessStatus.COMPLETED.value
    assert payload["effectiveness_score"] == score
    assert payload["durable_work"]["ai_job_public_id"] is None
    assert payload["durable_work"]["post_commit_job_public_id"].startswith("pcj_")
    assert payload["durable_work"]["opportunity_suggestion_job_public_id"].startswith("cosj_")
    row = db.execute(
        text("SELECT effectiveness_score, effectiveness_status FROM crm_customer_activities WHERE id=:id"),
        {"id": payload["id"]},
    ).mappings().one()
    assert int(row["effectiveness_score"]) == score
    assert row["effectiveness_status"] == CustomerActivityEffectivenessStatus.COMPLETED.value


@pytest.mark.parametrize(
    ("score", "is_valid"),
    [
        (0, False),
        (1, False),
        (40, False),
        (59, False),
        (59, True),
        (60, False),
        (0, True),
        (55, True),
        (58, True),
        (10, False),
    ],
    ids=lambda value: f"blocked-{value}",
)
def test_agent_api_finalized_activity_rejects_non_passing_scores(api_case, score: int, is_valid: bool) -> None:
    client, db, customer, _runtime = api_case
    response = client.post(
        f"/api/v1/customer-activities/{customer.public_id}/agent-finalized",
        json={
            "activity_kind": "PHONE_FOLLOW_UP",
            "source_content": f"【Agent API dev验收 {_RUN_LABEL} blocked-{score}-{is_valid}】客户说后续再看看。",
            "effectiveness_score": score,
            "effectiveness_is_valid": is_valid,
            "effectiveness_reason": "信息不足，需要补充",
            "effectiveness_detail_json": {},
        },
    )
    assert response.status_code == 422, response.text
    count = db.execute(
        text("SELECT COUNT(*) FROM crm_customer_activities WHERE source_content=:content"),
        {"content": f"【Agent API dev验收 {_RUN_LABEL} blocked-{score}-{is_valid}】客户说后续再看看。"},
    ).scalar_one()
    assert count == 0


@pytest.mark.parametrize(
    "case_index",
    list(range(10)),
    ids=lambda i: f"activity-list-existing-{i + 1:03d}",
)
def test_agent_api_existing_customer_activity_read_cases(api_case, dev_data_snapshot, case_index: int) -> None:
    client, _db, _customer, _runtime = api_case
    customer = dev_data_snapshot["customers"][case_index % len(dev_data_snapshot["customers"])]
    response = client.get(f"/api/v1/customer-activities/{customer.public_id}", params={"skip": 0, "limit": 100})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) <= 100
    assert all(item["customer_id"] == customer.public_id for item in payload)
    assert all("activity_kind" in item and "source_content" in item for item in payload)

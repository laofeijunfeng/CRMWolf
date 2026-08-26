"""Public HTTP contract tests for the unified CRM Agent API."""

from __future__ import annotations

import json
from collections.abc import Iterator
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.api import agent as agent_api
from app.core.database import Base
from app.models.agent import (
    AgentMessage,
    AgentMessageRole,
    AgentSession,
    AgentWorkflowAction,
)
from app.models.agent_async_operation import AgentAsyncOperation, AgentAsyncOperationEvent
from app.models.agent_persistence import AgentUIAction
from app.schemas.agent import AgentSSEEventEnvelope
from app.schemas.agent_persistence import AgentUIActionRegistration
from app.services.agent.ui.actions import AgentUIActionRepository
from app.services.agent.ui.schemas import TextAgentInput


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


class _FakeApplicationService:
    def __init__(self, events: list[AgentSSEEventEnvelope]) -> None:
        self.events = events
        self.calls: list[dict[str, object]] = []

    async def stream_chat_events(self, **kwargs):
        self.calls.append(kwargs)
        for event in self.events:
            yield event


@pytest.fixture
def api_harness(monkeypatch) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AgentSession.__table__,
            AgentMessage.__table__,
            AgentWorkflowAction.__table__,
            AgentUIAction.__table__,
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine)

    app = FastAPI()
    app.include_router(agent_api.router)

    def database_dependency() -> Iterator[Session]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[agent_api.get_db] = database_dependency
    app.dependency_overrides[agent_api.get_current_user_team] = lambda: 1
    app.dependency_overrides[agent_api.get_current_active_user] = lambda: SimpleNamespace(
        id=2,
        name="销售李",
        status="active",
    )
    monkeypatch.setattr(
        agent_api.permission_crud,
        "get_user_permissions",
        lambda *args, **kwargs: [],
    )

    async def project_no_pending_confirmations(*args, **kwargs):
        return []

    monkeypatch.setattr(
        agent_api.follow_up_confirmation_agent_ui_projection,
        "project_pending",
        project_no_pending_confirmations,
    )

    with TestClient(app) as client:
        yield client, session_factory

    engine.dispose()


def _create_session(client: TestClient, *, title: str = "上海客户") -> dict[str, object]:
    response = client.post("/v1/agent/sessions", json={"title": title})
    assert response.status_code == 201
    return response.json()


def _persist_message(
    session_factory: sessionmaker[Session],
    *,
    session_id: int,
    team_id: int = 1,
    user_id: int = 2,
    role: str = AgentMessageRole.ASSISTANT,
    content: str = "你在上海有 1 个客户。",
) -> AgentMessage:
    with session_factory() as db:
        row = AgentMessage(
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
            turn_id="turn_api_messages",
        )
        db.add(row)
        db.flush()
        row.ui_json = {
            "schema_version": "crm.agent.ui.v1",
            "message_id": int(row.id),
            "turn_id": row.turn_id,
            "role": "assistant",
            "state": "final",
            "blocks": [
                {
                    "id": "answer",
                    "type": "text",
                    "format": "plain",
                    "text": content,
                }
            ],
            "suggested_actions": [],
            "metadata": {
                "display": "MESSAGE",
                "route": "QUERY",
                "result_set_id": None,
                "accessibility_label": content,
            },
        }
        db.commit()
        db.refresh(row)
        db.expunge(row)
        return row



def _persist_interaction_message(
    session_factory: sessionmaker[Session],
    *,
    session_id: int,
    action_status: str,
) -> dict[str, object]:
    with session_factory() as db:
        row = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session_id,
            role=AgentMessageRole.ASSISTANT,
            content="确认创建跟进吗？",
            turn_id=f"turn_interaction_{action_status.lower()}",
        )
        db.add(row)
        db.flush()
        action_id = f"act_interaction_{action_status.lower()}"
        row.ui_json = {
            "schema_version": "crm.agent.ui.v1",
            "message_id": int(row.id),
            "turn_id": row.turn_id,
            "role": "assistant",
            "state": "final",
            "blocks": [
                {
                    "id": "confirmation",
                    "type": "interaction",
                    "interaction_id": "int_create_follow_up",
                    "interaction_type": "confirmation",
                    "state": "ACTIVE",
                    "prompt": "确认创建跟进吗？",
                    "fields": [],
                    "options": [
                        {
                            "value": "confirm",
                            "label": "确认创建",
                            "description": None,
                            "disabled": False,
                        },
                        {
                            "value": "cancel",
                            "label": "取消",
                            "description": None,
                            "disabled": False,
                        },
                    ],
                    "selection_mode": "single",
                    "submit_action_id": action_id,
                }
            ],
            "suggested_actions": [],
            "metadata": {
                "route": "WORKFLOW",
                "result_set_id": None,
                "accessibility_label": "确认创建跟进吗？",
            },
        }
        repository = AgentUIActionRepository()
        repository.register(
            db,
            AgentUIActionRegistration(
                public_id=action_id,
                team_id=1,
                user_id=2,
                session_id=session_id,
                message_id=int(row.id),
                action_type="submit_interaction",
                target={"interaction_type": "confirmation"},
                consumption_mode="ONE_SHOT",
            ),
        )
        request_id = "6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be"
        repository.begin_consumption(
            db,
            public_id=action_id,
            team_id=1,
            user_id=2,
            session_id=session_id,
            client_request_id=request_id,
        )
        if action_status == "CONSUMED":
            repository.complete_consumption(
                db,
                public_id=action_id,
                team_id=1,
                user_id=2,
                session_id=session_id,
                client_request_id=request_id,
                result_message_id=int(row.id),
            )
        db.commit()
        return dict(row.ui_json)

def _persist_action(session_factory: sessionmaker[Session], *, session_id: int) -> None:
    with session_factory() as db:
        db.add(
            AgentWorkflowAction(
                workflow_id="wf_api_audit",
                action_id="action_api_audit",
                team_id=1,
                user_id=2,
                session_id=session_id,
                source_type="agent",
                action_type="create_customer",
                status="EXECUTED",
                scope="required_write",
                source="explicit_user_request",
                execution_policy="requires_confirmation",
                on_reject="cancel_action",
                blocking=True,
                result_json={"customer_id": 101},
            )
        )
        db.commit()


def _stream_events(response) -> list[dict[str, object]]:
    return [json.loads(line.removeprefix("data: ")) for line in response.text.splitlines() if line.startswith("data: ")]


def test_session_create_and_list_are_scoped_to_current_owner(api_harness) -> None:
    client, session_factory = api_harness
    created = _create_session(client)
    with session_factory() as db:
        db.add(AgentSession(session_key="agent_other", team_id=1, user_id=99, title="其他用户"))
        db.commit()

    response = client.get("/v1/agent/sessions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [item["id"] for item in payload["items"]] == [created["id"]]


def test_message_history_returns_only_canonical_agent_ui(api_harness) -> None:
    client, session_factory = api_harness
    created = _create_session(client)
    message = _persist_message(session_factory, session_id=int(created["id"]))

    response = client.get(
        f"/v1/agent/sessions/{created['id']}/messages",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"] == [message.ui_json]
    assert payload["items"][0]["schema_version"] == "crm.agent.ui.v1"



@pytest.mark.parametrize(
    ("action_status", "expected_state"),
    [("CONSUMING", "READ_ONLY"), ("CONSUMED", "SUBMITTED")],
)
def test_message_history_projects_submitted_interactions_as_authoritative_read_only(
    api_harness,
    action_status: str,
    expected_state: str,
) -> None:
    client, session_factory = api_harness
    created = _create_session(client)
    persisted_ui = _persist_interaction_message(
        session_factory,
        session_id=int(created["id"]),
        action_status=action_status,
    )

    response = client.get(
        f"/v1/agent/sessions/{created['id']}/messages",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    interaction = response.json()["items"][0]["blocks"][0]
    assert persisted_ui["blocks"][0]["state"] == "ACTIVE"
    assert interaction["state"] == expected_state
    assert interaction["submit_action_id"] is None

def test_message_history_rejects_unowned_session(api_harness) -> None:
    client, session_factory = api_harness
    with session_factory() as db:
        other = AgentSession(session_key="agent_unowned", team_id=1, user_id=99, title="其他用户")
        db.add(other)
        db.commit()
        other_id = int(other.id)

    response = client.get(
        f"/v1/agent/sessions/{other_id}/messages",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent会话不存在"


def test_workflow_ledger_is_read_only_and_owner_scoped(api_harness) -> None:
    client, session_factory = api_harness
    created = _create_session(client)
    _persist_action(session_factory, session_id=int(created["id"]))

    actions_response = client.get(f"/v1/agent/sessions/{created['id']}/actions")
    detail_response = client.get("/v1/agent/workflows/wf_api_audit")

    assert actions_response.status_code == 200
    assert actions_response.json()["total"] == 1
    assert actions_response.json()["items"][0]["action_id"] == "action_api_audit"
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["workflow_status"] == "COMPLETED"
    assert detail["action_summary"] == {
        "total": 1,
        "by_status": {"EXECUTED": 1},
        "waiting_action_count": 0,
        "failed_action_count": 0,
        "blocked_action_count": 0,
    }



def test_operation_history_repairs_both_background_task_types_without_short_circuit(
    api_harness,
    monkeypatch,
) -> None:
    client, _ = api_harness
    created = _create_session(client)
    repair_calls: list[str] = []

    monkeypatch.setattr(
        agent_api,
        "_read_repair_customer_intelligence_operations",
        lambda db, operations: repair_calls.append("customer_intelligence_refresh") or True,
    )
    monkeypatch.setattr(
        agent_api,
        "_read_repair_customer_activity_post_commit_operations",
        lambda db, operations: repair_calls.append("customer_activity_post_commit") or True,
    )

    response = client.get(f"/v1/agent/sessions/{created['id']}/operations")

    assert response.status_code == 200
    assert response.json() == []
    assert repair_calls == [
        "customer_intelligence_refresh",
        "customer_activity_post_commit",
    ]

def test_chat_stream_delegates_only_to_application_service(api_harness, monkeypatch) -> None:
    client, _ = api_harness
    request_id = UUID("6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be")
    message = {
        "schema_version": "crm.agent.ui.v1",
        "message_id": 11,
        "turn_id": "turn_api_stream",
        "role": "assistant",
        "state": "final",
        "blocks": [
            {
                "id": "answer",
                "type": "text",
                "format": "plain",
                "text": "你在上海有 1 个客户。",
            }
        ],
        "suggested_actions": [],
        "metadata": {
            "display": "MESSAGE",
            "route": "QUERY",
            "result_set_id": None,
            "accessibility_label": "你在上海有 1 个客户。",
        },
    }
    fake = _FakeApplicationService(
        [
            AgentSSEEventEnvelope.model_validate(
                {"event": "session", "session_id": 7, "session_key": "agent_api_stream"}
            ),
            AgentSSEEventEnvelope.model_validate(
                {
                    "event": "agent_ui",
                    "phase": "final",
                    "message_id": 11,
                    "turn_id": "turn_api_stream",
                    "sequence": 1,
                    "message": message,
                }
            ),
            AgentSSEEventEnvelope.model_validate({"event": "done", "session_id": 7}),
        ]
    )
    monkeypatch.setattr(agent_api, "agent_application_service", fake)

    response = client.post(
        "/v1/agent/chat/stream",
        headers={"Authorization": "Bearer test-token"},
        json={
            "client_request_id": str(request_id),
            "input": {"type": "text", "text": "上海有哪些客户"},
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _stream_events(response)
    assert [event["event"] for event in events] == ["session", "agent_ui", "done"]
    assert events[1]["message"] == message
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["client_request_id"] == request_id
    assert call["team_id"] == 1
    assert call["user_id"] == 2
    assert call["authorization"] == "Bearer test-token"
    assert call["session_id"] is None
    assert call["session_key"] is None
    assert call["request_input"] == TextAgentInput(type="text", text="上海有哪些客户")


def test_removed_runtime_management_endpoints_are_not_registered(api_harness) -> None:
    client, _ = api_harness
    registered = {(method, route.path) for route in client.app.routes for method in getattr(route, "methods", set())}

    assert ("POST", "/v1/agent/workflows/{workflow_id}/retry") not in registered
    assert ("POST", "/v1/agent/workflows/{workflow_id}/actions/{action_id}/retry") not in registered
    assert ("POST", "/v1/agent/workflow-recovery/scan") not in registered
    assert ("GET", "/v1/agent/sessions/{session_id}/runtime/overview") not in registered
    assert ("GET", "/v1/agent/sessions/{session_id}/runtime/state") not in registered
    assert ("GET", "/v1/agent/sessions/{session_id}/runtime/history") not in registered
    assert (
        "GET",
        "/v1/agent/sessions/{session_id}/runtime/checkpoints/{checkpoint_id}",
    ) not in registered

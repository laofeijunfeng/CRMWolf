"""CRM AI Agent API tests."""
import asyncio
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.api import agent as agent_api
from app.core.database import Base
from app.models.agent import (
    AgentIdempotencyKey,
    AgentMessage,
    AgentMessageRole,
    AgentSession,
    AgentTask,
    AgentTaskStatus,
    AgentToolCall,
    AgentWorkflowAction,
)
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_vector_document import CustomerVectorDocument
from app.models.sales_commitment import (
    FollowUpTask,
    FollowUpTaskConfirmationCase,
    FollowUpTaskConfirmationPromptDelivery,
    FollowUpTaskEvent,
    FollowUpTaskProjectionRun,
    SalesCommitment,
)
from app.services.agent.confirmed_task_graph import ConfirmedTaskGraphService
from app.services.agent import action_workflow
from app.services.agent.input import AgentTurnInput
from app.services.agent.pending_graph import PendingTaskGraphService
from app.services.agent.root_runtime import AgentRootRuntime
from app.services.agent.schemas import (
    AgentFollowUpQualityResult,
    AgentPendingInterruptionDecision,
    AgentSemanticParseResult,
    AgentTurnRelationDecision,
)
from app.services.agent.state import (
    AgentRootRuntimeSideEffects,
    AgentRuntimeContext,
    AgentRuntimeTurnOutput,
)
from app.services.agent.interactions import _opportunity_interaction_fields
from app.services.agent.task_actions import _tool_payload_for_action
from app.services.agent.tools.base import AgentToolResult
from app.services.follow_up_task_confirmation_channel_service import (
    FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION,
    FOLLOW_UP_CONFIRMATION_PROMPT_EVENT,
    FOLLOW_UP_CONFIRMATION_RESOLVED_EVENT,
)
from app.services.im_agent_gateway import IMAgentGateway


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


def _build_client(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Customer.__table__,
        CustomerActivity.__table__,
        CustomerVectorDocument.__table__,
        SalesCommitment.__table__,
        FollowUpTask.__table__,
        FollowUpTaskEvent.__table__,
        FollowUpTaskProjectionRun.__table__,
        FollowUpTaskConfirmationCase.__table__,
        FollowUpTaskConfirmationPromptDelivery.__table__,
        AgentSession.__table__,
        AgentMessage.__table__,
        AgentTask.__table__,
        AgentToolCall.__table__,
        AgentIdempotencyKey.__table__,
        AgentWorkflowAction.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    Session = sessionmaker(bind=engine)

    app = FastAPI()
    app.include_router(agent_api.router)
    app.dependency_overrides[agent_api.get_db] = lambda: Session()
    app.dependency_overrides[agent_api.get_current_user_team] = lambda: 1
    app.dependency_overrides[agent_api.get_current_active_user] = lambda: SimpleNamespace(
        id=2,
        name="销售李",
        status="active",
    )
    monkeypatch.setattr(agent_api, "SessionLocal", lambda: Session())
    if agent_api.agent_application_module.agent_root_runtime is agent_api.agent_root_runtime:
        checkpointer = InMemorySaver()
        monkeypatch.setattr(
            agent_api.agent_application_module,
            "agent_root_runtime",
            AgentRootRuntime(
                checkpointer=checkpointer,
                new_flow_graph_service=agent_api.crm_agent_graph_service,
                pending_graph_service=PendingTaskGraphService(checkpointer=checkpointer),
                confirmed_task_graph_service=ConfirmedTaskGraphService(checkpointer=checkpointer),
            ),
        )

    return TestClient(app), engine


class FakeSemanticParser:
    def __init__(self, result):
        self.results = result if isinstance(result, list) else [result]
        self.calls = []

    async def parse(self, db, *, team_id, user_message, memory=None, current_date=None):
        self.calls.append({
            "team_id": team_id,
            "user_message": user_message,
            "memory": memory,
            "current_date": current_date,
        })
        index = min(len(self.calls) - 1, len(self.results) - 1)
        return AgentSemanticParseResult.model_validate(self.results[index])


class FakePendingInterruptionParser:
    def __init__(self, decision):
        self.decision = decision
        self.calls = []

    async def assess_pending_interruption(self, db, *, team_id, user_message, pending_task, memory=None, current_date=None):
        self.calls.append({
            "team_id": team_id,
            "user_message": user_message,
            "pending_task": pending_task,
            "memory": memory,
            "current_date": current_date,
        })
        return AgentPendingInterruptionDecision.model_validate(self.decision)


class FakeTurnRelationAndSemanticParser:
    def __init__(self, *, relation, semantic_results):
        self.relation = relation
        self.semantic_results = semantic_results if isinstance(semantic_results, list) else [semantic_results]
        self.relation_calls = []
        self.parse_calls = []

    async def assess_turn_relation(
        self,
        db,
        *,
        team_id,
        user_message,
        active_task=None,
        suspended_tasks=None,
        memory=None,
        current_date=None,
    ):
        self.relation_calls.append({
            "team_id": team_id,
            "user_message": user_message,
            "active_task": active_task,
            "suspended_tasks": suspended_tasks,
            "memory": memory,
            "current_date": current_date,
        })
        relation = dict(self.relation)
        if relation.get("target_task_id") == "__first_suspended__":
            relation["target_task_id"] = suspended_tasks[0]["id"]
        return AgentTurnRelationDecision.model_validate(relation)

    async def parse(self, db, *, team_id, user_message, memory=None, current_date=None):
        self.parse_calls.append({
            "team_id": team_id,
            "user_message": user_message,
            "memory": memory,
            "current_date": current_date,
        })
        index = min(len(self.parse_calls) - 1, len(self.semantic_results) - 1)
        return AgentSemanticParseResult.model_validate(self.semantic_results[index])


class FakeQualityEvaluator:
    def __init__(self, results):
        self.results = results if isinstance(results, list) else [results]
        self.calls = []

    async def evaluate_with_metadata(self, db, *, team_id, user_message, semantic_result, memory=None, current_date=None):
        self.calls.append({
            "team_id": team_id,
            "user_message": user_message,
            "semantic_result": semantic_result,
            "memory": memory,
            "current_date": current_date,
        })
        index = min(len(self.calls) - 1, len(self.results) - 1)
        result = AgentFollowUpQualityResult.model_validate(self.results[index])

        class Envelope:
            quality_source = "test_quality_evaluator"
            model = "test-model"
            fallback_reason = None
            fallback_error = None

            def __init__(self, quality_result):
                self.result = quality_result

        return Envelope(result)


def test_agent_session_and_stream_api(monkeypatch):
    class FakeRootRuntime:
        async def run_turn(self, *, content, context, **kwargs):
            context.side_effects.new_flow_events.extend([
                {"event": "agent_step", "step": "semantic_parse", "status": "started", "content": "AI 语义理解"},
                {"event": "tool_result", "tool_name": "get_customer_context", "success": True},
                {"event": "final", "content": f"已收到：{content}"},
            ])
            context.side_effects.new_flow_assistant_content = f"已收到：{content}"
            return {
                "application_action": "run_new_flow",
                "assistant_content": f"已收到：{content}",
            }

    monkeypatch.setattr(agent_api.agent_application_module, "agent_root_runtime", FakeRootRuntime())

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "跟进会话"})
        assert create_response.status_code == 201, create_response.text
        session = create_response.json()
        assert session["team_id"] == 1
        assert session["user_id"] == 2
        assert session["title"] == "跟进会话"

        list_response = client.get("/v1/agent/sessions")
        assert list_response.status_code == 200, list_response.text
        assert list_response.json()["total"] == 1

        stream_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "今天和越秀金融沟通了项目进展"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert stream_response.status_code == 200, stream_response.text
        stream_text = stream_response.text
        assert '"event": "message"' in stream_text
        assert "今天和越秀金融沟通了项目进展" in stream_text

        messages_response = client.get(f"/v1/agent/sessions/{session['id']}/messages")
        assert messages_response.status_code == 200, messages_response.text
        messages_body = messages_response.json()
        assert messages_body["total"] == 2
        assert [item["role"] for item in messages_body["items"]] == ["USER", "ASSISTANT"]
        assistant_message = messages_body["items"][1]
        trace_events = assistant_message["payload_json"]["trace_events"]
        assert [event["event"] for event in trace_events] == [
            "agent_step",
            "tool_result",
            "agent_turn_observability",
        ]
        assert trace_events[1]["tool_name"] == "get_customer_context"
        observability = assistant_message["payload_json"]["turn_observability"]
        assert observability["schema_version"] == "agent.turn_observability.v1"
        assert observability["retrieval"]["customer_context"]["called"] is True
    finally:
        engine.dispose()


def test_agent_session_actions_api_lists_workflow_action_timeline(monkeypatch):
    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "动作账本会话"}).json()
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            db.add_all([
                AgentWorkflowAction(
                    workflow_id="wf_action_api",
                    action_id="act_waiting",
                    team_id=1,
                    user_id=2,
                    session_id=session["id"],
                    source_type="agent_planning",
                    action_type="create_opportunity",
                    status="WAITING_USER",
                    scope="optional_suggestion",
                    source="business_suggestion",
                    execution_policy="requires_confirmation",
                    on_reject="skip_and_continue",
                    blocking=False,
                    target_type="customer",
                    target_id=7,
                    payload_json={"customer_id": 7},
                ),
                AgentWorkflowAction(
                    workflow_id="wf_action_api",
                    action_id="act_executed",
                    team_id=1,
                    user_id=2,
                    session_id=session["id"],
                    source_type="post_commit_projection",
                    action_type="project_next_follow_up_tasks",
                    status="EXECUTED",
                    scope="derived_automation",
                    source="system_automation",
                    execution_policy="auto_execute",
                    on_reject="ask_clarification",
                    blocking=False,
                    result_json={"created_task_count": 1},
                ),
                AgentWorkflowAction(
                    workflow_id="wf_background",
                    action_id="act_background",
                    team_id=1,
                    user_id=None,
                    session_id=None,
                    source_type="post_commit_reconciliation",
                    action_type="reconcile_historical_follow_up_tasks",
                    status="EXECUTED",
                    scope="derived_automation",
                    source="system_automation",
                    execution_policy="auto_execute",
                    on_reject="ask_clarification",
                    blocking=False,
                    target_type="customer",
                    target_id=7,
                    result_json={"matched_task_count": 1},
                ),
                AgentWorkflowAction(
                    workflow_id="wf_other_user",
                    action_id="act_other_user",
                    team_id=1,
                    user_id=3,
                    session_id=None,
                    source_type="agent_planning",
                    action_type="create_customer_activity",
                    status="EXECUTED",
                    scope="required_write",
                    source="explicit_user_request",
                    execution_policy="requires_confirmation",
                    on_reject="cancel_action",
                    blocking=True,
                    target_type="customer",
                    target_id=7,
                ),
            ])
            db.commit()
        finally:
            db.close()

        response = client.get(f"/v1/agent/sessions/{session['id']}/actions")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == 2
        assert [item["action_id"] for item in body["items"]] == ["act_waiting", "act_executed"]
        assert body["items"][0]["payload_json"] == {"customer_id": 7}
        assert body["items"][1]["result_json"] == {"created_task_count": 1}

        filtered_response = client.get(
            f"/v1/agent/sessions/{session['id']}/actions",
            params={"action_status": "WAITING_USER"},
        )
        assert filtered_response.status_code == 200, filtered_response.text
        filtered_body = filtered_response.json()
        assert filtered_body["total"] == 1
        assert filtered_body["items"][0]["action_id"] == "act_waiting"

        missing_response = client.get("/v1/agent/sessions/999/actions")
        assert missing_response.status_code == 404

        target_response = client.get(
            "/v1/agent/actions",
            params={"target_type": "customer", "target_id": 7},
        )
        assert target_response.status_code == 200, target_response.text
        target_body = target_response.json()
        assert target_body["total"] == 2
        assert {item["action_id"] for item in target_body["items"]} == {"act_waiting", "act_background"}
        assert "act_other_user" not in {item["action_id"] for item in target_body["items"]}
        waiting_item = next(item for item in target_body["items"] if item["action_id"] == "act_waiting")
        assert waiting_item["capability"]["is_write"] is True
        assert waiting_item["capability"]["requires_user_authorization"] is True
        assert waiting_item["capability"]["requires_idempotency_key"] is True
        assert waiting_item["capability"]["parallel_safe"] is False
    finally:
        engine.dispose()


def test_agent_workflow_detail_api_exposes_action_graph_and_status(monkeypatch):
    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "工作流图"}).json()
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            db.add_all([
                AgentWorkflowAction(
                    workflow_id="wf_graph_api",
                    action_id="act_root",
                    team_id=1,
                    user_id=2,
                    session_id=session["id"],
                    source_type="agent_planning",
                    action_type="create_customer_activity",
                    status="EXECUTED",
                    scope="required_write",
                    source="explicit_user_request",
                    execution_policy="requires_confirmation",
                    on_reject="cancel_action",
                    blocking=True,
                ),
                AgentWorkflowAction(
                    workflow_id="wf_graph_api",
                    action_id="act_projection",
                    parent_action_id="act_root",
                    team_id=1,
                    user_id=None,
                    session_id=session["id"],
                    source_type="post_commit_projection",
                    action_type="project_next_follow_up_tasks",
                    status="EXECUTED",
                    scope="derived_automation",
                    source="system_automation",
                    execution_policy="auto_execute",
                    on_reject="ask_clarification",
                    blocking=False,
                    dependency_json={
                        "depends_on": ["act_root"],
                        "parallel_group": "post_commit_activity_analysis",
                        "join": "apply_transition_policy",
                    },
                ),
                AgentWorkflowAction(
                    workflow_id="wf_graph_api",
                    action_id="act_reconciliation",
                    parent_action_id="act_root",
                    team_id=1,
                    user_id=2,
                    session_id=session["id"],
                    source_type="post_commit_reconciliation",
                    action_type="reconcile_historical_follow_up_tasks",
                    status="WAITING_USER",
                    scope="optional_suggestion",
                    source="business_suggestion",
                    execution_policy="requires_confirmation",
                    on_reject="skip_and_continue",
                    blocking=False,
                    status_reason="等待用户确认历史任务是否完成",
                    dependency_json={
                        "depends_on": ["act_root", "act_missing"],
                        "parallel_group": "post_commit_activity_analysis",
                    },
                ),
                AgentWorkflowAction(
                    workflow_id="wf_graph_api",
                    action_id="act_other_user",
                    team_id=1,
                    user_id=3,
                    session_id=session["id"],
                    source_type="agent_planning",
                    action_type="create_opportunity",
                    status="BLOCKED",
                    scope="optional_suggestion",
                    source="business_suggestion",
                    execution_policy="requires_confirmation",
                    on_reject="ask_clarification",
                    blocking=True,
                ),
            ])
            db.commit()
        finally:
            db.close()

        response = client.get("/v1/agent/workflows/wf_graph_api")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["workflow_status"] == "WAITING_USER"
        assert body["status_reason"] == "WAITING_USER: act_reconciliation"
        assert body["action_summary"] == {
            "total": 3,
            "by_status": {"EXECUTED": 2, "WAITING_USER": 1},
            "waiting_action_count": 1,
            "failed_action_count": 0,
            "blocked_action_count": 0,
        }
        assert [node["action_id"] for node in body["nodes"]] == [
            "act_root",
            "act_projection",
            "act_reconciliation",
        ]
        reconciliation_node = next(node for node in body["nodes"] if node["action_id"] == "act_reconciliation")
        assert reconciliation_node["depends_on"] == ["act_root", "act_missing"]
        assert reconciliation_node["parallel_group"] == "post_commit_activity_analysis"
        assert reconciliation_node["status_reason"] == "等待用户确认历史任务是否完成"
        assert reconciliation_node["error_message"] is None
        assert {tuple(edge.values()) for edge in body["edges"]} == {
            ("act_root", "act_projection", "parent"),
            ("act_root", "act_projection", "depends_on"),
            ("act_root", "act_reconciliation", "parent"),
            ("act_root", "act_reconciliation", "depends_on"),
        }
        assert "act_other_user" not in {action["action_id"] for action in body["actions"]}
        projection_action = next(action for action in body["actions"] if action["action_id"] == "act_projection")
        assert projection_action["capability"]["allows_background_recovery"] is True
        assert projection_action["capability"]["parallel_safe"] is True

        missing_response = client.get("/v1/agent/workflows/wf_missing")
        assert missing_response.status_code == 404
    finally:
        engine.dispose()


def test_agent_workflow_action_retry_api_prepares_retry_and_preserves_policy(monkeypatch):
    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "动作重试"}).json()
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            db.add_all([
                AgentWorkflowAction(
                    workflow_id="wf_retry_api",
                    action_id="act_retry_failed",
                    team_id=1,
                    user_id=2,
                    session_id=session["id"],
                    source_type="agent_planning",
                    action_type="create_customer_activity",
                    status="FAILED",
                    scope="required_write",
                    source="explicit_user_request",
                    execution_policy="requires_confirmation",
                    on_reject="cancel_action",
                    blocking=True,
                    result_json={"success": False},
                    status_reason="tool failed",
                    error_message="database timeout",
                ),
                AgentWorkflowAction(
                    workflow_id="wf_retry_api",
                    action_id="act_retry_executed",
                    team_id=1,
                    user_id=2,
                    session_id=session["id"],
                    source_type="agent_planning",
                    action_type="create_customer_activity",
                    status="EXECUTED",
                    scope="required_write",
                    source="explicit_user_request",
                    execution_policy="requires_confirmation",
                    on_reject="cancel_action",
                    blocking=True,
                ),
                AgentWorkflowAction(
                    workflow_id="wf_retry_api",
                    action_id="act_retry_other_user",
                    team_id=1,
                    user_id=3,
                    session_id=session["id"],
                    source_type="agent_planning",
                    action_type="create_customer_activity",
                    status="FAILED",
                    scope="required_write",
                    source="explicit_user_request",
                    execution_policy="requires_confirmation",
                    on_reject="cancel_action",
                    blocking=True,
                ),
            ])
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/v1/agent/workflows/wf_retry_api/actions/act_retry_failed/retry",
            json={"retry_source": "manual_api", "reason": "排除临时异常后重试"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "WAITING_USER"
        assert body["result_json"] is None
        assert body["error_message"] is None
        assert body["status_reason"] == "排除临时异常后重试"
        assert body["decision_json"]["last_retry"]["previous_status"] == "FAILED"
        assert body["decision_json"]["last_retry"]["previous_error_message"] == "database timeout"

        executed_response = client.post(
            "/v1/agent/workflows/wf_retry_api/actions/act_retry_executed/retry",
            json={"reason": "不应该重试已执行动作"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert executed_response.status_code == 409

        other_user_response = client.post(
            "/v1/agent/workflows/wf_retry_api/actions/act_retry_other_user/retry",
            json={"reason": "越权"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert other_user_response.status_code == 404
    finally:
        engine.dispose()


def test_agent_workflow_retry_api_delegates_to_root_runtime(monkeypatch):
    class FakeRootRuntime:
        def __init__(self):
            self.calls = []

        async def retry_workflow(self, **kwargs):
            self.calls.append(kwargs)
            actions = kwargs["actions"]
            actions[0].status = "PLANNED"
            actions[0].status_reason = "恢复工作流"
            actions[0].error_message = None
            return actions

    fake_runtime = FakeRootRuntime()
    monkeypatch.setattr(agent_api, "agent_root_runtime", fake_runtime)
    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "工作流恢复"}).json()
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            db.add(
                AgentWorkflowAction(
                    workflow_id="wf_retry_full_api",
                    action_id="act_retry_failed",
                    team_id=1,
                    user_id=2,
                    session_id=session["id"],
                    source_type="post_commit_projection",
                    action_type="project_next_follow_up_tasks",
                    status="FAILED",
                    scope="derived_automation",
                    source="system_automation",
                    execution_policy="auto_execute",
                    on_reject="ask_clarification",
                    blocking=False,
                    error_message="temporary projection failure",
                )
            )
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/v1/agent/workflows/wf_retry_full_api/retry",
            json={"retry_source": "manual_api", "reason": "恢复工作流"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["workflow_id"] == "wf_retry_full_api"
        assert body["actions"][0]["status"] == "PLANNED"
        assert body["actions"][0]["status_reason"] == "恢复工作流"
        assert fake_runtime.calls
        call = fake_runtime.calls[0]
        assert call["workflow_id"] == "wf_retry_full_api"
        assert call["session"].id == session["id"]
        assert call["authorization"] == "Bearer test-token"
        assert call["retry_source"] == "manual_api"
        assert call["reason"] == "恢复工作流"
    finally:
        engine.dispose()


def test_agent_workflow_recovery_scan_api_is_user_scoped_dry_run(monkeypatch):
    class FakeRecoveryService:
        def __init__(self):
            self.calls = []

        async def recover_once(self, *args, **kwargs):
            self.calls.append(kwargs)
            return {
                "scanned_actions": 1,
                "scanned_workflows": 1,
                "eligible_workflows": 1,
                "retried_workflows": 0,
                "retried_actions": 0,
                "dry_run": kwargs["dry_run"],
                "skipped": {},
                "policy_reasons": {},
                "failed": 0,
                "decisions": [
                    {
                        "workflow_id": "wf_scan",
                        "eligible": True,
                        "reason": "eligible",
                        "action_count": 1,
                        "retryable_action_count": 1,
                        "safe_action_count": 1,
                        "policy_reasons": {},
                        "retryable_action_policies": [
                            {
                                "action_id": "act_scan",
                                "action_type": "refresh_customer_profile",
                                "allowed": True,
                                "reason": "allowed",
                                "execution_mode": "root_runtime_retry",
                                "requires_user_authorization": False,
                            }
                        ],
                    }
                ],
            }

    fake_service = FakeRecoveryService()
    monkeypatch.setattr(agent_api, "agent_workflow_recovery_service", fake_service)
    client, engine = _build_client(monkeypatch)
    try:
        response = client.post(
            "/v1/agent/workflow-recovery/scan",
            json={"limit": 10, "safe_action_types": ["refresh_customer_profile"]},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["dry_run"] is True
        assert body["retried_workflows"] == 0
        assert fake_service.calls
        call = fake_service.calls[0]
        assert call["limit"] == 10
        assert call["dry_run"] is True
        assert call["safe_action_types"] == ["refresh_customer_profile"]
        assert call["team_id"] == 1
        assert call["user_id"] == 2
    finally:
        engine.dispose()


def test_agent_runtime_overview_api_combines_checkpoint_and_action_ledger(monkeypatch):
    class FakeRootRuntime:
        def __init__(self):
            self.calls = []

        async def current_checkpoint_state(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "checkpoint_id": "cp-overview",
                "runtime_status": "waiting",
                "current_interrupt": {
                    "type": "confirm_action",
                    "business_action": "RECONCILE_FOLLOW_UP_TASK",
                },
                "application_action": "resume_interrupt",
            }

    fake_runtime = FakeRootRuntime()
    monkeypatch.setattr(agent_api, "agent_root_runtime", fake_runtime)
    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "运行总览"}).json()
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            db.add_all([
                AgentWorkflowAction(
                    workflow_id="wf_overview",
                    action_id="act_waiting_overview",
                    team_id=1,
                    user_id=2,
                    session_id=session["id"],
                    source_type="agent_planning",
                    action_type="reconcile_follow_up_task",
                    status="WAITING_USER",
                    scope="optional_suggestion",
                    source="business_suggestion",
                    execution_policy="requires_confirmation",
                    on_reject="skip_and_continue",
                    blocking=False,
                ),
                AgentWorkflowAction(
                    workflow_id="wf_overview",
                    action_id="act_failed_overview",
                    team_id=1,
                    user_id=2,
                    session_id=session["id"],
                    source_type="post_commit_projection",
                    action_type="project_next_follow_up_tasks",
                    status="FAILED",
                    scope="derived_automation",
                    source="system_automation",
                    execution_policy="auto_execute",
                    on_reject="ask_clarification",
                    blocking=False,
                    error_message="projection failed",
                ),
                AgentWorkflowAction(
                    workflow_id="wf_overview",
                    action_id="act_blocked_overview",
                    team_id=1,
                    user_id=2,
                    session_id=session["id"],
                    source_type="agent_planning",
                    action_type="create_opportunity",
                    status="BLOCKED",
                    scope="optional_suggestion",
                    source="business_suggestion",
                    execution_policy="requires_confirmation",
                    on_reject="ask_clarification",
                    blocking=True,
                ),
                AgentWorkflowAction(
                    workflow_id="wf_overview",
                    action_id="act_system_overview",
                    team_id=1,
                    user_id=None,
                    session_id=session["id"],
                    source_type="post_commit_reconciliation",
                    action_type="reconcile_historical_follow_up_tasks",
                    status="EXECUTED",
                    scope="derived_automation",
                    source="system_automation",
                    execution_policy="auto_execute",
                    on_reject="ask_clarification",
                    blocking=False,
                ),
            ])
            db.commit()
        finally:
            db.close()

        response = client.get(
            f"/v1/agent/sessions/{session['id']}/runtime/overview",
            params={"recent_action_limit": 2},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["session_id"] == session["id"]
        assert body["session_key"] == session["session_key"]
        assert body["runtime_status"] == "waiting"
        assert body["checkpoint_id"] == "cp-overview"
        assert body["has_interrupt"] is True
        assert body["current_interrupt"]["business_action"] == "RECONCILE_FOLLOW_UP_TASK"
        assert body["action_summary"] == {
            "total": 4,
            "by_status": {
                "WAITING_USER": 1,
                "FAILED": 1,
                "BLOCKED": 1,
                "EXECUTED": 1,
            },
            "waiting_action_count": 1,
            "failed_action_count": 1,
            "blocked_action_count": 1,
        }
        assert len(body["recent_actions"]) == 2
        assert [item["action_id"] for item in body["recent_actions"]] == [
            "act_system_overview",
            "act_blocked_overview",
        ]
        assert body["values"]["application_action"] == "resume_interrupt"
        assert fake_runtime.calls[0] == {
            "team_id": 1,
            "user_id": 2,
            "session_id": session["id"],
            "session_key": session["session_key"],
        }

        missing_response = client.get("/v1/agent/sessions/999/runtime/overview")
        assert missing_response.status_code == 404
    finally:
        engine.dispose()


async def test_agent_application_streams_runtime_events_before_turn_finishes(monkeypatch):
    class FakeRootRuntime:
        def __init__(self):
            self.release = asyncio.Event()
            self.finished = False

        async def run_turn(self, *, content, context, **kwargs):
            if context.event_sink:
                await context.event_sink({
                    "event": "agent_step",
                    "step": "semantic_parse",
                    "status": "started",
                    "content": "AI 语义理解",
                })
            await self.release.wait()
            self.finished = True
            context.side_effects.new_flow_assistant_content = f"已收到：{content}"
            return {
                "application_action": "run_new_flow",
                "assistant_content": f"已收到：{content}",
            }

    client, engine = _build_client(monkeypatch)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(agent_api.agent_application_module, "SessionLocal", lambda: Session())
    fake_runtime = FakeRootRuntime()
    monkeypatch.setattr(agent_api.agent_application_module, "agent_root_runtime", fake_runtime)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "流式事件"}).json()
        stream = agent_api.agent_application_service.stream_chat_events(
            content="今天和越秀金融沟通了项目进展",
            team_id=1,
            user_id=2,
            authorization="Bearer test-token",
            session_id=session["id"],
        )

        assert (await anext(stream))["event"] == "session"
        user_event = await anext(stream)
        assert user_event["event"] == "message"
        assert user_event["role"] == "USER"

        step_event = await asyncio.wait_for(anext(stream), timeout=0.2)

        assert step_event == {
            "event": "agent_step",
            "step": "semantic_parse",
            "status": "started",
            "content": "AI 语义理解",
        }
        assert fake_runtime.finished is False

        fake_runtime.release.set()
        remaining_events = [event async for event in stream]
        assert [event["event"] for event in remaining_events] == [
            "agent_turn_observability",
            "message",
            "done",
        ]
        assert remaining_events[0]["summary"]["schema_version"] == "agent.turn_observability.v1"
        assert fake_runtime.finished is True
    finally:
        engine.dispose()


async def test_agent_application_uses_streamed_final_as_assistant_content(monkeypatch):
    class FakeRootRuntime:
        async def run_turn(self, *, context, **kwargs):
            if context.event_sink:
                await context.event_sink({
                    "event": "agent_step",
                    "step": "customer_intelligence",
                    "status": "completed",
                    "content": "生成客户回答：已基于客户档案、业务上下文和检索证据整理回答，置信度 92%",
                })
                await context.event_sink({
                    "event": "final",
                    "content": "中国科学院信息工程研究所当前有 1 个推进中的商机。",
                    "content_format": "markdown",
                })
            return {
                "application_action": "run_new_flow",
                "events": [{"event": "agent_root_customer_intelligence_graph_completed"}],
            }

    client, engine = _build_client(monkeypatch)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(agent_api.agent_application_module, "SessionLocal", lambda: Session())
    monkeypatch.setattr(agent_api.agent_application_module, "agent_root_runtime", FakeRootRuntime())
    try:
        session = client.post("/v1/agent/sessions", json={"title": "客户查询"}).json()
        events = []
        async for event in agent_api.agent_application_service.stream_chat_events(
            content="中科院现在是什么情况",
            team_id=1,
            user_id=2,
            authorization="Bearer test-token",
            session_id=session["id"],
        ):
            events.append(event)

        assistant_messages = [
            event for event in events
            if event.get("event") == "message" and event.get("role") == "ASSISTANT"
        ]
        assert assistant_messages[-1]["content"] == "中国科学院信息工程研究所当前有 1 个推进中的商机。"
        assert assistant_messages[-1]["content_format"] == "markdown"
        assert "好嘞，已处理完成。" not in [event.get("content") for event in events]

        db = Session()
        try:
            persisted_assistant = (
                db.query(AgentMessage)
                .filter(
                    AgentMessage.session_id == session["id"],
                    AgentMessage.role == "ASSISTANT",
                )
                .order_by(AgentMessage.id.desc())
                .first()
            )
            assert persisted_assistant is not None
            assert persisted_assistant.payload_json["content_format"] == "markdown"
        finally:
            db.close()
    finally:
        engine.dispose()


async def test_agent_application_persists_assistant_when_stream_is_closed_before_done(monkeypatch):
    class FakeRootRuntime:
        def __init__(self):
            self.release = asyncio.Event()

        async def run_turn(self, *, context, **kwargs):
            if context.event_sink:
                await context.event_sink({
                    "event": "final",
                    "content": "合同跟进记录已创建，周四继续跟进合同签订流程。",
                    "content_format": "markdown",
                })
            await self.release.wait()
            return {
                "application_action": "run_new_flow",
                "assistant_content": "合同跟进记录已创建，周四继续跟进合同签订流程。",
            }

    client, engine = _build_client(monkeypatch)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(agent_api.agent_application_module, "SessionLocal", lambda: Session())
    fake_runtime = FakeRootRuntime()
    monkeypatch.setattr(agent_api.agent_application_module, "agent_root_runtime", fake_runtime)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "断流收尾"}).json()
        stream = agent_api.agent_application_service.stream_chat_events(
            content="今天和地平线采购确认合同内容，周四跟进合同签订流程",
            team_id=1,
            user_id=2,
            authorization="Bearer test-token",
            session_id=session["id"],
        )

        assert (await anext(stream))["event"] == "session"
        assert (await anext(stream))["role"] == "USER"
        final_event = await asyncio.wait_for(anext(stream), timeout=0.2)
        assert final_event["event"] == "final"

        await stream.aclose()
        fake_runtime.release.set()
        await asyncio.sleep(0.05)

        db = Session()
        try:
            persisted_assistant = (
                db.query(AgentMessage)
                .filter(
                    AgentMessage.session_id == session["id"],
                    AgentMessage.role == "ASSISTANT",
                )
                .order_by(AgentMessage.id.desc())
                .first()
            )
            assert persisted_assistant is not None
            assert persisted_assistant.content == "合同跟进记录已创建，周四继续跟进合同签订流程。"
            assert persisted_assistant.payload_json["source"] == "langgraph_stream_cancelled_finalizer"
            assert persisted_assistant.payload_json["for_user_message_id"] > 0
            assert persisted_assistant.payload_json["content_format"] == "markdown"
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_and_im_gateway_do_not_prompt_unrelated_pending_confirmation_cases(monkeypatch):
    class FakeRootRuntime:
        async def run_turn(self, *, content, context, **kwargs):
            if context.event_sink:
                await context.event_sink({
                    "event": "final",
                    "content": f"已处理：{content}",
                    "content_format": "text",
                })
            return {"application_action": "run_new_flow", "events": []}

    monkeypatch.setattr(agent_api.agent_application_module, "agent_root_runtime", FakeRootRuntime())

    client, engine = _build_client(monkeypatch)
    Session = sessionmaker(bind=engine)
    try:
        web_session = client.post("/v1/agent/sessions", json={"title": "Web 确认提示"}).json()
        web_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": web_session["id"], "content": "今天我的任务有哪些"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert web_response.status_code == 200, web_response.text
        assert FOLLOW_UP_CONFIRMATION_PROMPT_EVENT not in web_response.text
        assert FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION not in web_response.text

        im_session = client.post("/v1/agent/sessions", json={"title": "IM 确认提示"}).json()
        db = Session()
        try:
            im_result = asyncio.run(
                IMAgentGateway().handle_text(
                    db,
                    team_id=1,
                    user_id=2,
                    provider="feishu",
                    session_id=im_session["id"],
                    user_text="@CRMWolf 今天我的任务有哪些",
                    agent_content="今天我的任务有哪些",
                )
            )
        finally:
            db.close()

        assert im_result["interaction"] is None
        assert not any(event.get("event") == FOLLOW_UP_CONFIRMATION_PROMPT_EVENT for event in im_result["im_events"])
    finally:
        engine.dispose()


def test_agent_stream_routes_structured_follow_up_confirmation_reply_through_root_runtime(monkeypatch):
    class FakeRootRuntime:
        def __init__(self):
            self.calls = []

        async def run_turn(self, *, turn_input, content, context, **kwargs):
            self.calls.append({"turn_input": turn_input, "content": content, **kwargs})
            event = {
                "event": FOLLOW_UP_CONFIRMATION_RESOLVED_EVENT,
                "content": "已更新为下周五继续跟进。",
                "content_format": "text",
                "case_public_id": turn_input.metadata["case_public_id"],
                "resolution": "delayed",
            }
            context.side_effects.new_flow_events.append(event)
            context.side_effects.new_flow_assistant_content = "已更新为下周五继续跟进。"
            return {
                "application_action": "run_new_flow",
                "assistant_content": "已更新为下周五继续跟进。",
                "events": [event],
            }

    fake_runtime = FakeRootRuntime()
    monkeypatch.setattr(agent_api.agent_application_module, "agent_root_runtime", fake_runtime)

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "确认回复"}).json()
        response = client.post(
            "/v1/agent/chat/stream",
            json={
                "session_id": session["id"],
                "content": "今天联系了，还没有进展，下周五再说",
                "interaction_metadata": {
                    "business_action": FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION,
                    "case_public_id": "fuc_22222222222222222222222222222222",
                },
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200, response.text
        assert FOLLOW_UP_CONFIRMATION_RESOLVED_EVENT in response.text
        assert "已更新为下周五继续跟进。" in response.text
        assert len(fake_runtime.calls) == 1
        assert fake_runtime.calls[0]["turn_input"].metadata["case_public_id"] == (
            "fuc_22222222222222222222222222222222"
        )
        assert fake_runtime.calls[0]["content"] == "今天联系了，还没有进展，下周五再说"

        messages_response = client.get(f"/v1/agent/sessions/{session['id']}/messages")
        assistant_message = messages_response.json()["items"][1]
        assert assistant_message["payload_json"]["source"] == "langgraph"
    finally:
        engine.dispose()


def test_agent_stream_does_not_resolve_implicit_follow_up_confirmation_for_long_text(monkeypatch):
    class FakeRootRuntime:
        def __init__(self):
            self.calls = []

        async def run_turn(self, *, content, context, **kwargs):
            self.calls.append({"content": content, **kwargs})
            context.side_effects.new_flow_events.append(
                {"event": "final", "content": "进入主 Agent 处理"}
            )
            context.side_effects.new_flow_assistant_content = "进入主 Agent 处理"
            return {
                "application_action": "run_new_flow",
                "assistant_content": "进入主 Agent 处理",
            }

    fake_runtime = FakeRootRuntime()
    monkeypatch.setattr(agent_api.agent_application_module, "agent_root_runtime", fake_runtime)

    client, engine = _build_client(monkeypatch)
    Session = sessionmaker(bind=engine)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "隐式确认误伤"}).json()
        db = Session()
        try:
            db.add(
                AgentMessage(
                    team_id=1,
                    user_id=2,
                    session_id=session["id"],
                    role=AgentMessageRole.ASSISTANT,
                    event_type="assistant_message",
                    content="这项跟进任务是否已完成?",
                    payload_json={
                        "trace_events": [
                            {
                                "event": FOLLOW_UP_CONFIRMATION_PROMPT_EVENT,
                                "interaction": {
                                    "business_action": FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION,
                                    "status": "waiting_user_input",
                                    "payload": {
                                        "case_public_id": "fuc_33333333333333333333333333333333",
                                    },
                                },
                            }
                        ],
                    },
                )
            )
            db.commit()
        finally:
            db.close()

        long_follow_up_note = (
            "今天和客户同步了续费方案, 采购侧已确认会先走供应商入库, "
            "技术侧还没有完成提单, 明天继续推动内部流程。"
        )
        response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": long_follow_up_note},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200, response.text
        assert "进入主 Agent 处理" in response.text
        assert FOLLOW_UP_CONFIRMATION_RESOLVED_EVENT not in response.text
        assert [call["content"] for call in fake_runtime.calls] == [long_follow_up_note]

        messages_response = client.get(f"/v1/agent/sessions/{session['id']}/messages")
        assistant_message = messages_response.json()["items"][-1]
        assert assistant_message["payload_json"]["source"] == "langgraph"
    finally:
        engine.dispose()


def test_agent_runtime_state_api_reads_root_checkpoint(monkeypatch):
    class FakeRootRuntime:
        def __init__(self):
            self.calls = []

        async def current_checkpoint_state(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "runtime_status": "waiting",
                "current_interrupt": {"type": "confirm", "business_action": "CREATE_FOLLOW_UP"},
            }

    fake_runtime = FakeRootRuntime()
    monkeypatch.setattr(agent_api, "agent_root_runtime", fake_runtime)

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "运行态会话"}).json()

        response = client.get(f"/v1/agent/sessions/{session['id']}/runtime/state")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["session_id"] == session["id"]
        assert body["session_key"] == session["session_key"]
        assert body["values"]["runtime_status"] == "waiting"
        assert body["values"]["current_interrupt"]["business_action"] == "CREATE_FOLLOW_UP"
        assert fake_runtime.calls[0] == {
            "team_id": 1,
            "user_id": 2,
            "session_id": session["id"],
            "session_key": session["session_key"],
        }
    finally:
        engine.dispose()


def test_agent_runtime_history_api_exposes_langgraph_checkpoints(monkeypatch):
    class FakeRootRuntime:
        def __init__(self):
            self.calls = []

        async def state_history(self, **kwargs):
            self.calls.append(kwargs)
            return [
                {
                    "checkpoint_id": "cp-2",
                    "parent_checkpoint_id": "cp-1",
                    "thread_id": "crm_agent:1:2:3:key",
                    "checkpoint_ns": "crm_agent",
                    "source": "loop",
                    "step": 2,
                    "next_nodes": ["pending_task_subgraph"],
                    "has_interrupt": True,
                    "interrupts": [{"type": "confirm"}],
                    "values": {
                        "application_action": "execute_confirmed_task",
                        "current_interrupt": {"type": "confirm"},
                    },
                }
            ]

    fake_runtime = FakeRootRuntime()
    monkeypatch.setattr(agent_api, "agent_root_runtime", fake_runtime)

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "运行态历史"}).json()

        response = client.get(
            f"/v1/agent/sessions/{session['id']}/runtime/history",
            params={"before_checkpoint_id": "cp-3", "limit": 5},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["session_id"] == session["id"]
        assert body["total"] == 1
        assert body["before_checkpoint_id"] == "cp-3"
        assert body["limit"] == 5
        assert body["items"][0]["checkpoint_id"] == "cp-2"
        assert body["items"][0]["has_interrupt"] is True
        assert body["items"][0]["values"]["application_action"] == "execute_confirmed_task"
        assert fake_runtime.calls[0] == {
            "team_id": 1,
            "user_id": 2,
            "session_id": session["id"],
            "session_key": session["session_key"],
            "before_checkpoint_id": "cp-3",
            "limit": 5,
        }
    finally:
        engine.dispose()


def test_agent_runtime_checkpoint_api_reads_historical_state(monkeypatch):
    class FakeRootRuntime:
        def __init__(self):
            self.calls = []

        async def checkpoint_state_at(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "runtime_status": "waiting",
                "current_interrupt": {"type": "form", "reason": "missing_required_fields"},
                "events": [{"event": "agent_root_pending_task_effects_applied"}],
            }

    fake_runtime = FakeRootRuntime()
    monkeypatch.setattr(agent_api, "agent_root_runtime", fake_runtime)

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "历史状态"}).json()

        response = client.get(f"/v1/agent/sessions/{session['id']}/runtime/checkpoints/cp-1")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["session_id"] == session["id"]
        assert body["checkpoint_id"] == "cp-1"
        assert body["values"]["current_interrupt"]["reason"] == "missing_required_fields"
        assert fake_runtime.calls[0] == {
            "checkpoint_id": "cp-1",
            "team_id": 1,
            "user_id": 2,
            "session_id": session["id"],
            "session_key": session["session_key"],
        }
    finally:
        engine.dispose()


def test_agent_stream_does_not_inject_waiting_task_without_checkpoint_interrupt(monkeypatch):
    class FakeRootRuntime:
        def __init__(self):
            self.context_tasks = []

        async def run_turn(self, *, context, **kwargs):
            self.context_tasks.append(context.task)
            return {
                "application_action": "run_new_flow",
                "assistant_content": "按新一轮输入处理",
                "events": [{"event": "agent_root_new_flow_graph_completed"}],
            }

    fake_root_runtime = FakeRootRuntime()
    monkeypatch.setattr(agent_api.agent_application_module, "agent_root_runtime", fake_root_runtime)

    client, engine = _build_client(monkeypatch)
    Session = sessionmaker(bind=engine)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "跟进会话"})
        assert create_response.status_code == 201, create_response.text
        session = create_response.json()

        db = Session()
        try:
            db.add(
                AgentTask(
                    task_key="task-opportunity-fields",
                    team_id=1,
                    user_id=2,
                    session_id=session["id"],
                    intent="CREATE_OPPORTUNITY",
                    status=AgentTaskStatus.WAITING_USER,
                    target_type="customer",
                    target_id=101,
                    summary="等待补充商机信息",
                    state_json={
                        "action": "collect_opportunity_fields",
                        "customer": {"id": 101, "account_name": "广州睿狐科技有限公司"},
                        "payload": {
                            "customer_id": 101,
                            "missing_fields": ["total_amount", "license_type"],
                            "interaction_fields": ["total_amount", "license_type"],
                        },
                    },
                )
            )
            db.commit()
        finally:
            db.close()

        stream_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "预计成交金额10万，授权模式订阅"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert stream_response.status_code == 200, stream_response.text

        assert fake_root_runtime.context_tasks == [None]
    finally:
        engine.dispose()


def test_agent_stream_prefers_root_checkpoint_interrupt_over_session_projection(monkeypatch):
    class FakeRootRuntime:
        def __init__(self):
            self.run_calls = []

        async def run_turn(self, *, context, **kwargs):
            self.run_calls.append({"context": context, **kwargs})
            return {
                "application_action": "no_pending_confirmation",
                "assistant_content": "已按 checkpoint 恢复",
                "events": [{"event": "agent_root_interrupt_resumed"}],
            }

    fake_root_runtime = FakeRootRuntime()
    monkeypatch.setattr(agent_api.agent_application_module, "agent_root_runtime", fake_root_runtime)

    client, engine = _build_client(monkeypatch)
    Session = sessionmaker(bind=engine)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "跟进会话"})
        assert create_response.status_code == 201, create_response.text
        session = create_response.json()

        db = Session()
        try:
            saved_session = db.query(AgentSession).one()
            saved_session.context_json = {
                "current_interrupt": {
                    "type": "confirm",
                    "reason": "write_confirmation",
                    "business_action": "stale_session_action",
                    "allowed_resume_actions": ["reject"],
                }
            }
            db.commit()
        finally:
            db.close()

        stream_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "确认"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert stream_response.status_code == 200, stream_response.text

        assert fake_root_runtime.run_calls
        assert "stale_session_action" not in stream_response.text
    finally:
        engine.dispose()


def test_agent_stream_does_not_use_waiting_task_table_as_runtime_source(monkeypatch):
    class FakeRootRuntime:
        def __init__(self):
            self.run_context_task_keys = []

        async def run_turn(self, *, context, **kwargs):
            task = getattr(context, "task", None)
            self.run_context_task_keys.append(getattr(task, "task_key", None))
            return {
                "application_action": "no_pending_confirmation",
                "assistant_content": "已按 checkpoint task 恢复",
                "events": [{"event": "agent_root_interrupt_resumed"}],
            }

    fake_root_runtime = FakeRootRuntime()
    monkeypatch.setattr(agent_api.agent_application_module, "agent_root_runtime", fake_root_runtime)

    client, engine = _build_client(monkeypatch)
    Session = sessionmaker(bind=engine)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "投影冲突会话"}).json()
        db = Session()
        try:
            db.add(
                AgentTask(
                    task_key="task-waiting-db",
                    team_id=1,
                    user_id=2,
                    session_id=session["id"],
                    intent="CREATE_FOLLOW_UP",
                    status=AgentTaskStatus.WAITING_USER,
                    summary="等待确认",
                    state_json={"action": "create_customer_activity", "payload": {"customer_id": 101}},
                )
            )
            db.commit()
        finally:
            db.close()

        stream_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "确认"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert stream_response.status_code == 200, stream_response.text
        assert fake_root_runtime.run_context_task_keys == [None]
    finally:
        engine.dispose()


def test_agent_application_structured_confirm_resumes_checkpoint_interrupt_as_approve(monkeypatch):
    class FakeRootRuntime:
        def __init__(self):
            self.run_calls = []

        async def run_turn(self, *, turn_input, **kwargs):
            self.run_calls.append({"turn_input": turn_input, **kwargs})
            return {
                "application_action": "no_pending_confirmation",
                "assistant_content": "已按结构化确认恢复",
                "events": [{"event": "agent_root_interrupt_resumed"}],
            }

    fake_root_runtime = FakeRootRuntime()
    monkeypatch.setattr(agent_api.agent_application_module, "agent_root_runtime", fake_root_runtime)

    client, engine = _build_client(monkeypatch)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(agent_api.agent_application_module, "SessionLocal", lambda: Session())
    try:
        session = client.post("/v1/agent/sessions", json={"title": "确认会话"}).json()

        async def collect_events():
            events = []
            async for event in agent_api.agent_application_service.stream_chat_events(
                content="确认",
                team_id=1,
                user_id=2,
                authorization="Bearer test-token",
                session_id=session["id"],
                turn_input=AgentTurnInput.confirm(source="web"),
            ):
                events.append(event)
            return events

        events = asyncio.run(collect_events())

        assert fake_root_runtime.run_calls
        assert fake_root_runtime.run_calls[0]["turn_input"].kind.value == "confirm"
        assert any(event.get("content") == "已按结构化确认恢复" for event in events)
    finally:
        engine.dispose()


def test_agent_stream_uses_root_runtime_new_flow_side_effects(monkeypatch):
    class FakeRootRuntime:
        async def run_turn(self, *, context, **kwargs):
            context.side_effects.new_flow_events.extend([
                {"event": "agent_step", "step": "semantic_parse", "status": "started", "content": "AI 语义理解"},
                {"event": "final", "content": "root 已处理"},
            ])
            context.side_effects.new_flow_assistant_content = "root 已处理"
            return {
                "application_action": "run_new_flow",
                "assistant_content": "root 已处理",
                "events": [{"event": "agent_root_new_flow_graph_completed"}],
            }

    monkeypatch.setattr(agent_api.agent_application_module, "agent_root_runtime", FakeRootRuntime())

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "跟进会话"}).json()
        response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "今天和越秀金融沟通"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200, response.text
        assert '"event": "agent_step"' in response.text
        assert '"content": "root 已处理"' in response.text
        assert "application must not run new-flow directly" not in response.text
    finally:
        engine.dispose()


def test_agent_stream_uses_root_runtime_confirmed_task_side_effects(monkeypatch):
    class FakeRootRuntime:
        async def run_turn(self, *, context, **kwargs):
            task_projection = {
                "id": 501,
                "task_key": "task-follow-up",
                "status": AgentTaskStatus.WAITING_USER,
            }
            context.side_effects.confirmed_task_events.extend([
                {"event": "tool_result", "tool_name": "create_customer_activity", "success": True},
                {"event": "task_completed", "task_id": task_projection["id"], "content": "root 已执行"},
                {"event": "final", "content": "root 已执行"},
            ])
            context.side_effects.confirmed_task_assistant_content = "root 已执行"
            return {
                "task_projection": task_projection,
                "application_action": "execute_confirmed_task",
                "assistant_content": "root 已执行",
                "events": [{"event": "agent_root_confirmed_task_execution_completed"}],
            }

    monkeypatch.setattr(agent_api.agent_application_module, "agent_root_runtime", FakeRootRuntime())

    client, engine = _build_client(monkeypatch)
    Session = sessionmaker(bind=engine)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "确认会话"}).json()
        db = Session()
        try:
            db.add(
                AgentTask(
                    task_key="task-follow-up",
                    team_id=1,
                    user_id=2,
                    session_id=session["id"],
                    intent="CREATE_FOLLOW_UP",
                    status=AgentTaskStatus.WAITING_USER,
                    summary="等待确认跟进记录",
                    state_json={"action": "create_customer_activity", "payload": {"customer_id": 101}},
                )
            )
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "确认"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200, response.text
        assert '"event": "tool_result"' in response.text
        assert '"content": "root 已执行"' in response.text
        assert "application must not execute confirmed task directly" not in response.text
    finally:
        engine.dispose()


def test_agent_stream_falls_back_to_pending_graph_only_for_checkpoint_storage_errors(monkeypatch):
    class FakeRootRuntime:
        async def run_turn(self, **kwargs):
            raise SQLAlchemyError("checkpoint storage failed")

    class FakeCheckpointFallbackRuntime:
        def __init__(self):
            self.calls = []

        async def run(self, **kwargs):
            self.calls.append(kwargs)
            return agent_api.agent_application_module.AgentApplicationRuntimeResult(
                state={
                    "checkpoint_unavailable": True,
                    "fallback_reason": "checkpoint_storage_error",
                    "events": [{
                        "event": "agent_root_checkpoint_unavailable_fallback_started",
                        "runtime": "crm_agent_root",
                        "checkpoint_unavailable": True,
                        "fallback_reason": "checkpoint_storage_error",
                    }],
                },
                turn_output=AgentRuntimeTurnOutput(
                    events=[
                        {
                            "event": "agent_root_checkpoint_unavailable_fallback_started",
                            "runtime": "crm_agent_root",
                            "checkpoint_unavailable": True,
                            "fallback_reason": "checkpoint_storage_error",
                        },
                        {"event": "final", "content": "已切到 checkpoint 故障隔离处理。"},
                    ],
                    assistant_content="已切到 checkpoint 故障隔离处理。",
                ),
                pending_task_result={"handled": True},
                checkpoint_unavailable=True,
            )

    fake_checkpoint_fallback_runtime = FakeCheckpointFallbackRuntime()
    monkeypatch.setattr(agent_api.agent_application_module, "agent_root_runtime", FakeRootRuntime())
    monkeypatch.setattr(
        agent_api.agent_application_module,
        "agent_checkpoint_fallback_runtime",
        fake_checkpoint_fallback_runtime,
    )
    monkeypatch.setattr(agent_api.agent_application_module, "is_checkpoint_storage_error", lambda exc: True)

    client, engine = _build_client(monkeypatch)
    Session = sessionmaker(bind=engine)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "跟进会话"}).json()
        db = Session()
        try:
            db.add(
                AgentTask(
                    task_key="task-follow-up",
                    team_id=1,
                    user_id=2,
                    session_id=session["id"],
                    intent="CREATE_FOLLOW_UP",
                    status=AgentTaskStatus.WAITING_USER,
                    summary="等待确认跟进记录",
                    state_json={"action": "create_customer_activity", "payload": {"customer_id": 101}},
                )
            )
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "确认"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200, response.text
        assert "agent_root_checkpoint_unavailable_fallback_started" in response.text
        assert '"fallback_reason": "checkpoint_storage_error"' in response.text
        assert "已切到 checkpoint 故障隔离处理。" in response.text
        assert len(fake_checkpoint_fallback_runtime.calls) == 1
        assert fake_checkpoint_fallback_runtime.calls[0]["task"] is None

        messages_response = client.get(f"/v1/agent/sessions/{session['id']}/messages")
        assert messages_response.status_code == 200, messages_response.text
        assistant_message = messages_response.json()["items"][1]
        trace_events = assistant_message["payload_json"]["trace_events"]
        fallback_events = [
            event
            for event in trace_events
            if event.get("event") == "agent_root_checkpoint_unavailable_fallback_started"
        ]
        assert fallback_events
        assert fallback_events[0]["runtime"] == "crm_agent_root"
        assert fallback_events[0]["checkpoint_unavailable"] is True
        assert fallback_events[0]["fallback_reason"] == "checkpoint_storage_error"
    finally:
        engine.dispose()


def test_agent_stream_does_not_fallback_for_business_sqlalchemy_errors(monkeypatch):
    class FakeRootRuntime:
        async def run_turn(self, **kwargs):
            raise SQLAlchemyError("business db failed")

    class FakeCheckpointFallbackRuntime:
        def __init__(self):
            self.calls = []

        async def run(self, **kwargs):
            self.calls.append(kwargs)
            return agent_api.agent_application_module.AgentApplicationRuntimeResult(checkpoint_unavailable=True)

    fake_checkpoint_fallback_runtime = FakeCheckpointFallbackRuntime()
    monkeypatch.setattr(agent_api.agent_application_module, "agent_root_runtime", FakeRootRuntime())
    monkeypatch.setattr(
        agent_api.agent_application_module,
        "agent_checkpoint_fallback_runtime",
        fake_checkpoint_fallback_runtime,
    )
    monkeypatch.setattr(agent_api.agent_application_module, "is_checkpoint_storage_error", lambda exc: False)

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "跟进会话"}).json()
        response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "确认"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200, response.text
        assert "business db failed" in response.text
        assert fake_checkpoint_fallback_runtime.calls == []
    finally:
        engine.dispose()


def test_agent_stream_persists_assistant_error_when_runtime_fails_after_user_message(monkeypatch):
    class FakeRootRuntime:
        async def run_turn(self, **kwargs):
            raise RuntimeError("customer intelligence provider failed")

    monkeypatch.setattr(agent_api.agent_application_module, "agent_root_runtime", FakeRootRuntime())

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "跟进会话"}).json()
        response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "确认"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200, response.text
        assert '"event": "message"' in response.text
        assert '"role": "ASSISTANT"' in response.text
        assert '"event": "error"' in response.text

        messages_response = client.get(f"/v1/agent/sessions/{session['id']}/messages")
        assert messages_response.status_code == 200, messages_response.text
        messages = messages_response.json()["items"]
        assert [message["role"] for message in messages] == ["USER", "ASSISTANT"]
        assistant_message = messages[1]
        assert "customer intelligence provider failed" in assistant_message["content"]
        assert assistant_message["payload_json"]["source"] == "runtime_error_fallback"
        assert assistant_message["payload_json"]["recovered_for_user_message_id"] == messages[0]["id"]
    finally:
        engine.dispose()


async def test_root_runtime_isolates_customer_intelligence_graph_failure():
    class FakeCustomerIntelligenceGraphService:
        async def stream_run(self, graph_input):
            yield {
                "kind": "event",
                "event": {
                    "event": "agent_step",
                    "step": "customer_intelligence",
                    "status": "started",
                    "content": "更新客户智能档案",
                },
            }
            raise RuntimeError("LLM rate limited")

    published_events = []

    async def collect_event(event):
        published_events.append(event)

    runtime = AgentRootRuntime(customer_intelligence_graph_service=FakeCustomerIntelligenceGraphService())
    context = AgentRuntimeContext(
        db=object(),
        team_id=1,
        user_id=2,
        session_id=8,
        customer_intelligence_event={"customer_id": 144, "team_id": 1},
        side_effects=AgentRootRuntimeSideEffects(),
        event_sink=collect_event,
    )

    update = await runtime._run_customer_intelligence_graph(
        {"customer_intelligence_requested": True},
        SimpleNamespace(context=context),
    )

    assert update["customer_intelligence_requested"] is False
    assert update["customer_intelligence_result"]["handled"] is False
    assert update["customer_intelligence_result"]["reason"] == "customer_intelligence_graph_failed"
    assert any(
        event.get("event") == "agent_root_customer_intelligence_graph_failed"
        for event in context.side_effects.customer_intelligence_events
    )
    assert any(
        event.get("event") == "agent_root_customer_intelligence_graph_failed"
        for event in published_events
    )


def test_agent_event_interaction_protocol_for_confirmation():
    event = agent_api._with_interaction({
        "event": "confirmation_required",
        "content": "请确认是否创建这条客户活动？",
    })

    assert event["interaction"]["type"] == "choice"
    assert event["interaction"]["schema_version"] == "agent.interaction.v1"
    assert event["interaction"]["business_action"] == "confirm_action"
    assert event["interaction"]["status"] == "waiting_confirmation"
    assert event["interaction"]["title"] == "确认操作"
    assert event["interaction"]["prompt"] == "请确认是否创建这条客户活动？"
    assert event["interaction"]["choices"] == [
        {"label": "是", "value": "是"},
        {"label": "否", "value": "否"},
    ]
    assert event["interaction"]["allow_free_text"] is True
    assert event["interaction"]["allow_cancel"] is True


def test_agent_event_interaction_protocol_for_turn_relation_clarification():
    event = agent_api._with_interaction({
        "event": "turn_relation_clarification_required",
        "content": "你想继续哪个草稿？",
        "candidates": [
            {"id": 201, "summary": "广州睿狐增购10个账号补商机信息"},
            {"id": 202, "summary": "广州睿狐创建商机确认"},
        ],
    })

    interaction = event["interaction"]
    assert interaction["type"] == "choice"
    assert interaction["schema_version"] == "agent.interaction.v1"
    assert interaction["business_action"] == "select_suspended_task"
    assert interaction["status"] == "waiting_user_input"
    assert interaction["title"] == "选择处理方式"
    assert interaction["prompt"] == "你想继续哪个草稿？"
    assert interaction["choices"] == [
        {
            "label": "继续处理：广州睿狐增购10个账号补商机信息",
            "value": "继续处理：广州睿狐增购10个账号补商机信息",
            "metadata": {"selected_task_id": 201},
        },
        {
            "label": "继续处理：广州睿狐创建商机确认",
            "value": "继续处理：广州睿狐创建商机确认",
            "metadata": {"selected_task_id": 202},
        },
        {
            "label": "作为新流程处理",
            "value": "作为新流程处理",
            "metadata": {"turn_relation": "START_NEW_FLOW"},
        },
    ]


def test_agent_event_interaction_protocol_for_turn_relation_clarification_uses_display_summary_and_new_flow_choice():
    event = agent_api._with_interaction({
        "event": "turn_relation_clarification_required",
        "content": "这句是继续跟进草稿，还是新开一个流程？",
        "candidates": [
            {
                "id": 301,
                "summary": "等待确认执行：create_customer_activity",
                "display_summary": "确认记录跟进｜广州睿狐科技有限公司",
            },
        ],
    })

    interaction = event["interaction"]
    assert interaction["choices"] == [
        {
            "label": "继续处理：确认记录跟进｜广州睿狐科技有限公司",
            "value": "继续处理：确认记录跟进｜广州睿狐科技有限公司",
            "metadata": {"selected_task_id": 301},
        },
        {
            "label": "作为新流程处理",
            "value": "作为新流程处理",
            "metadata": {"turn_relation": "START_NEW_FLOW"},
        },
    ]


def test_agent_event_interaction_protocol_for_turn_relation_clarification_hides_legacy_action_summary():
    event = agent_api._with_interaction({
        "event": "turn_relation_clarification_required",
        "content": "这句是继续「等待确认执行：create_customer_activity」，还是新开一个流程？",
        "candidates": [
            {
                "id": 301,
                "summary": "等待确认执行：create_customer_activity",
                "action": "create_customer_activity",
                "customer_name": "广州睿狐科技有限公司",
            },
        ],
    })

    interaction = event["interaction"]
    labels = [choice["label"] for choice in interaction["choices"]]
    assert labels == ["继续处理：确认记录跟进｜广州睿狐科技有限公司", "作为新流程处理"]
    assert "create_customer_activity" not in str(interaction)


def test_agent_event_interaction_protocol_for_missing_opportunity_fields():
    event = agent_api._with_interaction({
        "event": "opportunity_fields_required",
        "content": "还需要补充商机信息",
        "payload": {
            "missing_fields": [
                "total_amount",
                "user_count",
                "license_type",
                "expected_closing_date",
                "purchase_type",
            ],
        },
    })

    interaction = event["interaction"]
    assert interaction["type"] == "form"
    assert interaction["schema_version"] == "agent.interaction.v1"
    assert interaction["business_action"] == "create_opportunity"
    assert interaction["status"] == "waiting_user_input"
    assert interaction["title"] == "补充商机信息"
    assert interaction["payload"]["missing_fields"] == [
        "total_amount",
        "user_count",
        "license_type",
        "expected_closing_date",
        "purchase_type",
    ]
    assert interaction["prompt"] == "还需要补充商机信息"
    assert [field["key"] for field in interaction["fields"]] == [
        "total_amount",
        "user_count",
        "license_type",
        "expected_closing_date",
        "purchase_type",
    ]
    assert [field["type"] for field in interaction["fields"]] == [
        "number",
        "number",
        "select",
        "date",
        "select",
    ]


def test_agent_event_interaction_protocol_for_missing_lead_fields():
    event = agent_api._with_interaction({
        "event": "lead_fields_required",
        "content": "还需要补充线索信息",
        "payload": {
            "missing_fields": [
                "lead_name",
                "city",
                "contact_name",
                "contact_phone",
                "company_scale",
            ],
        },
    })

    interaction = event["interaction"]
    assert interaction["type"] == "form"
    assert interaction["schema_version"] == "agent.interaction.v1"
    assert interaction["business_action"] == "create_lead"
    assert interaction["title"] == "补充线索信息"
    assert interaction["prompt"] == "还需要补充线索信息"
    assert [field["key"] for field in interaction["fields"]] == [
        "lead_name",
        "city",
        "contact_name",
        "contact_phone",
        "company_scale",
    ]
    assert [field["type"] for field in interaction["fields"]] == [
        "text",
        "text",
        "text",
        "text",
        "select",
    ]


def test_agent_tool_payload_for_create_lead_defaults_source():
    payload = _tool_payload_for_action(
        "create_lead",
        {
            "lead": {
                "lead_name": "广州睿狐科技",
                "city": "广州",
                "contact_name": "王总",
                "contact_phone": "13800138000",
            },
        },
        customer={},
        task_key="task-lead-001",
    )

    assert payload == {
        "lead": {
            "lead_name": "广州睿狐科技",
            "city": "广州",
            "contact_name": "王总",
            "contact_phone": "13800138000",
            "source": "其他",
        },
        "idempotency_suffix": "task-lead-001",
    }


def test_agent_tool_payload_for_create_opportunity_strips_draft_fields():
    payload = _tool_payload_for_action(
        "create_opportunity",
        {
            "customer_id": 101,
            "opportunity": {
                "customer_id": 101,
                "opportunity_name": "广州睿狐科技 100人订阅商机",
                "total_amount": 50000,
                "user_count": 100,
                "license_type": "SUBSCRIPTION",
                "subscription_years": 1,
                "purchase_type": "NEW",
                "expected_closing_date_text": "8 月底",
                "expected_closing_date": "2026-08-31",
            },
        },
        customer={"id": 101, "account_name": "广州睿狐科技有限公司"},
        task_key="task-opportunity-001",
    )

    assert payload == {
        "opportunity": {
            "customer_id": 101,
            "total_amount": 50000,
            "user_count": 100,
            "license_type": "SUBSCRIPTION",
            "subscription_years": 1,
            "purchase_type": "NEW",
            "expected_closing_date": "2026-08-31",
        },
        "idempotency_suffix": "task-opportunity-001",
    }


def test_agent_event_interaction_protocol_for_follow_up_quality():
    event = agent_api._with_interaction({
        "event": "follow_up_quality_required",
        "content": "下一步计划什么时候、由谁跟进？",
    })

    assert event["interaction"]["type"] == "text"
    assert event["interaction"]["schema_version"] == "agent.interaction.v1"
    assert event["interaction"]["business_action"] == "create_follow_up"
    assert event["interaction"]["title"] == "补充跟进记录"
    assert event["interaction"]["prompt"] == "下一步计划什么时候、由谁跟进？"
    assert event["interaction"]["allow_free_text"] is True
    assert event["interaction"]["allow_cancel"] is True


def test_agent_event_interaction_protocol_for_customer_selection():
    event = agent_api._with_interaction({
        "event": "customer_selection_required",
        "content": "找到多个客户，请选择",
        "customers": [
            {"id": 1, "account_name": "广州睿狐科技有限公司"},
            {"id": 2, "account_name": "深圳睿狐科技有限公司"},
        ],
    })

    assert event["interaction"]["type"] == "choice"
    assert event["interaction"]["schema_version"] == "agent.interaction.v1"
    assert event["interaction"]["business_action"] == "select_customer"
    assert event["interaction"]["title"] == "选择客户"
    assert event["interaction"]["choices"] == [
        {
            "label": "广州睿狐科技有限公司",
            "value": "1",
            "metadata": {
                "resource_type": "customer",
                "choice_index": 1,
                "selected_customer_id": 1,
                "resource_id": 1,
            },
        },
        {
            "label": "深圳睿狐科技有限公司",
            "value": "2",
            "metadata": {
                "resource_type": "customer",
                "choice_index": 2,
                "selected_customer_id": 2,
                "resource_id": 2,
            },
        },
    ]


def test_agent_event_interaction_protocol_for_business_selection_hides_internal_identifiers():
    event = agent_api._with_interaction({
        "event": "business_selection_required",
        "content": "找到多个商机，请选择",
        "opportunities": [
            {
                "id": 11,
                "opportunity_name": "越秀 CRM 一期",
                "purchase_type": "NEW",
                "procurement_method_id": 2,
                "procurement_method_name": "公开招标",
                "expected_closing_date": "2026-12-31",
                "current_stage_name": "方案交流",
                "target_stage_template_id": 9,
                "target_stage_name": "POC",
            },
        ],
    })

    serialized = json.dumps(event["interaction"], ensure_ascii=False)
    assert "procurement_method_id" not in serialized
    assert "target_stage_template_id" not in serialized
    assert "越秀 CRM 一期" in event["interaction"]["choices"][0]["label"]
    assert "公开招标" in event["interaction"]["choices"][0]["label"]
    assert event["interaction"]["choices"][0]["value"] == "1"
    assert event["interaction"]["choices"][0]["metadata"] == {
        "resource_type": "opportunity",
        "choice_index": 1,
        "selected_opportunity_id": 11,
        "resource_id": 11,
    }


def test_agent_stream_creates_waiting_task_and_executes_confirmation(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "confirmation_required",
                "action": "create_customer_activity",
                "customer": {"id": 101, "account_name": "越秀金融"},
                "payload": {
                    "customer_id": 101,
                    "content": input_state["content"],
                    "next_action": "下周三继续跟进",
                    "next_follow_time_text": "下周三",
                    "next_follow_time_iso": "2026-07-29T09:00:00",
                },
            }
            yield {"event": "final", "content": "请确认是否创建这条客户活动？"}

    class FakeToolService:
        async def create_customer_activity(self, context, **kwargs):
            assert context.authorization == "Bearer test-token"
            assert context.task_id is not None
            assert kwargs["customer_id"] == 101
            assert kwargs["customer_name"] == "越秀金融"
            assert kwargs["source_content"] == "今天和越秀金融的王总沟通了项目进展，下周三继续跟进"
            assert kwargs["next_follow_time"] == "2026-07-29T09:00:00"
            return AgentToolResult(
                tool_name="create_customer_activity",
                success=True,
                data={"id": 9001, "customer_id": 101},
                tool_call_id=7001,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "跟进会话"})
        session = create_response.json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={
                "session_id": session["id"],
                "content": "今天和越秀金融的王总沟通了项目进展，下周三继续跟进",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "confirmation_required"' in plan_response.text
        assert '"task_id": 1' in plan_response.text

        confirm_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert '"event": "task_completed"' in confirm_response.text
        assert "客户活动已记录" in confirm_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.COMPLETED
            assert task.result_json == {"id": 9001, "customer_id": 101}
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_defers_follow_up_next_task_until_after_follow_up_created(monkeypatch):
    customer = {"id": 101, "account_name": "汇川技术", "owner_info": {"id": 2}, "collaborator_infos": []}

    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "confirmation_required",
                "action": "create_customer_activity",
                "customer": customer,
                "payload": {
                    "customer_id": 101,
                    "content": input_state["content"],
                    "method": "微信",
                    "_next_task": {
                        "action": "collect_opportunity_fields",
                        "customer": customer,
                        "payload": {
                            "customer_id": 101,
                            "opportunity": {"customer_id": 101, "purchase_type": "RENEWAL"},
                            "missing_fields": ["total_amount", "user_count", "license_type", "expected_closing_date"],
                        },
                        "content": "这条像续费商机，要不要我继续帮你补齐商机信息？",
                    },
                },
            }
            yield {"event": "final", "content": "请确认是否创建这条客户活动？"}

    class FakeToolService:
        async def create_customer_activity(self, context, **kwargs):
            return AgentToolResult(
                tool_name="create_customer_activity",
                success=True,
                data={"id": 9001, "customer_id": 101},
                tool_call_id=7001,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())
    monkeypatch.setattr(agent_api, "agent_semantic_parser", FakeSemanticParser({
        "intent": "CREATE_OPPORTUNITY",
        "intent_confidence": 0.95,
        "customer": {"name_text": "汇川技术", "confidence": 0.95, "resolution_source": "MEMORY"},
        "follow_up": {},
        "payment": {},
        "opportunity": {},
        "contact": {},
        "invoice_title": {},
        "deployment_info": {},
        "business_signals": [],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": [],
    }))

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "跟进会话"}).json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "今天微信找了汇川技术沟通续费"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert "请确认是否创建这条客户活动" in plan_response.text
        assert '"event": "final", "content": "请确认是否创建这条客户活动？"' in plan_response.text

        confirm_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert "客户活动已记录" in confirm_response.text
        assert "要不要我继续帮你补齐商机信息" in confirm_response.text
        assert '"next_task_id": 2' in confirm_response.text
        assert '"interaction":' in confirm_response.text

        yes_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert yes_response.status_code == 200, yes_response.text
        assert "还差商机" in yes_response.text
        assert "预计成交金额" in yes_response.text
    finally:
        engine.dispose()


def test_agent_stream_cancels_waiting_task_when_user_rejects(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "confirmation_required",
                "action": "create_customer_activity",
                "customer": {"id": 101, "account_name": "越秀金融"},
                "payload": {
                    "customer_id": 101,
                    "content": input_state["content"],
                },
            }
            yield {"event": "final", "content": "请确认是否创建这条客户活动？"}

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "跟进会话"}).json()
        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "今天和越秀金融沟通了项目进展"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text

        reject_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "先不处理"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert reject_response.status_code == 200, reject_response.text
        assert '"event": "task_cancelled"' in reject_response.text
        assert "好嘞，这一步先放着。" in reject_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.SUSPENDED
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_persists_current_customer_memory(monkeypatch):
    customer = {
        "id": 101,
        "account_name": "广州睿狐科技有限公司",
        "owner_info": {"id": 2},
        "collaborator_infos": [{"id": 9}],
    }

    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "business_context_loaded",
                "customer_id": customer["id"],
                "customer": customer,
            }
            yield {"event": "final", "content": "已加载客户上下文。"}

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "记忆会话"})
        session = create_response.json()

        stream_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "睿狐科技今天回了 5 万"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert stream_response.status_code == 200, stream_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            saved_session = db.query(AgentSession).one()
            assert saved_session.context_json["current_customer"] == customer
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_restores_current_customer_memory_on_next_turn(monkeypatch):
    customer = {
        "id": 101,
        "account_name": "广州睿狐科技有限公司",
        "owner_info": {"id": 2},
        "collaborator_infos": [],
    }
    captured_states = []

    class FakeGraphService:
        async def stream_events(self, input_state):
            captured_states.append(input_state)
            if len(captured_states) == 1:
                yield {
                    "event": "business_context_loaded",
                    "customer_id": customer["id"],
                    "customer": customer,
                }
                yield {"event": "final", "content": "已识别广州睿狐科技有限公司。"}
            else:
                yield {"event": "final", "content": "已继承客户上下文。"}

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "记忆会话"})
        session = create_response.json()

        first_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "睿狐科技今天回了 5 万"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert first_response.status_code == 200, first_response.text

        second_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "那帮我创建一个商机，5 万 100 人使用，订阅 1 年"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert second_response.status_code == 200, second_response.text
        assert captured_states[1]["session_context"]["current_customer"] == customer
    finally:
        engine.dispose()


def test_agent_stream_collects_opportunity_fields_without_rerunning_graph(monkeypatch):
    customer = {
        "id": 101,
        "account_name": "广州睿狐科技有限公司",
        "owner_info": {"id": 2},
        "collaborator_infos": [],
    }

    class FakeGraphService:
        def __init__(self):
            self.calls = []

        async def stream_events(self, input_state):
            self.calls.append(input_state)
            yield {
                "event": "opportunity_fields_required",
                "action": "collect_opportunity_fields",
                "customer": customer,
                "payload": {
                    "customer_id": customer["id"],
                    "opportunity": {
                        "customer_id": customer["id"],
                        "total_amount": 50000,
                        "user_count": 100,
                        "license_type": "SUBSCRIPTION",
                        "subscription_years": 1,
                    },
                    "missing_fields": ["purchase_type", "expected_closing_date"],
                },
            }
            yield {"event": "final", "content": "请补充采购类型和预计成交日期。"}

    fake_graph = FakeGraphService()
    monkeypatch.setattr(agent_api, "crm_agent_graph_service", fake_graph)
    monkeypatch.setattr(agent_api, "agent_semantic_parser", FakeSemanticParser({
        "intent": "CREATE_OPPORTUNITY",
        "intent_confidence": 0.95,
        "customer": {"name_text": "广州睿狐科技有限公司", "confidence": 0.95, "resolution_source": "MEMORY"},
        "follow_up": {},
        "payment": {},
        "opportunity": {
            "purchase_type": "NEW",
            "expected_closing_date_text": "下个月30号",
            "expected_closing_date": {
                "raw_text": "下个月30号",
                "kind": "EXPLICIT_DATE",
                "direction": "future",
                "date_text": "2026-08-30",
                "confidence": 0.9,
            },
        },
        "contact": {},
        "invoice_title": {},
        "deployment_info": {},
        "business_signals": [],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": ["新购，下个月30号成交"],
    }))

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "商机会话"})
        session = create_response.json()

        first_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "好的，帮我创建一个商机，5 万，100 人，1 年订阅"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert first_response.status_code == 200, first_response.text
        assert '"event": "opportunity_fields_required"' in first_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            assert db.query(AgentSession).one().context_json is None
        finally:
            db.close()

        second_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "新购的，预计下个月 30 号成"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert second_response.status_code == 200, second_response.text
        assert '"event": "confirmation_required"' in second_response.text
        assert '"type": "choice"' in second_response.text
        assert "商机信息齐了" in second_response.text
        assert len(fake_graph.calls) == 1

        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.state_json["action"] == "create_opportunity"
            opportunity = task.state_json["payload"]["opportunity"]
            assert opportunity["total_amount"] == 50000
            assert opportunity["user_count"] == 100
            assert opportunity["license_type"] == "SUBSCRIPTION"
            assert opportunity["subscription_years"] == 1
            assert opportunity["purchase_type"] == "NEW"
            assert opportunity["expected_closing_date"] == "2026-08-30"
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_cancels_active_form_interrupt_for_plain_skip_text(monkeypatch):
    customer = {
        "id": 101,
        "account_name": "广州睿狐科技有限公司",
        "owner_info": {"id": 2},
        "collaborator_infos": [],
    }

    class FakeGraphService:
        def __init__(self):
            self.calls = []

        async def stream_events(self, input_state):
            self.calls.append(input_state)
            yield {
                "event": "opportunity_fields_required",
                "action": "collect_opportunity_fields",
                "customer": customer,
                "payload": {
                    "customer_id": customer["id"],
                    "opportunity": {
                        "customer_id": customer["id"],
                        "total_amount": 50000,
                    },
                    "missing_fields": ["purchase_type", "expected_closing_date"],
                },
            }
            yield {"event": "final", "content": "请补充采购类型和预计成交日期。"}

    fake_graph = FakeGraphService()
    monkeypatch.setattr(agent_api, "crm_agent_graph_service", fake_graph)

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "商机会话"}).json()

        first_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮广州睿狐科技建一个商机，金额 5 万"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert first_response.status_code == 200, first_response.text
        assert '"event": "opportunity_fields_required"' in first_response.text

        second_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "暂不处理"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert second_response.status_code == 200, second_response.text
        assert '"event": "turn_intent_classified"' in second_response.text
        assert '"intent": "CANCEL_CURRENT_TASK"' in second_response.text
        assert '"resume_action": "cancel"' in second_response.text
        assert '"event": "task_cancelled"' in second_response.text
        assert "还差商机" not in second_response.text
        assert len(fake_graph.calls) == 1

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.SUSPENDED
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_skips_optional_suggestion_form_interrupt_for_plain_skip_text(monkeypatch):
    customer = {
        "id": 101,
        "account_name": "广州睿狐科技有限公司",
        "owner_info": {"id": 2},
        "collaborator_infos": [],
    }

    class FakeGraphService:
        def __init__(self):
            self.calls = []

        async def stream_events(self, input_state):
            self.calls.append(input_state)
            workflow = action_workflow.optional_suggestion_contract(action="collect_opportunity_fields")
            payload = {
                "customer_id": customer["id"],
                "opportunity": {
                    "customer_id": customer["id"],
                    "total_amount": 50000,
                },
                "missing_fields": ["purchase_type", "expected_closing_date"],
            }
            yield {
                "event": "opportunity_fields_required",
                "action": "collect_opportunity_fields",
                "customer": customer,
                "workflow": workflow,
                "payload": {**payload, "workflow": workflow},
            }
            yield {"event": "final", "content": "请补充采购类型和预计成交日期。"}

    fake_graph = FakeGraphService()
    monkeypatch.setattr(agent_api, "crm_agent_graph_service", fake_graph)

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "商机会话"}).json()

        first_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "今天记录一条广州睿狐科技的续费跟进"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert first_response.status_code == 200, first_response.text
        assert '"event": "opportunity_fields_required"' in first_response.text

        second_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "暂不处理"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert second_response.status_code == 200, second_response.text
        assert '"event": "turn_intent_classified"' in second_response.text
        assert '"intent": "DISMISS_CURRENT_SUGGESTION"' in second_response.text
        assert '"resume_action": "skip_current_action"' in second_response.text
        assert '"event": "workflow_action_skipped"' in second_response.text
        assert '"event": "task_cancelled"' not in second_response.text
        assert len(fake_graph.calls) == 1

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.SUSPENDED
            assert task.state_json["suspension_kind"] == "dismissed"
            assert task.state_json["dismissed_reason"] == "暂不处理"
            assert task.state_json["workflow"]["status"] == "skipped"
            assert task.state_json["workflow"]["status_reason"] == "暂不处理"
            assert task.state_json["workflow"]["status_source"] == "langgraph_resume"
            ledger_action = db.query(AgentWorkflowAction).one()
            assert ledger_action.task_id == task.id
            assert ledger_action.action_id == task.state_json["workflow"]["action_id"]
            assert ledger_action.status == "SKIPPED"
            assert ledger_action.status_reason == "暂不处理"
            assert ledger_action.decision_json["decision"] == "skip_current_action"
        finally:
            db.close()
    finally:
        engine.dispose()


def test_opportunity_interaction_includes_subscription_years_with_license_type():
    fields = _opportunity_interaction_fields(
        ["total_amount", "user_count", "license_type"],
        {"id": 101, "account_name": "测试客户"},
    )

    assert fields == [
        "total_amount",
        "user_count",
        "license_type",
        "subscription_years",
        "procurement_method_id",
    ]


def test_opportunity_interaction_uses_procurement_method_default(monkeypatch):
    monkeypatch.setattr(
        agent_api,
        "_procurement_method_options",
        lambda db, team_id: [{"label": "公开招标", "value": "3"}],
    )
    event = {
        "event": "opportunity_fields_required",
        "content": "还需要补充：授权模式、采购方式。",
        "payload": {
            "missing_fields": ["license_type"],
            "interaction_fields": ["license_type", "subscription_years", "procurement_method_id"],
            "field_defaults": {"procurement_method_id": 3},
        },
    }

    interaction = agent_api._interaction_for_event(event, db=None, team_id=1)

    fields = interaction["fields"]
    assert [field["key"] for field in fields] == ["license_type", "subscription_years", "procurement_method_id"]
    procurement_field = next(field for field in fields if field["key"] == "procurement_method_id")
    assert procurement_field["default_value"] == "3"


def test_agent_stream_create_opportunity_completion_is_terminal(monkeypatch):
    customer = {
        "id": 101,
        "account_name": "广州睿狐科技有限公司",
        "owner_info": {"id": 2},
        "collaborator_infos": [],
    }

    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "confirmation_required",
                "action": "create_opportunity",
                "customer": customer,
                "payload": {
                    "customer_id": customer["id"],
                    "opportunity": {
                        "customer_id": customer["id"],
                        "total_amount": 50000,
                        "user_count": 100,
                        "license_type": "SUBSCRIPTION",
                        "subscription_years": 1,
                        "purchase_type": "NEW",
                        "expected_closing_date_text": "8 月底",
                        "expected_closing_date": "2026-08-30",
                    },
                },
            }
            yield {"event": "final", "content": "请确认是否创建商机？"}

    class FakeToolService:
        async def create_opportunity(self, context, **kwargs):
            assert kwargs["opportunity"]["customer_id"] == customer["id"]
            assert "expected_closing_date_text" not in kwargs["opportunity"]
            return AgentToolResult(
                tool_name="create_opportunity",
                success=True,
                data={"id": 3001, "customer_id": customer["id"]},
                tool_call_id=7001,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "商机会话"}).json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮我给睿狐科技创建商机"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "confirmation_required"' in plan_response.text

        confirm_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert '"event": "task_completed"' in confirm_response.text
        assert "商机已创建，并已按系统现有流程提交审批。" in confirm_response.text
        assert '"interaction":' not in confirm_response.text
        assert "继续处理" not in confirm_response.text
    finally:
        engine.dispose()


def test_agent_stream_create_lead_follow_up_runs_quality_before_confirmation(monkeypatch):
    quality = FakeQualityEvaluator({
        "score": 86,
        "passed": True,
        "reason": "质量达标",
        "missing_aspects": [],
        "supplement_question": None,
        "suggested_revision": "客户对 CRM 有明确兴趣，计划下周三电话跟进需求细节。",
        "principle_scores": {},
    })
    tool_calls = []

    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "confirmation_required",
                "action": "create_lead",
                "payload": {
                    "lead": {
                        "lead_name": "广州睿狐科技",
                        "source": "其他",
                        "city": "广州",
                        "contact_name": "王总",
                        "contact_phone": "13800138000",
                    },
                    "lead_follow_up": {
                        "content": "客户对 CRM 有明确兴趣",
                        "method": "电话",
                        "next_action": "下周三电话跟进需求细节",
                        "next_follow_time_iso": "2026-07-29T09:00:00",
                    },
                },
            }
            yield {"event": "final", "content": "请确认是否创建线索？"}

    class FakeToolService:
        async def create_lead(self, context, **kwargs):
            tool_calls.append(("create_lead", kwargs))
            return AgentToolResult(
                tool_name="create_lead",
                success=True,
                data={"id": 8101, **kwargs["lead"]},
                tool_call_id=7001,
            )

        async def create_lead_follow_up(self, context, **kwargs):
            tool_calls.append(("create_lead_follow_up", kwargs))
            return AgentToolResult(
                tool_name="create_lead_follow_up",
                success=True,
                data={"id": 8201, "lead_id": kwargs["lead_id"]},
                tool_call_id=7002,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())
    monkeypatch.setattr(agent_api, "agent_follow_up_quality_evaluator", quality)

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "线索会话"}).json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮我创建广州睿狐科技线索，客户对 CRM 有明确兴趣"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "confirmation_required"' in plan_response.text

        create_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert create_response.status_code == 200, create_response.text
        assert "线索已创建。请确认是否同步创建线索跟进记录？" in create_response.text
        assert '"next_task_id": 2' in create_response.text
        assert len(quality.calls) == 1
        assert quality.calls[0]["semantic_result"].intent == "CREATE_LEAD"

        follow_up_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert follow_up_response.status_code == 200, follow_up_response.text
        assert "线索跟进记录已创建。" in follow_up_response.text
        assert [name for name, _ in tool_calls] == ["create_lead", "create_lead_follow_up"]
        assert tool_calls[1][1]["content"] == "客户对 CRM 有明确兴趣，计划下周三电话跟进需求细节。"
    finally:
        engine.dispose()


def test_agent_stream_create_customer_activity_runs_quality_before_confirmation(monkeypatch):
    quality = FakeQualityEvaluator({
        "score": 88,
        "passed": True,
        "reason": "质量达标",
        "missing_aspects": [],
        "supplement_question": None,
        "suggested_revision": "客户已确认采购 CRM 的初步意向，计划下周三电话跟进需求细节和预算。",
        "principle_scores": {},
    })
    tool_calls = []

    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "confirmation_required",
                "action": "create_customer",
                "payload": {
                    "customer": {
                        "account_name": "广州睿狐科技有限公司",
                        "source": "其他",
                        "city": "广州",
                        "contact_name": "王总",
                        "contact_phone": "13800138000",
                        "contact_position": "总经理",
                        "contact_gender": "男",
                    },
                    "customer_activity": {
                        "content": "客户已确认采购 CRM 的初步意向",
                        "method": "电话",
                        "next_action": "下周三电话跟进需求细节和预算",
                        "next_follow_time_iso": "2026-07-29T09:00:00",
                    },
                },
            }
            yield {"event": "final", "content": "请确认是否创建客户？"}

    class FakeToolService:
        async def create_customer(self, context, **kwargs):
            tool_calls.append(("create_customer", kwargs))
            assert kwargs["customer"]["primary_contact"] == {
                "name": "王总",
                "mobile": "13800138000",
                "position": "总经理",
                "gender": "1",
                "is_decision_maker": False,
            }
            return AgentToolResult(
                tool_name="create_customer",
                success=True,
                data={"id": 9101, "account_name": kwargs["customer"]["account_name"]},
                tool_call_id=7001,
            )

        async def create_customer_activity(self, context, **kwargs):
            tool_calls.append(("create_customer_activity", kwargs))
            return AgentToolResult(
                tool_name="create_customer_activity",
                success=True,
                data={"id": 9201, "customer_id": kwargs["customer_id"]},
                tool_call_id=7002,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())
    monkeypatch.setattr(agent_api, "agent_follow_up_quality_evaluator", quality)

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "客户会话"}).json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮我创建广州睿狐科技客户，客户已确认采购 CRM 的初步意向"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "confirmation_required"' in plan_response.text

        create_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert create_response.status_code == 200, create_response.text
        assert "客户已创建。请确认是否同步创建客户活动？" in create_response.text
        assert '"next_task_id": 2' in create_response.text
        assert len(quality.calls) == 1
        assert quality.calls[0]["semantic_result"].intent == "CUSTOMER_ACTIVITY"

        follow_up_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert follow_up_response.status_code == 200, follow_up_response.text
        assert "客户活动已记录。" in follow_up_response.text
        assert [name for name, _ in tool_calls] == ["create_customer", "create_customer_activity"]
        assert tool_calls[1][1]["source_content"] == "客户已确认采购 CRM 的初步意向"
        assert tool_calls[1][1]["customer_id"] == 9101
    finally:
        engine.dispose()


def test_agent_stream_create_lead_follow_up_requires_quality_supplement(monkeypatch):
    quality = FakeQualityEvaluator([
        {
            "score": 42,
            "passed": False,
            "reason": "缺少下一步动作",
            "missing_aspects": ["下一步动作"],
            "supplement_question": "请补充下一步由谁在什么时间做什么。",
            "suggested_revision": None,
            "principle_scores": {},
        },
        {
            "score": 82,
            "passed": True,
            "reason": "质量达标",
            "missing_aspects": [],
            "supplement_question": None,
            "suggested_revision": "客户对 CRM 有兴趣，计划下周三由销售电话跟进需求和预算。",
            "principle_scores": {},
        },
    ])
    tool_calls = []

    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "confirmation_required",
                "action": "create_lead",
                "payload": {
                    "lead": {
                        "lead_name": "广州睿狐科技",
                        "source": "其他",
                        "city": "广州",
                        "contact_name": "王总",
                        "contact_phone": "13800138000",
                    },
                    "lead_follow_up": {
                        "content": "客户对 CRM 有兴趣",
                        "method": "电话",
                    },
                },
            }
            yield {"event": "final", "content": "请确认是否创建线索？"}

    class FakeToolService:
        async def create_lead(self, context, **kwargs):
            tool_calls.append(("create_lead", kwargs))
            return AgentToolResult(
                tool_name="create_lead",
                success=True,
                data={"id": 8101, **kwargs["lead"]},
                tool_call_id=7001,
            )

        async def create_lead_follow_up(self, context, **kwargs):
            tool_calls.append(("create_lead_follow_up", kwargs))
            return AgentToolResult(
                tool_name="create_lead_follow_up",
                success=True,
                data={"id": 8201, "lead_id": kwargs["lead_id"]},
                tool_call_id=7002,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())
    monkeypatch.setattr(agent_api, "agent_follow_up_quality_evaluator", quality)
    monkeypatch.setattr(agent_api, "agent_semantic_parser", FakeSemanticParser({
        "intent": "CREATE_LEAD",
        "intent_confidence": 0.95,
        "customer": {"name_text": None, "confidence": 0.0, "resolution_source": "NONE"},
        "follow_up": {},
        "payment": {},
        "lead": {
            "follow_up_content": "计划下周三由销售电话跟进需求和预算",
            "follow_up_method": "电话",
            "next_action": "由销售电话跟进需求和预算",
            "next_follow_time_text": "下周三",
        },
        "opportunity": {},
        "contact": {},
        "invoice_title": {},
        "deployment_info": {},
        "customer_member": {},
        "business_signals": [],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": ["计划下周三由销售电话跟进需求和预算"],
    }))

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "线索会话"}).json()
        client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮我创建广州睿狐科技线索，客户对 CRM 有兴趣"},
            headers={"Authorization": "Bearer test-token"},
        )

        create_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert create_response.status_code == 200, create_response.text
        assert "线索已创建。请补充下一步由谁在什么时间做什么。" in create_response.text
        assert '"next_task_id": 2' in create_response.text

        supplement_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "计划下周三由销售电话跟进需求和预算"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert supplement_response.status_code == 200, supplement_response.text
        assert '"event": "confirmation_required"' in supplement_response.text
        assert "线索跟进内容已补齐" in supplement_response.text
        assert len(quality.calls) == 2

        follow_up_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert follow_up_response.status_code == 200, follow_up_response.text
        assert "线索跟进记录已创建。" in follow_up_response.text
        assert [name for name, _ in tool_calls] == ["create_lead", "create_lead_follow_up"]
        assert tool_calls[1][1]["content"] == "客户对 CRM 有兴趣，计划下周三由销售电话跟进需求和预算。"
    finally:
        engine.dispose()


def test_agent_stream_collects_follow_up_quality_fields_without_rerunning_graph(monkeypatch):
    customer = {
        "id": 101,
        "account_name": "广州凡亚信息科技有限公司",
        "owner_info": {"id": 2},
        "collaborator_infos": [],
    }

    class FakeGraphService:
        def __init__(self):
            self.calls = []

        async def stream_events(self, input_state):
            self.calls.append(input_state)
            yield {
                "event": "follow_up_quality_required",
                "action": "collect_follow_up_quality_fields",
                "customer": customer,
                "payload": {
                    "customer_id": customer["id"],
                    "content": "凡亚信息今天反馈项目没进展",
                    "method": "AI录入",
                    "next_action": None,
                    "next_follow_time_text": None,
                    "next_follow_time_iso": None,
                },
                "content": "下一步计划什么时候、由谁、跟凡亚信息做什么跟进？",
            }
            yield {"event": "final", "content": "下一步计划什么时候、由谁、跟凡亚信息做什么跟进？"}

    class FakeQualityEvaluator:
        def __init__(self):
            self.calls = []

        async def evaluate_with_metadata(self, db, *, team_id, user_message, semantic_result, memory=None, current_date=None):
            self.calls.append({
                "team_id": team_id,
                "user_message": user_message,
                "semantic_result": semantic_result,
                "memory": memory,
                "current_date": current_date,
            })
            return SimpleNamespace(
                result=SimpleNamespace(
                    passed=True,
                    score=72,
                    suggested_revision="凡亚信息反馈项目暂无进展，计划本月底再联系客户，确认后续推动方式，并争取安排现场拜访。",
                    model_dump=lambda exclude_none=True: {"passed": True, "score": 72},
                )
            )

    fake_graph = FakeGraphService()
    fake_quality = FakeQualityEvaluator()
    monkeypatch.setattr(agent_api, "crm_agent_graph_service", fake_graph)
    monkeypatch.setattr(agent_api, "agent_follow_up_quality_evaluator", fake_quality)
    monkeypatch.setattr(agent_api, "agent_semantic_parser", FakeSemanticParser({
        "intent": "CUSTOMER_ACTIVITY",
        "intent_confidence": 0.95,
        "customer": {"name_text": "广州凡亚信息科技有限公司", "confidence": 0.95, "resolution_source": "MEMORY"},
        "follow_up": {
            "content": "这个月底我会再联系下客户，确认下具体如何推动项目，争取能去现场拜访",
            "method": "AI录入",
            "next_action": "这个月底再联系客户，确认如何推动项目，争取现场拜访",
            "next_follow_time_text": "这个月底",
            "next_follow_time": {
                "raw_text": "这个月底",
                "kind": "MONTH_END",
                "direction": "current",
                "confidence": 0.9,
            },
        },
        "payment": {},
        "opportunity": {},
        "contact": {},
        "invoice_title": {},
        "deployment_info": {},
        "customer_member": {},
        "business_signals": [],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": ["这个月底我会再联系下客户"],
    }))

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "跟进质量会话"})
        session = create_response.json()

        first_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "凡亚信息今天反馈项目没进展"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert first_response.status_code == 200, first_response.text
        assert '"event": "follow_up_quality_required"' in first_response.text
        assert '"task_id": 1' in first_response.text

        second_response = client.post(
            "/v1/agent/chat/stream",
            json={
                "session_id": session["id"],
                "content": "这个月底我会再联系下客户，确认下具体如何推动项目，争取能去现场拜访",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert second_response.status_code == 200, second_response.text
        assert len(fake_graph.calls) == 1
        assert '"event": "confirmation_required"' in second_response.text
        assert '"type": "choice"' in second_response.text
        assert "客户活动内容已补齐" in second_response.text
        assert "广州凡亚信息科技有限公司" in second_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.WAITING_USER
            assert task.state_json["action"] == "create_customer_activity"
            assert task.state_json["customer"] == customer
            assert task.input_json["source_content"] == "这个月底我会再联系下客户，确认下具体如何推动项目，争取能去现场拜访"
            assert "补充：" not in task.input_json["source_content"]
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_keeps_collected_opportunity_fields_across_turns(monkeypatch):
    customer = {
        "id": 101,
        "account_name": "青岛四方阿尔斯通铁路运输设备有限公司",
        "owner_info": {"id": 2},
        "collaborator_infos": [],
    }

    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "opportunity_fields_required",
                "action": "collect_opportunity_fields",
                "customer": customer,
                "payload": {
                    "customer_id": customer["id"],
                    "opportunity": {
                        "customer_id": customer["id"],
                        "purchase_type": "RENEWAL",
                    },
                    "missing_fields": ["total_amount", "user_count", "license_type", "expected_closing_date"],
                },
            }
            yield {"event": "final", "content": "还需要补充商机信息。"}

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "agent_semantic_parser", FakeSemanticParser([
        {
            "intent": "CREATE_OPPORTUNITY",
            "intent_confidence": 0.95,
            "customer": {"name_text": "青岛四方", "confidence": 0.95, "resolution_source": "MEMORY"},
            "follow_up": {},
            "payment": {},
            "opportunity": {
                "total_amount": 100000,
                "user_count": 15,
                "license_type": "PERPETUAL",
                "expected_closing_date_text": "9 月底",
                "expected_closing_date": {"raw_text": "9 月底", "kind": "UNKNOWN", "confidence": 0.4},
            },
            "contact": {},
            "invoice_title": {},
            "deployment_info": {},
            "business_signals": [],
            "requested_actions": [],
            "missing_fields": ["expected_closing_date"],
            "need_clarification": False,
            "clarification_question": None,
            "evidence": ["10 万预算，15 个用户，买断使用，预计 9 月底能成交"],
        },
        {
            "intent": "CREATE_OPPORTUNITY",
            "intent_confidence": 0.95,
            "customer": {"name_text": "青岛四方", "confidence": 0.95, "resolution_source": "MEMORY"},
            "follow_up": {},
            "payment": {},
            "opportunity": {
                "expected_closing_date_text": "9 月 30 号",
                "expected_closing_date": {
                    "raw_text": "9 月 30 号",
                    "kind": "MONTH_DAY",
                    "month": 9,
                    "day": 30,
                    "confidence": 0.95,
                },
            },
            "contact": {},
            "invoice_title": {},
            "deployment_info": {},
            "business_signals": [],
            "requested_actions": [],
            "missing_fields": [],
            "need_clarification": False,
            "clarification_question": None,
            "evidence": ["9 月 30 号"],
        },
    ]))

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "商机会话"}).json()

        first_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮我给青岛四方创建续费商机"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert first_response.status_code == 200, first_response.text

        second_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "客户总共是 10 万预算，计划采购 15 个用户，买断使用，预计是 9 月底能成交"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert second_response.status_code == 200, second_response.text
        assert "还差商机" in second_response.text
        assert "预计成交日期" in second_response.text
        assert '"event": "opportunity_fields_required"' in second_response.text
        assert '"type": "form"' in second_response.text
        assert '"key": "expected_closing_date"' in second_response.text

        third_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "9 月 30 号"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert third_response.status_code == 200, third_response.text
        assert '"event": "confirmation_required"' in third_response.text
        assert '"type": "choice"' in third_response.text
        assert "商机信息齐了" in third_response.text
        assert "预计成交金额" not in third_response.text
        assert "采购用户数" not in third_response.text
        assert "授权模式" not in third_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            opportunity = task.state_json["payload"]["opportunity"]
            assert opportunity["total_amount"] == 100000
            assert opportunity["user_count"] == 15
            assert opportunity["license_type"] == "PERPETUAL"
            assert opportunity["purchase_type"] == "RENEWAL"
            assert opportunity["expected_closing_date"] == "2026-09-30"
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_interrupts_pending_task_for_clear_new_customer_flow(monkeypatch):
    customer = {
        "id": 101,
        "account_name": "广州睿狐科技有限公司",
        "owner_info": {"id": 2},
        "collaborator_infos": [],
    }
    captured_states = []

    class FakeGraphService:
        async def stream_events(self, input_state):
            captured_states.append(input_state)
            if len(captured_states) == 1:
                yield {
                    "event": "opportunity_fields_required",
                    "action": "collect_opportunity_fields",
                    "customer": customer,
                    "payload": {
                        "customer_id": customer["id"],
                        "opportunity": {
                            "customer_id": customer["id"],
                            "total_amount": 50000,
                            "user_count": 100,
                            "license_type": "SUBSCRIPTION",
                            "subscription_years": 1,
                        },
                        "missing_fields": ["purchase_type", "expected_closing_date"],
                    },
                }
                yield {"event": "final", "content": "请补充采购类型和预计成交日期。"}
            else:
                yield {"event": "final", "content": "已切换处理汇川技术的跟进。"}

    fake_parser = FakePendingInterruptionParser({
        "decision": "START_NEW_FLOW",
        "confidence": 0.92,
        "detected_customer_name": "汇川技术",
        "detected_intent": "CUSTOMER_ACTIVITY",
        "is_field_supplement": False,
        "reason": "本轮明确提到不同客户，并描述新的跟进记录。",
        "question": None,
    })
    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "agent_semantic_parser", fake_parser)

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "切换会话"})
        session = create_response.json()

        first_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "好的，帮我创建一个商机，5 万，100 人，1 年订阅"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert first_response.status_code == 200, first_response.text
        assert '"event": "opportunity_fields_required"' in first_response.text

        second_response = client.post(
            "/v1/agent/chat/stream",
            json={
                "session_id": session["id"],
                "content": "今天微信找了汇川技术的沟通续费方面的事宜，本月底会对接采购",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert second_response.status_code == 200, second_response.text
        assert '"event": "pending_task_interrupted"' in second_response.text
        assert "汇川技术" in second_response.text
        assert "切过来处理" in second_response.text
        assert captured_states[1]["content"] == "今天微信找了汇川技术的沟通续费方面的事宜，本月底会对接采购"
        assert fake_parser.calls[0]["pending_task"]["state"]["action"] == "collect_opportunity_fields"

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.SUSPENDED
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_resumes_suspended_opportunity_draft_with_structured_relation(monkeypatch):
    customer = {
        "id": 101,
        "account_name": "广州睿狐科技有限公司",
        "owner_info": {"id": 2},
        "collaborator_infos": [],
    }
    graph_calls = []

    class FakeGraphService:
        async def stream_events(self, input_state):
            graph_calls.append(input_state)
            yield {
                "event": "confirmation_required",
                "action": "create_opportunity",
                "customer": customer,
                "payload": {
                    "customer_id": customer["id"],
                    "opportunity": {
                        "customer_id": customer["id"],
                        "total_amount": 50000,
                        "user_count": 10,
                        "license_type": "SUBSCRIPTION",
                        "subscription_years": 1,
                        "purchase_type": "NEW",
                        "expected_closing_date": "2026-08-31",
                    },
                },
            }
            yield {"event": "final", "content": "商机信息齐了。要创建商机吗？"}

    fake_parser = FakeTurnRelationAndSemanticParser(
        relation={
            "relation": "RESUME_SUSPENDED_DRAFT",
            "confidence": 0.93,
            "target_task_id": "__first_suspended__",
            "detected_customer_name": None,
            "detected_intent": "CREATE_OPPORTUNITY",
            "reason": "用户在修改最近暂停的商机草稿。",
            "question": None,
        },
        semantic_results={
            "intent": "CREATE_OPPORTUNITY",
            "intent_confidence": 0.95,
            "customer": {"name_text": "广州睿狐科技有限公司", "confidence": 0.95, "resolution_source": "MEMORY"},
            "follow_up": {},
            "payment": {},
            "opportunity": {
                "user_count": 20,
                "purchase_type": "EXPANSION",
            },
            "contact": {},
            "invoice_title": {},
            "deployment_info": {},
            "business_signals": [],
            "requested_actions": [],
            "missing_fields": [],
            "need_clarification": False,
            "clarification_question": None,
            "evidence": ["改成增购 20 个"],
        },
    )
    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "agent_semantic_parser", fake_parser)

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "商机草稿恢复"}).json()
        first_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮广州睿狐科技建一个 10 个新购商机，8 月底成交"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert first_response.status_code == 200, first_response.text
        assert '"event": "confirmation_required"' in first_response.text

        second_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "先不处理"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert second_response.status_code == 200, second_response.text
        assert '"event": "task_cancelled"' in second_response.text

        third_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "张总说改成增购 20 个了"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert third_response.status_code == 200, third_response.text
        assert '"event": "turn_relation_classified"' in third_response.text
        assert '"event": "suspended_task_resumed"' in third_response.text
        assert '"event": "confirmation_required"' in third_response.text
        assert len(graph_calls) == 1
        assert fake_parser.relation_calls[0]["suspended_tasks"][0]["state"]["customer"]["account_name"] == customer["account_name"]

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.WAITING_USER
            assert task.state_json["action"] == "create_opportunity"
            assert task.state_json["customer"]["account_name"] == customer["account_name"]
            opportunity = task.state_json["payload"]["opportunity"]
            assert opportunity["customer_id"] == customer["id"]
            assert opportunity["total_amount"] == 50000
            assert opportunity["user_count"] == 20
            assert opportunity["license_type"] == "SUBSCRIPTION"
            assert opportunity["subscription_years"] == 1
            assert opportunity["purchase_type"] == "EXPANSION"
            assert opportunity["expected_closing_date"] == "2026-08-31"
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_resolves_customer_selection_before_confirmation(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "customer_selection_required",
                "action": "select_customer_for_activity",
                "customers": [
                    {"id": 101, "account_name": "越秀金融"},
                    {"id": 102, "account_name": "越秀金融科技"},
                ],
                "payload": {
                    "content": input_state["content"],
                    "next_action": "下周三继续跟进",
                    "next_follow_time_text": "下周三",
                    "next_follow_time_iso": "2026-07-29T09:00:00",
                },
            }
            yield {"event": "final", "content": "我找到了多个可能的客户，请回复序号或客户名称确认。"}

    class FakeToolService:
        async def create_customer_activity(self, context, **kwargs):
            assert context.authorization == "Bearer test-token"
            assert context.task_id is not None
            assert kwargs["customer_id"] == 102
            assert kwargs["customer_name"] == "越秀金融科技"
            assert kwargs["source_content"] == "今天和越秀金融的王总沟通了项目进展，下周三继续跟进"
            assert kwargs["next_follow_time"] == "2026-07-29T09:00:00"
            return AgentToolResult(
                tool_name="create_customer_activity",
                success=True,
                data={"id": 9002, "customer_id": 102},
                tool_call_id=7002,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "跟进会话"})
        session = create_response.json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={
                "session_id": session["id"],
                "content": "今天和越秀金融的王总沟通了项目进展，下周三继续跟进",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "customer_selection_required"' in plan_response.text
        assert '"task_id": 1' in plan_response.text

        select_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "2"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert select_response.status_code == 200, select_response.text
        assert '"event": "customer_selected"' in select_response.text
        assert "请确认是否创建这条客户活动" in select_response.text

        confirm_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert '"event": "task_completed"' in confirm_response.text
        assert "客户活动已记录" in confirm_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.COMPLETED
            assert task.target_id == 102
            assert task.result_json == {"id": 9002, "customer_id": 102}
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_collects_contact_fields_then_executes_confirmation(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "contact_fields_required",
                "action": "collect_contact_fields",
                "customer": {"id": 101, "account_name": "越秀金融"},
                "payload": {
                    "customer_id": 101,
                    "contact": {"name": "王总", "is_decision_maker": False},
                    "missing_fields": ["mobile", "position", "gender"],
                },
            }
            yield {"event": "final", "content": "还需要补充：手机号、职务、性别。"}

    class FakeToolService:
        async def create_contact(self, context, **kwargs):
            assert context.authorization == "Bearer test-token"
            assert context.task_id is not None
            assert kwargs["customer_id"] == 101
            assert kwargs["contact"] == {
                "name": "王总",
                "is_decision_maker": False,
                "mobile": "13800138000",
                "position": "总经理",
                "gender": "1",
            }
            return AgentToolResult(
                tool_name="create_contact",
                success=True,
                data={"id": 8001, "customer_id": 101, "name": "王总"},
                tool_call_id=7101,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())
    monkeypatch.setattr(agent_api, "agent_semantic_parser", FakeSemanticParser({
        "intent": "CREATE_CONTACT",
        "intent_confidence": 0.95,
        "customer": {"name_text": "越秀金融", "confidence": 0.95},
        "follow_up": {},
        "contact": {"mobile": "13800138000", "position": "总经理", "gender": "1"},
        "invoice_title": {},
        "deployment_info": {},
        "business_signals": [],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": ["手机号13800138000，职务总经理，男"],
    }))

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "联系人会话"})
        session = create_response.json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮我给越秀金融创建联系人王总"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "contact_fields_required"' in plan_response.text
        assert '"task_id": 1' in plan_response.text

        fill_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "手机号13800138000，职务总经理，男"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert fill_response.status_code == 200, fill_response.text
        assert '"event": "confirmation_required"' in fill_response.text
        assert '"type": "choice"' in fill_response.text
        assert "请确认是否为" in fill_response.text

        confirm_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert '"event": "task_completed"' in confirm_response.text
        assert "联系人已创建" in confirm_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.COMPLETED
            assert task.result_json == {"id": 8001, "customer_id": 101, "name": "王总"}
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_collects_invoice_title_fields_then_executes_confirmation(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "invoice_title_fields_required",
                "action": "collect_invoice_title_fields",
                "customer": {"id": 101, "account_name": "越秀金融"},
                "payload": {
                    "customer_id": 101,
                    "invoice_title": {"title_type": "COMPANY"},
                    "missing_fields": ["title", "taxpayer_id"],
                    "set_default": False,
                },
            }
            yield {"event": "final", "content": "还需要补充：开票抬头、纳税人识别号。"}

    class FakeToolService:
        async def create_invoice_title(self, context, **kwargs):
            assert context.authorization == "Bearer test-token"
            assert context.task_id is not None
            assert kwargs["customer_id"] == 101
            assert kwargs["invoice_title"] == {
                "title_type": "COMPANY",
                "title": "越秀金融控股有限公司",
                "taxpayer_id": "91440000123456789X",
            }
            assert kwargs["set_default"] is True
            return AgentToolResult(
                tool_name="create_invoice_title",
                success=True,
                data={
                    "invoice_title": {
                        "id": 6001,
                        "customer_id": 101,
                        "title": "越秀金融控股有限公司",
                    },
                    "set_default": True,
                },
                tool_call_id=7201,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())
    monkeypatch.setattr(agent_api, "agent_semantic_parser", FakeSemanticParser({
        "intent": "CREATE_INVOICE_TITLE",
        "intent_confidence": 0.95,
        "customer": {"name_text": "越秀金融", "confidence": 0.95},
        "follow_up": {},
        "contact": {},
        "invoice_title": {
            "title": "越秀金融控股有限公司",
            "taxpayer_id": "91440000123456789X",
            "set_default": True,
        },
        "deployment_info": {},
        "business_signals": [],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": ["抬头是越秀金融控股有限公司，税号91440000123456789X，设为默认"],
    }))

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "发票抬头会话"})
        session = create_response.json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮我给越秀金融创建发票抬头"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "invoice_title_fields_required"' in plan_response.text
        assert '"task_id": 1' in plan_response.text

        fill_response = client.post(
            "/v1/agent/chat/stream",
            json={
                "session_id": session["id"],
                "content": "抬头是越秀金融控股有限公司，税号91440000123456789X，设为默认",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert fill_response.status_code == 200, fill_response.text
        assert '"event": "confirmation_required"' in fill_response.text
        assert '"type": "choice"' in fill_response.text
        assert "请确认是否为" in fill_response.text

        confirm_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert '"event": "task_completed"' in confirm_response.text
        assert "发票抬头已创建" in confirm_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.COMPLETED
            assert task.result_json == {
                "invoice_title": {
                    "id": 6001,
                    "customer_id": 101,
                    "title": "越秀金融控股有限公司",
                },
                "set_default": True,
            }
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_customer_member_selection_loads_member_candidates(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "customer_selection_required",
                "action": "select_customer_for_customer_member",
                "customers": [
                    {"id": 101, "account_name": "越秀金融控股有限公司"},
                    {"id": 102, "account_name": "越秀金融租赁有限公司"},
                ],
                "payload": {
                    "customer_member": {"user_name": "张三", "member_role": "PRESALES"},
                    "missing_fields": [],
                },
            }
            yield {"event": "final", "content": "我找到了多个可能的客户，请回复序号确认。"}

    class FakeAPIClient:
        async def request(self, method, path, authorization, **kwargs):
            assert method == "GET"
            assert path == "/v1/customers/101/member-candidates"
            assert authorization == "Bearer test-token"
            return [{"id": 301, "name": "张三", "already_member": False}]

    class FakeToolService:
        def __init__(self):
            self.api_client = FakeAPIClient()

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", FakeToolService)

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "客户成员会话"})
        session = create_response.json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮我给越秀金融添加售前张三"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "customer_selection_required"' in plan_response.text

        select_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "1"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert select_response.status_code == 200, select_response.text
        assert '"event": "customer_selected"' in select_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.WAITING_USER
            assert task.state_json["action"] == "collect_customer_member_fields"
            assert task.state_json["payload"]["customer_id"] == 101
            assert task.state_json["payload"]["member_candidates"] == [
                {"id": 301, "name": "张三", "already_member": False}
            ]
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_collects_deployment_info_fields_then_executes_confirmation(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "deployment_info_fields_required",
                "action": "collect_deployment_info_fields",
                "customer": {"id": 101, "account_name": "越秀金融"},
                "payload": {
                    "customer_id": 101,
                    "deployment_info": {"customer_id": 101, "is_default": False},
                    "missing_fields": ["deployment_name", "server_address"],
                },
            }
            yield {"event": "final", "content": "还需要补充：部署名称、服务器地址。"}

    class FakeToolService:
        async def create_deployment_info(self, context, **kwargs):
            assert context.authorization == "Bearer test-token"
            assert context.task_id is not None
            assert kwargs["deployment_info"] == {
                "customer_id": 101,
                "is_default": True,
                "deployment_name": "生产环境",
                "server_address": "https://crm.example.com",
            }
            return AgentToolResult(
                tool_name="create_deployment_info",
                success=True,
                data={
                    "id": 6101,
                    "customer_id": 101,
                    "deployment_name": "生产环境",
                },
                tool_call_id=7301,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())
    monkeypatch.setattr(agent_api, "agent_semantic_parser", FakeSemanticParser({
        "intent": "CREATE_DEPLOYMENT_INFO",
        "intent_confidence": 0.95,
        "customer": {"name_text": "越秀金融", "confidence": 0.95},
        "follow_up": {},
        "contact": {},
        "invoice_title": {},
        "deployment_info": {
            "deployment_name": "生产环境",
            "server_address": "https://crm.example.com",
            "is_default": True,
        },
        "business_signals": [],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": ["部署名称是生产环境，服务器地址 https://crm.example.com，设为默认"],
    }))

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "部署信息会话"})
        session = create_response.json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮我给越秀金融创建部署信息"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "deployment_info_fields_required"' in plan_response.text
        assert '"task_id": 1' in plan_response.text

        fill_response = client.post(
            "/v1/agent/chat/stream",
            json={
                "session_id": session["id"],
                "content": "部署名称是生产环境，服务器地址 https://crm.example.com，设为默认",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert fill_response.status_code == 200, fill_response.text
        assert '"event": "confirmation_required"' in fill_response.text
        assert '"type": "choice"' in fill_response.text
        assert "请确认是否为" in fill_response.text

        confirm_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert '"event": "task_completed"' in confirm_response.text
        assert "部署信息已创建" in confirm_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.COMPLETED
            assert task.result_json == {
                "id": 6101,
                "customer_id": 101,
                "deployment_name": "生产环境",
            }
        finally:
            db.close()
    finally:
        engine.dispose()

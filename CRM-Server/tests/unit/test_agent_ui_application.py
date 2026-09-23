"""Application behavior at the typed Root Orchestrator dispatch seam."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING
from uuid import UUID
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.agent import AgentMessage, AgentMessageRole, AgentSession
from app.models.agent_persistence import (
    AgentQueryResultSet,
    AgentUIAction,
    AgentUIActionStatus,
)
from app.models.agent_turn_execution import AgentTurnExecution
from app.models.user import User
from app.models.customer import Customer, CustomerMember, CustomerProduct
from app.models.sales_commitment import FollowUpTask, FollowUpTaskConfirmationCase
from app.schemas.agent_persistence import AgentUIActionRegistration
from app.services.agent import application as application_module
from app.services.agent.application import AgentApplicationService
from app.services.agent.durable_work_contracts import CustomerActivityDurableWorkReceipt
from app.services.agent.orchestrator import (
    AgentExecutionError,
    ContextPolicy,
    FailureDispatchResult,
    QueryDispatchResult,
    RootConversationMemory,
    RootDecision,
    RootRuntimeContext,
    RootTurnInput,
    TextTurnInput,
    WorkflowContinuation,
    WorkflowDispatchResult,
)
from app.services.agent.orchestrator.contracts import RootContextSnapshot, RootRoutingPlan
from app.services.agent.orchestrator.graph import RootOrchestrator, build_root_graph_config
from app.services.agent.orchestrator.context import DatabaseRootContextResolver
from app.services.agent.orchestrator.errors import WorkflowCheckpointUnavailableError
from app.services.agent.query import CRMQueryAgentResult
from app.services.agent.semantic_plan import AgentSemanticPlan
from app.services.agent.ui.actions import ActionAlreadyConsumedError, AgentUIActionRepository
from app.services.agent.ui.schemas import (
    EntityActionInput,
    InteractionSubmissionInput,
    TextAgentInput,
)
from app.services.agent.workflow import (
    WorkflowCancelledResult,
    WorkflowCompletedResult,
    WorkflowFailedResult,
    WorkflowInteraction,
    WorkflowInteractionOption,
    WorkflowProgress,
    WorkflowRef,
    WorkflowReplayResult,
    WorkflowWaitingResult,
)
from app.services.agent.workflow.progress import (
    awaiting_required_input_progress,
    execution_progress,
    required_input_cancelled_progress,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.services.agent.orchestrator import RootDispatchResult


_REQUEST_ID = UUID("6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be")


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    del element, compiler, kw
    return "INTEGER"


def _decision(route: str, *, relation: str = "NEW_TASK") -> RootDecision:
    return RootDecision(
        task_relation=relation,
        route=route,
        risk="WRITE" if route == "WORKFLOW" else "READ_ONLY",
        context_policy=ContextPolicy(
            selected_entity="USE" if route == "WORKFLOW" else "IGNORE",
            previous_query="IGNORE",
            result_set="IGNORE",
            active_workflow="NONE",
        ),
        confidence=1.0,
        reason_code=f"{route}_TEST",
        semantic_plan=AgentSemanticPlan(
            speech_act="REQUEST_ACTION" if route == "WORKFLOW" else "ASK_FACT",
            business_object="CUSTOMER_ACTIVITY" if route == "WORKFLOW" else "CUSTOMER",
            operation="CREATE" if route == "WORKFLOW" else "READ",
            confidence=1.0,
        ),
        evidence=[],
    )


def _query_dispatch() -> QueryDispatchResult:
    return QueryDispatchResult(
        decision=_decision("QUERY"),
        query_result=CRMQueryAgentResult.model_validate(
            {
                "response": {
                    "status": "ANSWERED",
                    "answer": "你在上海有 1 个客户: 上海星云科技。",
                    "evidence_refs": ["qry_shanghai_customers"],
                },
                "query_results": [
                    {
                        "query_id": "qry_shanghai_customers",
                        "result_set_id": "rs_query_application_test",
                        "resource": "customer",
                        "status": "SUCCESS",
                        "executed_query": {
                            "resource": "customer",
                            "projection": ["public_id", "account_name", "city"],
                            "filters": [{"field": "city", "operator": "eq", "value": "上海"}],
                            "sorts": [],
                            "metrics": [],
                            "group_by": [],
                            "scope": "accessible",
                            "page_size": 20,
                        },
                        "rows": [
                            {
                                "public_id": "cus_shanghai_1",
                                "account_name": "上海星云科技",
                                "city": "上海",
                            }
                        ],
                        "entity_refs": [
                            {
                                "ref_id": "eref_customer_1",
                                "resource": "customer",
                                "public_id": "cus_shanghai_1",
                                "display_name": "上海星云科技",
                                "result_set_id": "rs_query_application_test",
                            }
                        ],
                        "total": 1,
                        "applied_filters": [{"field": "city", "operator": "eq", "value": "上海"}],
                        "applied_sorts": [],
                        "facts": [],
                        "warnings": [],
                    }
                ],
                "customer_context_results": [],
                "trace": {
                    "model": "test-model",
                    "tool_names": ["query_customers"],
                    "tool_calls": [],
                    "tool_call_count": 1,
                    "total_entity_count": 1,
                    "elapsed_ms": 1,
                    "stop_reason": "COMPLETED",
                },
            }
        ),
    )


def _completed_workflow_dispatch(*, action_claim_id: str | None = None) -> WorkflowDispatchResult:
    return WorkflowDispatchResult(
        decision=_decision("WORKFLOW"),
        workflow_result=WorkflowCompletedResult(
            workflow_ref=WorkflowRef(workflow_id="wf_customer_follow_up"),
            assistant_text="已创建跟进任务。",
            progress=execution_progress(
                confirmation_required=False,
                has_supplements=False,
                outcome="COMPLETED",
            ),
        ),
        action_claim_id=action_claim_id,
    )


def _confirmation_workflow_dispatch() -> WorkflowDispatchResult:
    continuation = WorkflowContinuation(
        root_thread_id="crm_agent_turn:test",
        workflow_ref=WorkflowRef(workflow_id="wf_customer_follow_up", interrupt_id="intr_confirm"),
        parent_checkpoint_id="parent_cp_confirm",
        subgraph_checkpoint_ns="workflow:customer_follow_up",
        subgraph_checkpoint_id="child_cp_confirm",
    )
    interaction = WorkflowInteraction(
        interaction_id="int_confirm_create",
        interaction_type="confirmation",
        business_action="create_customer_activity",
        title="确认创建",
        prompt="请确认是否创建这条客户活动？",  # noqa: RUF001
        options=[
            WorkflowInteractionOption(value="confirm", label="确认创建"),
            WorkflowInteractionOption(value="cancel", label="取消"),
        ],
        selection_mode="single",
        min_selections=1,
        max_selections=1,
    )
    return WorkflowDispatchResult(
        decision=_decision("WORKFLOW"),
        workflow_result=WorkflowWaitingResult(
            workflow_ref=continuation.workflow_ref,
            assistant_text=interaction.prompt,
            interaction=interaction,
            progress=awaiting_required_input_progress(),
        ),
        continuation=continuation,
    )


def _waiting_workflow_dispatch() -> WorkflowDispatchResult:
    continuation = WorkflowContinuation(
        root_thread_id="crm_agent_turn:test",
        workflow_ref=WorkflowRef(workflow_id="wf_customer_follow_up", interrupt_id="intr_customer"),
        parent_checkpoint_id="parent_cp_1",
        subgraph_checkpoint_ns="workflow:customer_follow_up",
        subgraph_checkpoint_id="child_cp_1",
    )
    interaction = WorkflowInteraction(
        interaction_id="int_customer_choice",
        interaction_type="choice",
        business_action="select_customer",
        title="选择客户",
        prompt="请选择客户。",
        options=[
            WorkflowInteractionOption(value="cus_shanghai_1", label="上海星云科技"),
            WorkflowInteractionOption(value="cus_shanghai_2", label="上海远景软件"),
        ],
        selection_mode="single",
        min_selections=1,
        max_selections=1,
    )
    return WorkflowDispatchResult(
        decision=_decision("WORKFLOW"),
        workflow_result=WorkflowWaitingResult(
            workflow_ref=continuation.workflow_ref,
            assistant_text=interaction.prompt,
            interaction=interaction,
            progress=awaiting_required_input_progress(),
        ),
        continuation=continuation,
    )


def _follow_up_content_workflow_dispatch() -> WorkflowDispatchResult:
    return WorkflowDispatchResult(
        decision=_decision("WORKFLOW"),
        workflow_result=WorkflowWaitingResult(
            workflow_ref=WorkflowRef(workflow_id="wf_follow_up", interrupt_id="intr_content"),
            assistant_text="请补充本次客户跟进的具体内容。",
            interaction=WorkflowInteraction(
                interaction_id="int_follow_up_content",
                interaction_type="text_input",
                business_action="provide_follow_up_content",
                title="补充跟进内容",
                allow_cancel=True,
                prompt="请补充本次客户跟进的具体内容。",
                allow_blank=False,
            ),
            progress=awaiting_required_input_progress(),
        ),
        continuation=_waiting_workflow_dispatch().continuation.model_copy(
            update={"workflow_ref": WorkflowRef(workflow_id="wf_follow_up", interrupt_id="intr_content")}
        ),
    )


def _cancelled_workflow_dispatch(action_id: str) -> WorkflowDispatchResult:
    return WorkflowDispatchResult(
        decision=_decision("WORKFLOW", relation="CONTINUE_TASK"),
        workflow_result=WorkflowCancelledResult(
            workflow_ref=WorkflowRef(workflow_id="wf_follow_up"),
            assistant_text="已取消当前工作流。",
            progress=required_input_cancelled_progress(),
        ),
        action_claim_id=action_id,
    )


class _CapturingDurableWorkBinder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def bind(self, db, *, receipts, binding) -> None:
        # The late-bind phase must only run after both turn messages are committed
        # and visible through a fresh transaction.
        assert db.query(AgentMessage).filter_by(id=binding.source_user_message_id).one()
        assert db.query(AgentMessage).filter_by(id=binding.source_assistant_message_id).one()
        self.calls.append({"receipts": receipts, "binding": binding})


class _FakeRootOrchestrator:
    def __init__(
        self,
        result: RootDispatchResult,
        *,
        on_dispatch: Callable[[RootTurnInput, RootRuntimeContext], None] | None = None,
    ) -> None:
        self.result = result
        self.on_dispatch = on_dispatch
        self.calls: list[tuple[RootTurnInput, RootRuntimeContext]] = []

    async def dispatch(
        self,
        turn: RootTurnInput,
        *,
        runtime: RootRuntimeContext,
        on_progress: Callable[[WorkflowProgress], None] | None = None,
    ) -> RootDispatchResult:
        del on_progress
        self.calls.append((turn, runtime))
        if self.on_dispatch is not None:
            self.on_dispatch(turn, runtime)
        return self.result


class _ProgressRootOrchestrator(_FakeRootOrchestrator):
    async def dispatch(
        self,
        turn: RootTurnInput,
        *,
        runtime: RootRuntimeContext,
        on_progress: Callable[[WorkflowProgress], None] | None = None,
    ) -> RootDispatchResult:
        self.calls.append((turn, runtime))
        if on_progress is not None:
            on_progress(
                WorkflowProgress.model_validate(
                    {
                        "steps": [
                            {
                                "key": "understand_request",
                                "title": "理解业务操作",
                                "status": "RUNNING",
                            }
                        ]
                    }
                )
            )
            on_progress(
                WorkflowProgress.model_validate(
                    {
                        "steps": [
                            {
                                "key": "understand_request",
                                "title": "理解业务操作",
                                "status": "COMPLETED",
                            },
                            {
                                "key": "prepare_plan",
                                "title": "生成执行计划",
                                "status": "RUNNING",
                            },
                        ]
                    }
                )
            )
        return self.result


@pytest.fixture
def application_harness(monkeypatch):
    engine = create_engine(
        f"sqlite:///file:agent-app-{uuid.uuid4().hex}?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False, "uri": True},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AgentSession.__table__,
            AgentMessage.__table__,
            AgentQueryResultSet.__table__,
            AgentUIAction.__table__,
            AgentTurnExecution.__table__,
            User.__table__,
            Customer.__table__,
            CustomerMember.__table__,
            CustomerProduct.__table__,
            FollowUpTask.__table__,
            FollowUpTaskConfirmationCase.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(
        application_module,
        "ai_config_crud",
        SimpleNamespace(
            get_config=lambda db, team_id: SimpleNamespace(
                api_host="https://ai.example.com/v1",
                model_name="test-model",
                temperature=0.1,
            ),
            get_decrypted_api_key=lambda db, team_id: "test-api-key",
        ),
    )
    monkeypatch.setattr(
        application_module,
        "permission_crud",
        SimpleNamespace(get_user_permissions=lambda db, user_id, team_id: []),
    )
    orchestrator = _FakeRootOrchestrator(_query_dispatch())
    service = AgentApplicationService(
        root_orchestrator=orchestrator,
        session_factory=session_factory,
    )
    try:
        yield service, session_factory
    finally:
        engine.dispose()


async def _collect(
    service: AgentApplicationService,
    *,
    request_input,
    client_request_id: UUID,
    session_id: int | None = None,
):
    return [
        event
        async for event in service.stream_chat_events(
            request_input=request_input,
            client_request_id=client_request_id,
            team_id=1,
            user_id=2,
            authorization="Bearer test-token",
            session_id=session_id,
        )
    ]


async def _start_customer_action(service: AgentApplicationService) -> tuple[int, str]:
    service.root_orchestrator = _FakeRootOrchestrator(_query_dispatch())
    events = await _collect(
        service,
        request_input=TextAgentInput(type="text", text="我在上海有哪些客户"),
        client_request_id=UUID("8fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
    )
    session_id = events[0]["session_id"]
    action_id = "act_customer_query_test"
    with service.session_factory() as db:
        service.action_repository.register(
            db,
            AgentUIActionRegistration(
                public_id=action_id,
                team_id=1,
                user_id=2,
                session_id=session_id,
                message_id=events[1]["message_id"],
                action_type="start_workflow",
                root_context_role="PROJECTION_ONLY",
                target={
                    "workflow": "create_follow_up_task",
                    "result_set_id": "rs_query_application_test",
                    "ref_id": "eref_customer_1",
                    "label": "为上海星云科技创建跟进任务",
                },
                consumption_mode="ONE_SHOT",
            ),
        )
        db.commit()
    return session_id, action_id


async def _start_interaction(service: AgentApplicationService) -> tuple[int, str]:
    service.root_orchestrator = _FakeRootOrchestrator(_waiting_workflow_dispatch())
    events = await _collect(
        service,
        request_input=TextAgentInput(type="text", text="创建跟进任务"),
        client_request_id=UUID("9fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
    )
    interaction = next(block for block in events[1]["message"]["blocks"] if block["type"] == "interaction")
    action_id = interaction["submit_action_id"]
    return events[0]["session_id"], action_id


@pytest.mark.asyncio
async def test_text_turn_dispatches_once_and_persists_one_authoritative_agent_ui(
    application_harness,
) -> None:
    service, session_factory = application_harness
    orchestrator = _FakeRootOrchestrator(_query_dispatch())
    service.root_orchestrator = orchestrator

    events = await _collect(
        service,
        request_input=TextAgentInput(type="text", text="我在上海有哪些客户"),
        client_request_id=_REQUEST_ID,
    )

    assert [event["event"] for event in events] == ["session", "agent_ui", "done"]
    assert len(orchestrator.calls) == 1
    turn, runtime = orchestrator.calls[0]
    assert turn.input.type == "text"
    assert turn.input.text == "我在上海有哪些客户"
    assert turn.selected_entity_ref is None
    assert runtime.authorization.startswith("Bearer ")
    from app.core.security import decode_access_token
    payload = decode_access_token(runtime.authorization.split(" ", 1)[1])
    assert payload is not None
    assert payload["purpose"] == "agent_worker"
    assert payload["sub"] == "2"
    assert runtime.metadata == {"source": "web"}
    with session_factory() as db:
        assistant = db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).one()
        diagnostics = assistant.diagnostics_json
        assert diagnostics is not None
        assert diagnostics["dispatch_type"] == "query"
        observability = diagnostics["turn_observability"]
        assert observability["outcome"] == "answered"
        assert len(observability["steps"]) == 6
        assert observability["steps"][0]["kind"] == "model"
        assert observability["steps"][4]["kind"] == "api"
        assert observability["steps"][4]["tone"] == "done"


@pytest.mark.asyncio
async def test_query_turn_persists_clickable_result_set_without_workflow_actions(
    application_harness,
) -> None:
    service, session_factory = application_harness

    events = await _collect(
        service,
        request_input=TextAgentInput(type="text", text="我在上海有哪些客户"),
        client_request_id=UUID("7fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
    )

    entity_item = events[1]["message"]["blocks"][1]["items"][0]
    assert entity_item["entity_ref"] == {
        "ref_id": "eref_customer_1",
        "resource": "customer",
        "public_id": "cus_shanghai_1",
        "display_name": "上海星云科技",
        "result_set_id": "rs_query_application_test",
    }
    assert set(entity_item) == {"entity_ref"}
    with session_factory() as db:
        assistant = db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).one()
        result_set = db.query(AgentQueryResultSet).one()
        assert result_set.public_id == "rs_query_application_test"
        assert result_set.source_message_id == assistant.id
        assert result_set.row_count == 1
        assert result_set.ordered_entity_refs_json[0]["ref_id"] == "eref_customer_1"
        assert db.query(AgentUIAction).count() == 0


@pytest.mark.asyncio
async def test_query_turn_server_signs_result_set_before_ui_and_persistence(
    application_harness,
) -> None:
    service, session_factory = application_harness
    dispatch = _query_dispatch()
    unsigned_results = [
        result.model_copy(
            update={
                "result_set_id": None,
                "entity_refs": [ref.model_copy(update={"result_set_id": None}) for ref in result.entity_refs],
            }
        )
        for result in dispatch.query_result.query_results
    ]
    service.root_orchestrator = _FakeRootOrchestrator(
        dispatch.model_copy(
            update={"query_result": dispatch.query_result.model_copy(update={"query_results": unsigned_results})}
        )
    )

    events = await _collect(
        service,
        request_input=TextAgentInput(type="text", text="我在上海有哪些客户"),
        client_request_id=UUID("70a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
    )

    assert [event["event"] for event in events] == ["session", "agent_ui", "done"]
    final_message = events[1]["message"]
    assert all(block["type"] != "error" for block in final_message["blocks"])
    entity_list = final_message["blocks"][1]
    assert entity_list["type"] == "entity_list"
    assert entity_list["result_set_id"].startswith("rs_")
    with session_factory() as db:
        result_set = db.query(AgentQueryResultSet).one()
        assert result_set.public_id == entity_list["result_set_id"]
        assert result_set.ordered_entity_refs_json[0]["result_set_id"] == result_set.public_id


class _FailingResultSetRepository:
    def create(self, db, request):
        del db, request
        raise RuntimeError("result set persistence failed")


@pytest.mark.asyncio
async def test_query_result_set_failure_rolls_back_assistant_result_set_and_actions(
    application_harness,
) -> None:
    service, session_factory = application_harness
    service.result_set_repository = _FailingResultSetRepository()

    events = await _collect(
        service,
        request_input=TextAgentInput(type="text", text="我在上海有哪些客户"),
        client_request_id=UUID("7ba2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
    )

    assert [event["event"] for event in events] == ["session", "agent_ui", "done"]
    error = next(block for block in events[1]["message"]["blocks"] if block["type"] == "error")
    assert error["code"] == "INTERNAL_ERROR"
    with session_factory() as db:
        assert db.query(AgentQueryResultSet).count() == 0
        assert db.query(AgentUIAction).count() == 0
        assistants = db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).all()
        assert len(assistants) == 1
        diagnostics = assistants[0].diagnostics_json
        assert diagnostics is not None
        assert diagnostics["dispatch_type"] == "failure"
        observability = diagnostics["turn_observability"]
        assert observability["outcome"] == "failed"
        assert len(observability["steps"]) == 6


@pytest.mark.asyncio
async def test_workflow_progress_is_streamed_before_the_authoritative_final_message(
    application_harness,
) -> None:
    service, _ = application_harness
    service.root_orchestrator = _ProgressRootOrchestrator(_completed_workflow_dispatch())

    events = await _collect(
        service,
        request_input=TextAgentInput(
            type="text",
            text="记录今天的客户跟进并创建下周待办",
        ),
        client_request_id=UUID("71a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
    )

    agent_ui_events = [event for event in events if event["event"] == "agent_ui"]
    assert [event["phase"] for event in agent_ui_events] == ["delta", "delta", "final"]
    assert [event["sequence"] for event in agent_ui_events] == [1, 2, 3]
    turn_ids = {event["turn_id"] for event in agent_ui_events}
    assert len(turn_ids) == 1
    assert all(turn_id.startswith("turn_") for turn_id in turn_ids)
    assert agent_ui_events[0]["operations"][0]["op"] == "upsert_block"
    assert agent_ui_events[0]["operations"][0]["block"]["type"] == "process"
    assert agent_ui_events[0]["operations"][0]["block"]["items"][0]["status"] == "RUNNING"
    assert agent_ui_events[1]["operations"][0]["block"]["items"][1]["status"] == "RUNNING"
    assert agent_ui_events[2]["message"]["blocks"][0]["type"] == "process"


@pytest.mark.asyncio
async def test_entity_action_passes_authoritative_selected_entity_and_consumes_once(
    application_harness,
    monkeypatch,
) -> None:
    service, session_factory = application_harness
    session_id, action_id = await _start_customer_action(service)
    with session_factory() as db:
        db.add(
            Customer(
                public_id="cus_shanghai_1",
                team_id=1,
                account_name="上海星云科技",
                city="上海",
                owner_id="2",
                creator_id="2",
            )
        )
        db.commit()
    monkeypatch.setattr(
        application_module,
        "permission_crud",
        SimpleNamespace(
            get_user_permissions=lambda db, user_id, team_id: [SimpleNamespace(code="customer:follow_up:create")]
        ),
    )
    orchestrator = _FakeRootOrchestrator(_completed_workflow_dispatch())
    service.root_orchestrator = orchestrator
    request_id = UUID("afa2e0e8-86d4-4d6c-a1b0-6490b2bf12be")

    first = await _collect(
        service,
        request_input=EntityActionInput(type="entity_action", action_id=action_id),
        client_request_id=request_id,
        session_id=session_id,
    )

    assert [event["event"] for event in first] == ["session", "agent_ui", "done"]
    assert len(orchestrator.calls) == 1
    turn, _ = orchestrator.calls[0]
    assert turn.input.type == "text"
    assert turn.input.text == "为上海星云科技创建跟进任务"
    assert turn.selected_entity_ref is not None
    assert turn.selected_entity_ref.public_id == "cus_shanghai_1"
    assert turn.selected_entity_ref.result_set_id == "rs_query_application_test"
    with session_factory() as db:
        action = db.query(AgentUIAction).filter_by(public_id=action_id).one()
        assert action.status == AgentUIActionStatus.CONSUMED
        assert action.consumed_request_id == str(request_id)
        assert action.result_message_id == first[1]["message_id"]

    replay = await _collect(
        service,
        request_input=EntityActionInput(type="entity_action", action_id=action_id),
        client_request_id=request_id,
        session_id=session_id,
    )
    assert replay[1] == first[1]
    assert len(orchestrator.calls) == 1


@pytest.mark.asyncio
async def test_entity_action_permission_failure_never_dispatches(
    application_harness,
) -> None:
    service, session_factory = application_harness
    session_id, action_id = await _start_customer_action(service)
    with session_factory() as db:
        db.add(
            Customer(
                public_id="cus_shanghai_1",
                team_id=1,
                account_name="上海星云科技",
                city="上海",
                owner_id="99",
                creator_id="99",
            )
        )
        db.commit()
    orchestrator = _FakeRootOrchestrator(_completed_workflow_dispatch())
    service.root_orchestrator = orchestrator

    events = await _collect(
        service,
        request_input=EntityActionInput(type="entity_action", action_id=action_id),
        client_request_id=UUID("bfa2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
        session_id=session_id,
    )

    error = next(block for block in events[1]["message"]["blocks"] if block["type"] == "error")
    assert error["code"] == "PERMISSION_DENIED"
    assert orchestrator.calls == []


@pytest.mark.asyncio
async def test_entity_action_rejects_expired_result_set_before_dispatch(
    application_harness,
    monkeypatch,
) -> None:
    service, session_factory = application_harness
    session_id, action_id = await _start_customer_action(service)
    with session_factory() as db:
        db.add(
            Customer(
                public_id="cus_shanghai_1",
                team_id=1,
                account_name="上海星云科技",
                city="上海",
                owner_id="2",
                creator_id="2",
            )
        )
        result_set = db.query(AgentQueryResultSet).filter_by(public_id="rs_query_application_test").one()
        result_set.expires_at = business_now() - timedelta(seconds=1)
        db.commit()
    monkeypatch.setattr(
        application_module,
        "permission_crud",
        SimpleNamespace(
            get_user_permissions=lambda db, user_id, team_id: [SimpleNamespace(code="customer:follow_up:create")]
        ),
    )
    orchestrator = _FakeRootOrchestrator(_completed_workflow_dispatch())
    service.root_orchestrator = orchestrator

    events = await _collect(
        service,
        request_input=EntityActionInput(type="entity_action", action_id=action_id),
        client_request_id=UUID("cfa2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
        session_id=session_id,
    )

    error = next(block for block in events[1]["message"]["blocks"] if block["type"] == "error")
    assert error["code"] == "RESULT_SET_EXPIRED"
    assert orchestrator.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("choice", "expected_content"),
    [("confirm", "确认创建"), ("cancel", "取消")],
)
async def test_interaction_submission_persists_the_clicked_button_label(
    application_harness,
    choice: str,
    expected_content: str,
) -> None:
    service, session_factory = application_harness
    service.root_orchestrator = _FakeRootOrchestrator(_confirmation_workflow_dispatch())
    initial = await _collect(
        service,
        request_input=TextAgentInput(type="text", text="创建跟进记录"),
        client_request_id=UUID("3fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
    )
    session_id = initial[0]["session_id"]
    interaction = next(block for block in initial[1]["message"]["blocks"] if block["type"] == "interaction")
    action_id = interaction["submit_action_id"]
    action_repository = AgentUIActionRepository()

    def claim_action(turn: RootTurnInput, runtime: RootRuntimeContext) -> None:
        action_repository.begin_consumption(
            runtime.db,
            public_id=action_id,
            team_id=turn.team_id,
            user_id=turn.user_id,
            session_id=turn.session_id,
            client_request_id=turn.client_request_id,
        )

    service.root_orchestrator = _FakeRootOrchestrator(
        _completed_workflow_dispatch(action_claim_id=action_id),
        on_dispatch=claim_action,
    )
    request_id = UUID(
        "4fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be" if choice == "confirm" else "5fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be"
    )

    await _collect(
        service,
        request_input=InteractionSubmissionInput(
            type="interaction_submission",
            action_id=action_id,
            values={"choice": choice},
        ),
        client_request_id=request_id,
        session_id=session_id,
    )

    with session_factory() as db:
        user_message = (
            db.query(AgentMessage)
            .filter(AgentMessage.client_request_id == str(request_id))
            .filter(AgentMessage.role == AgentMessageRole.USER)
            .one()
        )
        assert user_message.content == expected_content
        assert user_message.ui_json["blocks"][0]["text"] == expected_content
        assert user_message.ui_json["metadata"]["accessibility_label"] == expected_content


@pytest.mark.asyncio
async def test_interaction_input_is_claimed_by_root_and_completed_by_application(
    application_harness,
) -> None:
    service, session_factory = application_harness
    session_id, action_id = await _start_interaction(service)
    action_repository = AgentUIActionRepository()

    def claim_action(turn: RootTurnInput, runtime: RootRuntimeContext) -> None:
        assert turn.input.type == "interaction"
        assert turn.input.action_id == action_id
        assert turn.input.values == {"choice": "cus_shanghai_1"}
        action_repository.begin_consumption(
            runtime.db,
            public_id=action_id,
            team_id=turn.team_id,
            user_id=turn.user_id,
            session_id=turn.session_id,
            client_request_id=turn.client_request_id,
        )

    orchestrator = _FakeRootOrchestrator(
        _completed_workflow_dispatch(action_claim_id=action_id),
        on_dispatch=claim_action,
    )
    service.root_orchestrator = orchestrator
    request_id = UUID("dfa2e0e8-86d4-4d6c-a1b0-6490b2bf12be")

    events = await _collect(
        service,
        request_input=InteractionSubmissionInput(
            type="interaction_submission",
            action_id=action_id,
            values={"choice": "cus_shanghai_1"},
        ),
        client_request_id=request_id,
        session_id=session_id,
    )

    assert [event["event"] for event in events] == ["session", "agent_ui", "done"]
    assert len(orchestrator.calls) == 1
    with session_factory() as db:
        action = db.query(AgentUIAction).filter_by(public_id=action_id).one()
        assert action.status == AgentUIActionStatus.CONSUMED
        assert action.consumed_request_id == str(request_id)
        assert action.result_message_id == events[1]["message_id"]
        user_message = (
            db.query(AgentMessage)
            .filter(AgentMessage.client_request_id == str(request_id))
            .filter(AgentMessage.role == AgentMessageRole.USER)
            .one()
        )
        assert user_message.content == "提交"


@pytest.mark.asyncio
async def test_signed_follow_up_text_resume_claims_before_checkpoint_and_settles_old_card(
    application_harness, monkeypatch
) -> None:
    service, session_factory = application_harness
    initial_dispatch = _follow_up_content_workflow_dispatch()
    service.root_orchestrator = _FakeRootOrchestrator(initial_dispatch)
    initial = await _collect(
        service,
        request_input=TextAgentInput(type="text", text="为客户创建跟进"),
        client_request_id=UUID("21a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
    )
    session_id = initial[0]["session_id"]
    old_action_id = next(
        block["submit_action_id"] for block in initial[1]["message"]["blocks"] if block["type"] == "interaction"
    )
    continuation = initial_dispatch.continuation
    assert continuation is not None
    plan = RootRoutingPlan(
        kind="TEXT_WORKFLOW_RESUME",
        context=RootContextSnapshot(active_workflow=continuation.workflow_ref),
        decision=_decision("WORKFLOW", relation="CONTINUE_TASK"),
        continuation=continuation,
    )

    # Exercise the real text-resume adapter while controlling only checkpoint IO.
    orchestrator = object.__new__(RootOrchestrator)
    async def checkpoint_present(config):
        assert config["configurable"]["thread_id"] == continuation.root_thread_id

    async def resume_graph(graph_input, config, *, runtime, on_progress):
        del graph_input, config, on_progress
        with session_factory() as db:
            old_action = db.query(AgentUIAction).filter_by(public_id=old_action_id).one()
            assert old_action.status == AgentUIActionStatus.CONSUMING
            with pytest.raises(ActionAlreadyConsumedError):
                service.action_repository.begin_consumption(
                    db, public_id=old_action_id, team_id=1, user_id=2, session_id=session_id,
                    client_request_id=UUID("30a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
                )
        return {"dispatch_result": _completed_workflow_dispatch().model_dump(mode="json")}, None

    monkeypatch.setattr(orchestrator, "_require_continuation_checkpoint", checkpoint_present)
    monkeypatch.setattr(orchestrator, "_invoke_graph", resume_graph)

    async def dispatch(turn, *, runtime, on_progress=None):
        return await orchestrator._resume_text_plan(
            turn=turn,
            runtime=runtime,
            config=build_root_graph_config(turn),
            plan=plan,
            on_progress=on_progress,
        )

    monkeypatch.setattr(orchestrator, "dispatch", dispatch)
    service.root_orchestrator = orchestrator
    request_id = UUID("22a2e0e8-86d4-4d6c-a1b0-6490b2bf12be")
    resumed = await _collect(
        service,
        request_input=TextAgentInput(type="text", text="今天联系客户，下一步回访"),
        client_request_id=request_id,
        session_id=session_id,
    )
    assert [event["event"] for event in resumed] == ["session", "agent_ui", "done"]
    with session_factory() as db:
        old_action = db.query(AgentUIAction).filter_by(public_id=old_action_id).one()
        assert old_action.status == AgentUIActionStatus.CONSUMED, resumed[1]
        assert old_action.consumed_request_id == str(request_id)
        assert old_action.result_message_id == resumed[1]["message_id"]
        with pytest.raises(ActionAlreadyConsumedError):
            service.action_repository.begin_consumption(
                db, public_id=old_action_id, team_id=1, user_id=2, session_id=session_id,
                client_request_id=UUID("23a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
            )


@pytest.mark.asyncio
async def test_signed_text_resume_waiting_next_card_settles_only_old_card(application_harness, monkeypatch) -> None:
    service, session_factory = application_harness
    waiting = _follow_up_content_workflow_dispatch()
    service.root_orchestrator = _FakeRootOrchestrator(waiting)
    initial = await _collect(
        service, request_input=TextAgentInput(type="text", text="创建跟进"),
        client_request_id=UUID("34a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
    )
    session_id = initial[0]["session_id"]
    old_action_id = next(
        block["submit_action_id"] for block in initial[1]["message"]["blocks"] if block["type"] == "interaction"
    )
    continuation = waiting.continuation
    assert continuation is not None
    next_ref = WorkflowRef(workflow_id="wf_follow_up", interrupt_id="intr_next")
    next_continuation = continuation.model_copy(
        update={
            "workflow_ref": next_ref,
            "parent_checkpoint_id": "parent_cp_next",
            "subgraph_checkpoint_id": "child_cp_next",
        }
    )
    next_waiting = waiting.model_copy(
        update={
            "workflow_result": waiting.workflow_result.model_copy(update={"workflow_ref": next_ref}),
            "continuation": next_continuation,
        }
    )
    plan = RootRoutingPlan(
        kind="TEXT_WORKFLOW_RESUME",
        context=RootContextSnapshot(active_workflow=continuation.workflow_ref),
        decision=_decision("WORKFLOW", relation="CONTINUE_TASK"), continuation=continuation,
    )
    orchestrator = object.__new__(RootOrchestrator)

    async def checkpoint_present(config):
        del config

    async def resume_graph(graph_input, config, *, runtime, on_progress):
        del graph_input, config, runtime, on_progress
        return {"dispatch_result": None}, next_continuation
    monkeypatch.setattr(orchestrator, "_require_continuation_checkpoint", checkpoint_present)
    monkeypatch.setattr(orchestrator, "_invoke_graph", resume_graph)
    monkeypatch.setattr(orchestrator, "_dispatch_result_from_state", lambda state, *, continuation: next_waiting)

    async def dispatch(turn, *, runtime, on_progress=None):
        return await orchestrator._resume_text_plan(
            turn=turn, runtime=runtime, config=build_root_graph_config(turn),
            plan=plan, on_progress=on_progress,
        )

    monkeypatch.setattr(orchestrator, "dispatch", dispatch)
    service.root_orchestrator = orchestrator
    request_id = UUID("35a2e0e8-86d4-4d6c-a1b0-6490b2bf12be")
    result = await _collect(
        service, request_input=TextAgentInput(type="text", text="客户想要回访"),
        client_request_id=request_id, session_id=session_id,
    )
    next_action_id = next(
        block["submit_action_id"] for block in result[1]["message"]["blocks"] if block["type"] == "interaction"
    )
    assert old_action_id != next_action_id
    with session_factory() as db:
        old = db.query(AgentUIAction).filter_by(public_id=old_action_id).one()
        newer = db.query(AgentUIAction).filter_by(public_id=next_action_id).one()
        assert old.status == AgentUIActionStatus.CONSUMED
        assert old.result_message_id == result[1]["message_id"]
        assert newer.status == AgentUIActionStatus.ACTIVE
        assert newer.consumed_request_id is None
        assert newer.target_json["workflow_continuation"]["parent_checkpoint_id"] == "parent_cp_next"


@pytest.mark.asyncio
async def test_cancelled_follow_up_card_blocks_late_text_checkpoint(application_harness, monkeypatch) -> None:
    service, session_factory = application_harness
    waiting = _follow_up_content_workflow_dispatch()
    service.root_orchestrator = _FakeRootOrchestrator(waiting)
    initial = await _collect(
        service, request_input=TextAgentInput(type="text", text="准备跟进"),
        client_request_id=UUID("31a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
    )
    session_id = initial[0]["session_id"]
    action_id = next(
        block["submit_action_id"] for block in initial[1]["message"]["blocks"] if block["type"] == "interaction"
    )
    continuation = waiting.continuation
    assert continuation is not None
    plan = RootRoutingPlan(
        kind="TEXT_WORKFLOW_RESUME",
        context=RootContextSnapshot(active_workflow=continuation.workflow_ref),
        decision=_decision("WORKFLOW", relation="CONTINUE_TASK"), continuation=continuation,
    )
    orchestrator = object.__new__(RootOrchestrator)

    async def forbidden_checkpoint(config):
        del config
        pytest.fail("text continuation ran after cancellation won the action")

    monkeypatch.setattr(orchestrator, "_require_continuation_checkpoint", forbidden_checkpoint)

    async def dispatch(turn, *, runtime, on_progress=None):
        return await orchestrator._resume_text_plan(
            turn=turn, runtime=runtime, config=build_root_graph_config(turn),
            plan=plan, on_progress=on_progress,
        )

    with session_factory() as db:
        service.action_repository.begin_consumption(
            db, public_id=action_id, team_id=1, user_id=2, session_id=session_id,
            client_request_id=UUID("32a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
        )
        db.commit()
    monkeypatch.setattr(orchestrator, "dispatch", dispatch)
    service.root_orchestrator = orchestrator
    events = await _collect(
        service, request_input=TextAgentInput(type="text", text="迟到的补充"),
        client_request_id=UUID("33a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"), session_id=session_id,
    )
    assert events[1]["message"]["blocks"][0]["code"] == "ACTION_ALREADY_CONSUMED"
    with session_factory() as db:
        action = db.query(AgentUIAction).filter_by(public_id=action_id).one()
        assert action.status == AgentUIActionStatus.CONSUMING
        assert action.consumed_request_id == "32a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"




@pytest.mark.asyncio
async def test_failed_signed_text_resume_releases_old_card_for_retry(application_harness, monkeypatch) -> None:
    service, session_factory = application_harness
    first = _follow_up_content_workflow_dispatch()
    service.root_orchestrator = _FakeRootOrchestrator(first)
    initial = await _collect(
        service, request_input=TextAgentInput(type="text", text="记录客户跟进"),
        client_request_id=UUID("24a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
    )
    session_id = initial[0]["session_id"]
    action_id = next(
        block["submit_action_id"] for block in initial[1]["message"]["blocks"] if block["type"] == "interaction"
    )
    continuation = first.continuation
    assert continuation is not None
    plan = RootRoutingPlan(
        kind="TEXT_WORKFLOW_RESUME",
        context=RootContextSnapshot(active_workflow=continuation.workflow_ref),
        decision=_decision("WORKFLOW", relation="CONTINUE_TASK"),
        continuation=continuation,
    )
    orchestrator = object.__new__(RootOrchestrator)

    async def missing_checkpoint(config):
        del config
        raise WorkflowCheckpointUnavailableError("missing checkpoint")

    async def dispatch(turn, *, runtime, on_progress=None):
        return await orchestrator._resume_text_plan(
            turn=turn, runtime=runtime, config=build_root_graph_config(turn),
            plan=plan, on_progress=on_progress,
        )

    monkeypatch.setattr(orchestrator, "dispatch", dispatch)
    service.root_orchestrator = orchestrator
    failure = await _collect(
        service, request_input=TextAgentInput(type="text", text="今天回访客户"),
        client_request_id=UUID("25a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"), session_id=session_id,
    )
    assert failure[1]["message"]["blocks"][0]["retryable"] is True
    with session_factory() as db:
        action = db.query(AgentUIAction).filter_by(public_id=action_id).one()
        assert action.status == AgentUIActionStatus.ACTIVE
        assert action.consumed_request_id is None


@pytest.mark.asyncio
async def test_other_text_workflow_resume_keeps_existing_path(application_harness, monkeypatch) -> None:
    service, session_factory = application_harness
    waiting = _follow_up_content_workflow_dispatch()
    waiting = waiting.model_copy(
        update={
            "workflow_result": waiting.workflow_result.model_copy(
                update={
                    "interaction": waiting.workflow_result.interaction.model_copy(
                        update={"business_action": "supplement_follow_up_quality", "allow_cancel": False}
                    )
                }
            )
        }
    )
    service.root_orchestrator = _FakeRootOrchestrator(waiting)
    initial = await _collect(
        service, request_input=TextAgentInput(type="text", text="补充跟进信息"),
        client_request_id=UUID("28a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
    )
    action_id = next(
        block["submit_action_id"] for block in initial[1]["message"]["blocks"] if block["type"] == "interaction"
    )
    continuation = waiting.continuation
    assert continuation is not None
    plan = RootRoutingPlan(
        kind="TEXT_WORKFLOW_RESUME",
        context=RootContextSnapshot(active_workflow=continuation.workflow_ref),
        decision=_decision("WORKFLOW", relation="CONTINUE_TASK"), continuation=continuation,
    )
    orchestrator = object.__new__(RootOrchestrator)

    async def checkpoint_present(config):
        del config

    async def resume_graph(graph_input, config, *, runtime, on_progress):
        del graph_input, config, runtime, on_progress
        return {"dispatch_result": _completed_workflow_dispatch().model_dump(mode="json")}, None

    monkeypatch.setattr(orchestrator, "_require_continuation_checkpoint", checkpoint_present)
    monkeypatch.setattr(orchestrator, "_invoke_graph", resume_graph)

    async def dispatch(turn, *, runtime, on_progress=None):
        return await orchestrator._resume_text_plan(
            turn=turn, runtime=runtime, config=build_root_graph_config(turn),
            plan=plan, on_progress=on_progress,
        )

    monkeypatch.setattr(orchestrator, "dispatch", dispatch)
    service.root_orchestrator = orchestrator
    result = await _collect(
        service, request_input=TextAgentInput(type="text", text="客户希望下周回访"),
        client_request_id=UUID("29a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
        session_id=initial[0]["session_id"],
    )
    assert result[1]["message"]["blocks"][0]["type"] != "error"
    with session_factory() as db:
        assert db.query(AgentUIAction).filter_by(public_id=action_id).one().status == AgentUIActionStatus.ACTIVE


@pytest.mark.asyncio
async def test_text_resume_exception_releases_committed_action_claim(application_harness, monkeypatch) -> None:
    service, session_factory = application_harness
    initial_dispatch = _follow_up_content_workflow_dispatch()
    service.root_orchestrator = _FakeRootOrchestrator(initial_dispatch)
    initial = await _collect(
        service, request_input=TextAgentInput(type="text", text="跟进客户"),
        client_request_id=UUID("26a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
    )
    session_id = initial[0]["session_id"]
    action_id = next(
        block["submit_action_id"] for block in initial[1]["message"]["blocks"] if block["type"] == "interaction"
    )
    continuation = initial_dispatch.continuation
    assert continuation is not None
    plan = RootRoutingPlan(
        kind="TEXT_WORKFLOW_RESUME",
        context=RootContextSnapshot(active_workflow=continuation.workflow_ref),
        decision=_decision("WORKFLOW", relation="CONTINUE_TASK"), continuation=continuation,
    )
    orchestrator = object.__new__(RootOrchestrator)

    async def checkpoint_present(config):
        del config

    async def crashed_graph(graph_input, config, *, runtime, on_progress):
        del graph_input, config, runtime, on_progress
        raise RuntimeError("resume crashed after claim")

    monkeypatch.setattr(orchestrator, "_require_continuation_checkpoint", checkpoint_present)
    monkeypatch.setattr(orchestrator, "_invoke_graph", crashed_graph)

    async def dispatch(turn, *, runtime, on_progress=None):
        return await orchestrator._resume_text_plan(
            turn=turn, runtime=runtime, config=build_root_graph_config(turn),
            plan=plan, on_progress=on_progress,
        )

    monkeypatch.setattr(orchestrator, "dispatch", dispatch)
    service.root_orchestrator = orchestrator
    await _collect(
        service, request_input=TextAgentInput(type="text", text="继续补充"),
        client_request_id=UUID("27a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"), session_id=session_id,
    )
    with session_factory() as db:
        action = db.query(AgentUIAction).filter_by(public_id=action_id).one()
        assert action.status == AgentUIActionStatus.ACTIVE
        assert action.consumed_request_id is None


@pytest.mark.asyncio
async def test_follow_up_content_cancel_settles_action_and_erases_task_context_for_new_request(
    application_harness,
) -> None:
    service, session_factory = application_harness
    service.root_orchestrator = _FakeRootOrchestrator(_follow_up_content_workflow_dispatch())
    initial = await _collect(
        service,
        request_input=TextAgentInput(type="text", text="为河南双汇创建跟进，下一步回访"),
        client_request_id=UUID("00a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
    )
    assert [event["event"] for event in initial] == ["session", "agent_ui", "done"], initial
    session_id = initial[0]["session_id"]
    action_id = next(
        block["submit_action_id"] for block in initial[1]["message"]["blocks"] if block["type"] == "interaction"
    )
    with session_factory() as db:
        session = db.query(AgentSession).filter_by(id=session_id).one()
        session.context_json = {"client_context": {"view": "customers"}}
        db.commit()

    def claim_and_persist_old_draft(turn: RootTurnInput, runtime: RootRuntimeContext) -> None:
        assert turn.input.type == "interaction"
        assert turn.input.values == {"cancel": True}
        service.action_repository.begin_consumption(
            runtime.db,
            public_id=action_id,
            team_id=turn.team_id,
            user_id=turn.user_id,
            session_id=turn.session_id,
            client_request_id=turn.client_request_id,
        )
        DatabaseRootContextResolver().persist_conversation_memory(
            runtime.db,
            turn=turn,
            memory=RootConversationMemory(
                resolved_customer={
                    "customer_id": "cus_00000000000000000000000000000001",
                    "customer_name": "河南双汇实业有限公司",
                },
                current_task="customer_activity",
                known_activity_content="旧跟进正文",
                known_next_action="回访",
                pending_question="请补充跟进内容",
                user_corrections=["旧任务补充"],
            ),
        )

    orchestrator = _FakeRootOrchestrator(
        _cancelled_workflow_dispatch(action_id), on_dispatch=claim_and_persist_old_draft
    )
    service.root_orchestrator = orchestrator
    request = InteractionSubmissionInput(type="interaction_submission", action_id=action_id, values={"cancel": True})
    request_id = UUID("01a2e0e8-86d4-4d6c-a1b0-6490b2bf12be")
    events = await _collect(service, request_input=request, client_request_id=request_id, session_id=session_id)
    result_message_id = events[1]["message_id"]
    assert [event["event"] for event in events] == ["session", "agent_ui", "done"]
    with session_factory() as db:
        action = db.query(AgentUIAction).filter_by(public_id=action_id).one()
        session = db.query(AgentSession).filter_by(id=session_id).one()
        user_message = (
            db.query(AgentMessage).filter_by(client_request_id=str(request_id), role=AgentMessageRole.USER).one()
        )
        assert user_message.content == "取消"
        assert action.status == AgentUIActionStatus.CANCELLED
        assert action.submitted_values == {"cancel": True}
        assert action.result_message_id == result_message_id
        assert session.context_json["client_context"] == {"view": "customers"}
        assert DatabaseRootContextResolver._read_conversation_memory(session) == RootConversationMemory()
        next_turn = RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=session_id,
            client_request_id="new-complete-request",
            input=TextTurnInput(type="text", text="为新客户创建完整跟进"),
        )
        snapshot = await DatabaseRootContextResolver().resolve(turn=next_turn, runtime=RootRuntimeContext(db=db))
        assert snapshot.conversation_memory == RootConversationMemory()
        assert snapshot.recent_messages == []
        assert snapshot.active_workflow is None

    replay = await _collect(service, request_input=request, client_request_id=request_id, session_id=session_id)
    assert replay[1] == events[1]
    assert len(orchestrator.calls) == 1


@pytest.mark.asyncio
async def test_failed_follow_up_content_cancel_retains_task_memory_and_retryable_action(
    application_harness,
) -> None:
    service, session_factory = application_harness
    service.root_orchestrator = _FakeRootOrchestrator(_follow_up_content_workflow_dispatch())
    initial = await _collect(
        service,
        request_input=TextAgentInput(type="text", text="为河南双汇创建跟进"),
        client_request_id=UUID("02a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
    )
    session_id = initial[0]["session_id"]
    action_id = next(
        block["submit_action_id"] for block in initial[1]["message"]["blocks"] if block["type"] == "interaction"
    )
    memory = RootConversationMemory(current_task="customer_activity", known_activity_content="旧草稿")
    with session_factory() as db:
        session = db.query(AgentSession).filter_by(id=session_id).one()
        session.context_json = {"_root_conversation_memory": memory.model_dump(mode="json", exclude_none=True)}
        db.commit()

    def claim_action(turn: RootTurnInput, runtime: RootRuntimeContext) -> None:
        service.action_repository.begin_consumption(
            runtime.db,
            public_id=action_id,
            team_id=turn.team_id,
            user_id=turn.user_id,
            session_id=turn.session_id,
            client_request_id=turn.client_request_id,
        )

    service.root_orchestrator = _FakeRootOrchestrator(
        WorkflowDispatchResult(
            decision=_decision("WORKFLOW", relation="CONTINUE_TASK"),
            workflow_result=WorkflowFailedResult(
                workflow_ref=WorkflowRef(workflow_id="wf_follow_up"),
                code="CHECKPOINT_UNAVAILABLE",
                message="会话状态服务暂时不可用。",
                retryable=True,
                progress=execution_progress(confirmation_required=False, has_supplements=False, outcome="FAILED"),
            ),
            action_claim_id=action_id,
        ),
        on_dispatch=claim_action,
    )
    await _collect(
        service,
        request_input=InteractionSubmissionInput(
            type="interaction_submission", action_id=action_id, values={"cancel": True}
        ),
        client_request_id=UUID("03a2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
        session_id=session_id,
    )
    with session_factory() as db:
        action = db.query(AgentUIAction).filter_by(public_id=action_id).one()
        session = db.query(AgentSession).filter_by(id=session_id).one()
        assert action.status == AgentUIActionStatus.ACTIVE
        assert action.result_message_id is None
        assert DatabaseRootContextResolver._read_conversation_memory(session) == memory


@pytest.mark.asyncio
async def test_compact_task_completion_is_persisted_as_state_update_without_visible_turn_messages(
    application_harness,
) -> None:
    service, session_factory = application_harness
    session_id, action_id = await _start_interaction(service)
    action_repository = AgentUIActionRepository()

    with session_factory() as db:
        action = db.query(AgentUIAction).filter_by(public_id=action_id).one()
        action.target_json = {**action.target_json, "result_display": "STATE_UPDATE"}
        db.commit()

    def claim_action(turn: RootTurnInput, runtime: RootRuntimeContext) -> None:
        action_repository.begin_consumption(
            runtime.db,
            public_id=action_id,
            team_id=turn.team_id,
            user_id=turn.user_id,
            session_id=turn.session_id,
            client_request_id=turn.client_request_id,
        )

    service.root_orchestrator = _FakeRootOrchestrator(
        _completed_workflow_dispatch(action_claim_id=action_id),
        on_dispatch=claim_action,
    )
    request_id = UUID("efa2e0e8-86d4-4d6c-a1b0-6490b2bf12be")

    events = await _collect(
        service,
        request_input=InteractionSubmissionInput(
            type="interaction_submission",
            action_id=action_id,
            values={"choice": "cus_shanghai_1"},
        ),
        client_request_id=request_id,
        session_id=session_id,
    )

    assert events[1]["message"]["metadata"]["display"] == "STATE_UPDATE"
    with session_factory() as db:
        turn_messages = db.query(AgentMessage).filter(AgentMessage.client_request_id == str(request_id)).all()
        assert len(turn_messages) == 1
        assistant = (
            db.query(AgentMessage)
            .filter(AgentMessage.turn_id == turn_messages[0].turn_id)
            .filter(AgentMessage.role == AgentMessageRole.ASSISTANT)
            .one()
        )
        assert turn_messages[0].ui_json["metadata"]["display"] == "STATE_UPDATE"
        assert assistant.ui_json["metadata"]["display"] == "STATE_UPDATE"


@pytest.mark.asyncio
async def test_consumed_interaction_closes_the_already_persisted_turn_with_one_final_error(
    application_harness,
) -> None:
    service, session_factory = application_harness
    session_id, action_id = await _start_interaction(service)

    def reject_consumed_action(turn: RootTurnInput, runtime: RootRuntimeContext) -> None:
        del turn, runtime
        raise ActionAlreadyConsumedError("action already consumed")

    service.root_orchestrator = _FakeRootOrchestrator(
        _completed_workflow_dispatch(),
        on_dispatch=reject_consumed_action,
    )
    request_id = UUID("ffa2e0e8-86d4-4d6c-a1b0-6490b2bf12be")
    request = InteractionSubmissionInput(
        type="interaction_submission",
        action_id=action_id,
        values={"choice": "cus_shanghai_1"},
    )

    first = await _collect(
        service,
        request_input=request,
        client_request_id=request_id,
        session_id=session_id,
    )
    replay = await _collect(
        service,
        request_input=request,
        client_request_id=request_id,
        session_id=session_id,
    )

    assert [event["event"] for event in first] == ["session", "agent_ui", "done"]
    assert first[1]["message"] == replay[1]["message"]
    error_blocks = [block for block in first[1]["message"]["blocks"] if block["type"] == "error"]
    assert len(error_blocks) == 1
    assert error_blocks[0]["code"] == "ACTION_ALREADY_CONSUMED"
    assert not any(block["type"] == "text" for block in first[1]["message"]["blocks"])
    with session_factory() as db:
        turn_messages = db.query(AgentMessage).filter(AgentMessage.client_request_id == str(request_id)).all()
        assert len(turn_messages) == 1
        assistant_messages = (
            db.query(AgentMessage)
            .filter(AgentMessage.turn_id == turn_messages[0].turn_id)
            .filter(AgentMessage.role == AgentMessageRole.ASSISTANT)
            .all()
        )
        assert len(assistant_messages) == 1


@pytest.mark.asyncio
async def test_completed_workflow_late_binds_durable_work_after_turn_commit(
    application_harness,
) -> None:
    service, session_factory = application_harness
    binder = _CapturingDurableWorkBinder()
    service.durable_work_binder = binder
    service.root_orchestrator = _FakeRootOrchestrator(
        WorkflowDispatchResult(
            decision=_decision("WORKFLOW"),
            workflow_result=WorkflowCompletedResult(
                workflow_ref=WorkflowRef(workflow_id="wf_durable_work"),
                assistant_text="已记录客户跟进。",
                progress=execution_progress(
                    confirmation_required=False,
                    has_supplements=False,
                    outcome="COMPLETED",
                ),
                durable_work=[
                    CustomerActivityDurableWorkReceipt(
                        activity_id=241,
                        post_commit_job_public_id="pcj_application_001",
                        customer_intelligence_request_id="cir_application_001",
                    )
                ],
            ),
        )
    )

    events = await _collect(
        service,
        request_input=TextAgentInput(type="text", text="记录一条客户跟进"),
        client_request_id=UUID("dfa2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
    )

    assert [event["event"] for event in events] == ["session", "agent_ui", "done"]
    assert len(binder.calls) == 1
    call = binder.calls[0]
    assert call["receipts"][0].activity_id == 241
    assert call["binding"].source_assistant_message_id == events[1]["message_id"]
    with session_factory() as db:
        assistant = db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).one()
        diagnostics = assistant.diagnostics_json
        assert diagnostics is not None
        assert diagnostics["dispatch_type"] == "workflow"
        assert diagnostics["durable_work"][0]["activity_id"] == 241
        observability = diagnostics["turn_observability"]
        assert observability["outcome"] == "written"
        assert observability["steps"][-1]["kind"] == "background"
        assert observability["steps"][-1]["tone"] == "done"


@pytest.mark.asyncio
async def test_interaction_failure_releases_root_action_claim_and_hides_state_update_turn(
    application_harness,
) -> None:
    service, session_factory = application_harness
    session_id, action_id = await _start_interaction(service)
    action_repository = AgentUIActionRepository()

    with session_factory() as db:
        action = db.query(AgentUIAction).filter_by(public_id=action_id).one()
        action.target_json = {**action.target_json, "result_display": "STATE_UPDATE"}
        db.commit()

    def claim_action(turn: RootTurnInput, runtime: RootRuntimeContext) -> None:
        action_repository.begin_consumption(
            runtime.db,
            public_id=action_id,
            team_id=turn.team_id,
            user_id=turn.user_id,
            session_id=turn.session_id,
            client_request_id=turn.client_request_id,
        )

    orchestrator = _FakeRootOrchestrator(
        FailureDispatchResult(
            error=AgentExecutionError(
                code="CHECKPOINT_UNAVAILABLE",
                message="会话状态服务暂时不可用。",
                retryable=True,
            ),
            action_claim_id=action_id,
        ),
        on_dispatch=claim_action,
    )
    service.root_orchestrator = orchestrator

    events = await _collect(
        service,
        request_input=InteractionSubmissionInput(
            type="interaction_submission",
            action_id=action_id,
            values={"choice": "cus_shanghai_1"},
        ),
        client_request_id=UUID("efa2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
        session_id=session_id,
    )

    error = next(block for block in events[1]["message"]["blocks"] if block["type"] == "error")
    assert error["code"] == "CHECKPOINT_UNAVAILABLE"
    assert events[1]["message"]["metadata"]["display"] == "STATE_UPDATE"
    with session_factory() as db:
        action = db.query(AgentUIAction).filter_by(public_id=action_id).one()
        assert action.status == AgentUIActionStatus.ACTIVE
        assert action.consumed_request_id is None
        assert action.result_message_id is None


@pytest.mark.asyncio
async def test_failed_workflow_releases_root_action_claim(
    application_harness,
) -> None:
    service, session_factory = application_harness
    session_id, action_id = await _start_interaction(service)
    action_repository = AgentUIActionRepository()

    def claim_action(turn: RootTurnInput, runtime: RootRuntimeContext) -> None:
        action_repository.begin_consumption(
            runtime.db,
            public_id=action_id,
            team_id=turn.team_id,
            user_id=turn.user_id,
            session_id=turn.session_id,
            client_request_id=turn.client_request_id,
        )

    service.root_orchestrator = _FakeRootOrchestrator(
        WorkflowDispatchResult(
            decision=_decision("WORKFLOW", relation="CONTINUE_TASK"),
            workflow_result=WorkflowFailedResult(
                workflow_ref=WorkflowRef(workflow_id="wf_customer_follow_up"),
                code="CRM_WRITE_FAILED",
                message="待办完成失败。",
                retryable=True,
                progress=execution_progress(
                    confirmation_required=False,
                    has_supplements=False,
                    outcome="FAILED",
                ),
            ),
            action_claim_id=action_id,
        ),
        on_dispatch=claim_action,
    )

    await _collect(
        service,
        request_input=InteractionSubmissionInput(
            type="interaction_submission",
            action_id=action_id,
            values={"choice": "cus_shanghai_1"},
        ),
        client_request_id=UUID("ffa2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
        session_id=session_id,
    )

    with session_factory() as db:
        action = db.query(AgentUIAction).filter_by(public_id=action_id).one()
        assert action.status == AgentUIActionStatus.ACTIVE
        assert action.consumed_request_id is None
        assert action.result_message_id is None


@pytest.mark.asyncio
async def test_non_retryable_failed_workflow_completes_root_action_claim(
    application_harness,
) -> None:
    service, session_factory = application_harness
    session_id, action_id = await _start_interaction(service)
    action_repository = AgentUIActionRepository()

    def claim_action(turn: RootTurnInput, runtime: RootRuntimeContext) -> None:
        action_repository.begin_consumption(
            runtime.db,
            public_id=action_id,
            team_id=turn.team_id,
            user_id=turn.user_id,
            session_id=turn.session_id,
            client_request_id=turn.client_request_id,
        )

    service.root_orchestrator = _FakeRootOrchestrator(
        WorkflowDispatchResult(
            decision=_decision("WORKFLOW", relation="CONTINUE_TASK"),
            workflow_result=WorkflowFailedResult(
                workflow_ref=WorkflowRef(workflow_id="wf_create_lead"),
                code="WORKFLOW_CRM_API_REJECTED",
                message=(
                    "已创建线索「上海云图科技」，但首次跟进没写上：跟进方式无效。\n"
                    "请直接为这条线索补充跟进（电话 / 微信 / 拜访 / 邮件 / 其他），不要再创建同一条线索。"
                ),
                retryable=False,
                progress=execution_progress(
                    confirmation_required=True,
                    has_supplements=False,
                    outcome="FAILED",
                ),
            ),
            action_claim_id=action_id,
        ),
        on_dispatch=claim_action,
    )

    await _collect(
        service,
        request_input=InteractionSubmissionInput(
            type="interaction_submission",
            action_id=action_id,
            values={"choice": "confirm"},
        ),
        client_request_id=UUID("aaa2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
        session_id=session_id,
    )

    with session_factory() as db:
        action = db.query(AgentUIAction).filter_by(public_id=action_id).one()
        assert action.status == AgentUIActionStatus.CONSUMED
        assert action.submitted_values == {"choice": "confirm"}
        assert action.result_message_id is not None
        assert (
            action_repository.list_active_workflow_continuations(
                db,
                team_id=1,
                user_id=2,
                session_id=session_id,
            )
            == []
        )


@pytest.mark.asyncio
async def test_entity_action_dispatch_exception_releases_prepared_claim(
    application_harness,
    monkeypatch,
) -> None:
    service, session_factory = application_harness
    session_id, action_id = await _start_customer_action(service)
    with session_factory() as db:
        db.add(
            Customer(
                public_id="cus_shanghai_1",
                team_id=1,
                account_name="上海星云科技",
                city="上海",
                owner_id="2",
                creator_id="2",
            )
        )
        db.commit()
    monkeypatch.setattr(
        application_module,
        "permission_crud",
        SimpleNamespace(
            get_user_permissions=lambda db, user_id, team_id: [SimpleNamespace(code="customer:follow_up:create")]
        ),
    )

    def fail_dispatch(turn: RootTurnInput, runtime: RootRuntimeContext) -> None:
        del turn, runtime
        raise RuntimeError("workflow dispatch failed")

    service.root_orchestrator = _FakeRootOrchestrator(
        _completed_workflow_dispatch(),
        on_dispatch=fail_dispatch,
    )
    request_id = UUID("10a2e0e8-86d4-4d6c-a1b0-6490b2bf12be")

    events = await _collect(
        service,
        request_input=EntityActionInput(type="entity_action", action_id=action_id),
        client_request_id=request_id,
        session_id=session_id,
    )

    assert [event["event"] for event in events] == ["session", "agent_ui", "done"]
    error = next(block for block in events[1]["message"]["blocks"] if block["type"] == "error")
    assert error["code"] == "INTERNAL_ERROR"
    with session_factory() as db:
        action = db.query(AgentUIAction).filter_by(public_id=action_id).one()
        assert action.status == AgentUIActionStatus.ACTIVE
        assert action.consumed_request_id is None
        assert action.result_message_id is None


@pytest.mark.asyncio
async def test_interaction_dispatch_exception_releases_committed_action_claim(
    application_harness,
) -> None:
    service, session_factory = application_harness
    session_id, action_id = await _start_interaction(service)
    action_repository = AgentUIActionRepository()
    with session_factory() as db:
        action = db.query(AgentUIAction).filter_by(public_id=action_id).one()
        action.target_json = {**action.target_json, "result_display": "STATE_UPDATE"}
        db.commit()

    def claim_then_fail(turn: RootTurnInput, runtime: RootRuntimeContext) -> None:
        action_repository.begin_consumption(
            runtime.db,
            public_id=action_id,
            team_id=turn.team_id,
            user_id=turn.user_id,
            session_id=turn.session_id,
            client_request_id=turn.client_request_id,
        )
        runtime.db.commit()
        raise RuntimeError("workflow continuation crashed")

    service.root_orchestrator = _FakeRootOrchestrator(
        _completed_workflow_dispatch(),
        on_dispatch=claim_then_fail,
    )
    request_id = UUID("11a2e0e8-86d4-4d6c-a1b0-6490b2bf12be")

    events = await _collect(
        service,
        request_input=InteractionSubmissionInput(
            type="interaction_submission",
            action_id=action_id,
            values={"choice": "cus_shanghai_1"},
        ),
        client_request_id=request_id,
        session_id=session_id,
    )

    assert [event["event"] for event in events] == ["session", "agent_ui", "done"]
    assert events[1]["message"]["metadata"]["display"] == "STATE_UPDATE"
    with session_factory() as db:
        action = db.query(AgentUIAction).filter_by(public_id=action_id).one()
        assert action.status == AgentUIActionStatus.ACTIVE
        assert action.consumed_request_id is None
        assert action.result_message_id is None


@pytest.mark.asyncio
async def test_rejected_interaction_failure_does_not_consume_active_action(
    application_harness,
) -> None:
    service, session_factory = application_harness
    session_id, action_id = await _start_interaction(service)
    service.root_orchestrator = _FakeRootOrchestrator(
        FailureDispatchResult(
            error=AgentExecutionError(
                code="ACTION_INVALID",
                message="提交的操作无效,请刷新会话后重试。",
                retryable=False,
            )
        )
    )
    request_id = UUID("0fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be")

    events = await _collect(
        service,
        request_input=InteractionSubmissionInput(
            type="interaction_submission",
            action_id=action_id,
            values={"choice": "unsupported"},
        ),
        client_request_id=request_id,
        session_id=session_id,
    )

    assert [event["event"] for event in events] == ["session", "agent_ui", "done"]
    error_blocks = [block for block in events[1]["message"]["blocks"] if block["type"] == "error"]
    assert len(error_blocks) == 1
    assert error_blocks[0]["code"] == "ACTION_INVALID"
    assert not any(block["type"] == "text" for block in events[1]["message"]["blocks"])
    with session_factory() as db:
        action = db.query(AgentUIAction).filter_by(public_id=action_id).one()
        assert action.status == AgentUIActionStatus.ACTIVE
        assert action.consumed_request_id is None
        assert action.result_message_id is None


@pytest.mark.asyncio
async def test_workflow_replay_uses_persisted_message_without_creating_another_assistant(
    application_harness,
) -> None:
    service, session_factory = application_harness
    initial = await _collect(
        service,
        request_input=TextAgentInput(type="text", text="我在上海有哪些客户"),
        client_request_id=UUID("1fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
    )
    session_id = initial[0]["session_id"]
    message_id = initial[1]["message_id"]
    service.root_orchestrator = _FakeRootOrchestrator(
        WorkflowDispatchResult(
            decision=_decision("WORKFLOW", relation="CONTINUE_TASK"),
            workflow_result=WorkflowReplayResult(
                workflow_ref=WorkflowRef(workflow_id="wf_customer_follow_up"),
                message_id=message_id,
            ),
        )
    )

    replay = await _collect(
        service,
        request_input=InteractionSubmissionInput(
            type="interaction_submission",
            action_id="act_replayed_by_root",
            values={"choice": "cus_shanghai_1"},
        ),
        client_request_id=UUID("2fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
        session_id=session_id,
    )

    assert replay[1] == initial[1]
    with session_factory() as db:
        assert db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).count() == 1


@pytest.mark.asyncio
async def test_completed_request_replays_same_persisted_final_without_dispatch(
    application_harness,
) -> None:
    service, _ = application_harness
    orchestrator = _FakeRootOrchestrator(_query_dispatch())
    service.root_orchestrator = orchestrator
    request = TextAgentInput(type="text", text="我在上海有哪些客户")

    first = await _collect(service, request_input=request, client_request_id=_REQUEST_ID)
    second = await _collect(
        service,
        request_input=request,
        client_request_id=_REQUEST_ID,
        session_id=first[0]["session_id"],
    )

    assert second[1] == first[1]
    assert len(orchestrator.calls) == 1


@pytest.mark.asyncio
async def test_application_commits_root_memory_with_final_turn(application_harness) -> None:
    service, session_factory = application_harness
    memory = RootConversationMemory(
        resolved_customer={
            "customer_id": "cus_00000000000000000000000000000001",
            "customer_name": "河南双汇实业有限公司",
            "lookup_name": "河南双汇",
        },
        current_task="customer_activity",
    )

    def persist_memory(turn: RootTurnInput, runtime: RootRuntimeContext) -> None:
        DatabaseRootContextResolver().persist_conversation_memory(
            runtime.db,
            turn=turn,
            memory=memory,
        )

    service.root_orchestrator = _FakeRootOrchestrator(
        _query_dispatch(),
        on_dispatch=persist_memory,
    )
    events = await _collect(
        service,
        request_input=TextAgentInput(type="text", text="刚刚和河南双汇沟通了 POC 部署"),
        client_request_id=UUID("6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12cf"),
    )

    assert events[-1]["event"] == "done"
    session_id = events[0]["session_id"]
    with session_factory() as db:
        session = db.get(AgentSession, session_id)
        assert session is not None
        assert session.context_json["_root_conversation_memory"]["current_task"] == "customer_activity"
        assert (
            session.context_json["_root_conversation_memory"]["resolved_customer"]["customer_name"]
            == "河南双汇实业有限公司"
        )
        assert db.query(AgentMessage).filter(AgentMessage.session_id == session_id).count() == 2


async def test_request_id_reuse_with_different_typed_input_is_transport_error(
    application_harness,
) -> None:
    service, _ = application_harness
    orchestrator = _FakeRootOrchestrator(_query_dispatch())
    service.root_orchestrator = orchestrator
    first = await _collect(
        service,
        request_input=TextAgentInput(type="text", text="我在上海有哪些客户"),
        client_request_id=_REQUEST_ID,
    )

    second = await _collect(
        service,
        request_input=TextAgentInput(type="text", text="我在北京有哪些客户"),
        client_request_id=_REQUEST_ID,
        session_id=first[0]["session_id"],
    )

    assert [event["event"] for event in second] == ["session", "transport_error", "done"]
    assert second[1]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert len(orchestrator.calls) == 1


@pytest.mark.asyncio
async def test_closed_stream_still_settles_the_accepted_execution(application_harness) -> None:
    service, session_factory = application_harness
    started = asyncio.Event()
    release = asyncio.Event()

    async def dispatch(turn, *, runtime, on_progress=None):
        del turn, runtime, on_progress
        started.set()
        await release.wait()
        return _query_dispatch()

    service.root_orchestrator.dispatch = dispatch
    request_id = UUID("41a2e0e8-86d4-4d6c-a1b0-6490b2bf12be")
    stream = service.stream_chat_events(
        request_input=TextAgentInput(type="text", text="我在上海有哪些客户"),
        client_request_id=request_id, team_id=1, user_id=2, authorization="Bearer test-token",
    )
    assert (await anext(stream))["event"] == "session"
    await started.wait()
    await stream.aclose()
    release.set()
    await asyncio.wait_for(next(iter(service._workers.values())), timeout=2)
    with session_factory() as db:
        execution = db.query(AgentTurnExecution).filter_by(client_request_id=str(request_id)).one()
        assert execution.status == "COMPLETED"
        assert execution.result_message_id is not None


@pytest.mark.asyncio
async def test_stale_lease_cannot_overwrite_a_newer_execution(application_harness) -> None:
    service, session_factory = application_harness
    request_id = UUID("42a2e0e8-86d4-4d6c-a1b0-6490b2bf12be")
    await _collect(service, request_input=TextAgentInput(type="text", text="我在上海有哪些客户"), client_request_id=request_id)
    with session_factory() as db:
        execution = db.query(AgentTurnExecution).one()
        execution.status = "RUNNING"
        execution.lease_version = 2
        execution.lease_owner = "current-worker"
        execution.lease_expires_at = business_now() - timedelta(seconds=1)
        execution.result_message_id = None
        db.commit()
        execution_id = execution.id
    await service._run_execution(execution_id, "Bearer test-token", "stale-worker")
    with session_factory() as db:
        execution = db.get(AgentTurnExecution, execution_id)
        assert execution.lease_owner == "current-worker"
        assert execution.result_message_id is None


@pytest.mark.asyncio
async def test_recovery_stops_when_original_permission_is_gone(application_harness, monkeypatch) -> None:
    service, session_factory = application_harness
    request_id = UUID("43a2e0e8-86d4-4d6c-a1b0-6490b2bf12be")
    await _collect(service, request_input=TextAgentInput(type="text", text="我在上海有哪些客户"), client_request_id=request_id)
    with session_factory() as db:
        execution = db.query(AgentTurnExecution).one()
        execution.status = "RUNNING"
        execution.permission_codes_json = ["customer:create"]
        execution.lease_expires_at = business_now() - timedelta(seconds=1)
        db.commit()
    with session_factory() as db:
        db.add(User(id=2, email="agent@example.com", name="Agent", status="active"))
        db.commit()
    monkeypatch.setattr(application_module, "user_team_crud", SimpleNamespace(get_by_user_and_team=lambda db, user_id, team_id: object()))
    monkeypatch.setattr(application_module, "permission_crud", SimpleNamespace(get_user_permissions=lambda db, user_id, team_id: []))
    result = await service.recover_expired_executions()
    with session_factory() as db:
        execution = db.query(AgentTurnExecution).one()
        assert result == {"recovered": 0}
        assert execution.status == "FAILED"
        assert execution.last_error_code == "REAUTHORIZATION_FAILED"

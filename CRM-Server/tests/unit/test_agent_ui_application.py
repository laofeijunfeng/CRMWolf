"""Application behavior at the typed Root Orchestrator dispatch seam."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING
from uuid import UUID

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
from app.models.customer import Customer, CustomerMember
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
    WorkflowContinuation,
    WorkflowDispatchResult,
)
from app.services.agent.orchestrator.context import DatabaseRootContextResolver
from app.services.agent.query import CRMQueryAgentResult
from app.services.agent.semantic_plan import AgentSemanticPlan
from app.services.agent.ui.actions import ActionAlreadyConsumedError, AgentUIActionRepository
from app.services.agent.ui.schemas import (
    EntityActionInput,
    InteractionSubmissionInput,
    TextAgentInput,
)
from app.services.agent.workflow import (
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
                        "applied_filters": [
                            {"field": "city", "operator": "eq", "value": "上海"}
                        ],
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
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    @event.listens_for(engine, "connect")
    def _disable_sqlite_driver_transactions(dbapi_connection, connection_record):
        del connection_record
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _begin_sqlite_transaction(connection):
        connection.exec_driver_sql("BEGIN")

    Base.metadata.create_all(
        engine,
        tables=[
            AgentSession.__table__,
            AgentMessage.__table__,
            AgentQueryResultSet.__table__,
            AgentUIAction.__table__,
            Customer.__table__,
            CustomerMember.__table__,
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
    interaction = next(
        block for block in events[1]["message"]["blocks"] if block["type"] == "interaction"
    )
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
    assert runtime.authorization == "Bearer test-token"
    assert runtime.metadata == {"source": "web"}
    with session_factory() as db:
        assert db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).count() == 1


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
                "entity_refs": [
                    ref.model_copy(update={"result_set_id": None})
                    for ref in result.entity_refs
                ],
            }
        )
        for result in dispatch.query_result.query_results
    ]
    service.root_orchestrator = _FakeRootOrchestrator(
        dispatch.model_copy(
            update={
                "query_result": dispatch.query_result.model_copy(
                    update={"query_results": unsigned_results}
                )
            }
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
        assert assistants[0].diagnostics_json == {"dispatch_type": "failure"}


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
            get_user_permissions=lambda db, user_id, team_id: [
                SimpleNamespace(code="customer:follow_up:create")
            ]
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
        result_set = db.query(AgentQueryResultSet).filter_by(
            public_id="rs_query_application_test"
        ).one()
        result_set.expires_at = business_now() - timedelta(seconds=1)
        db.commit()
    monkeypatch.setattr(
        application_module,
        "permission_crud",
        SimpleNamespace(
            get_user_permissions=lambda db, user_id, team_id: [
                SimpleNamespace(code="customer:follow_up:create")
            ]
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
    interaction = next(
        block for block in initial[1]["message"]["blocks"] if block["type"] == "interaction"
    )
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
        "4fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be"
        if choice == "confirm"
        else "5fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be"
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
        turn_messages = (
            db.query(AgentMessage)
            .filter(AgentMessage.client_request_id == str(request_id))
            .all()
        )
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
    error_blocks = [
        block for block in first[1]["message"]["blocks"] if block["type"] == "error"
    ]
    assert len(error_blocks) == 1
    assert error_blocks[0]["code"] == "ACTION_ALREADY_CONSUMED"
    assert not any(block["type"] == "text" for block in first[1]["message"]["blocks"])
    with session_factory() as db:
        turn_messages = (
            db.query(AgentMessage)
            .filter(AgentMessage.client_request_id == str(request_id))
            .all()
        )
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
    service, _ = application_harness
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
            get_user_permissions=lambda db, user_id, team_id: [
                SimpleNamespace(code="customer:follow_up:create")
            ]
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
    error_blocks = [
        block for block in events[1]["message"]["blocks"] if block["type"] == "error"
    ]
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

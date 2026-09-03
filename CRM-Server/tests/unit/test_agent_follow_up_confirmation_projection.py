"""Behavior tests for native follow-up confirmation projection into Agent UI history."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.agent import AgentMessage, AgentMessageRole, AgentSession
from app.models.agent_persistence import AgentUIAction
from app.models.customer_activity_agent_origin import CustomerActivityAgentOrigin
from app.models.sales_commitment import (
    DueAtGranularity,
    FollowUpTask,
    FollowUpTaskConfirmationCase,
    FollowUpTaskConfirmationDeliveryPurpose,
    FollowUpTaskConfirmationPromptDelivery,
    FollowUpTaskConfirmationPromptStatus,
    FollowUpTaskConfirmationStatus,
    FollowUpTaskSourceType,
    FollowUpTaskStatus,
)
from app.services.agent.follow_up_confirmation_projection import (
    FollowUpConfirmationAgentUIProjection,
)
from app.services.agent.orchestrator import (
    ContextPolicy,
    RootDecision,
    RootRuntimeContext,
    RootTurnInput,
    WorkflowContinuation,
    WorkflowDispatchResult,
)
from app.services.agent.workflow import (
    WorkflowCompletedResult,
    WorkflowInteraction,
    WorkflowInteractionOption,
    WorkflowRef,
    WorkflowWaitingResult,
)
from app.services.agent.workflow.progress import (
    awaiting_confirmation_progress,
    execution_progress,
)
from app.services.agent.semantic_plan import AgentSemanticPlan
from app.utils.time import business_now


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    del element, compiler, kw
    return "INTEGER"


class _FakeRootOrchestrator:
    def __init__(self) -> None:
        self.calls: list[tuple[RootTurnInput, RootRuntimeContext]] = []

    async def dispatch(
        self,
        turn: RootTurnInput,
        *,
        runtime: RootRuntimeContext,
    ) -> WorkflowDispatchResult:
        self.calls.append((turn, runtime))
        resource_suffix = turn.input.resource_id[-8:]
        workflow_ref = WorkflowRef(
            workflow_id=f"wf_follow_up_confirmation_{resource_suffix}",
            interrupt_id=f"intr_follow_up_confirmation_{resource_suffix}",
        )
        return WorkflowDispatchResult(
            decision=RootDecision(
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
                reason_code="FOLLOW_UP_TASK_CONFIRMATION_TRIGGER",
                evidence=["服务端触发跟进任务确认工作流"],
                semantic_plan=AgentSemanticPlan(
                    speech_act="CONFIRM_ACTION",
                    business_object="FOLLOW_UP_TASK",
                    operation="TRANSITION",
                    confidence=1.0,
                ),
            ),
            workflow_result=WorkflowWaitingResult(
                workflow_ref=workflow_ref,
                assistant_text="是否将该跟进任务标记为已完成?",
                progress=awaiting_confirmation_progress(),
                interaction=WorkflowInteraction(
                    interaction_id=f"int_follow_up_confirmation_{resource_suffix}",
                    interaction_type="choice",
                    business_action="resolve_follow_up_task_confirmation_case",
                    title="确认跟进任务状态",
                    prompt="是否将该跟进任务标记为已完成?",
                    options=[
                        WorkflowInteractionOption(value="已完成", label="标记完成"),
                        WorkflowInteractionOption(value="先放着", label="保持未完成"),
                        WorkflowInteractionOption(value="不管了", label="不再跟进"),
                    ],
                    selection_mode="single",
                    min_selections=1,
                    max_selections=1,
                    submit_on_select=True,
                    submit_label="提交",
                ),
            ),
            continuation=WorkflowContinuation(
                root_thread_id="crm_agent_turn:test",
                workflow_ref=workflow_ref,
                parent_checkpoint_id=f"parent_cp_follow_up_confirmation_{resource_suffix}",
                subgraph_checkpoint_ns=f"workflow:follow_up_confirmation_{resource_suffix}",
                subgraph_checkpoint_id=f"child_cp_follow_up_confirmation_{resource_suffix}",
            ),
        )


@pytest.fixture
def projection_harness():
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
            AgentUIAction.__table__,
            CustomerActivityAgentOrigin.__table__,
            FollowUpTask.__table__,
            FollowUpTaskConfirmationCase.__table__,
            FollowUpTaskConfirmationPromptDelivery.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine)
    try:
        yield session_factory
    finally:
        engine.dispose()


def _seed_projection_task(db, *, task_id: int, status: str = FollowUpTaskStatus.OPEN, owner_id: str = "2") -> None:
    db.add(
        FollowUpTask(
            id=task_id,
            public_id=f"fut_{task_id:032x}",
            team_id=1,
            customer_id=300 + task_id,
            owner_id=owner_id,
            creator_id=owner_id,
            title="确认跟进任务",
            description="投影测试任务",
            status=status,
            due_at=business_now(),
            due_at_granularity=DueAtGranularity.DATETIME,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_key=f"projection-test:{task_id}",
            source_activity_id=500 + task_id,
            confidence=1.0,
            task_hash=f"projection-task-hash-{task_id}",
        )
    )
    db.flush()


@pytest.mark.asyncio
async def test_pending_case_projects_one_native_workflow_prompt_without_fake_user_turn(
    projection_harness,
) -> None:
    orchestrator = _FakeRootOrchestrator()
    projection = FollowUpConfirmationAgentUIProjection(root_orchestrator=orchestrator)

    with projection_harness() as db:
        session = AgentSession(session_key="agent-session-confirmation", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        _seed_projection_task(db, task_id=101)
        confirmation_case = FollowUpTaskConfirmationCase(
            public_id="fuc_1234567890abcdef1234567890abcdef",
            team_id=1,
            task_id=101,
            customer_id=201,
            owner_id="2",
            creator_id="2",
            status=FollowUpTaskConfirmationStatus.PENDING,
            suggested_action="COMPLETE",
            confirmation_hash="a" * 64,
            question_text="是否将该跟进任务标记为已完成?",
            source_activity_id=501,
            source_activity_revision=1,
            expires_at=business_now() + timedelta(days=1),
        )
        db.add(confirmation_case)
        db.flush()
        db.add(
            CustomerActivityAgentOrigin(
                team_id=1,
                activity_id=501,
                owner_id="2",
                agent_session_id=session.id,
                source_user_message_id=None,
                source_assistant_message_id=9001,
                agent_operation_public_id="aop_follow_up_confirmation_test",
            )
        )
        db.commit()
        session_id = int(session.id)

        projected = await projection.project_pending(
            db,
            team_id=1,
            user_id=2,
            session_id=session_id,
            authorization="Bearer test-token",
            permission_codes=frozenset({"follow_up_task:edit:own"}),
        )

        assert projected == 1
        assert len(orchestrator.calls) == 1
        turn, runtime = orchestrator.calls[0]
        assert turn.input.type == "workflow_trigger"
        assert turn.input.workflow == "follow_up_task_confirmation"
        assert turn.input.resource_id == confirmation_case.public_id
        assert runtime.authorization == "Bearer test-token"
        assert runtime.permission_codes == frozenset({"follow_up_task:edit:own"})
        assert runtime.root_model_config is None
        assert runtime.query_model_config is None

        messages = db.query(AgentMessage).order_by(AgentMessage.id.asc()).all()
        assert [message.role for message in messages] == [AgentMessageRole.ASSISTANT]
        assistant = messages[0]
        assert assistant.client_request_id is None
        assert assistant.ui_json["role"] == "assistant"
        assert [block["type"] for block in assistant.ui_json["blocks"]] == ["interaction"]
        interaction_block = assistant.ui_json["blocks"][0]
        assert interaction_block["interaction_type"] == "choice"
        assert interaction_block["presentation"] == "COMPACT_TASK_COMPLETION"
        assert interaction_block["selection_mode"] == "single"
        assert interaction_block["min_selections"] == 1
        assert interaction_block["max_selections"] == 1
        assert interaction_block["submit_on_select"] is True
        assert [option["value"] for option in interaction_block["options"]] == ["已完成"]

        action = db.query(AgentUIAction).one()
        assert action.message_id == assistant.id
        assert action.action_type == "submit_interaction"
        assert action.target_json["business_action"] == "resolve_follow_up_task_confirmation_case"
        assert action.target_json["result_display"] == "STATE_UPDATE"
        assert [choice["value"] for choice in action.target_json["choices"]] == ["已完成"]

        delivery = db.query(FollowUpTaskConfirmationPromptDelivery).one()
        assert delivery.case_id == confirmation_case.id
        assert delivery.purpose == FollowUpTaskConfirmationDeliveryPurpose.AGENT_TURN_PROMPT
        assert delivery.status == FollowUpTaskConfirmationPromptStatus.SENT
        assert delivery.provider_message_id == f"agent_message:{assistant.id}"
        assert delivery.prompt_key == (f"agent-turn-prompt:{confirmation_case.public_id}:{session_id}")

        replay_count = await projection.project_pending(
            db,
            team_id=1,
            user_id=2,
            session_id=session_id,
            authorization="Bearer test-token",
            permission_codes=frozenset({"follow_up_task:edit:own"}),
        )

        assert replay_count == 0
        assert len(orchestrator.calls) == 1
        assert db.query(AgentMessage).count() == 1
        assert db.query(AgentUIAction).count() == 1
        assert db.query(FollowUpTaskConfirmationPromptDelivery).count() == 1


@pytest.mark.asyncio
async def test_invalid_case_public_id_is_not_dispatched_or_projected(
    projection_harness,
) -> None:
    orchestrator = _FakeRootOrchestrator()
    projection = FollowUpConfirmationAgentUIProjection(root_orchestrator=orchestrator)

    with projection_harness() as db:
        session = AgentSession(session_key="agent-session-invalid-case", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        _seed_projection_task(db, task_id=102)
        confirmation_case = FollowUpTaskConfirmationCase(
            public_id="invalid-case-id",
            team_id=1,
            task_id=102,
            customer_id=202,
            owner_id="2",
            creator_id="2",
            status=FollowUpTaskConfirmationStatus.PENDING,
            suggested_action="COMPLETE",
            confirmation_hash="b" * 64,
            question_text="是否将该跟进任务标记为已完成?",
            source_activity_id=502,
            source_activity_revision=1,
            expires_at=business_now() + timedelta(days=1),
        )
        db.add(confirmation_case)
        db.flush()
        db.add(
            CustomerActivityAgentOrigin(
                team_id=1,
                activity_id=502,
                owner_id="2",
                agent_session_id=session.id,
                source_user_message_id=None,
                source_assistant_message_id=9002,
                agent_operation_public_id="aop_follow_up_confirmation_invalid",
            )
        )
        db.commit()

        projected = await projection.project_pending(
            db,
            team_id=1,
            user_id=2,
            session_id=int(session.id),
            authorization="Bearer test-token",
            permission_codes=frozenset({"follow_up_task:edit:own"}),
        )

        assert projected == 0
        assert orchestrator.calls == []
        assert db.query(AgentMessage).count() == 0
        assert db.query(AgentUIAction).count() == 0
        assert db.query(FollowUpTaskConfirmationPromptDelivery).count() == 0


class _CancellingRootOrchestrator(_FakeRootOrchestrator):
    def __init__(self, case_public_id: str) -> None:
        super().__init__()
        self.case_public_id = case_public_id

    async def dispatch(
        self,
        turn: RootTurnInput,
        *,
        runtime: RootRuntimeContext,
    ) -> WorkflowDispatchResult:
        db = runtime.db
        case = (
            db.query(FollowUpTaskConfirmationCase)
            .filter(FollowUpTaskConfirmationCase.public_id == self.case_public_id)
            .one()
        )
        case.status = FollowUpTaskConfirmationStatus.CANCELLED
        case.cancelled_at = business_now()
        case.cancelled_reason = "SOURCE_ACTIVITY_REVISION_SUPERSEDED"
        db.flush()
        return await super().dispatch(turn, runtime=runtime)


@pytest.mark.asyncio
async def test_case_cancelled_during_root_dispatch_is_not_projected(
    projection_harness,
) -> None:
    case_public_id = "fuc_" + "3" * 32
    orchestrator = _CancellingRootOrchestrator(case_public_id)
    projection = FollowUpConfirmationAgentUIProjection(root_orchestrator=orchestrator)

    with projection_harness() as db:
        session = AgentSession(session_key="agent-session-projection-race", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        confirmation_case = _seed_projection_case(
            db,
            case_number=33,
            session_id=int(session.id),
        )
        confirmation_case.public_id = case_public_id
        db.flush()
        db.commit()

        projected = await projection.project_pending(
            db,
            team_id=1,
            user_id=2,
            session_id=int(session.id),
            authorization="Bearer test-token",
            permission_codes=frozenset({"follow_up_task:edit:own"}),
        )

        assert projected == 0
        assert len(orchestrator.calls) == 1
        assert db.query(AgentMessage).count() == 0
        assert db.query(AgentUIAction).count() == 0
        assert db.query(FollowUpTaskConfirmationPromptDelivery).count() == 0
        db.refresh(confirmation_case)
        assert confirmation_case.status == FollowUpTaskConfirmationStatus.CANCELLED


class _FailingActionRepository:
    def register(self, db, request):
        del db, request
        raise RuntimeError("action persistence failed")


@pytest.mark.asyncio
async def test_action_registration_failure_rolls_back_entire_projection(
    projection_harness,
) -> None:
    orchestrator = _FakeRootOrchestrator()
    projection = FollowUpConfirmationAgentUIProjection(
        root_orchestrator=orchestrator,
        action_repository=_FailingActionRepository(),
    )

    with projection_harness() as db:
        session = AgentSession(session_key="agent-session-action-failure", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        _seed_projection_task(db, task_id=103)
        confirmation_case = FollowUpTaskConfirmationCase(
            public_id="fuc_2234567890abcdef1234567890abcdef",
            team_id=1,
            task_id=103,
            customer_id=203,
            owner_id="2",
            creator_id="2",
            status=FollowUpTaskConfirmationStatus.PENDING,
            suggested_action="COMPLETE",
            confirmation_hash="c" * 64,
            question_text="是否将该跟进任务标记为已完成?",
            source_activity_id=503,
            source_activity_revision=1,
            expires_at=business_now() + timedelta(days=1),
        )
        db.add(confirmation_case)
        db.flush()
        db.add(
            CustomerActivityAgentOrigin(
                team_id=1,
                activity_id=503,
                owner_id="2",
                agent_session_id=session.id,
                source_user_message_id=None,
                source_assistant_message_id=9003,
                agent_operation_public_id="aop_follow_up_confirmation_action_failure",
            )
        )
        db.commit()

        with pytest.raises(RuntimeError, match="action persistence failed"):
            await projection.project_pending(
                db,
                team_id=1,
                user_id=2,
                session_id=int(session.id),
                authorization="Bearer test-token",
                permission_codes=frozenset({"follow_up_task:edit:own"}),
            )

        assert len(orchestrator.calls) == 1
        assert db.query(AgentMessage).count() == 0
        assert db.query(AgentUIAction).count() == 0
        assert db.query(FollowUpTaskConfirmationPromptDelivery).count() == 0


def _seed_projection_case(
    db,
    *,
    case_number: int,
    session_id: int,
    case_team_id: int = 1,
    case_owner_id: str = "2",
    status: str = FollowUpTaskConfirmationStatus.PENDING,
    expires_at=None,
    include_origin: bool = True,
    origin_team_id: int = 1,
    origin_owner_id: str = "2",
    origin_session_id: int | None = None,
) -> FollowUpTaskConfirmationCase:
    activity_id = 600 + case_number
    _seed_projection_task(
        db,
        task_id=200 + case_number,
        status=FollowUpTaskStatus.OPEN,
        owner_id=case_owner_id,
    )
    confirmation_case = FollowUpTaskConfirmationCase(
        public_id=f"fuc_{case_number:032x}",
        team_id=case_team_id,
        task_id=200 + case_number,
        customer_id=300 + case_number,
        owner_id=case_owner_id,
        creator_id=case_owner_id,
        status=status,
        suggested_action="COMPLETE",
        confirmation_hash=f"{case_number:x}".rjust(64, "0"),
        question_text="是否将该跟进任务标记为已完成?",
        source_activity_id=activity_id,
        source_activity_revision=1,
        expires_at=expires_at or business_now() + timedelta(days=1),
    )
    db.add(confirmation_case)
    db.flush()
    if include_origin:
        db.add(
            CustomerActivityAgentOrigin(
                team_id=origin_team_id,
                activity_id=activity_id,
                owner_id=origin_owner_id,
                agent_session_id=origin_session_id or session_id,
                source_user_message_id=None,
                source_assistant_message_id=10_000 + case_number,
                agent_operation_public_id=f"aop_follow_up_confirmation_{case_number}",
            )
        )
    return confirmation_case


@pytest.mark.asyncio
async def test_pending_case_for_closed_task_is_not_projected(projection_harness) -> None:
    orchestrator = _FakeRootOrchestrator()
    projection = FollowUpConfirmationAgentUIProjection(root_orchestrator=orchestrator)

    with projection_harness() as db:
        session = AgentSession(session_key="agent-session-closed-task", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        confirmation_case = _seed_projection_case(
            db,
            case_number=40,
            session_id=int(session.id),
        )
        task = db.query(FollowUpTask).filter(FollowUpTask.id == confirmation_case.task_id).one()
        task.status = FollowUpTaskStatus.COMPLETED
        db.commit()

        projected = await projection.project_pending(
            db,
            team_id=1,
            user_id=2,
            session_id=int(session.id),
            authorization="Bearer test-token",
            permission_codes=frozenset({"follow_up_task:edit:own"}),
        )

        assert projected == 0
        assert orchestrator.calls == []
        assert db.query(AgentMessage).count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_number", "case_overrides", "origin_overrides"),
    [
        (1, {"case_owner_id": "3"}, {}),
        (2, {"case_team_id": 2}, {}),
        (3, {}, {"origin_session": "other"}),
        (4, {}, {"include_origin": False}),
    ],
)
async def test_only_cases_owned_by_current_principal_and_session_are_projected(
    projection_harness,
    case_number: int,
    case_overrides: dict,
    origin_overrides: dict,
) -> None:
    orchestrator = _FakeRootOrchestrator()
    projection = FollowUpConfirmationAgentUIProjection(root_orchestrator=orchestrator)

    with projection_harness() as db:
        session = AgentSession(session_key=f"agent-session-isolation-{case_number}", team_id=1, user_id=2)
        other_session = AgentSession(
            session_key=f"agent-session-other-{case_number}",
            team_id=1,
            user_id=2,
        )
        db.add_all([session, other_session])
        db.flush()
        resolved_origin_overrides = dict(origin_overrides)
        if resolved_origin_overrides.pop("origin_session", None) == "other":
            resolved_origin_overrides["origin_session_id"] = int(other_session.id)
        _seed_projection_case(
            db,
            case_number=case_number,
            session_id=int(session.id),
            **case_overrides,
            **resolved_origin_overrides,
        )
        db.commit()

        projected = await projection.project_pending(
            db,
            team_id=1,
            user_id=2,
            session_id=int(session.id),
            authorization="Bearer test-token",
            permission_codes=frozenset({"follow_up_task:edit:own"}),
        )

        assert projected == 0
        assert orchestrator.calls == []
        assert db.query(AgentMessage).count() == 0
        assert db.query(AgentUIAction).count() == 0
        assert db.query(FollowUpTaskConfirmationPromptDelivery).count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_number", "status", "expires_at"),
    [
        (11, FollowUpTaskConfirmationStatus.RESOLVED, None),
        (12, FollowUpTaskConfirmationStatus.CANCELLED, None),
        (13, FollowUpTaskConfirmationStatus.EXPIRED, None),
        (14, FollowUpTaskConfirmationStatus.PENDING, business_now() - timedelta(seconds=1)),
    ],
)
async def test_terminal_or_expired_cases_are_not_projected(
    projection_harness,
    case_number: int,
    status: str,
    expires_at,
) -> None:
    orchestrator = _FakeRootOrchestrator()
    projection = FollowUpConfirmationAgentUIProjection(root_orchestrator=orchestrator)

    with projection_harness() as db:
        session = AgentSession(session_key=f"agent-session-terminal-{case_number}", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        _seed_projection_case(
            db,
            case_number=case_number,
            session_id=int(session.id),
            status=status,
            expires_at=expires_at,
        )
        db.commit()

        projected = await projection.project_pending(
            db,
            team_id=1,
            user_id=2,
            session_id=int(session.id),
            authorization="Bearer test-token",
            permission_codes=frozenset({"follow_up_task:edit:own"}),
        )

        assert projected == 0
        assert orchestrator.calls == []
        assert db.query(AgentMessage).count() == 0


@pytest.mark.asyncio
async def test_multiple_pending_cases_share_one_assistant_message_with_independent_workflows(
    projection_harness,
) -> None:
    orchestrator = _FakeRootOrchestrator()
    projection = FollowUpConfirmationAgentUIProjection(root_orchestrator=orchestrator)

    with projection_harness() as db:
        session = AgentSession(session_key="agent-session-multiple-cases", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        cases = [
            _seed_projection_case(db, case_number=21, session_id=int(session.id)),
            _seed_projection_case(db, case_number=22, session_id=int(session.id)),
        ]
        db.commit()

        projected = await projection.project_pending(
            db,
            team_id=1,
            user_id=2,
            session_id=int(session.id),
            authorization="Bearer test-token",
            permission_codes=frozenset({"follow_up_task:edit:own"}),
        )

        expected_ids = [case.public_id for case in cases]
        assert projected == 2
        assert [call[0].input.resource_id for call in orchestrator.calls] == expected_ids
        assert [call[1].metadata["case_id"] for call in orchestrator.calls] == expected_ids

        messages = db.query(AgentMessage).all()
        assert len(messages) == 1
        assistant = messages[0]
        interaction_blocks = [
            block for block in assistant.ui_json["blocks"] if block["type"] == "interaction"
        ]
        assert len(interaction_blocks) == 2
        assert len({block["id"] for block in interaction_blocks}) == 2
        assert len({block["interaction_id"] for block in interaction_blocks}) == 2

        actions = db.query(AgentUIAction).order_by(AgentUIAction.id.asc()).all()
        assert len(actions) == 2
        assert {action.message_id for action in actions} == {assistant.id}
        continuations = [action.target_json["workflow_continuation"] for action in actions]
        assert len({item["workflow_ref"]["workflow_id"] for item in continuations}) == 2
        assert len({item["subgraph_checkpoint_ns"] for item in continuations}) == 2

        deliveries = db.query(FollowUpTaskConfirmationPromptDelivery).all()
        assert len(deliveries) == 2
        assert {delivery.provider_message_id for delivery in deliveries} == {
            f"agent_message:{assistant.id}"
        }

        replayed = await projection.project_pending(
            db,
            team_id=1,
            user_id=2,
            session_id=int(session.id),
            authorization="Bearer changed-client-token",
            permission_codes=frozenset(),
        )

        assert replayed == 0
        assert len(orchestrator.calls) == 2


@pytest.mark.asyncio
async def test_new_pending_case_creates_only_one_new_group_without_repeating_delivered_cases(
    projection_harness,
) -> None:
    orchestrator = _FakeRootOrchestrator()
    projection = FollowUpConfirmationAgentUIProjection(root_orchestrator=orchestrator)

    with projection_harness() as db:
        session = AgentSession(session_key="agent-session-incremental-cases", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        first = _seed_projection_case(db, case_number=23, session_id=int(session.id))
        second = _seed_projection_case(db, case_number=24, session_id=int(session.id))
        db.commit()

        assert await projection.project_pending(
            db,
            team_id=1,
            user_id=2,
            session_id=int(session.id),
            authorization="Bearer test-token",
            permission_codes=frozenset({"follow_up_task:edit:own"}),
        ) == 2

        first.status = FollowUpTaskConfirmationStatus.RESOLVED
        third = _seed_projection_case(db, case_number=25, session_id=int(session.id))
        db.commit()

        assert await projection.project_pending(
            db,
            team_id=1,
            user_id=2,
            session_id=int(session.id),
            authorization="Bearer test-token",
            permission_codes=frozenset({"follow_up_task:edit:own"}),
        ) == 1

        assert [call[0].input.resource_id for call in orchestrator.calls] == [
            first.public_id,
            second.public_id,
            third.public_id,
        ]
        assert db.query(AgentMessage).count() == 2
        assert db.query(AgentUIAction).count() == 3
        assert db.query(FollowUpTaskConfirmationPromptDelivery).count() == 3


class _CompletedRootOrchestrator(_FakeRootOrchestrator):
    async def dispatch(
        self,
        turn: RootTurnInput,
        *,
        runtime: RootRuntimeContext,
    ) -> WorkflowDispatchResult:
        waiting = await super().dispatch(turn, runtime=runtime)
        return WorkflowDispatchResult(
            decision=waiting.decision,
            workflow_result=WorkflowCompletedResult(
                workflow_ref=waiting.workflow_result.workflow_ref,
                assistant_text="确认流程已结束",
                progress=execution_progress(
                    confirmation_required=True,
                    has_supplements=False,
                    outcome="COMPLETED",
                ),
            ),
        )


@pytest.mark.asyncio
async def test_terminal_workflow_result_does_not_create_prompt_projection(
    projection_harness,
) -> None:
    orchestrator = _CompletedRootOrchestrator()
    projection = FollowUpConfirmationAgentUIProjection(root_orchestrator=orchestrator)

    with projection_harness() as db:
        session = AgentSession(session_key="agent-session-terminal-result", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        _seed_projection_case(db, case_number=31, session_id=int(session.id))
        db.commit()

        projected = await projection.project_pending(
            db,
            team_id=1,
            user_id=2,
            session_id=int(session.id),
            authorization="Bearer test-token",
            permission_codes=frozenset({"follow_up_task:edit:own"}),
        )

        assert projected == 0
        assert len(orchestrator.calls) == 1
        assert db.query(AgentMessage).count() == 0
        assert db.query(AgentUIAction).count() == 0
        assert db.query(FollowUpTaskConfirmationPromptDelivery).count() == 0


@pytest.mark.asyncio
async def test_delivery_ack_failure_rolls_back_message_action_and_delivery(
    projection_harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = _FakeRootOrchestrator()
    projection = FollowUpConfirmationAgentUIProjection(root_orchestrator=orchestrator)

    def fail_delivery_ack(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("delivery ack failed")

    monkeypatch.setattr(
        "app.services.agent.follow_up_confirmation_projection."
        "follow_up_task_confirmation_prompt_delivery_crud.acknowledge_sent",
        fail_delivery_ack,
    )

    with projection_harness() as db:
        session = AgentSession(session_key="agent-session-delivery-failure", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        _seed_projection_case(db, case_number=32, session_id=int(session.id))
        db.commit()

        with pytest.raises(RuntimeError, match="delivery ack failed"):
            await projection.project_pending(
                db,
                team_id=1,
                user_id=2,
                session_id=int(session.id),
                authorization="Bearer test-token",
                permission_codes=frozenset({"follow_up_task:edit:own"}),
            )

        assert len(orchestrator.calls) == 1
        assert db.query(AgentMessage).count() == 0
        assert db.query(AgentUIAction).count() == 0
        assert db.query(FollowUpTaskConfirmationPromptDelivery).count() == 0


@pytest.mark.asyncio
async def test_pending_confirmations_are_projected_in_protocol_sized_batches(
    projection_harness,
) -> None:
    orchestrator = _FakeRootOrchestrator()
    projection = FollowUpConfirmationAgentUIProjection(root_orchestrator=orchestrator)

    with projection_harness() as db:
        session = AgentSession(session_key="agent-session-batched-confirmations", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        session_id = int(session.id)
        for case_number in range(100, 131):
            _seed_projection_case(
                db,
                case_number=case_number,
                session_id=session_id,
            )
        db.commit()

        first_count = await projection.project_pending(
            db,
            team_id=1,
            user_id=2,
            session_id=session_id,
            authorization="Bearer test-token",
            permission_codes=frozenset({"follow_up_task:edit:own"}),
        )
        second_count = await projection.project_pending(
            db,
            team_id=1,
            user_id=2,
            session_id=session_id,
            authorization="Bearer test-token",
            permission_codes=frozenset({"follow_up_task:edit:own"}),
        )

        assert (first_count, second_count) == (30, 1)
        messages = db.query(AgentMessage).order_by(AgentMessage.id.asc()).all()
        assert [len(message.ui_json["blocks"]) for message in messages] == [30, 1]
        assert len(orchestrator.calls) == 31
        assert db.query(AgentUIAction).count() == 31
        assert db.query(FollowUpTaskConfirmationPromptDelivery).count() == 31

from datetime import datetime

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.crud.sales_commitment import (
    follow_up_task_crud,
    follow_up_task_event_crud,
)
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_vector_document import CustomerVectorDocument
from app.models.sales_commitment import (
    DueAtGranularity,
    FollowUpTask,
    FollowUpTaskConfirmationCase,
    FollowUpTaskConfirmationResolutionAction,
    FollowUpTaskConfirmationStatus,
    FollowUpTaskEvent,
    FollowUpTaskEventType,
    FollowUpTaskProjectionRun,
    FollowUpTaskSourceType,
    FollowUpTaskStatus,
    SalesCommitment,
)
from app.schemas.sales_commitment import FollowUpTaskInternalCreate
from app.services.follow_up_task_confirmation_application_service import (
    FollowUpTaskConfirmationApplicationService,
    FollowUpTaskConfirmationApplicationStatus,
)
from app.services.follow_up_task_confirmation_service import FollowUpTaskConfirmationService
from app.services.follow_up_task_reconciliation_evaluation_service import FollowUpTaskReconciliationDecision
from app.services.follow_up_task_transition_execution_service import FollowUpTaskTransitionExecutionStatus
from app.services.follow_up_task_transition_plan_service import FollowUpTaskTransitionPlanService
from app.services.task_reconciliation_service import TaskReconciliationCandidate, TaskReconciliationCandidateSet


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerActivity.__table__,
            CustomerVectorDocument.__table__,
            SalesCommitment.__table__,
            FollowUpTask.__table__,
            FollowUpTaskEvent.__table__,
            FollowUpTaskProjectionRun.__table__,
            FollowUpTaskConfirmationCase.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    _seed_customer_and_activity(session)
    session.commit()
    yield session
    session.close()
    engine.dispose()


def _seed_customer_and_activity(db_session) -> None:
    db_session.add_all([
        Customer(
            id=1,
            public_id="cus_11111111111111111111111111111111",
            team_id=1,
            account_name="测试客户",
            city="上海",
            owner_id="9",
            creator_id="9",
        ),
        CustomerActivity(
            id=101,
            team_id=1,
            customer_id=1,
            activity_kind="PHONE_FOLLOW_UP",
            source_content="客户说预算还没进展。",
            summary="客户预算还没进展。",
            occurred_at=datetime(2026, 8, 6, 10, 0, 0),
            owner_id="2",
            creator_id="2",
        ),
    ])


def _create_task(db_session, *, task_hash: str = "task-hash") -> FollowUpTask:
    return follow_up_task_crud.create(
        db_session,
        FollowUpTaskInternalCreate(
            team_id=1,
            customer_id=1,
            owner_id="2",
            creator_id="2",
            title="确认客户预算是否通过",
            description="客户说本周确认预算。",
            status=FollowUpTaskStatus.OPEN,
            due_at=datetime(2026, 8, 5, 10, 0, 0),
            due_at_text="本周三",
            due_at_granularity=DueAtGranularity.DATETIME,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_activity_id=101,
            source_public_id="act_11111111111111111111111111111111",
            confidence=0.91,
            evidence_json={"quote": "客户说本周确认预算"},
            task_hash=task_hash,
        ),
    )


def _candidate(task: FollowUpTask) -> TaskReconciliationCandidate:
    return TaskReconciliationCandidate(
        public_id=task.public_id,
        owner_id=task.owner_id,
        title=task.title,
        description=task.description,
        due_at=task.due_at.isoformat(),
        due_at_text=task.due_at_text,
        due_at_granularity=task.due_at_granularity,
        due_at_timezone=task.due_at_timezone,
        source_type=task.source_type,
        source_public_id=task.source_public_id,
        confidence=task.confidence,
        candidate_reasons=("same_customer", "open_task", "due_window", "same_owner"),
        auto_transition_eligible=True,
        confirmation_required_reason=None,
    )


def _confirmation_plan(task: FollowUpTask, *, decision: str = "COMPLETE"):
    return FollowUpTaskTransitionPlanService().plan(
        FollowUpTaskReconciliationDecision(
            decision=decision,
            task_public_id=task.public_id,
            candidate_public_ids=(task.public_id,),
            confidence=0.62,
            evidence_terms=("预算",),
        ),
        TaskReconciliationCandidateSet(
            items=[_candidate(task)],
            total=1,
            filters={"activity_owner_id": task.owner_id},
            usage_policy={
                "state_source": "mysql.crm_follow_up_tasks",
                "mutation": "forbidden",
                "cross_owner": "confirmation_only",
            },
        ),
        source_activity_public_id="act_22222222222222222222222222222222",
        plan_source="unit_test_plan",
    )


def _create_confirmation_case(db_session, task: FollowUpTask, *, decision: str = "COMPLETE"):
    plan = _confirmation_plan(task, decision=decision)
    return FollowUpTaskConfirmationService().create_case_from_plan_action(
        db_session,
        team_id=1,
        task=task,
        plan=plan,
        action=plan.actions[0],
        actor_id="2",
    ).case


def _task_events(db_session, task: FollowUpTask):
    events, total = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task.id)
    assert total == len(events)
    return events


def test_confirmation_reply_completion_is_applied_through_transition_executor(db_session):
    task = _create_task(db_session)
    case = _create_confirmation_case(db_session, task)

    resolved_case, decision, application = FollowUpTaskConfirmationApplicationService().resolve_reply_and_apply(
        db_session,
        team_id=1,
        case_public_id=case.public_id,
        actor_id="2",
        reply_text="已确认完成",
        base_date=datetime(2026, 8, 6, 10, 0, 0),
    )
    db_session.refresh(task)
    db_session.refresh(case)
    events = _task_events(db_session, task)

    assert resolved_case is not None
    assert decision.action == FollowUpTaskConfirmationResolutionAction.COMPLETE
    assert application.status == FollowUpTaskConfirmationApplicationStatus.APPLIED
    assert application.action == FollowUpTaskConfirmationResolutionAction.COMPLETE
    assert application.execution_results[0].status == FollowUpTaskTransitionExecutionStatus.EXECUTED
    assert case.status == FollowUpTaskConfirmationStatus.RESOLVED
    assert case.resolved_action == FollowUpTaskConfirmationResolutionAction.COMPLETE
    assert case.application_status == FollowUpTaskConfirmationApplicationStatus.APPLIED
    assert case.applied_by_id == "2"
    assert case.applied_at is not None
    assert task.status == FollowUpTaskStatus.COMPLETED
    assert task.completed_at is not None
    assert len(events) == 1
    assert events[0].event_type == FollowUpTaskEventType.COMPLETED
    assert events[0].payload_json["plan_source"] == "confirmation_case_reply"


def test_confirmation_reply_delay_keeps_task_open_and_updates_due_at(db_session):
    task = _create_task(db_session)
    case = _create_confirmation_case(db_session, task, decision="DELAY")

    _, decision, application = FollowUpTaskConfirmationApplicationService().resolve_reply_and_apply(
        db_session,
        team_id=1,
        case_public_id=case.public_id,
        actor_id="2",
        reply_text="今天联系了,还没有进展,下周五再说",
        base_date=datetime(2026, 8, 6, 10, 0, 0),
    )
    db_session.refresh(task)
    db_session.refresh(case)
    events = _task_events(db_session, task)

    assert decision.action == FollowUpTaskConfirmationResolutionAction.DELAY
    assert decision.proposed_due_at == datetime(2026, 8, 14, 10, 0, 0)
    assert application.status == FollowUpTaskConfirmationApplicationStatus.APPLIED
    assert task.status == FollowUpTaskStatus.OPEN
    assert task.due_at == datetime(2026, 8, 14, 10, 0, 0)
    assert case.resolved_due_at == datetime(2026, 8, 14, 10, 0, 0)
    assert case.application_status == FollowUpTaskConfirmationApplicationStatus.APPLIED
    assert len(events) == 1
    assert events[0].event_type == FollowUpTaskEventType.UPDATED

    replay = FollowUpTaskConfirmationApplicationService().apply_resolved_case(
        db_session,
        team_id=1,
        case_public_id=case.public_id,
        actor_id="2",
    )
    db_session.refresh(task)
    replayed_events = _task_events(db_session, task)

    assert replay.status == FollowUpTaskConfirmationApplicationStatus.APPLIED
    assert task.due_at == datetime(2026, 8, 14, 10, 0, 0)
    assert len(replayed_events) == 1


def test_confirmation_reply_keep_open_resolves_case_without_task_mutation(db_session):
    task = _create_task(db_session)
    original_due_at = task.due_at
    case = _create_confirmation_case(db_session, task)

    _, decision, application = FollowUpTaskConfirmationApplicationService().resolve_reply_and_apply(
        db_session,
        team_id=1,
        case_public_id=case.public_id,
        actor_id="2",
        reply_text="先放着,还没有进展",
        base_date=datetime(2026, 8, 6, 10, 0, 0),
    )
    db_session.refresh(task)
    db_session.refresh(case)

    assert decision.action == FollowUpTaskConfirmationResolutionAction.KEEP_OPEN
    assert application.status == FollowUpTaskConfirmationApplicationStatus.SKIPPED
    assert application.skip_reason == "KEEP_OPEN_NO_MUTATION"
    assert case.status == FollowUpTaskConfirmationStatus.RESOLVED
    assert case.application_status == FollowUpTaskConfirmationApplicationStatus.SKIPPED
    assert case.application_skip_reason == "KEEP_OPEN_NO_MUTATION"
    assert task.status == FollowUpTaskStatus.OPEN
    assert task.due_at == original_due_at
    assert _task_events(db_session, task) == []


def test_unknown_confirmation_reply_leaves_case_pending_and_task_unchanged(db_session):
    task = _create_task(db_session)
    case = _create_confirmation_case(db_session, task)

    _, decision, application = FollowUpTaskConfirmationApplicationService().resolve_reply_and_apply(
        db_session,
        team_id=1,
        case_public_id=case.public_id,
        actor_id="2",
        reply_text="客户态度一般",
        base_date=datetime(2026, 8, 6, 10, 0, 0),
    )
    db_session.refresh(task)
    db_session.refresh(case)

    assert decision.action == FollowUpTaskConfirmationResolutionAction.UNKNOWN
    assert application.status == FollowUpTaskConfirmationApplicationStatus.SKIPPED
    assert application.skip_reason == "CONFIRMATION_CASE_NOT_RESOLVED"
    assert case.status == FollowUpTaskConfirmationStatus.PENDING
    assert case.resolved_action is None
    assert case.unresolved_reply_count == 1
    assert case.last_unresolved_reply_text == "客户态度一般"
    assert case.last_unresolved_reply_by_id == "2"
    assert case.last_unresolved_reply_at == datetime(2026, 8, 6, 10, 0, 0)
    assert case.application_status is None
    assert task.status == FollowUpTaskStatus.OPEN
    assert _task_events(db_session, task) == []


def test_non_owner_reply_cannot_close_confirmation_case_or_mutate_task(db_session):
    task = _create_task(db_session)
    case = _create_confirmation_case(db_session, task)

    _, decision, application = FollowUpTaskConfirmationApplicationService().resolve_reply_and_apply(
        db_session,
        team_id=1,
        case_public_id=case.public_id,
        actor_id="3",
        reply_text="已确认完成",
        base_date=datetime(2026, 8, 6, 10, 0, 0),
    )
    db_session.refresh(task)
    db_session.refresh(case)

    assert decision.action == FollowUpTaskConfirmationResolutionAction.COMPLETE
    assert application.status == FollowUpTaskConfirmationApplicationStatus.SKIPPED
    assert application.skip_reason == "CONFIRMATION_ACTOR_NOT_OWNER"
    assert case.status == FollowUpTaskConfirmationStatus.PENDING
    assert case.resolved_action is None
    assert case.application_status is None
    assert task.status == FollowUpTaskStatus.OPEN
    assert _task_events(db_session, task) == []


def test_resolved_confirmation_still_respects_executor_open_task_guard(db_session):
    task = _create_task(db_session)
    case = _create_confirmation_case(db_session, task)
    follow_up_task_crud.complete(db_session, task)

    _, decision, application = FollowUpTaskConfirmationApplicationService().resolve_reply_and_apply(
        db_session,
        team_id=1,
        case_public_id=case.public_id,
        actor_id="2",
        reply_text="已确认完成",
        base_date=datetime(2026, 8, 6, 10, 0, 0),
    )
    db_session.refresh(task)
    db_session.refresh(case)

    assert decision.action == FollowUpTaskConfirmationResolutionAction.COMPLETE
    assert application.status == FollowUpTaskConfirmationApplicationStatus.SKIPPED
    assert application.skip_reason == "TASK_NOT_OPEN"
    assert application.execution_results[0].status == FollowUpTaskTransitionExecutionStatus.SKIPPED
    assert case.status == FollowUpTaskConfirmationStatus.RESOLVED
    assert case.application_status == FollowUpTaskConfirmationApplicationStatus.SKIPPED
    assert case.application_skip_reason == "TASK_NOT_OPEN"
    assert task.status == FollowUpTaskStatus.COMPLETED

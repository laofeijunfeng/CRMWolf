from dataclasses import replace
from datetime import datetime

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.crud.sales_commitment import (
    follow_up_task_confirmation_case_crud,
    follow_up_task_crud,
    follow_up_task_event_crud,
)
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_vector_document import (
    CustomerVectorDocument,
    CustomerVectorDocumentSourceType,
    CustomerVectorDocumentSyncStatus,
)
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
from app.schemas.sales_commitment import FollowUpTaskConfirmationCaseInternalCreate, FollowUpTaskInternalCreate
from app.services.follow_up_task_confirmation_cleanup_service import FollowUpTaskConfirmationCancelReason
from app.services.follow_up_task_reconciliation_evaluation_service import FollowUpTaskReconciliationDecision
from app.services.follow_up_task_transition_execution_service import (
    FollowUpTaskTransitionExecutionService,
    FollowUpTaskTransitionExecutionStatus,
)
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
    db_session.add_all(
        [
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
                source_content="客户说预算已经通过。",
                summary="客户预算已通过。",
                occurred_at=datetime(2026, 8, 6, 10, 0, 0),
                owner_id="2",
                creator_id="2",
            ),
        ]
    )


def _create_task(db_session, *, owner_id: str = "2", task_hash: str = "task-hash") -> FollowUpTask:
    return follow_up_task_crud.create(
        db_session,
        FollowUpTaskInternalCreate(
            team_id=1,
            customer_id=1,
            owner_id=owner_id,
            creator_id=owner_id,
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


def _create_confirmation_case(db_session, task: FollowUpTask, *, confirmation_hash: str) -> FollowUpTaskConfirmationCase:
    return follow_up_task_confirmation_case_crud.create(
        db_session,
        FollowUpTaskConfirmationCaseInternalCreate(
            team_id=task.team_id,
            task_id=task.id,
            customer_id=task.customer_id,
            owner_id=task.owner_id,
            creator_id=task.owner_id,
            status=FollowUpTaskConfirmationStatus.PENDING,
            suggested_action=FollowUpTaskConfirmationResolutionAction.COMPLETE,
            confirmation_hash=confirmation_hash,
            question_text="上次安排的任务是否已经完成?",
            source_activity_id=task.source_activity_id,
            source_public_id=task.source_public_id,
            source_plan_json={"plan_source": "unit_test"},
        ),
    )


def _candidate(task: FollowUpTask, *, auto_transition_eligible: bool = True) -> TaskReconciliationCandidate:
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
        auto_transition_eligible=auto_transition_eligible,
        confirmation_required_reason=None if auto_transition_eligible else "CROSS_OWNER",
    )


def _candidate_set(task: FollowUpTask) -> TaskReconciliationCandidateSet:
    return TaskReconciliationCandidateSet(
        items=[_candidate(task)],
        total=1,
        filters={"activity_owner_id": task.owner_id},
        usage_policy={
            "state_source": "mysql.crm_follow_up_tasks",
            "mutation": "forbidden",
            "cross_owner": "confirmation_only",
        },
    )


def _plan(task: FollowUpTask, *, decision: str = "COMPLETE", proposed_due_at: str | None = None):
    return FollowUpTaskTransitionPlanService().plan(
        FollowUpTaskReconciliationDecision(
            decision=decision,
            task_public_id=task.public_id,
            candidate_public_ids=(task.public_id,),
            confidence=0.94,
            proposed_due_at=proposed_due_at,
            evidence_terms=("预算已经通过", "确认客户预算"),
        ),
        _candidate_set(task),
        source_activity_public_id="act_22222222222222222222222222222222",
        plan_source="unit_test_plan",
    )


def test_transition_executor_is_disabled_by_default_and_does_not_mutate(db_session):
    task = _create_task(db_session)
    plan = _plan(task)

    results = FollowUpTaskTransitionExecutionService().execute_plan(
        db_session,
        team_id=1,
        plan=plan,
        actor_id="2",
    )
    db_session.refresh(task)
    events, total = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task.id)

    assert results[0].status == FollowUpTaskTransitionExecutionStatus.DISABLED
    assert results[0].skip_reason == "EXECUTOR_DISABLED"
    assert task.status == FollowUpTaskStatus.OPEN
    assert task.completed_at is None
    assert events == []
    assert total == 0


def test_transition_executor_completes_open_same_owner_task_and_records_event(db_session):
    task = _create_task(db_session)
    plan = _plan(task)

    results = FollowUpTaskTransitionExecutionService().execute_plan(
        db_session,
        team_id=1,
        plan=plan,
        actor_id="2",
        enabled=True,
    )
    db_session.refresh(task)
    events, total = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task.id)

    assert results[0].status == FollowUpTaskTransitionExecutionStatus.EXECUTED
    assert task.status == FollowUpTaskStatus.COMPLETED
    assert task.completed_at is not None
    assert total == 1
    assert events[0].event_type == FollowUpTaskEventType.COMPLETED
    assert events[0].previous_status == FollowUpTaskStatus.OPEN
    assert events[0].new_status == FollowUpTaskStatus.COMPLETED
    assert events[0].payload_json["task_public_id"] == task.public_id
    assert events[0].payload_json["source_activity_public_id"] == "act_22222222222222222222222222222222"
    assert "owner_id" not in str(events[0].payload_json)
    document = (
        db_session.query(CustomerVectorDocument)
        .filter(
            CustomerVectorDocument.source_type == CustomerVectorDocumentSourceType.FOLLOW_UP_TASK,
            CustomerVectorDocument.source_object_id == task.public_id,
        )
        .one()
    )
    assert document.metadata_json["status"] == FollowUpTaskStatus.COMPLETED
    assert document.metadata_json["completed_at"] == task.completed_at.isoformat()
    assert document.sync_status == CustomerVectorDocumentSyncStatus.PENDING


@pytest.mark.parametrize(
    ("decision", "expected_task_status", "expected_reason"),
    [
        ("COMPLETE", FollowUpTaskStatus.COMPLETED, FollowUpTaskConfirmationCancelReason.TASK_COMPLETED),
        ("CANCEL", FollowUpTaskStatus.CANCELLED, FollowUpTaskConfirmationCancelReason.TASK_CANCELLED),
    ],
)
def test_transition_executor_cancels_pending_confirmation_cases_when_task_is_closed(
    db_session,
    decision,
    expected_task_status,
    expected_reason,
):
    task = _create_task(db_session, task_hash=f"cleanup-on-{decision.lower()}")
    case = _create_confirmation_case(db_session, task, confirmation_hash=f"cleanup-on-{decision.lower()}-case")
    plan = _plan(task, decision=decision)

    results = FollowUpTaskTransitionExecutionService().execute_plan(
        db_session,
        team_id=1,
        plan=plan,
        actor_id="2",
        enabled=True,
    )
    db_session.refresh(task)
    db_session.refresh(case)

    assert results[0].status == FollowUpTaskTransitionExecutionStatus.EXECUTED
    assert task.status == expected_task_status
    assert case.status == FollowUpTaskConfirmationStatus.CANCELLED
    assert case.cancelled_by_id == "2"
    assert case.cancelled_reason == expected_reason


def test_transition_executor_delay_keeps_pending_confirmation_cases(db_session):
    task = _create_task(db_session, task_hash="cleanup-on-delay")
    case = _create_confirmation_case(db_session, task, confirmation_hash="cleanup-on-delay-case")
    plan = _plan(task, decision="DELAY", proposed_due_at="2026-08-14T10:00:00")

    results = FollowUpTaskTransitionExecutionService().execute_plan(
        db_session,
        team_id=1,
        plan=plan,
        actor_id="2",
        enabled=True,
    )
    db_session.refresh(case)

    assert results[0].status == FollowUpTaskTransitionExecutionStatus.EXECUTED
    assert case.status == FollowUpTaskConfirmationStatus.PENDING


def test_transition_executor_blocks_owner_mismatch(db_session):
    task = _create_task(db_session, owner_id="2")
    plan = _plan(task)

    results = FollowUpTaskTransitionExecutionService().execute_plan(
        db_session,
        team_id=1,
        plan=plan,
        actor_id="3",
        enabled=True,
    )
    db_session.refresh(task)
    events, total = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task.id)

    assert results[0].status == FollowUpTaskTransitionExecutionStatus.SKIPPED
    assert results[0].skip_reason == "TASK_OWNER_MISMATCH"
    assert task.status == FollowUpTaskStatus.OPEN
    assert events == []
    assert total == 0


def test_transition_executor_blocks_plan_with_safety_failures_even_if_action_is_executable(db_session):
    task = _create_task(db_session)
    plan = replace(_plan(task), safety_failures=("LOW_CONFIDENCE",))

    results = FollowUpTaskTransitionExecutionService().execute_plan(
        db_session,
        team_id=1,
        plan=plan,
        actor_id="2",
        enabled=True,
    )
    db_session.refresh(task)
    events, total = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task.id)

    assert results[0].status == FollowUpTaskTransitionExecutionStatus.SKIPPED
    assert results[0].skip_reason == "PLAN_SAFETY_FAILURES"
    assert task.status == FollowUpTaskStatus.OPEN
    assert events == []
    assert total == 0


def test_transition_executor_delays_task_without_closing_it(db_session):
    task = _create_task(db_session)
    plan = _plan(task, decision="DELAY", proposed_due_at="2026-08-14T10:00:00")

    results = FollowUpTaskTransitionExecutionService().execute_plan(
        db_session,
        team_id=1,
        plan=plan,
        actor_id="2",
        enabled=True,
    )
    db_session.refresh(task)
    events, total = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task.id)

    assert results[0].status == FollowUpTaskTransitionExecutionStatus.EXECUTED
    assert task.status == FollowUpTaskStatus.OPEN
    assert task.due_at == datetime(2026, 8, 14, 10, 0, 0)
    assert task.due_at_text == "2026-08-14T10:00:00"
    assert total == 1
    assert events[0].event_type == FollowUpTaskEventType.UPDATED
    assert events[0].previous_status == FollowUpTaskStatus.OPEN
    assert events[0].new_status == FollowUpTaskStatus.OPEN
    document = (
        db_session.query(CustomerVectorDocument)
        .filter(
            CustomerVectorDocument.source_type == CustomerVectorDocumentSourceType.FOLLOW_UP_TASK,
            CustomerVectorDocument.source_object_id == task.public_id,
        )
        .one()
    )
    assert document.metadata_json["status"] == FollowUpTaskStatus.OPEN
    assert document.metadata_json["due_at"] == "2026-08-14T10:00:00"
    assert document.metadata_json["due_at_text"] == "2026-08-14T10:00:00"


def test_transition_executor_event_has_public_id_and_rollback_snapshot_for_completion(db_session):
    task = _create_task(db_session)
    plan = _plan(task)

    FollowUpTaskTransitionExecutionService().execute_plan(
        db_session,
        team_id=1,
        plan=plan,
        actor_id="2",
        enabled=True,
    )
    events, _ = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task.id)

    assert events[0].public_id.startswith("fte_")
    rollback = events[0].payload_json["rollback"]
    assert rollback == {
        "type": "REOPEN",
        "previous_status": FollowUpTaskStatus.OPEN,
        "previous_due_at": "2026-08-05T10:00:00",
        "previous_due_at_text": "本周三",
        "previous_due_at_granularity": DueAtGranularity.DATETIME,
        "previous_due_at_timezone": "Asia/Shanghai",
    }


def test_transition_executor_rolls_back_automatic_completion_by_event_public_id(db_session):
    task = _create_task(db_session)
    plan = _plan(task)
    service = FollowUpTaskTransitionExecutionService()
    service.execute_plan(db_session, team_id=1, plan=plan, actor_id="2", enabled=True)
    events, _ = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task.id)

    result = service.rollback_event(
        db_session,
        team_id=1,
        event_public_id=events[0].public_id,
        actor_id="2",
    )
    db_session.refresh(task)
    rollback_events, total = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task.id)

    assert result.status == FollowUpTaskTransitionExecutionStatus.EXECUTED
    assert result.action == "ROLLBACK"
    assert task.status == FollowUpTaskStatus.OPEN
    assert task.completed_at is None
    assert total == 2
    assert rollback_events[-1].event_type == FollowUpTaskEventType.REOPENED
    assert rollback_events[-1].payload_json["rolled_back_event_public_id"] == events[0].public_id
    document = (
        db_session.query(CustomerVectorDocument)
        .filter(
            CustomerVectorDocument.source_type == CustomerVectorDocumentSourceType.FOLLOW_UP_TASK,
            CustomerVectorDocument.source_object_id == task.public_id,
        )
        .one()
    )
    assert document.metadata_json["status"] == FollowUpTaskStatus.OPEN
    assert "completed_at" not in document.metadata_json


def test_transition_executor_rolls_back_automatic_cancellation_by_event_public_id(db_session):
    task = _create_task(db_session)
    plan = _plan(task, decision="CANCEL")
    service = FollowUpTaskTransitionExecutionService()
    service.execute_plan(db_session, team_id=1, plan=plan, actor_id="2", enabled=True)
    events, _ = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task.id)

    result = service.rollback_event(
        db_session,
        team_id=1,
        event_public_id=events[0].public_id,
        actor_id="2",
    )
    db_session.refresh(task)

    assert result.status == FollowUpTaskTransitionExecutionStatus.EXECUTED
    assert task.status == FollowUpTaskStatus.OPEN
    assert task.cancelled_at is None


def test_transition_executor_rolls_back_automatic_delay_to_previous_due_at(db_session):
    task = _create_task(db_session)
    plan = _plan(task, decision="DELAY", proposed_due_at="2026-08-14T10:00:00")
    service = FollowUpTaskTransitionExecutionService()
    service.execute_plan(db_session, team_id=1, plan=plan, actor_id="2", enabled=True)
    events, _ = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task.id)

    result = service.rollback_event(
        db_session,
        team_id=1,
        event_public_id=events[0].public_id,
        actor_id="2",
    )
    db_session.refresh(task)
    rollback_events, total = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task.id)

    assert result.status == FollowUpTaskTransitionExecutionStatus.EXECUTED
    assert task.status == FollowUpTaskStatus.OPEN
    assert task.due_at == datetime(2026, 8, 5, 10, 0, 0)
    assert task.due_at_text == "本周三"
    assert total == 2
    assert rollback_events[-1].event_type == FollowUpTaskEventType.UPDATED
    assert rollback_events[-1].payload_json["reason"] == "RECONCILIATION_TRANSITION_ROLLBACK"


def test_transition_executor_rollback_is_idempotent(db_session):
    task = _create_task(db_session)
    plan = _plan(task)
    service = FollowUpTaskTransitionExecutionService()
    service.execute_plan(db_session, team_id=1, plan=plan, actor_id="2", enabled=True)
    events, _ = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task.id)

    first = service.rollback_event(db_session, team_id=1, event_public_id=events[0].public_id, actor_id="2")
    second = service.rollback_event(db_session, team_id=1, event_public_id=events[0].public_id, actor_id="2")
    _, total = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task.id)

    assert first.status == FollowUpTaskTransitionExecutionStatus.EXECUTED
    assert second.status == FollowUpTaskTransitionExecutionStatus.SKIPPED
    assert second.skip_reason == "EVENT_ALREADY_ROLLED_BACK"
    assert total == 2


def test_transition_executor_does_not_rollback_manual_confirmation_event(db_session):
    task = _create_task(db_session)
    plan = replace(_plan(task), plan_source="confirmation_case_reply")
    service = FollowUpTaskTransitionExecutionService()
    service.execute_plan(db_session, team_id=1, plan=plan, actor_id="2", enabled=True)
    events, _ = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task.id)

    result = service.rollback_event(
        db_session,
        team_id=1,
        event_public_id=events[0].public_id,
        actor_id="2",
    )
    db_session.refresh(task)
    _, total = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task.id)

    assert events[0].payload_json["execution_kind"] == "manual_confirmation"
    assert result.status == FollowUpTaskTransitionExecutionStatus.SKIPPED
    assert result.skip_reason == "EVENT_NOT_AUTOMATIC_TRANSITION"
    assert task.status == FollowUpTaskStatus.COMPLETED
    assert total == 1

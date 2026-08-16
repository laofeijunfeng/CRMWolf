from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.crud.sales_commitment import (
    follow_up_task_confirmation_case_crud,
    follow_up_task_crud,
)
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.sales_commitment import (
    DueAtGranularity,
    FollowUpTask,
    FollowUpTaskConfirmationCase,
    FollowUpTaskConfirmationResolutionAction,
    FollowUpTaskConfirmationStatus,
    FollowUpTaskEvent,
    FollowUpTaskProjectionRun,
    FollowUpTaskSourceType,
    FollowUpTaskStatus,
    SalesCommitment,
)
from app.schemas.sales_commitment import (
    FollowUpTaskConfirmationCaseInternalCreate,
    FollowUpTaskConfirmationCaseResponse,
    FollowUpTaskInternalCreate,
)
from app.services.follow_up_task_confirmation_cleanup_service import (
    FollowUpTaskConfirmationCancelReason,
    FollowUpTaskConfirmationCleanupService,
)
from app.services.follow_up_task_confirmation_service import FollowUpTaskConfirmationService
from app.services.follow_up_task_reconciliation_evaluation_service import FollowUpTaskReconciliationDecision
from app.services.follow_up_task_transition_plan_service import FollowUpTaskTransitionPlanService
from app.services.task_reconciliation_service import TaskReconciliationCandidate, TaskReconciliationCandidateSet
from app.utils.public_id import is_follow_up_task_confirmation_case_public_id


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


def _confirmation_plan(
    task: FollowUpTask,
    *,
    decision: str = "COMPLETE",
    confidence: float = 0.62,
    source_activity_public_id: str = "act_22222222222222222222222222222222",
):
    return FollowUpTaskTransitionPlanService().plan(
        FollowUpTaskReconciliationDecision(
            decision=decision,
            task_public_id=task.public_id,
            candidate_public_ids=(task.public_id,),
            confidence=confidence,
            evidence_terms=("预算",),
            needs_confirmation=decision == "ASK_CONFIRMATION",
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
        source_activity_public_id=source_activity_public_id,
        plan_source="unit_test_plan",
    )


def _create_confirmation_case(db_session, task: FollowUpTask) -> FollowUpTaskConfirmationCase:
    plan = _confirmation_plan(task)
    return FollowUpTaskConfirmationService().create_case_from_plan_action(
        db_session,
        team_id=1,
        task=task,
        plan=plan,
        action=plan.actions[0],
        actor_id="2",
    ).case


def _create_confirmation_case_with_status(
    db_session,
    task: FollowUpTask,
    *,
    confirmation_hash: str,
    status: str,
) -> FollowUpTaskConfirmationCase:
    return follow_up_task_confirmation_case_crud.create(
        db_session,
        FollowUpTaskConfirmationCaseInternalCreate(
            team_id=task.team_id,
            task_id=task.id,
            customer_id=task.customer_id,
            owner_id=task.owner_id,
            creator_id=task.owner_id,
            status=status,
            suggested_action=FollowUpTaskConfirmationResolutionAction.COMPLETE,
            confirmation_hash=confirmation_hash,
            question_text="上次安排的任务是否已经完成?",
            source_activity_id=task.source_activity_id,
            source_public_id=task.source_public_id,
            source_plan_json={"plan_source": "unit_test"},
        ),
    )


def test_confirmation_case_created_from_blocked_transition_plan_is_idempotent(db_session):
    task = _create_task(db_session)
    plan = _confirmation_plan(task)
    action = plan.actions[0]
    service = FollowUpTaskConfirmationService()

    first = service.create_case_from_plan_action(
        db_session,
        team_id=1,
        task=task,
        plan=plan,
        action=action,
        actor_id="2",
    )
    second = service.create_case_from_plan_action(
        db_session,
        team_id=1,
        task=task,
        plan=plan,
        action=action,
        actor_id="2",
    )

    assert first.created is True
    assert second.created is False
    assert second.case.id == first.case.id
    assert is_follow_up_task_confirmation_case_public_id(first.case.public_id)
    assert first.case.status == FollowUpTaskConfirmationStatus.PENDING
    assert first.case.suggested_action == FollowUpTaskConfirmationResolutionAction.COMPLETE
    assert first.case.question_text == "上次安排的「确认客户预算是否通过」这次是否已经完成?"
    response = FollowUpTaskConfirmationCaseResponse.from_model(
        first.case,
        task_public_id=task.public_id,
        customer_public_id="cus_11111111111111111111111111111111",
    )
    assert response.id == first.case.public_id
    assert response.task_id == task.public_id
    assert response.expires_at == first.case.expires_at
    assert "source_plan_json" not in response.model_dump()


def test_confirmation_case_does_not_inherit_task_source_activity_without_trigger_revision(db_session):
    task = _create_task(db_session)
    plan = _confirmation_plan(task)

    case = FollowUpTaskConfirmationService().create_case_from_plan_action(
        db_session,
        team_id=1,
        task=task,
        plan=plan,
        action=plan.actions[0],
        actor_id="2",
    ).case

    assert case.source_activity_id is None
    assert case.source_activity_revision is None
    assert case.source_plan_json["confirmation_source"]["source_activity_id"] is None
    assert case.source_plan_json["confirmation_source"]["source_activity_revision"] is None
    assert case.source_plan_json["confirmation_source"]["task_source_activity_id"] == task.source_activity_id


def test_confirmation_case_reuses_source_activity_task_thread_and_upgrades_suggestion(db_session):
    task = _create_task(db_session)
    service = FollowUpTaskConfirmationService()
    unknown_plan = _confirmation_plan(task, decision="ASK_CONFIRMATION", confidence=0.58)
    complete_plan = _confirmation_plan(task, decision="COMPLETE", confidence=0.94)

    first = service.create_case_from_plan_action(
        db_session,
        team_id=1,
        task=task,
        plan=unknown_plan,
        action=unknown_plan.actions[0],
        actor_id="2",
        source_activity_id=202,
        source_public_id="act_22222222222222222222222222222222",
    )
    second = service.create_case_from_plan_action(
        db_session,
        team_id=1,
        task=task,
        plan=complete_plan,
        action=replace(
            complete_plan.actions[0],
            action="ASK_CONFIRMATION",
            executable=False,
            requires_confirmation=True,
            reason="AUTO_TRANSITION_BLOCKED_BY_POLICY",
        ),
        actor_id="2",
        source_activity_id=202,
        source_public_id="act_22222222222222222222222222222222",
    )

    cases, total = follow_up_task_confirmation_case_crud.list_pending_by_source_activity(
        db_session,
        team_id=1,
        source_activity_id=202,
    )
    db_session.refresh(first.case)

    assert first.created is True
    assert second.created is False
    assert second.case.id == first.case.id
    assert total == 1
    assert cases[0].id == first.case.id
    assert first.case.suggested_action == FollowUpTaskConfirmationResolutionAction.COMPLETE
    assert first.case.confirmation_hash == second.confirmation_hash
    assert first.case.question_text == "上次安排的「确认客户预算是否通过」这次是否已经完成?"


def test_confirmation_case_prompt_count_is_tracked(db_session):
    task = _create_task(db_session)
    plan = _confirmation_plan(task)
    case = FollowUpTaskConfirmationService().create_case_from_plan_action(
        db_session,
        team_id=1,
        task=task,
        plan=plan,
        action=plan.actions[0],
        actor_id="2",
    ).case

    prompted = FollowUpTaskConfirmationService().mark_prompted(
        db_session,
        case=case,
        prompted_at=datetime(2026, 8, 6, 11, 0, 0),
    )

    assert prompted.prompt_count == 1
    assert prompted.last_prompted_at == datetime(2026, 8, 6, 11, 0, 0)


def test_confirmation_case_defaults_to_expiring_reply_window(db_session):
    task = _create_task(db_session)
    plan = _confirmation_plan(task)

    case = FollowUpTaskConfirmationService().create_case_from_plan_action(
        db_session,
        team_id=1,
        task=task,
        plan=plan,
        action=plan.actions[0],
        actor_id="2",
    ).case

    assert case.expires_at is not None
    assert case.expires_at > case.created_time


def test_pending_confirmation_listing_excludes_expired_cases(db_session):
    expired_task = _create_task(db_session, task_hash="expired-task")
    active_task = _create_task(db_session, task_hash="active-task")
    expired_case = _create_confirmation_case(db_session, expired_task)
    active_case = _create_confirmation_case(db_session, active_task)
    now = datetime(2026, 8, 6, 10, 0, 0)
    expired_case.expires_at = now - timedelta(seconds=1)
    active_case.expires_at = now + timedelta(days=1)
    db_session.commit()

    rows, total = follow_up_task_confirmation_case_crud.list_pending_for_owner(
        db_session,
        team_id=1,
        owner_id="2",
        now=now,
    )

    assert total == 1
    assert [case.public_id for case in rows] == [active_case.public_id]


def test_cleanup_service_expires_only_pending_cases_past_reply_window(db_session):
    expired_task = _create_task(db_session, task_hash="cleanup-expired-task")
    future_task = _create_task(db_session, task_hash="cleanup-future-task")
    resolved_task = _create_task(db_session, task_hash="cleanup-resolved-task")
    expired_case = _create_confirmation_case(db_session, expired_task)
    future_case = _create_confirmation_case(db_session, future_task)
    resolved_case = _create_confirmation_case(db_session, resolved_task)
    now = datetime(2026, 8, 6, 10, 0, 0)
    expired_case.expires_at = now - timedelta(seconds=1)
    future_case.expires_at = now + timedelta(days=1)
    resolved_case.expires_at = now - timedelta(seconds=1)
    resolved_case.status = FollowUpTaskConfirmationStatus.RESOLVED
    db_session.commit()

    result = FollowUpTaskConfirmationCleanupService().expire_pending_cases(
        db_session,
        team_id=1,
        before=now,
    )
    db_session.refresh(expired_case)
    db_session.refresh(future_case)
    db_session.refresh(resolved_case)

    assert result.expired_count == 1
    assert result.expired_case_public_ids == (expired_case.public_id,)
    assert expired_case.status == FollowUpTaskConfirmationStatus.EXPIRED
    assert expired_case.expired_at == now
    assert future_case.status == FollowUpTaskConfirmationStatus.PENDING
    assert resolved_case.status == FollowUpTaskConfirmationStatus.RESOLVED


def test_cleanup_service_cancels_only_pending_cases_for_selected_task(db_session):
    target_task = _create_task(db_session, task_hash="cleanup-cancel-target")
    other_task = _create_task(db_session, task_hash="cleanup-cancel-other")
    pending_case = _create_confirmation_case(db_session, target_task)
    resolved_case = _create_confirmation_case_with_status(
        db_session,
        target_task,
        confirmation_hash="cleanup-cancel-resolved",
        status=FollowUpTaskConfirmationStatus.RESOLVED,
    )
    expired_case = _create_confirmation_case_with_status(
        db_session,
        target_task,
        confirmation_hash="cleanup-cancel-expired",
        status=FollowUpTaskConfirmationStatus.EXPIRED,
    )
    already_cancelled_case = _create_confirmation_case_with_status(
        db_session,
        target_task,
        confirmation_hash="cleanup-cancel-already-cancelled",
        status=FollowUpTaskConfirmationStatus.CANCELLED,
    )
    other_pending_case = _create_confirmation_case(db_session, other_task)
    now = datetime(2026, 8, 6, 12, 0, 0)

    result = FollowUpTaskConfirmationCleanupService().cancel_pending_cases_for_task(
        db_session,
        team_id=1,
        task_id=target_task.id,
        actor_id="2",
        reason=FollowUpTaskConfirmationCancelReason.TASK_COMPLETED,
        cancelled_at=now,
    )
    for case in [pending_case, resolved_case, expired_case, already_cancelled_case, other_pending_case]:
        db_session.refresh(case)

    assert result.cancelled_count == 1
    assert result.cancelled_case_public_ids == (pending_case.public_id,)
    assert pending_case.status == FollowUpTaskConfirmationStatus.CANCELLED
    assert pending_case.cancelled_at == now
    assert pending_case.cancelled_by_id == "2"
    assert pending_case.cancelled_reason == FollowUpTaskConfirmationCancelReason.TASK_COMPLETED
    assert resolved_case.status == FollowUpTaskConfirmationStatus.RESOLVED
    assert expired_case.status == FollowUpTaskConfirmationStatus.EXPIRED
    assert already_cancelled_case.status == FollowUpTaskConfirmationStatus.CANCELLED
    assert other_pending_case.status == FollowUpTaskConfirmationStatus.PENDING


def test_confirmation_reply_interpretation_handles_common_sales_replies():
    service = FollowUpTaskConfirmationService()
    base_date = datetime(2026, 8, 6, 10, 0, 0)

    complete = service.interpret_reply("已确认,预算通过了", base_date=base_date)
    cancel = service.interpret_reply("这个不管了", base_date=base_date)
    keep_open = service.interpret_reply("先放着,还没有进展", base_date=base_date)
    delay = service.interpret_reply("今天联系了,还没有进展,下周五再说", base_date=base_date)
    unknown = service.interpret_reply("客户态度一般", base_date=base_date)

    assert complete.action == FollowUpTaskConfirmationResolutionAction.COMPLETE
    assert cancel.action == FollowUpTaskConfirmationResolutionAction.CANCEL
    assert keep_open.action == FollowUpTaskConfirmationResolutionAction.KEEP_OPEN
    assert delay.action == FollowUpTaskConfirmationResolutionAction.DELAY
    assert delay.proposed_due_at == datetime(2026, 8, 14, 10, 0, 0)
    assert unknown.action == FollowUpTaskConfirmationResolutionAction.UNKNOWN


def test_resolving_confirmation_case_from_reply_does_not_mutate_task_status(db_session):
    task = _create_task(db_session)
    plan = _confirmation_plan(task)
    service = FollowUpTaskConfirmationService()
    case = service.create_case_from_plan_action(
        db_session,
        team_id=1,
        task=task,
        plan=plan,
        action=plan.actions[0],
        actor_id="2",
    ).case

    resolved_case, decision = service.resolve_case_from_reply(
        db_session,
        team_id=1,
        case_public_id=case.public_id,
        actor_id="2",
        reply_text="已确认完成",
        base_date=datetime(2026, 8, 6, 10, 0, 0),
    )
    db_session.refresh(task)

    assert decision.action == FollowUpTaskConfirmationResolutionAction.COMPLETE
    assert resolved_case is not None
    assert resolved_case.status == FollowUpTaskConfirmationStatus.RESOLVED
    assert resolved_case.resolved_action == FollowUpTaskConfirmationResolutionAction.COMPLETE
    assert resolved_case.resolution_text == "已确认完成"
    assert task.status == FollowUpTaskStatus.OPEN
    pending, total = follow_up_task_confirmation_case_crud.list_pending_for_owner(
        db_session,
        team_id=1,
        owner_id="2",
    )
    assert pending == []
    assert total == 0


def test_resolving_expired_confirmation_case_marks_expired_without_mutating_task(db_session):
    task = _create_task(db_session)
    plan = _confirmation_plan(task)
    service = FollowUpTaskConfirmationService()
    case = service.create_case_from_plan_action(
        db_session,
        team_id=1,
        task=task,
        plan=plan,
        action=plan.actions[0],
        actor_id="2",
    ).case
    now = datetime(2026, 8, 6, 10, 0, 0)
    case.expires_at = now - timedelta(seconds=1)
    db_session.commit()

    resolved_case, decision = service.resolve_case_from_reply(
        db_session,
        team_id=1,
        case_public_id=case.public_id,
        actor_id="2",
        reply_text="已确认完成",
        base_date=now,
    )
    db_session.refresh(task)
    db_session.refresh(case)

    assert decision.action == FollowUpTaskConfirmationResolutionAction.COMPLETE
    assert resolved_case is not None
    assert resolved_case.status == FollowUpTaskConfirmationStatus.EXPIRED
    assert resolved_case.expired_at == now
    assert resolved_case.resolved_action is None
    assert task.status == FollowUpTaskStatus.OPEN

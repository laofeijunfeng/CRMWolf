from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


from app.core import deps
from app.core.database import Base
from app.crud.customer_activity import customer_activity_crud
from app.crud.sales_commitment import (
    follow_up_task_confirmation_case_crud,
    follow_up_task_crud,
    follow_up_task_event_crud,
    follow_up_task_llm_matcher_run_crud,
    follow_up_task_projection_run_crud,
    follow_up_task_reconciliation_evaluation_run_crud,
    follow_up_task_reconciliation_run_crud,
    sales_commitment_crud,
)
from app.models.customer import Customer, CustomerMember
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
    FollowUpTaskLLMMatcherRun,
    FollowUpTaskLLMMatcherRunStatus,
    FollowUpTaskProjectionRun,
    FollowUpTaskProjectionStatus,
    FollowUpTaskProjectionTrigger,
    FollowUpTaskReconciliationEvaluationRun,
    FollowUpTaskReconciliationEvaluationRunStatus,
    FollowUpTaskReconciliationRun,
    FollowUpTaskReconciliationRunStatus,
    FollowUpTaskSourceType,
    FollowUpTaskStatus,
    SalesCommitment,
    SalesCommitmentStatus,
)
from app.schemas.sales_commitment import (
    FollowUpTaskConfirmationCaseInternalCreate,
    FollowUpTaskEventResponse,
    FollowUpTaskInternalCreate,
    FollowUpTaskProjectionRunInternalCreate,
    FollowUpTaskProjectionRunResponse,
    FollowUpTaskResponse,
    SalesCommitmentInternalCreate,
    SalesCommitmentResponse,
)
from app.services.follow_up_task_backfill_service import follow_up_task_backfill_service
from app.services.follow_up_task_projection_service import (
    FollowUpTaskProjectionSkipReason,
    follow_up_task_projection_service,
)
from app.services.follow_up_task_reconciliation_evaluation_service import (
    FollowUpTaskReconciliationDecision,
    FollowUpTaskReconciliationEvaluationCase,
    follow_up_task_reconciliation_evaluation_service,
)
from app.services.work_summary_golden_suite import run_work_summary_golden_suite
from app.utils.public_id import (
    is_follow_up_task_projection_run_public_id,
    is_follow_up_task_public_id,
    is_follow_up_task_reconciliation_evaluation_run_public_id,
    is_sales_commitment_public_id,
)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerMember.__table__,
            CustomerActivity.__table__,
            CustomerVectorDocument.__table__,
            SalesCommitment.__table__,
            FollowUpTask.__table__,
            FollowUpTaskConfirmationCase.__table__,
            FollowUpTaskEvent.__table__,
            FollowUpTaskProjectionRun.__table__,
            FollowUpTaskReconciliationRun.__table__,
            FollowUpTaskLLMMatcherRun.__table__,
            FollowUpTaskReconciliationEvaluationRun.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def _seed_customer_and_activity(db_session, *, customer_owner_id: str = "1") -> None:
    db_session.add(
        Customer(
            id=1,
            public_id="cus_11111111111111111111111111111111",
            team_id=1,
            account_name="测试客户",
            city="上海",
            owner_id=customer_owner_id,
            creator_id="1",
        )
    )
    db_session.add(
        CustomerActivity(
            id=10,
            team_id=1,
            customer_id=1,
            activity_kind="PHONE_FOLLOW_UP",
            source_content="客户说下周看预算",
            next_action="下周三回访预算进展",
            next_follow_time=datetime(2026, 8, 12, 10, 0, 0),
            occurred_at=datetime(2026, 8, 6, 9, 0, 0),
            creator_id="1",
            owner_id="2",
        )
    )
    db_session.commit()


def _task_create(
    *,
    owner_id: str = "2",
    customer_id: int = 1,
    team_id: int = 1,
    source_activity_id: int | None = 10,
    task_hash: str = "task-hash-1",
    due_at: datetime | None = None,
    due_at_granularity: str = DueAtGranularity.DATETIME,
) -> FollowUpTaskInternalCreate:
    due_at = due_at or datetime(2026, 8, 12, 10, 0, 0)
    return FollowUpTaskInternalCreate(
        team_id=team_id,
        customer_id=customer_id,
        owner_id=owner_id,
        creator_id=owner_id,
        title="回访预算进展",
        description="客户说下周看预算",
        due_at=due_at,
        due_at_text="下周三",
        due_at_granularity=due_at_granularity,
        source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
        source_activity_id=source_activity_id,
        evidence_json={"activity_id": source_activity_id, "quote": "客户说下周看预算"},
        task_hash=task_hash,
    )


def test_public_id_helpers_accept_sales_commitment_prefixes_only():
    assert is_sales_commitment_public_id("scm_1234567890abcdef1234567890abcdef")
    assert is_follow_up_task_public_id("fut_1234567890abcdef1234567890abcdef")
    assert is_follow_up_task_projection_run_public_id("tpr_1234567890abcdef1234567890abcdef")
    assert is_follow_up_task_reconciliation_evaluation_run_public_id("ter_1234567890abcdef1234567890abcdef")
    assert not is_follow_up_task_public_id("123")
    assert not is_follow_up_task_public_id(123)


def test_sales_commitment_and_task_crud_use_public_ids_and_source_hash(db_session):
    _seed_customer_and_activity(db_session)

    commitment = sales_commitment_crud.create(
        db_session,
        SalesCommitmentInternalCreate(
            team_id=1,
            customer_id=1,
            owner_id="2",
            creator_id="2",
            title="跟进预算",
            content="下周三回访预算进展",
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_activity_id=10,
            due_at=datetime(2026, 8, 12, 10, 0, 0),
            due_at_text="下周三",
            evidence_json={"activity_id": 10},
            commitment_hash="commitment-hash-1",
        ),
    )
    task = follow_up_task_crud.create(
        db_session,
        _task_create(task_hash="task-hash-1"),
    )

    assert is_sales_commitment_public_id(commitment.public_id)
    assert is_follow_up_task_public_id(task.public_id)
    assert sales_commitment_crud.get_by_public_id(db_session, commitment.public_id, 1).id == commitment.id
    assert follow_up_task_crud.get_by_public_id(db_session, task.public_id, 1).id == task.id
    assert sales_commitment_crud.get_by_source_hash(
        db_session,
        team_id=1,
        source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
        source_activity_id=10,
        commitment_hash="commitment-hash-1",
    ).id == commitment.id
    assert follow_up_task_crud.get_by_source_hash(
        db_session,
        team_id=1,
        source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
        source_activity_id=10,
        task_hash="task-hash-1",
    ).id == task.id
    assert commitment.source_key == "activity:10"
    assert task.source_key == "activity:10"

    task_response = FollowUpTaskResponse.from_model(task)
    commitment_response = SalesCommitmentResponse.from_model(commitment)
    assert task_response.id == task.public_id
    assert commitment_response.id == commitment.public_id
    assert task_response.customer_id is None
    assert task_response.commitment_id is None
    assert commitment_response.customer_id is None

    with pytest.raises(ValidationError):
        FollowUpTaskResponse.model_validate(task)
    with pytest.raises(ValidationError):
        SalesCommitmentResponse.model_validate(commitment)


def test_source_key_supports_idempotency_when_source_activity_is_null(db_session):
    _seed_customer_and_activity(db_session)

    task = follow_up_task_crud.create(
        db_session,
        _task_create(
            source_activity_id=None,
            task_hash="historical-task",
        ).model_copy(
            update={
                "source_type": FollowUpTaskSourceType.HISTORICAL_BACKFILL,
                "source_key": "backfill:customer:1:owner:2:2026-08-06",
                "source_public_id": None,
                "evidence_json": {"backfill": True},
            }
        ),
    )

    assert task.source_activity_id is None
    assert task.source_key == "backfill:customer:1:owner:2:2026-08-06"
    assert follow_up_task_crud.get_by_source_hash(
        db_session,
        team_id=1,
        source_type=FollowUpTaskSourceType.HISTORICAL_BACKFILL,
        source_activity_id=None,
        source_key="backfill:customer:1:owner:2:2026-08-06",
        task_hash="historical-task",
    ).id == task.id


def test_source_key_unique_constraints_reject_duplicate_source_hashes(db_session):
    _seed_customer_and_activity(db_session)

    sales_commitment_crud.create(
        db_session,
        SalesCommitmentInternalCreate(
            team_id=1,
            customer_id=1,
            owner_id="2",
            creator_id="2",
            title="跟进预算",
            content="下周三回访预算进展",
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_activity_id=10,
            due_at=datetime(2026, 8, 12, 10, 0, 0),
            commitment_hash="duplicate-commitment",
        ),
    )
    with pytest.raises(IntegrityError):
        sales_commitment_crud.create(
            db_session,
            SalesCommitmentInternalCreate(
                team_id=1,
                customer_id=1,
                owner_id="2",
                creator_id="2",
                title="跟进预算",
                content="下周三回访预算进展",
                source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
                source_activity_id=10,
                due_at=datetime(2026, 8, 12, 10, 0, 0),
                commitment_hash="duplicate-commitment",
            ),
        )

    db_session.rollback()
    follow_up_task_crud.create(db_session, _task_create(source_activity_id=None, task_hash="duplicate-task").model_copy(
        update={
            "source_type": FollowUpTaskSourceType.HISTORICAL_BACKFILL,
            "source_key": "backfill:customer:1:owner:2:latest",
        }
    ))
    with pytest.raises(IntegrityError):
        follow_up_task_crud.create(db_session, _task_create(source_activity_id=None, task_hash="duplicate-task").model_copy(
            update={
                "source_type": FollowUpTaskSourceType.HISTORICAL_BACKFILL,
                "source_key": "backfill:customer:1:owner:2:latest",
            }
        ))


def test_crud_write_methods_can_flush_without_committing(db_session):
    _seed_customer_and_activity(db_session)

    task = follow_up_task_crud.create(db_session, _task_create(task_hash="no-commit"), commit=False)
    event = follow_up_task_event_crud.record_status_change(
        db_session,
        task=task,
        event_type=FollowUpTaskEventType.CREATED,
        actor_id="2",
        previous_status=None,
        commit=False,
    )

    assert task.id is not None
    assert task.public_id is not None
    assert event.id is not None
    assert follow_up_task_crud.get_by_public_id(db_session, task.public_id, 1).id == task.id

    db_session.rollback()
    assert follow_up_task_crud.get_by_public_id(db_session, task.public_id, 1) is None


def test_follow_up_task_owner_listing_filters_team_status_customer_and_due_window(db_session):
    _seed_customer_and_activity(db_session)
    base_due_at = datetime(2026, 8, 12, 10, 0, 0)

    expected = follow_up_task_crud.create(db_session, _task_create(task_hash="expected", due_at=base_due_at))
    follow_up_task_crud.create(db_session, _task_create(owner_id="3", task_hash="other-owner", due_at=base_due_at))
    follow_up_task_crud.create(
        db_session,
        _task_create(task_hash="too-late", due_at=base_due_at + timedelta(days=10)),
    )
    completed = follow_up_task_crud.create(db_session, _task_create(task_hash="completed", due_at=base_due_at))
    follow_up_task_crud.complete(db_session, completed)

    rows, total = follow_up_task_crud.list_for_owner(
        db_session,
        team_id=1,
        owner_id="2",
        statuses=[FollowUpTaskStatus.OPEN],
        due_at_start=datetime(2026, 8, 1),
        due_at_end=datetime(2026, 8, 20),
        customer_id=1,
    )

    assert total == 1
    assert [row.id for row in rows] == [expected.id]


def test_follow_up_task_named_due_windows_handle_date_and_datetime_overdue(db_session):
    _seed_customer_and_activity(db_session)
    anchor = datetime(2026, 8, 6, 15, 30, 0)
    today_date = follow_up_task_crud.create(
        db_session,
        _task_create(
            task_hash="today-date",
            due_at=datetime(2026, 8, 6, 0, 0, 0),
            due_at_granularity=DueAtGranularity.DATE,
        ),
    )
    today_datetime_expired = follow_up_task_crud.create(
        db_session,
        _task_create(
            task_hash="today-datetime-expired",
            due_at=datetime(2026, 8, 6, 9, 0, 0),
            due_at_granularity=DueAtGranularity.DATETIME,
        ),
    )
    yesterday_date = follow_up_task_crud.create(
        db_session,
        _task_create(
            task_hash="yesterday-date",
            due_at=datetime(2026, 8, 5, 0, 0, 0),
            due_at_granularity=DueAtGranularity.DATE,
        ),
    )
    next_week = follow_up_task_crud.create(
        db_session,
        _task_create(
            task_hash="next-week",
            due_at=datetime(2026, 8, 10, 10, 0, 0),
            due_at_granularity=DueAtGranularity.DATETIME,
        ),
    )
    completed_overdue = follow_up_task_crud.create(
        db_session,
        _task_create(
            task_hash="completed-overdue",
            due_at=datetime(2026, 8, 4, 10, 0, 0),
            due_at_granularity=DueAtGranularity.DATETIME,
        ),
    )
    follow_up_task_crud.complete(db_session, completed_overdue)

    today_rows, today_total = follow_up_task_crud.list_for_owner(
        db_session,
        team_id=1,
        owner_id="2",
        statuses=[FollowUpTaskStatus.OPEN],
        due_window="today",
        due_window_now=anchor,
    )
    overdue_rows, overdue_total = follow_up_task_crud.list_for_owner(
        db_session,
        team_id=1,
        owner_id="2",
        statuses=[FollowUpTaskStatus.OPEN],
        due_window="overdue",
        due_window_now=anchor,
    )
    next_week_rows, next_week_total = follow_up_task_crud.list_for_owner(
        db_session,
        team_id=1,
        owner_id="2",
        statuses=[FollowUpTaskStatus.OPEN],
        due_window="next_week",
        due_window_now=anchor,
    )

    assert today_total == 2
    assert [row.id for row in today_rows] == [today_date.id, today_datetime_expired.id]
    assert overdue_total == 2
    assert [row.id for row in overdue_rows] == [yesterday_date.id, today_datetime_expired.id]
    assert next_week_total == 1
    assert [row.id for row in next_week_rows] == [next_week.id]

    with pytest.raises(ValueError):
        follow_up_task_crud.list_for_owner(
            db_session,
            team_id=1,
            owner_id="2",
            due_window="today",
            due_at_start=datetime(2026, 8, 6),
        )


def test_empty_status_filter_returns_no_rows(db_session):
    _seed_customer_and_activity(db_session)
    follow_up_task_crud.create(db_session, _task_create(task_hash="empty-status-filter"))

    rows, total = follow_up_task_crud.list_for_owner(
        db_session,
        team_id=1,
        owner_id="2",
        statuses=[],
    )

    assert rows == []
    assert total == 0


def test_cancel_after_complete_clears_completed_timestamp(db_session):
    _seed_customer_and_activity(db_session)
    task = follow_up_task_crud.create(db_session, _task_create(task_hash="status-timestamps"))

    follow_up_task_crud.complete(db_session, task)
    assert task.completed_at is not None
    assert task.cancelled_at is None

    follow_up_task_crud.cancel(db_session, task)
    assert task.status == FollowUpTaskStatus.CANCELLED
    assert task.completed_at is None
    assert task.cancelled_at is not None


def test_follow_up_task_events_and_projection_run_status_updates(db_session):
    _seed_customer_and_activity(db_session)
    task = follow_up_task_crud.create(db_session, _task_create(task_hash="event-task"))

    previous_status = task.status
    follow_up_task_crud.complete(db_session, task)
    event = follow_up_task_event_crud.record_status_change(
        db_session,
        task=task,
        event_type=FollowUpTaskEventType.COMPLETED,
        actor_id="2",
        previous_status=previous_status,
        payload_json={"source": "test"},
    )

    rows, total = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task.id)
    assert total == 1
    assert rows[0].id == event.id
    assert rows[0].previous_status == FollowUpTaskStatus.OPEN
    assert rows[0].new_status == FollowUpTaskStatus.COMPLETED
    assert rows[0].source_public_id is None
    event_response = FollowUpTaskEventResponse.from_model(rows[0], task_public_id=task.public_id)
    assert event_response.task_id == task.public_id
    assert event_response.task_public_id == task.public_id
    assert event_response.source_public_id is None

    run = follow_up_task_projection_run_crud.create_running(
        db_session,
        FollowUpTaskProjectionRunInternalCreate(
            team_id=1,
            trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_STRUCTURED_COMPLETED,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_activity_id=10,
            actor_id="2",
            input_snapshot_hash="input-hash",
        ),
    )
    assert is_follow_up_task_projection_run_public_id(run.public_id)
    assert run.status == FollowUpTaskProjectionStatus.RUNNING
    assert run.source_key == "activity:10"

    run = follow_up_task_projection_run_crud.mark_success(
        db_session,
        run,
        created_task_ids=[task.id],
        projection_hash="projection-hash",
        duration_ms=123,
    )
    assert run.status == FollowUpTaskProjectionStatus.SUCCESS
    assert run.task_count == 1
    assert run.created_task_ids_json == [task.id]
    assert run.finished_at is not None
    rows, total = follow_up_task_projection_run_crud.list_by_source(
        db_session,
        team_id=1,
        source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
        source_activity_id=10,
    )
    assert total == 1
    assert rows[0].id == run.id
    run_response = FollowUpTaskProjectionRunResponse.from_model(
        run,
        created_task_public_ids=follow_up_task_crud.list_public_ids_by_ids(
            db_session,
            team_id=1,
            task_ids=run.created_task_ids_json,
        ),
    )
    assert run_response.id == run.public_id
    assert run_response.created_task_ids == [task.public_id]


def test_reconciliation_and_llm_run_crud_default_started_at_when_none(db_session):
    _seed_customer_and_activity(db_session)

    reconciliation_run = follow_up_task_reconciliation_run_crud.create(
        db_session,
        {
            "team_id": 1,
            "customer_id": 1,
            "owner_id": "2",
            "status": FollowUpTaskReconciliationRunStatus.SKIPPED,
            "skip_reason": "NO_OPEN_CANDIDATES",
            "include_cross_owner": False,
            "started_at": None,
        },
    )
    matcher_run = follow_up_task_llm_matcher_run_crud.create(
        db_session,
        {
            "team_id": 1,
            "owner_id": "2",
            "status": FollowUpTaskLLMMatcherRunStatus.SKIPPED,
            "source": "safe_fallback",
            "needs_confirmation": False,
            "started_at": None,
        },
    )

    assert reconciliation_run.started_at is not None
    assert reconciliation_run.finished_at is not None
    assert matcher_run.started_at is not None
    assert matcher_run.finished_at is not None


def test_reconciliation_evaluation_run_crud_persists_quality_gate_metrics(db_session):
    summary = follow_up_task_reconciliation_evaluation_service.evaluate_many(
        [
            FollowUpTaskReconciliationEvaluationCase(
                name="false_close_budget_case",
                activity_owner_id="2",
                task_owner_by_public_id={"fut_budget": "2"},
                result=FollowUpTaskReconciliationDecision(
                    decision="COMPLETE",
                    confidence=0.96,
                    task_public_id="fut_budget",
                    candidate_public_ids=("fut_budget",),
                ),
                allowed_decisions={"KEEP_OPEN"},
            ),
            FollowUpTaskReconciliationEvaluationCase(
                name="correct_delay_case",
                activity_owner_id="2",
                task_owner_by_public_id={"fut_demo": "2"},
                result=FollowUpTaskReconciliationDecision(
                    decision="DELAY",
                    confidence=0.91,
                    task_public_id="fut_demo",
                    candidate_public_ids=("fut_demo",),
                    proposed_due_at="2026-08-14T10:00:00",
                ),
                expected_decision="DELAY",
            ),
        ]
    )

    run = follow_up_task_reconciliation_evaluation_run_crud.record_summary(
        db_session,
        team_id=1,
        suite_name="unit_golden",
        fixture_path="tests/fixtures/follow_up_task_reconciliation_golden_cases.json",
        fixture_hash="abc123",
        summary=summary,
        thresholds_json={"false_close_rate_max": 0.0},
        duration_ms=42,
    )
    failed_run = follow_up_task_reconciliation_evaluation_run_crud.record_failed(
        db_session,
        suite_name="unit_golden",
        error_message="fixture parse failed",
        fixture_hash="bad123",
    )
    work_summary_run = follow_up_task_reconciliation_evaluation_run_crud.record_summary(
        db_session,
        suite_name="work_summary_unit_golden",
        summary=run_work_summary_golden_suite(),
        fixture_path="tests/fixtures/work_summary_golden_cases.json",
        fixture_hash="work123",
    )

    assert is_follow_up_task_reconciliation_evaluation_run_public_id(run.public_id)
    assert run.status == FollowUpTaskReconciliationEvaluationRunStatus.SUCCESS
    assert run.ok is False
    assert run.total_cases == 2
    assert run.passed_cases == 1
    assert run.failed_cases == 1
    assert run.false_close_count == 1
    assert run.false_close_rate == 0.5
    assert run.false_delay_count == 0
    assert run.metrics_json["false_close"]["case_names"] == ["false_close_budget_case"]
    assert run.failure_cases_json == [
        {
            "case_name": "false_close_budget_case",
            "failures": ["decision_not_allowed:COMPLETE"],
        }
    ]
    assert run.case_results_json[0]["case_name"] == "false_close_budget_case"
    assert run.thresholds_json == {"false_close_rate_max": 0.0}
    assert run.started_at is not None
    assert run.finished_at is not None

    assert is_follow_up_task_reconciliation_evaluation_run_public_id(failed_run.public_id)
    assert failed_run.team_id is None
    assert failed_run.status == FollowUpTaskReconciliationEvaluationRunStatus.FAILED
    assert failed_run.ok is False
    assert failed_run.error_message == "fixture parse failed"

    assert work_summary_run.ok is True
    assert work_summary_run.false_close_count == 0
    assert work_summary_run.false_delay_count == 0
    assert work_summary_run.metrics_json["fact_recall"]["rate"] == 1.0
    assert work_summary_run.metrics_json["hallucination_rate"]["rate"] == 0.0


def test_task_view_permission_can_use_customer_access_but_operation_requires_task_owner(db_session, monkeypatch):
    _seed_customer_and_activity(db_session, customer_owner_id="1")
    task = follow_up_task_crud.create(db_session, _task_create(owner_id="2", task_hash="permission-task"))
    permission_codes = ["customer:view:own"]

    def _fake_get_user_permissions(db, user_id, team_id=None):  # noqa: ARG001
        return [SimpleNamespace(code=code) for code in permission_codes]

    monkeypatch.setattr(deps.permission_crud, "get_user_permissions", _fake_get_user_permissions)
    current_user = SimpleNamespace(id=1)

    assert deps.check_follow_up_task_view_permission(task.public_id, 1, current_user, db_session).id == task.id

    with pytest.raises(HTTPException) as exc_info:
        deps.check_follow_up_task_owner_permission(task.public_id, 1, current_user, db_session)
    assert exc_info.value.status_code == 403

    with pytest.raises(HTTPException) as exc_info:
        deps.check_follow_up_task_direct_view_permission(task.public_id, 1, current_user, db_session)
    assert exc_info.value.status_code == 403

    permission_codes[:] = ["follow_up_task:operate:all"]
    assert deps.check_follow_up_task_owner_permission(task.public_id, 1, current_user, db_session).id == task.id


def test_projection_service_creates_task_from_activity_and_is_idempotent(db_session):
    _seed_customer_and_activity(db_session)

    result = follow_up_task_projection_service.project_activity(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_STRUCTURED_COMPLETED,
        actor_id="2",
    )
    repeat_result = follow_up_task_projection_service.project_activity(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_STRUCTURED_COMPLETED,
        actor_id="2",
    )

    assert result.created_task_ids
    assert result.created_commitment_ids
    assert result.skip_reason is None
    assert repeat_result.skip_reason == FollowUpTaskProjectionSkipReason.NO_CHANGE

    rows, total = follow_up_task_crud.list_for_owner(
        db_session,
        team_id=1,
        owner_id="2",
        statuses=[FollowUpTaskStatus.OPEN],
    )
    assert total == 1
    assert rows[0].title == "下周三回访预算进展"
    assert rows[0].owner_id == "2"
    assert rows[0].creator_id == "1"
    assert rows[0].source_key == "activity:10"
    assert rows[0].source_activity_id == 10
    assert rows[0].due_at == datetime(2026, 8, 12, 10, 0, 0)
    assert rows[0].due_at_granularity == DueAtGranularity.DATETIME
    assert "activity_id" not in rows[0].evidence_json

    events, event_total = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=rows[0].id)
    assert event_total == 1
    assert events[0].event_type == FollowUpTaskEventType.CREATED


def test_projection_service_stages_commitment_and_task_vector_metadata(db_session):
    _seed_customer_and_activity(db_session)

    result = follow_up_task_projection_service.project_activity(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_STRUCTURED_COMPLETED,
        actor_id="2",
    )

    task = follow_up_task_crud.get_by_id(db_session, result.created_task_ids[0], team_id=1)
    commitment = sales_commitment_crud.get_by_id(db_session, result.created_commitment_ids[0], team_id=1)
    documents = {
        document.source_type: document
        for document in db_session.query(CustomerVectorDocument).order_by(CustomerVectorDocument.source_type.asc())
    }
    assert set(documents) == {
        CustomerVectorDocumentSourceType.FOLLOW_UP_TASK,
        CustomerVectorDocumentSourceType.SALES_COMMITMENT,
    }
    assert documents[CustomerVectorDocumentSourceType.FOLLOW_UP_TASK].source_object_id == task.public_id
    assert documents[CustomerVectorDocumentSourceType.FOLLOW_UP_TASK].business_object_id == task.public_id
    assert documents[CustomerVectorDocumentSourceType.FOLLOW_UP_TASK].metadata_json["task_public_id"] == task.public_id
    assert documents[CustomerVectorDocumentSourceType.FOLLOW_UP_TASK].metadata_json["status"] == FollowUpTaskStatus.OPEN
    assert documents[CustomerVectorDocumentSourceType.SALES_COMMITMENT].source_object_id == commitment.public_id
    assert documents[CustomerVectorDocumentSourceType.SALES_COMMITMENT].metadata_json["commitment_public_id"] == commitment.public_id
    assert documents[CustomerVectorDocumentSourceType.SALES_COMMITMENT].sync_status == CustomerVectorDocumentSyncStatus.PENDING


def test_projection_run_records_success_and_idempotent_retry(db_session):
    _seed_customer_and_activity(db_session)

    result = follow_up_task_projection_service.run_activity_projection(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_STRUCTURED_COMPLETED,
        actor_id="2",
    )
    repeat_result = follow_up_task_projection_service.run_activity_projection(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_STRUCTURED_COMPLETED,
        actor_id="2",
    )

    assert result.projection_run_status == FollowUpTaskProjectionStatus.SUCCESS
    assert result.projection_run_id is not None
    assert result.created_task_ids
    run = follow_up_task_projection_run_crud.get_by_id(db_session, result.projection_run_id, team_id=1)
    assert run.status == FollowUpTaskProjectionStatus.SUCCESS
    assert run.created_task_ids_json == result.created_task_ids
    assert run.created_commitment_ids_json == result.created_commitment_ids
    assert run.task_count == 1
    assert run.commitment_count == 1
    assert run.input_snapshot_hash == result.input_snapshot_hash
    assert run.projection_hash == result.projection_hash
    assert run.finished_at is not None

    assert repeat_result.projection_run_status == FollowUpTaskProjectionStatus.SKIPPED
    assert repeat_result.skip_reason == FollowUpTaskProjectionSkipReason.NO_CHANGE
    rows, total = follow_up_task_crud.list_for_owner(
        db_session,
        team_id=1,
        owner_id="2",
        statuses=[FollowUpTaskStatus.OPEN],
    )
    assert total == 1
    assert rows[0].id == result.created_task_ids[0]


def test_projection_run_skips_existing_completed_source_hash_instead_of_failing(db_session):
    _seed_customer_and_activity(db_session)

    first = follow_up_task_projection_service.run_activity_projection(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.HISTORICAL_BACKFILL,
        actor_id="2",
    )
    task = follow_up_task_crud.get_by_id(db_session, first.created_task_ids[0], team_id=1)
    follow_up_task_crud.complete(db_session, task)

    repeat = follow_up_task_projection_service.run_activity_projection(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.HISTORICAL_BACKFILL,
        actor_id="2",
    )

    assert repeat.projection_run_status == FollowUpTaskProjectionStatus.SKIPPED
    assert repeat.skip_reason == FollowUpTaskProjectionSkipReason.DUPLICATE_EXISTING_TASK
    assert repeat.error_message is None
    assert db_session.query(FollowUpTask).count() == 1
    run = follow_up_task_projection_run_crud.get_by_id(db_session, repeat.projection_run_id, team_id=1)
    assert run.status == FollowUpTaskProjectionStatus.SKIPPED
    assert run.skip_reason == FollowUpTaskProjectionSkipReason.DUPLICATE_EXISTING_TASK
    assert run.error_message is None


def test_projection_run_records_skipped_without_next_step(db_session):
    _seed_customer_and_activity(db_session)
    activity = customer_activity_crud.get_by_id(db_session, 10)
    activity.next_action = None
    activity.next_follow_time = None
    db_session.commit()

    result = follow_up_task_projection_service.run_activity_projection(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_STRUCTURED_COMPLETED,
        actor_id="2",
    )

    assert result.projection_run_status == FollowUpTaskProjectionStatus.SKIPPED
    assert result.skip_reason == FollowUpTaskProjectionSkipReason.NO_NEXT_STEP
    run = follow_up_task_projection_run_crud.get_by_id(db_session, result.projection_run_id, team_id=1)
    assert run.status == FollowUpTaskProjectionStatus.SKIPPED
    assert run.skip_reason == FollowUpTaskProjectionSkipReason.NO_NEXT_STEP
    assert run.task_count == 0
    assert run.commitment_count == 0


def test_projection_run_records_commitment_only_skip_reason(db_session):
    _seed_customer_and_activity(db_session)
    activity = customer_activity_crud.get_by_id(db_session, 10)
    activity.next_action = "后续继续保持联系"
    activity.next_follow_time = None
    db_session.commit()

    result = follow_up_task_projection_service.run_activity_projection(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_STRUCTURED_COMPLETED,
        actor_id="2",
    )

    assert result.projection_run_status == FollowUpTaskProjectionStatus.SKIPPED
    assert result.skip_reason == FollowUpTaskProjectionSkipReason.NO_DUE_AT
    assert result.created_commitment_ids
    run = follow_up_task_projection_run_crud.get_by_id(db_session, result.projection_run_id, team_id=1)
    assert run.status == FollowUpTaskProjectionStatus.SKIPPED
    assert run.skip_reason == FollowUpTaskProjectionSkipReason.NO_DUE_AT
    assert run.created_commitment_ids_json == result.created_commitment_ids
    assert run.commitment_count == 1


def test_projection_run_records_failed_and_truncates_error(db_session, monkeypatch):
    _seed_customer_and_activity(db_session)

    def _raise_projection(*args, **kwargs):  # noqa: ARG001
        raise RuntimeError("x" * 5000)

    monkeypatch.setattr(follow_up_task_projection_service, "project_activity", _raise_projection)

    result = follow_up_task_projection_service.run_activity_projection(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_STRUCTURED_COMPLETED,
        actor_id="2",
    )

    assert result.projection_run_status == FollowUpTaskProjectionStatus.FAILED
    assert result.error_message == "x" * 4000
    failed_rows, failed_total = follow_up_task_projection_run_crud.list_failed(
        db_session,
        team_id=1,
        source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
    )
    assert failed_total == 1
    assert failed_rows[0].id == result.projection_run_id
    assert failed_rows[0].status == FollowUpTaskProjectionStatus.FAILED
    assert failed_rows[0].error_message == "x" * 4000


def test_projection_run_retry_failed_run_uses_same_projection_and_does_not_duplicate(db_session, monkeypatch):
    _seed_customer_and_activity(db_session)
    original_project_activity = follow_up_task_projection_service.project_activity
    calls = {"count": 0}

    def _fail_once(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary failure")
        return original_project_activity(*args, **kwargs)

    monkeypatch.setattr(follow_up_task_projection_service, "project_activity", _fail_once)
    failed_result = follow_up_task_projection_service.run_activity_projection(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_STRUCTURED_COMPLETED,
        actor_id="2",
    )
    retry_result = follow_up_task_projection_service.retry_projection_run(
        db_session,
        projection_run_id=failed_result.projection_run_id,
        actor_id="2",
    )
    repeat_result = follow_up_task_projection_service.retry_projection_run(
        db_session,
        projection_run_id=failed_result.projection_run_id,
        actor_id="2",
    )

    assert failed_result.projection_run_status == FollowUpTaskProjectionStatus.FAILED
    assert retry_result.projection_run_status == FollowUpTaskProjectionStatus.SUCCESS
    assert retry_result.created_task_ids
    assert repeat_result.projection_run_status == FollowUpTaskProjectionStatus.SKIPPED
    assert repeat_result.skip_reason == FollowUpTaskProjectionSkipReason.NO_CHANGE

    rows, total = follow_up_task_crud.list_for_owner(
        db_session,
        team_id=1,
        owner_id="2",
        statuses=[FollowUpTaskStatus.OPEN],
    )
    assert total == 1
    retry_run = follow_up_task_projection_run_crud.get_by_id(db_session, retry_result.projection_run_id, team_id=1)
    repeat_run = follow_up_task_projection_run_crud.get_by_id(db_session, repeat_result.projection_run_id, team_id=1)
    assert retry_run.attempt_count == 2
    assert repeat_run.attempt_count == 2


def test_projection_service_updates_same_source_task_after_activity_changes(db_session):
    _seed_customer_and_activity(db_session)
    created = follow_up_task_projection_service.project_activity(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_CREATED_DETERMINISTIC,
        actor_id="2",
    )
    task_id = created.created_task_ids[0]
    activity = customer_activity_crud.get_by_id(db_session, 10)
    activity.next_action = "周五确认采购流程"
    activity.next_follow_time = datetime(2026, 8, 14, 16, 0, 0)
    db_session.commit()

    result = follow_up_task_projection_service.project_activity(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_UPDATED,
        actor_id="2",
    )

    assert result.updated_task_ids == [task_id]
    task = follow_up_task_crud.get_by_id(db_session, task_id, team_id=1)
    assert task.title == "周五确认采购流程"
    assert task.due_at == datetime(2026, 8, 14, 16, 0, 0)
    assert task.status == FollowUpTaskStatus.OPEN
    events, event_total = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task_id)
    assert event_total == 2
    assert events[-1].event_type == FollowUpTaskEventType.UPDATED
    task_document = (
        db_session.query(CustomerVectorDocument)
        .filter(
            CustomerVectorDocument.source_type == CustomerVectorDocumentSourceType.FOLLOW_UP_TASK,
            CustomerVectorDocument.source_object_id == task.public_id,
        )
        .one()
    )
    assert task_document.metadata_json["due_at"] == "2026-08-14T16:00:00"
    assert task_document.metadata_json["status"] == FollowUpTaskStatus.OPEN


def test_projection_service_cancels_same_source_task_when_next_step_removed(db_session):
    _seed_customer_and_activity(db_session)
    created = follow_up_task_projection_service.project_activity(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_CREATED_DETERMINISTIC,
        actor_id="2",
    )
    activity = customer_activity_crud.get_by_id(db_session, 10)
    activity.next_action = None
    activity.next_follow_time = None
    db_session.commit()

    result = follow_up_task_projection_service.project_activity(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_UPDATED,
        actor_id="2",
    )

    assert result.skip_reason == FollowUpTaskProjectionSkipReason.SOURCE_NEXT_STEP_REMOVED
    assert result.cancelled_task_ids == created.created_task_ids
    task = follow_up_task_crud.get_by_id(db_session, created.created_task_ids[0], team_id=1)
    commitment = sales_commitment_crud.get_by_id(db_session, created.created_commitment_ids[0], team_id=1)
    assert task.status == FollowUpTaskStatus.CANCELLED
    assert commitment.status == SalesCommitmentStatus.CANCELLED
    task_document = (
        db_session.query(CustomerVectorDocument)
        .filter(
            CustomerVectorDocument.source_type == CustomerVectorDocumentSourceType.FOLLOW_UP_TASK,
            CustomerVectorDocument.source_object_id == task.public_id,
        )
        .one()
    )
    commitment_document = (
        db_session.query(CustomerVectorDocument)
        .filter(
            CustomerVectorDocument.source_type == CustomerVectorDocumentSourceType.SALES_COMMITMENT,
            CustomerVectorDocument.source_object_id == commitment.public_id,
        )
        .one()
    )
    assert task_document.metadata_json["status"] == FollowUpTaskStatus.CANCELLED
    assert commitment_document.metadata_json["status"] == SalesCommitmentStatus.CANCELLED


def test_projection_service_cancels_pending_confirmation_case_when_next_step_removed(db_session):
    _seed_customer_and_activity(db_session)
    created = follow_up_task_projection_service.project_activity(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_CREATED_DETERMINISTIC,
        actor_id="2",
    )
    task = follow_up_task_crud.get_by_id(db_session, created.created_task_ids[0], team_id=1)
    case = follow_up_task_confirmation_case_crud.create(
        db_session,
        FollowUpTaskConfirmationCaseInternalCreate(
            team_id=1,
            task_id=task.id,
            customer_id=task.customer_id,
            owner_id=task.owner_id,
            creator_id=task.owner_id,
            status=FollowUpTaskConfirmationStatus.PENDING,
            suggested_action=FollowUpTaskConfirmationResolutionAction.COMPLETE,
            confirmation_hash="projection-next-step-removed-case",
            question_text="上次安排的任务是否已经完成?",
            source_activity_id=10,
            source_public_id=task.source_public_id,
            source_plan_json={"plan_source": "unit_test"},
        ),
    )
    activity = customer_activity_crud.get_by_id(db_session, 10)
    activity.next_action = None
    activity.next_follow_time = None
    db_session.commit()

    result = follow_up_task_projection_service.project_activity(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_UPDATED,
        actor_id="2",
    )
    db_session.refresh(case)

    assert result.skip_reason == FollowUpTaskProjectionSkipReason.SOURCE_NEXT_STEP_REMOVED
    assert case.status == FollowUpTaskConfirmationStatus.CANCELLED
    assert case.cancelled_by_id == "2"
    assert case.cancelled_reason == FollowUpTaskProjectionSkipReason.SOURCE_NEXT_STEP_REMOVED


def test_projection_service_creates_commitment_only_without_due_at(db_session):
    _seed_customer_and_activity(db_session)
    activity = customer_activity_crud.get_by_id(db_session, 10)
    activity.next_action = "后续继续保持联系"
    activity.next_follow_time = None
    db_session.commit()

    result = follow_up_task_projection_service.project_activity(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_STRUCTURED_COMPLETED,
        actor_id="2",
    )

    assert result.skip_reason == FollowUpTaskProjectionSkipReason.NO_DUE_AT
    assert result.created_commitment_ids
    assert result.created_task_ids == []
    rows, total = follow_up_task_crud.list_for_owner(
        db_session,
        team_id=1,
        owner_id="2",
        statuses=[FollowUpTaskStatus.OPEN],
    )
    assert rows == []
    assert total == 0
    commitment = sales_commitment_crud.get_by_id(db_session, result.created_commitment_ids[0], team_id=1)
    document = (
        db_session.query(CustomerVectorDocument)
        .filter(
            CustomerVectorDocument.source_type == CustomerVectorDocumentSourceType.SALES_COMMITMENT,
            CustomerVectorDocument.source_object_id == commitment.public_id,
        )
        .one()
    )
    assert document.metadata_json["commitment_public_id"] == commitment.public_id
    assert document.metadata_json["status"] == SalesCommitmentStatus.OPEN


def test_projection_service_cancels_open_task_for_deleted_activity_snapshot(db_session):
    _seed_customer_and_activity(db_session)
    created = follow_up_task_projection_service.project_activity(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_CREATED_DETERMINISTIC,
        actor_id="2",
    )
    activity_snapshot = customer_activity_crud.get_by_id(db_session, 10)

    result = follow_up_task_projection_service.project_activity(
        db_session,
        activity_id=10,
        activity_snapshot=activity_snapshot,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_DELETED,
        actor_id="2",
    )

    assert result.skip_reason == FollowUpTaskProjectionSkipReason.SOURCE_ACTIVITY_DELETED
    assert result.cancelled_task_ids == created.created_task_ids
    task = follow_up_task_crud.get_by_id(db_session, created.created_task_ids[0], team_id=1)
    assert task.status == FollowUpTaskStatus.CANCELLED


def test_projection_service_keeps_same_customer_different_owner_tasks_separate(db_session):
    _seed_customer_and_activity(db_session)
    db_session.add(
        CustomerActivity(
            id=11,
            team_id=1,
            customer_id=1,
            activity_kind="PHONE_FOLLOW_UP",
            source_content="销售自己周五确认合同流程",
            next_action="周五确认合同流程",
            next_follow_time=datetime(2026, 8, 14, 10, 0, 0),
            occurred_at=datetime(2026, 8, 6, 11, 0, 0),
            creator_id="3",
            owner_id="3",
        )
    )
    db_session.commit()

    follow_up_task_projection_service.project_activity(
        db_session,
        activity_id=10,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_CREATED_DETERMINISTIC,
        actor_id="2",
    )
    follow_up_task_projection_service.project_activity(
        db_session,
        activity_id=11,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_CREATED_DETERMINISTIC,
        actor_id="3",
    )

    owner_2_rows, owner_2_total = follow_up_task_crud.list_for_owner(
        db_session,
        team_id=1,
        owner_id="2",
        statuses=[FollowUpTaskStatus.OPEN],
    )
    owner_3_rows, owner_3_total = follow_up_task_crud.list_for_owner(
        db_session,
        team_id=1,
        owner_id="3",
        statuses=[FollowUpTaskStatus.OPEN],
    )
    assert owner_2_total == 1
    assert owner_3_total == 1
    assert owner_2_rows[0].source_activity_id == 10
    assert owner_3_rows[0].source_activity_id == 11


def test_historical_backfill_dry_run_does_not_write_tasks_or_projection_runs(db_session):
    _seed_customer_and_activity(db_session)

    result = follow_up_task_backfill_service.backfill_customer_activities(
        db_session,
        team_id=1,
        days=90,
        dry_run=True,
        now=datetime(2026, 8, 20, 10, 0, 0),
    )

    assert result.dry_run is True
    assert result.scanned_activity_count == 1
    assert result.selected_group_count == 1
    assert result.would_project_count == 1
    assert db_session.query(FollowUpTask).count() == 0
    assert db_session.query(FollowUpTaskProjectionRun).count() == 0


def test_historical_backfill_skips_group_when_latest_activity_has_no_due_time(db_session):
    _seed_customer_and_activity(db_session)
    db_session.add(
        CustomerActivity(
            id=11,
            team_id=1,
            customer_id=1,
            activity_kind="OTHER_FOLLOW_UP",
            source_content="客户说预算还没进展",
            summary="预算还没进展",
            next_action=None,
            next_follow_time=None,
            occurred_at=datetime(2026, 8, 7, 9, 0, 0),
            creator_id="2",
            owner_id="2",
        )
    )
    db_session.commit()

    result = follow_up_task_backfill_service.backfill_customer_activities(
        db_session,
        team_id=1,
        days=90,
        dry_run=False,
        now=datetime(2026, 8, 20, 10, 0, 0),
    )

    assert result.selected_group_count == 1
    assert result.duplicate_group_activity_count == 1
    assert result.skipped_no_due_at_count == 1
    assert result.would_project_count == 0
    assert db_session.query(FollowUpTask).count() == 0
    assert db_session.query(FollowUpTaskProjectionRun).count() == 0


def test_historical_backfill_projects_only_latest_due_activity_per_customer_owner_and_is_idempotent(db_session):
    _seed_customer_and_activity(db_session)
    db_session.add(
        CustomerActivity(
            id=11,
            team_id=1,
            customer_id=1,
            activity_kind="PHONE_FOLLOW_UP",
            source_content="客户说下周五确认预算",
            summary="客户下周五确认预算",
            next_action="下周五确认预算",
            next_follow_time=datetime(2026, 8, 21, 10, 0, 0),
            occurred_at=datetime(2026, 8, 7, 9, 0, 0),
            creator_id="2",
            owner_id="2",
        )
    )
    db_session.commit()

    first = follow_up_task_backfill_service.backfill_customer_activities(
        db_session,
        team_id=1,
        days=90,
        dry_run=False,
        now=datetime(2026, 8, 20, 10, 0, 0),
    )
    second = follow_up_task_backfill_service.backfill_customer_activities(
        db_session,
        team_id=1,
        days=90,
        dry_run=False,
        now=datetime(2026, 8, 20, 10, 0, 0),
    )

    rows, total = follow_up_task_crud.list_for_owner(
        db_session,
        team_id=1,
        owner_id="2",
        statuses=[FollowUpTaskStatus.OPEN],
    )
    assert first.created_task_count == 1
    assert first.created_commitment_count == 1
    assert first.projection_run_ids
    assert second.created_task_count == 0
    assert second.skipped_projection_count == 1
    assert total == 1
    assert rows[0].source_activity_id == 11
    assert rows[0].title == "下周五确认预算"

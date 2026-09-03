"""Regression tests for durable customer-activity deletion watermarks."""

from datetime import datetime

from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud.customer_activity import CustomerActivityCRUD
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def test_hard_delete_writes_tombstone_in_same_transaction():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(
        engine,
        tables=[Customer.__table__, CustomerActivity.__table__, CustomerActivityDeletionTombstone.__table__],
    )
    db = sessionmaker(bind=engine)()
    try:
        customer = Customer(team_id=2, account_name="删除测试客户", city="广州", creator_id="u1")
        db.add(customer)
        db.flush()
        activity = CustomerActivity(
            team_id=2,
            customer_id=customer.id,
            activity_kind="PHONE_CALL",
            source_content="已删除的跟进",
            occurred_at=datetime(2026, 8, 29, 10, 0),
            creator_id="u1",
            owner_id="u1",
            activity_revision=3,
        )
        db.add(activity)
        db.commit()
        activity_id = activity.id

        CustomerActivityCRUD().delete(db, activity, commit=False, deleted_by="u1")

        tombstone = (
            db.query(CustomerActivityDeletionTombstone)
            .filter(CustomerActivityDeletionTombstone.activity_id == activity_id)
            .one()
        )
        assert tombstone.customer_id == customer.id
        assert tombstone.team_id == 2
        assert tombstone.activity_revision == 3
        assert tombstone.deleted_by == "u1"
        assert db.query(CustomerActivity).filter(CustomerActivity.id == activity_id).one_or_none() is None

        db.commit()
        assert (
            db.query(CustomerActivityDeletionTombstone)
            .filter(CustomerActivityDeletionTombstone.activity_id == activity_id)
            .count()
            == 1
        )
    finally:
        db.close()
        engine.dispose()


def test_delete_preserves_unfinished_job_evidence_and_marks_it_skipped(monkeypatch):
    from sqlalchemy.pool import StaticPool

    from app.crud.customer_activity_ai_job import CustomerActivityAIJobCRUD
    from app.crud.customer_activity_post_commit_job import CustomerActivityPostCommitJobCRUD
    from app.models.customer_activity_ai_job import CustomerActivityAIJob
    from app.models.customer_opportunity_suggestion_job import CustomerOpportunitySuggestionJob
    from app.models.customer_activity_post_commit_job import (
        CustomerActivityPostCommitJob,
        CustomerActivityPostCommitJobStatus,
    )
    from app.services.customer_activity_write_service import CustomerActivityWriteService
    from app.services.customer_intelligence_refresh_service import CustomerIntelligenceCommittedEventRequest

    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerActivity.__table__,
            CustomerActivityDeletionTombstone.__table__,
            CustomerActivityAIJob.__table__,
            CustomerActivityPostCommitJob.__table__,
            CustomerOpportunitySuggestionJob.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        customer = Customer(team_id=2, account_name="删除任务证据客户", city="广州", creator_id="u1")
        db.add(customer)
        db.flush()
        activity = CustomerActivity(
            team_id=2,
            customer_id=customer.id,
            activity_kind="PHONE_CALL",
            source_content="待删除的页面跟进",
            occurred_at=datetime(2026, 8, 29, 10, 0),
            creator_id="u1",
            owner_id="u1",
            activity_revision=1,
            submission_source="FORM",
        )
        db.add(activity)
        db.flush()
        ai_job = CustomerActivityAIJob(
            public_id="caij_delete_evidence",
            team_id=2,
            activity_id=activity.id,
            activity_revision=1,
            job_type="STRUCTURE_AND_EVALUATE",
            submission_source="FORM",
            status="RUNNING",
            attempt_count=1,
            lease_token="ai-lease",
            lease_expires_at=datetime(2026, 9, 2, 12, 0),
            run_id="ai-run",
            graph_thread_id="ai-thread",
            result_json={"partial": "保留"},
            error_message="worker still running",
        )
        ai_completed = CustomerActivityAIJob(
            public_id="caij_delete_completed",
            team_id=2,
            activity_id=activity.id,
            activity_revision=1,
            job_type="ANOTHER_JOB",
            submission_source="FORM",
            status="COMPLETED",
            attempt_count=1,
            run_id="ai-run-completed",
            graph_thread_id="ai-thread-completed",
            result_json={"done": True},
        )
        post_commit_job = CustomerActivityPostCommitJob(
            public_id="pcj_delete_evidence",
            team_id=2,
            activity_id=activity.id,
            activity_revision=1,
            trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
            actor_id="u1",
            status=CustomerActivityPostCommitJobStatus.RETRY_PENDING,
            attempt_count=1,
            next_attempt_at=datetime(2026, 9, 2, 11, 0),
            lease_token=None,
            lease_expires_at=None,
            run_id="pc-run",
            graph_thread_id="pc-thread",
            result_json={"attempt": 1},
            error_message="temporary failure",
        )
        opportunity_suggestion_job = CustomerOpportunitySuggestionJob(
            public_id="cosj_delete_evidence",
            team_id=2,
            activity_id=activity.id,
            activity_revision=1,
            submission_source="AGENT",
            status="RETRY_PENDING",
            attempt_count=1,
            next_attempt_at=datetime(2026, 9, 2, 11, 0),
            run_id="opp-run",
            graph_thread_id="opp-thread",
            result_json={"decision": "CREATE_OPPORTUNITY"},
            error_message="temporary opportunity suggestion failure",
        )
        opportunity_suggestion_completed = CustomerOpportunitySuggestionJob(
            public_id="cosj_delete_completed",
            team_id=2,
            activity_id=activity.id,
            activity_revision=2,
            submission_source="AGENT",
            status="COMPLETED",
            attempt_count=1,
            run_id="opp-run-completed",
            graph_thread_id="opp-thread-completed",
            result_json={"decision": "NO_ACTION"},
        )
        db.add_all([ai_job, ai_completed, post_commit_job, opportunity_suggestion_job, opportunity_suggestion_completed])
        db.commit()

        class _Projection:
            def run_activity_projection(self, db, **kwargs):
                return None

        class _Refresh:
            def enqueue_committed_event_refresh(self, db, *, event, scope):
                return CustomerIntelligenceCommittedEventRequest(
                    request_id="refresh-delete",
                    event=event,
                    scope=scope,
                )

        monkeypatch.setattr(
            "app.services.follow_up_task_projection_service.follow_up_task_projection_service",
            _Projection(),
            raising=False,
        )
        service = CustomerActivityWriteService(
            ai_job_crud=CustomerActivityAIJobCRUD(),
            post_commit_job_crud=CustomerActivityPostCommitJobCRUD(),
            intelligence_refresh_service=_Refresh(),
        )
        result = service.delete(db, activity=activity, actor_id="u1")

        assert result.activity_id == activity.id
        assert db.query(CustomerActivity).filter(CustomerActivity.id == activity.id).one_or_none() is None
        skipped_ai = db.query(CustomerActivityAIJob).filter_by(public_id="caij_delete_evidence").one()
        assert skipped_ai.status == "SKIPPED"
        assert skipped_ai.result_json["partial"] == "保留"
        assert skipped_ai.result_json["skip_reason"] == "SOURCE_ACTIVITY_DELETED"
        assert skipped_ai.error_message == "SOURCE_ACTIVITY_DELETED"
        assert skipped_ai.lease_token is None
        assert skipped_ai.lease_expires_at is None
        assert skipped_ai.next_attempt_at is None
        assert skipped_ai.finished_at is not None

        completed_ai = db.query(CustomerActivityAIJob).filter_by(public_id="caij_delete_completed").one()
        assert completed_ai.status == "COMPLETED"
        skipped_post_commit = (
            db.query(CustomerActivityPostCommitJob).filter_by(public_id="pcj_delete_evidence").one()
        )
        assert skipped_post_commit.status == CustomerActivityPostCommitJobStatus.SKIPPED
        assert skipped_post_commit.result_json["attempt"] == 1
        assert skipped_post_commit.result_json["skip_reason"] == "SOURCE_ACTIVITY_DELETED"
        assert skipped_post_commit.error_message == "SOURCE_ACTIVITY_DELETED"
        assert skipped_post_commit.next_attempt_at is None
        assert skipped_post_commit.finished_at is not None

        skipped_opportunity_suggestion = (
            db.query(CustomerOpportunitySuggestionJob).filter_by(public_id="cosj_delete_evidence").one()
        )
        assert skipped_opportunity_suggestion.status == "SKIPPED"
        assert skipped_opportunity_suggestion.result_json["decision"] == "CREATE_OPPORTUNITY"
        assert skipped_opportunity_suggestion.result_json["skip_reason"] == "SOURCE_ACTIVITY_DELETED"
        assert skipped_opportunity_suggestion.error_message == "SOURCE_ACTIVITY_DELETED"
        assert skipped_opportunity_suggestion.next_attempt_at is None
        assert skipped_opportunity_suggestion.finished_at is not None

        completed_opportunity_suggestion = (
            db.query(CustomerOpportunitySuggestionJob).filter_by(public_id="cosj_delete_completed").one()
        )
        assert completed_opportunity_suggestion.status == "COMPLETED"
    finally:
        db.close()
        engine.dispose()

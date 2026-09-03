"""Durability tests for Agent opportunity-suggestion jobs."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.crud.customer_opportunity_suggestion_job import CustomerOpportunitySuggestionJobCRUD
from app.models.customer_opportunity_suggestion_job import CustomerOpportunitySuggestionJob
from app.services.customer_activity_contracts import CustomerActivitySuggestionJobStatus


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
    Base.metadata.create_all(engine, tables=[CustomerOpportunitySuggestionJob.__table__])
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


def _enqueue(crud: CustomerOpportunitySuggestionJobCRUD, db_session, activity_id: int = 212):
    return crud.enqueue(
        db_session,
        team_id=1,
        activity_id=activity_id,
        activity_revision=1,
        submission_source="AGENT",
    )


def test_enqueue_is_idempotent_for_activity_revision(db_session):
    crud = CustomerOpportunitySuggestionJobCRUD()
    first = _enqueue(crud, db_session)
    second = _enqueue(crud, db_session)
    db_session.commit()

    assert first.public_id == second.public_id
    assert db_session.query(CustomerOpportunitySuggestionJob).count() == 1
    assert first.status == CustomerActivitySuggestionJobStatus.QUEUED.value
    assert first.graph_thread_id.startswith("customer_opportunity_suggestion:1:212:1:")


def test_enqueue_rejects_non_agent_sources(db_session):
    with pytest.raises(ValueError, match="仅允许由 Agent 活动创建"):
        CustomerOpportunitySuggestionJobCRUD().enqueue(
            db_session,
            team_id=1,
            activity_id=1,
            activity_revision=1,
            submission_source="FORM",
        )


def test_claim_is_exclusive_until_lease_expires(db_session):
    crud = CustomerOpportunitySuggestionJobCRUD()
    job = _enqueue(crud, db_session)
    now = datetime(2026, 9, 2, 10, 0)

    first = crud.claim_for_execution(
        db_session,
        team_id=1,
        public_id=job.public_id,
        lease_token="lease-a",
        lease_expires_at=datetime(2026, 9, 2, 10, 5),
        max_attempts=5,
        now=now,
    )
    second = crud.claim_for_execution(
        db_session,
        team_id=1,
        public_id=job.public_id,
        lease_token="lease-b",
        lease_expires_at=datetime(2026, 9, 2, 10, 6),
        max_attempts=5,
        now=now,
    )

    assert first is not None
    assert second is None
    assert first.attempt_count == 1
    assert first.lease_token == "lease-a"


def test_expired_running_lease_can_be_recovered(db_session):
    crud = CustomerOpportunitySuggestionJobCRUD()
    job = _enqueue(crud, db_session)
    crud.claim_for_execution(
        db_session,
        team_id=1,
        public_id=job.public_id,
        lease_token="dead-worker",
        lease_expires_at=datetime(2026, 9, 2, 10, 1),
        max_attempts=5,
        now=datetime(2026, 9, 2, 10, 0),
    )

    recovered = crud.claim_for_execution(
        db_session,
        team_id=1,
        public_id=job.public_id,
        lease_token="recovery-worker",
        lease_expires_at=datetime(2026, 9, 2, 10, 10),
        max_attempts=5,
        now=datetime(2026, 9, 2, 10, 2),
    )

    assert recovered is not None
    assert recovered.attempt_count == 2
    assert recovered.lease_token == "recovery-worker"


def test_completion_requires_current_lease_owner(db_session):
    crud = CustomerOpportunitySuggestionJobCRUD()
    job = _enqueue(crud, db_session)
    crud.claim_for_execution(
        db_session,
        team_id=1,
        public_id=job.public_id,
        lease_token="lease-owner",
        lease_expires_at=datetime(2026, 9, 2, 10, 5),
        max_attempts=5,
        now=datetime(2026, 9, 2, 10, 0),
    )

    assert (
        crud.mark_completed_if_lease_owner(
            db_session,
            team_id=1,
            public_id=job.public_id,
            lease_token="stale-lease",
            result_json={"decision": "NO_ACTION"},
        )
        is None
    )
    completed = crud.mark_completed_if_lease_owner(
        db_session,
        team_id=1,
        public_id=job.public_id,
        lease_token="lease-owner",
        result_json={"decision": "NO_ACTION"},
    )

    assert completed is not None
    assert completed.status == CustomerActivitySuggestionJobStatus.COMPLETED.value
    assert completed.result_json == {"decision": "NO_ACTION"}
    assert completed.finished_at is not None


def test_recovery_scan_only_returns_due_jobs(db_session):
    crud = CustomerOpportunitySuggestionJobCRUD()
    due = _enqueue(crud, db_session, activity_id=302)
    future = _enqueue(crud, db_session, activity_id=303)
    future.status = CustomerActivitySuggestionJobStatus.RETRY_PENDING.value
    future.next_attempt_at = datetime(2026, 9, 2, 11, 0)
    db_session.commit()

    candidates = crud.list_system_recovery_candidates(
        db_session,
        max_attempts=5,
        limit=20,
        now=datetime(2026, 9, 2, 10, 0),
    )

    assert [item.job_public_id for item in candidates] == [due.public_id]


def test_deletion_skips_unfinished_but_preserves_result_evidence(db_session):
    crud = CustomerOpportunitySuggestionJobCRUD()
    job = _enqueue(crud, db_session)
    job.error_message = "temporary error"
    job.result_json = {"partial": True}
    db_session.commit()

    changed = crud.mark_unfinished_skipped_for_activity(
        db_session,
        team_id=1,
        activity_id=212,
        reason="SOURCE_ACTIVITY_DELETED",
    )

    assert changed == 1
    persisted = crud.get_by_public_id(db_session, team_id=1, public_id=job.public_id)
    assert persisted is not None
    assert persisted.status == CustomerActivitySuggestionJobStatus.SKIPPED.value
    assert persisted.result_json == {
        "partial": True,
        "skip_reason": "SOURCE_ACTIVITY_DELETED",
        "source_activity_deleted": True,
        "previous_error": "temporary error",
    }
    assert persisted.lease_token is None
    assert persisted.next_attempt_at is None


def test_completed_jobs_are_not_rewritten_on_deletion(db_session):
    crud = CustomerOpportunitySuggestionJobCRUD()
    job = _enqueue(crud, db_session)
    job.status = CustomerActivitySuggestionJobStatus.COMPLETED.value
    job.result_json = {"decision": "CREATE_OPPORTUNITY"}
    db_session.commit()

    changed = crud.mark_unfinished_skipped_for_activity(
        db_session,
        team_id=1,
        activity_id=212,
        reason="SOURCE_ACTIVITY_DELETED",
    )

    assert changed == 0
    persisted = crud.get_by_public_id(db_session, team_id=1, public_id=job.public_id)
    assert persisted is not None
    assert persisted.status == CustomerActivitySuggestionJobStatus.COMPLETED.value
    assert persisted.result_json == {"decision": "CREATE_OPPORTUNITY"}

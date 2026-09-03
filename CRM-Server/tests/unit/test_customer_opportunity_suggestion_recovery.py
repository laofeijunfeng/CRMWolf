"""Recovery scheduler tests for durable Agent opportunity suggestions."""

from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.crud.customer_opportunity_suggestion_job import CustomerOpportunitySuggestionJobCRUD
from app.models.customer_opportunity_suggestion_job import CustomerOpportunitySuggestionJob
from app.services.customer_activity_contracts import CustomerActivitySuggestionJobStatus
from app.services.customer_opportunity_suggestion_job_service import (
    CustomerOpportunitySuggestionJobRunResult,
)
from app.tasks.customer_opportunity_suggestion_recovery import (
    CustomerOpportunitySuggestionRecoveryScheduler,
)


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


class _RecordingRunner:
    def __init__(self, statuses: dict[str, str]) -> None:
        self.statuses = statuses
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        status = self.statuses[request.job_public_id]
        return CustomerOpportunitySuggestionJobRunResult(
            job_public_id=request.job_public_id,
            activity_id=1,
            execution_status=status,
            success=status in {"COMPLETED", "SKIPPED"},
            retryable=status in {"RETRY_PENDING", "BUSY"},
        )


@pytest.mark.asyncio
async def test_recovery_dispatches_queued_and_expired_jobs_and_reports_outcomes(
    db_session,
    monkeypatch,
):
    crud = CustomerOpportunitySuggestionJobCRUD()
    queued = crud.enqueue(
        db_session,
        team_id=1,
        activity_id=501,
        activity_revision=1,
        submission_source="AGENT",
    )
    expired = crud.enqueue(
        db_session,
        team_id=2,
        activity_id=502,
        activity_revision=1,
        submission_source="AGENT",
    )
    crud.claim_for_execution(
        db_session,
        team_id=2,
        public_id=expired.public_id,
        lease_token="worker-before-restart",
        lease_expires_at=datetime(2026, 9, 2, 9, 1),
        max_attempts=5,
        now=datetime(2026, 9, 2, 9, 0),
    )
    expired.lease_expires_at = datetime(2026, 9, 1, 9, 0)
    db_session.commit()

    session_factory = sessionmaker(bind=db_session.get_bind())
    runner = _RecordingRunner(
        {
            queued.public_id: CustomerActivitySuggestionJobStatus.COMPLETED.value,
            expired.public_id: CustomerActivitySuggestionJobStatus.RETRY_PENDING.value,
        }
    )
    monkeypatch.setattr("app.tasks.customer_opportunity_suggestion_recovery.SessionLocal", session_factory)
    monkeypatch.setattr(
        "app.tasks.customer_opportunity_suggestion_recovery.customer_opportunity_suggestion_job_crud",
        crud,
    )
    monkeypatch.setattr(
        "app.tasks.customer_opportunity_suggestion_recovery.customer_opportunity_suggestion_job_service",
        runner,
    )
    monkeypatch.setattr(
        "app.tasks.customer_opportunity_suggestion_recovery.get_settings",
        lambda: SimpleNamespace(
            CUSTOMER_ACTIVITY_SUGGESTION_JOB_MAX_ATTEMPTS=5,
            CUSTOMER_ACTIVITY_SUGGESTION_JOB_RECOVERY_BATCH_SIZE=20,
        ),
    )

    counts = await CustomerOpportunitySuggestionRecoveryScheduler().recover_once()

    assert counts == {
        "scanned": 2,
        "completed": 1,
        "retry_pending": 1,
        "exhausted": 0,
        "skipped": 0,
        "busy": 0,
        "failed": 0,
    }
    assert {(item.team_id, item.job_public_id) for item in runner.requests} == {
        (1, queued.public_id),
        (2, expired.public_id),
    }

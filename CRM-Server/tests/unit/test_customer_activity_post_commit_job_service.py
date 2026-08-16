"""Behavior tests for durable customer-activity post-commit execution."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.customer_activity_post_commit_job import (
    CustomerActivityPostCommitJob,
    CustomerActivityPostCommitJobStatus,
)
from app.services.customer_activity_post_commit_job_service import (
    CustomerActivityPostCommitJobRequest,
    CustomerActivityPostCommitJobService,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def job_session_factory(monkeypatch):
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[CustomerActivityPostCommitJob.__table__])
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr("app.services.customer_activity_post_commit_job_service.SessionLocal", Session)
    monkeypatch.setattr(
        "app.services.customer_activity_post_commit_job_service.get_settings",
        lambda: SimpleNamespace(
            CUSTOMER_ACTIVITY_POST_COMMIT_LEASE_SECONDS=60,
            CUSTOMER_ACTIVITY_POST_COMMIT_MAX_ATTEMPTS=5,
            CUSTOMER_ACTIVITY_POST_COMMIT_RETRY_BASE_SECONDS=1,
        ),
    )
    yield Session
    engine.dispose()


@pytest.mark.asyncio
async def test_exhausted_job_is_terminal_instead_of_reported_as_busy(job_session_factory):
    session = job_session_factory()
    job = CustomerActivityPostCommitJob(
        public_id="pcj_exhausted",
        team_id=1,
        activity_id=212,
        activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="1",
        status=CustomerActivityPostCommitJobStatus.FAILED,
        attempt_count=5,
        next_attempt_at=None,
        run_id="run-exhausted",
        graph_thread_id="thread-exhausted",
        error_message="provider unavailable",
        created_time=datetime(2026, 8, 14, 10, 0),
        updated_time=datetime(2026, 8, 14, 10, 0),
    )
    session.add(job)
    session.commit()
    session.close()

    result = await CustomerActivityPostCommitJobService().run(
        CustomerActivityPostCommitJobRequest(job_public_id="pcj_exhausted", team_id=1)
    )

    assert result["execution_status"] == "RETRIES_EXHAUSTED"
    assert result["retryable"] is False
    assert result["busy"] is False
    session = job_session_factory()
    persisted = session.query(CustomerActivityPostCommitJob).filter_by(public_id="pcj_exhausted").one()
    assert persisted.status == CustomerActivityPostCommitJobStatus.EXHAUSTED
    assert persisted.result_json == result
    assert persisted.finished_at is not None
    session.close()


@pytest.mark.asyncio
async def test_job_passes_persisted_activity_revision_to_workflow(job_session_factory, monkeypatch):
    session = job_session_factory()
    session.add(
        CustomerActivityPostCommitJob(
            public_id="pcj_revision_contract",
            team_id=1,
            activity_id=212,
            activity_revision=7,
            trigger_type="ACTIVITY_UPDATED_DETERMINISTIC",
            actor_id="2",
            status=CustomerActivityPostCommitJobStatus.QUEUED,
            attempt_count=0,
            run_id="run-revision-contract",
            graph_thread_id="thread-revision-contract",
            created_time=datetime(2026, 8, 14, 10, 0),
            updated_time=datetime(2026, 8, 14, 10, 0),
        )
    )
    session.commit()
    session.close()

    monkeypatch.setattr(
        "app.services.customer_activity_post_commit_job_service.customer_activity_crud.get_by_id",
        lambda db, activity_id, team_id: SimpleNamespace(
            id=activity_id,
            team_id=team_id,
            post_commit_revision=7,
        ),
    )
    captured = {}

    async def _run_workflow(**kwargs):
        captured.update(kwargs)
        return {
            "post_commit": {
                "needs_user_confirmation": False,
                "confirmation_case_public_ids": [],
            }
        }

    monkeypatch.setattr(
        "app.services.customer_activity_post_commit_job_service.customer_activity_post_commit_workflow.run",
        _run_workflow,
    )

    result = await CustomerActivityPostCommitJobService().run(
        CustomerActivityPostCommitJobRequest(job_public_id="pcj_revision_contract", team_id=1)
    )

    assert captured == {
        "activity_id": 212,
        "team_id": 1,
        "expected_activity_revision": 7,
        "trigger_type": "ACTIVITY_UPDATED_DETERMINISTIC",
        "actor_id": "2",
        "run_id": "run-revision-contract",
        "thread_id": "thread-revision-contract",
    }
    assert result["success"] is True


@pytest.mark.asyncio
async def test_last_crashing_attempt_is_persisted_and_returned_as_exhausted(job_session_factory, monkeypatch):
    session = job_session_factory()
    session.add(
        CustomerActivityPostCommitJob(
            public_id="pcj_last_attempt",
            team_id=1,
            activity_id=213,
            activity_revision=1,
            trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
            actor_id="1",
            status=CustomerActivityPostCommitJobStatus.FAILED,
            attempt_count=4,
            next_attempt_at=None,
            run_id="run-last-attempt",
            graph_thread_id="thread-last-attempt",
            error_message="previous failure",
            created_time=datetime(2026, 8, 14, 10, 0),
            updated_time=datetime(2026, 8, 14, 10, 0),
        )
    )
    session.commit()
    session.close()

    monkeypatch.setattr(
        "app.services.customer_activity_post_commit_job_service.customer_activity_crud.get_by_id",
        lambda db, activity_id, team_id: SimpleNamespace(id=activity_id, team_id=team_id, post_commit_revision=1),
    )

    async def _crash(**kwargs):
        raise RuntimeError("matcher unavailable")

    monkeypatch.setattr(
        "app.services.customer_activity_post_commit_job_service.customer_activity_post_commit_workflow.run",
        _crash,
    )

    result = await CustomerActivityPostCommitJobService().run(
        CustomerActivityPostCommitJobRequest(job_public_id="pcj_last_attempt", team_id=1)
    )

    assert result["execution_status"] == "RETRIES_EXHAUSTED"
    assert result["retryable"] is False
    assert result["error"] == "matcher unavailable"
    session = job_session_factory()
    persisted = session.query(CustomerActivityPostCommitJob).filter_by(public_id="pcj_last_attempt").one()
    assert persisted.status == CustomerActivityPostCommitJobStatus.EXHAUSTED
    assert persisted.attempt_count == 5
    assert persisted.result_json == result
    session.close()


@pytest.mark.asyncio
async def test_last_workflow_error_attempt_becomes_terminal_immediately(job_session_factory, monkeypatch):
    session = job_session_factory()
    session.add(
        CustomerActivityPostCommitJob(
            public_id="pcj_workflow_error",
            team_id=1,
            activity_id=214,
            activity_revision=1,
            trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
            actor_id="1",
            status=CustomerActivityPostCommitJobStatus.FAILED,
            attempt_count=4,
            next_attempt_at=None,
            run_id="run-workflow-error",
            graph_thread_id="thread-workflow-error",
            error_message="previous failure",
            created_time=datetime(2026, 8, 14, 10, 0),
            updated_time=datetime(2026, 8, 14, 10, 0),
        )
    )
    session.commit()
    session.close()

    monkeypatch.setattr(
        "app.services.customer_activity_post_commit_job_service.customer_activity_crud.get_by_id",
        lambda db, activity_id, team_id: SimpleNamespace(id=activity_id, team_id=team_id, post_commit_revision=1),
    )

    async def _workflow_error(**kwargs):
        return {
            "error_message": "projection failed",
            "post_commit": {"needs_user_confirmation": False, "confirmation_case_public_ids": []},
        }

    monkeypatch.setattr(
        "app.services.customer_activity_post_commit_job_service.customer_activity_post_commit_workflow.run",
        _workflow_error,
    )

    result = await CustomerActivityPostCommitJobService().run(
        CustomerActivityPostCommitJobRequest(job_public_id="pcj_workflow_error", team_id=1)
    )

    assert result["execution_status"] == "RETRIES_EXHAUSTED"
    assert result["retryable"] is False
    assert result["error"] == "projection failed"
    assert result["post_commit"] == {"needs_user_confirmation": False, "confirmation_case_public_ids": []}
    session = job_session_factory()
    persisted = session.query(CustomerActivityPostCommitJob).filter_by(public_id="pcj_workflow_error").one()
    assert persisted.status == CustomerActivityPostCommitJobStatus.EXHAUSTED
    assert persisted.result_json == result
    session.close()


def test_recovery_scan_includes_legacy_exhausted_rows_for_terminalization(job_session_factory):
    from datetime import timedelta

    from app.crud.customer_activity_post_commit_job import customer_activity_post_commit_job_crud

    session = job_session_factory()
    session.add(
        CustomerActivityPostCommitJob(
            public_id="pcj_legacy_exhausted",
            team_id=1,
            activity_id=215,
            activity_revision=1,
            trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
            actor_id="1",
            status=CustomerActivityPostCommitJobStatus.FAILED,
            attempt_count=5,
            next_attempt_at=datetime(2026, 8, 15, 10, 0),
            run_id="run-legacy-exhausted",
            graph_thread_id="thread-legacy-exhausted",
            error_message="legacy exhausted failure",
            created_time=datetime(2026, 8, 14, 10, 0),
            updated_time=datetime(2026, 8, 14, 10, 0),
        )
    )
    session.commit()

    rows = customer_activity_post_commit_job_crud.list_system_recovery_candidates(
        session,
        max_attempts=5,
        limit=10,
        now=datetime(2026, 8, 14, 12, 0) + timedelta(seconds=1),
    )

    assert [(row.team_id, row.job_public_id) for row in rows] == [(1, "pcj_legacy_exhausted")]
    session.close()

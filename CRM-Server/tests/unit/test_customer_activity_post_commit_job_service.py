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


@pytest.mark.asyncio
async def test_completed_job_projects_bound_async_operation(monkeypatch):
    from app.models.agent import AgentSession
    from app.models.agent_async_operation import AgentAsyncOperation, AgentAsyncOperationEvent
    from app.services.agent.async_operation_service import AgentAsyncOperationService

    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(
        engine,
        tables=[
            CustomerActivityPostCommitJob.__table__,
            AgentSession.__table__,
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
        ],
    )
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
    session = Session()
    session.add(AgentSession(id=3, session_key="session-3", team_id=1, user_id=2, title="跟进会话"))
    session.add(
        CustomerActivityPostCommitJob(
            public_id="pcj_project_complete",
            team_id=1,
            activity_id=241,
            activity_revision=1,
            trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
            actor_id="2",
            status=CustomerActivityPostCommitJobStatus.QUEUED,
            attempt_count=0,
            run_id="run-project-complete",
            graph_thread_id="thread-project-complete",
            created_time=datetime(2026, 8, 18, 10, 0),
            updated_time=datetime(2026, 8, 18, 10, 0),
        )
    )
    AgentAsyncOperationService().ensure_scheduled(
        session,
        operation_key="customer-activity-post-commit:pcj_project_complete",
        request_id="pcj_project_complete",
        team_id=1,
        user_id=2,
        session_id=3,
        source_user_message_id=None,
        operation_type="customer_activity_post_commit",
        resource_type="customer_activity",
        resource_id=241,
        summary="跟进已记录，任务对账处理中",
    )
    session.commit()
    session.close()

    monkeypatch.setattr(
        "app.services.customer_activity_post_commit_job_service.customer_activity_crud.get_by_id",
        lambda db, activity_id, team_id: SimpleNamespace(
            id=activity_id,
            team_id=team_id,
            post_commit_revision=1,
        ),
    )

    async def _run_workflow(**kwargs):
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
        CustomerActivityPostCommitJobRequest(job_public_id="pcj_project_complete", team_id=1)
    )

    assert result["success"] is True
    session = Session()
    operation = session.query(AgentAsyncOperation).one()
    assert operation.status == "SUCCEEDED"
    assert operation.request_id == "pcj_project_complete"
    session.close()
    engine.dispose()


@pytest.mark.asyncio
async def test_superseded_job_does_not_complete_operation_until_successor_finishes(monkeypatch):
    from app.models.agent import AgentSession
    from app.models.agent_async_operation import AgentAsyncOperation, AgentAsyncOperationEvent
    from app.services.agent.async_operation_service import AgentAsyncOperationService

    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(
        engine,
        tables=[
            CustomerActivityPostCommitJob.__table__,
            AgentSession.__table__,
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
        ],
    )
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
    session = Session()
    session.add(AgentSession(id=3, session_key="session-3", team_id=1, user_id=2, title="跟进会话"))
    session.add(
        CustomerActivityPostCommitJob(
            public_id="pcj_superseded",
            team_id=1,
            activity_id=241,
            activity_revision=1,
            trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
            actor_id="2",
            status=CustomerActivityPostCommitJobStatus.QUEUED,
            attempt_count=0,
            run_id="run-superseded",
            graph_thread_id="thread-superseded",
            created_time=datetime(2026, 8, 18, 10, 0),
            updated_time=datetime(2026, 8, 18, 10, 0),
        )
    )
    session.add(
        CustomerActivityPostCommitJob(
            public_id="pcj_successor",
            team_id=1,
            activity_id=241,
            activity_revision=2,
            trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
            actor_id="2",
            status=CustomerActivityPostCommitJobStatus.QUEUED,
            attempt_count=0,
            run_id="run-successor",
            graph_thread_id="thread-successor",
            created_time=datetime(2026, 8, 18, 10, 1),
            updated_time=datetime(2026, 8, 18, 10, 1),
        )
    )
    AgentAsyncOperationService().ensure_scheduled(
        session,
        operation_key="customer-activity-post-commit:pcj_superseded",
        request_id="pcj_superseded",
        team_id=1,
        user_id=2,
        session_id=3,
        source_user_message_id=None,
        operation_type="customer_activity_post_commit",
        resource_type="customer_activity",
        resource_id=241,
        summary="跟进已记录，任务对账处理中",
    )
    session.commit()
    session.close()

    monkeypatch.setattr(
        "app.services.customer_activity_post_commit_job_service.customer_activity_crud.get_by_id",
        lambda db, activity_id, team_id: SimpleNamespace(
            id=activity_id,
            team_id=team_id,
            post_commit_revision=2,
        ),
    )

    async def _run_workflow(**kwargs):
        return {
            "match_result": {"decision": "ASK_CONFIRMATION"},
            "post_commit": {
                "needs_user_confirmation": True,
                "confirmation_case_public_ids": ["fcc_001"],
            },
        }

    monkeypatch.setattr(
        "app.services.customer_activity_post_commit_job_service.customer_activity_post_commit_workflow.run",
        _run_workflow,
    )

    superseded_result = await CustomerActivityPostCommitJobService().run(
        CustomerActivityPostCommitJobRequest(job_public_id="pcj_superseded", team_id=1)
    )
    session = Session()
    operation = session.query(AgentAsyncOperation).one()
    assert superseded_result["skip_reason"] == "SUPERSEDED_ACTIVITY_REVISION"
    assert operation.status != "SUCCEEDED"
    session.close()

    successor_result = await CustomerActivityPostCommitJobService().run(
        CustomerActivityPostCommitJobRequest(job_public_id="pcj_successor", team_id=1)
    )
    session = Session()
    operation = session.query(AgentAsyncOperation).one()
    assert successor_result["success"] is True
    assert operation.status == "SUCCEEDED"
    assert (operation.result_json or {}).get("post_commit", {}).get("needs_user_confirmation") is True
    session.close()
    engine.dispose()

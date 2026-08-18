"""Projection tests for customer-activity post-commit Agent operations."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.agent import AgentSession
from app.models.agent_async_operation import AgentAsyncOperation, AgentAsyncOperationEvent
from app.models.customer_activity_post_commit_job import (
    CustomerActivityPostCommitJob,
    CustomerActivityPostCommitJobStatus,
)
from app.services.agent.async_operation_service import AgentAsyncOperationService
from app.services.customer_activity_post_commit_operation_projector import (
    CustomerActivityPostCommitOperationProjector,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AgentSession.__table__,
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
            CustomerActivityPostCommitJob.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    session.add(AgentSession(id=3, session_key="session-3", team_id=1, user_id=2, title="跟进会话"))
    session.commit()
    return engine, session


def _job(status: str, **overrides) -> CustomerActivityPostCommitJob:
    values = {
        "public_id": "pcj_async_001",
        "team_id": 1,
        "activity_id": 241,
        "activity_revision": 1,
        "trigger_type": "ACTIVITY_CREATED_DETERMINISTIC",
        "actor_id": "2",
        "status": status,
        "run_id": "run-async-001",
        "graph_thread_id": "thread-async-001",
        "created_time": datetime(2026, 8, 18, 10, 0),
        "updated_time": datetime(2026, 8, 18, 10, 0),
        "result_json": {"success": True, "activity_id": 241},
    }
    values.update(overrides)
    return CustomerActivityPostCommitJob(**values)


def test_project_job_without_bound_operation_returns_none():
    engine, db = _session()
    try:
        job = _job(CustomerActivityPostCommitJobStatus.COMPLETED)
        db.add(job)
        db.commit()

        projected = CustomerActivityPostCommitOperationProjector().project_job(db, job)

        assert projected is None
        assert db.query(AgentAsyncOperation).count() == 0
    finally:
        db.close()
        engine.dispose()


def test_project_completed_job_marks_bound_operation_succeeded():
    engine, db = _session()
    operations = AgentAsyncOperationService()
    try:
        operation = operations.ensure_scheduled(
            db,
            operation_key="customer-activity-post-commit:pcj_async_001",
            request_id="pcj_async_001",
            team_id=1,
            user_id=2,
            session_id=3,
            source_user_message_id=None,
            operation_type="customer_activity_post_commit",
            resource_type="customer_activity",
            resource_id=241,
            summary="跟进已记录，任务对账处理中",
        )
        job = _job(CustomerActivityPostCommitJobStatus.COMPLETED)
        db.add(job)
        db.commit()

        projected = CustomerActivityPostCommitOperationProjector().project_job(db, job)
        db.commit()

        assert projected is not None
        assert projected.id == operation.id
        assert projected.status == "SUCCEEDED"
        assert projected.request_id == "pcj_async_001"
        assert "完成" in (projected.summary or "")
    finally:
        db.close()
        engine.dispose()


def test_project_running_job_marks_queued_operation_running():
    engine, db = _session()
    operations = AgentAsyncOperationService()
    try:
        operations.ensure_scheduled(
            db,
            operation_key="customer-activity-post-commit:pcj_async_001",
            request_id="pcj_async_001",
            team_id=1,
            user_id=2,
            session_id=3,
            source_user_message_id=None,
            operation_type="customer_activity_post_commit",
            resource_type="customer_activity",
            resource_id=241,
            summary="跟进已记录，任务对账处理中",
        )
        job = _job(CustomerActivityPostCommitJobStatus.RUNNING)
        db.add(job)
        db.commit()

        projected = CustomerActivityPostCommitOperationProjector().project_job(db, job)
        db.commit()

        assert projected is not None
        assert projected.status == "RUNNING"
    finally:
        db.close()
        engine.dispose()


def _bind_operation(db, *, request_id: str, activity_id: int = 241):
    return AgentAsyncOperationService().ensure_scheduled(
        db,
        operation_key=f"customer-activity-post-commit:{request_id}",
        request_id=request_id,
        team_id=1,
        user_id=2,
        session_id=3,
        source_user_message_id=None,
        operation_type="customer_activity_post_commit",
        resource_type="customer_activity",
        resource_id=activity_id,
        summary="跟进已记录，任务对账处理中",
    )


def test_superseded_job_does_not_complete_bound_operation():
    engine, db = _session()
    try:
        _bind_operation(db, request_id="pcj_async_001")
        job = _job(
            CustomerActivityPostCommitJobStatus.SKIPPED,
            result_json={
                "success": True,
                "activity_id": 241,
                "skip_reason": "SUPERSEDED_ACTIVITY_REVISION",
            },
        )
        db.add(job)
        db.commit()

        projected = CustomerActivityPostCommitOperationProjector().project_job(db, job)
        db.commit()

        assert projected is not None
        assert projected.status != "SUCCEEDED"
        assert "完成" not in (projected.summary or "")
        assert projected.request_id == "pcj_async_001"
    finally:
        db.close()
        engine.dispose()


def test_successor_job_projects_operation_bound_to_superseded_job():
    engine, db = _session()
    try:
        _bind_operation(db, request_id="pcj_async_001")
        superseded = _job(
            CustomerActivityPostCommitJobStatus.SKIPPED,
            result_json={
                "success": True,
                "activity_id": 241,
                "skip_reason": "SUPERSEDED_ACTIVITY_REVISION",
            },
        )
        successor = _job(
            CustomerActivityPostCommitJobStatus.COMPLETED,
            public_id="pcj_async_002",
            activity_revision=2,
            run_id="run-async-002",
            graph_thread_id="thread-async-002",
            result_json={
                "success": True,
                "activity_id": 241,
                "match_result": {"decision": "ASK_CONFIRMATION"},
                "post_commit": {"needs_user_confirmation": True},
            },
        )
        db.add_all([superseded, successor])
        db.commit()

        projected = CustomerActivityPostCommitOperationProjector().project_job(db, successor)
        db.commit()

        assert projected is not None
        assert projected.id == db.query(AgentAsyncOperation).one().id
        assert projected.status == "SUCCEEDED"
        assert "完成" in (projected.summary or "")
        assert (projected.result_json or {}).get("post_commit", {}).get("needs_user_confirmation") is True
    finally:
        db.close()
        engine.dispose()


def test_project_request_follows_latest_job_after_supersede():
    engine, db = _session()
    try:
        _bind_operation(db, request_id="pcj_async_001")
        superseded = _job(
            CustomerActivityPostCommitJobStatus.SKIPPED,
            result_json={
                "success": True,
                "activity_id": 241,
                "skip_reason": "SUPERSEDED_ACTIVITY_REVISION",
            },
        )
        successor = _job(
            CustomerActivityPostCommitJobStatus.COMPLETED,
            public_id="pcj_async_002",
            activity_revision=2,
            run_id="run-async-002",
            graph_thread_id="thread-async-002",
            result_json={
                "success": True,
                "activity_id": 241,
                "match_result": {"decision": "COMPLETE"},
            },
        )
        db.add_all([superseded, successor])
        db.commit()

        projected = CustomerActivityPostCommitOperationProjector().project_request(
            db,
            team_id=1,
            request_id="pcj_async_001",
        )
        db.commit()

        assert projected is not None
        assert projected.status == "SUCCEEDED"
        assert (projected.result_json or {}).get("match_result", {}).get("decision") == "COMPLETE"
    finally:
        db.close()
        engine.dispose()


def test_activity_not_found_skip_still_completes_operation():
    engine, db = _session()
    try:
        _bind_operation(db, request_id="pcj_async_001")
        job = _job(
            CustomerActivityPostCommitJobStatus.SKIPPED,
            result_json={
                "success": True,
                "activity_id": 241,
                "skip_reason": "ACTIVITY_NOT_FOUND",
            },
        )
        db.add(job)
        db.commit()

        projected = CustomerActivityPostCommitOperationProjector().project_job(db, job)
        db.commit()

        assert projected is not None
        assert projected.status == "SUCCEEDED"
    finally:
        db.close()
        engine.dispose()

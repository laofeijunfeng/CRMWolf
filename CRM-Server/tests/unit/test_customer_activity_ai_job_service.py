"""Durability tests for customer-activity AI job persistence."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.crud.customer_activity_ai_job import CustomerActivityAIJobCRUD
from app.models.customer_activity_ai_job import CustomerActivityAIJob
from app.services.customer_activity_ai_job_service import (
    CustomerActivityAIJobRequest,
    CustomerActivityAIJobService,
)
from app.services.customer_activity_contracts import CustomerActivityAIJobStatus


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
    Base.metadata.create_all(engine, tables=[CustomerActivityAIJob.__table__])
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


def test_enqueue_is_idempotent_for_activity_revision(db_session):
    service = CustomerActivityAIJobService(job_crud=CustomerActivityAIJobCRUD())
    activity = SimpleNamespace(id=212, team_id=1, activity_revision=1, submission_source="FORM")

    first = service.enqueue_in_transaction(db_session, activity=activity)
    second = service.enqueue_in_transaction(db_session, activity=activity)
    db_session.commit()

    assert first == second
    assert db_session.query(CustomerActivityAIJob).count() == 1
    persisted = db_session.query(CustomerActivityAIJob).one()
    assert persisted.status == CustomerActivityAIJobStatus.QUEUED.value
    assert persisted.activity_id == 212
    assert persisted.activity_revision == 1


def test_completion_requires_the_running_lease_owner(db_session):
    crud = CustomerActivityAIJobCRUD()
    service = CustomerActivityAIJobService(job_crud=crud)
    request = service.enqueue_in_transaction(
        db_session,
        activity=SimpleNamespace(id=212, team_id=1, activity_revision=1, submission_source="FORM"),
    )
    job = crud.get_by_public_id(
        db_session,
        team_id=1,
        public_id=request.job_public_id,
    )
    assert job is not None
    job.status = CustomerActivityAIJobStatus.RUNNING.value
    job.lease_token = "lease-owner"
    job.lease_expires_at = datetime(2026, 9, 2, 12, 0)
    db_session.flush()

    with pytest.raises(RuntimeError, match="租约已失效"):
        service.mark_completed_in_transaction(
            db_session,
            request=request,
            lease_token="stale-lease",
            result_json={"activity_id": 212},
        )

    service.mark_completed_in_transaction(
        db_session,
        request=request,
        lease_token="lease-owner",
        result_json={"activity_id": 212, "activity_revision": 2},
    )
    db_session.commit()

    persisted = crud.get_by_public_id(
        db_session,
        team_id=1,
        public_id=request.job_public_id,
    )
    assert persisted is not None
    assert persisted.status == CustomerActivityAIJobStatus.COMPLETED.value
    assert persisted.result_json == {"activity_id": 212, "activity_revision": 2}
    assert persisted.lease_token is None
    assert persisted.finished_at is not None


def test_claim_is_exclusive_until_lease_expires(db_session):
    crud = CustomerActivityAIJobCRUD()
    job = crud.enqueue(
        db_session,
        team_id=1,
        activity_id=300,
        activity_revision=1,
        submission_source="FORM",
    )
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
    crud = CustomerActivityAIJobCRUD()
    job = crud.enqueue(
        db_session,
        team_id=1,
        activity_id=301,
        activity_revision=1,
        submission_source="FORM",
    )
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


def test_recovery_scan_only_returns_due_or_expired_jobs(db_session):
    crud = CustomerActivityAIJobCRUD()
    due = crud.enqueue(
        db_session,
        team_id=1,
        activity_id=302,
        activity_revision=1,
        submission_source="FORM",
    )
    future = crud.enqueue(
        db_session,
        team_id=1,
        activity_id=303,
        activity_revision=1,
        submission_source="FORM",
    )
    future.status = CustomerActivityAIJobStatus.RETRY_PENDING.value
    future.next_attempt_at = datetime(2026, 9, 2, 11, 0)
    db_session.commit()

    candidates = crud.list_system_recovery_candidates(
        db_session,
        max_attempts=5,
        limit=20,
        now=datetime(2026, 9, 2, 10, 0),
    )

    assert [item.job_public_id for item in candidates] == [due.public_id]


@pytest.mark.asyncio
async def test_deleted_activity_is_marked_skipped_without_running_llm(db_session, monkeypatch):
    crud = CustomerActivityAIJobCRUD()
    job = crud.enqueue(
        db_session,
        team_id=1,
        activity_id=304,
        activity_revision=1,
        submission_source="FORM",
    )
    session_factory = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr("app.services.customer_activity_ai_job_service.SessionLocal", session_factory)
    monkeypatch.setattr(
        "app.services.customer_activity_ai_job_service.get_settings",
        lambda: SimpleNamespace(
            CUSTOMER_ACTIVITY_AI_JOB_LEASE_SECONDS=60,
            CUSTOMER_ACTIVITY_AI_JOB_MAX_ATTEMPTS=5,
            CUSTOMER_ACTIVITY_AI_JOB_RETRY_BASE_SECONDS=1,
        ),
    )
    monkeypatch.setattr(
        "app.services.customer_activity_ai_job_service.customer_activity_crud.get_by_id",
        lambda db, activity_id, team_id: None,
    )

    result = await CustomerActivityAIJobService(job_crud=crud).run(
        CustomerActivityAIJobRequest(job_public_id=job.public_id, team_id=1)
    )

    assert result.execution_status == CustomerActivityAIJobStatus.SKIPPED.value
    assert result.skip_reason == "SOURCE_ACTIVITY_DELETED"
    db_session.expire_all()
    persisted = crud.get_by_public_id(db_session, team_id=1, public_id=job.public_id)
    assert persisted is not None
    assert persisted.status == CustomerActivityAIJobStatus.SKIPPED.value


def _job_settings(*, max_attempts: int = 3):
    return SimpleNamespace(
        CUSTOMER_ACTIVITY_AI_JOB_LEASE_SECONDS=60,
        CUSTOMER_ACTIVITY_AI_JOB_MAX_ATTEMPTS=max_attempts,
        CUSTOMER_ACTIVITY_AI_JOB_RETRY_BASE_SECONDS=1,
    )


def _pending_activity(*, activity_id: int = 400, revision: int = 1):
    return SimpleNamespace(
        id=activity_id,
        team_id=1,
        activity_revision=revision,
        submission_source="FORM",
        processing_status="PENDING",
        processing_error=None,
        effectiveness_status="PENDING",
        effectiveness_error_message=None,
    )


def _final_result(*, score: int = 78):
    from app.services.customer_activity_ai.schemas import CustomerActivityAIFinalResult

    return CustomerActivityAIFinalResult(
        title="确认测试计划",
        content_json={"content": "客户确认本周测试, 下周反馈结果"},
        summary="客户确认测试计划并将在下周反馈",
        next_action="下周确认测试结果",
        next_action_source="AI_EXTRACTED",
        next_follow_time=None,
        next_follow_time_source=None,
        effectiveness_score=score,
        effectiveness_is_valid=score >= 60,
        effectiveness_reason="信息完整且下一步明确",
        effectiveness_detail={"facts": {"score": 18, "max_score": 20}},
    )


class _WorkflowSequence:
    def __init__(self, *outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls = []

    async def compute_finalization(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _CompletingWriteService:
    def __init__(self, job_service: CustomerActivityAIJobService) -> None:
        self.job_service = job_service
        self.finalize_calls = []
        self.kick_calls = []

    def finalize_pending_from_ai(self, db, **kwargs):
        from app.services.customer_activity_write_service import CustomerActivityWriteResult

        self.finalize_calls.append(kwargs)
        finalization = kwargs["finalization"]
        next_revision = kwargs["expected_activity_revision"] + 1
        result_json = {
            "job_public_id": kwargs["ai_job_public_id"],
            "activity_id": kwargs["activity_id"],
            "execution_status": "COMPLETED",
            "success": True,
            "retryable": False,
            "skip_reason": None,
            "error": None,
            "activity_revision": next_revision,
            "effectiveness_score": finalization.effectiveness_score,
        }
        self.job_service.mark_completed_in_transaction(
            db,
            request=CustomerActivityAIJobRequest(
                job_public_id=kwargs["ai_job_public_id"],
                team_id=kwargs["team_id"],
            ),
            lease_token=kwargs["lease_token"],
            result_json=result_json,
        )
        db.commit()
        return CustomerActivityWriteResult(
            activity=SimpleNamespace(id=kwargs["activity_id"]),
            activity_revision=next_revision,
            post_commit_job=None,
            customer_intelligence_request=None,
        )

    def kick(self, result):
        self.kick_calls.append(result)


class _RacingWriteService:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def finalize_pending_from_ai(self, db, **kwargs):
        raise self.error

    def kick(self, result):
        raise AssertionError("skipped finalization must not kick post-commit work")


@pytest.mark.asyncio
async def test_worker_success_finalizes_once_and_terminal_replay_returns_persisted_result(
    db_session,
    monkeypatch,
):
    crud = CustomerActivityAIJobCRUD()
    activity = _pending_activity()
    job = crud.enqueue(
        db_session,
        team_id=1,
        activity_id=activity.id,
        activity_revision=1,
        submission_source="FORM",
    )
    session_factory = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr("app.services.customer_activity_ai_job_service.SessionLocal", session_factory)
    monkeypatch.setattr("app.services.customer_activity_ai_job_service.get_settings", _job_settings)
    monkeypatch.setattr(
        "app.services.customer_activity_ai_job_service.customer_activity_crud.get_by_id",
        lambda db, activity_id, team_id: activity,
    )
    workflow = _WorkflowSequence(_final_result(score=81))
    service = CustomerActivityAIJobService(job_crud=crud, workflow=workflow)
    write_service = _CompletingWriteService(service)
    service._write_service = write_service
    request = CustomerActivityAIJobRequest(job_public_id=job.public_id, team_id=1)

    first = await service.run(request)
    replay = await service.run(request)

    assert first == replay
    assert first.execution_status == CustomerActivityAIJobStatus.COMPLETED.value
    assert first.activity_revision == 2
    assert first.effectiveness_score == 81
    assert len(workflow.calls) == 1
    assert len(write_service.finalize_calls) == 1
    assert len(write_service.kick_calls) == 1
    db_session.expire_all()
    persisted = crud.get_by_public_id(db_session, team_id=1, public_id=job.public_id)
    assert persisted is not None
    assert persisted.status == CustomerActivityAIJobStatus.COMPLETED.value
    assert persisted.attempt_count == 1
    assert persisted.result_json["effectiveness_score"] == 81


@pytest.mark.asyncio
async def test_transient_failure_retries_then_completes_without_duplicate_finalization(
    db_session,
    monkeypatch,
):
    crud = CustomerActivityAIJobCRUD()
    activity = _pending_activity(activity_id=401)
    job = crud.enqueue(
        db_session,
        team_id=1,
        activity_id=activity.id,
        activity_revision=1,
        submission_source="FORM",
    )
    session_factory = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr("app.services.customer_activity_ai_job_service.SessionLocal", session_factory)
    monkeypatch.setattr("app.services.customer_activity_ai_job_service.get_settings", _job_settings)
    monkeypatch.setattr(
        "app.services.customer_activity_ai_job_service.customer_activity_crud.get_by_id",
        lambda db, activity_id, team_id: activity,
    )
    workflow = _WorkflowSequence(RuntimeError("temporary model outage"), _final_result(score=64))
    service = CustomerActivityAIJobService(job_crud=crud, workflow=workflow)
    write_service = _CompletingWriteService(service)
    service._write_service = write_service
    request = CustomerActivityAIJobRequest(job_public_id=job.public_id, team_id=1)

    failed = await service.run(request)
    assert failed.execution_status == CustomerActivityAIJobStatus.RETRY_PENDING.value
    assert failed.retryable is True
    assert activity.processing_status == "PENDING"
    assert activity.effectiveness_status == "PENDING"

    db_session.expire_all()
    persisted = crud.get_by_public_id(db_session, team_id=1, public_id=job.public_id)
    assert persisted is not None
    persisted.next_attempt_at = datetime(2026, 9, 1, 9, 0)
    db_session.commit()

    recovered = await service.run(request)

    assert recovered.execution_status == CustomerActivityAIJobStatus.COMPLETED.value
    assert recovered.effectiveness_score == 64
    assert len(workflow.calls) == 2
    assert len(write_service.finalize_calls) == 1
    db_session.expire_all()
    persisted = crud.get_by_public_id(db_session, team_id=1, public_id=job.public_id)
    assert persisted is not None
    assert persisted.status == CustomerActivityAIJobStatus.COMPLETED.value
    assert persisted.attempt_count == 2


@pytest.mark.asyncio
async def test_max_attempt_failure_keeps_source_activity_and_projects_failed_status(
    db_session,
    monkeypatch,
):
    crud = CustomerActivityAIJobCRUD()
    activity = _pending_activity(activity_id=402)
    job = crud.enqueue(
        db_session,
        team_id=1,
        activity_id=activity.id,
        activity_revision=1,
        submission_source="FORM",
    )
    session_factory = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr("app.services.customer_activity_ai_job_service.SessionLocal", session_factory)
    monkeypatch.setattr(
        "app.services.customer_activity_ai_job_service.get_settings",
        lambda: _job_settings(max_attempts=1),
    )
    monkeypatch.setattr(
        "app.services.customer_activity_ai_job_service.customer_activity_crud.get_by_id",
        lambda db, activity_id, team_id: activity,
    )
    service = CustomerActivityAIJobService(
        job_crud=crud,
        workflow=_WorkflowSequence(RuntimeError("permanent model outage")),
    )

    result = await service.run(CustomerActivityAIJobRequest(job_public_id=job.public_id, team_id=1))

    assert result.execution_status == CustomerActivityAIJobStatus.EXHAUSTED.value
    assert result.success is False
    assert result.retryable is False
    assert activity.processing_status == "FAILED"
    assert activity.effectiveness_status == "FAILED"
    db_session.expire_all()
    persisted = crud.get_by_public_id(db_session, team_id=1, public_id=job.public_id)
    assert persisted is not None
    assert persisted.status == CustomerActivityAIJobStatus.EXHAUSTED.value
    assert persisted.attempt_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_type", "skip_reason"),
    [
        ("deleted", "SOURCE_ACTIVITY_DELETED"),
        ("revision", "SUPERSEDED_ACTIVITY_REVISION"),
    ],
)
async def test_finalization_race_is_skipped_after_compute_without_retry(
    db_session,
    monkeypatch,
    error_type,
    skip_reason,
):
    from app.services.customer_activity_write_service import (
        CustomerActivityRevisionSupersededError,
        CustomerActivitySourceDeletedError,
    )

    crud = CustomerActivityAIJobCRUD()
    activity = _pending_activity(activity_id=403)
    job = crud.enqueue(
        db_session,
        team_id=1,
        activity_id=activity.id,
        activity_revision=1,
        submission_source="FORM",
    )
    session_factory = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr("app.services.customer_activity_ai_job_service.SessionLocal", session_factory)
    monkeypatch.setattr("app.services.customer_activity_ai_job_service.get_settings", _job_settings)
    monkeypatch.setattr(
        "app.services.customer_activity_ai_job_service.customer_activity_crud.get_by_id",
        lambda db, activity_id, team_id: activity,
    )
    race_error = (
        CustomerActivitySourceDeletedError("客户活动不存在")
        if error_type == "deleted"
        else CustomerActivityRevisionSupersededError("客户活动修订号已变化")
    )
    service = CustomerActivityAIJobService(
        job_crud=crud,
        workflow=_WorkflowSequence(_final_result()),
        write_service=_RacingWriteService(race_error),
    )

    result = await service.run(CustomerActivityAIJobRequest(job_public_id=job.public_id, team_id=1))

    assert result.execution_status == CustomerActivityAIJobStatus.SKIPPED.value
    assert result.skip_reason == skip_reason
    assert result.retryable is False
    db_session.expire_all()
    persisted = crud.get_by_public_id(db_session, team_id=1, public_id=job.public_id)
    assert persisted is not None
    assert persisted.status == CustomerActivityAIJobStatus.SKIPPED.value
    assert persisted.next_attempt_at is None

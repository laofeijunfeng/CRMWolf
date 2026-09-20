from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.services.agent.customer_initial_enrichment_graph import CustomerInitialEnrichmentResult
from app.services.customer_enrichment_contracts import (
    CustomerEnrichmentDecision,
    CustomerEnrichmentJobRequest,
)
from app.services.customer_enrichment_inference_service import CustomerEnrichmentInferenceError
from app.services.customer_enrichment_job_service import CustomerEnrichmentJobService
from app.services.customer_enrichment_write_service import CustomerEnrichmentWriteResult
from app.utils.time import business_now


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.pending_customer_write = False
        self.persisted_customer_write = False
        self.closed = False

    def commit(self) -> None:
        self.commits += 1
        if self.pending_customer_write:
            self.persisted_customer_write = True
            self.pending_customer_write = False

    def rollback(self) -> None:
        self.rollbacks += 1
        self.pending_customer_write = False

    def close(self) -> None:
        self.closed = True

    def add(self, _value) -> None:
        return None


class FakeSessionFactory:
    def __init__(self) -> None:
        self.sessions: list[FakeSession] = []

    def __call__(self) -> FakeSession:
        session = FakeSession()
        self.sessions.append(session)
        return session


class FakeJobCrud:
    def __init__(
        self,
        *,
        existing=None,
        claimed=...,
        mark_completed_result=...,
        mark_retry_result=...,
        mark_exhausted_result=...,
    ) -> None:
        self.existing = existing or _job()
        self.claimed = self.existing if claimed is ... else claimed
        self.mark_completed_result = self.existing if mark_completed_result is ... else mark_completed_result
        self.mark_retry_result = self.existing if mark_retry_result is ... else mark_retry_result
        self.mark_exhausted_result = self.existing if mark_exhausted_result is ... else mark_exhausted_result
        self.retry_next_attempt_at_delta: timedelta | None = None
        self.calls: list[str] = []
        self.lease_valid_for_write = True
    def get_by_public_id(self, db, *, team_id, public_id, for_update=False):
        self.calls.append("get")
        if not self.lease_valid_for_write and self.calls.count("get") > 1:
            self.existing.lease_token = "replacement"
        return self.existing

    def claim_for_execution(
        self,
        db,
        *,
        team_id,
        public_id,
        lease_token,
        lease_expires_at,
        now,
        commit,
    ):
        self.calls.append("claim")
        if self.claimed is not None:
            self.claimed.status = "RUNNING"
            self.claimed.attempt_count = int(self.claimed.attempt_count or 0) + 1
            self.claimed.lease_expires_at = lease_expires_at
            self.claimed.lease_token = lease_token
        return self.claimed


    def mark_completed_if_lease_owner(
        self,
        db,
        *,
        team_id,
        public_id,
        lease_token,
        result_json,
        skipped=False,
        now,
        commit,
    ):
        self.calls.append("mark_skipped" if skipped else "mark_completed")
        if self.mark_completed_result is not None:
            self.mark_completed_result.status = "SKIPPED" if skipped else "COMPLETED"
            self.mark_completed_result.result_json = result_json
            self.mark_completed_result.first_attempt_finished_at = (
                self.mark_completed_result.first_attempt_finished_at or now
            )
        return self.mark_completed_result

    def mark_retry_pending_if_lease_owner(
        self,
        db,
        *,
        team_id,
        public_id,
        lease_token,
        error_message,
        next_attempt_at,
        result_json,
        now,
        commit,
    ):
        self.calls.append("mark_retry")
        self.retry_next_attempt_at_delta = next_attempt_at - now
        if self.mark_retry_result is not None:
            self.mark_retry_result.status = "RETRY_PENDING"
            self.mark_retry_result.result_json = result_json
            self.mark_retry_result.first_attempt_finished_at = (
                self.mark_retry_result.first_attempt_finished_at or now
            )
        return self.mark_retry_result

    def mark_exhausted_if_lease_owner(
        self,
        db,
        *,
        team_id,
        public_id,
        lease_token,
        error_message,
        result_json,
        now,
        commit,
    ):
        self.calls.append("mark_exhausted")
        if self.mark_exhausted_result is not None:
            self.mark_exhausted_result.status = "EXHAUSTED"
            self.mark_exhausted_result.result_json = result_json
            self.mark_exhausted_result.first_attempt_finished_at = (
                self.mark_exhausted_result.first_attempt_finished_at or now
            )
        return self.mark_exhausted_result


class FakeWorkflow:
    def __init__(self, *, result=None, error: Exception | None = None) -> None:
        self.result = result or _decision_result()
        self.error = error
        self.calls: list[object] = []

    async def run(self, request):
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self.result


class FakeWriteService:
    def __init__(self, *, result=None) -> None:
        self.result = result or CustomerEnrichmentWriteResult(
            outcome="APPLIED", applied_fields=("industry",), customer_version=5
        )
        self.calls: list[dict[str, object]] = []

    def apply(self, db, **kwargs):
        self.calls.append({"db": db, **kwargs})
        if self.result.outcome == "APPLIED":
            if kwargs.get("commit", True):
                db.persisted_customer_write = True
            else:
                db.pending_customer_write = True
        return self.result


class FakeCompletionPort:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def on_first_attempt_finished(self, job) -> None:
        self.calls.append("first_attempt")

    def on_terminal_success(self, job, result) -> None:
        self.calls.append("terminal_success")


def _job(
    *,
    status: str = "QUEUED",
    result_json=None,
    attempt_count: int = 1,
    lease_token: str | None = None,
    lease_expires_at=None,
):
    return SimpleNamespace(
        public_id="cej_job-1",
        team_id=2,
        customer_id=101,
        plan_version="customer-initial-v1",
        requested_fields_json=["industry"],
        status=status,
        result_json=result_json,
        attempt_count=attempt_count,
        max_attempts=3,
        lease_token=lease_token,
        lease_expires_at=lease_expires_at,
        run_id="run-1",
        graph_thread_id="customer-enrichment:2:101:customer-initial-v1",
        first_attempt_finished_at=None,
        error_message=None,
    )


def _job_request() -> CustomerEnrichmentJobRequest:
    return CustomerEnrichmentJobRequest(team_id=2, job_public_id="cej_job-1")


def _decision_result() -> CustomerInitialEnrichmentResult:
    return CustomerInitialEnrichmentResult(
        customer_id=101,
        expected_version=4,
        decisions=(
            CustomerEnrichmentDecision(field="industry", value="internet_saas", reason="软件研发"),
        ),
    )


def _service(
    *,
    crud: FakeJobCrud | None = None,
    workflow_result=None,
    workflow_error: Exception | None = None,
    write_result=None,
    attempt_count: int = 1,
    mark_completed_result=...,
):
    job = _job(attempt_count=max(0, attempt_count - 1))
    crud = crud or FakeJobCrud(existing=job, mark_completed_result=mark_completed_result)
    session_factory = FakeSessionFactory()
    service = CustomerEnrichmentJobService(
        job_crud=crud,
        workflow=FakeWorkflow(result=workflow_result, error=workflow_error),
        write_service=FakeWriteService(result=write_result),
        completion_port=FakeCompletionPort(),
        session_factory=session_factory,
    )
    service.session_factory_fake = session_factory
    return service


@pytest.mark.asyncio
async def test_terminal_job_returns_persisted_result_without_compute():
    crud = FakeJobCrud(
        existing=_job(
            status="COMPLETED",
            result_json={"execution_status": "COMPLETED", "success": True},
        )
    )
    service = _service(crud=crud)

    result = await service.run(_job_request())

    assert result.execution_status == "COMPLETED"
    assert service.workflow.calls == []


@pytest.mark.asyncio
async def test_busy_job_does_not_compute():
    crud = FakeJobCrud(existing=_job(status="QUEUED"), claimed=None)
    service = _service(crud=crud)

    result = await service.run(_job_request())

    assert result.execution_status == "BUSY"
    assert service.workflow.calls == []

@pytest.mark.asyncio
async def test_live_final_attempt_returns_busy_without_clearing_lease():
    live_until = business_now() + timedelta(minutes=5)
    job = _job(
        status="RUNNING",
        attempt_count=3,
        lease_token="current-owner",
        lease_expires_at=live_until,
    )
    crud = FakeJobCrud(existing=job)
    service = _service(crud=crud)

    result = await service.run(_job_request())

    assert result.execution_status == "BUSY"
    assert job.status == "RUNNING"
    assert job.lease_token == "current-owner"
    assert job.lease_expires_at == live_until
    assert service.workflow.calls == []
    assert crud.calls == ["get"]
    assert service.session_factory_fake.sessions[0].rollbacks == 1


@pytest.mark.asyncio
async def test_expired_final_attempt_becomes_exhausted():
    job = _job(
        status="RUNNING",
        attempt_count=3,
        lease_token="expired-owner",
        lease_expires_at=business_now() - timedelta(seconds=1),
    )
    crud = FakeJobCrud(existing=job)
    service = _service(crud=crud)

    result = await service.run(_job_request())

    assert result.execution_status == "EXHAUSTED"
    assert job.status == "EXHAUSTED"
    assert job.lease_token is None
    assert job.lease_expires_at is None
    assert service.workflow.calls == []


@pytest.mark.asyncio
async def test_success_completes_job_and_calls_completion_port_in_order():
    service = _service(
        workflow_result=_decision_result(),
        write_result=CustomerEnrichmentWriteResult(
            outcome="APPLIED", applied_fields=("industry",), customer_version=5
        ),
    )

    result = await service.run(_job_request())

    assert result.execution_status == "COMPLETED"
    assert result.applied_fields == ["industry"]
    assert service.completion_port.calls == ["first_attempt", "terminal_success"]
    assert len(service.session_factory_fake.sessions) == 2
    assert all(session.closed for session in service.session_factory_fake.sessions)
    mutation_session = service.session_factory_fake.sessions[1]
    assert service.write_service.calls[0]["commit"] is False
    assert mutation_session.commits == 1
    assert mutation_session.persisted_customer_write is True
    assert mutation_session.pending_customer_write is False


@pytest.mark.asyncio
async def test_first_failure_retries_and_releases_profile_gate():
    service = _service(workflow_error=CustomerEnrichmentInferenceError("timeout"), attempt_count=1)

    result = await service.run(_job_request())

    assert result.execution_status == "RETRY_PENDING"
    assert result.retryable is True
    assert service.completion_port.calls == ["first_attempt"]
    assert service.job_crud.retry_next_attempt_at_delta == timedelta(seconds=60)


@pytest.mark.asyncio
async def test_second_failure_retries_after_five_minutes():
    service = _service(workflow_error=CustomerEnrichmentInferenceError("timeout"), attempt_count=2)

    result = await service.run(_job_request())

    assert result.execution_status == "RETRY_PENDING"
    assert service.job_crud.retry_next_attempt_at_delta == timedelta(seconds=300)


@pytest.mark.asyncio
async def test_third_failure_exhausts():
    service = _service(workflow_error=CustomerEnrichmentInferenceError("timeout"), attempt_count=3)

    result = await service.run(_job_request())

    assert result.execution_status == "EXHAUSTED"
    assert result.retryable is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("write_result", "expected_status"),
    [
        (CustomerEnrichmentWriteResult(outcome="SKIPPED", reason="FIELD_ALREADY_FILLED"), "SKIPPED"),
        (
            CustomerEnrichmentWriteResult(
                outcome="RETRY", reason="CUSTOMER_CHANGED_DURING_ENRICHMENT"
            ),
            "RETRY_PENDING",
        ),
    ],
)
async def test_write_outcome_controls_terminal_state(write_result, expected_status):
    service = _service(workflow_result=_decision_result(), write_result=write_result)

    result = await service.run(_job_request())

    assert result.execution_status == expected_status


@pytest.mark.asyncio
async def test_stale_lease_before_write_does_not_mutate_customer():
    service = _service(workflow_result=_decision_result())
    service.job_crud.lease_valid_for_write = False

    result = await service.run(_job_request())

    assert result.execution_status == "BUSY"
    assert service.write_service.calls == []
    assert service.completion_port.calls == []


@pytest.mark.asyncio
async def test_stale_lease_cannot_finalize():
    service = _service(workflow_result=_decision_result(), mark_completed_result=None)

    result = await service.run(_job_request())

    assert result.execution_status == "BUSY"
    assert result.success is False
    assert service.completion_port.calls == []


@pytest.mark.asyncio
async def test_stale_finalization_rolls_back_pending_customer_write():
    service = _service(workflow_result=_decision_result(), mark_completed_result=None)

    result = await service.run(_job_request())

    mutation_session = service.session_factory_fake.sessions[1]
    assert result.execution_status == "BUSY"
    assert service.write_service.calls[0]["commit"] is False
    assert mutation_session.rollbacks == 1
    assert mutation_session.pending_customer_write is False
    assert mutation_session.persisted_customer_write is False

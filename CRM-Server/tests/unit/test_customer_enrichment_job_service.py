from __future__ import annotations

import asyncio
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
from app.services.customer_enrichment_profile_coordinator import CustomerEnrichmentProfileCoordinator
from app.services.customer_enrichment_write_service import CustomerEnrichmentWriteResult
from app.services.customer_intelligence_refresh_service import (
    CustomerIntelligenceCommittedEventRequest,
)
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
            outcome="APPLIED",
            applied_fields=("industry",),
            decision_reasons={"industry": "软件研发"},
            customer_version=5,
        ),
    )

    result = await service.run(_job_request())

    assert result.execution_status == "COMPLETED"
    assert result.applied_fields == ["industry"]
    assert result.decision_reasons == {"industry": "软件研发"}
    assert service.job_crud.existing.result_json["decision_reasons"] == {
        "industry": "软件研发"
    }
    assert service.completion_port.calls == ["first_attempt", "terminal_success"]
    assert len(service.session_factory_fake.sessions) == 2
    assert all(session.closed for session in service.session_factory_fake.sessions)
    mutation_session = service.session_factory_fake.sessions[1]
    assert service.write_service.calls[0]["commit"] is False
    assert mutation_session.commits == 1
    assert mutation_session.persisted_customer_write is True
    assert mutation_session.pending_customer_write is False


def test_persisted_legacy_result_defaults_decision_reasons():
    job = _job(
        status="COMPLETED",
        result_json={
            "job_public_id": "cej_job-1",
            "customer_id": 101,
            "execution_status": "COMPLETED",
            "success": True,
            "applied_fields": ["industry"],
        },
    )

    result = CustomerEnrichmentJobService._persisted_result(job)

    assert result.decision_reasons == {}

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
async def test_deleted_customer_is_skipped_once_without_retry_or_terminal_refresh():
    from app.services.customer_enrichment_context_service import CustomerEnrichmentSkip

    service = _service(
        workflow_error=CustomerEnrichmentSkip("CUSTOMER_NOT_FOUND"),
        attempt_count=1,
    )

    result = await service.run(_job_request())

    assert result.execution_status == "SKIPPED"
    assert result.skip_reason == "CUSTOMER_NOT_FOUND"
    assert result.retryable is False
    assert service.job_crud.calls.count("mark_skipped") == 1
    assert "mark_retry" not in service.job_crud.calls
    assert "mark_exhausted" not in service.job_crud.calls
    assert service.write_service.calls == []
    assert service.completion_port.calls == ["first_attempt"]

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
async def test_delete_after_model_skip_does_not_retry_or_request_terminal_refresh():
    service = _service(
        workflow_result=_decision_result(),
        write_result=CustomerEnrichmentWriteResult(
            outcome="SKIPPED",
            reason="CUSTOMER_NOT_FOUND",
        ),
    )

    result = await service.run(_job_request())

    assert result.execution_status == "SKIPPED"
    assert result.skip_reason == "CUSTOMER_NOT_FOUND"
    assert service.job_crud.calls.count("mark_skipped") == 1
    assert "mark_retry" not in service.job_crud.calls
    assert "mark_exhausted" not in service.job_crud.calls
    assert service.completion_port.calls == ["first_attempt"]



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


class CoordinatorSession(FakeSession):
    def __init__(self, locked_job) -> None:
        super().__init__()
        self.locked_job = locked_job
        self.flushed = 0

    def flush(self) -> None:
        self.flushed += 1


class CoordinatorSessionFactory:
    def __init__(self, locked_job) -> None:
        self.locked_job = locked_job
        self.sessions = []

    def __call__(self):
        session = CoordinatorSession(self.locked_job)
        self.sessions.append(session)
        return session


class CoordinatorJobCrud:
    def __init__(self, locked_job) -> None:
        self.locked_job = locked_job
        self.calls = []

    def get_by_public_id(self, db, *, team_id, public_id, for_update=False):
        self.calls.append((team_id, public_id, for_update))
        return self.locked_job


class CoordinatorRunService:
    def __init__(self, released_sequences) -> None:
        self.released_sequences = list(released_sequences)
        self.calls = []

    def release_deferred_for_customer(self, db, *, team_id, customer_id):
        self.calls.append((team_id, customer_id))
        return self.released_sequences.pop(0) if self.released_sequences else []

    def cancel_deferred_for_customer(self, db, *, team_id, customer_id, reason, now=None):
        del db, reason, now
        self.calls.append(("cancel", team_id, customer_id))
        return self.released_sequences.pop(0) if self.released_sequences else []


class CoordinatorRefreshService:
    def __init__(self) -> None:
        self.calls = []
        self.kick_requests = []

    async def run_due_retries(self, *, team_id, limit):
        self.calls.append((team_id, limit))
        return {"success": True}

    def kick_committed_event_refresh(self, request):
        self.kick_requests.append(request)


class CoordinatorPublicationService:
    def __init__(self, results=None) -> None:
        self.events = []
        self.results = list(results or [])
        self.after_commit_calls = []

    def persist_in_transaction_request(self, db, *, event, scope):
        self.events.append((db, event, scope))
        result = self.results.pop(0) if self.results else SimpleNamespace(
            request_id=f"business-event-{event.trigger_type}-{event.event_key[:16]}",
            scheduled=True,
            schedule_error=None,
        )
        if isinstance(result, Exception):
            raise result
        return CustomerIntelligenceCommittedEventRequest(
            request_id=result.request_id,
            event=event,
            scope=scope,
            scheduled=result.scheduled,
            kick_required=False,
            schedule_error=result.schedule_error,
        )

    def enqueue_after_commit(self, *, event, scope):
        self.after_commit_calls.append((event, scope))
        raise AssertionError("coordinator must not open a second-session enqueue")


class CoordinatorEventService:
    def __init__(self) -> None:
        self.calls = []

    def business_object_changed(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            event_key=f"enrichment-{kwargs['change_id']}",
            trigger_type=kwargs["trigger_type"],
            team_id=kwargs["team_id"],
            customer_id=kwargs["customer_id"],
        )


def _coordinator(*, job, released_sequences, publication_results=None):
    session_factory = CoordinatorSessionFactory(job)
    coordinator = CustomerEnrichmentProfileCoordinator(
        job_crud=CoordinatorJobCrud(job),
        run_service=CoordinatorRunService(released_sequences),
        refresh_service=CoordinatorRefreshService(),
        event_service=CoordinatorEventService(),
        publication_service=CoordinatorPublicationService(publication_results),
        session_factory=session_factory,
    )
    coordinator.session_factory_fake = session_factory
    return coordinator


@pytest.mark.asyncio
async def test_deleted_customer_first_attempt_cancels_deferred_profile_without_kick_or_receipt():
    job = _job(
        status="SKIPPED",
        result_json={
            "execution_status": "SKIPPED",
            "success": True,
            "skip_reason": "CUSTOMER_NOT_FOUND",
        },
    )
    job.profile_refresh_request_id = None
    job.profile_refresh_enqueued_at = None
    coordinator = _coordinator(job=job, released_sequences=[[41]])

    coordinator.on_first_attempt_finished(job)
    await asyncio.sleep(0)

    assert coordinator.run_service.calls == [("cancel", 2, 101)]
    assert coordinator.refresh_service.calls == []
    assert job.profile_refresh_request_id is None
    assert job.profile_refresh_enqueued_at is None


@pytest.mark.asyncio
async def test_first_attempt_callback_releases_deferred_profile_runs_and_kicks_due_worker():
    job = _job(status="RETRY_PENDING")
    coordinator = _coordinator(job=job, released_sequences=[[31, 32]])

    coordinator.on_first_attempt_finished(job)
    await asyncio.sleep(0)

    assert coordinator.run_service.calls == [(2, 101)]
    assert coordinator.refresh_service.calls == [(2, 2)]
    assert coordinator.session_factory_fake.sessions[0].commits == 1
    assert coordinator.session_factory_fake.sessions[0].closed is True


@pytest.mark.asyncio
async def test_terminal_success_records_released_run_without_enqueuing_duplicate_refresh():
    job = _job(status="COMPLETED")
    job.profile_refresh_request_id = None
    job.profile_refresh_enqueued_at = None
    coordinator = _coordinator(job=job, released_sequences=[[41]])

    coordinator.on_first_attempt_finished(job)
    coordinator.on_terminal_success(job, SimpleNamespace())
    await asyncio.sleep(0)

    assert job.profile_refresh_request_id == "released:41"
    assert job.profile_refresh_enqueued_at is not None
    assert coordinator.publication_service.events == []
    assert coordinator.publication_service.after_commit_calls == []


def test_terminal_success_retries_after_durable_publication_failure():
    job = _job(status="COMPLETED")
    job.profile_refresh_request_id = None
    job.profile_refresh_enqueued_at = None
    coordinator = _coordinator(
        job=job,
        released_sequences=[[], []],
        publication_results=[
            SimpleNamespace(
                request_id="durable-request-1",
                scheduled=False,
                schedule_error="store down",
            ),
            SimpleNamespace(
                request_id="durable-request-2",
                scheduled=True,
                schedule_error=None,
            ),
        ],
    )

    coordinator.on_terminal_success(job, SimpleNamespace())

    assert job.profile_refresh_request_id is None
    assert job.profile_refresh_enqueued_at is None

    coordinator.on_terminal_success(job, SimpleNamespace())

    assert job.profile_refresh_request_id == "durable-request-2"
    assert job.profile_refresh_enqueued_at is not None
    assert len(coordinator.publication_service.events) == 2
    assert coordinator.publication_service.after_commit_calls == []


def test_terminal_success_persists_durable_request_receipt_after_enqueue(monkeypatch):
    job = _job(status="COMPLETED")
    job.profile_refresh_request_id = None
    job.profile_refresh_enqueued_at = None
    occurred_at = business_now()
    enqueued_at = occurred_at + timedelta(seconds=1)
    times = iter((occurred_at, enqueued_at))
    monkeypatch.setattr(
        "app.services.customer_enrichment_profile_coordinator.business_now",
        lambda: next(times),
    )
    coordinator = _coordinator(
        job=job,
        released_sequences=[[]],
        publication_results=[
            SimpleNamespace(
                request_id="durable-request-exact",
                scheduled=True,
                schedule_error=None,
            )
        ],
    )
    original_persist = coordinator.publication_service.persist_in_transaction_request

    def assert_receipt_is_empty_during_persist(db, *, event, scope):
        assert db is coordinator.session_factory_fake.sessions[0]
        assert db.commits == 0
        assert job.profile_refresh_request_id is None
        assert job.profile_refresh_enqueued_at is None
        return original_persist(db, event=event, scope=scope)

    coordinator.publication_service.persist_in_transaction_request = (
        assert_receipt_is_empty_during_persist
    )

    coordinator.on_terminal_success(job, SimpleNamespace())

    assert job.profile_refresh_request_id == "durable-request-exact"
    assert job.profile_refresh_enqueued_at == enqueued_at
    assert coordinator.session_factory_fake.sessions[0].commits == 1
    assert coordinator.publication_service.after_commit_calls == []
    assert [request.request_id for request in coordinator.refresh_service.kick_requests] == [
        "durable-request-exact"
    ]
    assert coordinator.refresh_service.kick_requests[0].kick_required is True
    assert coordinator.event_service.calls[0]["occurred_at"] == occurred_at


def test_terminal_success_enqueue_exception_is_caught_by_callback_boundary(caplog):
    job = _job(status="COMPLETED")
    job.profile_refresh_request_id = None
    job.profile_refresh_enqueued_at = None
    coordinator = _coordinator(
        job=job,
        released_sequences=[[]],
        publication_results=[RuntimeError("store exploded")],
    )
    service = _service()
    service.completion_port = coordinator

    with caplog.at_level("ERROR"):
        service._call_terminal_success(job, SimpleNamespace())

    assert job.profile_refresh_request_id is None
    assert job.profile_refresh_enqueued_at is None
    assert "客户补全终态成功回调失败" in caplog.text
    assert "store exploded" in caplog.text


def test_retry_kick_done_callback_logs_returned_exception(caplog):
    error = RuntimeError("retry kick exploded")
    task = SimpleNamespace(cancelled=lambda: False, exception=lambda: error)

    with caplog.at_level("ERROR"):
        CustomerEnrichmentProfileCoordinator._consume_task_exception(task)

    assert "唤醒已释放客户档案任务失败" in caplog.text
    assert caplog.records[-1].exc_info[1] is error


def test_terminal_success_enqueues_once_and_persists_receipt_when_nothing_is_deferred():
    job = _job(status="COMPLETED")
    job.profile_refresh_request_id = None
    job.profile_refresh_enqueued_at = None
    coordinator = _coordinator(job=job, released_sequences=[[], []])

    coordinator.on_terminal_success(job, SimpleNamespace())
    coordinator.on_terminal_success(job, SimpleNamespace())

    assert job.profile_refresh_request_id == (
        "business-event-customer_business_object_updated-enrichment-initi"
    )
    assert job.profile_refresh_enqueued_at is not None
    assert len(coordinator.publication_service.events) == 1
    _db, event, scope = coordinator.publication_service.events[0]
    assert scope == "full"
    assert event.trigger_type == "customer_business_object_updated"
    assert coordinator.event_service.calls[0]["payload"] == {
        "change_origin": "CUSTOMER_INITIAL_ENRICHMENT"
    }

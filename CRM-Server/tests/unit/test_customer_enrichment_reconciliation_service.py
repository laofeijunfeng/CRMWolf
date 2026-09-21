from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.crud.customer_enrichment_job import CustomerEnrichmentJobCRUD
from app.models.customer import Customer
from app.models.customer_enrichment_job import CustomerEnrichmentJob
from app.models.customer_intelligence_run import (
    CustomerIntelligenceRun,
    CustomerIntelligenceRunStatus,
)
from app.services.customer_enrichment_contracts import (
    CustomerEnrichmentJobStatus,
    CustomerEnrichmentPurpose,
)
from app.services.customer_enrichment_plan import ACTIVE_CUSTOMER_ENRICHMENT_PLAN, CustomerEnrichmentPlan
from app.services.customer_enrichment_profile_coordinator import CustomerEnrichmentProfileCoordinator
from app.services.customer_enrichment_reconciliation_service import (
    CustomerEnrichmentReconciliationService,
)
from app.services.customer_intelligence_run_service import CustomerIntelligenceRunService
from app.utils.time import business_now


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerEnrichmentJob.__table__,
            CustomerIntelligenceRun.__table__,
        ],
    )
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


def _customer(db, *, team_id: int = 2, industry: str | None = None) -> Customer:
    customer = Customer(
        team_id=team_id,
        account_name=f"customer-{team_id}-{db.query(Customer).count()}",
        city="Shanghai",
        industry=industry,
        creator_id="9",
    )
    db.add(customer)
    db.flush()
    return customer


def _job(
    db,
    customer: Customer,
    *,
    status: str = CustomerEnrichmentJobStatus.QUEUED.value,
    first_attempt_finished: bool = False,
    gate_expired: bool = False,
    receipt: str | None = None,
    purpose: str = CustomerEnrichmentPurpose.INITIAL_CREATION.value,
) -> CustomerEnrichmentJob:
    now = business_now()
    job = CustomerEnrichmentJob(
        team_id=customer.team_id,
        customer_id=customer.id,
        purpose=purpose,
        plan_version=ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version,
        requested_fields_json=list(ACTIVE_CUSTOMER_ENRICHMENT_PLAN.fields),
        status=status,
        available_at=now,
        profile_gate_deadline_at=now - timedelta(seconds=1) if gate_expired else now + timedelta(hours=1),
        attempt_count=1 if first_attempt_finished else 0,
        max_attempts=3,
        run_id=f"run-{customer.id}",
        graph_thread_id=f"thread-{customer.id}",
        first_attempt_finished_at=now if first_attempt_finished else None,
        profile_refresh_request_id=receipt,
    )
    db.add(job)
    db.flush()
    return job


def _profile_run(
    db,
    customer: Customer,
    *,
    sequence: int,
    status: str = CustomerIntelligenceRunStatus.PENDING,
    deferred: bool = True,
) -> CustomerIntelligenceRun:
    now = business_now()
    run = CustomerIntelligenceRun(
        run_key=f"run-key-{customer.id}-{sequence}",
        request_id=f"request-{customer.id}-{sequence}",
        event_key=f"event-{customer.id}-{sequence}",
        tenant_id=customer.team_id,
        team_id=customer.team_id,
        customer_id=customer.id,
        trigger_type="customer_created",
        scope="full",
        status=status,
        attempt_count=0,
        max_attempts=3,
        not_before_at=now if deferred else None,
    )
    db.add(run)
    db.flush()
    return run


def _orphan_job(db, *, team_id: int, customer_id: int) -> CustomerEnrichmentJob:
    now = business_now()
    job = CustomerEnrichmentJob(
        team_id=team_id,
        customer_id=customer_id,
        purpose=CustomerEnrichmentPurpose.INITIAL_CREATION.value,
        plan_version=ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version,
        requested_fields_json=list(ACTIVE_CUSTOMER_ENRICHMENT_PLAN.fields),
        status=CustomerEnrichmentJobStatus.SKIPPED.value,
        available_at=now,
        profile_gate_deadline_at=now,
        attempt_count=1,
        max_attempts=3,
        run_id=f"orphan-run-{team_id}-{customer_id}",
        graph_thread_id=f"orphan-thread-{team_id}-{customer_id}",
        first_attempt_finished_at=now,
        result_json={"skip_reason": "CUSTOMER_NOT_FOUND"},
    )
    db.add(job)
    db.flush()
    return job


def _orphan_profile_run(
    db,
    *,
    team_id: int,
    customer_id: int,
    sequence: int,
    deferred: bool = True,
) -> CustomerIntelligenceRun:
    run = CustomerIntelligenceRun(
        run_key=f"orphan-run-key-{team_id}-{customer_id}-{sequence}",
        request_id=f"orphan-request-{team_id}-{customer_id}-{sequence}",
        event_key=f"orphan-event-{team_id}-{customer_id}-{sequence}",
        tenant_id=team_id,
        team_id=team_id,
        customer_id=customer_id,
        trigger_type="customer_created",
        scope="full",
        status=CustomerIntelligenceRunStatus.PENDING,
        attempt_count=0,
        max_attempts=3,
        not_before_at=business_now() if deferred else None,
        next_retry_at=business_now(),
        lease_token="stale-lease",
        lease_expires_at=business_now() + timedelta(minutes=5),
    )
    db.add(run)
    db.flush()
    return run


class FakeRunService:
    def __init__(self, *, releases: dict[int, list[int]] | None = None) -> None:
        self.releases = releases or {}
        self.calls: list[dict[str, int]] = []

    def release_deferred_for_customer(self, db, **kwargs):
        del db
        self.calls.append(kwargs)
        return list(self.releases.get(kwargs["customer_id"], []))


class FakeProfileCoordinator:
    def __init__(self, *, fail_customer_id: int | None = None) -> None:
        self.fail_customer_id = fail_customer_id
        self.calls: list[int] = []

    def repair_missing_profile_receipt(self, db, *, job, now=None):
        del now
        self.calls.append(int(job.customer_id))
        if int(job.customer_id) == self.fail_customer_id:
            raise RuntimeError("repair failed")
        job.profile_refresh_request_id = f"refresh-{job.public_id}"
        db.add(job)
        db.flush()
        return True

def _service(*, job_crud=None, run_service=None, coordinator=None, plan=None):
    return CustomerEnrichmentReconciliationService(
        job_crud=job_crud,
        run_service=run_service or FakeRunService(),
        profile_coordinator=coordinator or FakeProfileCoordinator(),
        plan=plan,
        max_attempts=3,
    )

class RecordingJobCRUD(CustomerEnrichmentJobCRUD):
    def __init__(self) -> None:
        self.timeout_calls = []

    def record_profile_gate_timeout_if_unset(self, db, **kwargs):
        self.timeout_calls.append(kwargs)
        return super().record_profile_gate_timeout_if_unset(db, **kwargs)


def test_reconciliation_creates_missing_job_as_historical_and_is_idempotent(db_session):
    customer = _customer(db_session)
    service = _service()

    first = service.reconcile_once(db_session, team_id=2, limit=50, dry_run=False)
    second = service.reconcile_once(db_session, team_id=2, limit=50, dry_run=False)

    assert first.jobs_created == 1
    assert second.jobs_created == 0
    job = db_session.query(CustomerEnrichmentJob).one()
    assert job.customer_id == customer.id
    assert job.purpose == CustomerEnrichmentPurpose.HISTORICAL_BACKFILL.value
    assert job.plan_version == ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version



def test_reconciliation_creates_one_job_for_blank_industry_and_skips_filled(db_session):
    blank = _customer(db_session, industry="  \t")
    _customer(db_session, industry="software")
    service = _service()

    first = service.reconcile_once(db_session, team_id=2, limit=50, dry_run=False)
    second = service.reconcile_once(db_session, team_id=2, limit=50, dry_run=False)

    assert first.jobs_created == 1
    assert second.jobs_created == 0
    assert db_session.query(CustomerEnrichmentJob).one().customer_id == blank.id


@pytest.mark.parametrize("dry_run", [False, True])
def test_reconciliation_disabled_backfill_plan_does_not_create_historical_jobs(
    db_session,
    dry_run,
):
    _customer(db_session)
    plan = CustomerEnrichmentPlan(
        version="customer-initial-disabled",
        fields=("industry",),
        backfill_enabled=False,
    )
    service = _service(plan=plan)

    result = service.reconcile_once(db_session, team_id=2, limit=50, dry_run=dry_run)

    assert result.jobs_created == 0
    assert db_session.query(CustomerEnrichmentJob).count() == 0

def test_reconciliation_releases_expired_gate_and_repairs_missing_refresh_receipt(db_session):
    gated_customer = _customer(db_session)
    terminal_customer = _customer(db_session, industry="software")
    _job(db_session, gated_customer, gate_expired=True)
    terminal = _job(
        db_session,
        terminal_customer,
        status=CustomerEnrichmentJobStatus.COMPLETED.value,
        first_attempt_finished=True,
    )
    run_service = FakeRunService(releases={int(gated_customer.id): [91]})
    job_crud = RecordingJobCRUD()
    coordinator = FakeProfileCoordinator()
    service = _service(job_crud=job_crud, run_service=run_service, coordinator=coordinator)

    result = service.reconcile_once(db_session, team_id=2, limit=50, dry_run=False)

    assert result.gates_released == 1
    assert result.refreshes_repaired == 1
    assert coordinator.calls == [terminal_customer.id]
    assert terminal.profile_refresh_request_id == f"refresh-{terminal.public_id}"
    assert job_crud.timeout_calls == [
        {
            "team_id": int(gated_customer.team_id),
            "customer_id": int(gated_customer.id),
            "plan_version": ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version,
            "timed_out_at": db_session.get(CustomerEnrichmentJob, 1).profile_gate_timed_out_at,
        }
    ]
    assert db_session.get(CustomerEnrichmentJob, 1).profile_gate_timed_out_at is not None


def test_reconciliation_dry_run_does_not_mutate_and_returns_stable_cursor(db_session):
    first = _customer(db_session)
    second = _customer(db_session)
    service = _service()

    result = service.reconcile_once(db_session, team_id=None, limit=1, dry_run=True)

    assert result.scanned == 1
    assert result.jobs_created == 1
    assert result.next_customer_id == first.id
    assert result.dry_run is True
    assert db_session.query(CustomerEnrichmentJob).count() == 0

    next_page = service.reconcile_once(
        db_session,
        team_id=None,
        limit=1,
        after_customer_id=result.next_customer_id,
        dry_run=True,
    )
    assert next_page.next_customer_id == second.id




@pytest.mark.parametrize("deferred_count", [0, 2])
def test_reconciliation_dry_run_counts_exact_releasable_runs_without_updates(
    db_session,
    deferred_count,
):
    customer = _customer(db_session, industry="software")
    _job(db_session, customer, gate_expired=True)
    deferred_runs = [
        _profile_run(db_session, customer, sequence=index)
        for index in range(deferred_count)
    ]
    terminal = _profile_run(
        db_session,
        customer,
        sequence=99,
        status=CustomerIntelligenceRunStatus.SUCCESS,
    )
    service = CustomerEnrichmentReconciliationService(
        run_service=CustomerIntelligenceRunService(),
        profile_coordinator=FakeProfileCoordinator(),
        max_attempts=3,
    )

    result = service.reconcile_once(db_session, team_id=2, limit=50, dry_run=True)

    assert result.gates_released == deferred_count
    assert all(run.not_before_at is not None for run in deferred_runs)
    assert terminal.not_before_at is not None
    assert db_session.query(CustomerEnrichmentJob).one().profile_gate_timed_out_at is None

def test_reconciliation_records_released_run_as_terminal_profile_receipt(db_session):
    customer = _customer(db_session, industry="software")
    job = _job(
        db_session,
        customer,
        status=CustomerEnrichmentJobStatus.COMPLETED.value,
        first_attempt_finished=True,
        gate_expired=True,
    )
    run_service = FakeRunService(releases={int(customer.id): [71]})
    coordinator = FakeProfileCoordinator()
    service = _service(run_service=run_service, coordinator=coordinator)

    result = service.reconcile_once(db_session, team_id=2, limit=50, dry_run=False)

    assert result.gates_released == 1
    assert result.refreshes_repaired == 1
    assert job.profile_refresh_request_id == "released:71"
    assert coordinator.calls == []
    assert job.profile_gate_timed_out_at is None
    assert job.first_attempt_finished_at is not None


@pytest.mark.parametrize("receipt_kind", ["released", "request"])
def test_reconciliation_repairs_receipt_when_target_run_is_absent(db_session, receipt_kind):
    customer = _customer(db_session, industry="software")
    receipt = "released:9999" if receipt_kind == "released" else "missing-request"
    job = _job(
        db_session,
        customer,
        status=CustomerEnrichmentJobStatus.COMPLETED.value,
        first_attempt_finished=True,
        receipt=receipt,
    )
    coordinator = FakeProfileCoordinator()
    service = CustomerEnrichmentReconciliationService(
        run_service=CustomerIntelligenceRunService(),
        profile_coordinator=coordinator,
        max_attempts=3,
    )

    result = service.reconcile_once(db_session, team_id=2, limit=50, dry_run=False)

    assert result.refreshes_repaired == 1
    assert coordinator.calls == [customer.id]
    assert job.profile_refresh_request_id == f"refresh-{job.public_id}"


@pytest.mark.parametrize("receipt_kind", ["released", "request"])
def test_reconciliation_keeps_valid_receipt_target(db_session, receipt_kind):
    customer = _customer(db_session, industry="software")
    run = _profile_run(db_session, customer, sequence=21, deferred=False)
    receipt = f"released:{run.id}" if receipt_kind == "released" else run.request_id
    job = _job(
        db_session,
        customer,
        status=CustomerEnrichmentJobStatus.COMPLETED.value,
        first_attempt_finished=True,
        receipt=receipt,
    )
    coordinator = FakeProfileCoordinator()
    service = CustomerEnrichmentReconciliationService(
        run_service=CustomerIntelligenceRunService(),
        profile_coordinator=coordinator,
        max_attempts=3,
    )

    result = service.reconcile_once(db_session, team_id=2, limit=50, dry_run=False)

    assert result.refreshes_repaired == 0
    assert coordinator.calls == []
    assert job.profile_refresh_request_id == receipt


@pytest.mark.parametrize("mismatch", ["team", "customer"])
def test_reconciliation_rejects_receipt_target_outside_job_scope(db_session, mismatch):
    customer = _customer(db_session, team_id=2, industry="software")
    target_customer = (
        _customer(db_session, team_id=3, industry="software")
        if mismatch == "team"
        else _customer(db_session, team_id=2, industry="software")
    )
    run = _profile_run(db_session, target_customer, sequence=31, deferred=False)
    job = _job(
        db_session,
        customer,
        status=CustomerEnrichmentJobStatus.COMPLETED.value,
        first_attempt_finished=True,
        receipt=f"released:{run.id}",
    )
    coordinator = FakeProfileCoordinator()
    service = CustomerEnrichmentReconciliationService(
        run_service=CustomerIntelligenceRunService(),
        profile_coordinator=coordinator,
        max_attempts=3,
    )

    result = service.reconcile_once(db_session, team_id=2, limit=50, dry_run=False)

    assert result.refreshes_repaired == 1
    assert coordinator.calls == [customer.id]
    assert job.profile_refresh_request_id == f"refresh-{job.public_id}"


def test_reconciliation_dry_run_reports_stale_receipt_without_mutation(db_session):
    customer = _customer(db_session, industry="software")
    job = _job(
        db_session,
        customer,
        status=CustomerEnrichmentJobStatus.COMPLETED.value,
        first_attempt_finished=True,
        receipt="released:9999",
    )
    coordinator = FakeProfileCoordinator()
    service = CustomerEnrichmentReconciliationService(
        run_service=CustomerIntelligenceRunService(),
        profile_coordinator=coordinator,
        max_attempts=3,
    )

    result = service.reconcile_once(db_session, team_id=2, limit=50, dry_run=True)

    assert result.refreshes_repaired == 1
    assert coordinator.calls == []
    assert job.profile_refresh_request_id == "released:9999"


def test_reconciliation_does_not_repair_customer_not_found_skip_receipt(db_session):
    customer = _customer(db_session, industry="software")
    job = _job(
        db_session,
        customer,
        status=CustomerEnrichmentJobStatus.SKIPPED.value,
        first_attempt_finished=True,
    )
    job.result_json = {"skip_reason": "CUSTOMER_NOT_FOUND"}
    coordinator = FakeProfileCoordinator()
    service = CustomerEnrichmentReconciliationService(
        run_service=CustomerIntelligenceRunService(),
        profile_coordinator=coordinator,
        max_attempts=3,
    )

    result = service.reconcile_once(db_session, team_id=2, limit=50, dry_run=False)

    assert result.refreshes_repaired == 0
    assert coordinator.calls == []

def test_reconciliation_does_not_record_timeout_for_historical_job(db_session):
    customer = _customer(db_session, industry="software")
    job = _job(
        db_session,
        customer,
        purpose=CustomerEnrichmentPurpose.HISTORICAL_BACKFILL.value,
        gate_expired=True,
    )
    service = _service(
        run_service=FakeRunService(releases={int(customer.id): [72]}),
        coordinator=FakeProfileCoordinator(),
    )

    result = service.reconcile_once(db_session, team_id=2, limit=50, dry_run=False)

    assert result.gates_released == 1
    assert job.profile_gate_timed_out_at is None


def test_reconciliation_does_not_count_rolled_back_customer_work(db_session):
    _customer(db_session)

    class FailingCRUD:
        def get_by_identity(self, db, **kwargs):
            del db, kwargs
            return None

        def ensure(self, db, **kwargs):
            del db, kwargs
            raise RuntimeError("ensure failed")

    service = CustomerEnrichmentReconciliationService(
        job_crud=FailingCRUD(),
        run_service=FakeRunService(),
        profile_coordinator=FakeProfileCoordinator(),
        max_attempts=3,
    )

    result = service.reconcile_once(db_session, team_id=2, limit=50, dry_run=False)

    assert result.scanned == 1
    assert result.errors == 1
    assert result.jobs_created == 0
    assert db_session.query(CustomerEnrichmentJob).count() == 0

def test_reconciliation_isolates_customer_errors_in_savepoints(db_session):
    failing = _customer(db_session, industry="software")
    healthy = _customer(db_session)
    failed_job = _job(
        db_session,
        failing,
        status=CustomerEnrichmentJobStatus.SKIPPED.value,
        first_attempt_finished=True,
    )
    coordinator = FakeProfileCoordinator(fail_customer_id=int(failing.id))
    service = _service(coordinator=coordinator)

    result = service.reconcile_once(db_session, team_id=2, limit=50, dry_run=False)

    assert result.scanned == 2
    assert result.errors == 1
    assert result.jobs_created == 1
    assert failed_job.profile_refresh_request_id is None
    assert (
        db_session.query(CustomerEnrichmentJob)
        .filter(CustomerEnrichmentJob.customer_id == healthy.id)
        .one()
        .purpose
        == CustomerEnrichmentPurpose.HISTORICAL_BACKFILL.value
    )


def test_profile_coordinator_repairs_receipt_in_caller_transaction(db_session):
    customer = _customer(db_session, industry="software")
    job = _job(
        db_session,
        customer,
        status=CustomerEnrichmentJobStatus.COMPLETED.value,
        first_attempt_finished=True,
    )
    db_session.commit()

    class EventService:
        def business_object_changed(self, **kwargs):
            return SimpleNamespace(**kwargs)

    class PublicationService:
        def persist_in_transaction_request(self, db, *, event, scope):
            del db, event, scope
            return SimpleNamespace(scheduled=True, request_id="durable-refresh-1")

    coordinator = CustomerEnrichmentProfileCoordinator(
        run_service=FakeRunService(),
        event_service=EventService(),
        publication_service=PublicationService(),
    )

    repaired = coordinator.repair_missing_profile_receipt(db_session, job=job)

    assert repaired is True
    assert job.profile_refresh_request_id == "durable-refresh-1"
    assert job.profile_refresh_enqueued_at is not None
    db_session.rollback()
    db_session.expire_all()
    assert (
        db_session.query(CustomerEnrichmentJob)
        .filter(CustomerEnrichmentJob.id == job.id)
        .one()
        .profile_refresh_request_id
        is None
    )


def test_reconciliation_cancels_deferred_profile_runs_for_orphan_customer(db_session):
    _orphan_job(db_session, team_id=2, customer_id=901)
    run = _orphan_profile_run(db_session, team_id=2, customer_id=901, sequence=1)
    service = CustomerEnrichmentReconciliationService(
        run_service=CustomerIntelligenceRunService(),
        profile_coordinator=FakeProfileCoordinator(),
        max_attempts=3,
    )

    result = service.reconcile_once(db_session, team_id=2, limit=10, dry_run=False)

    assert result.gates_cancelled == 1
    db_session.refresh(run)
    assert run.status == CustomerIntelligenceRunStatus.CANCELLED
    assert run.error_message == "CUSTOMER_NOT_FOUND"
    assert run.not_before_at is None
    assert run.next_retry_at is None
    assert run.lease_token is None
    assert run.lease_expires_at is None


def test_reconciliation_dry_run_counts_orphan_cancellations_without_mutation(db_session):
    _orphan_job(db_session, team_id=2, customer_id=902)
    first = _orphan_profile_run(db_session, team_id=2, customer_id=902, sequence=1)
    second = _orphan_profile_run(db_session, team_id=2, customer_id=902, sequence=2)
    service = CustomerEnrichmentReconciliationService(
        run_service=CustomerIntelligenceRunService(),
        profile_coordinator=FakeProfileCoordinator(),
        max_attempts=3,
    )

    result = service.reconcile_once(db_session, team_id=2, limit=10, dry_run=True)

    assert result.gates_cancelled == 2
    assert first.status == CustomerIntelligenceRunStatus.PENDING
    assert second.status == CustomerIntelligenceRunStatus.PENDING
    assert first.not_before_at is not None
    assert second.not_before_at is not None


def test_reconciliation_orphan_cancellation_is_tenant_scoped(db_session):
    _orphan_job(db_session, team_id=2, customer_id=903)
    own = _orphan_profile_run(db_session, team_id=2, customer_id=903, sequence=1)
    _orphan_job(db_session, team_id=3, customer_id=903)
    other = _orphan_profile_run(db_session, team_id=3, customer_id=903, sequence=2)
    service = CustomerEnrichmentReconciliationService(
        run_service=CustomerIntelligenceRunService(),
        profile_coordinator=FakeProfileCoordinator(),
        max_attempts=3,
    )

    result = service.reconcile_once(db_session, team_id=2, limit=10, dry_run=False)

    assert result.gates_cancelled == 1
    assert own.status == CustomerIntelligenceRunStatus.CANCELLED
    assert other.status == CustomerIntelligenceRunStatus.PENDING


def test_clean_orphan_does_not_block_later_dirty_orphan_under_limit(db_session):
    _orphan_job(db_session, team_id=2, customer_id=904)
    _orphan_profile_run(db_session, team_id=2, customer_id=904, sequence=1, deferred=False)
    _orphan_job(db_session, team_id=2, customer_id=905)
    dirty = _orphan_profile_run(db_session, team_id=2, customer_id=905, sequence=2)
    service = CustomerEnrichmentReconciliationService(
        run_service=CustomerIntelligenceRunService(),
        profile_coordinator=FakeProfileCoordinator(),
        max_attempts=3,
    )

    result = service.reconcile_once(db_session, team_id=2, limit=1, dry_run=False)

    assert result.gates_cancelled == 1
    assert dirty.status == CustomerIntelligenceRunStatus.CANCELLED


def test_orphan_dry_run_pages_without_repeats(db_session):
    jobs = []
    for customer_id in (910, 911, 912):
        jobs.append(_orphan_job(db_session, team_id=2, customer_id=customer_id))
        _orphan_profile_run(db_session, team_id=2, customer_id=customer_id, sequence=customer_id)
    service = CustomerEnrichmentReconciliationService(
        run_service=CustomerIntelligenceRunService(),
        profile_coordinator=FakeProfileCoordinator(),
        max_attempts=3,
    )

    first = service.reconcile_once(db_session, team_id=2, limit=2, dry_run=True)
    second = service.reconcile_once(
        db_session,
        team_id=2,
        limit=2,
        after_orphan_job_id=first.next_orphan_job_id,
        dry_run=True,
    )
    third = service.reconcile_once(
        db_session,
        team_id=2,
        limit=2,
        after_orphan_job_id=second.next_orphan_job_id,
        dry_run=True,
    )

    assert first.gates_cancelled == 2
    assert first.next_orphan_job_id == jobs[1].id
    assert second.gates_cancelled == 1
    assert second.next_orphan_job_id == jobs[2].id
    assert third.gates_cancelled == 0
    assert third.next_orphan_job_id is None


def test_erroring_orphan_advances_cursor_to_later_page(db_session):
    first_job = _orphan_job(db_session, team_id=2, customer_id=920)
    _orphan_profile_run(db_session, team_id=2, customer_id=920, sequence=1)
    second_job = _orphan_job(db_session, team_id=2, customer_id=921)
    second_run = _orphan_profile_run(db_session, team_id=2, customer_id=921, sequence=2)

    class FailingFirstRunService(CustomerIntelligenceRunService):
        def cancel_deferred_for_customer(self, db, *, team_id, customer_id, reason, now=None):
            if customer_id == 920:
                raise RuntimeError("cancel failed")
            return super().cancel_deferred_for_customer(
                db,
                team_id=team_id,
                customer_id=customer_id,
                reason=reason,
                now=now,
            )

    service = CustomerEnrichmentReconciliationService(
        run_service=FailingFirstRunService(),
        profile_coordinator=FakeProfileCoordinator(),
        max_attempts=3,
    )

    first = service.reconcile_once(db_session, team_id=2, limit=1, dry_run=False)
    second = service.reconcile_once(
        db_session,
        team_id=2,
        limit=1,
        after_orphan_job_id=first.next_orphan_job_id,
        dry_run=False,
    )

    assert first.errors == 1
    assert first.next_orphan_job_id == first_job.id
    assert second.next_orphan_job_id == second_job.id
    assert second.gates_cancelled == 1
    assert second_run.status == CustomerIntelligenceRunStatus.CANCELLED

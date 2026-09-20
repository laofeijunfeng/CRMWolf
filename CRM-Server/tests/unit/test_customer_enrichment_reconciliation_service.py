from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.customer import Customer
from app.models.customer_enrichment_job import CustomerEnrichmentJob
from app.services.customer_enrichment_contracts import (
    CustomerEnrichmentJobStatus,
    CustomerEnrichmentPurpose,
)
from app.services.customer_enrichment_plan import ACTIVE_CUSTOMER_ENRICHMENT_PLAN
from app.services.customer_enrichment_profile_coordinator import CustomerEnrichmentProfileCoordinator
from app.services.customer_enrichment_reconciliation_service import (
    CustomerEnrichmentReconciliationService,
)
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
        tables=[Customer.__table__, CustomerEnrichmentJob.__table__],
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
) -> CustomerEnrichmentJob:
    now = business_now()
    job = CustomerEnrichmentJob(
        team_id=customer.team_id,
        customer_id=customer.id,
        purpose=CustomerEnrichmentPurpose.INITIAL_CREATION.value,
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


def _service(*, run_service=None, coordinator=None):
    return CustomerEnrichmentReconciliationService(
        run_service=run_service or FakeRunService(),
        profile_coordinator=coordinator or FakeProfileCoordinator(),
        max_attempts=3,
    )


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
    coordinator = FakeProfileCoordinator()
    service = _service(run_service=run_service, coordinator=coordinator)

    result = service.reconcile_once(db_session, team_id=2, limit=50, dry_run=False)

    assert result.gates_released == 1
    assert result.refreshes_repaired == 1
    assert coordinator.calls == [terminal_customer.id]
    assert terminal.profile_refresh_request_id == f"refresh-{terminal.public_id}"


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

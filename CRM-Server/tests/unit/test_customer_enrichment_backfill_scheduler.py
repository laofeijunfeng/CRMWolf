from __future__ import annotations

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.customer import Customer
from app.models.customer_enrichment_job import CustomerEnrichmentJob
from app.models.customer_profile_projection import (
    CustomerProfileCurrent,
    CustomerProfileProjectionVersion,
    CustomerProfilePublicationStatus,
    CustomerProfileStatus,
)
from app.services.customer_enrichment_backfill_service import (
    CustomerEnrichmentBackfillResult,
    CustomerEnrichmentBackfillService,
)
from app.services.customer_enrichment_contracts import CustomerEnrichmentPurpose
from app.services.customer_enrichment_plan import ACTIVE_CUSTOMER_ENRICHMENT_PLAN, CustomerEnrichmentPlan
from app.tasks.customer_enrichment_backfill import CustomerEnrichmentBackfillScheduler
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
            CustomerProfileProjectionVersion.__table__,
            CustomerProfileCurrent.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


def _customer(db, *, team_id: int = 2, industry: str | None = None) -> Customer:
    customer = Customer(
        team_id=team_id,
        account_name=f"客户-{team_id}-{db.query(Customer).count()}",
        industry=industry,
        city="杭州",
        creator_id="user-1",
    )
    db.add(customer)
    db.flush()
    return customer


def _readable_profile(db, customer: Customer) -> None:
    version = CustomerProfileProjectionVersion(
        team_id=customer.team_id,
        customer_id=customer.id,
        schema_version="1",
        profile_version=1,
        publication_status=CustomerProfilePublicationStatus.PUBLISHED,
        current_situation_json={},
        current_journeys_json=[],
        important_changes_json=[],
        long_term_context_json={},
        follow_up_process_json=[],
        recorded_follow_ups_json=[],
        evidence_refs_json=[],
        quality_report_json={},
        source_watermark_json={},
        source_watermark_hash="a" * 64,
        graph_version="test",
        content_hash="b" * 64,
        published_at=business_now(),
    )
    db.add(version)
    db.flush()
    db.add(
        CustomerProfileCurrent(
            team_id=customer.team_id,
            customer_id=customer.id,
            current_profile_version_id=version.id,
            profile_status=CustomerProfileStatus.READY,
            last_successful_version=1,
            last_successful_published_at=version.published_at,
            latest_source_watermark_json={},
        )
    )
    db.flush()


def test_backfill_scans_null_industry_even_when_profile_exists(db_session) -> None:
    customer = _customer(db_session)
    _readable_profile(db_session, customer)
    service = CustomerEnrichmentBackfillService()

    result = service.scan_and_ensure(db_session, limit=20, dry_run=False)

    assert result.scanned == 1
    assert result.eligible == 1
    assert result.scheduled == 1
    assert result.customer_ids == [customer.id]
    job = db_session.query(CustomerEnrichmentJob).one()
    assert job.purpose == CustomerEnrichmentPurpose.HISTORICAL_BACKFILL.value
    assert job.profile_gate_deadline_at is None



def test_backfill_schedules_blank_industry_once_and_skips_filled(db_session) -> None:
    blank = _customer(db_session, industry="\u3000")
    _customer(db_session, industry="software")
    service = CustomerEnrichmentBackfillService()

    first = service.scan_and_ensure(db_session, limit=20, dry_run=False)
    second = service.scan_and_ensure(db_session, limit=20, dry_run=False)

    assert first.customer_ids == [blank.id]
    assert first.scheduled == 1
    assert second.scheduled == 0
    assert db_session.query(CustomerEnrichmentJob).count() == 1


@pytest.mark.parametrize("dry_run", [False, True])
def test_backfill_disabled_plan_scans_and_schedules_nothing(db_session, dry_run) -> None:
    _customer(db_session)
    plan = CustomerEnrichmentPlan(
        version="customer-initial-disabled",
        fields=("industry",),
        backfill_enabled=False,
    )
    service = CustomerEnrichmentBackfillService(plan=plan)

    result = service.scan_and_ensure(db_session, limit=20, dry_run=dry_run)

    assert result.scanned == 0
    assert result.eligible == 0
    assert result.scheduled == 0
    assert result.customer_ids == []
    assert db_session.query(CustomerEnrichmentJob).count() == 0

def test_backfill_skips_existing_industry_and_existing_plan_job(db_session) -> None:
    _customer(db_session, industry="software")
    existing_job_customer = _customer(db_session)
    db_session.add(
        CustomerEnrichmentJob(
            team_id=existing_job_customer.team_id,
            customer_id=existing_job_customer.id,
            purpose=CustomerEnrichmentPurpose.INITIAL_CREATION.value,
            plan_version=ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version,
            requested_fields_json=list(ACTIVE_CUSTOMER_ENRICHMENT_PLAN.fields),
            status="QUEUED",
            available_at=business_now(),
            profile_gate_deadline_at=business_now(),
            attempt_count=0,
            max_attempts=3,
            run_id="existing-run",
            graph_thread_id="existing-thread",
            requeue_count=0,
        )
    )
    db_session.flush()
    service = CustomerEnrichmentBackfillService()

    result = service.scan_and_ensure(db_session, limit=20, dry_run=False)

    assert result.scanned == 0
    assert result.eligible == 0
    assert result.scheduled == 0
    assert db_session.query(CustomerEnrichmentJob).count() == 1


def test_backfill_is_idempotent_and_uses_cursor(db_session) -> None:
    first_customer = _customer(db_session)
    second_customer = _customer(db_session)
    service = CustomerEnrichmentBackfillService()

    first = service.scan_and_ensure(db_session, limit=1, dry_run=False)
    second = service.scan_and_ensure(
        db_session,
        limit=1,
        after_customer_id=first.next_customer_id,
        dry_run=False,
    )
    third = service.scan_and_ensure(db_session, limit=20, dry_run=False)

    assert len(set(first.customer_ids + second.customer_ids)) == 2
    assert first.customer_ids == [first_customer.id]
    assert second.customer_ids == [second_customer.id]
    assert third.scheduled == 0
    assert db_session.query(CustomerEnrichmentJob).count() == 2


def test_backfill_dry_run_has_no_mutations_and_honors_team_filter(db_session) -> None:
    selected = _customer(db_session, team_id=2)
    _customer(db_session, team_id=3)
    service = CustomerEnrichmentBackfillService()

    result = service.scan_and_ensure(db_session, team_id=2, limit=20, dry_run=True)

    assert result.dry_run is True
    assert result.scanned == 1
    assert result.eligible == 1
    assert result.scheduled == 0
    assert result.customer_ids == [selected.id]
    assert db_session.query(CustomerEnrichmentJob).count() == 0


class FakeDB:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class FakeBackfillService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def scan_and_ensure(self, db, **kwargs) -> CustomerEnrichmentBackfillResult:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        dry_run = bool(kwargs["dry_run"])
        return CustomerEnrichmentBackfillResult(
            success=True,
            scanned=1,
            eligible=1,
            scheduled=0 if dry_run else 1,
            skipped=0,
            customer_ids=[11],
            next_customer_id=11,
            dry_run=dry_run,
        )


class FakeRecoveryScheduler:
    def __init__(self) -> None:
        self.calls = 0

    async def recover_once(self):
        self.calls += 1
        return {"scanned": 1}


@pytest.mark.asyncio
async def test_scheduler_commits_normal_run_and_dry_run_does_not_commit() -> None:
    normal_db = FakeDB()
    dry_db = FakeDB()
    sessions = iter([normal_db, dry_db])
    service = FakeBackfillService()
    recovery = FakeRecoveryScheduler()
    scheduler = CustomerEnrichmentBackfillScheduler(
        backfill_service=service,
        recovery_scheduler=recovery,
        session_factory=lambda: next(sessions),
    )

    normal = await scheduler.backfill_once(limit=7, dry_run=False)
    dry = await scheduler.backfill_once(limit=7, dry_run=True)

    assert normal["scheduled"] == 1 and dry["dry_run"] is True
    assert service.calls == [
        {"limit": 7, "dry_run": False},
        {"limit": 7, "dry_run": True},
    ]
    assert normal_db.committed is True
    assert dry_db.committed is False
    assert recovery.calls == 1
    assert normal_db.closed is True and dry_db.closed is True


@pytest.mark.asyncio
async def test_scheduler_rolls_back_and_closes_on_failure() -> None:
    db = FakeDB()
    scheduler = CustomerEnrichmentBackfillScheduler(
        backfill_service=FakeBackfillService(error=RuntimeError("boom")),
        recovery_scheduler=FakeRecoveryScheduler(),
        session_factory=lambda: db,
    )

    with pytest.raises(RuntimeError, match="boom"):
        await scheduler.backfill_once(limit=7)

    assert db.rolled_back is True
    assert db.closed is True

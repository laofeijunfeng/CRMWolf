from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud.customer_enrichment_job import CustomerEnrichmentJobCRUD
from app.models.customer_enrichment_job import CustomerEnrichmentJob
from app.services.customer_enrichment_contracts import (
    CustomerEnrichmentJobStatus,
    CustomerEnrichmentPurpose,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ANN001, ANN003
    return "INTEGER"


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[CustomerEnrichmentJob.__table__])
    return sessionmaker(bind=engine)()


def _ensure(
    crud: CustomerEnrichmentJobCRUD,
    db,
    *,
    customer_id: int = 101,
    purpose: str = CustomerEnrichmentPurpose.INITIAL_CREATION.value,
    available_at: datetime | None = None,
):
    now = datetime(2026, 9, 20, 10, 0, 0)
    return crud.ensure(
        db,
        team_id=2,
        customer_id=customer_id,
        purpose=purpose,
        plan_version="customer-initial-v1",
        requested_fields=["industry"],
        available_at=available_at or now,
        profile_gate_deadline_at=(available_at or now) + timedelta(seconds=30)
        if purpose == CustomerEnrichmentPurpose.INITIAL_CREATION.value
        else None,
        max_attempts=3,
    )


def test_ensure_is_idempotent_for_customer_and_plan():
    db = _session()
    crud = CustomerEnrichmentJobCRUD()
    first = _ensure(crud, db)
    second = _ensure(crud, db, purpose=CustomerEnrichmentPurpose.HISTORICAL_BACKFILL.value)
    assert second.id == first.id
    assert second.purpose == CustomerEnrichmentPurpose.INITIAL_CREATION.value
    assert db.query(CustomerEnrichmentJob).count() == 1


def test_claim_honors_available_at_and_live_lease():
    db = _session()
    crud = CustomerEnrichmentJobCRUD()
    now = datetime(2026, 9, 20, 10, 0, 0)
    job = _ensure(crud, db, available_at=now + timedelta(seconds=5))
    assert crud.claim_for_execution(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="early",
        lease_expires_at=now + timedelta(seconds=120),
        now=now,
    ) is None
    claimed = crud.claim_for_execution(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="owner",
        lease_expires_at=now + timedelta(seconds=125),
        now=now + timedelta(seconds=5),
    )
    assert claimed is not None
    assert claimed.status == CustomerEnrichmentJobStatus.RUNNING.value
    assert claimed.attempt_count == 1
    assert crud.claim_for_execution(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="other",
        lease_expires_at=now + timedelta(seconds=130),
        now=now + timedelta(seconds=10),
    ) is None


def test_running_job_without_lease_token_can_be_reclaimed():
    db = _session()
    crud = CustomerEnrichmentJobCRUD()
    now = datetime(2026, 9, 20, 10, 0, 0)
    job = _ensure(crud, db, available_at=now)
    claimed = crud.claim_for_execution(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="owner",
        lease_expires_at=now + timedelta(seconds=120),
        now=now,
    )
    assert claimed is not None
    claimed.lease_token = None
    db.commit()

    reclaimed = crud.claim_for_execution(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="replacement",
        lease_expires_at=now + timedelta(seconds=130),
        now=now + timedelta(seconds=10),
    )

    assert reclaimed is not None
    assert reclaimed.lease_token == "replacement"
    assert reclaimed.attempt_count == 2


def test_retry_sets_first_attempt_finished_at():
    db = _session()
    crud = CustomerEnrichmentJobCRUD()
    now = datetime(2026, 9, 20, 10, 0, 0)
    job = _ensure(crud, db, available_at=now)
    crud.claim_for_execution(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="owner",
        lease_expires_at=now + timedelta(seconds=120),
        now=now,
    )
    updated = crud.mark_retry_pending_if_lease_owner(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="owner",
        error_message="timeout",
        next_attempt_at=now + timedelta(seconds=60),
        result_json={"first_attempt_outcome": "RETRY_PENDING"},
        now=now + timedelta(seconds=2),
    )
    assert updated is not None
    assert updated.status == CustomerEnrichmentJobStatus.RETRY_PENDING.value
    assert updated.first_attempt_finished_at == now + timedelta(seconds=2)
    assert updated.lease_token is None


def test_completed_lease_owner_clears_lease():
    db = _session()
    crud = CustomerEnrichmentJobCRUD()
    now = datetime(2026, 9, 20, 10, 0, 0)
    job = _ensure(crud, db, available_at=now)
    crud.claim_for_execution(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="owner",
        lease_expires_at=now + timedelta(seconds=120),
        now=now,
    )
    updated = crud.mark_completed_if_lease_owner(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="owner",
        result_json={"applied_fields": ["industry"]},
        now=now + timedelta(seconds=3),
    )
    assert updated is not None
    assert updated.status == CustomerEnrichmentJobStatus.COMPLETED.value
    assert updated.finished_at == now + timedelta(seconds=3)
    assert updated.lease_token is None


def test_exhausted_job_can_be_requeued_in_place():
    db = _session()
    crud = CustomerEnrichmentJobCRUD()
    now = datetime(2026, 9, 20, 10, 0, 0)
    job = _ensure(crud, db, available_at=now)
    job.profile_gate_timed_out_at = now - timedelta(seconds=5)
    db.flush()
    crud.claim_for_execution(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="owner",
        lease_expires_at=now + timedelta(seconds=120),
        now=now,
    )
    exhausted = crud.mark_exhausted_if_lease_owner(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="owner",
        error_message="model down",
        result_json={"terminal": "EXHAUSTED"},
        now=now + timedelta(seconds=3),
    )
    requeued = crud.requeue_exhausted(
        db,
        team_id=2,
        public_id=job.public_id,
        available_at=now + timedelta(minutes=1),
        now=now + timedelta(seconds=4),
    )
    assert exhausted is not None and requeued is not None
    assert requeued.id == job.id
    assert requeued.status == CustomerEnrichmentJobStatus.QUEUED.value
    assert requeued.attempt_count == 0
    assert requeued.requeue_count == 1
    assert requeued.result_json["previous_terminal"]["terminal"] == "EXHAUSTED"
    assert requeued.profile_gate_timed_out_at == now - timedelta(seconds=5)


def test_recovery_candidates_take_initial_and_backfill_quotas():
    db = _session()
    crud = CustomerEnrichmentJobCRUD()
    now = datetime(2026, 9, 20, 10, 0, 0)
    for customer_id in range(1, 31):
        _ensure(crud, db, customer_id=customer_id, available_at=now)
    for customer_id in range(101, 111):
        _ensure(
            crud,
            db,
            customer_id=customer_id,
            purpose=CustomerEnrichmentPurpose.HISTORICAL_BACKFILL.value,
            available_at=now,
        )
    candidates = crud.list_system_recovery_candidates(
        db,
        initial_limit=20,
        backfill_limit=5,
        now=now,
    )
    assert len(candidates) == 25
    assert sum(item.purpose == CustomerEnrichmentPurpose.INITIAL_CREATION.value for item in candidates) == 20
    assert sum(item.purpose == CustomerEnrichmentPurpose.HISTORICAL_BACKFILL.value for item in candidates) == 5

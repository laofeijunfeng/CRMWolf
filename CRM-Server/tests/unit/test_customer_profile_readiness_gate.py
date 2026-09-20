from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.customer_intelligence_event_service import (
    CustomerIntelligenceEvent,
    CustomerIntelligenceSource,
)
from app.services.customer_profile_readiness_gate import CustomerProfileReadinessGate


def _now() -> datetime:
    return datetime(2026, 9, 20, 10, 0, 0)


def _event(trigger: str) -> CustomerIntelligenceEvent:
    return CustomerIntelligenceEvent(
        event_key=f"event-{trigger}",
        trigger_type=trigger,
        tenant_id=2,
        team_id=2,
        customer_id=101,
        occurred_at=_now(),
        source=CustomerIntelligenceSource(
            source_type="customer",
            source_object_id="101",
        ),
    )


def _job(**kwargs):
    return SimpleNamespace(**kwargs)


class FakeJobCrud:
    def __init__(self, job) -> None:
        self.job = job
        self.identity_calls = []
        self.timeout_calls = []

    def get_by_identity(self, db, **kwargs):
        self.identity_calls.append({"db": db, **kwargs})
        return self.job

    def record_profile_gate_timeout_if_unset(self, db, **kwargs):
        self.timeout_calls.append({"db": db, **kwargs})
        return len(self.timeout_calls) == 1

class FakeDB:
    pass


class FakeRunService:
    def __init__(self) -> None:
        self.defer_calls = []

    def defer_until(self, db, *, team_id, run_id, not_before_at):
        self.defer_calls.append((team_id, run_id, not_before_at))


def _gate(job) -> CustomerProfileReadinessGate:
    gate = CustomerProfileReadinessGate(
        job_crud=FakeJobCrud(job),
        run_service=FakeRunService(),
    )
    return gate


def test_customer_created_event_is_gated():
    deadline = _now() + timedelta(seconds=30)
    gate = _gate(
        _job(
            purpose="INITIAL_CREATION",
            first_attempt_finished_at=None,
            profile_gate_deadline_at=deadline,
        )
    )

    deferred = gate.defer_if_needed(
        object(), event=_event("customer_created"), run=SimpleNamespace(id=7), now=_now()
    )

    assert deferred == _now() + timedelta(seconds=5)
    assert gate.run_service.defer_calls == [(2, 7, deferred)]


def test_customer_activity_created_event_is_gated():
    deadline = _now() + timedelta(seconds=30)
    gate = _gate(
        _job(
            purpose="INITIAL_CREATION",
            first_attempt_finished_at=None,
            profile_gate_deadline_at=deadline,
        )
    )

    assert gate.defer_if_needed(
        object(), event=_event("customer_activity_created"), run=SimpleNamespace(id=7), now=_now()
    ) == _now() + timedelta(seconds=5)


def test_historical_job_does_not_gate():
    gate = _gate(
        _job(
            purpose="HISTORICAL_BACKFILL",
            first_attempt_finished_at=None,
            profile_gate_deadline_at=None,
        )
    )

    assert gate.defer_if_needed(
        object(), event=_event("customer_created"), run=SimpleNamespace(id=7), now=_now()
    ) is None
    assert gate.run_service.defer_calls == []


def test_gate_deadline_passed_records_timeout_once_before_allowing_profile():
    before_deadline = _now() - timedelta(seconds=10)
    job = _job(
        purpose="INITIAL_CREATION",
        first_attempt_finished_at=None,
        profile_gate_deadline_at=_now() - timedelta(seconds=1),
        profile_gate_timed_out_at=None,
    )
    gate = _gate(job)
    db = FakeDB()

    assert gate.defer_if_needed(
        db, event=_event("customer_created"), run=SimpleNamespace(id=7), now=before_deadline
    ) == before_deadline + timedelta(seconds=5)
    assert job.profile_gate_timed_out_at is None

    assert gate.defer_if_needed(
        db, event=_event("customer_created"), run=SimpleNamespace(id=7), now=_now()
    ) is None
    gate.defer_if_needed(
        db,
        event=_event("customer_created"),
        run=SimpleNamespace(id=7),
        now=_now() + timedelta(minutes=1),
    )
    assert gate.job_crud.timeout_calls == [
        {
            "db": db,
            "team_id": 2,
            "customer_id": 101,
            "plan_version": "customer-initial-v1",
            "timed_out_at": _now(),
        },
        {
            "db": db,
            "team_id": 2,
            "customer_id": 101,
            "plan_version": "customer-initial-v1",
            "timed_out_at": _now() + timedelta(minutes=1),
        },
    ]
    assert gate.run_service.defer_calls == [(2, 7, before_deadline + timedelta(seconds=5))]


def test_first_attempt_finished_does_not_gate_or_record_timeout():
    job = _job(
        purpose="INITIAL_CREATION",
        first_attempt_finished_at=_now(),
        profile_gate_deadline_at=_now() - timedelta(seconds=30),
        profile_gate_timed_out_at=None,
    )
    gate = _gate(job)

    assert gate.defer_if_needed(
        object(), event=_event("customer_created"), run=SimpleNamespace(id=7), now=_now()
    ) is None
    assert job.profile_gate_timed_out_at is None
    assert gate.run_service.defer_calls == []


def test_missing_job_does_not_gate():
    gate = _gate(None)

    assert gate.defer_if_needed(
        object(), event=_event("customer_created"), run=SimpleNamespace(id=7), now=_now()
    ) is None
    assert gate.run_service.defer_calls == []

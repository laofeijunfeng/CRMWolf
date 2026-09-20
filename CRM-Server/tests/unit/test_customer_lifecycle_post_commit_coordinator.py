from __future__ import annotations

from contextlib import nullcontext
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from app.services.customer_enrichment_contracts import CustomerEnrichmentJobRequest
from app.services.customer_intelligence_refresh_service import CustomerIntelligenceCommittedEventRequest
from app.services.customer_lifecycle_post_commit_coordinator import (
    CustomerLifecyclePostCommitCoordinator,
    CustomerLifecyclePostCommitWork,
)


class FakeDb:
    def __init__(self) -> None:
        self.savepoints = 0
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def begin_nested(self):
        self.savepoints += 1
        return nullcontext()

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


class FakeJobService:
    def __init__(self, *, ensure_error=None, kick_error=None) -> None:
        self.ensure_error = ensure_error
        self.kick_error = kick_error
        self.ensure_calls: list[dict[str, object]] = []
        self.kick_calls: list[str] = []
        self.job = SimpleNamespace(public_id="cej_1")

    def ensure(self, db, **kwargs):
        self.ensure_calls.append(kwargs)
        if self.ensure_error is not None:
            raise self.ensure_error
        return self.job

    def kick(self, request) -> None:
        self.kick_calls.append(request.job_public_id)
        if self.kick_error is not None:
            raise self.kick_error


class FakeIntelligenceService:
    def __init__(
        self,
        *,
        prepare_error=None,
        after_commit_error=None,
        after_commit_profile_service=None,
    ) -> None:
        self.prepare_error = prepare_error
        self.after_commit_error = after_commit_error
        self.after_commit_profile_service = after_commit_profile_service
        self.calls: list[dict[str, object]] = []
        self.after_commit_calls: list[dict[str, object]] = []
        self.request = SimpleNamespace(request_id="profile-1", scheduled=True, kick_required=True)

    def enqueue_customer_lifecycle_refresh(self, db, **kwargs):
        self.calls.append(kwargs)
        if self.prepare_error is not None:
            raise self.prepare_error
        return self.request

    def enqueue_customer_lifecycle_refresh_after_commit(self, **kwargs):
        self.after_commit_calls.append(kwargs)
        if self.after_commit_error is not None:
            raise self.after_commit_error
        if self.after_commit_profile_service is not None:
            self.after_commit_profile_service.kick_committed_event_refresh(self.request)
        return self.request


class FakeProfileService:
    def __init__(self, *, kick_error=None) -> None:
        self.kick_error = kick_error
        self.kick_calls: list[str] = []
        self.kick_required_calls: list[bool] = []

    def kick_committed_event_refresh(self, request) -> None:
        self.kick_calls.append(request.request_id)
        self.kick_required_calls.append(bool(getattr(request, "kick_required", False)))
        if self.kick_error is not None:
            raise self.kick_error


def _customer(*, industry):
    return SimpleNamespace(id=101, team_id=2, industry=industry, version=1)


def _coordinator(
    *,
    job_error=None,
    profile_error=None,
    enrichment_kick_error=None,
    profile_kick_error=None,
    session_factory=None,
):
    job_service = FakeJobService(ensure_error=job_error, kick_error=enrichment_kick_error)
    profile_service = FakeProfileService(kick_error=profile_kick_error)
    intelligence = FakeIntelligenceService(
        prepare_error=profile_error,
        after_commit_profile_service=profile_service,
    )
    coordinator = CustomerLifecyclePostCommitCoordinator(
        job_service=job_service,
        intelligence_service=intelligence,
        profile_refresh_service=profile_service,
        session_factory=session_factory or FakeDb,
        settle_seconds=5,
        profile_gate_max_seconds=30,
        max_attempts=3,
    )
    return coordinator, SimpleNamespace(
        job_service=job_service,
        intelligence=intelligence,
        profile_service=profile_service,
    )


def _work_with_both_requests() -> CustomerLifecyclePostCommitWork:
    return CustomerLifecyclePostCommitWork(
        enrichment_request=CustomerEnrichmentJobRequest(team_id=2, job_public_id="cej_1"),
        profile_request=CustomerIntelligenceCommittedEventRequest(
            request_id="profile-1",
            event=SimpleNamespace(),
            scope="full",
            kick_required=False,
        ),
        warnings=(),
    )



def test_work_keeps_warnings_as_third_positional_field():
    warnings = ("existing warning",)

    work = CustomerLifecyclePostCommitWork(None, None, warnings)

    assert work.warnings == warnings
    assert work.profile_kick_pending is True

def test_work_is_frozen():
    work = _work_with_both_requests()

    with pytest.raises(FrozenInstanceError):
        work.warnings = ("changed",)


def test_prepare_registers_enrichment_and_profile_for_null_industry():
    coordinator, fakes = _coordinator()
    work = coordinator.prepare_in_transaction(
        FakeDb(),
        customer=_customer(industry=None),
        actor_id="9",
        trigger_type="customer_created",
    )

    assert work.enrichment_request.job_public_id == "cej_1"
    assert work.profile_request.request_id == "profile-1"
    assert fakes.job_service.ensure_calls[0]["purpose"] == "INITIAL_CREATION"
    assert fakes.intelligence.calls[0]["trigger_type"] == "customer_created"


@pytest.mark.parametrize("industry", ["", "   \t"])
def test_prepare_registers_enrichment_for_blank_industry(industry):
    coordinator, fakes = _coordinator()

    work = coordinator.prepare_in_transaction(
        FakeDb(),
        customer=_customer(industry=industry),
        actor_id="9",
        trigger_type="customer_created",
    )

    assert work.enrichment_request.job_public_id == "cej_1"
    assert len(fakes.job_service.ensure_calls) == 1

@pytest.mark.parametrize("industry", ["", "   \t"])
def test_enqueue_after_commit_registers_enrichment_for_blank_industry(industry):
    sessions: list[FakeDb] = []

    def session_factory():
        session = FakeDb()
        sessions.append(session)
        return session

    coordinator, fakes = _coordinator(session_factory=session_factory)

    work = coordinator.enqueue_after_commit(
        customer=_customer(industry=industry),
        actor_id="9",
        trigger_type="customer_created",
    )

    assert work.enrichment_request.job_public_id == "cej_1"
    assert len(fakes.job_service.ensure_calls) == 1
    assert sessions[0].commits == 1

def test_prepare_skips_enrichment_when_industry_already_filled():
    coordinator, fakes = _coordinator()
    work = coordinator.prepare_in_transaction(
        FakeDb(), customer=_customer(industry="finance"), actor_id="9", trigger_type="customer_created"
    )

    assert work.enrichment_request is None
    assert work.profile_request.request_id == "profile-1"
    assert fakes.job_service.ensure_calls == []


def test_prepare_isolates_job_registration_failure():
    coordinator, _ = _coordinator(job_error=RuntimeError("job store down"))
    db = FakeDb()
    work = coordinator.prepare_in_transaction(
        db, customer=_customer(industry=None), actor_id="9", trigger_type="customer_created"
    )

    assert work.enrichment_request is None
    assert "job store down" in work.warnings[0]
    assert work.profile_request.request_id == "profile-1"
    assert db.savepoints == 2


def test_prepare_isolates_profile_registration_failure():
    coordinator, _ = _coordinator(profile_error=RuntimeError("profile store down"))
    db = FakeDb()
    work = coordinator.prepare_in_transaction(
        db, customer=_customer(industry=None), actor_id="9", trigger_type="customer_created"
    )

    assert work.enrichment_request.job_public_id == "cej_1"
    assert work.profile_request is None
    assert "profile store down" in work.warnings[0]
    assert db.savepoints == 2


def test_repeated_prepare_reuses_same_job():
    coordinator, fakes = _coordinator()
    first = coordinator.prepare_in_transaction(
        FakeDb(), customer=_customer(industry=None), actor_id="9", trigger_type="customer_created"
    )
    second = coordinator.prepare_in_transaction(
        FakeDb(), customer=_customer(industry=None), actor_id="9", trigger_type="customer_created"
    )

    assert first.enrichment_request.job_public_id == second.enrichment_request.job_public_id
    assert len(fakes.job_service.ensure_calls) == 2


def test_enqueue_after_commit_uses_short_session_for_enrichment_receipt():
    sessions: list[FakeDb] = []

    def session_factory():
        session = FakeDb()
        sessions.append(session)
        return session

    coordinator, fakes = _coordinator(session_factory=session_factory)
    work = coordinator.enqueue_after_commit(
        customer=_customer(industry=None),
        actor_id="9",
        trigger_type="customer_converted_from_lead",
        source_lead_id=44,
    )

    assert work.enrichment_request.job_public_id == "cej_1"
    assert work.profile_request.request_id == "profile-1"
    assert sessions[0].commits == 1
    assert sessions[0].closed is True
    assert fakes.intelligence.after_commit_calls[0]["source_lead_id"] == 44


def test_enqueue_after_commit_profile_publication_is_the_single_kick_owner():
    coordinator, fakes = _coordinator()
    work = coordinator.enqueue_after_commit(
        customer=_customer(industry=None),
        actor_id="9",
        trigger_type="customer_converted_from_lead",
        source_lead_id=44,
    )

    warnings = coordinator.kick(work)

    assert warnings == ()
    assert fakes.job_service.kick_calls == ["cej_1"]
    assert fakes.profile_service.kick_calls == ["profile-1"]


def test_prepare_profile_request_is_kicked_once_after_commit():
    coordinator, fakes = _coordinator()
    work = coordinator.prepare_in_transaction(
        FakeDb(),
        customer=_customer(industry=None),
        actor_id="9",
        trigger_type="customer_created",
    )

    warnings = coordinator.kick(work)

    assert warnings == ()
    assert fakes.job_service.kick_calls == ["cej_1"]
    assert fakes.profile_service.kick_calls == ["profile-1"]
    assert fakes.profile_service.kick_required_calls == [True]


def test_prepare_surfaces_unscheduled_profile_receipt_as_warning():
    coordinator, fakes = _coordinator()
    fakes.intelligence.request = SimpleNamespace(
        request_id="profile-1",
        scheduled=False,
        kick_required=False,
        schedule_error="profile store down",
    )

    work = coordinator.prepare_in_transaction(
        FakeDb(), customer=_customer(industry="finance"), actor_id="9", trigger_type="customer_created"
    )

    assert any("profile store down" in warning for warning in work.warnings)


def test_enqueue_after_commit_converts_session_factory_failure_to_warning():
    def fail_session_factory():
        raise RuntimeError("session unavailable")

    coordinator, _ = _coordinator(session_factory=fail_session_factory)

    work = coordinator.enqueue_after_commit(
        customer=_customer(industry=None),
        actor_id="9",
        trigger_type="customer_created",
    )

    assert work.enrichment_request is None
    assert any("session unavailable" in warning for warning in work.warnings)


def test_kick_attempts_both_workers_and_returns_warnings():
    coordinator, fakes = _coordinator(enrichment_kick_error=RuntimeError("enrichment down"))

    warnings = coordinator.kick(_work_with_both_requests())

    assert fakes.job_service.kick_calls == ["cej_1"]
    assert fakes.profile_service.kick_calls == ["profile-1"]
    assert fakes.profile_service.kick_required_calls == [True]
    assert any("enrichment down" in item for item in warnings)


def test_kick_never_raises_when_both_workers_fail():
    coordinator, _ = _coordinator(
        enrichment_kick_error=RuntimeError("enrichment down"),
        profile_kick_error=RuntimeError("profile down"),
    )

    warnings = coordinator.kick(_work_with_both_requests())

    assert any("enrichment down" in item for item in warnings)
    assert any("profile down" in item for item in warnings)

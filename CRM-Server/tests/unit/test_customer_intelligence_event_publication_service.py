from __future__ import annotations

from types import SimpleNamespace

from app.services.customer_intelligence_event_publication_service import (
    CustomerIntelligenceEventPublicationService,
)
from app.services.customer_intelligence_event_service import (
    CustomerIntelligenceEvent,
    CustomerIntelligenceSource,
)
from app.services.customer_intelligence_refresh_service import CustomerIntelligenceCommittedEventRequest


class _NestedTransaction:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class _Db:
    def begin_nested(self):
        return _NestedTransaction()


def _event() -> CustomerIntelligenceEvent:
    return CustomerIntelligenceEvent(
        event_key="event-1",
        trigger_type="deal_journey_event_recorded",
        tenant_id=1,
        team_id=1,
        customer_id=2,
        source=CustomerIntelligenceSource("deal_journey_event", "10"),
    )


def test_persist_in_transaction_is_the_single_savepoint_publication_seam(monkeypatch):
    refresh = SimpleNamespace(
        calls=[],
        enqueue_committed_event_refresh=lambda db, **kwargs: (
            refresh.calls.append((db, kwargs))
            or CustomerIntelligenceCommittedEventRequest(
                request_id="request-1",
                event=kwargs["event"],
                scope=kwargs["scope"],
            )
        ),
    )
    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.customer_intelligence_refresh_service",
        refresh,
    )

    service = CustomerIntelligenceEventPublicationService()
    request = service.persist_in_transaction_request(_Db(), event=_event(), scope="partial")

    assert request is not None
    assert request.scheduled is True
    assert request.kick_required is False
    assert request.schedule_error is None
    assert len(refresh.calls) == 1
    assert refresh.calls[0][1]["event"].event_key == "event-1"
    assert refresh.calls[0][1]["scope"] == "partial"


def test_persist_in_transaction_isolates_refresh_failures(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("outbox unavailable")

    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.customer_intelligence_refresh_service",
        SimpleNamespace(enqueue_committed_event_refresh=fail),
    )

    error = CustomerIntelligenceEventPublicationService().persist_in_transaction(
        _Db(), event=_event()
    )

    assert error == "RuntimeError: outbox unavailable"


def test_enqueue_after_commit_owns_durable_receipt_and_low_latency_kick(monkeypatch):
    request = SimpleNamespace(scheduled=True, schedule_error=None)
    refresh = SimpleNamespace(
        enqueue_calls=[],
        kick_calls=[],
        enqueue_committed_event_refresh_after_commit=lambda **kwargs: (
            refresh.enqueue_calls.append(kwargs) or request
        ),
        kick_committed_event_refresh=lambda value: refresh.kick_calls.append(value),
    )
    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.customer_intelligence_refresh_service",
        refresh,
    )

    result = CustomerIntelligenceEventPublicationService().enqueue_after_commit(
        event=_event(), scope="full"
    )

    assert result is request
    assert refresh.enqueue_calls == [{"event": _event(), "scope": "full"}]
    assert refresh.kick_calls == [request]


def test_kick_after_commit_converts_scheduler_failure_to_observable_error(monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("scheduler unavailable")

    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.customer_intelligence_refresh_service",
        SimpleNamespace(enqueue_committed_event_refresh_after_commit=fail),
    )

    error = CustomerIntelligenceEventPublicationService().kick_after_commit(event=_event())

    assert error == "RuntimeError: scheduler unavailable"


def test_enqueue_after_commit_isolates_receipt_persistence_failure(monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("durable store unavailable")

    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.customer_intelligence_refresh_service",
        SimpleNamespace(enqueue_committed_event_refresh_after_commit=fail),
    )

    request = CustomerIntelligenceEventPublicationService().enqueue_after_commit(event=_event())

    assert request.scheduled is False
    assert request.kick_required is False
    assert request.schedule_error == "RuntimeError: durable store unavailable"


def test_enqueue_after_commit_isolates_kick_failure_after_receipt_is_durable(monkeypatch):
    request = CustomerIntelligenceCommittedEventRequest(
        request_id="request-1",
        event=_event(),
        scope="partial",
    )

    def fail(_request):
        raise RuntimeError("worker unavailable")

    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.customer_intelligence_refresh_service",
        SimpleNamespace(
            enqueue_committed_event_refresh_after_commit=lambda **kwargs: request,
            kick_committed_event_refresh=fail,
        ),
    )

    result = CustomerIntelligenceEventPublicationService().enqueue_after_commit(event=_event())

    assert result.scheduled is True
    assert result.kick_required is False
    assert result.schedule_error == "RuntimeError: worker unavailable"


def test_trigger_committed_event_refresh_routes_through_publication_seam(monkeypatch):
    calls = []

    async def fake_trigger(db, **kwargs):
        calls.append((db, kwargs))
        return "started"

    refresh = SimpleNamespace(trigger_committed_event_refresh=fake_trigger)
    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.customer_intelligence_refresh_service",
        refresh,
    )

    result = __import__("asyncio").run(
        CustomerIntelligenceEventPublicationService().trigger_committed_event_refresh(
            _Db(), event=_event(), scope="partial"
        )
    )

    assert result == "started"
    assert calls[0][1] == {"event": _event(), "scope": "partial"}

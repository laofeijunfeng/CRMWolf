from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.customer_intelligence_run import CustomerIntelligenceRun, CustomerIntelligenceRunStatus
from app.services.customer_intelligence_event_service import (
    CustomerIntelligenceEvent,
    CustomerIntelligenceSource,
)
from app.services.customer_intelligence_run_service import (
    CustomerIntelligenceRunInput,
    customer_intelligence_run_service,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[CustomerIntelligenceRun.__table__])
    Session = sessionmaker(bind=engine)
    return Session()


def _event(
    *,
    event_key: str = "event-1",
    team_id: int = 2,
    customer_id: int = 101,
    request_id: str = "request-1",
):
    return CustomerIntelligenceEvent(
        event_key=event_key,
        trigger_type="manual_refresh_requested",
        tenant_id=team_id,
        team_id=team_id,
        customer_id=customer_id,
        occurred_at=datetime(2026, 8, 2, 10, 0, 0),
        source=CustomerIntelligenceSource(
            source_type="manual_refresh",
            source_object_id=request_id,
        ),
        actor_id="9",
    )


def test_customer_intelligence_run_service_records_success_idempotently():
    db = _session()
    run_input = CustomerIntelligenceRunInput(request_id="request-1", event=_event(), scope="full")

    pending = customer_intelligence_run_service.ensure_pending(db, run_input)
    running = customer_intelligence_run_service.mark_running(
        db,
        run_input,
        started_at=datetime(2026, 8, 2, 10, 0, 0),
    )
    succeeded = customer_intelligence_run_service.mark_succeeded(
        db,
        run_input,
        result={
            "route": "refresh_profile",
            "event": {"event_key": "event-1"},
            "persisted_customer_fact_refs": [{"fact_id": 501}],
            "visible_trace": [{"title": "读取客户上下文", "content": "已读取客户上下文"}],
        },
        finished_at=datetime(2026, 8, 2, 10, 0, 2),
    )
    db.commit()

    assert pending.id == running.id == succeeded.id
    assert db.query(CustomerIntelligenceRun).count() == 1
    assert succeeded.status == CustomerIntelligenceRunStatus.SUCCESS
    assert succeeded.attempt_count == 1
    assert succeeded.last_duration_ms == 2000
    assert succeeded.route == "refresh_profile"
    assert succeeded.result_json["persisted_fact_count"] == 1
    assert succeeded.visible_trace_json[0]["title"] == "读取客户上下文"


def test_customer_intelligence_run_service_records_retryable_failure():
    db = _session()
    run_input = CustomerIntelligenceRunInput(request_id="request-1", event=_event(), scope="brief")

    customer_intelligence_run_service.mark_running(
        db,
        run_input,
        started_at=datetime(2026, 8, 2, 10, 0, 0),
    )
    failed = customer_intelligence_run_service.mark_failed(
        db,
        run_input,
        error_message="graph failed",
        finished_at=datetime(2026, 8, 2, 10, 0, 1),
    )
    db.commit()

    assert failed.status == CustomerIntelligenceRunStatus.RETRY_PENDING
    assert failed.attempt_count == 1
    assert failed.next_retry_at is not None
    assert failed.error_message == "graph failed"


def test_customer_intelligence_run_service_lists_retryable_runs():
    db = _session()
    run_input = CustomerIntelligenceRunInput(request_id="request-1", event=_event(), scope="brief")
    other_team_input = CustomerIntelligenceRunInput(
        request_id="request-2",
        event=_event(event_key="event-2", team_id=3, customer_id=201, request_id="request-2"),
        scope="brief",
    )
    customer_intelligence_run_service.mark_running(db, run_input)
    customer_intelligence_run_service.mark_failed(
        db,
        run_input,
        error_message="graph failed",
        finished_at=datetime(2026, 8, 2, 10, 0, 0),
    )
    customer_intelligence_run_service.mark_running(db, other_team_input)
    customer_intelligence_run_service.mark_failed(
        db,
        other_team_input,
        error_message="other team graph failed",
        finished_at=datetime(2026, 8, 2, 10, 0, 0),
    )
    db.commit()

    retryable = customer_intelligence_run_service.list_retryable(
        db,
        now=datetime(2026, 8, 2, 10, 1, 0),
        team_id=2,
    )

    assert [run.request_id for run in retryable] == ["request-1"]


def test_customer_intelligence_run_service_lists_pending_and_due_retry_runs():
    db = _session()
    pending_input = CustomerIntelligenceRunInput(
        request_id="pending-request",
        event=_event(event_key="pending-event", request_id="pending-request"),
        scope="brief",
    )
    due_retry_input = CustomerIntelligenceRunInput(
        request_id="due-retry-request",
        event=_event(event_key="due-retry-event", request_id="due-retry-request"),
        scope="brief",
    )
    future_retry_input = CustomerIntelligenceRunInput(
        request_id="future-retry-request",
        event=_event(event_key="future-retry-event", request_id="future-retry-request"),
        scope="brief",
    )
    stale_running_input = CustomerIntelligenceRunInput(
        request_id="stale-running-request",
        event=_event(event_key="stale-running-event", request_id="stale-running-request"),
        scope="brief",
    )
    active_running_input = CustomerIntelligenceRunInput(
        request_id="active-running-request",
        event=_event(event_key="active-running-event", request_id="active-running-request"),
        scope="brief",
    )

    pending = customer_intelligence_run_service.ensure_pending(db, pending_input)
    pending.created_time = datetime(2026, 8, 2, 10, 0, 0)
    due_retry = customer_intelligence_run_service.mark_running(db, due_retry_input)
    due_retry.created_time = datetime(2026, 8, 2, 10, 1, 0)
    customer_intelligence_run_service.mark_failed(
        db,
        due_retry_input,
        error_message="graph failed",
        finished_at=datetime(2026, 8, 2, 10, 0, 0),
    )
    future_retry = customer_intelligence_run_service.mark_running(db, future_retry_input)
    future_retry.created_time = datetime(2026, 8, 2, 10, 2, 0)
    customer_intelligence_run_service.mark_failed(
        db,
        future_retry_input,
        error_message="graph failed",
        finished_at=datetime(2026, 8, 2, 10, 3, 0),
    )
    stale_running = customer_intelligence_run_service.mark_running(
        db,
        stale_running_input,
        started_at=datetime(2026, 8, 2, 9, 45, 0),
    )
    stale_running.created_time = datetime(2026, 8, 2, 10, 4, 0)
    active_running = customer_intelligence_run_service.mark_running(
        db,
        active_running_input,
        started_at=datetime(2026, 8, 2, 10, 0, 30),
    )
    active_running.created_time = datetime(2026, 8, 2, 10, 5, 0)
    db.commit()

    due_runs = customer_intelligence_run_service.list_due(
        db,
        now=datetime(2026, 8, 2, 10, 1, 0),
        team_id=2,
    )

    assert [run.request_id for run in due_runs] == [
        "pending-request",
        "due-retry-request",
        "stale-running-request",
    ]


def test_customer_intelligence_run_service_projects_diagnostic_trace_events():
    db = _session()
    run_input = CustomerIntelligenceRunInput(request_id="request-1", event=_event(), scope="full")
    customer_intelligence_run_service.mark_running(
        db,
        run_input,
        started_at=datetime(2026, 8, 2, 10, 0, 0),
    )
    succeeded = customer_intelligence_run_service.mark_succeeded(
        db,
        run_input,
        result={
            "route": "refresh_profile",
            "event": {"event_key": "event-1"},
            "persisted_customer_fact_refs": [{"fact_id": 501}],
            "visible_trace": [
                {"title": "读取客户上下文", "content": "已读取客户上下文"},
                {"title": "更新客户记忆", "content": "已沉淀客户摘要和证据索引"},
            ],
        },
        finished_at=datetime(2026, 8, 2, 10, 0, 2),
    )
    db.commit()

    diagnostic = customer_intelligence_run_service.get_diagnostic(
        db,
        team_id=2,
        run_id=succeeded.id,
    )

    assert diagnostic is not None
    assert diagnostic.request_id == "request-1"
    assert diagnostic.route == "refresh_profile"
    assert [step["title"] for step in diagnostic.visible_trace] == ["读取客户上下文", "更新客户记忆"]
    assert [event["content"] for event in diagnostic.trace_events] == [
        "读取客户上下文：已读取客户上下文",
        "更新客户记忆：已沉淀客户摘要和证据索引",
    ]


def test_customer_intelligence_run_service_lists_customer_and_request_diagnostics():
    db = _session()
    first_input = CustomerIntelligenceRunInput(request_id="request-1", event=_event(), scope="full")
    second_event = CustomerIntelligenceEvent(
        event_key="event-2",
        trigger_type="manual_refresh_requested",
        tenant_id=2,
        team_id=2,
        customer_id=101,
        occurred_at=datetime(2026, 8, 2, 10, 1, 0),
        source=CustomerIntelligenceSource(
            source_type="manual_refresh",
            source_object_id="request-2",
        ),
        actor_id="9",
    )
    second_input = CustomerIntelligenceRunInput(request_id="request-2", event=second_event, scope="brief")

    first = customer_intelligence_run_service.mark_running(db, first_input)
    first.created_time = datetime(2026, 8, 2, 10, 0, 0)
    customer_intelligence_run_service.mark_failed(
        db,
        first_input,
        error_message="graph failed",
        finished_at=datetime(2026, 8, 2, 10, 0, 1),
    )
    second = customer_intelligence_run_service.mark_running(db, second_input)
    second.created_time = datetime(2026, 8, 2, 10, 1, 0)
    customer_intelligence_run_service.mark_succeeded(
        db,
        second_input,
        result={"route": "refresh_brief"},
        finished_at=datetime(2026, 8, 2, 10, 1, 1),
    )
    db.commit()

    customer_runs = customer_intelligence_run_service.list_customer_diagnostics(
        db,
        team_id=2,
        customer_id=101,
    )
    request_runs = customer_intelligence_run_service.list_request_diagnostics(
        db,
        team_id=2,
        request_id="request-1",
    )

    assert [run.request_id for run in customer_runs] == ["request-2", "request-1"]
    assert [run.request_id for run in request_runs] == ["request-1"]
    assert request_runs[0].error_message == "graph failed"


def test_customer_intelligence_run_service_lists_diagnostics_with_filters():
    db = _session()
    failed_input = CustomerIntelligenceRunInput(request_id="request-1", event=_event(), scope="full")
    success_input = CustomerIntelligenceRunInput(
        request_id="request-2",
        event=_event(event_key="event-2", request_id="request-2"),
        scope="brief",
    )
    other_team_input = CustomerIntelligenceRunInput(
        request_id="request-3",
        event=_event(event_key="event-3", team_id=3, customer_id=201, request_id="request-3"),
        scope="brief",
    )

    failed = customer_intelligence_run_service.mark_running(db, failed_input)
    failed.created_time = datetime(2026, 8, 2, 10, 0, 0)
    customer_intelligence_run_service.mark_failed(
        db,
        failed_input,
        error_message="graph failed",
        finished_at=datetime(2026, 8, 2, 10, 0, 1),
    )
    success = customer_intelligence_run_service.mark_running(db, success_input)
    success.created_time = datetime(2026, 8, 2, 10, 1, 0)
    customer_intelligence_run_service.mark_succeeded(
        db,
        success_input,
        result={"route": "refresh_brief"},
        finished_at=datetime(2026, 8, 2, 10, 1, 1),
    )
    other_team = customer_intelligence_run_service.mark_running(db, other_team_input)
    other_team.created_time = datetime(2026, 8, 2, 10, 2, 0)
    customer_intelligence_run_service.mark_failed(
        db,
        other_team_input,
        error_message="other team graph failed",
        finished_at=datetime(2026, 8, 2, 10, 2, 1),
    )
    db.commit()

    failed_runs = customer_intelligence_run_service.list_diagnostics(
        db,
        team_id=2,
        status=CustomerIntelligenceRunStatus.RETRY_PENDING,
    )
    request_runs = customer_intelligence_run_service.list_diagnostics(
        db,
        team_id=2,
        request_id="request-2",
    )

    assert [run.request_id for run in failed_runs] == ["request-1"]
    assert [run.request_id for run in request_runs] == ["request-2"]

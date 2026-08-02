"""Persistent audit and retry metadata for customer intelligence graph runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import TypeAlias

from sqlalchemy.orm import Session

from app.models.customer_intelligence_run import CustomerIntelligenceRun, CustomerIntelligenceRunStatus
from app.services.agent.types import coerce_json_dict
from app.services.customer_intelligence_event_service import CustomerIntelligenceEvent
from app.services.customer_intelligence_trace_service import visible_trace_events

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
JSONDict: TypeAlias = dict[str, JSONValue]
STALE_RUNNING_AFTER = timedelta(minutes=10)


@dataclass(frozen=True)
class CustomerIntelligenceRunInput:
    request_id: str
    event: CustomerIntelligenceEvent
    scope: str
    max_attempts: int = 3


@dataclass(frozen=True)
class CustomerIntelligenceRunDiagnostic:
    id: int
    request_id: str
    event_key: str
    team_id: int
    customer_id: int
    actor_id: str | None
    trigger_type: str
    scope: str
    status: str
    attempt_count: int
    max_attempts: int
    route: str | None
    result: JSONDict
    visible_trace: list[JSONDict]
    trace_events: list[JSONDict]
    error_message: str | None
    created_time: datetime | None
    started_time: datetime | None
    finished_time: datetime | None
    next_retry_at: datetime | None
    last_duration_ms: int | None


class CustomerIntelligenceRunService:
    def ensure_pending(self, db: Session, run_input: CustomerIntelligenceRunInput) -> CustomerIntelligenceRun:
        run = self._get_by_key(db, self.run_key(run_input))
        if run is None:
            run = CustomerIntelligenceRun(
                run_key=self.run_key(run_input),
                request_id=run_input.request_id,
                event_key=run_input.event.event_key,
                event_json=run_input.event.to_dict(),
                tenant_id=run_input.event.tenant_id,
                team_id=run_input.event.team_id,
                customer_id=run_input.event.customer_id,
                actor_id=run_input.event.actor_id,
                trigger_type=run_input.event.trigger_type,
                scope=run_input.scope,
                status=CustomerIntelligenceRunStatus.PENDING,
                max_attempts=run_input.max_attempts,
            )
            db.add(run)
        else:
            run.max_attempts = run_input.max_attempts
            run.event_json = run_input.event.to_dict()
        db.flush()
        return run

    def mark_running(
        self,
        db: Session,
        run_input: CustomerIntelligenceRunInput,
        *,
        started_at: datetime | None = None,
    ) -> CustomerIntelligenceRun:
        run = self.ensure_pending(db, run_input)
        run.status = CustomerIntelligenceRunStatus.RUNNING
        run.attempt_count = int(run.attempt_count or 0) + 1
        run.started_time = started_at or datetime.now()
        run.finished_time = None
        run.next_retry_at = None
        run.error_message = None
        db.flush()
        return run

    def mark_succeeded(
        self,
        db: Session,
        run_input: CustomerIntelligenceRunInput,
        *,
        result: JSONDict,
        finished_at: datetime | None = None,
    ) -> CustomerIntelligenceRun:
        run = self.ensure_pending(db, run_input)
        completed_at = finished_at or datetime.now()
        run.status = CustomerIntelligenceRunStatus.SUCCESS
        run.finished_time = completed_at
        run.last_duration_ms = _duration_ms(run.started_time, completed_at)
        run.next_retry_at = None
        run.route = str(result.get("route") or "") or None
        run.result_json = _result_summary(result)
        run.visible_trace_json = _visible_trace(result)
        run.error_message = None
        db.flush()
        return run

    def mark_failed(
        self,
        db: Session,
        run_input: CustomerIntelligenceRunInput,
        *,
        error_message: str,
        finished_at: datetime | None = None,
    ) -> CustomerIntelligenceRun:
        run = self.ensure_pending(db, run_input)
        completed_at = finished_at or datetime.now()
        attempts = int(run.attempt_count or 0)
        retryable = attempts < int(run.max_attempts or 1)
        run.status = (
            CustomerIntelligenceRunStatus.RETRY_PENDING
            if retryable
            else CustomerIntelligenceRunStatus.FAILED
        )
        run.finished_time = completed_at
        run.last_duration_ms = _duration_ms(run.started_time, completed_at)
        run.next_retry_at = _next_retry_at(completed_at, attempts) if retryable else None
        run.error_message = error_message[:2000]
        db.flush()
        return run

    def list_retryable(
        self,
        db: Session,
        *,
        now: datetime | None = None,
        team_id: int | None = None,
        limit: int = 50,
    ) -> list[CustomerIntelligenceRun]:
        current_time = now or datetime.now()
        query = db.query(CustomerIntelligenceRun).filter(
            CustomerIntelligenceRun.status == CustomerIntelligenceRunStatus.RETRY_PENDING,
            CustomerIntelligenceRun.next_retry_at <= current_time,
        )
        if team_id is not None:
            query = query.filter(CustomerIntelligenceRun.team_id == team_id)
        return (
            query.order_by(CustomerIntelligenceRun.next_retry_at.asc(), CustomerIntelligenceRun.created_time.asc())
            .limit(limit)
            .all()
        )

    def list_due(
        self,
        db: Session,
        *,
        now: datetime | None = None,
        team_id: int | None = None,
        limit: int = 50,
    ) -> list[CustomerIntelligenceRun]:
        current_time = now or datetime.now()
        stale_running_started_before = current_time - STALE_RUNNING_AFTER
        query = db.query(CustomerIntelligenceRun).filter(
            (
                CustomerIntelligenceRun.status == CustomerIntelligenceRunStatus.PENDING
            )
            | (
                (CustomerIntelligenceRun.status == CustomerIntelligenceRunStatus.RETRY_PENDING)
                & (CustomerIntelligenceRun.next_retry_at <= current_time)
            )
            | (
                (CustomerIntelligenceRun.status == CustomerIntelligenceRunStatus.RUNNING)
                & (CustomerIntelligenceRun.started_time <= stale_running_started_before)
            )
        )
        if team_id is not None:
            query = query.filter(CustomerIntelligenceRun.team_id == team_id)
        return (
            query.order_by(CustomerIntelligenceRun.created_time.asc(), CustomerIntelligenceRun.next_retry_at.asc())
            .limit(max(1, min(limit, 100)))
            .all()
        )

    def get_diagnostic(
        self,
        db: Session,
        *,
        team_id: int,
        run_id: int,
    ) -> CustomerIntelligenceRunDiagnostic | None:
        run = (
            db.query(CustomerIntelligenceRun)
            .filter(
                CustomerIntelligenceRun.team_id == team_id,
                CustomerIntelligenceRun.id == run_id,
            )
            .one_or_none()
        )
        return _run_diagnostic(run) if run is not None else None

    def list_customer_diagnostics(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        limit: int = 20,
    ) -> list[CustomerIntelligenceRunDiagnostic]:
        runs = (
            db.query(CustomerIntelligenceRun)
            .filter(
                CustomerIntelligenceRun.team_id == team_id,
                CustomerIntelligenceRun.customer_id == customer_id,
            )
            .order_by(CustomerIntelligenceRun.created_time.desc(), CustomerIntelligenceRun.id.desc())
            .limit(max(1, min(limit, 100)))
            .all()
        )
        return [_run_diagnostic(run) for run in runs]

    def list_request_diagnostics(
        self,
        db: Session,
        *,
        team_id: int,
        request_id: str,
        limit: int = 20,
    ) -> list[CustomerIntelligenceRunDiagnostic]:
        runs = (
            db.query(CustomerIntelligenceRun)
            .filter(
                CustomerIntelligenceRun.team_id == team_id,
                CustomerIntelligenceRun.request_id == request_id,
            )
            .order_by(CustomerIntelligenceRun.created_time.desc(), CustomerIntelligenceRun.id.desc())
            .limit(max(1, min(limit, 100)))
            .all()
        )
        return [_run_diagnostic(run) for run in runs]

    def list_diagnostics(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int | None = None,
        request_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[CustomerIntelligenceRunDiagnostic]:
        query = db.query(CustomerIntelligenceRun).filter(CustomerIntelligenceRun.team_id == team_id)
        if customer_id is not None:
            query = query.filter(CustomerIntelligenceRun.customer_id == customer_id)
        if request_id:
            query = query.filter(CustomerIntelligenceRun.request_id == request_id)
        if status:
            query = query.filter(CustomerIntelligenceRun.status == status)
        runs = (
            query.order_by(CustomerIntelligenceRun.created_time.desc(), CustomerIntelligenceRun.id.desc())
            .limit(max(1, min(limit, 100)))
            .all()
        )
        return [_run_diagnostic(run) for run in runs]

    def run_key(self, run_input: CustomerIntelligenceRunInput) -> str:
        raw = (
            "crmwolf/customer-intelligence-run/"
            f"{run_input.event.team_id}/{run_input.event.customer_id}/"
            f"{run_input.request_id}/{run_input.event.event_key}"
        )
        return sha256(raw.encode("utf-8")).hexdigest()

    def _get_by_key(self, db: Session, run_key: str) -> CustomerIntelligenceRun | None:
        return (
            db.query(CustomerIntelligenceRun)
            .filter(CustomerIntelligenceRun.run_key == run_key)
            .one_or_none()
        )


def _duration_ms(started_at: datetime | None, finished_at: datetime) -> int | None:
    if started_at is None:
        return None
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _next_retry_at(finished_at: datetime, attempts: int) -> datetime:
    delay_seconds = min(300, max(30, 30 * (2 ** max(0, attempts - 1))))
    return finished_at + timedelta(seconds=delay_seconds)


def _visible_trace(result: JSONDict) -> list[JSONDict]:
    trace = result.get("visible_trace")
    if not isinstance(trace, list):
        return []
    return [coerce_json_dict(item) for item in trace if isinstance(item, dict)][:50]


def _result_summary(result: JSONDict) -> JSONDict:
    review = coerce_json_dict(result.get("customer_fact_review"))
    persisted_refs = result.get("persisted_customer_fact_refs")
    return {
        "route": str(result.get("route") or ""),
        "event_key": str(coerce_json_dict(result.get("event")).get("event_key") or ""),
        "persisted_fact_count": len(persisted_refs) if isinstance(persisted_refs, list) else 0,
        "review_status": str(review.get("status") or ""),
        "has_interrupt": "__interrupt__" in result,
        "error_count": len(result.get("errors", [])) if isinstance(result.get("errors"), list) else 0,
    }


def _run_diagnostic(run: CustomerIntelligenceRun) -> CustomerIntelligenceRunDiagnostic:
    visible_trace = _visible_trace_from_run(run)
    return CustomerIntelligenceRunDiagnostic(
        id=int(run.id),
        request_id=str(run.request_id),
        event_key=str(run.event_key),
        team_id=int(run.team_id),
        customer_id=int(run.customer_id),
        actor_id=str(run.actor_id) if run.actor_id is not None else None,
        trigger_type=str(run.trigger_type),
        scope=str(run.scope),
        status=str(run.status),
        attempt_count=int(run.attempt_count or 0),
        max_attempts=int(run.max_attempts or 0),
        route=str(run.route) if run.route is not None else None,
        result=coerce_json_dict(run.result_json),
        visible_trace=visible_trace,
        trace_events=visible_trace_events({"visible_trace": visible_trace}),
        error_message=str(run.error_message) if run.error_message is not None else None,
        created_time=run.created_time,
        started_time=run.started_time,
        finished_time=run.finished_time,
        next_retry_at=run.next_retry_at,
        last_duration_ms=int(run.last_duration_ms) if run.last_duration_ms is not None else None,
    )


def _visible_trace_from_run(run: CustomerIntelligenceRun) -> list[JSONDict]:
    trace = run.visible_trace_json
    if not isinstance(trace, list):
        return []
    return [coerce_json_dict(item) for item in trace if isinstance(item, dict)][:50]


customer_intelligence_run_service = CustomerIntelligenceRunService()

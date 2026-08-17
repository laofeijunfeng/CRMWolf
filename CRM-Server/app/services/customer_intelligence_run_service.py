"""Durable execution state for customer-intelligence LangGraph runs.

The persisted run is the correctness boundary. In-process tasks are only a
low-latency kick: every executor must first acquire a renewable, expiring lease,
and only the lease owner may publish a terminal transition.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from typing import TypeAlias
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.customer_intelligence_run import CustomerIntelligenceRun, CustomerIntelligenceRunStatus
from app.services.agent.types import coerce_json_dict
from app.services.customer_intelligence_event_service import CustomerIntelligenceEvent
from app.services.customer_intelligence_trace_service import visible_trace_events
from app.utils.time import business_now

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
JSONDict: TypeAlias = dict[str, JSONValue]
TERMINAL_RUN_STATUSES = frozenset({
    CustomerIntelligenceRunStatus.SUCCESS,
    CustomerIntelligenceRunStatus.FAILED,
    CustomerIntelligenceRunStatus.CANCELLED,
})


class CustomerIntelligenceRunClaimStatus(StrEnum):
    CLAIMED = "CLAIMED"
    BUSY = "BUSY"
    TERMINAL = "TERMINAL"
    ATTEMPTS_EXHAUSTED = "ATTEMPTS_EXHAUSTED"


class CustomerIntelligenceRunLeaseMutationStatus(StrEnum):
    APPLIED = "APPLIED"
    STALE_LEASE = "STALE_LEASE"
    TERMINAL = "TERMINAL"


@dataclass(frozen=True)
class CustomerIntelligenceRunInput:
    request_id: str
    event: CustomerIntelligenceEvent
    scope: str
    max_attempts: int = 3


@dataclass(frozen=True)
class CustomerIntelligenceRunClaim:
    status: CustomerIntelligenceRunClaimStatus
    run: CustomerIntelligenceRun
    lease_token: str | None = None


@dataclass(frozen=True)
class CustomerIntelligenceRunLeaseMutation:
    status: CustomerIntelligenceRunLeaseMutationStatus
    run: CustomerIntelligenceRun


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
    lease_token: str | None
    lease_expires_at: datetime | None
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
        """Idempotently persist the run intent without changing an existing lifecycle."""

        run_key = self.run_key(run_input)
        run = self._get_by_key(db, team_id=run_input.event.team_id, run_key=run_key)
        if run is None:
            run = CustomerIntelligenceRun(
                run_key=run_key,
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
                max_attempts=max(1, run_input.max_attempts),
            )
            db.add(run)
        else:
            run.max_attempts = max(1, run_input.max_attempts)
            if not run.event_json:
                run.event_json = run_input.event.to_dict()
        db.flush()
        return run

    def get_by_request_id(
        self,
        db: Session,
        *,
        team_id: int,
        request_id: str,
    ) -> CustomerIntelligenceRun | None:
        return (
            db.query(CustomerIntelligenceRun)
            .filter(
                CustomerIntelligenceRun.team_id == team_id,
                CustomerIntelligenceRun.request_id == request_id,
            )
            .order_by(CustomerIntelligenceRun.id.desc())
            .first()
        )

    def claim_for_execution(
        self,
        db: Session,
        run_input: CustomerIntelligenceRunInput,
        *,
        now: datetime | None = None,
        lease_seconds: int = 300,
    ) -> CustomerIntelligenceRunClaim:
        """Claim one due run under a row lock.

        A live lease is never treated as a failure. Expired leases are reclaimed,
        and attempts are incremented exactly once per successful claim.
        """

        self.ensure_pending(db, run_input)
        current_time = now or business_now()
        run = self._get_by_key_for_update(
            db,
            team_id=run_input.event.team_id,
            run_key=self.run_key(run_input),
        )
        status = str(run.status)
        if status in TERMINAL_RUN_STATUSES:
            return CustomerIntelligenceRunClaim(CustomerIntelligenceRunClaimStatus.TERMINAL, run)
        if status == CustomerIntelligenceRunStatus.RUNNING:
            lease_expires_at = run.lease_expires_at
            if lease_expires_at is not None and lease_expires_at > current_time:
                return CustomerIntelligenceRunClaim(CustomerIntelligenceRunClaimStatus.BUSY, run)
        if status == CustomerIntelligenceRunStatus.RETRY_PENDING:
            next_retry_at = run.next_retry_at
            if next_retry_at is not None and next_retry_at > current_time:
                return CustomerIntelligenceRunClaim(CustomerIntelligenceRunClaimStatus.BUSY, run)

        attempts = int(run.attempt_count or 0)
        max_attempts = max(1, int(run.max_attempts or run_input.max_attempts or 1))
        if attempts >= max_attempts:
            run.status = CustomerIntelligenceRunStatus.FAILED
            run.finished_time = current_time
            run.next_retry_at = None
            run.lease_token = None
            run.lease_expires_at = None
            run.error_message = run.error_message or "客户智能档案刷新已达到最大重试次数。"
            db.flush()
            return CustomerIntelligenceRunClaim(CustomerIntelligenceRunClaimStatus.ATTEMPTS_EXHAUSTED, run)

        lease_token = uuid4().hex
        run.status = CustomerIntelligenceRunStatus.RUNNING
        run.attempt_count = attempts + 1
        run.started_time = current_time
        run.finished_time = None
        run.next_retry_at = None
        run.error_message = None
        run.lease_token = lease_token
        run.lease_expires_at = current_time + timedelta(seconds=max(30, lease_seconds))
        db.flush()
        return CustomerIntelligenceRunClaim(
            CustomerIntelligenceRunClaimStatus.CLAIMED,
            run,
            lease_token,
        )

    def mark_succeeded_if_lease_owner(
        self,
        db: Session,
        run_input: CustomerIntelligenceRunInput,
        *,
        lease_token: str,
        result: JSONDict,
        finished_at: datetime | None = None,
    ) -> CustomerIntelligenceRunLeaseMutation:
        run = self._get_by_key_for_update(
            db,
            team_id=run_input.event.team_id,
            run_key=self.run_key(run_input),
        )
        if str(run.status) in TERMINAL_RUN_STATUSES:
            return CustomerIntelligenceRunLeaseMutation(CustomerIntelligenceRunLeaseMutationStatus.TERMINAL, run)
        if str(run.lease_token or "") != lease_token or str(run.status) != CustomerIntelligenceRunStatus.RUNNING:
            return CustomerIntelligenceRunLeaseMutation(CustomerIntelligenceRunLeaseMutationStatus.STALE_LEASE, run)
        completed_at = finished_at or business_now()
        run.status = CustomerIntelligenceRunStatus.SUCCESS
        run.finished_time = completed_at
        run.last_duration_ms = _duration_ms(run.started_time, completed_at)
        run.next_retry_at = None
        run.route = str(result.get("route") or "") or None
        run.result_json = _result_summary(result)
        run.visible_trace_json = _merge_visible_trace(run.visible_trace_json, _visible_trace(result))
        run.error_message = None
        run.lease_token = None
        run.lease_expires_at = None
        db.flush()
        return CustomerIntelligenceRunLeaseMutation(CustomerIntelligenceRunLeaseMutationStatus.APPLIED, run)

    def record_visible_progress_if_lease_owner(
        self,
        db: Session,
        run_input: CustomerIntelligenceRunInput,
        *,
        lease_token: str,
        progress: JSONDict,
    ) -> CustomerIntelligenceRunLeaseMutation:
        """Persist streamed progress on the authoritative run before UI projection.

        Agent operations may be bound after the graph has already started. Keeping
        progress on the leased run makes those events replayable when the UI
        projection appears later, while the lease check prevents a superseded
        executor from publishing stale progress.
        """

        run = self._get_by_key_for_update(
            db,
            team_id=run_input.event.team_id,
            run_key=self.run_key(run_input),
        )
        if str(run.status) in TERMINAL_RUN_STATUSES:
            return CustomerIntelligenceRunLeaseMutation(CustomerIntelligenceRunLeaseMutationStatus.TERMINAL, run)
        if str(run.lease_token or "") != lease_token or str(run.status) != CustomerIntelligenceRunStatus.RUNNING:
            return CustomerIntelligenceRunLeaseMutation(CustomerIntelligenceRunLeaseMutationStatus.STALE_LEASE, run)
        run.visible_trace_json = _merge_visible_trace(run.visible_trace_json, [progress])
        db.flush()
        return CustomerIntelligenceRunLeaseMutation(CustomerIntelligenceRunLeaseMutationStatus.APPLIED, run)

    def mark_failed_if_lease_owner(
        self,
        db: Session,
        run_input: CustomerIntelligenceRunInput,
        *,
        lease_token: str,
        error_message: str,
        finished_at: datetime | None = None,
    ) -> CustomerIntelligenceRunLeaseMutation:
        run = self._get_by_key_for_update(
            db,
            team_id=run_input.event.team_id,
            run_key=self.run_key(run_input),
        )
        if str(run.status) in TERMINAL_RUN_STATUSES:
            return CustomerIntelligenceRunLeaseMutation(CustomerIntelligenceRunLeaseMutationStatus.TERMINAL, run)
        if str(run.lease_token or "") != lease_token or str(run.status) != CustomerIntelligenceRunStatus.RUNNING:
            return CustomerIntelligenceRunLeaseMutation(CustomerIntelligenceRunLeaseMutationStatus.STALE_LEASE, run)
        completed_at = finished_at or business_now()
        attempts = int(run.attempt_count or 0)
        retryable = attempts < max(1, int(run.max_attempts or 1))
        run.status = (
            CustomerIntelligenceRunStatus.RETRY_PENDING
            if retryable
            else CustomerIntelligenceRunStatus.FAILED
        )
        run.finished_time = completed_at
        run.last_duration_ms = _duration_ms(run.started_time, completed_at)
        run.next_retry_at = _next_retry_at(completed_at, attempts) if retryable else None
        run.error_message = error_message[:2000]
        run.lease_token = None
        run.lease_expires_at = None
        db.flush()
        return CustomerIntelligenceRunLeaseMutation(CustomerIntelligenceRunLeaseMutationStatus.APPLIED, run)

    def list_retryable(
        self,
        db: Session,
        *,
        now: datetime | None = None,
        team_id: int | None = None,
        limit: int = 50,
    ) -> list[CustomerIntelligenceRun]:
        current_time = now or business_now()
        query = db.query(CustomerIntelligenceRun).filter(
            CustomerIntelligenceRun.status == CustomerIntelligenceRunStatus.RETRY_PENDING,
            CustomerIntelligenceRun.next_retry_at <= current_time,
        )
        if team_id is not None:
            query = query.filter(CustomerIntelligenceRun.team_id == team_id)
        return (
            query.order_by(CustomerIntelligenceRun.next_retry_at.asc(), CustomerIntelligenceRun.created_time.asc())
            .limit(max(1, min(limit, 100)))
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
        current_time = now or business_now()
        query = db.query(CustomerIntelligenceRun).filter(
            (CustomerIntelligenceRun.status == CustomerIntelligenceRunStatus.PENDING)
            | (
                (CustomerIntelligenceRun.status == CustomerIntelligenceRunStatus.RETRY_PENDING)
                & (CustomerIntelligenceRun.next_retry_at <= current_time)
            )
            | (
                (CustomerIntelligenceRun.status == CustomerIntelligenceRunStatus.RUNNING)
                & or_(
                    CustomerIntelligenceRun.lease_expires_at.is_(None),
                    CustomerIntelligenceRun.lease_expires_at <= current_time,
                )
            )
        )
        if team_id is not None:
            query = query.filter(CustomerIntelligenceRun.team_id == team_id)
        return (
            query.order_by(CustomerIntelligenceRun.created_time.asc(), CustomerIntelligenceRun.next_retry_at.asc())
            .limit(max(1, min(limit, 100)))
            .all()
        )

    def get_diagnostic(self, db: Session, *, team_id: int, run_id: int) -> CustomerIntelligenceRunDiagnostic | None:
        run = (
            db.query(CustomerIntelligenceRun)
            .filter(CustomerIntelligenceRun.team_id == team_id, CustomerIntelligenceRun.id == run_id)
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

    def _get_by_key(
        self,
        db: Session,
        *,
        team_id: int,
        run_key: str,
    ) -> CustomerIntelligenceRun | None:
        return (
            db.query(CustomerIntelligenceRun)
            .filter(
                CustomerIntelligenceRun.team_id == team_id,
                CustomerIntelligenceRun.run_key == run_key,
            )
            .one_or_none()
        )

    def _get_by_key_for_update(
        self,
        db: Session,
        *,
        team_id: int,
        run_key: str,
    ) -> CustomerIntelligenceRun:
        return (
            db.query(CustomerIntelligenceRun)
            .filter(
                CustomerIntelligenceRun.team_id == team_id,
                CustomerIntelligenceRun.run_key == run_key,
            )
            .populate_existing()
            .with_for_update()
            .one()
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


def _merge_visible_trace(existing: object, incoming: list[JSONDict]) -> list[JSONDict]:
    merged: list[JSONDict] = []
    seen: set[tuple[str, str]] = set()
    existing_items = existing if isinstance(existing, list) else []
    for item in [*existing_items, *incoming]:
        trace = coerce_json_dict(item)
        title = str(trace.get("title") or trace.get("step") or "").strip()
        content = str(trace.get("content") or trace.get("message") or "").strip()
        if not content:
            continue
        identity = (title, content)
        if identity in seen:
            continue
        seen.add(identity)
        merged.append(trace)
        if len(merged) >= 50:
            break
    return merged


def _result_summary(result: JSONDict) -> JSONDict:
    review = coerce_json_dict(result.get("customer_fact_review"))
    brief_result = coerce_json_dict(result.get("brief_refresh_result"))
    persisted_refs = result.get("persisted_customer_fact_refs")
    return {
        "route": str(result.get("route") or ""),
        "event_key": str(coerce_json_dict(result.get("event")).get("event_key") or ""),
        "persisted_fact_count": len(persisted_refs) if isinstance(persisted_refs, list) else 0,
        "review_status": str(review.get("status") or ""),
        "has_interrupt": "__interrupt__" in result,
        "error_count": len(result.get("errors", [])) if isinstance(result.get("errors"), list) else 0,
        "degraded": result.get("degraded") is True or brief_result.get("degraded") is True,
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
        lease_token=str(run.lease_token) if run.lease_token is not None else None,
        lease_expires_at=run.lease_expires_at,
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

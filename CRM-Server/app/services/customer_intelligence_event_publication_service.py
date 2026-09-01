"""Durable publication seam for Customer Intelligence events.

Business modules own their source-of-truth writes and event construction.  This
module owns the one cross-cutting concern that every committed intelligence
event shares: durable registration, post-commit liveness, and failure
isolation.  Keeping that policy here prevents task, journey, and business
object modules from gradually developing different delivery semantics.
"""

from __future__ import annotations

import logging
from dataclasses import is_dataclass, replace
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.customer_intelligence_event_service import CustomerIntelligenceEvent
    from app.services.customer_intelligence_refresh_service import (
        CustomerIntelligenceCommittedEventRequest,
        CustomerIntelligenceRefreshScope,
    )


class CustomerIntelligenceRefreshPort(Protocol):
    """Minimal scheduler port required by the publication boundary."""

    async def trigger_committed_event_refresh(
        self,
        db: Session,
        *,
        event: CustomerIntelligenceEvent,
        scope: CustomerIntelligenceRefreshScope,
    ) -> CustomerIntelligenceCommittedEventRequest: ...

    def enqueue_committed_event_refresh(
        self,
        db: Session,
        *,
        event: CustomerIntelligenceEvent,
        scope: CustomerIntelligenceRefreshScope,
    ) -> CustomerIntelligenceCommittedEventRequest: ...

    def enqueue_committed_event_refresh_after_commit(
        self,
        *,
        event: CustomerIntelligenceEvent,
        scope: CustomerIntelligenceRefreshScope,
    ) -> CustomerIntelligenceCommittedEventRequest: ...

    def kick_committed_event_refresh(
        self,
        request: CustomerIntelligenceCommittedEventRequest,
    ) -> None: ...

logger = logging.getLogger(__name__)


class CustomerIntelligenceEventPublicationService:
    """Publish an already-built event without coupling callers to scheduling.

    The interface deliberately separates two moments:

    * ``persist_in_transaction`` records the durable run while the source
      transaction is still open;
    * ``enqueue_after_commit`` records the run in an independent transaction
      for source writes that have already committed, then kicks the
      worker for low latency.

    Both paths are best-effort from the source business module's perspective:
    reconciliation can repair a missing refresh, while a profile problem must
    not roll back a customer, journey, task, or commitment write.
    """

    def __init__(self, *, refresh_service: CustomerIntelligenceRefreshPort | None = None) -> None:
        self._refresh_service = refresh_service

    def _scheduler(self) -> CustomerIntelligenceRefreshPort:
        if self._refresh_service is not None:
            return self._refresh_service
        from app.services.customer_intelligence_refresh_service import customer_intelligence_refresh_service

        return customer_intelligence_refresh_service

    async def trigger_committed_event_refresh(
        self,
        db: Session,
        *,
        event: CustomerIntelligenceEvent | None,
        scope: CustomerIntelligenceRefreshScope = "partial",
    ) -> CustomerIntelligenceCommittedEventRequest | None:
        """Start a committed event through the publication seam.

        This operation is intentionally thin: business-object
        modules construct the event, while the scheduler remains the owner of
        durable run registration and liveness.  Keeping the call here prevents
        callers from reaching around the event publication module to a global
        refresh singleton.
        """

        if event is None:
            return None
        return await self._scheduler().trigger_committed_event_refresh(
            db,
            event=event,
            scope=scope,
        )

    def persist_in_transaction_request(
        self,
        db: Session,
        *,
        event: CustomerIntelligenceEvent | None,
        scope: CustomerIntelligenceRefreshScope = "partial",
    ) -> CustomerIntelligenceCommittedEventRequest | None:
        """Register ``event`` and return its explicit in-transaction outcome.

        The returned request is marked ``kick_required=False`` because the
        source transaction is still open.  Callers that need low latency must
        kick only after their own commit; reconciliation remains authoritative.
        """

        if event is None:
            return None
        from app.services.customer_intelligence_refresh_service import CustomerIntelligenceCommittedEventRequest

        request_id = f"business-event-{event.trigger_type}-{event.event_key[:16]}"
        try:
            with db.begin_nested():
                request = self._scheduler().enqueue_committed_event_refresh(
                    db,
                    event=event,
                    scope=scope,
                )
            if is_dataclass(request):
                return replace(request, kick_required=False)
            # The scheduler contract returns CustomerIntelligenceCommittedEventRequest;
            # lightweight test doubles may return the same structural value.
            return request
        except Exception as exc:  # pragma: no cover - defensive persistence boundary
            error = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "登记客户智能事件失败, 将由对账机制补偿: event_key=%s team_id=%s customer_id=%s",
                event.event_key,
                event.team_id,
                event.customer_id,
            )
            return CustomerIntelligenceCommittedEventRequest(
                request_id=request_id,
                event=event,
                scope=scope,
                scheduled=False,
                kick_required=False,
                schedule_error=error,
            )

    def persist_in_transaction(
        self,
        db: Session,
        *,
        event: CustomerIntelligenceEvent | None,
        scope: CustomerIntelligenceRefreshScope = "partial",
    ) -> str | None:
        """Register ``event`` inside an isolated savepoint.

        Returns a human-readable error for observability and never raises a
        projection persistence failure into the source business transaction.
        """

        request = self.persist_in_transaction_request(db, event=event, scope=scope)
        return request.schedule_error if request is not None else None

    def enqueue_after_commit(
        self,
        *,
        event: CustomerIntelligenceEvent,
        scope: CustomerIntelligenceRefreshScope = "partial",
    ) -> CustomerIntelligenceCommittedEventRequest:
        """Persist a receipt after the source commit without raising into callers.

        CRUD methods call this after their own transaction has committed.
        A scheduler outage must therefore become an observable unscheduled
        request, not a failed customer/contact/opportunity response.
        """

        scheduler = self._scheduler()
        request_id = f"business-event-{event.trigger_type}-{event.event_key[:16]}"
        try:
            request = scheduler.enqueue_committed_event_refresh_after_commit(
                event=event,
                scope=scope,
            )
        except Exception as exc:  # pragma: no cover - defensive post-commit boundary
            error = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "客户智能提交后持久化失败, 将由对账机制补偿: event_key=%s team_id=%s customer_id=%s",
                event.event_key,
                event.team_id,
                event.customer_id,
            )
            from app.services.customer_intelligence_refresh_service import CustomerIntelligenceCommittedEventRequest

            return CustomerIntelligenceCommittedEventRequest(
                request_id=request_id,
                event=event,
                scope=scope,
                scheduled=False,
                kick_required=False,
                schedule_error=error,
            )

        if not request.scheduled:
            return request
        try:
            scheduler.kick_committed_event_refresh(request)
        except Exception as exc:  # pragma: no cover - defensive liveness boundary
            error = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "客户智能提交后唤醒失败, 保留持久运行等待恢复: event_key=%s request_id=%s",
                event.event_key,
                request.request_id,
            )
            return replace(request, kick_required=False, schedule_error=error)
        return request

    def kick_after_commit(
        self,
        *,
        event: CustomerIntelligenceEvent | None,
        scope: CustomerIntelligenceRefreshScope = "partial",
    ) -> str | None:
        """Persist/kick an event whose source transaction has already committed."""

        if event is None:
            return None
        try:
            request = self.enqueue_after_commit(event=event, scope=scope)
            return request.schedule_error
        except Exception as exc:  # pragma: no cover - defensive post-commit boundary
            error = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "客户智能事件提交后调度失败: event_key=%s team_id=%s customer_id=%s",
                event.event_key,
                event.team_id,
                event.customer_id,
            )
            return error


customer_intelligence_event_publication_service = CustomerIntelligenceEventPublicationService()

"""Customer intelligence refresh entrypoint.

Page buttons, background retries, and future admin jobs should emit a customer
intelligence event here instead of orchestrating profile and brief services
directly. The LangGraph runtime owns the refresh sequence.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import exists, func, or_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.database import SessionLocal
from app.crud.customer import customer_crud
from app.models.contract import Contract
from app.models.customer import Contact, Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_intelligence_run import CustomerIntelligenceRun, CustomerIntelligenceRunStatus
from app.models.deployment import DeploymentInfo
from app.models.invoice import InvoiceApplication, InvoiceTitle
from app.models.license_application import LicenseApplication
from app.models.opportunity import Opportunity
from app.services.agent.customer_intelligence_graph import (
    CustomerIntelligenceGraphService,
    customer_intelligence_graph_service,
)
from app.services.agent.types import JSONDict
from app.services.customer_intelligence_event_service import (
    CustomerIntelligenceEvent,
    CustomerIntelligenceEventService,
    CustomerIntelligenceSource,
    CustomerIntelligenceTriggerType,
    JsonObject,
    customer_intelligence_event_service,
)
from app.services.customer_intelligence_run_service import (
    CustomerIntelligenceRunInput,
    CustomerIntelligenceRunService,
    customer_intelligence_run_service,
)
from app.services.customer_identity_resolution_service import (
    CustomerIdentityResolutionService,
    customer_identity_resolution_service,
)
from app.services.customer_vector_document_service import (
    CustomerVectorDocumentService,
    customer_vector_document_service,
)
from app.utils.time import business_now

logger = logging.getLogger(__name__)

CustomerIntelligenceRefreshScope = Literal["full", "brief"]
CustomerIntelligenceRefreshTrigger = Literal[
    "manual_refresh_requested",
    "customer_intelligence_batch_rebuild_requested",
    "customer_intelligence_historical_backfill_requested",
    "customer_created",
    "customer_converted_from_lead",
]
CustomerIntelligenceBusinessObjectChangeType = Literal["created", "updated", "deleted"]
CUSTOMER_INTELLIGENCE_STALE_STATUS_AFTER = timedelta(minutes=10)


@dataclass(frozen=True)
class CustomerIntelligenceRefreshRequest:
    team_id: int
    customer_id: int
    actor_id: str | None
    scope: CustomerIntelligenceRefreshScope
    request_id: str
    trigger_type: CustomerIntelligenceRefreshTrigger = "manual_refresh_requested"
    source_lead_id: int | None = None


@dataclass(frozen=True)
class CustomerIntelligenceCommittedEventRequest:
    request_id: str
    event: CustomerIntelligenceEvent
    scope: CustomerIntelligenceRefreshScope
    scheduled: bool = True
    schedule_error: str | None = None


@dataclass(frozen=True)
class CustomerIntelligenceBatchRebuildResult:
    success: bool
    request_id: str
    team_id: int
    scope: CustomerIntelligenceRefreshScope
    total: int
    scheduled: int
    customer_ids: list[int]


@dataclass(frozen=True)
class CustomerIntelligenceHistoricalBackfillResult:
    success: bool
    request_id: str
    scope: CustomerIntelligenceRefreshScope
    total: int
    scheduled: int
    customer_ids: list[int]
    profile_vector_reindexed: int = 0
    profile_vector_customer_ids: tuple[int, ...] = ()
    identity_terms_reindexed: int = 0
    identity_term_customer_ids: tuple[int, ...] = ()


class CustomerIntelligenceRefreshService:
    def __init__(
        self,
        *,
        graph_service: CustomerIntelligenceGraphService | None = None,
        event_service: CustomerIntelligenceEventService | None = None,
        run_service: CustomerIntelligenceRunService | None = None,
        vector_document_service: CustomerVectorDocumentService | None = None,
        identity_resolution_service: CustomerIdentityResolutionService | None = None,
    ) -> None:
        self.graph_service = graph_service or customer_intelligence_graph_service
        self.event_service = event_service or customer_intelligence_event_service
        self.run_service = run_service or customer_intelligence_run_service
        self.vector_document_service = vector_document_service or customer_vector_document_service
        self.identity_resolution_service = identity_resolution_service or customer_identity_resolution_service

    async def trigger_committed_event_refresh(
        self,
        db: Session,
        *,
        event: CustomerIntelligenceEvent,
        scope: CustomerIntelligenceRefreshScope = "brief",
    ) -> CustomerIntelligenceCommittedEventRequest:
        request = CustomerIntelligenceCommittedEventRequest(
            request_id=f"business-event-{event.trigger_type}-{uuid4().hex}",
            event=event,
            scope=scope,
        )
        scheduled_request = self._schedule_committed_event_run(request)
        if scheduled_request.scheduled:
            asyncio.create_task(self.run_committed_event_refresh(scheduled_request))
        return scheduled_request

    def enqueue_committed_event_refresh(
        self,
        db: Session,
        *,
        event: CustomerIntelligenceEvent,
        scope: CustomerIntelligenceRefreshScope = "brief",
    ) -> CustomerIntelligenceCommittedEventRequest:
        request = CustomerIntelligenceCommittedEventRequest(
            request_id=f"business-event-{event.trigger_type}-{event.event_key[:16]}",
            event=event,
            scope=scope,
        )
        self._mark_pending_event(db, request)
        self._ensure_pending_event_run(db, request)
        return request

    async def trigger_business_object_change_refresh(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        actor_id: str | None,
        source_type: str,
        source_id: int,
        change_type: CustomerIntelligenceBusinessObjectChangeType,
        summary: str,
        payload: JsonObject | None = None,
    ) -> CustomerIntelligenceCommittedEventRequest:
        trigger_type = self._business_object_change_trigger_type(change_type)
        event = self.event_service.business_object_changed(
            team_id=team_id,
            customer_id=customer_id,
            actor_id=actor_id,
            trigger_type=trigger_type,
            source_type=source_type,
            source_id=source_id,
            change_id=uuid4().hex,
            summary=summary,
            payload=payload,
            occurred_at=business_now(),
        )
        return await self.trigger_committed_event_refresh(
            db,
            event=event,
            scope="brief",
        )

    def enqueue_business_object_change_refresh(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        actor_id: str | None,
        source_type: str,
        source_id: int,
        change_type: CustomerIntelligenceBusinessObjectChangeType,
        summary: str,
        payload: JsonObject | None = None,
    ) -> CustomerIntelligenceCommittedEventRequest:
        trigger_type = self._business_object_change_trigger_type(change_type)
        event = self.event_service.business_object_changed(
            team_id=team_id,
            customer_id=customer_id,
            actor_id=actor_id,
            trigger_type=trigger_type,
            source_type=source_type,
            source_id=source_id,
            change_id=uuid4().hex,
            summary=summary,
            payload=payload,
            occurred_at=business_now(),
        )
        return self.enqueue_committed_event_refresh(
            db,
            event=event,
            scope="brief",
        )

    def _business_object_change_trigger_type(
        self,
        change_type: CustomerIntelligenceBusinessObjectChangeType,
    ) -> Literal[
        "customer_business_object_created",
        "customer_business_object_updated",
        "customer_business_object_deleted",
    ]:
        if change_type == "created":
            return "customer_business_object_created"
        if change_type == "updated":
            return "customer_business_object_updated"
        return "customer_business_object_deleted"

    async def trigger_manual_refresh(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        actor_id: str | None,
        scope: CustomerIntelligenceRefreshScope,
    ) -> CustomerIntelligenceRefreshRequest:
        request = CustomerIntelligenceRefreshRequest(
            team_id=team_id,
            customer_id=customer_id,
            actor_id=actor_id,
            scope=scope,
            request_id=f"manual-refresh-{uuid4().hex}",
            trigger_type="manual_refresh_requested",
        )
        self._mark_pending(db, request)
        self._ensure_pending_run(db, request)
        self._commit_pending_schedule(db, request)
        asyncio.create_task(self.run_refresh(request))
        return request

    async def trigger_customer_created_refresh(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        actor_id: str | None,
        source_lead_id: int | None = None,
    ) -> CustomerIntelligenceRefreshRequest:
        trigger_type: CustomerIntelligenceRefreshTrigger = (
            "customer_converted_from_lead" if source_lead_id is not None else "customer_created"
        )
        request = CustomerIntelligenceRefreshRequest(
            team_id=team_id,
            customer_id=customer_id,
            actor_id=actor_id,
            scope="full",
            request_id=f"{trigger_type}-{uuid4().hex}",
            trigger_type=trigger_type,
            source_lead_id=source_lead_id,
        )
        self.identity_resolution_service.rebuild_customer_identity_terms(
            db,
            team_id=team_id,
            customer_id=customer_id,
        )
        self._mark_pending(db, request)
        self._ensure_pending_run(db, request)
        self._commit_pending_schedule(db, request)
        asyncio.create_task(self.run_refresh(request))
        return request

    async def trigger_batch_rebuild(
        self,
        db: Session,
        *,
        team_id: int,
        actor_id: str | None,
        scope: CustomerIntelligenceRefreshScope,
        customer_ids: list[int] | None = None,
        limit: int = 100,
    ) -> CustomerIntelligenceBatchRebuildResult:
        target_customer_ids = self._select_batch_customer_ids(
            db,
            team_id=team_id,
            customer_ids=customer_ids,
            limit=limit,
        )
        request_id = f"batch-rebuild-{uuid4().hex}"
        for customer_id in target_customer_ids:
            request = CustomerIntelligenceRefreshRequest(
                team_id=team_id,
                customer_id=customer_id,
                actor_id=actor_id,
                scope=scope,
                request_id=request_id,
                trigger_type="customer_intelligence_batch_rebuild_requested",
            )
            self._mark_pending(db, request)
            self._ensure_pending_run(db, request)
        self._commit_pending_schedule(db, request_id=request_id)
        for customer_id in target_customer_ids:
            request = CustomerIntelligenceRefreshRequest(
                team_id=team_id,
                customer_id=customer_id,
                actor_id=actor_id,
                scope=scope,
                request_id=request_id,
                trigger_type="customer_intelligence_batch_rebuild_requested",
            )
            asyncio.create_task(self.run_refresh(request))
        return CustomerIntelligenceBatchRebuildResult(
            success=True,
            request_id=request_id,
            team_id=team_id,
            scope=scope,
            total=len(target_customer_ids),
            scheduled=len(target_customer_ids),
            customer_ids=target_customer_ids,
        )

    async def trigger_missing_historical_backfill(
        self,
        db: Session,
        *,
        team_id: int | None = None,
        limit: int = 20,
        schedule_runs: bool = True,
    ) -> CustomerIntelligenceHistoricalBackfillResult:
        self.recover_stale_runtime_state(db, team_id=team_id)
        profile_vector_customer_ids = self.vector_document_service.rebuild_stale_customer_profiles(
            db,
            team_id=team_id,
            limit=limit,
            commit=False,
        )
        identity_term_customer_ids = self.identity_resolution_service.rebuild_team_identity_terms(
            db,
            team_id=team_id,
            limit=limit,
        )
        target_customer_ids = self._select_missing_historical_customer_ids(
            db,
            team_id=team_id,
            limit=limit,
        )
        request_id = f"historical-backfill-{uuid4().hex}"
        requests: list[CustomerIntelligenceRefreshRequest] = []
        for customer_id in target_customer_ids:
            customer_team_id = self._customer_team_id(db, customer_id)
            if customer_team_id is None:
                continue
            request = CustomerIntelligenceRefreshRequest(
                team_id=customer_team_id,
                customer_id=customer_id,
                actor_id=None,
                scope="full",
                request_id=request_id,
                trigger_type="customer_intelligence_historical_backfill_requested",
            )
            requests.append(request)
            self._mark_pending(db, request)
            self._ensure_pending_run(db, request)
        if schedule_runs:
            for request in requests:
                asyncio.create_task(self.run_refresh(request))
        return CustomerIntelligenceHistoricalBackfillResult(
            success=True,
            request_id=request_id,
            scope="full",
            total=len(requests),
            scheduled=len(requests),
            customer_ids=[request.customer_id for request in requests],
            profile_vector_reindexed=len(profile_vector_customer_ids),
            profile_vector_customer_ids=tuple(profile_vector_customer_ids),
            identity_terms_reindexed=len(identity_term_customer_ids),
            identity_term_customer_ids=tuple(identity_term_customer_ids),
        )

    async def run_refresh(self, request: CustomerIntelligenceRefreshRequest) -> JSONDict:
        event = self._build_event(request)
        return await self._run_event_refresh(
            request_id=request.request_id,
            event=event,
            scope=request.scope,
        )

    async def run_committed_event_refresh(self, request: CustomerIntelligenceCommittedEventRequest) -> JSONDict:
        return await self._run_event_refresh(
            request_id=request.request_id,
            event=request.event,
            scope=request.scope,
        )

    async def _run_event_refresh(
        self,
        *,
        request_id: str,
        event: CustomerIntelligenceEvent,
        scope: CustomerIntelligenceRefreshScope,
    ) -> JSONDict:
        run_input = CustomerIntelligenceRunInput(
            request_id=request_id,
            event=event,
            scope=scope,
        )
        try:
            self._mark_run_running(run_input)
        except Exception as exc:
            logger.exception(
                "客户智能刷新运行状态标记失败: team_id=%s, customer_id=%s, trigger_type=%s, scope=%s, request_id=%s",
                event.team_id,
                event.customer_id,
                event.trigger_type,
                scope,
                request_id,
            )
            self._mark_failed_event(event=event, scope=scope, request_id=request_id, error_message=str(exc))
            return {
                "success": False,
                "request_id": request_id,
                "error": str(exc),
            }

        try:
            result = await self.graph_service.run({
                "team_id": event.team_id,
                "user_id": _actor_user_id(event.actor_id),
                "session_id": 0,
                "event": event,
            })
            self._mark_run_succeeded(run_input, result=result)
            return {
                "success": True,
                "request_id": request_id,
                "event_key": event.event_key,
                "route": str(result.get("route") or ""),
            }
        except Exception as exc:
            logger.exception(
                "客户智能刷新失败: team_id=%s, customer_id=%s, trigger_type=%s, scope=%s, request_id=%s",
                event.team_id,
                event.customer_id,
                event.trigger_type,
                scope,
                request_id,
            )
            try:
                self._mark_run_failed(run_input, error_message=str(exc))
            except Exception:
                logger.exception(
                    "记录客户智能运行失败状态失败: customer_id=%s, request_id=%s",
                    event.customer_id,
                    request_id,
                )
            self._mark_failed_event(event=event, scope=scope, request_id=request_id, error_message=str(exc))
            return {
                "success": False,
                "request_id": request_id,
                "error": str(exc),
            }

    def _mark_run_running(self, run_input: CustomerIntelligenceRunInput) -> None:
        db = SessionLocal()
        try:
            self.run_service.mark_running(db, run_input)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _mark_run_succeeded(self, run_input: CustomerIntelligenceRunInput, *, result: JSONDict) -> None:
        db = SessionLocal()
        try:
            self.run_service.mark_succeeded(db, run_input, result=result)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _mark_run_failed(self, run_input: CustomerIntelligenceRunInput, *, error_message: str) -> None:
        db = SessionLocal()
        try:
            self.run_service.mark_failed(db, run_input, error_message=error_message)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def run_manual_refresh(self, request: CustomerIntelligenceRefreshRequest) -> JSONDict:
        return await self.run_refresh(request)

    async def run_due_retries(self, *, team_id: int | None = None, limit: int = 20) -> JSONDict:
        db = SessionLocal()
        try:
            recovered = self.recover_stale_runtime_state(db, team_id=team_id)
            db.commit()
            retry_requests = [
                _request_from_run(run)
                for run in self.run_service.list_due(db, team_id=team_id, limit=limit)
            ]
        finally:
            db.close()

        results: list[JSONDict] = []
        for request in retry_requests:
            if isinstance(request, CustomerIntelligenceCommittedEventRequest):
                results.append(await self.run_committed_event_refresh(request))
            else:
                results.append(await self.run_refresh(request))
        return {
            "success": True,
            "recovered": recovered,
            "total": len(results),
            "succeeded": sum(1 for result in results if result.get("success") is True),
            "failed": sum(1 for result in results if result.get("success") is not True),
            "results": results,
        }

    def recover_stale_runtime_state(self, db: Session, *, team_id: int | None = None) -> JSONDict:
        """Align stuck customer-facing statuses with persisted run state.

        The run table remains the durable audit/retry boundary. Customer rows are
        a UI projection and must not stay in GENERATING forever after a worker
        restart or interrupted background run.
        """
        if not hasattr(db, "query"):
            return {
                "stale_runs": 0,
                "pending_customers": 0,
                "failed_customers": 0,
            }
        current_time = business_now()
        obsolete_historical_runs = self._close_obsolete_historical_backfill_runs(
            db,
            team_id=team_id,
            finished_at=current_time,
        )
        stale_running_started_before = current_time - CUSTOMER_INTELLIGENCE_STALE_STATUS_AFTER

        stale_query = db.query(CustomerIntelligenceRun).filter(
            CustomerIntelligenceRun.status == CustomerIntelligenceRunStatus.RUNNING,
            CustomerIntelligenceRun.started_time <= stale_running_started_before,
        )
        if team_id is not None:
            stale_query = stale_query.filter(CustomerIntelligenceRun.team_id == team_id)

        stale_runs = stale_query.limit(200).all()
        stale_count = 0
        for run in stale_runs:
            attempts = int(run.attempt_count or 0)
            if attempts < int(run.max_attempts or 1):
                run.status = CustomerIntelligenceRunStatus.RETRY_PENDING
                run.next_retry_at = current_time
                run.error_message = "上一次客户智能档案刷新未正常结束，已自动恢复为待重试。"
            else:
                run.status = CustomerIntelligenceRunStatus.FAILED
                run.finished_time = current_time
                run.next_retry_at = None
                run.error_message = "上一次客户智能档案刷新未正常结束，且已达到最大重试次数。"
            stale_count += 1

        retryable_customer_ids = self._customer_ids_with_runs(
            db,
            statuses=[
                CustomerIntelligenceRunStatus.PENDING,
                CustomerIntelligenceRunStatus.RETRY_PENDING,
            ],
            team_id=team_id,
        )
        failed_customer_ids = self._customer_ids_with_runs(
            db,
            statuses=[CustomerIntelligenceRunStatus.FAILED],
            team_id=team_id,
        ) - retryable_customer_ids

        pending_updates = self._reset_generating_customers(
            db,
            customer_ids=retryable_customer_ids,
            status="PENDING",
            error_message=None,
        )
        failed_updates = self._reset_generating_customers(
            db,
            customer_ids=failed_customer_ids,
            status="FAILED",
            error_message="客户智能档案刷新失败，等待下一次业务触发或重建。",
        )
        return {
            "obsolete_historical_runs": obsolete_historical_runs,
            "stale_runs": stale_count,
            "pending_customers": pending_updates,
            "failed_customers": failed_updates,
        }

    def _close_obsolete_historical_backfill_runs(
        self,
        db: Session,
        *,
        team_id: int | None,
        finished_at: datetime,
    ) -> int:
        """Close historical backfill runs already satisfied by a customer brief.

        Historical backfill is a gap-filling runtime. If a newer run or manual
        refresh has already written a non-empty customer brief, old backfill
        runs must stop owning retry/runtime decisions for that customer.
        """
        active_statuses = [
            CustomerIntelligenceRunStatus.PENDING,
            CustomerIntelligenceRunStatus.RUNNING,
            CustomerIntelligenceRunStatus.RETRY_PENDING,
        ]
        query = (
            db.query(CustomerIntelligenceRun)
            .join(
                Customer,
                (Customer.team_id == CustomerIntelligenceRun.team_id)
                & (Customer.id == CustomerIntelligenceRun.customer_id),
            )
            .filter(
                CustomerIntelligenceRun.trigger_type == "customer_intelligence_historical_backfill_requested",
                CustomerIntelligenceRun.status.in_(active_statuses),
                Customer.customer_brief_markdown.isnot(None),
                func.length(func.trim(Customer.customer_brief_markdown)) > 0,
            )
        )
        if team_id is not None:
            query = query.filter(CustomerIntelligenceRun.team_id == team_id)

        closed = 0
        for run in query.limit(500).all():
            run.status = CustomerIntelligenceRunStatus.CANCELLED
            run.finished_time = finished_at
            run.next_retry_at = None
            run.error_message = None
            run.route = run.route or "historical_backfill_satisfied"
            run.result_json = {
                "route": "historical_backfill_satisfied",
                "reason": "customer_brief_already_available",
            }
            closed += 1
        if closed > 0:
            db.flush()
        return closed

    def _customer_ids_with_runs(
        self,
        db: Session,
        *,
        statuses: list[str],
        team_id: int | None,
    ) -> set[int]:
        query = db.query(CustomerIntelligenceRun.customer_id).filter(
            CustomerIntelligenceRun.status.in_(statuses),
        )
        if team_id is not None:
            query = query.filter(CustomerIntelligenceRun.team_id == team_id)
        return {int(row[0]) for row in query.all()}

    def _reset_generating_customers(
        self,
        db: Session,
        *,
        customer_ids: set[int],
        status: str,
        error_message: str | None,
    ) -> int:
        if not customer_ids:
            return 0
        customers = db.query(Customer).filter(Customer.id.in_(sorted(customer_ids))).all()
        updated = 0
        for customer in customers:
            touched = False
            if customer.profile_status == "GENERATING":
                customer.profile_status = status
                customer.profile_error_message = error_message
                touched = True
            if customer.customer_brief_status == "GENERATING":
                customer.customer_brief_status = status
                customer.customer_brief_error_message = error_message
                touched = True
            if touched:
                customer.version = int(customer.version or 0) + 1
                updated += 1
        db.flush()
        return updated

    def _build_event(self, request: CustomerIntelligenceRefreshRequest) -> CustomerIntelligenceEvent:
        occurred_at = business_now()
        if request.trigger_type == "manual_refresh_requested":
            return self.event_service.manual_refresh_requested(
                team_id=request.team_id,
                customer_id=request.customer_id,
                actor_id=request.actor_id,
                request_id=request.request_id,
                refresh_scope=request.scope,
                occurred_at=occurred_at,
            )
        if request.trigger_type == "customer_intelligence_batch_rebuild_requested":
            return self.event_service.batch_rebuild_requested(
                team_id=request.team_id,
                customer_id=request.customer_id,
                actor_id=request.actor_id,
                request_id=request.request_id,
                refresh_scope=request.scope,
                occurred_at=occurred_at,
            )
        if request.trigger_type == "customer_intelligence_historical_backfill_requested":
            return self.event_service.historical_backfill_requested(
                team_id=request.team_id,
                customer_id=request.customer_id,
                request_id=request.request_id,
                refresh_scope=request.scope,
                occurred_at=occurred_at,
            )
        return self.event_service.customer_lifecycle_refresh_requested(
            team_id=request.team_id,
            customer_id=request.customer_id,
            actor_id=request.actor_id,
            request_id=request.request_id,
            trigger_type=request.trigger_type,
            source_lead_id=request.source_lead_id,
            occurred_at=occurred_at,
        )

    def _mark_pending(self, db: Session, request: CustomerIntelligenceRefreshRequest) -> None:
        if request.scope == "full":
            customer_crud.update_profile_status(db, request.customer_id, "PENDING")
        customer_crud.update_customer_brief_status(db, request.customer_id, "PENDING")

    def _mark_pending_event(self, db: Session, request: CustomerIntelligenceCommittedEventRequest) -> None:
        if request.scope == "full":
            customer_crud.update_profile_status(db, request.event.customer_id, "PENDING")
        customer_crud.update_customer_brief_status(db, request.event.customer_id, "PENDING")

    def _ensure_pending_run(self, db: Session, request: CustomerIntelligenceRefreshRequest) -> None:
        event = self._build_event(request)
        self.run_service.ensure_pending(
            db,
            CustomerIntelligenceRunInput(
                request_id=request.request_id,
                event=event,
                scope=request.scope,
            ),
        )

    def _ensure_pending_event_run(self, db: Session, request: CustomerIntelligenceCommittedEventRequest) -> None:
        self.run_service.ensure_pending(
            db,
            CustomerIntelligenceRunInput(
                request_id=request.request_id,
                event=request.event,
                scope=request.scope,
            ),
        )

    def _commit_pending_schedule(
        self,
        db: Session,
        request: CustomerIntelligenceRefreshRequest | None = None,
        *,
        request_id: str | None = None,
    ) -> None:
        try:
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                logger.exception(
                    "回滚客户智能刷新调度事务失败: request_id=%s",
                    request.request_id if request else request_id,
                )
            if request is not None:
                logger.exception(
                    "客户智能刷新调度提交失败: team_id=%s, customer_id=%s, trigger_type=%s, scope=%s, request_id=%s",
                    request.team_id,
                    request.customer_id,
                    request.trigger_type,
                    request.scope,
                    request.request_id,
                )
            else:
                logger.exception("客户智能批量刷新调度提交失败: request_id=%s", request_id)
            raise

    def _schedule_committed_event_run(
        self,
        request: CustomerIntelligenceCommittedEventRequest,
    ) -> CustomerIntelligenceCommittedEventRequest:
        db = SessionLocal()
        try:
            self._mark_pending_event(db, request)
            self._ensure_pending_event_run(db, request)
            db.commit()
            return request
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                logger.exception(
                    "回滚客户智能刷新调度事务失败: customer_id=%s, request_id=%s",
                    request.event.customer_id,
                    request.request_id,
                )
            logger.exception(
                "客户智能刷新调度失败，已隔离为非阻塞事件: team_id=%s, customer_id=%s, trigger_type=%s, scope=%s, request_id=%s",
                request.event.team_id,
                request.event.customer_id,
                request.event.trigger_type,
                request.scope,
                request.request_id,
            )
            return CustomerIntelligenceCommittedEventRequest(
                request_id=request.request_id,
                event=request.event,
                scope=request.scope,
                scheduled=False,
                schedule_error=str(exc),
            )
        finally:
            db.close()

    def _mark_failed(self, request: CustomerIntelligenceRefreshRequest, error_message: str) -> None:
        self._mark_failed_event(
            event=self._build_event(request),
            scope=request.scope,
            request_id=request.request_id,
            error_message=error_message,
        )

    def _mark_failed_event(
        self,
        *,
        event: CustomerIntelligenceEvent,
        scope: CustomerIntelligenceRefreshScope,
        request_id: str,
        error_message: str,
    ) -> None:
        db = SessionLocal()
        try:
            if scope == "full":
                customer_crud.update_profile_status(db, event.customer_id, "FAILED", error_message)
            customer_crud.update_customer_brief_status(db, event.customer_id, "FAILED", error_message)
        except Exception:
            logger.exception(
                "标记客户智能手动刷新失败状态失败: customer_id=%s, request_id=%s",
                event.customer_id,
                request_id,
            )
        finally:
            db.close()

    def _select_batch_customer_ids(
        self,
        db: Session,
        *,
        team_id: int,
        customer_ids: list[int] | None,
        limit: int,
    ) -> list[int]:
        query = db.query(Customer.id).filter(Customer.team_id == team_id)
        if customer_ids is not None:
            normalized_ids = sorted({customer_id for customer_id in customer_ids if customer_id > 0})
            if not normalized_ids:
                return []
            query = query.filter(Customer.id.in_(normalized_ids))
        return [
            int(row[0])
            for row in query.order_by(Customer.id.asc()).limit(max(1, min(limit, 500))).all()
        ]

    def _select_missing_historical_customer_ids(
        self,
        db: Session,
        *,
        team_id: int | None,
        limit: int,
    ) -> list[int]:
        query = db.query(Customer.id).filter(
            self._missing_customer_intelligence_brief_filter(),
            self._has_customer_business_data_filter(),
            ~self._has_active_customer_intelligence_run_filter(),
        )
        if team_id is not None:
            query = query.filter(Customer.team_id == team_id)
        return [
            int(row[0])
            for row in query.order_by(Customer.id.asc()).limit(max(1, min(limit, 500))).all()
        ]

    def has_customer_business_data(self, db: Session, *, customer_id: int, team_id: int) -> bool:
        return bool(
            db.query(Customer.id)
            .filter(
                Customer.id == customer_id,
                Customer.team_id == team_id,
                self._has_customer_business_data_filter(),
            )
            .first()
        )

    def _customer_team_id(self, db: Session, customer_id: int) -> int | None:
        row = db.query(Customer.team_id).filter(Customer.id == customer_id).one_or_none()
        if row is None:
            return None
        return int(row[0])

    def _missing_customer_intelligence_brief_filter(self) -> ColumnElement[bool]:
        return or_(
            Customer.customer_brief_markdown.is_(None),
            func.length(func.trim(Customer.customer_brief_markdown)) == 0,
        )

    def _has_active_customer_intelligence_run_filter(self) -> ColumnElement[bool]:
        return exists().where(
            CustomerIntelligenceRun.team_id == Customer.team_id,
            CustomerIntelligenceRun.customer_id == Customer.id,
            CustomerIntelligenceRun.status.in_([
                CustomerIntelligenceRunStatus.PENDING,
                CustomerIntelligenceRunStatus.RUNNING,
                CustomerIntelligenceRunStatus.RETRY_PENDING,
            ]),
        )

    def _has_customer_business_data_filter(self) -> ColumnElement[bool]:
        return or_(
            exists().where(Contact.team_id == Customer.team_id, Contact.customer_id == Customer.id),
            exists().where(CustomerActivity.team_id == Customer.team_id, CustomerActivity.customer_id == Customer.id),
            exists().where(Opportunity.team_id == Customer.team_id, Opportunity.customer_id == Customer.id),
            exists().where(
                Contract.team_id == Customer.team_id,
                Contract.customer_id == Customer.id,
                Contract.deleted_at.is_(None),
            ),
            exists().where(InvoiceTitle.team_id == Customer.team_id, InvoiceTitle.customer_id == Customer.id),
            exists().where(
                InvoiceApplication.team_id == Customer.team_id,
                InvoiceApplication.customer_id == Customer.id,
            ),
            exists().where(DeploymentInfo.team_id == Customer.team_id, DeploymentInfo.customer_id == Customer.id),
            exists().where(
                LicenseApplication.team_id == Customer.team_id,
                LicenseApplication.customer_id == Customer.id,
            ),
        )


def _actor_user_id(actor_id: str | None) -> int:
    if actor_id is None:
        return 0
    try:
        return int(actor_id)
    except ValueError:
        return 0


def _request_from_run(
    run: CustomerIntelligenceRun,
) -> CustomerIntelligenceRefreshRequest | CustomerIntelligenceCommittedEventRequest:
    committed_event = _committed_event_request_from_run(run)
    if committed_event is not None:
        return committed_event
    event_json = run.event_json if isinstance(run.event_json, dict) else {}
    payload = event_json.get("payload") if isinstance(event_json.get("payload"), dict) else {}
    trigger_type = cast(CustomerIntelligenceRefreshTrigger, str(run.trigger_type))
    if trigger_type not in {
        "manual_refresh_requested",
        "customer_intelligence_batch_rebuild_requested",
        "customer_intelligence_historical_backfill_requested",
        "customer_created",
        "customer_converted_from_lead",
    }:
        trigger_type = "manual_refresh_requested"
    scope = cast(CustomerIntelligenceRefreshScope, str(run.scope))
    if scope not in {"full", "brief"}:
        scope = "full"
    return CustomerIntelligenceRefreshRequest(
        team_id=int(run.team_id),
        customer_id=int(run.customer_id),
        actor_id=str(run.actor_id) if run.actor_id is not None else None,
        scope=scope,
        request_id=str(run.request_id),
        trigger_type=trigger_type,
        source_lead_id=_positive_int(payload.get("source_lead_id")),
    )


def _committed_event_request_from_run(run: CustomerIntelligenceRun) -> CustomerIntelligenceCommittedEventRequest | None:
    if run.trigger_type in {
        "manual_refresh_requested",
        "customer_intelligence_batch_rebuild_requested",
        "customer_intelligence_historical_backfill_requested",
        "customer_created",
        "customer_converted_from_lead",
    }:
        return None
    event_json = run.event_json if isinstance(run.event_json, dict) else {}
    event = _event_from_json(event_json)
    if event is None:
        return None
    scope = cast(CustomerIntelligenceRefreshScope, str(run.scope))
    if scope not in {"full", "brief"}:
        scope = "brief"
    return CustomerIntelligenceCommittedEventRequest(
        request_id=str(run.request_id),
        event=event,
        scope=scope,
    )


def _event_from_json(event_json: JsonObject) -> CustomerIntelligenceEvent | None:
    source_json = event_json.get("source")
    if not isinstance(source_json, dict):
        return None
    event_key = event_json.get("event_key")
    trigger_type = event_json.get("trigger_type")
    tenant_id = _positive_int(event_json.get("tenant_id"))
    team_id = _positive_int(event_json.get("team_id"))
    customer_id = _positive_int(event_json.get("customer_id"))
    if not isinstance(event_key, str) or not isinstance(trigger_type, str):
        return None
    if tenant_id is None or team_id is None or customer_id is None:
        return None
    payload = event_json.get("payload")
    occurred_at = _datetime_from_iso(event_json.get("occurred_at"))
    return CustomerIntelligenceEvent(
        event_key=event_key,
        trigger_type=cast(CustomerIntelligenceTriggerType, trigger_type),
        tenant_id=tenant_id,
        team_id=team_id,
        customer_id=customer_id,
        occurred_at=occurred_at,
        source=CustomerIntelligenceSource(
            source_type=_string_or_empty(source_json.get("source_type")),
            source_object_id=_string_or_empty(source_json.get("source_object_id")),
            business_object_type=_optional_string(source_json.get("business_object_type")),
            business_object_id=_optional_string(source_json.get("business_object_id")),
        ),
        summary=_optional_string(event_json.get("summary")),
        payload=payload if isinstance(payload, dict) else {},
        actor_id=_optional_string(event_json.get("actor_id")),
    )


def _positive_int(value: object) -> int | None:
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def _datetime_from_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_or_empty(value: object) -> str:
    return value if isinstance(value, str) else ""


customer_intelligence_refresh_service = CustomerIntelligenceRefreshService()

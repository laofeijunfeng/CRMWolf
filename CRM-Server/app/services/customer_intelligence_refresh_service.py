"""Customer intelligence refresh entrypoint.

Page buttons, background retries, and future admin jobs should emit a customer
intelligence event here instead of orchestrating profile and brief services
directly. The LangGraph runtime owns the refresh sequence.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import exists, func, or_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.crud.customer import customer_crud
from app.crud.team import team_crud
from app.models.contract import Contract
from app.models.customer import Contact, Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_intelligence_run import CustomerIntelligenceRun, CustomerIntelligenceRunStatus
from app.models.deployment import DeploymentInfo
from app.models.invoice import InvoiceApplication, InvoiceTitle
from app.models.license_application import LicenseApplication
from app.models.opportunity import Opportunity
from app.services.agent.async_operation_service import (
    AgentAsyncOperationService,
    agent_async_operation_service,
)
from app.services.agent.customer_intelligence_graph import (
    CustomerIntelligenceGraphService,
    build_customer_intelligence_thread_id,
    customer_intelligence_graph_service,
)
from app.services.agent.types import JSONDict, coerce_json_dict
from app.services.customer_identity_resolution_service import (
    CustomerIdentityResolutionService,
    customer_identity_resolution_service,
)
from app.services.customer_intelligence_event_service import (
    CustomerIntelligenceEvent,
    CustomerIntelligenceEventService,
    JsonObject,
    customer_intelligence_event_service,
)
from app.services.customer_intelligence_operation_projector import (
    CustomerIntelligenceOperationProjector,
)
from app.services.customer_intelligence_run_service import (
    CustomerIntelligenceRunClaim,
    CustomerIntelligenceRunClaimStatus,
    CustomerIntelligenceRunInput,
    CustomerIntelligenceRunLeaseMutation,
    CustomerIntelligenceRunLeaseMutationStatus,
    CustomerIntelligenceRunService,
    customer_intelligence_run_service,
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
class AgentAsyncOperationBinding:
    team_id: int
    user_id: int
    session_id: int
    source_user_message_id: int | None = None
    source_assistant_message_id: int | None = None


@dataclass(frozen=True)
class CustomerIntelligenceCommittedEventRequest:
    request_id: str
    event: CustomerIntelligenceEvent
    scope: CustomerIntelligenceRefreshScope
    scheduled: bool = True
    kick_required: bool = True
    schedule_error: str | None = None
    operation_public_id: str | None = None
    agent_binding: AgentAsyncOperationBinding | None = None


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
        async_operation_service: AgentAsyncOperationService | None = None,
        operation_projector: CustomerIntelligenceOperationProjector | None = None,
    ) -> None:
        self.graph_service = graph_service or customer_intelligence_graph_service
        self.event_service = event_service or customer_intelligence_event_service
        self.run_service = run_service or customer_intelligence_run_service
        self.vector_document_service = vector_document_service or customer_vector_document_service
        self.identity_resolution_service = identity_resolution_service or customer_identity_resolution_service
        self.async_operation_service = async_operation_service or agent_async_operation_service
        self.operation_projector = operation_projector or CustomerIntelligenceOperationProjector(
            run_service=self.run_service,
            operation_service=self.async_operation_service,
        )

    async def trigger_committed_event_refresh(
        self,
        db: Session,
        *,
        event: CustomerIntelligenceEvent,
        scope: CustomerIntelligenceRefreshScope = "brief",
        agent_binding: AgentAsyncOperationBinding | None = None,
    ) -> CustomerIntelligenceCommittedEventRequest:
        request = CustomerIntelligenceCommittedEventRequest(
            request_id=self._committed_event_request_id(event),
            event=event,
            scope=scope,
            agent_binding=agent_binding,
        )
        scheduled_request = self._schedule_committed_event_run(request)
        if scheduled_request.scheduled and scheduled_request.kick_required:
            asyncio.create_task(self.run_committed_event_refresh(scheduled_request))
        return scheduled_request

    def kick_committed_event_refresh(
        self,
        request: CustomerIntelligenceCommittedEventRequest,
    ) -> None:
        """Best-effort low-latency kick; durable run recovery remains authoritative."""

        task = asyncio.create_task(self.run_committed_event_refresh(request))
        task.add_done_callback(self._consume_background_task_exception)

    @staticmethod
    def _committed_event_request_id(event: CustomerIntelligenceEvent) -> str:
        return f"business-event-{event.trigger_type}-{event.event_key[:16]}"

    @staticmethod
    def _consume_background_task_exception(task: asyncio.Task[JSONDict]) -> None:
        if task.cancelled():
            return
        try:
            task.exception()
        except Exception:
            logger.exception("客户智能后台任务回调失败")

    def enqueue_committed_event_refresh(
        self,
        db: Session,
        *,
        event: CustomerIntelligenceEvent,
        scope: CustomerIntelligenceRefreshScope = "brief",
    ) -> CustomerIntelligenceCommittedEventRequest:
        request = CustomerIntelligenceCommittedEventRequest(
            request_id=self._committed_event_request_id(event),
            event=event,
            scope=scope,
        )
        self._mark_pending_event(db, request)
        self._ensure_pending_event_run(db, request)
        return request

    def bind_committed_event_to_agent(
        self,
        db: Session,
        *,
        team_id: int,
        request_id: str,
        binding: AgentAsyncOperationBinding,
    ) -> CustomerIntelligenceCommittedEventRequest:
        """Bind an already-persisted durable run to its exact Agent turn.

        This is deliberately a projection-only operation: it never reconstructs
        or resets the run lifecycle. Callers own the surrounding transaction and
        may kick the returned request only after that transaction commits.
        """

        if int(binding.team_id) != int(team_id):
            raise ValueError("客户智能请求与 Agent 绑定团队不一致")
        run = self.run_service.get_by_request_id(db, team_id=team_id, request_id=request_id)
        if run is None:
            raise ValueError("客户智能持久运行不存在")
        event_json = run.event_json if isinstance(run.event_json, dict) else {}
        event = self.event_service.from_dict(cast(JsonObject, event_json))
        if event is None:
            raise ValueError("客户智能持久事件快照无效")
        if (
            int(run.team_id) != int(team_id)
            or int(event.team_id) != int(team_id)
            or int(event.tenant_id) != int(team_id)
            or int(run.customer_id) != int(event.customer_id)
        ):
            raise ValueError("客户智能持久运行身份校验失败")
        customer = (
            db.query(Customer)
            .filter(Customer.team_id == team_id, Customer.id == event.customer_id)
            .one_or_none()
        )
        if customer is None:
            raise ValueError("客户智能运行关联客户不存在")
        scope = cast(CustomerIntelligenceRefreshScope, str(run.scope))
        if scope not in {"full", "brief"}:
            raise ValueError("客户智能持久运行刷新范围无效")
        graph_thread_id = build_customer_intelligence_thread_id(
            team_id=binding.team_id,
            event_key=event.event_key,
        )
        operation = self.async_operation_service.bind_source(
            db,
            operation_key=f"customer-intelligence:{request_id}",
            request_id=request_id,
            team_id=binding.team_id,
            user_id=binding.user_id,
            session_id=binding.session_id,
            source_user_message_id=binding.source_user_message_id,
            source_assistant_message_id=binding.source_assistant_message_id,
            operation_type="customer_intelligence_refresh",
            resource_type="customer",
            resource_id=event.customer_id,
            resource_public_id=str(customer.public_id),
            graph_thread_id=graph_thread_id,
            summary="客户档案后台更新",
        )
        projected_operation = self.operation_projector.project_run(
            db,
            run=run,
            operation_public_id=str(operation.public_id),
        )
        if projected_operation is None:
            raise RuntimeError("客户智能异步操作绑定后投影不可见")
        operation = projected_operation
        return CustomerIntelligenceCommittedEventRequest(
            request_id=request_id,
            event=event,
            scope=scope,
            scheduled=True,
            kick_required=self._run_can_be_kicked(run),
            operation_public_id=str(operation.public_id),
            agent_binding=binding,
        )

    def bind_committed_events_to_agent(
        self,
        db: Session,
        *,
        team_id: int,
        request_ids: list[str] | tuple[str, ...],
        binding: AgentAsyncOperationBinding,
    ) -> tuple[CustomerIntelligenceCommittedEventRequest, ...]:
        """Bind exact persisted runs to one Agent source without replaying work.

        The caller owns the transaction. Request IDs are de-duplicated while
        preserving order so both the root runtime and the application late-bind
        phase share one authoritative projection seam.
        """

        bound: list[CustomerIntelligenceCommittedEventRequest] = []
        seen: set[str] = set()
        for raw_request_id in request_ids:
            request_id = str(raw_request_id).strip()
            if not request_id or request_id in seen:
                continue
            seen.add(request_id)
            bound.append(
                self.bind_committed_event_to_agent(
                    db,
                    team_id=team_id,
                    request_id=request_id,
                    binding=binding,
                )
            )
        return tuple(bound)

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
            agent_binding=request.agent_binding,
            operation_public_id=request.operation_public_id,
        )

    async def _run_event_refresh(
        self,
        *,
        request_id: str,
        event: CustomerIntelligenceEvent,
        scope: CustomerIntelligenceRefreshScope,
        agent_binding: AgentAsyncOperationBinding | None = None,
        operation_public_id: str | None = None,
    ) -> JSONDict:
        settings = get_settings()
        run_input = CustomerIntelligenceRunInput(
            request_id=request_id,
            event=event,
            scope=scope,
            max_attempts=settings.CUSTOMER_INTELLIGENCE_MAX_ATTEMPTS,
        )
        try:
            claim = self._claim_run(
                run_input,
                lease_seconds=settings.CUSTOMER_INTELLIGENCE_LEASE_SECONDS,
            )
        except Exception as exc:
            logger.exception(
                "客户智能运行租约获取失败: team_id=%s, customer_id=%s, request_id=%s",
                event.team_id,
                event.customer_id,
                request_id,
            )
            return {"success": False, "request_id": request_id, "error": str(exc)}

        if claim.status != CustomerIntelligenceRunClaimStatus.CLAIMED:
            self._project_operation_run(
                run=claim.run,
                operation_public_id=operation_public_id,
            )
            return self._claim_response(request_id=request_id, event=event, claim=claim)

        lease_token = claim.lease_token
        if lease_token is None:
            raise RuntimeError("客户智能运行已获取执行权但缺少租约令牌")

        operation = self._project_operation_run(
            run=claim.run,
            operation_public_id=operation_public_id,
        )
        graph_user_id = int(operation.user_id) if operation is not None else _actor_user_id(event.actor_id)
        graph_session_id = int(operation.session_id or 0) if operation is not None else 0
        try:
            graph_input = {
                "team_id": event.team_id,
                "user_id": graph_user_id,
                "session_id": graph_session_id,
                "event": event,
            }
            result: JSONDict = {}
            stream_run = getattr(self.graph_service, "stream_run", None)
            if callable(stream_run):
                async for chunk in stream_run(graph_input):
                    if chunk.get("kind") == "event":
                        self._record_operation_progress(
                            run_input=run_input,
                            lease_token=lease_token,
                            operation_public_id=operation_public_id,
                            event=chunk.get("event"),
                        )
                    elif chunk.get("kind") == "result":
                        result = cast(JSONDict, chunk.get("result") or {})
            else:
                result = await self.graph_service.run(graph_input)

            mutation = self._mark_run_succeeded(
                run_input,
                lease_token=lease_token,
                result=result,
            )
            if mutation.status != CustomerIntelligenceRunLeaseMutationStatus.APPLIED:
                self._project_operation_run(
                    run=mutation.run,
                    operation_public_id=operation_public_id,
                )
                return {
                    "success": False,
                    "request_id": request_id,
                    "superseded": True,
                    "run_status": str(mutation.run.status),
                }
            self._project_operation_run(
                run=mutation.run,
                operation_public_id=operation_public_id,
            )
            degraded = coerce_json_dict(mutation.run.result_json).get("degraded") is True
            response: JSONDict = {
                "success": True,
                "request_id": request_id,
                "event_key": event.event_key,
                "route": str(mutation.run.route or result.get("route") or ""),
            }
            if degraded:
                response["degraded"] = True
            return response
        except Exception as exc:
            logger.exception(
                "客户智能刷新失败: team_id=%s, customer_id=%s, trigger_type=%s, scope=%s, request_id=%s",
                event.team_id,
                event.customer_id,
                event.trigger_type,
                scope,
                request_id,
            )
            mutation = self._mark_run_failed(
                run_input,
                lease_token=lease_token,
                error_message=str(exc),
            )
            if mutation.status == CustomerIntelligenceRunLeaseMutationStatus.APPLIED:
                self._project_operation_run(
                    run=mutation.run,
                    operation_public_id=operation_public_id,
                )
                self._project_customer_failure(event=event, scope=scope, run=mutation.run)
            return {
                "success": False,
                "request_id": request_id,
                "error": str(exc),
                "superseded": mutation.status == CustomerIntelligenceRunLeaseMutationStatus.STALE_LEASE,
                "run_status": str(mutation.run.status),
            }

    @staticmethod
    def _claim_response(
        *,
        request_id: str,
        event: CustomerIntelligenceEvent,
        claim: CustomerIntelligenceRunClaim,
    ) -> JSONDict:
        run_status = str(claim.run.status)
        if claim.status == CustomerIntelligenceRunClaimStatus.TERMINAL:
            return {
                "success": run_status == CustomerIntelligenceRunStatus.SUCCESS,
                "request_id": request_id,
                "event_key": event.event_key,
                "terminal": True,
                "run_status": run_status,
                "route": str(claim.run.route or ""),
                "error": str(claim.run.error_message or "") or None,
            }
        if claim.status == CustomerIntelligenceRunClaimStatus.ATTEMPTS_EXHAUSTED:
            return {
                "success": False,
                "request_id": request_id,
                "terminal": True,
                "run_status": run_status,
                "error": str(claim.run.error_message or "客户智能档案刷新已达到最大重试次数。"),
            }
        return {
            "success": True,
            "request_id": request_id,
            "scheduled": True,
            "busy": True,
            "run_status": run_status,
        }

    def _claim_run(
        self,
        run_input: CustomerIntelligenceRunInput,
        *,
        lease_seconds: int,
    ) -> CustomerIntelligenceRunClaim:
        db = SessionLocal()
        try:
            claim = self.run_service.claim_for_execution(
                db,
                run_input,
                lease_seconds=lease_seconds,
            )
            db.commit()
            self._detach(db, claim.run)
            return claim
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _mark_run_succeeded(
        self,
        run_input: CustomerIntelligenceRunInput,
        *,
        lease_token: str,
        result: JSONDict,
    ) -> CustomerIntelligenceRunLeaseMutation:
        db = SessionLocal()
        try:
            mutation = self.run_service.mark_succeeded_if_lease_owner(
                db,
                run_input,
                lease_token=lease_token,
                result=result,
            )
            db.commit()
            self._detach(db, mutation.run)
            return mutation
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _mark_run_failed(
        self,
        run_input: CustomerIntelligenceRunInput,
        *,
        lease_token: str,
        error_message: str,
    ) -> CustomerIntelligenceRunLeaseMutation:
        db = SessionLocal()
        try:
            mutation = self.run_service.mark_failed_if_lease_owner(
                db,
                run_input,
                lease_token=lease_token,
                error_message=error_message,
            )
            db.commit()
            self._detach(db, mutation.run)
            return mutation
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _project_operation_run(
        self,
        *,
        run: CustomerIntelligenceRun,
        operation_public_id: str | None,
    ):
        db = SessionLocal()
        try:
            projected = self.operation_projector.project_run(
                db,
                run=run,
                operation_public_id=operation_public_id,
            )
            db.commit()
            self._detach(db, projected)
            return projected
        except Exception as exc:
            db.rollback()
            logger.exception("投影客户智能异步操作失败: request_id=%s", run.request_id)
            self._record_operation_projection_warning(
                run=run,
                operation_public_id=operation_public_id,
                error_message=str(exc),
            )
            return None
        finally:
            db.close()

    def _record_operation_progress(
        self,
        *,
        run_input: CustomerIntelligenceRunInput,
        lease_token: str,
        operation_public_id: str | None,
        event: object,
    ) -> None:
        progress = coerce_json_dict(event)
        message = str(progress.get("content") or progress.get("message") or "").strip()
        if not message:
            return
        db = SessionLocal()
        try:
            mutation = self.run_service.record_visible_progress_if_lease_owner(
                db,
                run_input,
                lease_token=lease_token,
                progress=progress,
            )
            db.commit()
            self._detach(db, mutation.run)
        except Exception:
            db.rollback()
            logger.exception("持久化客户智能运行进度失败: request_id=%s", run_input.request_id)
            return
        finally:
            db.close()
        if mutation.status == CustomerIntelligenceRunLeaseMutationStatus.APPLIED:
            self._project_operation_run(
                run=mutation.run,
                operation_public_id=operation_public_id,
            )

    def _record_operation_projection_warning(
        self,
        *,
        run: CustomerIntelligenceRun,
        operation_public_id: str | None,
        error_message: str,
    ) -> None:
        db = SessionLocal()
        try:
            operation = self.async_operation_service.get_for_update(
                db,
                team_id=int(run.team_id),
                request_id=str(run.request_id),
                operation_public_id=operation_public_id,
            )
            if operation is None:
                return
            self.async_operation_service.record_projection_warning(
                db,
                operation,
                run_id=int(run.id),
                run_status=str(run.status),
                error_message=error_message,
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("记录客户智能投影异常失败: request_id=%s", run.request_id)
        finally:
            db.close()

    def _project_customer_failure(
        self,
        *,
        event: CustomerIntelligenceEvent,
        scope: CustomerIntelligenceRefreshScope,
        run: CustomerIntelligenceRun,
    ) -> None:
        db = SessionLocal()
        try:
            status = str(run.status)
            if status == CustomerIntelligenceRunStatus.RETRY_PENDING:
                projected_status = "PENDING"
                error_message = None
            else:
                projected_status = "FAILED"
                error_message = str(run.error_message or "客户智能档案刷新失败")
            if scope == "full":
                customer_crud.update_profile_status(
                    db, event.customer_id, projected_status, error_message, commit=False
                )
            customer_crud.update_customer_brief_status(
                db, event.customer_id, projected_status, error_message, commit=False
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("投影客户智能客户状态失败: request_id=%s", run.request_id)
        finally:
            db.close()

    @staticmethod
    def _detach(db: Session, obj: object) -> None:
        try:
            db.refresh(obj)
            db.expunge(obj)
        except Exception:
            return

    async def run_manual_refresh(self, request: CustomerIntelligenceRefreshRequest) -> JSONDict:
        return await self.run_refresh(request)

    async def run_due_retries(self, *, team_id: int | None = None, limit: int = 20) -> JSONDict:
        db = SessionLocal()
        try:
            recovered = self.recover_stale_runtime_state(db, team_id=team_id)
            db.commit()
            retry_requests = []
            for run in self.run_service.list_due(db, team_id=team_id, limit=limit):
                retry_request = self._request_from_run(run)
                if isinstance(retry_request, CustomerIntelligenceCommittedEventRequest):
                    try:
                        operation = self.async_operation_service.get_by_request_id(
                            db,
                            team_id=run.team_id,
                            request_id=retry_request.request_id,
                        )
                    except (AttributeError, NotImplementedError):
                        operation = None
                    if operation is not None:
                        retry_request = replace(
                            retry_request,
                            operation_public_id=str(operation.public_id),
                            agent_binding=AgentAsyncOperationBinding(
                                team_id=int(operation.team_id),
                                user_id=int(operation.user_id),
                                session_id=int(operation.session_id or 0),
                                source_user_message_id=(
                                    int(operation.source_user_message_id)
                                    if operation.source_user_message_id is not None
                                    else None
                                ),
                                source_assistant_message_id=(
                                    int(operation.source_assistant_message_id)
                                    if operation.source_assistant_message_id is not None
                                    else None
                                ),
                            ),
                        )
                retry_requests.append(retry_request)
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
        """Repair projections without stealing or failing a live execution lease.

        Expired RUNNING rows remain durable execution intents. ``list_due`` and
        ``claim_for_execution`` perform the only legal reclaim transition. This
        method merely aligns customer/Agent projections with the persisted run.
        """
        if not hasattr(db, "query"):
            return {
                "obsolete_historical_runs": 0,
                "reconciled_operations": 0,
                "stale_runs": 0,
                "pending_customers": 0,
                "failed_customers": 0,
            }
        if team_id is None:
            totals: JSONDict = {
                "obsolete_historical_runs": 0,
                "reconciled_operations": 0,
                "stale_runs": 0,
                "pending_customers": 0,
                "failed_customers": 0,
            }
            for team in team_crud.get_all_teams(db):
                team_result = self.recover_stale_runtime_state(db, team_id=int(team.id))
                for key in totals:
                    totals[key] = int(totals[key]) + int(team_result.get(key) or 0)
            return totals
        current_time = business_now()
        obsolete_historical_runs = self._close_obsolete_historical_backfill_runs(
            db,
            team_id=team_id,
            finished_at=current_time,
        )

        reconciliation = self.operation_projector.reconcile(db, team_id=team_id, limit=200)

        due_runs = self.run_service.list_due(
            db,
            now=current_time,
            team_id=team_id,
            limit=200,
        )
        expired_running_runs = [
            run
            for run in due_runs
            if str(run.status) == CustomerIntelligenceRunStatus.RUNNING
        ]
        for run in due_runs:
            self.operation_projector.project_run(db, run=run)

        retryable_customer_ids = self._customer_ids_with_runs(
            db,
            statuses=[
                CustomerIntelligenceRunStatus.PENDING,
                CustomerIntelligenceRunStatus.RETRY_PENDING,
            ],
            team_id=team_id,
        ) | {int(run.customer_id) for run in expired_running_runs}
        active_customer_ids = self._customer_ids_with_runs(
            db,
            statuses=[
                CustomerIntelligenceRunStatus.PENDING,
                CustomerIntelligenceRunStatus.RUNNING,
                CustomerIntelligenceRunStatus.RETRY_PENDING,
            ],
            team_id=team_id,
        )
        failed_customer_ids = self._customer_ids_with_runs(
            db,
            statuses=[CustomerIntelligenceRunStatus.FAILED],
            team_id=team_id,
        ) - active_customer_ids

        pending_updates = self._reset_generating_customers(
            db,
            customer_ids=retryable_customer_ids,
            team_id=team_id,
            status="PENDING",
            error_message=None,
        )
        failed_updates = self._reset_generating_customers(
            db,
            customer_ids=failed_customer_ids,
            team_id=team_id,
            status="FAILED",
            error_message="客户智能档案刷新失败，等待下一次业务触发或重建。",
        )
        return {
            "obsolete_historical_runs": obsolete_historical_runs,
            "reconciled_operations": reconciliation.projected,
            "stale_runs": len(expired_running_runs),
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
        for run in (
            query.order_by(CustomerIntelligenceRun.id.asc())
            .limit(500)
            .populate_existing()
            .with_for_update()
            .all()
        ):
            run.status = CustomerIntelligenceRunStatus.CANCELLED
            run.finished_time = finished_at
            run.next_retry_at = None
            run.lease_token = None
            run.lease_expires_at = None
            run.error_message = None
            run.route = run.route or "historical_backfill_satisfied"
            run.result_json = {
                "route": "historical_backfill_satisfied",
                "reason": "customer_brief_already_available",
            }
            operation = self.async_operation_service.get_by_request_id(
                db,
                team_id=int(run.team_id),
                request_id=str(run.request_id),
            )
            if operation is not None:
                self.async_operation_service.cancel(
                    db,
                    operation,
                    summary="客户档案已由更新的数据生成，本次历史补齐任务已取消",
                    result={
                        "route": "historical_backfill_satisfied",
                        "reason": "customer_brief_already_available",
                    },
                )
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
        team_id: int | None,
        status: str,
        error_message: str | None,
    ) -> int:
        if not customer_ids:
            return 0
        query = db.query(Customer).filter(Customer.id.in_(sorted(customer_ids)))
        if team_id is not None:
            query = query.filter(Customer.team_id == team_id)
        customers = query.all()
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
            customer_crud.update_profile_status(db, request.customer_id, "PENDING", commit=False)
        customer_crud.update_customer_brief_status(db, request.customer_id, "PENDING", commit=False)

    def _mark_pending_event(self, db: Session, request: CustomerIntelligenceCommittedEventRequest) -> None:
        if request.scope == "full":
            customer_crud.update_profile_status(db, request.event.customer_id, "PENDING", commit=False)
        customer_crud.update_customer_brief_status(db, request.event.customer_id, "PENDING", commit=False)

    def _ensure_pending_run(self, db: Session, request: CustomerIntelligenceRefreshRequest) -> None:
        event = self._build_event(request)
        self.run_service.ensure_pending(
            db,
            CustomerIntelligenceRunInput(
                request_id=request.request_id,
                event=event,
                scope=request.scope,
                max_attempts=get_settings().CUSTOMER_INTELLIGENCE_MAX_ATTEMPTS,
            ),
        )

    def _ensure_pending_event_run(self, db: Session, request: CustomerIntelligenceCommittedEventRequest) -> None:
        self.run_service.ensure_pending(
            db,
            CustomerIntelligenceRunInput(
                request_id=request.request_id,
                event=request.event,
                scope=request.scope,
                max_attempts=get_settings().CUSTOMER_INTELLIGENCE_MAX_ATTEMPTS,
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
            scheduled_request = request
            binding = request.agent_binding
            if binding is not None:
                customer_public_id = (
                    db.query(Customer.public_id)
                    .filter(
                        Customer.team_id == request.event.team_id,
                        Customer.id == request.event.customer_id,
                    )
                    .scalar()
                )
                graph_thread_id = build_customer_intelligence_thread_id(
                    team_id=binding.team_id,
                    event_key=request.event.event_key,
                )
                operation = self.async_operation_service.bind_source(
                    db,
                    operation_key=f"customer-intelligence:{request.request_id}",
                    request_id=request.request_id,
                    team_id=binding.team_id,
                    user_id=binding.user_id,
                    session_id=binding.session_id,
                    source_user_message_id=binding.source_user_message_id,
                    source_assistant_message_id=binding.source_assistant_message_id,
                    operation_type="customer_intelligence_refresh",
                    resource_type="customer",
                    resource_id=request.event.customer_id,
                    resource_public_id=str(customer_public_id) if customer_public_id else None,
                    summary="客户档案后台更新",
                    graph_thread_id=graph_thread_id,
                )
                run = self.run_service.get_by_request_id(
                    db,
                    team_id=request.event.team_id,
                    request_id=request.request_id,
                )
                if run is None:
                    raise RuntimeError("客户智能持久运行调度后不可见")
                projected_operation = self.operation_projector.project_run(
                    db,
                    run=run,
                    operation_public_id=str(operation.public_id),
                )
                if projected_operation is None:
                    raise RuntimeError("客户智能异步操作调度后投影不可见")
                operation = projected_operation
                scheduled_request = replace(
                    request,
                    scheduled=True,
                    kick_required=self._run_can_be_kicked(run),
                    operation_public_id=str(operation.public_id),
                )
            db.commit()
            return scheduled_request
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
                agent_binding=request.agent_binding,
            )
        finally:
            db.close()

    @staticmethod
    def _run_can_be_kicked(run: CustomerIntelligenceRun) -> bool:
        status = str(run.status)
        if status == CustomerIntelligenceRunStatus.PENDING:
            return True
        if status == CustomerIntelligenceRunStatus.RETRY_PENDING:
            return run.next_retry_at is None or run.next_retry_at <= business_now()
        if status == CustomerIntelligenceRunStatus.RUNNING:
            return run.lease_expires_at is None or run.lease_expires_at <= business_now()
        return False

    def _request_from_run(
        self,
        run: CustomerIntelligenceRun,
    ) -> CustomerIntelligenceRefreshRequest | CustomerIntelligenceCommittedEventRequest:
        committed_event = self._committed_event_request_from_run(run)
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

    def _committed_event_request_from_run(
        self,
        run: CustomerIntelligenceRun,
    ) -> CustomerIntelligenceCommittedEventRequest | None:
        if run.trigger_type in {
            "manual_refresh_requested",
            "customer_intelligence_batch_rebuild_requested",
            "customer_intelligence_historical_backfill_requested",
            "customer_created",
            "customer_converted_from_lead",
        }:
            return None
        event_json = run.event_json if isinstance(run.event_json, dict) else {}
        event = self.event_service.from_dict(cast(JsonObject, event_json))
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
        return [int(row[0]) for row in query.order_by(Customer.id.asc()).limit(max(1, min(limit, 500))).all()]

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
        return [int(row[0]) for row in query.order_by(Customer.id.asc()).limit(max(1, min(limit, 500))).all()]

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
            CustomerIntelligenceRun.status.in_(
                [
                    CustomerIntelligenceRunStatus.PENDING,
                    CustomerIntelligenceRunStatus.RUNNING,
                    CustomerIntelligenceRunStatus.RETRY_PENDING,
                ]
            ),
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

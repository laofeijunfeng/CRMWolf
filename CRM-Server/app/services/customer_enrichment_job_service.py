"""Durable execution service for customer initial-enrichment jobs."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.crud.customer_enrichment_job import CustomerEnrichmentJobCRUD, customer_enrichment_job_crud
from app.services.agent.customer_initial_enrichment_graph import (
    CustomerInitialEnrichmentRequest,
    CustomerInitialEnrichmentResult,
)
from app.services.ai_task_limiter import ai_generation_semaphore
from app.services.customer_enrichment_contracts import (
    CustomerEnrichmentJobRequest,
    CustomerEnrichmentJobStatus,
    CustomerEnrichmentRunResult,
)
from app.services.customer_enrichment_write_service import (
    APPLIED,
    RETRY,
    SKIPPED,
    CustomerEnrichmentWriteResult,
    CustomerEnrichmentWriteService,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from app.models.customer_enrichment_job import CustomerEnrichmentJob


logger = logging.getLogger(__name__)
_TERMINAL = {
    CustomerEnrichmentJobStatus.COMPLETED.value,
    CustomerEnrichmentJobStatus.SKIPPED.value,
    CustomerEnrichmentJobStatus.EXHAUSTED.value,
}


class CustomerEnrichmentCompletionPort(Protocol):
    def on_first_attempt_finished(self, job: CustomerEnrichmentJob) -> None:
        """Release the first-profile gate after the first real attempt."""

    def on_terminal_success(
        self, job: CustomerEnrichmentJob, result: CustomerEnrichmentRunResult
    ) -> None:
        """Release or enqueue exactly one profile refresh after terminal success."""


class CustomerInitialEnrichmentWorkflowRunner(Protocol):
    async def run(
        self, request: CustomerInitialEnrichmentRequest
    ) -> CustomerInitialEnrichmentResult: ...


class CustomerEnrichmentJobService:
    def __init__(
        self,
        *,
        job_crud: CustomerEnrichmentJobCRUD | None = None,
        workflow: CustomerInitialEnrichmentWorkflowRunner | None = None,
        write_service: CustomerEnrichmentWriteService | None = None,
        completion_port: CustomerEnrichmentCompletionPort,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self.job_crud = job_crud or customer_enrichment_job_crud
        self._workflow = workflow
        self._write_service = write_service
        self.completion_port = completion_port
        self._session_factory = session_factory

    @property
    def workflow(self) -> CustomerInitialEnrichmentWorkflowRunner:
        if self._workflow is None:
            from app.services.agent.customer_initial_enrichment_workflow import (
                customer_initial_enrichment_workflow,
            )

            self._workflow = customer_initial_enrichment_workflow
        return self._workflow

    @property
    def write_service(self) -> CustomerEnrichmentWriteService:
        if self._write_service is None:
            self._write_service = CustomerEnrichmentWriteService()
        return self._write_service

    async def run(self, request: CustomerEnrichmentJobRequest) -> CustomerEnrichmentRunResult:
        claimed_at = business_now()
        settings = get_settings()
        lease_token = uuid4().hex
        lease_expires_at = claimed_at + timedelta(
            seconds=max(30, int(settings.CUSTOMER_INITIAL_ENRICHMENT_LEASE_SECONDS))
        )

        db = self._session_factory()
        try:
            existing = self.job_crud.get_by_public_id(
                db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                for_update=True,
            )
            if existing is None:
                raise ValueError("客户补全任务不存在")
            if str(existing.status) in _TERMINAL:
                return self._persisted_result(existing)
            if int(existing.attempt_count or 0) >= max(1, int(existing.max_attempts or 1)):
                return self._finalize_already_exhausted(db, existing, now=claimed_at)

            claimed = self.job_crud.claim_for_execution(
                db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
                now=claimed_at,
                commit=False,
            )
            if claimed is None:
                db.rollback()
                return self._busy_result(request, customer_id=int(existing.customer_id))
            snapshot = {
                "customer_id": int(claimed.customer_id),
                "plan_version": str(claimed.plan_version),
                "requested_fields": tuple(str(item) for item in (claimed.requested_fields_json or [])),
                "attempt_count": int(claimed.attempt_count or 0),
                "max_attempts": max(1, int(claimed.max_attempts or 1)),
                "run_id": str(claimed.run_id),
                "thread_id": str(claimed.graph_thread_id),
                "first_attempt_finished": claimed.first_attempt_finished_at is not None,
            }
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        graph_request = CustomerInitialEnrichmentRequest(
            team_id=request.team_id,
            customer_id=snapshot["customer_id"],
            plan_version=snapshot["plan_version"],
            requested_fields=snapshot["requested_fields"],
            run_id=snapshot["run_id"],
            thread_id=snapshot["thread_id"],
        )
        try:
            async with ai_generation_semaphore:
                computed = await self.workflow.run(graph_request)
        except Exception as exc:
            logger.exception("客户补全任务计算失败: job=%s", request.job_public_id)
            return self._record_failure(
                request,
                lease_token=lease_token,
                customer_id=snapshot["customer_id"],
                attempt_count=snapshot["attempt_count"],
                max_attempts=snapshot["max_attempts"],
                first_attempt_finished=snapshot["first_attempt_finished"],
                exc=exc,
            )

        if computed.skip_reason is not None:
            result = self._result(
                request,
                customer_id=snapshot["customer_id"],
                execution_status=CustomerEnrichmentJobStatus.SKIPPED.value,
                success=True,
                skip_reason=computed.skip_reason,
            )
            return self._complete(
                request,
                lease_token=lease_token,
                result=result,
                skipped=True,
                first_attempt_finished=snapshot["first_attempt_finished"],
            )

        db = self._session_factory()
        try:
            lease_job = self.job_crud.get_by_public_id(
                db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                for_update=True,
            )
            if not self._owns_live_lease(lease_job, lease_token, now=business_now()):
                db.rollback()
                return self._busy_result(request, customer_id=snapshot["customer_id"])
            try:
                write_result = self.write_service.apply(
                    db,
                    team_id=request.team_id,
                    customer_id=snapshot["customer_id"],
                    expected_version=computed.expected_version,
                    decisions=computed.decisions,
                    plan_version=snapshot["plan_version"],
                    job_public_id=request.job_public_id,
                )
            except Exception as exc:
                logger.exception("客户补全任务写入失败: job=%s", request.job_public_id)
                return self._record_failure_in_session(
                    db,
                    request,
                    lease_token=lease_token,
                    customer_id=snapshot["customer_id"],
                    attempt_count=snapshot["attempt_count"],
                    max_attempts=snapshot["max_attempts"],
                    first_attempt_finished=snapshot["first_attempt_finished"],
                    exc=exc,
                )
            return self._record_write_result(
                db,
                request,
                lease_token=lease_token,
                customer_id=snapshot["customer_id"],
                attempt_count=snapshot["attempt_count"],
                max_attempts=snapshot["max_attempts"],
                first_attempt_finished=snapshot["first_attempt_finished"],
                write_result=write_result,
            )
        finally:
            db.close()

    def kick(self, request: CustomerEnrichmentJobRequest) -> None:
        """Schedule a guarded latency kick only when this thread owns an event loop."""

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("当前线程没有运行中的事件循环, 客户补全任务交由恢复器执行")
            return
        task = asyncio.create_task(self._run_guarded(request))
        task.add_done_callback(self._consume_task_exception)

    async def _run_guarded(self, request: CustomerEnrichmentJobRequest) -> None:
        try:
            await self.run(request)
        except Exception:
            logger.exception("客户补全任务即时执行失败: job=%s", request.job_public_id)

    @staticmethod
    def _consume_task_exception(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        try:
            task.exception()
        except Exception:
            logger.exception("客户补全任务回调失败")

    def _record_write_result(
        self,
        db: Session,
        request: CustomerEnrichmentJobRequest,
        *,
        lease_token: str,
        customer_id: int,
        attempt_count: int,
        max_attempts: int,
        first_attempt_finished: bool,
        write_result: CustomerEnrichmentWriteResult,
    ) -> CustomerEnrichmentRunResult:
        now = business_now()
        if write_result.outcome == APPLIED:
            result = self._result(
                request,
                customer_id=customer_id,
                execution_status=CustomerEnrichmentJobStatus.COMPLETED.value,
                success=True,
                applied_fields=list(write_result.applied_fields),
            )
            updated = self.job_crud.mark_completed_if_lease_owner(
                db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                lease_token=lease_token,
                result_json=result.model_dump(mode="json"),
                now=now,
                commit=False,
            )
            return self._finish_mutation(
                db,
                request,
                customer_id=customer_id,
                updated=updated,
                result=result,
                first_attempt_finished=first_attempt_finished,
                terminal_success=True,
            )
        if write_result.outcome == SKIPPED:
            result = self._result(
                request,
                customer_id=customer_id,
                execution_status=CustomerEnrichmentJobStatus.SKIPPED.value,
                success=True,
                skip_reason=write_result.reason,
            )
            updated = self.job_crud.mark_completed_if_lease_owner(
                db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                lease_token=lease_token,
                result_json=result.model_dump(mode="json"),
                skipped=True,
                now=now,
                commit=False,
            )
            return self._finish_mutation(
                db,
                request,
                customer_id=customer_id,
                updated=updated,
                result=result,
                first_attempt_finished=first_attempt_finished,
                terminal_success=True,
            )
        if write_result.outcome == RETRY:
            return self._record_retry_in_session(
                db,
                request,
                lease_token=lease_token,
                customer_id=customer_id,
                attempt_count=attempt_count,
                max_attempts=max_attempts,
                first_attempt_finished=first_attempt_finished,
                error=write_result.reason or "CUSTOMER_CHANGED_DURING_ENRICHMENT",
            )
        raise ValueError(f"unsupported customer enrichment write outcome: {write_result.outcome}")

    def _complete(
        self,
        request: CustomerEnrichmentJobRequest,
        *,
        lease_token: str,
        result: CustomerEnrichmentRunResult,
        skipped: bool,
        first_attempt_finished: bool,
    ) -> CustomerEnrichmentRunResult:
        db = self._session_factory()
        try:
            updated = self.job_crud.mark_completed_if_lease_owner(
                db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                lease_token=lease_token,
                result_json=result.model_dump(mode="json"),
                skipped=skipped,
                now=business_now(),
                commit=False,
            )
            return self._finish_mutation(
                db,
                request,
                customer_id=result.customer_id,
                updated=updated,
                result=result,
                first_attempt_finished=first_attempt_finished,
                terminal_success=True,
            )
        finally:
            db.close()

    def _record_failure(
        self,
        request: CustomerEnrichmentJobRequest,
        *,
        lease_token: str,
        customer_id: int,
        attempt_count: int,
        max_attempts: int,
        first_attempt_finished: bool,
        exc: Exception,
    ) -> CustomerEnrichmentRunResult:
        db = self._session_factory()
        try:
            return self._record_failure_in_session(
                db,
                request,
                lease_token=lease_token,
                customer_id=customer_id,
                attempt_count=attempt_count,
                max_attempts=max_attempts,
                first_attempt_finished=first_attempt_finished,
                exc=exc,
            )
        finally:
            db.close()

    def _record_failure_in_session(
        self,
        db: Session,
        request: CustomerEnrichmentJobRequest,
        *,
        lease_token: str,
        customer_id: int,
        attempt_count: int,
        max_attempts: int,
        first_attempt_finished: bool,
        exc: Exception,
    ) -> CustomerEnrichmentRunResult:
        error = f"{type(exc).__name__}: {exc}"
        return self._record_retry_in_session(
            db,
            request,
            lease_token=lease_token,
            customer_id=customer_id,
            attempt_count=attempt_count,
            max_attempts=max_attempts,
            first_attempt_finished=first_attempt_finished,
            error=error,
        )

    def _record_retry_in_session(
        self,
        db: Session,
        request: CustomerEnrichmentJobRequest,
        *,
        lease_token: str,
        customer_id: int,
        attempt_count: int,
        max_attempts: int,
        first_attempt_finished: bool,
        error: str,
    ) -> CustomerEnrichmentRunResult:
        now = business_now()
        if attempt_count >= max_attempts:
            result = self._result(
                request,
                customer_id=customer_id,
                execution_status=CustomerEnrichmentJobStatus.EXHAUSTED.value,
                success=False,
                retryable=False,
                error=error,
            )
            updated = self.job_crud.mark_exhausted_if_lease_owner(
                db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                lease_token=lease_token,
                error_message=error,
                result_json=result.model_dump(mode="json"),
                now=now,
                commit=False,
            )
        else:
            result = self._result(
                request,
                customer_id=customer_id,
                execution_status=CustomerEnrichmentJobStatus.RETRY_PENDING.value,
                success=False,
                retryable=True,
                error=error,
            )
            updated = self.job_crud.mark_retry_pending_if_lease_owner(
                db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                lease_token=lease_token,
                error_message=error,
                next_attempt_at=now + self._retry_delay(attempt_count),
                result_json=result.model_dump(mode="json"),
                now=now,
                commit=False,
            )
        return self._finish_mutation(
            db,
            request,
            customer_id=customer_id,
            updated=updated,
            result=result,
            first_attempt_finished=first_attempt_finished,
            terminal_success=False,
        )

    def _finish_mutation(
        self,
        db: Session,
        request: CustomerEnrichmentJobRequest,
        *,
        customer_id: int,
        updated: CustomerEnrichmentJob | None,
        result: CustomerEnrichmentRunResult,
        first_attempt_finished: bool,
        terminal_success: bool,
    ) -> CustomerEnrichmentRunResult:
        if updated is None:
            db.rollback()
            return self._busy_result(request, customer_id=customer_id)
        db.commit()
        self._detach_after_commit(db, updated)
        if not first_attempt_finished and updated.first_attempt_finished_at is not None:
            self._call_first_attempt_finished(updated)
        if terminal_success:
            self._call_terminal_success(updated, result)
        return result

    def _finalize_already_exhausted(
        self, db: Session, job: CustomerEnrichmentJob, *, now: datetime
    ) -> CustomerEnrichmentRunResult:
        result = self._result(
            CustomerEnrichmentJobRequest(team_id=int(job.team_id), job_public_id=str(job.public_id)),
            customer_id=int(job.customer_id),
            execution_status=CustomerEnrichmentJobStatus.EXHAUSTED.value,
            success=False,
            retryable=False,
            error=job.error_message or "customer enrichment retries exhausted",
        )
        first_attempt_finished = job.first_attempt_finished_at is not None
        job.status = CustomerEnrichmentJobStatus.EXHAUSTED.value
        job.result_json = result.model_dump(mode="json")
        job.error_message = result.error
        job.next_attempt_at = None
        job.finished_at = now
        job.first_attempt_finished_at = job.first_attempt_finished_at or now
        job.lease_token = None
        job.lease_expires_at = None
        db.add(job)
        db.commit()
        self._detach_after_commit(db, job)
        if not first_attempt_finished:
            self._call_first_attempt_finished(job)
        return result

    def _call_first_attempt_finished(self, job: CustomerEnrichmentJob) -> None:
        try:
            self.completion_port.on_first_attempt_finished(job)
        except Exception:
            logger.exception("客户补全首次尝试完成回调失败: job=%s", job.public_id)

    def _call_terminal_success(
        self, job: CustomerEnrichmentJob, result: CustomerEnrichmentRunResult
    ) -> None:
        try:
            self.completion_port.on_terminal_success(job, result)
        except Exception:
            logger.exception("客户补全终态成功回调失败: job=%s", job.public_id)

    @staticmethod
    def _detach_after_commit(db: Session, job: CustomerEnrichmentJob) -> None:
        refresh = getattr(db, "refresh", None)
        expunge = getattr(db, "expunge", None)
        if callable(refresh):
            refresh(job)
        if callable(expunge):
            expunge(job)

    @staticmethod
    def _retry_delay(attempt_count: int) -> timedelta:
        return timedelta(seconds=60 if attempt_count <= 1 else 300)

    @staticmethod
    def _owns_live_lease(job: CustomerEnrichmentJob | None, lease_token: str, *, now: datetime) -> bool:
        return bool(
            job is not None
            and str(job.status) == CustomerEnrichmentJobStatus.RUNNING.value
            and job.lease_token == lease_token
            and job.lease_expires_at is not None
            and job.lease_expires_at > now
        )

    @staticmethod
    def _persisted_result(job: CustomerEnrichmentJob) -> CustomerEnrichmentRunResult:
        payload = job.result_json
        if isinstance(payload, dict):
            try:
                return CustomerEnrichmentRunResult.model_validate(payload)
            except Exception:
                logger.warning("客户补全任务持久结果无效, 使用任务状态重建: job=%s", job.public_id)
        status = str(job.status)
        return CustomerEnrichmentRunResult(
            job_public_id=str(job.public_id),
            customer_id=int(job.customer_id),
            execution_status=status,
            success=status in {
                CustomerEnrichmentJobStatus.COMPLETED.value,
                CustomerEnrichmentJobStatus.SKIPPED.value,
            },
            retryable=False,
            error=job.error_message,
        )

    @staticmethod
    def _busy_result(
        request: CustomerEnrichmentJobRequest, *, customer_id: int
    ) -> CustomerEnrichmentRunResult:
        return CustomerEnrichmentRunResult(
            job_public_id=request.job_public_id,
            customer_id=customer_id,
            execution_status="BUSY",
            success=False,
            retryable=True,
        )

    @staticmethod
    def _result(
        request: CustomerEnrichmentJobRequest,
        *,
        customer_id: int,
        execution_status: str,
        success: bool,
        retryable: bool = False,
        applied_fields: list[str] | None = None,
        skip_reason: str | None = None,
        error: str | None = None,
    ) -> CustomerEnrichmentRunResult:
        return CustomerEnrichmentRunResult(
            job_public_id=request.job_public_id,
            customer_id=customer_id,
            execution_status=execution_status,
            success=success,
            retryable=retryable,
            applied_fields=applied_fields or [],
            skip_reason=skip_reason,
            error=error,
        )


def build_customer_enrichment_job_service(
    completion_port: CustomerEnrichmentCompletionPort,
) -> CustomerEnrichmentJobService:
    return CustomerEnrichmentJobService(completion_port=completion_port)

"""Durable execution boundary for form-submitted customer-activity AI jobs."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.crud.customer_activity import customer_activity_crud
from app.crud.customer_activity_ai_job import CustomerActivityAIJobCRUD, customer_activity_ai_job_crud
from app.services.ai_task_limiter import ai_generation_semaphore
from app.services.customer_activity_contracts import (
    CustomerActivityAIJobStatus,
    CustomerActivityEffectivenessStatus,
    CustomerActivityProcessingStatus,
    CustomerActivitySubmissionSource,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

    from app.models.customer_activity import CustomerActivity
    from app.models.customer_activity_ai_job import CustomerActivityAIJob
    from app.services.customer_activity_ai.workflow import CustomerActivityAIWorkflow
    from app.services.customer_activity_write_service import CustomerActivityWriteService

logger = logging.getLogger(__name__)
_TERMINAL = {
    CustomerActivityAIJobStatus.COMPLETED.value,
    CustomerActivityAIJobStatus.SKIPPED.value,
    CustomerActivityAIJobStatus.EXHAUSTED.value,
}
_ALLOWED_SOURCES = {
    CustomerActivitySubmissionSource.FORM.value,
    CustomerActivitySubmissionSource.CUTOVER_MIGRATION.value,
}


class CustomerActivityAIJobRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_public_id: str
    team_id: int


class CustomerActivityAIJobRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_public_id: str
    activity_id: int
    execution_status: str
    success: bool
    retryable: bool = False
    skip_reason: str | None = None
    error: str | None = None
    activity_revision: int | None = None
    effectiveness_score: int | None = None


class CustomerActivityAIJobService:
    def __init__(
        self,
        *,
        job_crud: CustomerActivityAIJobCRUD | None = None,
        workflow: CustomerActivityAIWorkflow | None = None,
        write_service: CustomerActivityWriteService | None = None,
    ) -> None:
        self.job_crud = job_crud or customer_activity_ai_job_crud
        self._workflow = workflow
        self._write_service = write_service

    @property
    def workflow(self) -> CustomerActivityAIWorkflow:
        if self._workflow is None:
            from app.services.customer_activity_ai.workflow import customer_activity_ai_workflow

            self._workflow = customer_activity_ai_workflow
        return self._workflow

    @property
    def write_service(self) -> CustomerActivityWriteService:
        if self._write_service is None:
            from app.services.customer_activity_write_service import customer_activity_write_service

            self._write_service = customer_activity_write_service
        return self._write_service

    def enqueue_in_transaction(
        self,
        db: Session,
        *,
        activity: CustomerActivity,
    ) -> CustomerActivityAIJobRequest:
        if str(activity.submission_source) not in _ALLOWED_SOURCES:
            raise ValueError("Agent 来源活动不得创建客户活动 AI 任务")
        job = self.job_crud.enqueue(
            db,
            team_id=int(activity.team_id),
            activity_id=int(activity.id),
            activity_revision=int(activity.activity_revision or 1),
            submission_source=str(activity.submission_source),
            commit=False,
        )
        return CustomerActivityAIJobRequest(job_public_id=str(job.public_id), team_id=int(job.team_id))

    async def run(self, request: CustomerActivityAIJobRequest) -> CustomerActivityAIJobRunResult:
        settings = get_settings()
        max_attempts = max(1, settings.CUSTOMER_ACTIVITY_AI_JOB_MAX_ATTEMPTS)
        claimed_at = business_now()
        lease_token = uuid4().hex
        lease_expires_at = claimed_at + timedelta(seconds=max(30, settings.CUSTOMER_ACTIVITY_AI_JOB_LEASE_SECONDS))

        db = SessionLocal()
        try:
            existing = self.job_crud.get_by_public_id(
                db,
                team_id=request.team_id,
                public_id=request.job_public_id,
            )
            if existing is None:
                raise ValueError("客户活动 AI 任务不存在")
            if existing.status in _TERMINAL:
                return self._persisted_result(existing)
            if int(existing.attempt_count or 0) >= max_attempts:
                return self._terminalize_exhausted(db, existing, max_attempts=max_attempts, now=claimed_at)

            job = self.job_crud.claim_for_execution(
                db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
                max_attempts=max_attempts,
                now=claimed_at,
                commit=False,
            )
            if job is None:
                return self._result(
                    request,
                    activity_id=int(existing.activity_id),
                    execution_status="BUSY",
                    success=False,
                    retryable=True,
                )
            activity = customer_activity_crud.get_by_id(db, int(job.activity_id), int(job.team_id))
            skip_reason = self._preflight_skip_reason(job=job, activity=activity)
            if skip_reason:
                return self._mark_skipped(db, job=job, lease_token=lease_token, reason=skip_reason)

            activity.processing_status = CustomerActivityProcessingStatus.PROCESSING.value
            activity.processing_error = None
            activity.effectiveness_status = CustomerActivityEffectivenessStatus.GENERATING.value
            activity.effectiveness_error_message = None
            db.commit()
            job_data = {
                "activity_id": int(job.activity_id),
                "activity_revision": int(job.activity_revision),
                "attempt_count": int(job.attempt_count),
                "run_id": str(job.run_id),
                "thread_id": str(job.graph_thread_id),
            }
        finally:
            db.close()

        try:
            async with ai_generation_semaphore:
                final_result = await self.workflow.compute_finalization(
                    activity_id=job_data["activity_id"],
                    team_id=request.team_id,
                    expected_activity_revision=job_data["activity_revision"],
                    run_id=job_data["run_id"],
                    thread_id=job_data["thread_id"],
                )

            from app.models.sales_commitment import FollowUpTaskProjectionTrigger
            from app.services.customer_activity_write_service import CustomerActivityFinalization

            db = SessionLocal()
            try:
                write_result = self.write_service.finalize_pending_from_ai(
                    db,
                    activity_id=job_data["activity_id"],
                    team_id=request.team_id,
                    expected_activity_revision=job_data["activity_revision"],
                    ai_job_public_id=request.job_public_id,
                    lease_token=lease_token,
                    finalization=CustomerActivityFinalization(
                        title=final_result.title,
                        content_json=final_result.content_json,
                        summary=final_result.summary,
                        next_action=final_result.next_action,
                        next_action_source=final_result.next_action_source,
                        next_follow_time=final_result.next_follow_time,
                        next_follow_time_source=final_result.next_follow_time_source,
                        effectiveness_score=final_result.effectiveness_score,
                        effectiveness_is_valid=final_result.effectiveness_is_valid,
                        effectiveness_reason=final_result.effectiveness_reason,
                        effectiveness_detail_json=json.dumps(
                            final_result.effectiveness_detail,
                            ensure_ascii=False,
                        ),
                    ),
                    post_commit_trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_STRUCTURED_COMPLETED,
                    actor_id=None,
                )
            finally:
                db.close()
            self.write_service.kick(write_result)
            return self._result(
                request,
                activity_id=job_data["activity_id"],
                execution_status=CustomerActivityAIJobStatus.COMPLETED.value,
                success=True,
                activity_revision=write_result.activity_revision,
                effectiveness_score=final_result.effectiveness_score,
            )
        except Exception as exc:
            reason = self._finalization_skip_reason(exc)
            if reason:
                return self._skip_after_compute(
                    request, lease_token=lease_token, activity_id=job_data["activity_id"], reason=reason
                )
            logger.exception("客户活动 AI 任务执行失败: job=%s", request.job_public_id)
            return self._record_failure(
                request,
                lease_token=lease_token,
                activity_id=job_data["activity_id"],
                activity_revision=job_data["activity_revision"],
                attempt_count=job_data["attempt_count"],
                exc=exc,
            )

    def kick(self, request: CustomerActivityAIJobRequest) -> None:
        """Best-effort low-latency kick; durable recovery remains authoritative."""

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("当前线程没有运行中的事件循环, 客户活动 AI 任务交由恢复器执行")
            return
        task = asyncio.create_task(self._run_guarded(request))
        task.add_done_callback(self._consume_task_exception)

    async def _run_guarded(self, request: CustomerActivityAIJobRequest) -> None:
        try:
            await self.run(request)
        except Exception:
            logger.exception("客户活动 AI 任务即时执行失败: job=%s", request.job_public_id)

    @staticmethod
    def _consume_task_exception(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        try:
            task.exception()
        except Exception:
            logger.exception("客户活动 AI 任务回调失败")

    def mark_completed_in_transaction(
        self,
        db: Session,
        *,
        request: CustomerActivityAIJobRequest,
        lease_token: str,
        result_json: dict[str, object],
    ) -> None:
        job = self.job_crud.mark_completed_if_lease_owner(
            db,
            team_id=request.team_id,
            public_id=request.job_public_id,
            lease_token=lease_token,
            result_json=result_json,
            commit=False,
        )
        if job is None:
            raise RuntimeError("客户活动 AI 任务租约已失效")

    def _record_failure(
        self,
        request: CustomerActivityAIJobRequest,
        *,
        lease_token: str,
        activity_id: int,
        activity_revision: int,
        attempt_count: int,
        exc: Exception,
    ) -> CustomerActivityAIJobRunResult:
        settings = get_settings()
        max_attempts = max(1, settings.CUSTOMER_ACTIVITY_AI_JOB_MAX_ATTEMPTS)
        error = f"{type(exc).__name__}: {exc}"
        db = SessionLocal()
        try:
            activity = customer_activity_crud.get_by_id(db, activity_id, request.team_id)
            if attempt_count >= max_attempts:
                result = self._result(
                    request,
                    activity_id=activity_id,
                    execution_status=CustomerActivityAIJobStatus.EXHAUSTED.value,
                    success=False,
                    retryable=False,
                    error=error,
                )
                updated = self.job_crud.mark_exhausted_if_lease_owner(
                    db,
                    team_id=request.team_id,
                    public_id=request.job_public_id,
                    lease_token=lease_token,
                    result_json=result.model_dump(),
                    error_message=error,
                    commit=False,
                )
                if (
                    updated is not None
                    and activity is not None
                    and int(activity.activity_revision or 1) == activity_revision
                ):
                    activity.processing_status = CustomerActivityProcessingStatus.FAILED.value
                    activity.processing_error = error[:4000]
                    activity.effectiveness_status = CustomerActivityEffectivenessStatus.FAILED.value
                    activity.effectiveness_error_message = error[:4000]
                db.commit()
                return result if updated is not None else self._lease_lost_result(request, activity_id)

            updated = self.job_crud.mark_retry_pending_if_lease_owner(
                db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                lease_token=lease_token,
                error_message=error,
                next_attempt_at=self._next_attempt_at(attempt_count),
                commit=False,
            )
            if (
                updated is not None
                and activity is not None
                and int(activity.activity_revision or 1) == activity_revision
            ):
                activity.processing_status = CustomerActivityProcessingStatus.PENDING.value
                activity.processing_error = error[:4000]
                activity.effectiveness_status = CustomerActivityEffectivenessStatus.PENDING.value
                activity.effectiveness_error_message = error[:4000]
            db.commit()
            if updated is None:
                return self._lease_lost_result(request, activity_id)
            return self._result(
                request,
                activity_id=activity_id,
                execution_status=CustomerActivityAIJobStatus.RETRY_PENDING.value,
                success=False,
                retryable=True,
                error=error,
            )
        finally:
            db.close()

    def _skip_after_compute(
        self,
        request: CustomerActivityAIJobRequest,
        *,
        lease_token: str,
        activity_id: int,
        reason: str,
    ) -> CustomerActivityAIJobRunResult:
        db = SessionLocal()
        try:
            job = self.job_crud.get_by_public_id(
                db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                for_update=True,
            )
            if job is None:
                return self._lease_lost_result(request, activity_id)
            return self._mark_skipped(db, job=job, lease_token=lease_token, reason=reason)
        finally:
            db.close()

    def _mark_skipped(
        self,
        db: Session,
        *,
        job: CustomerActivityAIJob,
        lease_token: str,
        reason: str,
    ) -> CustomerActivityAIJobRunResult:
        request = CustomerActivityAIJobRequest(job_public_id=str(job.public_id), team_id=int(job.team_id))
        result = self._result(
            request,
            activity_id=int(job.activity_id),
            execution_status=CustomerActivityAIJobStatus.SKIPPED.value,
            success=True,
            skip_reason=reason,
        )
        updated = self.job_crud.mark_completed_if_lease_owner(
            db,
            team_id=int(job.team_id),
            public_id=str(job.public_id),
            lease_token=lease_token,
            result_json=result.model_dump(),
            skipped=True,
            commit=False,
        )
        if updated is None:
            db.rollback()
            return self._lease_lost_result(request, int(job.activity_id))
        db.commit()
        return result

    def _terminalize_exhausted(
        self,
        db: Session,
        job: CustomerActivityAIJob,
        *,
        max_attempts: int,
        now: datetime,
    ) -> CustomerActivityAIJobRunResult:
        request = CustomerActivityAIJobRequest(job_public_id=str(job.public_id), team_id=int(job.team_id))
        result = self._result(
            request,
            activity_id=int(job.activity_id),
            execution_status=CustomerActivityAIJobStatus.EXHAUSTED.value,
            success=False,
            retryable=False,
            error=job.error_message or "customer activity AI retries exhausted",
        )
        updated = self.job_crud.finalize_retries_exhausted(
            db,
            team_id=int(job.team_id),
            public_id=str(job.public_id),
            max_attempts=max_attempts,
            result_json=result.model_dump(),
            now=now,
            commit=False,
        )
        if updated is None:
            db.rollback()
            return self._result(
                request,
                activity_id=int(job.activity_id),
                execution_status="BUSY",
                success=False,
                retryable=True,
            )
        activity = customer_activity_crud.get_by_id(db, int(job.activity_id), int(job.team_id))
        if activity is not None and int(activity.activity_revision or 1) == int(job.activity_revision):
            activity.processing_status = CustomerActivityProcessingStatus.FAILED.value
            activity.processing_error = result.error
            activity.effectiveness_status = CustomerActivityEffectivenessStatus.FAILED.value
            activity.effectiveness_error_message = result.error
        db.commit()
        return result

    @staticmethod
    def _preflight_skip_reason(
        *,
        job: CustomerActivityAIJob,
        activity: CustomerActivity | None,
    ) -> str | None:
        if activity is None:
            return "SOURCE_ACTIVITY_DELETED"
        if int(activity.activity_revision or 1) != int(job.activity_revision):
            return "SUPERSEDED_ACTIVITY_REVISION"
        if str(activity.submission_source) not in _ALLOWED_SOURCES:
            return "INVALID_SUBMISSION_SOURCE"
        return None

    @staticmethod
    def _finalization_skip_reason(exc: Exception) -> str | None:
        from app.services.customer_activity_write_service import (
            CustomerActivityRevisionSupersededError,
            CustomerActivitySourceDeletedError,
            CustomerActivitySubmissionSourceError,
        )

        if isinstance(exc, CustomerActivitySourceDeletedError):
            return "SOURCE_ACTIVITY_DELETED"
        if isinstance(exc, CustomerActivityRevisionSupersededError):
            return "SUPERSEDED_ACTIVITY_REVISION"
        if isinstance(exc, CustomerActivitySubmissionSourceError):
            return "INVALID_SUBMISSION_SOURCE"
        return None

    @staticmethod
    def _next_attempt_at(attempt_count: int) -> datetime:
        settings = get_settings()
        base = max(1, settings.CUSTOMER_ACTIVITY_AI_JOB_RETRY_BASE_SECONDS)
        return business_now() + timedelta(seconds=base * (2 ** max(0, attempt_count - 1)))

    @staticmethod
    def _result(
        request: CustomerActivityAIJobRequest,
        *,
        activity_id: int,
        execution_status: str,
        success: bool,
        retryable: bool = False,
        skip_reason: str | None = None,
        error: str | None = None,
        activity_revision: int | None = None,
        effectiveness_score: int | None = None,
    ) -> CustomerActivityAIJobRunResult:
        return CustomerActivityAIJobRunResult(
            job_public_id=request.job_public_id,
            activity_id=activity_id,
            execution_status=execution_status,
            success=success,
            retryable=retryable,
            skip_reason=skip_reason,
            error=error,
            activity_revision=activity_revision,
            effectiveness_score=effectiveness_score,
        )

    def _persisted_result(self, job: CustomerActivityAIJob) -> CustomerActivityAIJobRunResult:
        if isinstance(job.result_json, dict):
            try:
                return CustomerActivityAIJobRunResult.model_validate(job.result_json)
            except Exception:
                pass
        request = CustomerActivityAIJobRequest(job_public_id=str(job.public_id), team_id=int(job.team_id))
        return self._result(
            request,
            activity_id=int(job.activity_id),
            execution_status=str(job.status),
            success=job.status
            in {CustomerActivityAIJobStatus.COMPLETED.value, CustomerActivityAIJobStatus.SKIPPED.value},
            retryable=False,
            error=job.error_message,
        )

    def _lease_lost_result(
        self, request: CustomerActivityAIJobRequest, activity_id: int
    ) -> CustomerActivityAIJobRunResult:
        return self._result(
            request,
            activity_id=activity_id,
            execution_status="LEASE_LOST",
            success=False,
            retryable=True,
            error="execution lease ownership changed before persistence",
        )


customer_activity_ai_job_service = CustomerActivityAIJobService()

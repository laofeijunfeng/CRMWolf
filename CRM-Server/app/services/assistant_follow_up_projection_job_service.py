"""Durable Assistant 2.0 follow-up projection orchestration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from app.core.app_loop import run_on_app_loop
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.crud.assistant_follow_up_projection_job import assistant_follow_up_projection_job_crud
from app.models.assistant_follow_up_projection_job import AssistantFollowUpProjectionJobStatus
from app.models.customer_activity import CustomerActivity
from app.models.sales_commitment import FollowUpTaskProjectionStatus, FollowUpTaskProjectionTrigger
from app.services.follow_up_task_projection_service import (
    FollowUpTaskProjectionResult,
    follow_up_task_projection_service,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class AssistantFollowUpProjectionJobRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_public_id: str
    team_id: int
    status: str = AssistantFollowUpProjectionJobStatus.QUEUED
    result_json: dict[str, object] | None = None

class AssistantFollowUpProjectionJobService:
    def enqueue_in_transaction(
        self,
        db: Session,
        *,
        activity: CustomerActivity,
        actor_id: str | None,
    ) -> AssistantFollowUpProjectionJobRequest:
        job = assistant_follow_up_projection_job_crud.enqueue(
            db,
            team_id=int(activity.team_id),
            activity_id=int(activity.id),
            activity_revision=int(activity.activity_revision or 1),
            trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_CREATED_DETERMINISTIC,
            actor_id=actor_id,
            commit=False,
        )
        return AssistantFollowUpProjectionJobRequest(
            job_public_id=str(job.public_id),
            team_id=int(job.team_id),
            status=str(job.status),
            result_json=job.result_json,
        )

    def kick(self, request: AssistantFollowUpProjectionJobRequest) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("当前线程没有运行中的事件循环, Assistant 2.0 跟进任务投影交由恢复器执行")
            return
        run_on_app_loop(partial(self._start, request), f"follow-up projection job={request.job_public_id}")

    def _start(self, request: AssistantFollowUpProjectionJobRequest) -> None:
        task = asyncio.create_task(self._run_guarded(request))
        task.add_done_callback(self._consume_task_exception)

    async def run(self, request: AssistantFollowUpProjectionJobRequest) -> dict[str, object]:
        settings = get_settings()
        max_attempts = max(1, settings.CUSTOMER_ACTIVITY_POST_COMMIT_MAX_ATTEMPTS)
        lease_token = uuid4().hex
        claimed_at = business_now()
        lease_expires_at = claimed_at + timedelta(
            seconds=max(30, settings.CUSTOMER_ACTIVITY_POST_COMMIT_LEASE_SECONDS)
        )
        existing = None
        job = None
        claimed_attempt_count = None
        validation_error = None
        db = SessionLocal()
        try:
            existing = assistant_follow_up_projection_job_crud.get_by_public_id(
                db, team_id=request.team_id, public_id=request.job_public_id
            )
            if existing is None:
                raise ValueError("Assistant 2.0 跟进任务投影任务不存在")
            if existing.status in AssistantFollowUpProjectionJobStatus.TERMINAL:
                return dict(existing.result_json or {})
            lease_active = (
                existing.status == AssistantFollowUpProjectionJobStatus.RUNNING
                and existing.lease_expires_at is not None
                and existing.lease_expires_at > claimed_at
            )
            if int(existing.attempt_count or 0) >= max_attempts and not lease_active:
                result = self._exhausted_result(int(existing.activity_id))
                assistant_follow_up_projection_job_crud.mark_exhausted_without_lease(
                    db,
                    team_id=request.team_id,
                    public_id=request.job_public_id,
                    result_json=result,
                    error_message="projection attempts exhausted",
                )
                return result
            job = assistant_follow_up_projection_job_crud.claim_for_execution(
                db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
                max_attempts=max_attempts,
                now=claimed_at,
            )
            if job is None:
                return self._busy_result(int(existing.activity_id) if existing is not None else 0)
            activity_id = int(job.activity_id)
            team_id = int(job.team_id)
            actor_id = str(job.actor_id) if job.actor_id is not None else None
            attempt_count = int(job.attempt_count or 1)
            claimed_attempt_count = attempt_count
            activity_revision = int(job.activity_revision)
            activity = db.query(CustomerActivity).filter(CustomerActivity.id == activity_id).one_or_none()
            if activity is None:
                raise ValueError("Assistant 2.0 跟进任务来源活动不存在")
            if int(activity.team_id) != team_id:
                raise ValueError("Assistant 2.0 跟进任务来源活动租户不匹配")
            if int(activity.activity_revision or 1) != int(job.activity_revision):
                raise ValueError("Assistant 2.0 跟进任务来源活动版本已变化")
            if activity.submission_source != "ASSISTANT_2":
                raise ValueError("Assistant 2.0 跟进任务来源活动提交来源不匹配")
        except Exception as exc:
            validation_error = exc
        finally:
            db.close()
        if validation_error is not None:
            return await self._record_failure(
                request,
                lease_token=lease_token,
                activity_id=int(existing.activity_id) if existing is not None else 0,
                attempt_count=(
                    claimed_attempt_count
                    if claimed_attempt_count is not None
                    else int(existing.attempt_count or 1)
                    if existing is not None
                    else 1
                ),
                error_message=str(validation_error),
            )

        projection_db = SessionLocal()
        try:
            locked_job = assistant_follow_up_projection_job_crud.get_by_public_id(
                projection_db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                for_update=True,
            )
            if not assistant_follow_up_projection_job_crud._owns_running_lease(locked_job, lease_token):
                projection_db.rollback()
                return self._busy_result(activity_id)
            projection = follow_up_task_projection_service.run_activity_projection(
                projection_db,
                activity_id=activity_id,
                trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_CREATED_DETERMINISTIC,
                actor_id=actor_id,
                team_id=team_id,
                attempt_count=attempt_count,
                expected_activity_revision=activity_revision,
                expected_submission_source="ASSISTANT_2",
                commit=False,
            )
            # Refresh under the row lock: a test double or a database backend
            # that permits lease transfer must still fence the final commit.
            current_job = assistant_follow_up_projection_job_crud.get_by_public_id(
                projection_db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                for_update=True,
            )
            if not assistant_follow_up_projection_job_crud._owns_running_lease(current_job, lease_token):
                projection_db.rollback()
                return self._busy_result(activity_id)
            result = self._projection_result(projection, activity_id=activity_id)
            if projection.projection_run_status == FollowUpTaskProjectionStatus.FAILED:
                return await self._record_failure(
                    request,
                    lease_token=lease_token,
                    activity_id=activity_id,
                    attempt_count=attempt_count,
                    error_message=projection.error_message or "follow-up projection failed",
                    db=projection_db,
                )
            updated = assistant_follow_up_projection_job_crud.mark_completed_if_lease_owner(
                projection_db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                lease_token=lease_token,
                result_json=result,
                skipped=projection.projection_run_status == FollowUpTaskProjectionStatus.SKIPPED,
                commit=False,
            )
            if updated is None:
                projection_db.rollback()
                return self._busy_result(activity_id)
            projection_db.commit()
            return result
        except Exception as exc:
            projection_db.rollback()
            return await self._record_failure(
                request,
                lease_token=lease_token,
                activity_id=activity_id,
                attempt_count=attempt_count,
                error_message=str(exc),
            )
        finally:
            projection_db.close()

    async def _record_failure(
        self,
        request: AssistantFollowUpProjectionJobRequest,
        *,
        lease_token: str,
        activity_id: int,
        attempt_count: int,
        error_message: str,
        db: Session | None = None,
    ) -> dict[str, object]:
        owned_db = db or SessionLocal()
        try:
            settings = get_settings()
            max_attempts = max(1, settings.CUSTOMER_ACTIVITY_POST_COMMIT_MAX_ATTEMPTS)
            if attempt_count >= max_attempts:
                result = {
                    "success": False,
                    "activity_id": activity_id,
                    "execution_status": "RETRIES_EXHAUSTED",
                    "error": error_message,
                }
                updated = assistant_follow_up_projection_job_crud.mark_exhausted_if_lease_owner(
                    owned_db,
                    team_id=request.team_id,
                    public_id=request.job_public_id,
                    lease_token=lease_token,
                    result_json=result,
                    error_message=error_message,
                )
                return result if updated is not None else self._busy_result(activity_id)
            next_attempt_at = self._next_attempt_at(attempt_count)
            updated = assistant_follow_up_projection_job_crud.mark_failed_if_lease_owner(
                owned_db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                lease_token=lease_token,
                error_message=error_message,
                next_attempt_at=next_attempt_at,
            )
            return {
                "success": False,
                "activity_id": activity_id,
                "execution_status": "FAILED",
                "retryable": updated is not None,
                "error": error_message,
            }
        finally:
            if db is None:
                owned_db.close()

    @staticmethod
    def _projection_result(result: FollowUpTaskProjectionResult, *, activity_id: int) -> dict[str, object]:
        return {
            "success": result.projection_run_status != FollowUpTaskProjectionStatus.FAILED,
            "activity_id": activity_id,
            "projection_run_id": result.projection_run_id,
            "projection_run_status": result.projection_run_status,
            "skip_reason": result.skip_reason,
            "created_task_ids": result.created_task_ids,
            "updated_task_ids": result.updated_task_ids,
            "cancelled_task_ids": result.cancelled_task_ids,
            "error": result.error_message,
        }

    @staticmethod
    def _next_attempt_at(attempt_count: int) -> datetime:
        settings = get_settings()
        base = max(1, settings.CUSTOMER_ACTIVITY_POST_COMMIT_RETRY_BASE_SECONDS)
        return business_now() + timedelta(seconds=base * (2 ** max(0, attempt_count - 1)))

    @staticmethod
    def _exhausted_result(activity_id: int) -> dict[str, object]:
        return {
            "success": False,
            "activity_id": activity_id,
            "execution_status": "RETRIES_EXHAUSTED",
            "retryable": False,
            "error": "projection attempts exhausted",
        }

    @staticmethod
    def _busy_result(activity_id: int) -> dict[str, object]:
        return {"success": False, "busy": True, "activity_id": activity_id, "execution_status": "BUSY"}

    @staticmethod
    def _consume_task_exception(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        try:
            task.exception()
        except Exception:
            logger.exception("Assistant 2.0 跟进任务投影后台回调失败")

    async def _run_guarded(self, request: AssistantFollowUpProjectionJobRequest) -> None:
        try:
            await self.run(request)
        except Exception:
            logger.exception("Assistant 2.0 跟进任务投影即时执行失败: job=%s", request.job_public_id)


assistant_follow_up_projection_job_service = AssistantFollowUpProjectionJobService()

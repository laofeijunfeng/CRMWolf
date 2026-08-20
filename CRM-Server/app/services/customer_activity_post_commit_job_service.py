"""Durable orchestration for customer-activity post-commit workflows."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.crud.customer_activity import customer_activity_crud
from app.crud.customer_activity_post_commit_job import customer_activity_post_commit_job_crud
from app.models.customer_activity_post_commit_job import (
    CustomerActivityPostCommitJob,
    CustomerActivityPostCommitJobStatus,
)
from app.services.customer_activity_post_commit_operation_projector import (
    customer_activity_post_commit_operation_projector,
)
from app.services.customer_activity_post_commit_workflow import customer_activity_post_commit_workflow
from app.services.follow_up_task_confirmation_agent_message_card_service import (
    follow_up_task_confirmation_agent_message_card_service,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

    from app.models.customer_activity import CustomerActivity


logger = logging.getLogger(__name__)


class CustomerActivityPostCommitJobRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_public_id: str
    team_id: int


class CustomerActivityPostCommitJobService:
    """Owns enqueue, execution, retry and recovery of post-commit work."""

    def enqueue_in_transaction(
        self,
        db: Session,
        *,
        activity: CustomerActivity,
        trigger_type: str,
        actor_id: str | None = None,
    ) -> CustomerActivityPostCommitJobRequest:
        """Write the revision-scoped durable job in the caller's transaction."""

        job = customer_activity_post_commit_job_crud.enqueue(
            db,
            team_id=int(activity.team_id),
            activity_id=int(activity.id),
            activity_revision=int(activity.post_commit_revision or 1),
            trigger_type=trigger_type,
            actor_id=actor_id,
            commit=False,
        )
        return CustomerActivityPostCommitJobRequest(
            job_public_id=str(job.public_id),
            team_id=int(job.team_id),
        )

    def enqueue(
        self,
        *,
        activity_id: int,
        team_id: int,
        trigger_type: str,
        actor_id: str | None = None,
        activity_revision: int | None = None,
    ) -> CustomerActivityPostCommitJobRequest:
        db = SessionLocal()
        try:
            activity = customer_activity_crud.get_by_id(db, activity_id, team_id)
            if activity is None:
                raise ValueError("客户活动不存在")
            revision = int(activity_revision or activity.post_commit_revision or 1)
            job = customer_activity_post_commit_job_crud.enqueue(
                db,
                team_id=team_id,
                activity_id=activity_id,
                activity_revision=revision,
                trigger_type=trigger_type,
                actor_id=actor_id,
                commit=True,
            )
            return CustomerActivityPostCommitJobRequest(job_public_id=job.public_id, team_id=team_id)
        finally:
            db.close()

    async def run(self, request: CustomerActivityPostCommitJobRequest) -> dict[str, object]:
        settings = get_settings()
        lease_token = uuid4().hex
        claimed_at = business_now()
        lease_expires_at = claimed_at + timedelta(seconds=max(30, settings.CUSTOMER_ACTIVITY_POST_COMMIT_LEASE_SECONDS))
        db = SessionLocal()
        try:
            existing = customer_activity_post_commit_job_crud.get_by_public_id(
                db,
                team_id=request.team_id,
                public_id=request.job_public_id,
            )
            if existing is None:
                raise ValueError("客户活动后提交任务不存在")
            if existing.status in CustomerActivityPostCommitJobStatus.TERMINAL:
                self._project_bound_operation(db, existing)
                return dict(existing.result_json or {})
            max_attempts = max(1, settings.CUSTOMER_ACTIVITY_POST_COMMIT_MAX_ATTEMPTS)
            if int(existing.attempt_count or 0) >= max_attempts:
                terminal_result = self._retries_exhausted_result(
                    existing.activity_id,
                    error_message=existing.error_message,
                )
                finalized = customer_activity_post_commit_job_crud.finalize_retries_exhausted(
                    db,
                    team_id=request.team_id,
                    public_id=request.job_public_id,
                    max_attempts=max_attempts,
                    result_json=terminal_result,
                    now=claimed_at,
                )
                if finalized is not None and finalized.status in CustomerActivityPostCommitJobStatus.TERMINAL:
                    self._project_bound_operation(db, finalized)
                    return dict(finalized.result_json or terminal_result)
                return self._busy_result(existing.activity_id)
            job = customer_activity_post_commit_job_crud.claim_for_execution(
                db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
                max_attempts=max_attempts,
                now=claimed_at,
            )
            if job is None:
                return self._busy_result(existing.activity_id)

            activity = customer_activity_crud.get_by_id(db, job.activity_id, job.team_id)
            if activity is None:
                result = self._skipped_result(job.activity_id, "ACTIVITY_NOT_FOUND")
                updated = customer_activity_post_commit_job_crud.mark_completed_if_lease_owner(
                    db,
                    team_id=job.team_id,
                    public_id=job.public_id,
                    lease_token=lease_token,
                    result_json=result,
                    skipped=True,
                )
                self._project_bound_operation(db, updated or job)
                return result
            if int(activity.post_commit_revision or 1) != int(job.activity_revision):
                result = self._skipped_result(job.activity_id, "SUPERSEDED_ACTIVITY_REVISION")
                updated = customer_activity_post_commit_job_crud.mark_completed_if_lease_owner(
                    db,
                    team_id=job.team_id,
                    public_id=job.public_id,
                    lease_token=lease_token,
                    result_json=result,
                    skipped=True,
                )
                self._project_bound_operation(db, updated or job)
                return result
            job_data = {
                "activity_id": int(job.activity_id),
                "team_id": int(job.team_id),
                "trigger_type": str(job.trigger_type),
                "actor_id": str(job.actor_id) if job.actor_id is not None else None,
                "run_id": str(job.run_id),
                "graph_thread_id": str(job.graph_thread_id),
                "activity_revision": int(job.activity_revision),
                "attempt_count": int(job.attempt_count or 1),
            }
            self._project_bound_operation(db, job)
        finally:
            db.close()

        try:
            state = await customer_activity_post_commit_workflow.run(
                activity_id=job_data["activity_id"],
                team_id=job_data["team_id"],
                expected_activity_revision=job_data["activity_revision"],
                trigger_type=job_data["trigger_type"],
                actor_id=job_data["actor_id"],
                run_id=job_data["run_id"],
                thread_id=job_data["graph_thread_id"],
            )
            result = self._result_from_state(job_data["activity_id"], state)
        except Exception as exc:
            failure_result = await self._record_failure(
                request,
                lease_token=lease_token,
                activity_id=job_data["activity_id"],
                attempt_count=job_data["attempt_count"],
                exc=exc,
            )
            if failure_result is not None:
                return failure_result
            raise

        db = SessionLocal()
        try:
            workflow_error = str(result.get("error") or "").strip()
            if workflow_error and job_data["attempt_count"] >= max_attempts:
                post_commit = result.get("post_commit")
                result = self._retries_exhausted_result(
                    job_data["activity_id"],
                    error_message=workflow_error,
                    post_commit=post_commit if isinstance(post_commit, dict) else None,
                )
                updated = customer_activity_post_commit_job_crud.mark_exhausted_if_lease_owner(
                    db,
                    team_id=request.team_id,
                    public_id=request.job_public_id,
                    lease_token=lease_token,
                    result_json=result,
                    error_message=workflow_error,
                )
            elif workflow_error:
                updated = customer_activity_post_commit_job_crud.mark_failed_if_lease_owner(
                    db,
                    team_id=request.team_id,
                    public_id=request.job_public_id,
                    lease_token=lease_token,
                    error_message=workflow_error,
                    next_attempt_at=self._next_attempt_at(job_data["attempt_count"]),
                )
            else:
                updated = customer_activity_post_commit_job_crud.mark_completed_if_lease_owner(
                    db,
                    team_id=request.team_id,
                    public_id=request.job_public_id,
                    lease_token=lease_token,
                    result_json=result,
                    skipped=bool(result.get("skip_reason")),
                )
            if updated is None:
                logger.warning(
                    "客户活动后提交任务执行结果因租约已变更被忽略: job=%s",
                    request.job_public_id,
                )
                return self._lease_lost_result(job_data["activity_id"])
            self._project_bound_operation(db, updated)
            return result
        finally:
            db.close()

    @staticmethod
    def _project_bound_operation(db: Session, job: CustomerActivityPostCommitJob | None) -> None:
        if job is None:
            return
        try:
            projected = customer_activity_post_commit_operation_projector.project_job(db, job)
            if projected is not None:
                follow_up_task_confirmation_agent_message_card_service.ensure_job_cards(
                    db,
                    job=job,
                    commit=False,
                )
                db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "投影客户活动后提交异步操作失败: job=%s",
                getattr(job, "public_id", None),
            )

    def kick(self, request: CustomerActivityPostCommitJobRequest) -> None:
        """Best-effort latency optimization; durable recovery remains authoritative."""

        task = asyncio.create_task(self._run_guarded(request))
        task.add_done_callback(self._consume_task_exception)

    async def _run_guarded(self, request: CustomerActivityPostCommitJobRequest) -> None:
        try:
            await self.run(request)
        except Exception:
            logger.exception("客户活动后提交任务即时执行失败: job=%s", request.job_public_id)

    async def _record_failure(
        self,
        request: CustomerActivityPostCommitJobRequest,
        *,
        lease_token: str,
        activity_id: int,
        attempt_count: int,
        exc: Exception,
    ) -> dict[str, object] | None:
        settings = get_settings()
        max_attempts = max(1, settings.CUSTOMER_ACTIVITY_POST_COMMIT_MAX_ATTEMPTS)
        db = SessionLocal()
        try:
            if attempt_count >= max_attempts:
                result = self._retries_exhausted_result(activity_id, error_message=str(exc))
                updated = customer_activity_post_commit_job_crud.mark_exhausted_if_lease_owner(
                    db,
                    team_id=request.team_id,
                    public_id=request.job_public_id,
                    lease_token=lease_token,
                    result_json=result,
                    error_message=str(exc),
                )
                if updated is not None:
                    self._project_bound_operation(db, updated)
                    return result
            else:
                updated = customer_activity_post_commit_job_crud.mark_failed_if_lease_owner(
                    db,
                    team_id=request.team_id,
                    public_id=request.job_public_id,
                    lease_token=lease_token,
                    error_message=str(exc),
                    next_attempt_at=self._next_attempt_at(attempt_count),
                )
                if updated is not None:
                    self._project_bound_operation(db, updated)
                    return None
            logger.warning(
                "客户活动后提交任务失败结果因租约已变更被忽略: job=%s",
                request.job_public_id,
            )
            return self._lease_lost_result(activity_id)
        finally:
            db.close()

    @staticmethod
    def _consume_task_exception(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        try:
            task.exception()
        except Exception:
            logger.exception("客户活动后提交后台任务回调失败")

    @staticmethod
    def _next_attempt_at(attempt_count: int | None) -> datetime:
        settings = get_settings()
        base = max(1, settings.CUSTOMER_ACTIVITY_POST_COMMIT_RETRY_BASE_SECONDS)
        exponent = max(0, int(attempt_count or 1) - 1)
        return business_now() + timedelta(seconds=base * (2**exponent))

    @staticmethod
    def _result_from_state(activity_id: int, state: dict[str, object]) -> dict[str, object]:
        return {
            "success": not bool(state.get("error_message")),
            "activity_id": activity_id,
            "skip_reason": state.get("skip_reason"),
            "error": state.get("error_message"),
            "projection_result": state.get("projection_result"),
            "match_result": state.get("match_result"),
            "transition_plan": state.get("transition_plan"),
            "policy_results": state.get("policy_results") or [],
            "execution_results": state.get("execution_results") or [],
            "confirmation_cases": state.get("confirmation_cases") or [],
            "post_commit": state.get("post_commit") or _empty_post_commit_outcome(),
        }

    @staticmethod
    def _retries_exhausted_result(
        activity_id: int,
        *,
        error_message: str | None,
        post_commit: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return {
            "success": False,
            "busy": False,
            "retryable": False,
            "execution_status": "RETRIES_EXHAUSTED",
            "activity_id": activity_id,
            "skip_reason": None,
            "error": error_message or "customer activity post-commit retries exhausted",
            "post_commit": post_commit or _empty_post_commit_outcome(),
        }

    @staticmethod
    def _busy_result(activity_id: int) -> dict[str, object]:
        return {
            "success": False,
            "busy": True,
            "execution_status": "BUSY",
            "activity_id": activity_id,
            "skip_reason": None,
            "error": None,
            "post_commit": _empty_post_commit_outcome(),
        }

    @staticmethod
    def _lease_lost_result(activity_id: int) -> dict[str, object]:
        return {
            "success": False,
            "busy": False,
            "execution_status": "LEASE_LOST",
            "activity_id": activity_id,
            "skip_reason": None,
            "error": "execution lease ownership changed before persistence",
            "post_commit": _empty_post_commit_outcome(),
        }

    @staticmethod
    def _skipped_result(activity_id: int, reason: str) -> dict[str, object]:
        return {
            "success": True,
            "activity_id": activity_id,
            "skip_reason": reason,
            "error": None,
            "post_commit": _empty_post_commit_outcome(),
        }


def _empty_post_commit_outcome() -> dict[str, object]:
    return {
        "needs_user_confirmation": False,
        "confirmation_case_public_ids": [],
        "confirmation_cases": [],
        "created_confirmation_case_count": 0,
        "confirmation_deliveries": [],
        "prompt_policy": {
            "prompt_scope": "current_activity",
            "delivery": "durable_confirmation_inbox",
        },
    }


customer_activity_post_commit_job_service = CustomerActivityPostCommitJobService()

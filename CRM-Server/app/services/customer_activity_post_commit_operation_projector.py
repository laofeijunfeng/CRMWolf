"""Materialize durable customer-activity post-commit jobs into Agent UI operations.

The post-commit job is the authoritative execution record. Agent operations are a
late-bindable, replayable projection and must never determine whether matching
runs or reaches a terminal state.

A revision-scoped job may be skipped as SUPERSEDED_ACTIVITY_REVISION when the
activity is rewritten during AI processing. That skip is not matcher completion.
The projection follows the latest job for the same activity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.crud.customer_activity_post_commit_job import customer_activity_post_commit_job_crud
from app.models.agent_async_operation import AgentAsyncOperation, AgentAsyncOperationStatus
from app.models.customer_activity_post_commit_job import (
    CustomerActivityPostCommitJob,
    CustomerActivityPostCommitJobStatus,
)
from app.services.agent.async_operation_service import (
    AgentAsyncOperationService,
    agent_async_operation_service,
)
from app.services.agent.types import coerce_json_dict

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_SUPERSEDED_SKIP_REASON = "SUPERSEDED_ACTIVITY_REVISION"
_IN_PROGRESS_SUMMARY = "跟进已记录，任务对账处理中"
_COMPLETED_SUMMARY = "跟进已记录，任务对账完成"


class CustomerActivityPostCommitOperationProjector:
    """Own the consistency seam between post-commit jobs and UI projections."""

    def __init__(
        self,
        *,
        operation_service: AgentAsyncOperationService | None = None,
    ) -> None:
        self.operation_service = operation_service or agent_async_operation_service

    def project_job(
        self,
        db: Session,
        job: CustomerActivityPostCommitJob,
        *,
        operation_public_id: str | None = None,
    ) -> AgentAsyncOperation | None:
        authoritative = self._authoritative_job(db, job)
        operation = self._resolve_operation(
            db,
            authoritative,
            fallback_request_id=str(job.public_id),
            operation_public_id=operation_public_id,
        )
        if operation is None:
            return None
        if self._is_superseded(authoritative):
            return self._keep_in_progress(db, operation, authoritative)
        return self._project(db, operation, authoritative)

    def project_request(
        self,
        db: Session,
        *,
        team_id: int,
        request_id: str,
        operation_public_id: str | None = None,
    ) -> AgentAsyncOperation | None:
        job = customer_activity_post_commit_job_crud.get_by_public_id(
            db,
            team_id=team_id,
            public_id=request_id,
        )
        if job is None:
            return None
        return self.project_job(
            db,
            job,
            operation_public_id=operation_public_id,
        )

    def _authoritative_job(
        self,
        db: Session,
        job: CustomerActivityPostCommitJob,
    ) -> CustomerActivityPostCommitJob:
        if not self._is_superseded(job):
            return job
        latest = customer_activity_post_commit_job_crud.get_latest_by_activity(
            db,
            team_id=int(job.team_id),
            activity_id=int(job.activity_id),
        )
        if latest is None or str(latest.public_id) == str(job.public_id):
            return job
        return latest

    def _resolve_operation(
        self,
        db: Session,
        job: CustomerActivityPostCommitJob,
        *,
        fallback_request_id: str | None = None,
        operation_public_id: str | None = None,
    ) -> AgentAsyncOperation | None:
        request_ids = [str(job.public_id)]
        if fallback_request_id and fallback_request_id not in request_ids:
            request_ids.append(fallback_request_id)
        for request_id in request_ids:
            operation = self.operation_service.get_for_update(
                db,
                team_id=int(job.team_id),
                request_id=request_id,
                operation_public_id=operation_public_id,
            )
            if operation is not None:
                return operation
        query = db.query(AgentAsyncOperation).filter(
            AgentAsyncOperation.team_id == int(job.team_id),
            AgentAsyncOperation.operation_type == "customer_activity_post_commit",
            AgentAsyncOperation.resource_type == "customer_activity",
            AgentAsyncOperation.resource_id == int(job.activity_id),
        )
        if operation_public_id:
            query = query.filter(AgentAsyncOperation.public_id == operation_public_id)
        return query.order_by(AgentAsyncOperation.id.desc()).populate_existing().with_for_update().first()

    def _keep_in_progress(
        self,
        db: Session,
        operation: AgentAsyncOperation,
        job: CustomerActivityPostCommitJob,
    ) -> AgentAsyncOperation:
        if str(operation.status) == AgentAsyncOperationStatus.QUEUED:
            return self.operation_service.mark_running(
                db,
                operation,
                graph_thread_id=str(job.graph_thread_id) if job.graph_thread_id else None,
                summary=_IN_PROGRESS_SUMMARY,
            )
        return operation

    def _project(
        self,
        db: Session,
        operation: AgentAsyncOperation,
        job: CustomerActivityPostCommitJob,
    ) -> AgentAsyncOperation:
        job_status = str(job.status)
        if job_status == CustomerActivityPostCommitJobStatus.QUEUED:
            return operation
        if job_status == CustomerActivityPostCommitJobStatus.RUNNING:
            if str(operation.status) == AgentAsyncOperationStatus.QUEUED:
                return self.operation_service.mark_running(
                    db,
                    operation,
                    graph_thread_id=str(job.graph_thread_id) if job.graph_thread_id else None,
                    summary=_IN_PROGRESS_SUMMARY,
                )
            return operation
        if job_status in {
            CustomerActivityPostCommitJobStatus.COMPLETED,
            CustomerActivityPostCommitJobStatus.SKIPPED,
        }:
            return self.operation_service.complete(
                db,
                operation,
                degraded=False,
                summary=_COMPLETED_SUMMARY,
                result=coerce_json_dict(job.result_json),
            )
        if job_status == CustomerActivityPostCommitJobStatus.FAILED:
            return self.operation_service.fail(
                db,
                operation,
                error_message=str(job.error_message or "customer activity post-commit failed"),
                retry_at=job.next_attempt_at,
                summary="跟进已记录，任务对账将自动重试",
            )
        if job_status == CustomerActivityPostCommitJobStatus.EXHAUSTED:
            return self.operation_service.fail(
                db,
                operation,
                error_message=str(job.error_message or "customer activity post-commit retries exhausted"),
                summary="跟进已记录，任务对账失败",
            )
        return operation

    @staticmethod
    def _is_superseded(job: CustomerActivityPostCommitJob) -> bool:
        if str(job.status) != CustomerActivityPostCommitJobStatus.SKIPPED:
            return False
        result = job.result_json if isinstance(job.result_json, dict) else {}
        return str(result.get("skip_reason") or "") == _SUPERSEDED_SKIP_REASON


customer_activity_post_commit_operation_projector = CustomerActivityPostCommitOperationProjector()

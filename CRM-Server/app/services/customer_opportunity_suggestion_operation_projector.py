"""Project durable opportunity-suggestion jobs into Agent operations.

The suggestion job is authoritative.  This module only materializes its current
snapshot for the owning Agent turn; it never creates an opportunity or moves a
stage.  Those business writes remain separate resumable Agent workflows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.crud.customer_opportunity_suggestion_job import (
    customer_opportunity_suggestion_job_crud,
)
from app.models.agent_async_operation import AgentAsyncOperation, AgentAsyncOperationStatus
from app.models.customer_opportunity_suggestion_job import CustomerOpportunitySuggestionJob
from app.services.agent.async_operation_service import (
    AgentAsyncOperationService,
    agent_async_operation_service,
)
from app.services.agent.types import coerce_json_dict
from app.services.customer_activity_contracts import CustomerActivitySuggestionJobStatus

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.customer_opportunity_suggestion_job import CustomerOpportunitySuggestionJob

_CREATE = "CREATE_OPPORTUNITY"
_MOVE = "MOVE_OPPORTUNITY_STAGE"
_NO_ACTION = "NO_ACTION"

_QUEUED = CustomerActivitySuggestionJobStatus.QUEUED.value
_RUNNING = CustomerActivitySuggestionJobStatus.RUNNING.value
_RETRY_PENDING = CustomerActivitySuggestionJobStatus.RETRY_PENDING.value
_COMPLETED = CustomerActivitySuggestionJobStatus.COMPLETED.value
_SKIPPED = CustomerActivitySuggestionJobStatus.SKIPPED.value
_EXHAUSTED = CustomerActivitySuggestionJobStatus.EXHAUSTED.value


class CustomerOpportunitySuggestionOperationProjector:
    """Keep the user-visible operation convergent with one suggestion job."""

    def __init__(
        self,
        *,
        operation_service: AgentAsyncOperationService | None = None,
    ) -> None:
        self.operation_service = operation_service or agent_async_operation_service

    def project_job(
        self,
        db: Session,
        job: CustomerOpportunitySuggestionJob,
        *,
        operation_public_id: str | None = None,
    ) -> AgentAsyncOperation | None:
        operation = self._resolve_operation(
            db,
            job,
            operation_public_id=operation_public_id,
        )
        if operation is None:
            return None

        status = str(job.status)
        result = coerce_json_dict(job.result_json)
        if status == _QUEUED:
            return operation
        if status == _RUNNING:
            if str(operation.status) in {
                AgentAsyncOperationStatus.QUEUED,
                AgentAsyncOperationStatus.RETRY_SCHEDULED,
            }:
                return self.operation_service.mark_running(
                    db,
                    operation,
                    graph_thread_id=str(job.graph_thread_id) if job.graph_thread_id else None,
                    summary="正在分析是否需要推进商机",
                )
            return operation
        if status == _RETRY_PENDING:
            return self.operation_service.fail(
                db,
                operation,
                error_message=str(job.error_message or "商机建议任务暂未完成"),
                retry_at=job.next_attempt_at,
                summary="跟进已记录，商机建议将自动重试",  # noqa: RUF001
            )
        if status == _COMPLETED:
            return self._project_completed(db, operation, job, result)
        if status == _SKIPPED:
            return self.operation_service.cancel(
                db,
                operation,
                summary=self._skip_summary(result),
                result=self._result_payload(job, result),
            )
        if status == _EXHAUSTED:
            return self.operation_service.fail(
                db,
                operation,
                error_message=str(job.error_message or "商机建议任务重试次数已耗尽"),
                summary="跟进已记录，商机建议分析失败",  # noqa: RUF001
            )
        return operation

    def project_request(
        self,
        db: Session,
        *,
        team_id: int,
        request_id: str,
        operation_public_id: str | None = None,
    ) -> AgentAsyncOperation | None:
        job = customer_opportunity_suggestion_job_crud.get_by_public_id(
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

    def _resolve_operation(
        self,
        db: Session,
        job: CustomerOpportunitySuggestionJob,
        *,
        operation_public_id: str | None,
    ) -> AgentAsyncOperation | None:
        operation = self.operation_service.get_for_update(
            db,
            team_id=int(job.team_id),
            request_id=str(job.public_id),
            operation_public_id=operation_public_id,
        )
        if operation is not None:
            return operation
        query = db.query(AgentAsyncOperation).filter(
            AgentAsyncOperation.team_id == int(job.team_id),
            AgentAsyncOperation.operation_type == "customer_opportunity_suggestion",
            AgentAsyncOperation.resource_type == "customer_activity",
            AgentAsyncOperation.resource_id == int(job.activity_id),
            AgentAsyncOperation.request_id == str(job.public_id),
        )
        if operation_public_id:
            query = query.filter(AgentAsyncOperation.public_id == operation_public_id)
        return query.order_by(AgentAsyncOperation.id.desc()).populate_existing().with_for_update().first()

    def _project_completed(
        self,
        db: Session,
        operation: AgentAsyncOperation,
        job: CustomerOpportunitySuggestionJob,
        result: dict[str, Any],
    ) -> AgentAsyncOperation:
        decision = str(result.get("decision") or _NO_ACTION)
        payload = self._result_payload(job, result)
        suggestion = result.get("suggestion")
        if isinstance(suggestion, dict):
            payload["suggestion"] = suggestion

        if decision in {_CREATE, _MOVE}:
            payload["requires_user_action"] = True
            payload["continuation_kind"] = "create_opportunity" if decision == _CREATE else "move_opportunity_stage"
            return self.operation_service.wait_for_user(
                db,
                operation,
                summary=(
                    "发现一个明确的商机机会，等待确认创建"  # noqa: RUF001
                    if decision == _CREATE
                    else "发现一个明确的商机推进建议，等待确认"  # noqa: RUF001
                ),
                result=payload,
            )

        payload["requires_user_action"] = False
        return self.operation_service.complete(
            db,
            operation,
            degraded=False,
            summary=(
                "已确认已有商机，无需重复创建"  # noqa: RUF001
                if result.get("silent_reason") == "HIGH_CONFIDENCE_EXISTING_OPPORTUNITY"
                else "商机建议分析完成，暂无需要处理的商机"  # noqa: RUF001
            ),
            result=payload,
        )

    @staticmethod
    def _result_payload(
        job: CustomerOpportunitySuggestionJob,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(result)
        payload.setdefault("job_public_id", str(job.public_id))
        payload.setdefault("activity_id", int(job.activity_id))
        payload.setdefault("activity_revision", int(job.activity_revision))
        payload.setdefault("job_status", str(job.status))
        return payload

    @staticmethod
    def _skip_summary(result: dict[str, Any]) -> str:
        reason = str(result.get("skip_reason") or "")
        if reason == "SOURCE_ACTIVITY_DELETED":
            return "源跟进已删除，商机建议未执行"  # noqa: RUF001
        return "商机建议未执行"


customer_opportunity_suggestion_operation_projector = CustomerOpportunitySuggestionOperationProjector()

"""Durable application projection for hidden PendingTask application steps."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Protocol
from uuid import uuid4

from app.crud.agent_pending_application_step import agent_pending_application_step_crud
from app.models.agent_pending_application_step import AgentPendingApplicationStepStatus
from app.services.agent.pending_application_step_contracts import (
    PendingApplicationStepRequest,
    is_pending_application_step_request,
)
from app.services.agent.pending_continuation import pending_task_continuation_from_json
from app.services.agent.pending_effects import (
    PendingTaskSideEffectContext,
    project_pending_task_effect_intents,
)
from app.services.agent.types import JSONDict, coerce_json_dict
from app.utils.time import business_now


@dataclass
class PendingApplicationStepExecutionRequest:
    db: object
    session: object
    task: object | None
    team_id: int
    user_id: int
    session_id: int
    authorization: str
    step: PendingApplicationStepRequest


class PendingApplicationStepExecutor(Protocol):
    async def execute(self, request: PendingApplicationStepExecutionRequest) -> JSONDict: ...


@dataclass
class PendingApplicationStepProjectionRequest:
    db: object
    session: object
    team_id: int
    user_id: int
    session_id: int
    root_thread_id: str
    step: PendingApplicationStepRequest
    task: object | None = None
    authorization: str = ""


@dataclass
class PendingApplicationStepProjectionResult:
    status: str
    step_id: str
    result: JSONDict = field(default_factory=dict)
    replayed: bool = False
    busy: bool = False
    retryable: bool = False
    failure_reason: str | None = None


class MissingPendingApplicationStepExecutor:
    async def execute(self, _request: PendingApplicationStepExecutionRequest) -> JSONDict:
        raise RuntimeError("pending application-step executor is not configured")


class PendingApplicationStepProjector:
    def __init__(
        self,
        *,
        executor: PendingApplicationStepExecutor | None = None,
        lease_seconds: int = 60,
    ) -> None:
        self.executor = executor or MissingPendingApplicationStepExecutor()
        self.lease_seconds = lease_seconds
        self.crud = agent_pending_application_step_crud

    async def project(
        self,
        request: PendingApplicationStepProjectionRequest,
    ) -> PendingApplicationStepProjectionResult:
        failure_reason = _validate_request(request)
        step_id = str(coerce_json_dict(request.step).get("step_id") or "pending_application_step:invalid")
        if failure_reason is not None:
            return PendingApplicationStepProjectionResult(
                status="FAILED",
                step_id=step_id,
                retryable=False,
                failure_reason=failure_reason,
            )

        continuation = pending_task_continuation_from_json(
            request.step["checkpoint_ref"],
            expected_thread_id=request.root_thread_id,
        )
        assert continuation is not None
        record = self.crud.ensure(
            request.db,
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
            task_id=_request_task_id(request, continuation),
            step_id=step_id,
            step_type=request.step["step_type"],
            continuation_json=coerce_json_dict(continuation),
            request_json=coerce_json_dict(request.step),
        )
        identity_failure = _validate_record_identity(record, request)
        if identity_failure is not None:
            return PendingApplicationStepProjectionResult(
                status="FAILED",
                step_id=step_id,
                retryable=False,
                failure_reason=identity_failure,
            )
        if record.status == AgentPendingApplicationStepStatus.COMPLETED:
            return PendingApplicationStepProjectionResult(
                status="COMPLETED",
                step_id=step_id,
                result=coerce_json_dict(record.result_json),
                replayed=True,
            )

        lease_token = uuid4().hex
        claimed = self.crud.claim(
            request.db,
            team_id=request.team_id,
            user_id=request.user_id,
            step_id=step_id,
            lease_token=lease_token,
            lease_expires_at=business_now() + timedelta(seconds=self.lease_seconds),
        )
        if claimed is None:
            latest = self.crud.get_by_step_id(
                request.db,
                team_id=request.team_id,
                user_id=request.user_id,
                step_id=step_id,
            )
            if latest is not None and latest.status == AgentPendingApplicationStepStatus.COMPLETED:
                return PendingApplicationStepProjectionResult(
                    status="COMPLETED",
                    step_id=step_id,
                    result=coerce_json_dict(latest.result_json),
                    replayed=True,
                )
            return PendingApplicationStepProjectionResult(
                status="IN_PROGRESS",
                step_id=step_id,
                busy=True,
                retryable=True,
                failure_reason="application_step_lease_busy",
            )

        try:
            result = coerce_json_dict(await self.executor.execute(PendingApplicationStepExecutionRequest(
                db=request.db,
                session=request.session,
                task=request.task,
                team_id=request.team_id,
                user_id=request.user_id,
                session_id=request.session_id,
                authorization=request.authorization,
                step=request.step,
            )))
        except Exception as exc:
            rollback = getattr(request.db, "rollback", None)
            if callable(rollback):
                rollback()
            self.crud.fail_if_lease_owner(
                request.db,
                team_id=request.team_id,
                user_id=request.user_id,
                step_id=step_id,
                lease_token=lease_token,
                error_message=str(exc),
            )
            return PendingApplicationStepProjectionResult(
                status="FAILED",
                step_id=step_id,
                retryable=True,
                failure_reason=str(exc),
            )

        try:
            _project_application_effects(request, result)
            completed = self.crud.complete_if_lease_owner(
                request.db,
                team_id=request.team_id,
                user_id=request.user_id,
                step_id=step_id,
                lease_token=lease_token,
                result_json=result,
            )
        except Exception as exc:
            rollback = getattr(request.db, "rollback", None)
            if callable(rollback):
                rollback()
            self.crud.fail_if_lease_owner(
                request.db,
                team_id=request.team_id,
                user_id=request.user_id,
                step_id=step_id,
                lease_token=lease_token,
                error_message=str(exc),
            )
            return PendingApplicationStepProjectionResult(
                status="FAILED",
                step_id=step_id,
                retryable=True,
                failure_reason=str(exc),
            )
        if completed is None:
            rollback = getattr(request.db, "rollback", None)
            if callable(rollback):
                rollback()
            return PendingApplicationStepProjectionResult(
                status="IN_PROGRESS",
                step_id=step_id,
                busy=True,
                retryable=True,
                failure_reason="application_step_lease_lost",
            )
        return PendingApplicationStepProjectionResult(
            status="COMPLETED",
            step_id=step_id,
            result=result,
        )


def _project_application_effects(
    request: PendingApplicationStepProjectionRequest,
    result: JSONDict,
) -> None:
    intents = result.get("application_effect_intents")
    if not intents:
        return
    project_pending_task_effect_intents(
        intents,
        PendingTaskSideEffectContext(
            db=request.db,
            session=request.session,
            team_id=request.team_id,
            user_id=request.user_id,
            task=request.task,
            commit=False,
        ),
    )


def _validate_request(request: PendingApplicationStepProjectionRequest) -> str | None:
    if not is_pending_application_step_request(request.step):
        return "invalid_application_step_request"
    continuation = pending_task_continuation_from_json(
        request.step.get("checkpoint_ref"),
        expected_team_id=request.team_id,
        expected_user_id=request.user_id,
        expected_session_id=request.session_id,
        expected_thread_id=request.root_thread_id,
    )
    if continuation is None:
        return "invalid_continuation"
    continuation_task_id = continuation.get("task_id")
    task_snapshot = coerce_json_dict(request.step.get("task_snapshot"))
    snapshot_task_id = _optional_int(task_snapshot.get("id"))
    if (
        isinstance(continuation_task_id, int)
        and isinstance(snapshot_task_id, int)
        and continuation_task_id != snapshot_task_id
    ):
        return "task_continuation_mismatch"
    task_id = snapshot_task_id or continuation_task_id
    if task_id is not None:
        if request.task is None or getattr(request.task, "id", None) != task_id:
            return "task_identity_mismatch"
        if getattr(request.task, "team_id", None) != request.team_id:
            return "task_owner_mismatch"
        if getattr(request.task, "user_id", None) != request.user_id:
            return "task_owner_mismatch"
        if getattr(request.task, "session_id", None) != request.session_id:
            return "task_session_mismatch"
        for field, expected in (
            ("team_id", request.team_id),
            ("user_id", request.user_id),
            ("session_id", request.session_id),
        ):
            snapshot_value = _optional_int(task_snapshot.get(field))
            if snapshot_value is not None and snapshot_value != expected:
                return "task_snapshot_owner_mismatch"
    return None


def _request_task_id(
    request: PendingApplicationStepProjectionRequest,
    continuation: object,
) -> int | None:
    task_snapshot_id = _optional_int(coerce_json_dict(request.step.get("task_snapshot")).get("id"))
    continuation_task_id = _optional_int(coerce_json_dict(continuation).get("task_id"))
    return task_snapshot_id or continuation_task_id


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _validate_record_identity(record: object, request: PendingApplicationStepProjectionRequest) -> str | None:
    if getattr(record, "session_id", None) != request.session_id:
        return "application_step_session_mismatch"
    if getattr(record, "step_type", None) != request.step.get("step_type"):
        return "application_step_type_mismatch"
    if coerce_json_dict(getattr(record, "continuation_json", None)) != coerce_json_dict(
        request.step.get("checkpoint_ref")
    ):
        return "application_step_continuation_mismatch"
    if coerce_json_dict(getattr(record, "request_json", None)) != coerce_json_dict(request.step):
        return "application_step_request_mismatch"
    return None

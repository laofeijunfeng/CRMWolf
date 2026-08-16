"""Durable application projection for confirmed Agent write intents."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from app.crud.agent import agent_task_crud
from app.crud.agent_confirmed_application_step import (
    AgentConfirmedApplicationStepCRUD,
    agent_confirmed_application_step_crud,
)
from app.models.agent import AgentTaskStatus
from app.models.agent_confirmed_application_step import AgentConfirmedApplicationStepStatus
from app.services.agent.confirmed_application_step_contracts import (
    ConfirmedApplicationStepRequest,
    is_confirmed_application_step_request,
)
from app.services.agent.types import AgentRuntimeEventSink, JSONDict, coerce_json_dict


@dataclass(frozen=True)
class ConfirmedApplicationStepExecutionRequest:
    db: object
    session: object
    task: object
    team_id: int
    user_id: int
    session_id: int
    authorization: str
    channel: str
    provider: str | None
    step: ConfirmedApplicationStepRequest
    event_sink: AgentRuntimeEventSink | None = None


class ConfirmedApplicationStepExecutor(Protocol):
    async def execute(self, request: ConfirmedApplicationStepExecutionRequest) -> JSONDict: ...


@dataclass(frozen=True)
class ConfirmedApplicationStepProjectionRequest:
    db: object
    session: object
    task: object
    team_id: int
    user_id: int
    session_id: int
    authorization: str
    channel: str
    provider: str | None
    step: ConfirmedApplicationStepRequest
    event_sink: AgentRuntimeEventSink | None = None


@dataclass(frozen=True)
class ConfirmedApplicationStepProjectionResult:
    status: str
    step_id: str
    result: JSONDict = field(default_factory=dict)
    replayed: bool = False
    busy: bool = False
    retryable: bool = False
    failure_reason: str | None = None


class ConfirmedApplicationStepProjector:
    """Claims a stable confirmed-task intent and safely replays its durable result."""

    def __init__(
        self,
        *,
        executor: ConfirmedApplicationStepExecutor | None = None,
        crud: AgentConfirmedApplicationStepCRUD | None = None,
        lease_seconds: int = 120,
    ) -> None:
        if executor is None:
            from app.services.agent.confirmed_application_steps import confirmed_application_step_executor

            executor = confirmed_application_step_executor
        self.executor = executor
        self.crud = crud or agent_confirmed_application_step_crud
        self.lease_seconds = lease_seconds

    async def project(
        self,
        request: ConfirmedApplicationStepProjectionRequest,
    ) -> ConfirmedApplicationStepProjectionResult:
        step_id = str(request.step.get("step_id") or "")
        rejection = _validate_request(request)
        if rejection:
            return ConfirmedApplicationStepProjectionResult(
                status="REJECTED",
                step_id=step_id,
                retryable=False,
                failure_reason=rejection,
            )

        existing = self.crud.get_by_step_id(
            request.db,
            team_id=request.team_id,
            user_id=request.user_id,
            step_id=step_id,
        )
        if existing is not None:
            record_rejection = _validate_record_identity(existing, request)
            if record_rejection:
                return ConfirmedApplicationStepProjectionResult(
                    status="REJECTED",
                    step_id=step_id,
                    failure_reason=record_rejection,
                )
            if existing.status == AgentConfirmedApplicationStepStatus.COMPLETED:
                return ConfirmedApplicationStepProjectionResult(
                    status="COMPLETED",
                    step_id=step_id,
                    result=coerce_json_dict(existing.result_json),
                    replayed=True,
                )
        elif getattr(request.task, "status", None) != AgentTaskStatus.WAITING_USER:
            return ConfirmedApplicationStepProjectionResult(
                status="REJECTED",
                step_id=step_id,
                failure_reason="task_not_waiting_confirmation",
            )

        task_id = int(request.step["task_snapshot"]["id"])
        ensured = self.crud.ensure(
            request.db,
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
            task_id=task_id,
            step_id=step_id,
            step_type=request.step["step_type"],
            request_json=coerce_json_dict(request.step),
        )
        if getattr(ensured, "step_id", None) != step_id:
            return ConfirmedApplicationStepProjectionResult(
                status="REJECTED",
                step_id=step_id,
                failure_reason="application_step_task_already_claimed",
            )
        record_rejection = _validate_record_identity(ensured, request)
        if record_rejection:
            return ConfirmedApplicationStepProjectionResult(
                status="REJECTED",
                step_id=step_id,
                failure_reason=record_rejection,
            )
        lease_token = uuid.uuid4().hex
        claimed = self.crud.claim(
            request.db,
            team_id=request.team_id,
            user_id=request.user_id,
            step_id=step_id,
            lease_token=lease_token,
            lease_seconds=self.lease_seconds,
        )
        if claimed is None:
            completed = self.crud.get_by_step_id(
                request.db,
                team_id=request.team_id,
                user_id=request.user_id,
                step_id=step_id,
            )
            if completed is not None and completed.status == AgentConfirmedApplicationStepStatus.COMPLETED:
                return ConfirmedApplicationStepProjectionResult(
                    status="COMPLETED",
                    step_id=step_id,
                    result=coerce_json_dict(completed.result_json),
                    replayed=True,
                )
            return ConfirmedApplicationStepProjectionResult(
                status="IN_PROGRESS",
                step_id=step_id,
                busy=True,
                retryable=True,
                failure_reason="application_step_lease_busy",
            )

        task_claim_rejection = _claim_task_execution(request, attempt_count=int(claimed.attempt_count or 0))
        if task_claim_rejection:
            self.crud.fail_if_lease_owner(
                request.db,
                team_id=request.team_id,
                user_id=request.user_id,
                step_id=step_id,
                lease_token=lease_token,
                error_message=task_claim_rejection,
            )
            return ConfirmedApplicationStepProjectionResult(
                status="REJECTED",
                step_id=step_id,
                failure_reason=task_claim_rejection,
            )

        try:
            result = coerce_json_dict(await self.executor.execute(ConfirmedApplicationStepExecutionRequest(
                db=request.db,
                session=request.session,
                task=request.task,
                team_id=request.team_id,
                user_id=request.user_id,
                session_id=request.session_id,
                authorization=request.authorization,
                channel=request.channel,
                provider=request.provider,
                step=request.step,
                event_sink=request.event_sink,
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
            raise

        completed = self.crud.complete_if_lease_owner(
            request.db,
            team_id=request.team_id,
            user_id=request.user_id,
            step_id=step_id,
            lease_token=lease_token,
            result_json=result,
        )
        if completed is None:
            return ConfirmedApplicationStepProjectionResult(
                status="IN_PROGRESS",
                step_id=step_id,
                busy=True,
                retryable=True,
                failure_reason="application_step_lease_lost",
            )
        return ConfirmedApplicationStepProjectionResult(
            status="COMPLETED",
            step_id=step_id,
            result=result,
        )


def _claim_task_execution(
    request: ConfirmedApplicationStepProjectionRequest,
    *,
    attempt_count: int,
) -> str | None:
    task_id = _optional_int(request.step["task_snapshot"].get("id"))
    if task_id is None:
        return "task_identity_mismatch"
    task = agent_task_crud.get_by_id_for_update(
        request.db,
        task_id,
        team_id=request.team_id,
        user_id=request.user_id,
    )
    if task is None:
        return "task_identity_mismatch"
    if getattr(task, "session_id", None) != request.session_id:
        return "task_session_mismatch"
    if str(getattr(task, "task_key", "") or "") != str(request.step["task_snapshot"].get("task_key") or ""):
        return "task_key_mismatch"
    state = coerce_json_dict(getattr(task, "state_json", None))
    if request.step.get("action") != state.get("action"):
        return "task_action_mismatch"

    status = getattr(task, "status", None)
    if attempt_count <= 1 and status != AgentTaskStatus.WAITING_USER:
        return "task_not_waiting_confirmation"
    if attempt_count > 1 and status not in {
        AgentTaskStatus.WAITING_USER,
        AgentTaskStatus.RUNNING,
        AgentTaskStatus.COMPLETED,
        AgentTaskStatus.FAILED,
    }:
        return "task_recovery_status_not_allowed"
    if status in {AgentTaskStatus.WAITING_USER, AgentTaskStatus.FAILED}:
        task.status = AgentTaskStatus.RUNNING
        request.db.add(task)
        request.db.commit()
        request.db.refresh(task)
    return None


def _validate_request(request: ConfirmedApplicationStepProjectionRequest) -> str | None:
    if not is_confirmed_application_step_request(request.step):
        return "invalid_application_step_request"
    snapshot = coerce_json_dict(request.step.get("task_snapshot"))
    task = request.task
    if task is None or _optional_int(snapshot.get("id")) != _optional_int(getattr(task, "id", None)):
        return "task_identity_mismatch"
    if getattr(task, "team_id", None) != request.team_id or _optional_int(snapshot.get("team_id")) != request.team_id:
        return "task_owner_mismatch"
    if getattr(task, "user_id", None) != request.user_id or _optional_int(snapshot.get("user_id")) != request.user_id:
        return "task_owner_mismatch"
    if (
        getattr(task, "session_id", None) != request.session_id
        or _optional_int(snapshot.get("session_id")) != request.session_id
    ):
        return "task_session_mismatch"
    if str(getattr(task, "task_key", "") or "") != str(snapshot.get("task_key") or ""):
        return "task_key_mismatch"
    state = coerce_json_dict(getattr(task, "state_json", None))
    if request.step.get("action") != state.get("action"):
        return "task_action_mismatch"
    return None


def _validate_record_identity(record: object, request: ConfirmedApplicationStepProjectionRequest) -> str | None:
    if getattr(record, "session_id", None) != request.session_id:
        return "application_step_session_mismatch"
    if getattr(record, "task_id", None) != _optional_int(request.step["task_snapshot"].get("id")):
        return "application_step_task_mismatch"
    if getattr(record, "step_type", None) != request.step.get("step_type"):
        return "application_step_type_mismatch"
    if coerce_json_dict(getattr(record, "request_json", None)) != coerce_json_dict(request.step):
        return "application_step_request_mismatch"
    return None


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

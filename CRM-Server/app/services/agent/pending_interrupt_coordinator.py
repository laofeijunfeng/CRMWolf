"""Root-facing coordinator for durable PendingTask interrupt exposure.

The root graph owns routing, while this deep module owns the child interrupt
state machine: checkpoint recovery, transactional CRM projection, durable
visibility state, retry/failure semantics, and transport-neutral events.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from app.services.agent.pending_continuation import (
    PendingTaskContinuationRef,
    build_agent_root_thread_id,
    pending_task_continuation_from_json,
)
from app.services.agent.pending_interrupt_projection import (
    PendingInterruptProjectionRequest,
    PendingInterruptProjectionResult,
    PendingInterruptProjector,
    pending_interrupt_projection_key,
)
from app.services.agent.pending_outcome import (
    PENDING_TASK_CHECKPOINT_RECOVERY_FAILED_STATUS,
    PENDING_TASK_RECOVERY_FAILED_MESSAGE,
    PENDING_TASK_RECOVERY_RETRYABLE_MESSAGE,
    PendingTaskOutcomeRecovery,
    is_retryable_pending_task_recovery_failure,
)
from app.services.agent.types import JSONDict, coerce_json_dict

if TYPE_CHECKING:
    from app.services.agent.interrupts import AgentInterruptPayload
    from app.services.agent.state import AgentRuntimeContext, PendingTaskGraphResult

PendingInterruptCoordinationStatus = Literal[
    "PROJECTED",
    "IN_PROGRESS",
    "RETRYABLE_FAILURE",
    "TERMINAL_FAILURE",
]


@dataclass(frozen=True)
class PendingInterruptCoordinationRequest:
    interrupt: AgentInterruptPayload
    context: AgentRuntimeContext | None
    root_thread_id: str
    continuation: PendingTaskContinuationRef


@dataclass
class PendingInterruptCoordinationOutcome:
    status: PendingInterruptCoordinationStatus
    runtime_status: str
    retryable: bool
    assistant_content: str
    projection_state: JSONDict
    event: JSONDict
    pending_result: PendingTaskGraphResult | None = None
    task: object | None = None
    events: list[JSONDict] = field(default_factory=list)
    switch_notice: str | None = None
    current_interrupt: AgentInterruptPayload | None = None
    task_projection: JSONDict = field(default_factory=dict)
    terminal: bool = False

    @property
    def exposable(self) -> bool:
        return self.status == "PROJECTED" and self.current_interrupt is not None


PendingOutcomeLoader = Callable[..., Awaitable[PendingTaskOutcomeRecovery]]


class PendingInterruptCoordinator:
    """Coordinate one authenticated child interrupt into a root-visible state."""

    def __init__(
        self,
        *,
        outcome_loader: PendingOutcomeLoader,
        projector: PendingInterruptProjector,
    ) -> None:
        self.outcome_loader = outcome_loader
        self.projector = projector

    async def coordinate(
        self,
        request: PendingInterruptCoordinationRequest,
    ) -> PendingInterruptCoordinationOutcome:
        recovery = await self.outcome_loader(
            request.interrupt,
            context=request.context,
            continuation=request.continuation,
        )
        pending_result = recovery.outcome
        if pending_result is None:
            return _recovery_failure_outcome(
                request.interrupt,
                reason=recovery.failure_reason or "checkpoint_locator_not_found",
                continuation=request.continuation,
            )
        continuation = request.continuation

        context = request.context
        if context is None or context.db is None or context.session is None:
            return _projection_failure_outcome(
                projection=PendingInterruptProjectionResult(
                    status="FAILED",
                    projection_key=pending_interrupt_projection_key(continuation, request.interrupt),
                    failure_reason="missing_runtime_context",
                ),
                pending_result=pending_result,
                continuation=continuation,
                interrupt=request.interrupt,
            )

        projection = await self.projector.project(
            PendingInterruptProjectionRequest(
                db=context.db,
                session=context.session,
                team_id=context.team_id,
                user_id=context.user_id,
                session_id=context.session_id,
                continuation=continuation,
                interrupt=request.interrupt,
                outcome=pending_result,
                root_thread_id=request.root_thread_id,
                task=context.task,
                switch_notice=context.switch_notice,
                event_sink=context.event_sink,
            )
        )
        if projection.status != "PROJECTED":
            return _projection_failure_outcome(
                projection=projection,
                pending_result=pending_result,
                continuation=continuation,
                interrupt=request.interrupt,
            )

        task_projection = coerce_json_dict(pending_result.get("task_projection"))
        current_interrupt = projection.current_interrupt or request.interrupt
        return PendingInterruptCoordinationOutcome(
            status="PROJECTED",
            runtime_status="pending_projection_projected",
            retryable=False,
            assistant_content=projection.assistant_content or str(pending_result.get("assistant_content") or ""),
            projection_state=projection_state(
                projection,
                continuation=continuation,
                interrupt=request.interrupt,
            ),
            event={
                "event": "agent_root_pending_task_interrupt_projected",
                "projection_key": projection.projection_key,
                "replayed": projection.replayed,
                "delivery_status": projection.delivery_status,
            },
            pending_result=pending_result,
            task=projection.task,
            events=projection.events,
            switch_notice=projection.switch_notice,
            current_interrupt=current_interrupt,
            task_projection=task_projection,
        )


def projection_state(
    projection: object,
    *,
    continuation: PendingTaskContinuationRef | None = None,
    interrupt: AgentInterruptPayload | None = None,
) -> JSONDict:
    """Return the durable root-side projection state.

    Retryable states retain the exact authenticated child continuation and
    interrupt because LangGraph may checkpoint a root state update without
    preserving the child interrupt in the latest snapshot topology.
    """

    state = coerce_json_dict(
        {
            "status": getattr(projection, "status", None),
            "projection_key": getattr(projection, "projection_key", None),
            "replayed": bool(getattr(projection, "replayed", False)),
            "busy": bool(getattr(projection, "busy", False)),
            "retryable": bool(getattr(projection, "retryable", False)),
            "failure_reason": getattr(projection, "failure_reason", None),
            "delivery_status": getattr(projection, "delivery_status", None),
        }
    )
    if continuation is not None:
        state["continuation"] = coerce_json_dict(continuation)
    if interrupt is not None:
        state["interrupt"] = coerce_json_dict(interrupt)
    return state


def projection_matches_interrupt(values: JSONDict, interrupt: AgentInterruptPayload) -> bool:
    continuation = _continuation_from_interrupt(interrupt, values=values)
    if continuation is None:
        return False
    projection = coerce_json_dict(values.get("pending_interrupt_projection"))
    return projection.get("projection_key") == pending_interrupt_projection_key(continuation, interrupt)


def projection_is_exposable(values: JSONDict, interrupt: AgentInterruptPayload) -> bool:
    projection = coerce_json_dict(values.get("pending_interrupt_projection"))
    return projection.get("status") == "PROJECTED" and projection_matches_interrupt(values, interrupt)


def retryable_projection_interrupt(values: JSONDict) -> AgentInterruptPayload | None:
    """Recover an authenticated hidden interrupt from durable root state."""

    projection = coerce_json_dict(values.get("pending_interrupt_projection"))
    if projection.get("status") not in {"IN_PROGRESS", "FAILED"} or projection.get("retryable") is not True:
        return None

    from app.services.agent.interrupts import interrupt_payload_from_json
    from app.services.agent.pending_application_step_contracts import is_pending_application_step_request
    raw_interrupt = coerce_json_dict(projection.get("interrupt"))
    interrupt = (
        raw_interrupt
        if is_pending_application_step_request(raw_interrupt)
        else interrupt_payload_from_json(raw_interrupt)
    )
    if interrupt is None:
        return None
    continuation = pending_task_continuation_from_json(
        projection.get("continuation"),
        expected_team_id=values.get("team_id") if isinstance(values.get("team_id"), int) else None,
        expected_user_id=values.get("user_id") if isinstance(values.get("user_id"), int) else None,
        expected_session_id=values.get("session_id") if isinstance(values.get("session_id"), int) else None,
        expected_thread_id=_expected_root_thread_id(values),
    )
    interrupt_continuation = _continuation_from_interrupt(interrupt, values=values)
    if continuation is None or interrupt_continuation != continuation:
        return None
    if projection.get("projection_key") != pending_interrupt_projection_key(continuation, interrupt):
        return None
    return interrupt


def projection_is_terminal_failure(values: JSONDict, interrupt: AgentInterruptPayload) -> bool:
    return (
        values.get("runtime_status") in {"pending_projection_failed", "checkpoint_recovery_failed"}
        and values.get("runtime_retryable") is False
        and projection_matches_interrupt(values, interrupt)
    )


def _recovery_failure_outcome(
    interrupt: AgentInterruptPayload,
    *,
    reason: str,
    continuation: PendingTaskContinuationRef | None = None,
) -> PendingInterruptCoordinationOutcome:
    continuation = continuation or _continuation_from_interrupt(interrupt)
    retryable = is_retryable_pending_task_recovery_failure(reason)
    projection_key = (
        pending_interrupt_projection_key(continuation, interrupt)
        if continuation is not None
        else "pending_interrupt_projection:invalid_continuation"
    )
    projection = coerce_json_dict(
        {
            "status": "FAILED",
            "projection_key": projection_key,
            "replayed": False,
            "busy": False,
            "retryable": retryable,
            "failure_reason": reason,
            "delivery_status": None,
        }
    )
    return PendingInterruptCoordinationOutcome(
        status="RETRYABLE_FAILURE" if retryable else "TERMINAL_FAILURE",
        runtime_status=PENDING_TASK_CHECKPOINT_RECOVERY_FAILED_STATUS,
        retryable=retryable,
        assistant_content=(
            PENDING_TASK_RECOVERY_RETRYABLE_MESSAGE
            if retryable
            else PENDING_TASK_RECOVERY_FAILED_MESSAGE
        ),
        projection_state=projection,
        event={
            "event": "pending_task_checkpoint_recovery_failed",
            "reason": reason,
            "source_event": interrupt.get("source_event"),
            "projection_key": projection_key,
            "retryable": retryable,
        },
        terminal=not retryable,
    )


def _projection_failure_outcome(
    *,
    projection: PendingInterruptProjectionResult,
    pending_result: PendingTaskGraphResult,
    continuation: PendingTaskContinuationRef,
    interrupt: AgentInterruptPayload,
) -> PendingInterruptCoordinationOutcome:
    in_progress = projection.status == "IN_PROGRESS" or projection.busy
    retryable = bool(projection.retryable or in_progress)
    status: PendingInterruptCoordinationStatus
    if in_progress:
        status = "IN_PROGRESS"
        runtime_status = "pending_projection_in_progress"
        assistant_content = "当前待确认流程正在完成状态同步，请稍后刷新或重试。"  # noqa: RUF001
        event_name = "pending_task_interrupt_projection_in_progress"
    elif retryable:
        status = "RETRYABLE_FAILURE"
        runtime_status = "pending_projection_failed"
        assistant_content = "当前待确认流程投影失败，请稍后重试。"  # noqa: RUF001
        event_name = "pending_task_interrupt_projection_failed"
    else:
        status = "TERMINAL_FAILURE"
        runtime_status = "pending_projection_failed"
        assistant_content = "当前待确认流程投影失败，本次流程已终止；你可以重新发起。"  # noqa: RUF001
        event_name = "pending_task_interrupt_projection_failed"
    return PendingInterruptCoordinationOutcome(
        status=status,
        runtime_status=runtime_status,
        retryable=retryable,
        assistant_content=assistant_content,
        projection_state=projection_state(
            projection,
            continuation=continuation,
            interrupt=interrupt,
        ),
        event={
            "event": event_name,
            "reason": projection.failure_reason,
            "projection_key": projection.projection_key,
            "retryable": retryable,
        },
        pending_result=pending_result,
        task_projection=coerce_json_dict(pending_result.get("task_projection")),
        terminal=status == "TERMINAL_FAILURE",
    )


def _continuation_from_interrupt(
    interrupt: AgentInterruptPayload,
    *,
    values: JSONDict | None = None,
) -> PendingTaskContinuationRef | None:
    scoped = values or {}
    return pending_task_continuation_from_json(
        interrupt.get("checkpoint_ref"),
        expected_team_id=scoped.get("team_id") if isinstance(scoped.get("team_id"), int) else None,
        expected_user_id=scoped.get("user_id") if isinstance(scoped.get("user_id"), int) else None,
        expected_session_id=scoped.get("session_id") if isinstance(scoped.get("session_id"), int) else None,
        expected_thread_id=_expected_root_thread_id(scoped),
    )


def _expected_root_thread_id(values: JSONDict) -> str | None:
    team_id = values.get("team_id")
    user_id = values.get("user_id")
    session_id = values.get("session_id")
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in (team_id, user_id, session_id)):
        return None
    session_key = values.get("session_key")
    return build_agent_root_thread_id(
        team_id=team_id,
        user_id=user_id,
        session_id=session_id,
        session_key=session_key if isinstance(session_key, str) else None,
    )

"""Side effects emitted by the pending-task LangGraph subgraph."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.crud.agent import agent_task_crud
from app.services.agent import interactions, session_state
from app.services.agent.interrupts import AgentInterruptPayload, interrupt_from_waiting_events
from app.services.agent.state import PendingTaskGraphResult, PendingTaskGraphSideEffects
from app.services.agent.types import JSONDict, coerce_json_dict


@dataclass
class PendingTaskSideEffectContext:
    """Run-scoped CRM dependencies for pending-task persistence effects."""

    db: object
    session: object
    team_id: int = 0
    user_id: int = 0
    task: object | None = None
    switch_notice: str | None = None
    graph_side_effects: PendingTaskGraphSideEffects | None = None


@dataclass
class PendingTaskSideEffectResult:
    """Application-facing outputs from pending-task effects."""

    task: object | None = None
    events: list[JSONDict] = field(default_factory=list)
    assistant_content: str | None = None
    switch_notice: str | None = None
    current_interrupt: AgentInterruptPayload | None = None


class PendingTaskSideEffectHandler:
    """Applies CRM persistence effects for pending-task graph results."""

    def apply(
        self,
        graph_state: PendingTaskGraphResult,
        context: PendingTaskSideEffectContext,
    ) -> PendingTaskSideEffectResult:
        if not _has_pending_task_result(graph_state):
            return PendingTaskSideEffectResult(task=context.task)

        suspended_task = _suspended_task_from_result(graph_state, context)
        if suspended_task:
            session_state._suspend_pending_task(
                context.db,
                context.session,
                suspended_task,
                graph_state.get("suspend_reason") or "用户开启了新的业务流程",
                suspension_kind=_suspension_kind(graph_state),
            )

        task = _task_from_result(graph_state, context)
        context.task = task

        selected_customer = graph_state.get("selected_customer")
        if selected_customer:
            session_state._remember_current_customer(context.db, context.session, selected_customer)

        switch_notice = graph_state.get("switch_notice")
        context.switch_notice = switch_notice if isinstance(switch_notice, str) else None
        assistant_content = graph_state.get("assistant_content")
        events = [
            coerce_json_dict(interactions._with_interaction(event, db=context.db, team_id=context.team_id))
            for event in graph_state.get("events", [])
            if isinstance(event, dict)
        ]
        graph_interrupt = graph_state.get("current_interrupt")
        current_interrupt = graph_interrupt or interrupt_from_waiting_events(
            events,
            interaction=_last_waiting_interaction(events),
        )
        return PendingTaskSideEffectResult(
            task=task,
            events=events,
            assistant_content=assistant_content if isinstance(assistant_content, str) else None,
            switch_notice=context.switch_notice,
            current_interrupt=current_interrupt,
        )


def _has_pending_task_result(graph_state: PendingTaskGraphResult) -> bool:
    return bool(graph_state.get("has_active_task") or graph_state.get("handled") or graph_state.get("events"))


def _suspension_kind(graph_state: PendingTaskGraphResult) -> str | None:
    value = graph_state.get("suspension_kind")
    return value if value in {"paused", "dismissed"} else None


def _task_from_result(
    graph_state: PendingTaskGraphResult,
    context: PendingTaskSideEffectContext,
) -> object | None:
    clear_pending_task_id = graph_state.get("clear_pending_task_id")
    if isinstance(clear_pending_task_id, int):
        if context.graph_side_effects and _object_id(context.graph_side_effects.task) == clear_pending_task_id:
            return None
        if _object_id(context.task) == clear_pending_task_id:
            return None
    if context.graph_side_effects and context.graph_side_effects.task:
        return context.graph_side_effects.task
    if context.task:
        return context.task
    task_id = _task_projection_id(graph_state)
    if task_id is None:
        return None
    return agent_task_crud.get_by_id(
        context.db,
        task_id,
        team_id=context.team_id,
        user_id=_context_user_id(context),
    )


def _suspended_task_from_result(
    graph_state: PendingTaskGraphResult,
    context: PendingTaskSideEffectContext,
) -> object | None:
    if context.graph_side_effects and context.graph_side_effects.suspended_task:
        return context.graph_side_effects.suspended_task
    suspended_task_id = graph_state.get("suspended_task_id")
    if not isinstance(suspended_task_id, int):
        return None
    if context.task and getattr(context.task, "id", None) == suspended_task_id:
        return context.task
    return agent_task_crud.get_by_id(
        context.db,
        suspended_task_id,
        team_id=context.team_id,
        user_id=_context_user_id(context),
    )


def _context_user_id(context: PendingTaskSideEffectContext) -> int | None:
    value = getattr(context, "user_id", None)
    if isinstance(value, int):
        return value
    return None


def _object_id(value: object | None) -> int | None:
    raw_id = getattr(value, "id", None)
    if isinstance(raw_id, int):
        return raw_id
    if isinstance(raw_id, str):
        try:
            return int(raw_id)
        except ValueError:
            return None
    return None


def _task_projection_id(graph_state: PendingTaskGraphResult) -> int | None:
    task_projection = graph_state.get("task_projection")
    if not isinstance(task_projection, dict):
        return None
    raw_id = task_projection.get("id")
    if isinstance(raw_id, int):
        return raw_id
    if isinstance(raw_id, str):
        try:
            return int(raw_id)
        except ValueError:
            return None
    return None


def _last_waiting_interaction(events: list[JSONDict]) -> JSONDict | None:
    for event in reversed(events):
        interaction = event.get("interaction")
        if isinstance(interaction, dict):
            return coerce_json_dict(interaction)
    return None


pending_task_side_effect_handler = PendingTaskSideEffectHandler()

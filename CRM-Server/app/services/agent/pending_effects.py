"""Side effects emitted by the pending-task LangGraph subgraph."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.crud.agent import agent_task_crud
from app.models.agent import AgentTaskStatus
from app.schemas.agent import AgentTaskUpdate
from app.services.agent import interactions, session_state
from app.services.agent.interrupts import AgentInterruptPayload, interrupt_from_waiting_events
from app.services.agent.state import PendingTaskGraphResult, PendingTaskGraphSideEffects
from app.services.agent.task_projection import (
    task_matches_projection,
    task_projection_conflicts,
    validate_task_projection_contract,
)
from app.services.agent.types import JSONDict, coerce_json_dict
from app.services.agent.workflow_action_cancellation_projection import (
    WorkflowActionCancellationProjectionContext,
    project_workflow_action_cancellation,
)


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
    commit: bool = True


@dataclass
class PendingTaskSideEffectResult:
    """Application-facing outputs from pending-task effects."""

    task: object | None = None
    suspended_task: object | None = None
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

        _apply_effect_intents(graph_state, context)

        suspended_task = _suspended_task_from_result(graph_state, context)
        if suspended_task:
            session_state._suspend_pending_task(
                context.db,
                context.session,
                suspended_task,
                graph_state.get("suspend_reason") or "用户开启了新的业务流程",
                suspension_kind=_suspension_kind(graph_state),
                commit=context.commit,
            )

        task = _task_from_result(graph_state, context)
        context.task = task

        selected_customer = graph_state.get("selected_customer")
        if selected_customer:
            session_state._remember_current_customer(
                context.db,
                context.session,
                selected_customer,
                commit=context.commit,
            )

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
            suspended_task=suspended_task,
            events=events,
            assistant_content=assistant_content if isinstance(assistant_content, str) else None,
            switch_notice=context.switch_notice,
            current_interrupt=current_interrupt,
        )


def _apply_effect_intents(
    graph_state: PendingTaskGraphResult,
    context: PendingTaskSideEffectContext,
) -> None:
    project_pending_task_effect_intents(
        graph_state.get("effect_intents"),
        context,
        allow_workflow_cancellation=True,
    )


def project_pending_task_effect_intents(
    intents: object,
    context: PendingTaskSideEffectContext,
    *,
    allow_workflow_cancellation: bool = False,
) -> None:
    """Project authenticated task effects at an application boundary.

    The hidden ``task_transition`` application step uses this seam to make a
    graph-planned task ownership/state transition durable before a following
    DB/LLM interaction executes.  Terminal outcome projection may additionally
    opt into workflow-action cancellation effects.
    """

    if not isinstance(intents, list):
        return
    for raw_intent in intents:
        intent = coerce_json_dict(raw_intent)
        intent_type = intent.get("intent_type")
        if intent_type == "project_pending_task_state":
            _project_pending_task_state(intent, context)
        elif intent_type == "resume_suspended_task":
            _project_resume_suspended_task(intent, context)
        elif intent_type == "cancel_workflow_action" and allow_workflow_cancellation:
            _project_cancel_workflow_action(intent, context)
        else:
            raise ValueError(f"unsupported pending task transition intent: {intent_type}")


def _project_pending_task_state(intent: JSONDict, context: PendingTaskSideEffectContext) -> None:
    """Project one optimistic graph mutation contract into durable CRM state."""

    task = _load_intent_task(intent, context)
    expected, desired, update = validate_task_projection_contract(
        intent.get("expected_task"),
        intent.get("task_update"),
    )
    resumed = (
        expected.get("status") == AgentTaskStatus.SUSPENDED
        and desired.get("status") == AgentTaskStatus.WAITING_USER
    )

    if task_matches_projection(task, desired):
        _set_projected_task(task, context, resumed=resumed)
        return

    conflicts = task_projection_conflicts(task, expected, desired)
    if conflicts:
        raise ValueError(
            "pending task projection conflict: " + ", ".join(sorted(conflicts))
        )

    projected = agent_task_crud.update(
        context.db,
        task,
        update,
        commit=context.commit,
    )
    _set_projected_task(projected, context, resumed=resumed)


def _project_resume_suspended_task(intent: JSONDict, context: PendingTaskSideEffectContext) -> None:
    task = _load_intent_task(intent, context)
    if task.status == AgentTaskStatus.WAITING_USER:
        _set_projected_task(task, context, resumed=True)
        return
    if task.status != AgentTaskStatus.SUSPENDED:
        raise ValueError("pending task resume intent requires a suspended task")
    state = coerce_json_dict(getattr(task, "state_json", None))
    state.pop("suspended_reason", None)
    projected = agent_task_crud.update(
        context.db,
        task,
        AgentTaskUpdate(status=AgentTaskStatus.WAITING_USER, state_json=state),
        commit=context.commit,
    )
    _set_projected_task(projected, context, resumed=True)


def _project_cancel_workflow_action(intent: JSONDict, context: PendingTaskSideEffectContext) -> None:
    projection = project_workflow_action_cancellation(
        intent,
        WorkflowActionCancellationProjectionContext(
            db=context.db,
            session=context.session,
            team_id=context.team_id,
            user_id=_context_user_id(context),
            commit=context.commit,
        ),
    )
    _set_projected_task(projection.task, context, resumed=False)


def _load_intent_task(intent: JSONDict, context: PendingTaskSideEffectContext) -> object:
    task_id = intent.get("task_id")
    if not isinstance(task_id, int):
        raise ValueError("pending effect intent requires task_id")
    task = agent_task_crud.get_by_id_for_update(
        context.db,
        task_id,
        team_id=context.team_id,
        user_id=_context_user_id(context),
    )
    if task is None:
        raise ValueError("pending effect intent task not found")
    session_id = getattr(context.session, "id", None)
    if not isinstance(session_id, int) or getattr(task, "session_id", None) != session_id:
        raise ValueError("pending effect intent task session mismatch")
    return task


def _set_projected_task(
    task: object,
    context: PendingTaskSideEffectContext,
    *,
    resumed: bool,
) -> None:
    context.task = task
    if context.graph_side_effects is not None:
        context.graph_side_effects.task = task
        if resumed:
            context.graph_side_effects.resumed_task = task


def _has_pending_task_result(graph_state: PendingTaskGraphResult) -> bool:
    return bool(
        graph_state.get("has_active_task")
        or graph_state.get("handled")
        or graph_state.get("events")
        or graph_state.get("effect_intents")
        or graph_state.get("projection_aborted")
    )


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

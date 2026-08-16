"""LangGraph orchestration for durable confirmed Agent write intents."""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.services.agent import task_execution
from app.services.agent.checkpointer import agent_checkpoint_saver
from app.services.agent.confirmed_application_step_contracts import build_confirmed_application_step_request
from app.services.agent.confirmed_application_step_projection import (
    ConfirmedApplicationStepProjectionRequest,
    ConfirmedApplicationStepProjector,
)
from app.services.agent.confirmed_application_steps import DefaultConfirmedApplicationStepExecutor
from app.services.agent.confirmed_task_effects import (
    ConfirmedTaskSideEffectHandler,
    confirmed_task_side_effect_handler,
)
from app.services.agent.state import (
    ConfirmedTaskExecutionResult,
    ConfirmedTaskGraphInput,
    ConfirmedTaskGraphResult,
    ConfirmedTaskGraphSideEffects,
    ConfirmedTaskGraphState,
    ConfirmedTaskRuntimeContext,
    internal_graph_start_event,
    visible_graph_events,
)
from app.services.agent.task_projection import agent_task_snapshot
from app.services.agent.types import AgentRuntimeEventSink, JSONDict, coerce_json_dict, coerce_json_value

CONFIRMED_TASK_CHECKPOINT_NS = "crm_agent_confirmed_task"


class ConfirmedTaskGraphService:
    """Checkpoints execution intent and hydrates results from the application projector."""

    def __init__(
        self,
        *,
        side_effect_handler: ConfirmedTaskSideEffectHandler | None = None,
        application_projector: ConfirmedApplicationStepProjector | None = None,
        checkpointer: object | None = None,
    ) -> None:
        self.side_effect_handler = side_effect_handler or confirmed_task_side_effect_handler
        self.application_projector = application_projector or ConfirmedApplicationStepProjector(
            executor=DefaultConfirmedApplicationStepExecutor(side_effect_handler=self.side_effect_handler)
        )
        self._graph = self._build_graph(checkpointer)

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(ConfirmedTaskGraphState, context_schema=ConfirmedTaskRuntimeContext)
        graph.add_node("prepare_execution", self._prepare_execution)
        graph.add_node("execute_confirmed_task", self._execute_confirmed_task)
        graph.add_node("apply_execution_effects", self._apply_execution_effects)
        graph.add_node("finish_execution", self._finish_execution)
        graph.add_edge(START, "prepare_execution")
        graph.add_edge("prepare_execution", "execute_confirmed_task")
        graph.add_edge("execute_confirmed_task", "apply_execution_effects")
        graph.add_edge("apply_execution_effects", "finish_execution")
        graph.add_edge("finish_execution", END)
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    async def run(self, input_state: ConfirmedTaskGraphInput) -> ConfirmedTaskGraphResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        side_effects = ConfirmedTaskGraphSideEffects()
        context = _runtime_context_from_input(input_state, side_effects)
        config = build_confirmed_task_graph_config(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            task_id=_optional_object_id(context.task),
        )
        # Confirmed tasks are write-capable. Checkpoint failures must bubble to
        # the root runtime, whose single fail-closed policy preserves the last
        # durable interrupt and blocks unowned execution.
        result = await self._graph.ainvoke(checkpoint_state, config, context=context)
        return _with_visible_events(_merge_side_effects(result, side_effects))

    def _prepare_execution(
        self,
        state: ConfirmedTaskGraphState,
        runtime: Runtime[ConfirmedTaskRuntimeContext],
    ) -> ConfirmedTaskGraphState:
        task_projection = state.get("task_projection") or agent_task_snapshot(runtime.context.task)
        action = _task_action(runtime.context.task)
        tool_request: JSONDict = {"task": task_projection, "action": action}
        application_step = build_confirmed_application_step_request(
            task_snapshot=task_projection,
            action=action or "",
        )
        return {
            "task_projection": task_projection,
            "tool_request": tool_request,
            "application_step": application_step,
            "events": [{
                "event": "confirmed_task_graph_started",
                "task_id": task_projection.get("id"),
                "action": action,
                "application_step_id": application_step["step_id"],
            }],
        }

    async def _execute_confirmed_task(
        self,
        state: ConfirmedTaskGraphState,
        runtime: Runtime[ConfirmedTaskRuntimeContext],
    ) -> ConfirmedTaskGraphState:
        context = runtime.context
        if not context.db or not context.session or not context.task:
            return {
                "execution_status": "unavailable",
                "events": [{
                    "event": "confirmed_task_execution_unavailable",
                    "reason": "missing_runtime_context",
                }],
            }

        application_step = coerce_json_dict(state.get("application_step"))
        projection = await self.application_projector.project(ConfirmedApplicationStepProjectionRequest(
            db=context.db,
            session=context.session,
            task=context.task,
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            authorization=context.authorization or "",
            channel=context.channel,
            provider=context.provider,
            step=application_step,  # type: ignore[arg-type]
            event_sink=context.event_sink,
        ))
        if projection.status != "COMPLETED":
            return {
                "execution_status": projection.status.lower(),
                "events": [{
                    "event": "confirmed_task_application_projection_deferred",
                    "step_id": projection.step_id,
                    "status": projection.status,
                    "retryable": projection.retryable,
                    "reason": projection.failure_reason,
                }],
            }

        application_result = coerce_json_dict(projection.result)
        tool_result = coerce_json_dict(application_result.get("tool_result"))
        task_event = coerce_json_dict(application_result.get("task_event"))
        assistant_content = application_result.get("assistant_content")
        return {
            "application_step_result": application_result,
            "tool_result": tool_result,
            "task_event": task_event,
            "assistant_content": assistant_content if isinstance(assistant_content, str) else None,
            "execution_status": str(application_result.get("execution_status") or "failed"),
            "events": [
                *_events(application_result.get("progress_events")),
                {
                    "event": "confirmed_task_execution_completed",
                    "task_event": task_event.get("event"),
                    "application_step_id": projection.step_id,
                    "application_step_replayed": projection.replayed,
                },
            ],
        }

    def _apply_execution_effects(
        self,
        state: ConfirmedTaskGraphState,
        runtime: Runtime[ConfirmedTaskRuntimeContext],
    ) -> ConfirmedTaskGraphState:
        application_result = coerce_json_dict(state.get("application_step_result"))
        if not application_result:
            return {
                "events": [{
                    "event": "confirmed_task_effects_skipped",
                    "reason": "missing_application_step_result",
                }],
            }

        task_event = coerce_json_dict(application_result.get("task_event"))
        assistant_content = application_result.get("assistant_content")
        output_events = _events(application_result.get("output_events"))
        executed_task_snapshot = coerce_json_dict(application_result.get("executed_task_snapshot"))
        active_task_snapshot = coerce_json_dict(application_result.get("active_task_snapshot"))
        side_effects = runtime.context.side_effects
        side_effects.tool_event = coerce_json_dict(application_result.get("tool_result")) or None
        side_effects.task_event = task_event
        side_effects.assistant_content = assistant_content if isinstance(assistant_content, str) else None
        side_effects.output_events = output_events
        side_effects.executed_task_snapshot = executed_task_snapshot
        side_effects.active_task_snapshot = active_task_snapshot
        return {
            "task_event": task_event,
            "assistant_content": side_effects.assistant_content,
            "executed_task_snapshot": executed_task_snapshot,
            "active_task_snapshot": active_task_snapshot,
            "events": [{
                "event": "confirmed_task_effects_applied",
                "emitted_event_count": len(output_events),
            }],
        }

    def _finish_execution(self, state: ConfirmedTaskGraphState) -> ConfirmedTaskGraphState:
        return {
            "events": [{
                "event": "confirmed_task_graph_finished",
                "execution_status": state.get("execution_status"),
            }],
        }


def build_confirmed_task_thread_id(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    task_id: int | None = None,
) -> str:
    task_key = str(task_id) if task_id is not None else "task"
    return f"crm_agent_confirmed:{team_id}:{user_id}:{session_id}:{task_key}"


def build_confirmed_task_graph_config(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    task_id: int | None = None,
) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": build_confirmed_task_thread_id(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                task_id=task_id,
            ),
        },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "task_id": task_id,
            "runtime": "crm_agent_confirmed_task",
            "runtime_namespace": CONFIRMED_TASK_CHECKPOINT_NS,
        },
    }


async def execute_confirmed_task(
    db: object,
    task: object,
    *,
    session: object,
    team_id: int,
    user_id: int,
    authorization: str,
    event_sink: AgentRuntimeEventSink | None = None,
) -> ConfirmedTaskExecutionResult:
    """Compatibility seam for direct callers outside runtime orchestration."""
    execution = await task_execution._execute_waiting_task(
        db,
        task,
        session=session,
        team_id=team_id,
        user_id=user_id,
        authorization=authorization,
        event_sink=event_sink,
    )
    result = execution.tool_result
    assistant_content = execution.assistant_content
    task_event: JSONDict = {
        "event": "task_completed" if result and result.success else "task_failed",
        "task_id": coerce_json_value(getattr(task, "id", None)),
        "content": assistant_content,
    }
    return ConfirmedTaskExecutionResult(
        tool_event=coerce_json_dict(result.to_event()) if result else None,
        task_event=coerce_json_dict(task_event),
        assistant_content=assistant_content,
        next_task=execution.next_task,
        progress_events=execution.progress_events,
    )


def _checkpoint_state_from_input(input_state: ConfirmedTaskGraphInput) -> ConfirmedTaskGraphState:
    task = input_state.get("task")
    state: ConfirmedTaskGraphState = {
        "team_id": int(input_state.get("team_id") or 0),
        "user_id": int(input_state.get("user_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "task_projection": agent_task_snapshot(task),
        "events": [internal_graph_start_event("confirmed_task_graph_invocation_started")],
    }
    state["events"].extend(_events(input_state.get("events") or []))
    return state


def _runtime_context_from_input(
    input_state: ConfirmedTaskGraphInput,
    side_effects: ConfirmedTaskGraphSideEffects,
) -> ConfirmedTaskRuntimeContext:
    return ConfirmedTaskRuntimeContext(
        db=input_state.get("db"),
        session=input_state.get("session"),
        task=input_state.get("task"),
        team_id=int(input_state.get("team_id") or 0),
        user_id=int(input_state.get("user_id") or 0),
        session_id=int(input_state.get("session_id") or 0),
        authorization=input_state.get("authorization"),
        channel=str(input_state.get("channel") or "web"),
        provider=input_state.get("provider"),
        side_effects=side_effects,
        event_sink=input_state.get("event_sink"),
    )


def _merge_side_effects(
    state: ConfirmedTaskGraphState,
    side_effects: ConfirmedTaskGraphSideEffects,
) -> ConfirmedTaskGraphResult:
    result: ConfirmedTaskGraphResult = dict(state)
    result["output_events"] = list(side_effects.output_events)
    return result


def _with_visible_events(result: ConfirmedTaskGraphResult) -> ConfirmedTaskGraphResult:
    projected: ConfirmedTaskGraphResult = dict(result)
    projected["events"] = visible_graph_events(projected.get("events"))
    return projected


def _task_action(task: object) -> str | None:
    state = coerce_json_dict(getattr(task, "state_json", None))
    action = state.get("action")
    return action if isinstance(action, str) else None


def _optional_object_id(value: object) -> int | None:
    raw_id = getattr(value, "id", None)
    if raw_id is None:
        return None
    try:
        return int(raw_id)
    except (TypeError, ValueError):
        return None


def _events(events: object) -> list[JSONDict]:
    if not isinstance(events, list):
        return []
    return [coerce_json_dict(event) for event in events if isinstance(event, dict)]


confirmed_task_graph_service = ConfirmedTaskGraphService(checkpointer=agent_checkpoint_saver)

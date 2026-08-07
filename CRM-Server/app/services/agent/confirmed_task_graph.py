"""LangGraph subgraph for confirmed Agent write execution."""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy.exc import SQLAlchemyError

from app.services.agent import task_execution
from app.services.agent.checkpointer import (
    agent_checkpoint_saver,
    checkpoint_unavailable_fallback_event,
    is_checkpoint_storage_error,
    with_checkpoint_unavailable_fallback_event,
)
from app.services.agent.confirmed_task_effects import (
    ConfirmedTaskSideEffectContext,
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
from app.services.agent.types import AgentRuntimeEventSink, JSONDict, coerce_json_dict, coerce_json_value


CONFIRMED_TASK_CHECKPOINT_NS = "crm_agent_confirmed_task"


class ConfirmedTaskGraphService:
    """Executes user-approved write tasks as a checkpointed subgraph."""

    def __init__(
        self,
        *,
        side_effect_handler: ConfirmedTaskSideEffectHandler | None = None,
        checkpointer: object | None = None,
    ) -> None:
        self.side_effect_handler = side_effect_handler or confirmed_task_side_effect_handler
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

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
        try:
            result = await self._graph.ainvoke(checkpoint_state, config, context=context)
            return _with_visible_events(_merge_side_effects(result, side_effects))
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            fallback_side_effects = ConfirmedTaskGraphSideEffects()
            fallback_context = _runtime_context_from_input(input_state, fallback_side_effects)
            result = await self._fallback_graph.ainvoke(checkpoint_state, config, context=fallback_context)
            merged = _with_visible_events(_merge_side_effects(result, fallback_side_effects))
            fallback_event = checkpoint_unavailable_fallback_event(
                runtime="crm_agent_confirmed_task",
                graph=CONFIRMED_TASK_CHECKPOINT_NS,
            )
            merged = with_checkpoint_unavailable_fallback_event(
                merged,
                runtime="crm_agent_confirmed_task",
                graph=CONFIRMED_TASK_CHECKPOINT_NS,
            )
            merged["output_events"] = [fallback_event, *_events(merged.get("output_events"))]
            return merged

    def _prepare_execution(
        self,
        state: ConfirmedTaskGraphState,
        runtime: Runtime[ConfirmedTaskRuntimeContext],
    ) -> ConfirmedTaskGraphState:
        task_projection = state.get("task_projection") or _task_projection(runtime.context.task)
        tool_request: JSONDict = {
            "task": task_projection,
            "action": _task_action(runtime.context.task),
        }
        return {
            "task_projection": task_projection,
            "tool_request": tool_request,
            "events": [{
                "event": "confirmed_task_graph_started",
                "task_id": task_projection.get("id"),
                "action": tool_request.get("action"),
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

        execution = await execute_confirmed_task(
            context.db,
            context.task,
            session=context.session,
            team_id=context.team_id,
            user_id=context.user_id,
            authorization=context.authorization or "",
            event_sink=context.event_sink,
        )
        tool_result: JSONDict = {}
        if execution.tool_event:
            tool_result = coerce_json_dict(execution.tool_event)
            context.side_effects.tool_event = tool_result
        context.side_effects.execution = execution
        context.side_effects.task_event = coerce_json_dict(execution.task_event)
        context.side_effects.assistant_content = execution.assistant_content
        return {
            "tool_result": tool_result,
            "task_event": coerce_json_dict(execution.task_event),
            "assistant_content": execution.assistant_content,
            "execution_status": "completed" if execution.task_event.get("event") == "task_completed" else "failed",
            "events": [
                *execution.progress_events,
                {
                    "event": "confirmed_task_execution_completed",
                    "task_event": execution.task_event.get("event"),
                },
            ],
        }

    def _apply_execution_effects(
        self,
        state: ConfirmedTaskGraphState,
        runtime: Runtime[ConfirmedTaskRuntimeContext],
    ) -> ConfirmedTaskGraphState:
        context = runtime.context
        execution = context.side_effects.execution
        if not context.db or not context.session or not context.task or not execution:
            return {
                "events": [{
                    "event": "confirmed_task_effects_skipped",
                    "reason": "missing_runtime_context",
                }],
            }
        effect_result = self.side_effect_handler.apply(
            ConfirmedTaskSideEffectContext(
                db=context.db,
                session=context.session,
                task=context.task,
                team_id=context.team_id,
                user_id=context.user_id,
                execution=execution,
                channel=context.channel,
                provider=context.provider,
            )
        )
        context.side_effects.task_event = effect_result.task_event
        context.side_effects.assistant_content = effect_result.assistant_content
        context.side_effects.output_events = effect_result.output_events
        return {
            "task_event": effect_result.task_event,
            "assistant_content": effect_result.assistant_content,
            "events": [{
                "event": "confirmed_task_effects_applied",
                "emitted_event_count": len(effect_result.output_events),
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
        "task_projection": _task_projection(task),
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


def _task_projection(task: object) -> JSONDict:
    if not task:
        return {}
    projection: JSONDict = {}
    for key in ("id", "task_key", "status", "intent", "target_type", "target_id"):
        value = getattr(task, key, None)
        if value is not None:
            projection[key] = coerce_json_value(value)
    return projection


def _task_action(task: object) -> str | None:
    state_json = getattr(task, "state_json", None)
    state = coerce_json_dict(state_json)
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

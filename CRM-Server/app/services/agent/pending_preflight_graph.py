"""LangGraph subgraph for pending-task preflight routing."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Optional, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy.exc import SQLAlchemyError

from app.services.agent import agent_copy, session_state
from app.services.agent.checkpointer import (
    agent_checkpoint_saver,
    checkpoint_unavailable_fallback_event,
    is_checkpoint_storage_error,
)
from app.services.agent.confirmation_intent import agent_confirmation_intent_service
from app.services.agent.input import AgentTurnInput
from app.services.agent.state import internal_graph_start_event, merge_turn_scoped_events
from app.services.agent.types import JSONDict, JSONValue, coerce_json_dict, coerce_json_value


PENDING_PREFLIGHT_CHECKPOINT_NS = "crm_agent_pending_preflight"


class PendingPreflightGraphState(TypedDict, total=False):
    team_id: int
    session_id: int
    task_projection: JSONDict
    content: str
    is_executable: bool
    confirmation_decision: JSONDict
    interruption_decision: JSONDict
    route: str
    result_projection: JSONDict
    events: Annotated[list[JSONDict], merge_turn_scoped_events]


class PendingPreflightGraphInput(TypedDict, total=False):
    db: object
    session: object
    task: object
    turn_input: AgentTurnInput
    team_id: int
    session_id: int
    events: list[JSONDict]


@dataclass
class PendingTaskPreflightResult:
    """Runtime result produced by the pending preflight LangGraph subgraph."""

    task: object = None
    handled: bool = False
    events: list[JSONDict] = field(default_factory=list)
    assistant_content: str | None = None
    switch_notice: str | None = None
    suspended_task: object = None
    suspend_reason: str | None = None
    suspension_kind: str | None = None
    clear_pending_task_id: int | None = None
    confirmation_decision: object = None


@dataclass
class PendingPreflightGraphSideEffects:
    result: PendingTaskPreflightResult | None = None
    confirmation_decision: object | None = None
    confirmation_events: list[JSONDict] = field(default_factory=list)
    interruption_decision: object | None = None


@dataclass
class PendingPreflightRuntimeContext:
    db: object | None = None
    session: object | None = None
    task: object | None = None
    turn_input: AgentTurnInput | None = None
    team_id: int = 0
    session_id: int = 0
    side_effects: PendingPreflightGraphSideEffects = field(default_factory=PendingPreflightGraphSideEffects)


class PendingPreflightGraphService:
    """Routes a waiting task through explicit LangGraph preflight branches."""

    def __init__(self, *, checkpointer: object | None = None) -> None:
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(PendingPreflightGraphState, context_schema=PendingPreflightRuntimeContext)
        graph.add_node("prepare", self._prepare)
        graph.add_node("cancel_rejected_non_executable", self._cancel_rejected_non_executable)
        graph.add_node("assess_confirmation", self._assess_confirmation)
        graph.add_node("route_interruption", self._route_interruption)
        graph.add_node("finalize_unknown_confirmation", self._finalize_unknown_confirmation)
        graph.add_edge(START, "prepare")
        graph.add_conditional_edges(
            "prepare",
            self._route_after_prepare,
            {
                "cancel": "cancel_rejected_non_executable",
                "assess_confirmation": "assess_confirmation",
                "route_interruption": "route_interruption",
                "end": END,
            },
        )
        graph.add_conditional_edges(
            "assess_confirmation",
            self._route_after_confirmation,
            {
                "route_interruption": "route_interruption",
                "unknown": "finalize_unknown_confirmation",
                "end": END,
            },
        )
        graph.add_conditional_edges(
            "route_interruption",
            self._route_after_interruption,
            {
                "unknown": "finalize_unknown_confirmation",
                "end": END,
            },
        )
        graph.add_edge("cancel_rejected_non_executable", END)
        graph.add_edge("finalize_unknown_confirmation", END)
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    async def run(self, input_state: PendingPreflightGraphInput) -> PendingTaskPreflightResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        side_effects = PendingPreflightGraphSideEffects()
        context = _runtime_context_from_input(input_state, side_effects)
        config = build_pending_preflight_graph_config(
            team_id=context.team_id,
            session_id=context.session_id,
            task_id=_optional_object_id(context.task),
        )
        try:
            await self._graph.ainvoke(checkpoint_state, config, context=context)
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            fallback_side_effects = PendingPreflightGraphSideEffects()
            fallback_context = _runtime_context_from_input(input_state, fallback_side_effects)
            await self._fallback_graph.ainvoke(checkpoint_state, config, context=fallback_context)
            side_effects = fallback_side_effects
            result = side_effects.result or PendingTaskPreflightResult(task=input_state.get("task"))
            result.events = [
                checkpoint_unavailable_fallback_event(
                    runtime="crm_agent_pending_preflight",
                    graph=PENDING_PREFLIGHT_CHECKPOINT_NS,
                ),
                *result.events,
            ]
            return result
        return side_effects.result or PendingTaskPreflightResult(task=input_state.get("task"))

    def _prepare(
        self,
        state: PendingPreflightGraphState,
        runtime: Runtime[PendingPreflightRuntimeContext],
    ) -> PendingPreflightGraphState:
        task = runtime.context.task
        turn_input = runtime.context.turn_input
        if not task or not turn_input:
            runtime.context.side_effects.result = PendingTaskPreflightResult(task=None)
            return {"route": "end", "events": [{"event": "pending_preflight_skipped"}]}
        is_executable = agent_confirmation_intent_service.is_executable_confirmation_task(task)
        if not is_executable and session_state._is_rejection(turn_input.content):
            return {"is_executable": False, "route": "cancel"}
        return {
            "is_executable": is_executable,
            "route": "assess_confirmation" if is_executable else "route_interruption",
            "events": [{
                "event": "pending_preflight_started",
                "task_id": coerce_json_value(getattr(task, "id", None)),
                "is_executable": is_executable,
            }],
        }

    def _cancel_rejected_non_executable(
        self,
        state: PendingPreflightGraphState,
        runtime: Runtime[PendingPreflightRuntimeContext],
    ) -> PendingPreflightGraphState:
        result = _cancel_task(runtime.context.task)
        runtime.context.side_effects.result = result
        return _result_update(result)

    async def _assess_confirmation(
        self,
        state: PendingPreflightGraphState,
        runtime: Runtime[PendingPreflightRuntimeContext],
    ) -> PendingPreflightGraphState:
        context = runtime.context
        if not context.db or not context.session or not context.task or not context.turn_input:
            return {}
        decision = await agent_confirmation_intent_service.assess(
            context.db,
            team_id=context.team_id,
            turn_input=context.turn_input,
            task=context.task,
            memory=session_state._memory_snapshot_for_session(context.session, context.task),
        )
        context.side_effects.confirmation_decision = decision
        assessed_event = {
            "event": "confirmation_intent_assessed",
            "task_id": coerce_json_value(getattr(context.task, "id", None)),
            "intent": coerce_json_value(decision.intent),
            "confidence": coerce_json_value(decision.confidence),
            "reason": coerce_json_value(decision.reason),
        }
        context.side_effects.confirmation_events = [assessed_event]
        if decision.intent == "reject":
            result = _cancel_task(context.task)
            result = PendingTaskPreflightResult(
                task=result.task,
                handled=result.handled,
                events=[assessed_event, *result.events],
                assistant_content=result.assistant_content,
                suspended_task=result.suspended_task,
                suspend_reason=result.suspend_reason,
                suspension_kind=result.suspension_kind,
                clear_pending_task_id=result.clear_pending_task_id,
                confirmation_decision=decision,
            )
            context.side_effects.result = result
        elif decision.intent == "confirm":
            context.side_effects.result = PendingTaskPreflightResult(
                task=context.task,
                events=[assessed_event],
                confirmation_decision=decision,
            )
        return {
            "confirmation_decision": _decision_projection(decision),
            "events": [assessed_event],
        }

    async def _route_interruption(
        self,
        state: PendingPreflightGraphState,
        runtime: Runtime[PendingPreflightRuntimeContext],
    ) -> PendingPreflightGraphState:
        context = runtime.context
        if not context.db or not context.session or not context.task or not context.turn_input:
            return {}
        decision = await session_state._assess_pending_interruption(
            context.db,
            team_id=context.team_id,
            session=context.session,
            task=context.task,
            user_message=context.turn_input.content,
        )
        context.side_effects.interruption_decision = decision
        assessed_event = {
            "event": "pending_interruption_assessed",
            "decision": coerce_json_value(decision.decision),
            "confidence": coerce_json_value(decision.confidence),
            "detected_customer_name": coerce_json_value(decision.detected_customer_name),
            "detected_intent": coerce_json_value(decision.detected_intent),
            "reason": coerce_json_value(decision.reason),
        }
        confirmation_events = _confirmation_events_from_state(state)
        if session_state._is_high_confidence_new_flow(decision):
            switch_notice = agent_copy.pending_switch_notice(decision.detected_customer_name)
            result = PendingTaskPreflightResult(
                task=None,
                switch_notice=switch_notice,
                suspended_task=context.task,
                suspend_reason=decision.reason or "用户开启了新的业务流程",
                suspension_kind="paused",
                events=[
                    *confirmation_events,
                    assessed_event,
                    {
                        "event": "pending_task_interrupted",
                        "content": switch_notice,
                        "suspended_task_id": coerce_json_value(getattr(context.task, "id", None)),
                    },
                ],
                confirmation_decision=context.side_effects.confirmation_decision,
            )
            context.side_effects.result = result
            return _result_update(result, interruption_decision=decision)
        if session_state._is_ambiguous_pending_interruption(decision):
            assistant_content = decision.question or agent_copy.pending_interruption_clarification()
            result = PendingTaskPreflightResult(
                task=context.task,
                handled=True,
                assistant_content=assistant_content,
                events=[
                    *confirmation_events,
                    assessed_event,
                    {
                        "event": "pending_interruption_confirmation_required",
                        "task_id": coerce_json_value(getattr(context.task, "id", None)),
                        "content": assistant_content,
                        "decision": coerce_json_dict(decision.model_dump()),
                    },
                    {"event": "final", "content": assistant_content},
                ],
                confirmation_decision=context.side_effects.confirmation_decision,
            )
            context.side_effects.result = result
            return _result_update(result, interruption_decision=decision)
        result = PendingTaskPreflightResult(
            task=context.task,
            events=[*confirmation_events, assessed_event],
            confirmation_decision=context.side_effects.confirmation_decision,
        )
        context.side_effects.result = result
        return _result_update(result, interruption_decision=decision)

    def _finalize_unknown_confirmation(
        self,
        state: PendingPreflightGraphState,
        runtime: Runtime[PendingPreflightRuntimeContext],
    ) -> PendingPreflightGraphState:
        existing = runtime.context.side_effects.result
        task = existing.task if existing else runtime.context.task
        assistant_content = agent_copy.confirmation_unknown()
        assessed_events = list(existing.events) if existing else []
        result = PendingTaskPreflightResult(
            task=task,
            handled=True,
            assistant_content=assistant_content,
            confirmation_decision=runtime.context.side_effects.confirmation_decision,
            events=[
                *assessed_events,
                {
                    "event": "confirmation_intent_unknown",
                    "task_id": coerce_json_value(getattr(task, "id", None)),
                    "content": assistant_content,
                },
                {"event": "final", "content": assistant_content},
            ],
        )
        runtime.context.side_effects.result = result
        return _result_update(result)

    def _route_after_prepare(self, state: PendingPreflightGraphState) -> str:
        route = state.get("route")
        return route if isinstance(route, str) else "end"

    def _route_after_confirmation(self, state: PendingPreflightGraphState) -> str:
        decision = state.get("confirmation_decision")
        intent = decision.get("intent") if isinstance(decision, dict) else None
        if intent == "confirm" or intent == "reject":
            return "end"
        return "route_interruption"

    def _route_after_interruption(self, state: PendingPreflightGraphState) -> str:
        result = state.get("result_projection")
        if not isinstance(result, dict):
            return "end"
        if result.get("handled") or not result.get("has_task"):
            return "end"
        decision = state.get("confirmation_decision")
        intent = decision.get("intent") if isinstance(decision, dict) else None
        if intent == "unknown":
            return "unknown"
        return "end"


def build_pending_preflight_graph_config(*, team_id: int, session_id: int, task_id: int | None = None) -> RunnableConfig:
    task_key = str(task_id) if task_id is not None else "task"
    return {
        "configurable": {"thread_id": f"crm_agent_pending_preflight:{team_id}:{session_id}:{task_key}"},
        "metadata": {
            "team_id": team_id,
            "session_id": session_id,
            "task_id": task_id,
            "runtime": "crm_agent_pending_preflight",
            "runtime_namespace": PENDING_PREFLIGHT_CHECKPOINT_NS,
        },
    }


def _checkpoint_state_from_input(input_state: PendingPreflightGraphInput) -> PendingPreflightGraphState:
    turn_input = input_state.get("turn_input")
    content = turn_input.content if turn_input else ""
    state: PendingPreflightGraphState = {
        "team_id": int(input_state.get("team_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "task_projection": _task_projection(input_state.get("task")),
        "content": content,
        "events": [internal_graph_start_event("pending_preflight_graph_invocation_started")],
    }
    state["events"].extend(_events(input_state.get("events") or []))
    return state


def _runtime_context_from_input(
    input_state: PendingPreflightGraphInput,
    side_effects: PendingPreflightGraphSideEffects,
) -> PendingPreflightRuntimeContext:
    return PendingPreflightRuntimeContext(
        db=input_state.get("db"),
        session=input_state.get("session"),
        task=input_state.get("task"),
        turn_input=input_state.get("turn_input"),
        team_id=int(input_state.get("team_id") or 0),
        session_id=int(input_state.get("session_id") or 0),
        side_effects=side_effects,
    )


def _cancel_task(task: object) -> PendingTaskPreflightResult:
    assistant_content = agent_copy.task_put_aside()
    return PendingTaskPreflightResult(
        task=None,
        handled=True,
        assistant_content=assistant_content,
        suspended_task=task,
        suspend_reason="用户选择先不处理。",
        suspension_kind="dismissed",
        clear_pending_task_id=_optional_object_id(task),
        events=[
            {
                "event": "task_cancelled",
                "task_id": coerce_json_value(getattr(task, "id", None)),
                "content": assistant_content,
            },
            {"event": "final", "content": assistant_content},
        ],
    )


def _result_update(
    result: PendingTaskPreflightResult,
    *,
    interruption_decision: object | None = None,
) -> PendingPreflightGraphState:
    update: PendingPreflightGraphState = {
        "result_projection": _result_projection(result),
        "events": _events(result.events),
    }
    if result.confirmation_decision:
        update["confirmation_decision"] = _decision_projection(result.confirmation_decision)
    if interruption_decision:
        update["interruption_decision"] = _decision_projection(interruption_decision)
    return update


def _result_projection(result: PendingTaskPreflightResult) -> JSONDict:
    return {
        "has_task": bool(result.task),
        "handled": result.handled,
        "has_assistant_content": bool(result.assistant_content),
        "has_switch_notice": bool(result.switch_notice),
        "suspended_task_id": coerce_json_value(_optional_object_id(result.suspended_task)),
        "clear_pending_task_id": coerce_json_value(result.clear_pending_task_id),
        "suspension_kind": coerce_json_value(result.suspension_kind),
    }


def _decision_projection(decision: object) -> JSONDict:
    if not decision:
        return {}
    if hasattr(decision, "model_dump"):
        return coerce_json_dict(decision.model_dump())
    return coerce_json_dict(decision)


def _task_projection(task: object) -> JSONDict:
    if not task:
        return {}
    projection: JSONDict = {}
    for key in ("id", "task_key", "status", "intent", "target_type", "target_id"):
        value = getattr(task, key, None)
        if value is not None:
            projection[key] = coerce_json_value(value)
    return projection


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


def _confirmation_events_from_state(state: PendingPreflightGraphState) -> list[JSONDict]:
    return [
        event
        for event in _events(state.get("events") or [])
        if event.get("event") == "confirmation_intent_assessed"
    ]


pending_preflight_graph_service = PendingPreflightGraphService(checkpointer=agent_checkpoint_saver)

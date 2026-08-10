"""Follow-up quality domain subgraph for the CRM Agent."""
from __future__ import annotations

from datetime import date, datetime

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy.exc import SQLAlchemyError

from app.services.agent.checkpointer import (
    agent_checkpoint_saver,
    is_checkpoint_storage_error,
    with_checkpoint_unavailable_fallback_event,
)
from app.services.agent.quality import (
    AgentFollowUpQualityEvaluator,
    AgentFollowUpQualityEvaluatorError,
    agent_follow_up_quality_evaluator,
)
from app.services.agent.schemas import AgentMemorySnapshot, AgentSemanticParseResult
from app.services.agent.state import (
    FollowUpQualityGraphInput,
    FollowUpQualityGraphResult,
    FollowUpQualityGraphState,
    FollowUpQualityRuntimeContext,
    internal_graph_start_event,
    visible_graph_events,
)
from app.services.agent.types import coerce_json_dict

FOLLOW_UP_QUALITY_CHECKPOINT_NS = "crm_agent_follow_up_quality"


def build_follow_up_quality_thread_id(*, team_id: int, user_id: int, session_id: int) -> str:
    return f"crm_agent_follow_up_quality:{team_id}:{user_id}:{session_id}"


def build_follow_up_quality_graph_config(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": build_follow_up_quality_thread_id(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
            ),
        },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "runtime": "crm_agent_follow_up_quality",
            "runtime_namespace": FOLLOW_UP_QUALITY_CHECKPOINT_NS,
        },
    }


class FollowUpQualityGraphService:
    """Evaluates follow-up record quality behind a checkpointed domain graph."""

    def __init__(
        self,
        *,
        follow_up_quality_evaluator: AgentFollowUpQualityEvaluator | None = None,
        checkpointer: object | None = None,
    ) -> None:
        self.follow_up_quality_evaluator = follow_up_quality_evaluator or agent_follow_up_quality_evaluator
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(FollowUpQualityGraphState, context_schema=FollowUpQualityRuntimeContext)
        graph.add_node("preflight", self._preflight)
        graph.add_node("evaluate_quality", self._evaluate_quality)
        graph.add_edge(START, "preflight")
        graph.add_conditional_edges(
            "preflight",
            self._route_after_preflight,
            {
                "evaluate": "evaluate_quality",
                "end": END,
            },
        )
        graph.add_edge("evaluate_quality", END)
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    async def run(self, input_state: FollowUpQualityGraphInput) -> FollowUpQualityGraphResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        context = _runtime_context_from_input(input_state)
        config = build_follow_up_quality_graph_config(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
        )
        try:
            result = _with_visible_events(await self._graph.ainvoke(checkpoint_state, config, context=context))
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            fallback_context = _runtime_context_from_input(input_state)
            result = _with_visible_events(
                await self._fallback_graph.ainvoke(checkpoint_state, config, context=fallback_context)
            )
            result = with_checkpoint_unavailable_fallback_event(
                result,
                runtime="crm_agent_follow_up_quality",
                graph=FOLLOW_UP_QUALITY_CHECKPOINT_NS,
            )
            context = fallback_context
        return _attach_side_effects(result, context)

    def _preflight(
        self,
        state: FollowUpQualityGraphState,
        runtime: Runtime[FollowUpQualityRuntimeContext],
    ) -> FollowUpQualityGraphState:
        semantic_result = runtime.context.semantic_result
        skip_reason = _quality_skip_reason(
            state,
            semantic_result=semantic_result,
        )
        if skip_reason:
            return {
                "quality_evaluation_requested": False,
                "quality_skip_reason": skip_reason,
            }
        return {
            "quality_evaluation_requested": True,
            "quality_skip_reason": None,
        }

    def _route_after_preflight(self, state: FollowUpQualityGraphState) -> str:
        if state.get("quality_evaluation_requested"):
            return "evaluate"
        return "end"

    async def _evaluate_quality(
        self,
        state: FollowUpQualityGraphState,
        runtime: Runtime[FollowUpQualityRuntimeContext],
    ) -> FollowUpQualityGraphState:
        context = runtime.context
        semantic_result = context.semantic_result
        if not semantic_result or not context.db:
            return {}

        try:
            envelope = await self.follow_up_quality_evaluator.evaluate_with_metadata(
                context.db,
                team_id=context.team_id,
                user_message=state.get("content", ""),
                semantic_result=semantic_result,
                memory=context.memory,
                current_date=_current_date(state),
            )
        except AgentFollowUpQualityEvaluatorError as exc:
            return {
                "follow_up_quality_error": str(exc),
                "events": [{"event": "follow_up_quality_failed", "message": str(exc)}],
            }

        context.side_effects.follow_up_quality_result = envelope.result
        return {
            "follow_up_quality": coerce_json_dict(envelope.result.model_dump(exclude_none=True)),
            "follow_up_quality_metadata": {
                "quality_source": envelope.quality_source,
                "model": envelope.model,
                "fallback_reason": envelope.fallback_reason,
                "fallback_error": envelope.fallback_error,
            },
        }


def _quality_skip_reason(
    state: FollowUpQualityGraphState,
    *,
    semantic_result: AgentSemanticParseResult | None,
) -> str | None:
    if not semantic_result:
        return "missing_semantic_result"
    if semantic_result.intent != "CUSTOMER_ACTIVITY":
        return "unsupported_intent"
    if _requires_clarification(
        semantic_result,
        has_memory_customer=bool(state.get("has_memory_customer")),
    ):
        return "requires_clarification"
    if not state.get("has_db"):
        return "missing_db"
    if not state.get("has_single_customer"):
        return "missing_single_customer"
    return None


def _requires_clarification(
    semantic_result: AgentSemanticParseResult,
    *,
    has_memory_customer: bool = False,
) -> bool:
    customer_from_memory = semantic_result.customer.resolution_source == "MEMORY" or has_memory_customer
    return (
        semantic_result.need_clarification
        or semantic_result.intent == "UNKNOWN"
        or semantic_result.intent_confidence < 0.75
        or (
            semantic_result.intent != "UNKNOWN"
            and semantic_result.intent != "CRM_READ_QUERY"
            and semantic_result.intent != "FOLLOW_UP_TASK_TRANSITION"
            and semantic_result.intent not in {"CREATE_LEAD", "CREATE_CUSTOMER"}
            and not customer_from_memory
            and semantic_result.customer.confidence < 0.7
        )
    )


def _attach_side_effects(
    result: FollowUpQualityGraphState,
    context: FollowUpQualityRuntimeContext,
) -> FollowUpQualityGraphResult:
    projected: FollowUpQualityGraphResult = dict(result)
    if context.side_effects.follow_up_quality_result:
        projected["follow_up_quality_result"] = context.side_effects.follow_up_quality_result
    return projected


def _checkpoint_state_from_input(input_state: FollowUpQualityGraphInput) -> FollowUpQualityGraphState:
    state: FollowUpQualityGraphState = {
        "team_id": int(input_state.get("team_id") or 0),
        "user_id": int(input_state.get("user_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "content": str(input_state.get("content") or ""),
        "has_db": input_state.get("db") is not None,
        "current_date": None,
        "intent": None,
        "has_single_customer": bool(input_state.get("has_single_customer")),
        "has_memory_customer": bool(input_state.get("has_memory_customer")),
        "quality_evaluation_requested": False,
        "quality_skip_reason": None,
        "follow_up_quality": {},
        "follow_up_quality_metadata": {},
        "follow_up_quality_error": None,
        "events": [internal_graph_start_event("follow_up_quality_graph_invocation_started")],
    }
    current_date = input_state.get("current_date")
    if isinstance(current_date, str):
        state["current_date"] = current_date
    elif isinstance(current_date, datetime):
        state["current_date"] = current_date.date().isoformat()
    elif isinstance(current_date, date):
        state["current_date"] = current_date.isoformat()
    semantic_result = input_state.get("semantic_result")
    if isinstance(semantic_result, AgentSemanticParseResult):
        state["intent"] = semantic_result.intent
    events = input_state.get("events")
    if isinstance(events, list):
        state["events"].extend(
            coerce_json_dict(event)
            for event in events
            if isinstance(event, dict)
        )
    return state


def _with_visible_events(result: FollowUpQualityGraphResult) -> FollowUpQualityGraphResult:
    projected: FollowUpQualityGraphResult = dict(result)
    projected["events"] = visible_graph_events(projected.get("events"))
    return projected


def _runtime_context_from_input(input_state: FollowUpQualityGraphInput) -> FollowUpQualityRuntimeContext:
    semantic_result = input_state.get("semantic_result")
    memory = input_state.get("memory")
    return FollowUpQualityRuntimeContext(
        db=input_state.get("db"),
        team_id=int(input_state.get("team_id") or 0),
        user_id=int(input_state.get("user_id") or 0),
        session_id=int(input_state.get("session_id") or 0),
        semantic_result=semantic_result if isinstance(semantic_result, AgentSemanticParseResult) else None,
        memory=memory if isinstance(memory, AgentMemorySnapshot) else None,
    )


def _current_date(state: FollowUpQualityGraphState) -> date | None:
    current_date = state.get("current_date")
    if isinstance(current_date, str):
        try:
            return date.fromisoformat(current_date)
        except ValueError:
            return None
    return None


follow_up_quality_graph_service = FollowUpQualityGraphService(checkpointer=agent_checkpoint_saver)

"""Customer business-context domain subgraph for the CRM Agent."""
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
from app.services.agent.schemas import AgentSemanticParseResult
from app.services.agent.state import (
    BusinessContextGraphInput,
    BusinessContextGraphResult,
    BusinessContextGraphState,
    BusinessContextRuntimeContext,
    internal_graph_start_event,
    visible_graph_events,
)
from app.services.agent.suggestion import (
    AgentSuggestionGenerator,
    AgentSuggestionGeneratorError,
    agent_suggestion_generator,
)
from app.services.agent.tool_registry import AgentToolRegistry, agent_tool_registry
from app.services.agent.tools.base import AgentToolContext
from app.services.agent.types import coerce_json_dict

BUSINESS_CONTEXT_CHECKPOINT_NS = "crm_agent_business_context"


def build_business_context_thread_id(*, team_id: int, user_id: int, session_id: int) -> str:
    return f"crm_agent_business_context:{team_id}:{user_id}:{session_id}"


def build_business_context_graph_config(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": build_business_context_thread_id(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
            ),
        },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "runtime": "crm_agent_business_context",
            "runtime_namespace": BUSINESS_CONTEXT_CHECKPOINT_NS,
        },
    }


class BusinessContextGraphService:
    """Loads customer business context and derives follow-on business suggestions."""

    def __init__(
        self,
        *,
        tool_registry: AgentToolRegistry | None = None,
        suggestion_generator: AgentSuggestionGenerator | None = None,
        checkpointer: object | None = None,
    ) -> None:
        self.tool_registry = tool_registry or agent_tool_registry
        self.suggestion_generator = suggestion_generator or agent_suggestion_generator
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(BusinessContextGraphState, context_schema=BusinessContextRuntimeContext)
        graph.add_node("load_customer_context", self._load_customer_context)
        graph.add_node("generate_suggestions", self._generate_suggestions)
        graph.add_edge(START, "load_customer_context")
        graph.add_conditional_edges(
            "load_customer_context",
            self._route_after_context,
            {
                "suggestions": "generate_suggestions",
                "end": END,
            },
        )
        graph.add_edge("generate_suggestions", END)
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    async def run(self, input_state: BusinessContextGraphInput) -> BusinessContextGraphResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        context = _runtime_context_from_input(input_state)
        config = build_business_context_graph_config(
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
                runtime="crm_agent_business_context",
                graph=BUSINESS_CONTEXT_CHECKPOINT_NS,
            )
            context = fallback_context
        return _attach_side_effects(result, context)

    async def _load_customer_context(
        self,
        state: BusinessContextGraphState,
        runtime: Runtime[BusinessContextRuntimeContext],
    ) -> BusinessContextGraphState:
        context = runtime.context
        customer = state.get("selected_customer") or {}
        customer_id = _customer_identifier_from_state(customer)
        if customer_id is None or not context.authorization or not context.db:
            return {}

        tool_context = AgentToolContext(
            db=context.db,
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            authorization=context.authorization,
        )
        result = await self.tool_registry.execute(
            "get_customer_context",
            tool_context,
            {
                "customer_id": customer_id,
                "query_text": state.get("content", ""),
            },
        )
        events = [result.to_event()]
        if not result.success:
            return {"events": events}
        business_context = coerce_json_dict(result.data)
        events.append({
            "event": "business_context_loaded",
            "customer_id": customer_id,
            "customer": customer,
        })
        return {"business_context": business_context, "events": events}

    def _route_after_context(self, state: BusinessContextGraphState) -> str:
        if state.get("business_context") and runtime_semantic_allows_suggestions(state.get("intent")):
            return "suggestions"
        return "end"

    async def _generate_suggestions(
        self,
        state: BusinessContextGraphState,
        runtime: Runtime[BusinessContextRuntimeContext],
    ) -> BusinessContextGraphState:
        context = runtime.context
        semantic_result = context.semantic_result
        business_context = state.get("business_context") or {}
        if not semantic_result or not business_context or not context.db:
            return {}

        try:
            envelope = await self.suggestion_generator.generate_with_metadata(
                context.db,
                team_id=context.team_id,
                user_message=state.get("content", ""),
                semantic_result=semantic_result,
                customer_context=business_context,
                current_date=state.get("current_date"),
            )
        except AgentSuggestionGeneratorError as exc:
            return {
                "suggestion_error": str(exc),
                "events": [{"event": "suggestion_failed", "message": str(exc)}],
            }

        context.side_effects.suggestion_result = envelope.result
        return {
            "suggestion_metadata": {
                "suggestion_source": envelope.suggestion_source,
                "model": envelope.model,
                "structured_output_strategy": getattr(envelope, "structured_output_strategy", None),
                "fallback_reason": getattr(envelope, "fallback_reason", None),
                "fallback_error": getattr(envelope, "fallback_error", None),
                "fallback_error_message": getattr(envelope, "fallback_error_message", None),
            },
        }


def runtime_semantic_allows_suggestions(intent: object) -> bool:
    return isinstance(intent, str) and intent not in {"CREATE_LEAD", "CREATE_CUSTOMER", "CRM_READ_QUERY"}


def _attach_side_effects(
    result: BusinessContextGraphState,
    context: BusinessContextRuntimeContext,
) -> BusinessContextGraphResult:
    projected: BusinessContextGraphResult = dict(result)
    if context.side_effects.suggestion_result:
        projected["suggestion_result"] = context.side_effects.suggestion_result
    return projected


def _checkpoint_state_from_input(input_state: BusinessContextGraphInput) -> BusinessContextGraphState:
    state: BusinessContextGraphState = {
        "team_id": int(input_state.get("team_id") or 0),
        "user_id": int(input_state.get("user_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "content": str(input_state.get("content") or ""),
        "has_db": input_state.get("db") is not None,
        "has_authorization": isinstance(input_state.get("authorization"), str)
        and bool(str(input_state.get("authorization")).strip()),
        "intent": None,
        "current_date": None,
        "selected_customer": {},
        "business_context": {},
        "suggestion_metadata": {},
        "suggestion_error": None,
        "events": [internal_graph_start_event("business_context_graph_invocation_started")],
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
    selected_customer = coerce_json_dict(input_state.get("selected_customer"))
    if selected_customer:
        state["selected_customer"] = selected_customer
    business_context = coerce_json_dict(input_state.get("business_context"))
    if business_context:
        state["business_context"] = business_context
    events = input_state.get("events")
    if isinstance(events, list):
        state["events"].extend(
            coerce_json_dict(event)
            for event in events
            if isinstance(event, dict)
        )
    return state


def _with_visible_events(result: BusinessContextGraphResult) -> BusinessContextGraphResult:
    projected: BusinessContextGraphResult = dict(result)
    projected["events"] = visible_graph_events(projected.get("events"))
    return projected


def _runtime_context_from_input(input_state: BusinessContextGraphInput) -> BusinessContextRuntimeContext:
    authorization = input_state.get("authorization")
    return BusinessContextRuntimeContext(
        db=input_state.get("db"),
        team_id=int(input_state.get("team_id") or 0),
        user_id=int(input_state.get("user_id") or 0),
        session_id=int(input_state.get("session_id") or 0),
        authorization=authorization if isinstance(authorization, str) else None,
        semantic_result=input_state.get("semantic_result"),
    )


business_context_graph_service = BusinessContextGraphService(checkpointer=agent_checkpoint_saver)


def _customer_identifier_from_state(customer: dict[str, object]) -> str | None:
    public_id = _non_empty_string(customer.get("public_id"))
    if public_id is not None:
        return public_id
    value = customer.get("id")
    if isinstance(value, int):
        return str(value) if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        customer_id = int(value.strip())
        return str(customer_id) if customer_id > 0 else None
    return _non_empty_string(value)


def _non_empty_string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None

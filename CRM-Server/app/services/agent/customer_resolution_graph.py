"""Customer resolution domain subgraph for the CRM Agent."""
from __future__ import annotations

from typing import Optional

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy.exc import SQLAlchemyError

from app.services.agent import business_rules
from app.services.agent.checkpointer import (
    agent_checkpoint_saver,
    is_checkpoint_storage_error,
    with_checkpoint_unavailable_fallback_event,
)
from app.services.agent.schemas import AgentSemanticParseResult
from app.services.agent.state import (
    CustomerResolutionGraphInput,
    CustomerResolutionGraphResult,
    CustomerResolutionGraphState,
    CustomerResolutionRuntimeContext,
)
from app.services.agent.tool_registry import AgentToolRegistry, agent_tool_registry
from app.services.agent.tools.base import AgentToolContext
from app.services.agent.types import JSONDict, coerce_json_dict


CUSTOMER_RESOLUTION_CHECKPOINT_NS = "crm_agent_customer_resolution"


def build_customer_resolution_thread_id(*, team_id: int, user_id: int, session_id: int) -> str:
    return f"crm_agent_customer_resolution:{team_id}:{user_id}:{session_id}"


def build_customer_resolution_graph_config(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": build_customer_resolution_thread_id(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
            ),
        },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "runtime": "crm_agent_customer_resolution",
            "runtime_namespace": CUSTOMER_RESOLUTION_CHECKPOINT_NS,
        },
    }


class CustomerResolutionGraphService:
    """Resolves the customer target for business workflows."""

    def __init__(
        self,
        *,
        tool_registry: AgentToolRegistry | None = None,
        checkpointer: object | None = None,
    ) -> None:
        self.tool_registry = tool_registry or agent_tool_registry
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(CustomerResolutionGraphState, context_schema=CustomerResolutionRuntimeContext)
        graph.add_node("resolve_from_memory", self._resolve_from_memory)
        graph.add_node("search_customer", self._search_customer)
        graph.add_edge(START, "resolve_from_memory")
        graph.add_conditional_edges(
            "resolve_from_memory",
            self._route_after_memory,
            {
                "search": "search_customer",
                "end": END,
            },
        )
        graph.add_edge("search_customer", END)
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    async def run(self, input_state: CustomerResolutionGraphInput) -> CustomerResolutionGraphResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        context = _runtime_context_from_input(input_state)
        config = build_customer_resolution_graph_config(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
        )
        try:
            return await self._graph.ainvoke(checkpoint_state, config, context=context)
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            fallback_context = _runtime_context_from_input(input_state)
            result = await self._fallback_graph.ainvoke(checkpoint_state, config, context=fallback_context)
            return with_checkpoint_unavailable_fallback_event(
                result,
                runtime="crm_agent_customer_resolution",
                graph=CUSTOMER_RESOLUTION_CHECKPOINT_NS,
            )

    def _resolve_from_memory(
        self,
        state: CustomerResolutionGraphState,
        runtime: Runtime[CustomerResolutionRuntimeContext],
    ) -> CustomerResolutionGraphState:
        semantic_result = runtime.context.semantic_result
        parsed = state.get("parsed") or {}
        memory_customer = self._memory_current_customer(runtime.context.memory)
        if not self._should_use_memory_customer(semantic_result, parsed, memory_customer):
            return {
                "customer_search_requested": self._should_request_customer_search(
                    state,
                    semantic_result=semantic_result,
                    memory=runtime.context.memory,
                ),
            }
        selected_customer = dict(memory_customer)
        parsed = {**parsed, "customer_name": selected_customer.get("account_name")}
        return {
            "customer_search_requested": False,
            "parsed": parsed,
            "customer_candidates": [selected_customer],
            "selected_customer": selected_customer,
            "events": [{"event": "customer_memory_used", "customer": selected_customer}],
        }

    def _route_after_memory(self, state: CustomerResolutionGraphState) -> str:
        if (state.get("selected_customer") or {}).get("id"):
            return "end"
        if self._should_run_customer_search(state):
            return "search"
        return "end"

    async def _search_customer(
        self,
        state: CustomerResolutionGraphState,
        runtime: Runtime[CustomerResolutionRuntimeContext],
    ) -> CustomerResolutionGraphState:
        context = runtime.context
        semantic_result = runtime.context.semantic_result
        parsed = state.get("parsed") or {}
        customer_name = parsed.get("customer_name")
        if (
            not customer_name
            or not context.authorization
            or not context.db
            or self._requires_clarification(semantic_result)
        ):
            return {}

        tool_context = AgentToolContext(
            db=context.db,
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            authorization=context.authorization,
        )
        result = await self.tool_registry.execute(
            "search_customers",
            tool_context,
            {"keyword": customer_name, "limit": 10},
        )
        events = [result.to_event()]
        candidates = business_rules.extract_customer_candidates(result.data) if result.success else []
        if candidates:
            events.append({"event": "customer_candidates", "customers": candidates})
        state_update: CustomerResolutionGraphState = {
            "customer_candidates": candidates,
            "events": events,
        }
        if len(candidates) == 1:
            state_update["selected_customer"] = candidates[0]
        return state_update

    def _should_run_customer_search(self, state: CustomerResolutionGraphState) -> bool:
        return bool(state.get("customer_search_requested"))

    def _should_request_customer_search(
        self,
        state: CustomerResolutionGraphState,
        *,
        semantic_result: Optional[AgentSemanticParseResult],
        memory: Optional[object],
    ) -> bool:
        if not semantic_result or semantic_result.intent in {"CREATE_LEAD", "CREATE_CUSTOMER"}:
            return False
        parsed = state.get("parsed") or {}
        memory_customer = self._memory_current_customer(memory)
        return (
            bool(state.get("has_authorization"))
            and bool(state.get("has_db"))
            and bool(parsed.get("customer_name"))
            and not self._requires_clarification(
                semantic_result,
                has_memory_customer=bool(memory_customer),
            )
            and not self._should_use_memory_customer(semantic_result, parsed, memory_customer)
        )

    @staticmethod
    def _requires_clarification(
        semantic_result: Optional[AgentSemanticParseResult],
        *,
        has_memory_customer: bool = False,
    ) -> bool:
        if semantic_result is None:
            return False
        customer_from_memory = semantic_result.customer.resolution_source == "MEMORY" or has_memory_customer
        return (
            semantic_result.need_clarification
            or semantic_result.intent == "UNKNOWN"
            or semantic_result.intent_confidence < 0.75
            or (
                semantic_result.intent != "UNKNOWN"
                and semantic_result.intent != "CUSTOMER_QUERY"
                and semantic_result.intent not in {"CREATE_LEAD", "CREATE_CUSTOMER"}
                and not customer_from_memory
                and semantic_result.customer.confidence < 0.7
            )
        )

    @staticmethod
    def _memory_current_customer(memory: Optional[object]) -> Optional[dict[str, object]]:
        context = getattr(memory, "session_context", None) if memory else None
        if not isinstance(context, dict):
            return None
        customer = context.get("current_customer")
        if isinstance(customer, dict) and customer.get("id") and customer.get("account_name"):
            return customer
        return None

    @staticmethod
    def _should_use_memory_customer(
        semantic_result: Optional[AgentSemanticParseResult],
        parsed: dict[str, object],
        memory_customer: Optional[dict[str, object]],
    ) -> bool:
        if not semantic_result or not memory_customer:
            return False
        if parsed.get("_customer_name_source") == "EXPLICIT_TEXT_HINT":
            return False
        if semantic_result.intent in {"UNKNOWN", "CUSTOMER_QUERY"}:
            return False
        if semantic_result.customer.resolution_source == "MEMORY":
            return True
        return not parsed.get("customer_name")


def _checkpoint_state_from_input(input_state: CustomerResolutionGraphInput) -> CustomerResolutionGraphState:
    state: CustomerResolutionGraphState = {
        "team_id": int(input_state.get("team_id") or 0),
        "user_id": int(input_state.get("user_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "content": str(input_state.get("content") or ""),
        "has_db": input_state.get("db") is not None,
        "has_authorization": isinstance(input_state.get("authorization"), str)
        and bool(str(input_state.get("authorization")).strip()),
        "intent": None,
        "customer_search_requested": False,
        "parsed": {},
        "customer_candidates": [],
        "selected_customer": {},
        "events": [],
    }
    intent = input_state.get("intent")
    if isinstance(intent, str):
        state["intent"] = intent
    parsed = coerce_json_dict(input_state.get("parsed"))
    if parsed:
        state["parsed"] = parsed
    events = input_state.get("events")
    if isinstance(events, list):
        state["events"] = [
            coerce_json_dict(event)
            for event in events
            if isinstance(event, dict)
        ]
    return state


def _runtime_context_from_input(input_state: CustomerResolutionGraphInput) -> CustomerResolutionRuntimeContext:
    authorization = input_state.get("authorization")
    return CustomerResolutionRuntimeContext(
        db=input_state.get("db"),
        team_id=int(input_state.get("team_id") or 0),
        user_id=int(input_state.get("user_id") or 0),
        session_id=int(input_state.get("session_id") or 0),
        authorization=authorization if isinstance(authorization, str) else None,
        memory=input_state.get("memory"),
        semantic_result=input_state.get("semantic_result"),
    )


customer_resolution_graph_service = CustomerResolutionGraphService(checkpointer=agent_checkpoint_saver)

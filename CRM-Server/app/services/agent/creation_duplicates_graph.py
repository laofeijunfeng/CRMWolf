"""Creation duplicate-check domain subgraph for the CRM Agent."""
from __future__ import annotations

from collections.abc import Mapping

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
    CreationDuplicateGraphInput,
    CreationDuplicateGraphResult,
    CreationDuplicateGraphState,
    CreationDuplicateRuntimeContext,
    internal_graph_start_event,
    visible_graph_events,
)
from app.services.agent.tool_registry import AgentToolRegistry, agent_tool_registry
from app.services.agent.tools.base import AgentToolContext
from app.services.agent.types import JSONDict, coerce_json_dict


CREATION_DUPLICATES_CHECKPOINT_NS = "crm_agent_creation_duplicates"


def build_creation_duplicates_thread_id(*, team_id: int, user_id: int, session_id: int) -> str:
    return f"crm_agent_creation_duplicates:{team_id}:{user_id}:{session_id}"


def build_creation_duplicates_graph_config(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": build_creation_duplicates_thread_id(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
            ),
        },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "runtime": "crm_agent_creation_duplicates",
            "runtime_namespace": CREATION_DUPLICATES_CHECKPOINT_NS,
        },
    }


class CreationDuplicateGraphService:
    """Checks duplicate customers/leads before create workflows proceed."""

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
        graph = StateGraph(CreationDuplicateGraphState, context_schema=CreationDuplicateRuntimeContext)
        graph.add_node("preflight", self._preflight)
        graph.add_node("search_duplicates", self._search_duplicates)
        graph.add_edge(START, "preflight")
        graph.add_conditional_edges(
            "preflight",
            self._route_after_preflight,
            {
                "search": "search_duplicates",
                "end": END,
            },
        )
        graph.add_edge("search_duplicates", END)
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    async def run(self, input_state: CreationDuplicateGraphInput) -> CreationDuplicateGraphResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        context = _runtime_context_from_input(input_state)
        config = build_creation_duplicates_graph_config(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
        )
        try:
            return _with_visible_events(await self._graph.ainvoke(checkpoint_state, config, context=context))
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            fallback_context = _runtime_context_from_input(input_state)
            result = _with_visible_events(
                await self._fallback_graph.ainvoke(checkpoint_state, config, context=fallback_context)
            )
            return with_checkpoint_unavailable_fallback_event(
                result,
                runtime="crm_agent_creation_duplicates",
                graph=CREATION_DUPLICATES_CHECKPOINT_NS,
            )

    def _preflight(
        self,
        state: CreationDuplicateGraphState,
        runtime: Runtime[CreationDuplicateRuntimeContext],
    ) -> CreationDuplicateGraphState:
        skip_reason = _duplicate_skip_reason(state, semantic_result=runtime.context.semantic_result)
        if skip_reason:
            return {
                "duplicate_search_requested": False,
                "duplicate_skip_reason": skip_reason,
            }

        payload = _duplicate_search_payload(state)
        if not payload:
            return {
                "duplicate_search_requested": False,
                "duplicate_skip_reason": "missing_search_terms",
            }
        return {
            "duplicate_search_requested": True,
            "duplicate_skip_reason": None,
            "duplicate_search_payload": payload,
        }

    def _route_after_preflight(self, state: CreationDuplicateGraphState) -> str:
        if state.get("duplicate_search_requested"):
            return "search"
        return "end"

    async def _search_duplicates(
        self,
        state: CreationDuplicateGraphState,
        runtime: Runtime[CreationDuplicateRuntimeContext],
    ) -> CreationDuplicateGraphState:
        context = runtime.context
        payload = state.get("duplicate_search_payload") or {}
        if not context.db or not context.authorization or not payload:
            return {}

        tool_context = AgentToolContext(
            db=context.db,
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            authorization=context.authorization,
        )
        result = await self.tool_registry.execute(
            "search_creation_duplicates",
            tool_context,
            payload,
        )
        events = [result.to_event()]
        if not result.success or not isinstance(result.data, dict):
            return {"events": events}

        duplicate_candidates = _duplicate_candidates_from_tool_data(result.data)
        if not _has_duplicate_candidates(duplicate_candidates):
            return {"events": events}

        events.append({
            "event": "creation_duplicate_candidates",
            "customers": duplicate_candidates["customers"],
            "leads": duplicate_candidates["leads"],
            "hidden_customer_count": duplicate_candidates["hidden_customer_count"],
            "hidden_lead_count": duplicate_candidates["hidden_lead_count"],
        })
        return {
            "creation_duplicate_candidates": duplicate_candidates,
            "events": events,
        }


def _duplicate_skip_reason(
    state: CreationDuplicateGraphState,
    *,
    semantic_result: AgentSemanticParseResult | None,
) -> str | None:
    if state.get("intent") not in {"CREATE_LEAD", "CREATE_CUSTOMER"}:
        return "unsupported_intent"
    if not state.get("has_authorization"):
        return "missing_authorization"
    if not state.get("has_db"):
        return "missing_db"
    if semantic_result and _requires_clarification(semantic_result):
        return "requires_clarification"
    return None


def _requires_clarification(semantic_result: AgentSemanticParseResult) -> bool:
    return (
        semantic_result.need_clarification
        or semantic_result.intent == "UNKNOWN"
        or semantic_result.intent_confidence < 0.75
    )


def _duplicate_search_payload(state: CreationDuplicateGraphState) -> JSONDict:
    intent = state.get("intent")
    parsed = state.get("parsed") or {}
    create_payload = (
        coerce_json_dict(parsed.get("lead"))
        if intent == "CREATE_LEAD"
        else coerce_json_dict(parsed.get("customer_create"))
    )
    name_value = create_payload.get("lead_name") if intent == "CREATE_LEAD" else create_payload.get("account_name")
    phone_value = create_payload.get("contact_phone")
    name = name_value if isinstance(name_value, str) else None
    phone = phone_value if isinstance(phone_value, str) else None
    customer_keywords = business_rules.creation_duplicate_keywords(name)
    lead_keywords = list(customer_keywords)
    if not customer_keywords and not lead_keywords and not phone:
        return {}
    return {
        "customer_keywords": customer_keywords,
        "lead_keywords": lead_keywords,
        "phone": phone,
        "limit": 5,
    }


def _duplicate_candidates_from_tool_data(data: dict[object, object]) -> JSONDict:
    return {
        "customers": _json_dict_list(data.get("customers")),
        "leads": _json_dict_list(data.get("leads")),
        "hidden_customer_count": _count_from_value(data.get("hidden_customer_count")),
        "hidden_lead_count": _count_from_value(data.get("hidden_lead_count")),
    }


def _json_dict_list(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    return [
        coerce_json_dict(item)
        for item in value
        if isinstance(item, Mapping)
    ]


def _count_from_value(value: object) -> int:
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def _has_duplicate_candidates(duplicate_candidates: JSONDict) -> bool:
    return bool(
        duplicate_candidates["customers"]
        or duplicate_candidates["leads"]
        or duplicate_candidates["hidden_customer_count"]
        or duplicate_candidates["hidden_lead_count"]
    )


def _checkpoint_state_from_input(input_state: CreationDuplicateGraphInput) -> CreationDuplicateGraphState:
    state: CreationDuplicateGraphState = {
        "team_id": int(input_state.get("team_id") or 0),
        "user_id": int(input_state.get("user_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "content": str(input_state.get("content") or ""),
        "has_db": input_state.get("db") is not None,
        "has_authorization": isinstance(input_state.get("authorization"), str)
        and bool(str(input_state.get("authorization")).strip()),
        "intent": None,
        "parsed": {},
        "duplicate_search_requested": False,
        "duplicate_skip_reason": None,
        "duplicate_search_payload": {},
        "creation_duplicate_candidates": {},
        "events": [internal_graph_start_event("creation_duplicate_graph_invocation_started")],
    }
    semantic_result = input_state.get("semantic_result")
    if isinstance(semantic_result, AgentSemanticParseResult):
        state["intent"] = semantic_result.intent
    parsed = coerce_json_dict(input_state.get("parsed"))
    if parsed:
        state["parsed"] = parsed
    events = input_state.get("events")
    if isinstance(events, list):
        state["events"].extend(
            coerce_json_dict(event)
            for event in events
            if isinstance(event, dict)
        )
    return state


def _with_visible_events(result: CreationDuplicateGraphResult) -> CreationDuplicateGraphResult:
    projected: CreationDuplicateGraphResult = dict(result)
    projected["events"] = visible_graph_events(projected.get("events"))
    return projected


def _runtime_context_from_input(input_state: CreationDuplicateGraphInput) -> CreationDuplicateRuntimeContext:
    authorization = input_state.get("authorization")
    semantic_result = input_state.get("semantic_result")
    return CreationDuplicateRuntimeContext(
        db=input_state.get("db"),
        team_id=int(input_state.get("team_id") or 0),
        user_id=int(input_state.get("user_id") or 0),
        session_id=int(input_state.get("session_id") or 0),
        authorization=authorization if isinstance(authorization, str) else None,
        semantic_result=semantic_result if isinstance(semantic_result, AgentSemanticParseResult) else None,
    )


creation_duplicate_graph_service = CreationDuplicateGraphService(checkpointer=agent_checkpoint_saver)

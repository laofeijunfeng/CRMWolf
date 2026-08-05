"""Customer resolution domain subgraph for the CRM Agent."""
from __future__ import annotations

import re
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
from app.services.agent.resource_resolution_graph import (
    ResourceResolutionGraphService,
    resource_resolution_graph_service,
)
from app.services.agent.schemas import AgentSemanticParseResult
from app.services.agent.state import (
    CustomerResolutionGraphInput,
    CustomerResolutionGraphResult,
    CustomerResolutionGraphState,
    CustomerResolutionRuntimeContext,
    internal_graph_start_event,
    visible_graph_events,
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
        resource_resolution_graph: ResourceResolutionGraphService | None = None,
        checkpointer: object | None = None,
    ) -> None:
        self.tool_registry = tool_registry or agent_tool_registry
        self.resource_resolution_graph = resource_resolution_graph or resource_resolution_graph_service
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
            selected = _select_single_customer_candidate(
                candidate=candidates[0],
                target_name=str(customer_name),
                content=state.get("content") or "",
            )
            if selected:
                state_update["selected_customer"] = selected
        elif len(candidates) > 1:
            resolution = await self.resource_resolution_graph.run(
                {
                    "team_id": context.team_id,
                    "user_id": context.user_id,
                    "session_id": context.session_id,
                    "resource_kind": "customer",
                    "action_name": "resolve_customer",
                    "content": state.get("content") or "",
                    "target": {"target_name": customer_name},
                    "candidates": candidates,
                },
                ranker=_rank_customer_candidates_by_search_match,
            )
            events.extend([
                event for event in resolution.get("events", [])
                if isinstance(event, dict)
            ])
            selected = coerce_json_dict(resolution.get("selected_candidate"))
            if selected.get("id"):
                state_update["selected_customer"] = selected
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
        "events": [internal_graph_start_event("customer_resolution_graph_invocation_started")],
    }
    intent = input_state.get("intent")
    if isinstance(intent, str):
        state["intent"] = intent
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


def _with_visible_events(result: CustomerResolutionGraphResult) -> CustomerResolutionGraphResult:
    projected: CustomerResolutionGraphResult = dict(result)
    projected["events"] = visible_graph_events(projected.get("events"))
    return projected


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


async def _rank_customer_candidates_by_search_match(state: CustomerResolutionGraphState) -> list[JSONDict]:
    candidates = state.get("candidates")
    if not isinstance(candidates, list):
        return []
    target_name = str(coerce_json_dict(state.get("target")).get("target_name") or "")
    content = str(state.get("content") or "")
    rankings: list[JSONDict] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        customer_id = candidate.get("id")
        if not isinstance(customer_id, (str, int)) or not str(customer_id):
            continue
        match = coerce_json_dict(candidate.get("match"))
        score = _customer_identity_score(candidate, match=match, target_name=target_name, content=content)
        evidence = _customer_identity_evidence(candidate, match=match, target_name=target_name)
        risk_notes = [] if score >= 0.82 else ["候选客户身份证据不足"]
        rankings.append({
            "resource_id": customer_id,
            "confidence": score,
            "evidence": evidence,
            "risk_notes": risk_notes,
        })
    return sorted(rankings, key=lambda item: float(item.get("confidence") or 0), reverse=True)


def _select_single_customer_candidate(*, candidate: JSONDict, target_name: str, content: str) -> JSONDict:
    match = coerce_json_dict(candidate.get("match"))
    score = _customer_identity_score(candidate, match=match, target_name=target_name, content=content)
    if score < 0.82:
        return {}
    selected = dict(candidate)
    selected["confidence"] = score
    selected["evidence"] = _customer_identity_evidence(candidate, match=match, target_name=target_name)
    return selected


def _customer_identity_score(candidate: JSONDict, *, match: JSONDict, target_name: str, content: str) -> float:
    source = str(match.get("source") or "")
    raw_score = _candidate_match_score(match)
    identity_support = _identity_support_score(candidate, match=match, target_name=target_name, content=content)
    if identity_support >= 0.95:
        return min(1.0, max(raw_score, 0.95))
    if identity_support >= 0.88:
        return min(0.94, max(raw_score, 0.93))
    if identity_support >= 0.78:
        return min(0.86, max(raw_score, 0.78))
    sources = match.get("sources")
    source_set = {str(item) for item in sources} if isinstance(sources, list) else {source}
    if source in {"customer_identity_term", "generated_match_term", "customer_alias_fact", "hybrid_identity"}:
        return min(0.94, max(raw_score, 0.86))
    if source_set & {"customer_identity_term", "generated_match_term", "customer_alias_fact"}:
        return min(0.96, max(raw_score, 0.88))
    if source == "customer_knowledge":
        return min(raw_score, 0.68)
    if source == "customer_alias":
        return min(raw_score, 0.72)
    if source in {"customer_search", "hybrid"}:
        return min(raw_score, 0.76)
    return min(raw_score, 0.55)


def _identity_support_score(candidate: JSONDict, *, match: JSONDict, target_name: str, content: str) -> float:
    target = _normalize_identity_text(target_name)
    if not target:
        return 0.0
    candidate_names = _customer_candidate_names(candidate, match)
    for name in candidate_names:
        normalized_name = _normalize_identity_text(name)
        if not normalized_name:
            continue
        if normalized_name == target:
            return 0.98
        if _contains_identity(normalized_name, target):
            return 0.78 if len(target) <= 3 else 0.92
        if _contains_identity(target, normalized_name):
            return 0.92
    evidence_text = _candidate_evidence_text(match)
    if _contains_identity(_normalize_identity_text(evidence_text), target):
        return 0.88
    if _contains_identity(_normalize_identity_text(content), target):
        return 0.72
    return 0.0


def _customer_candidate_names(candidate: JSONDict, match: JSONDict) -> list[str]:
    names: list[str] = []
    for field in ("account_name", "name", "display_name"):
        value = candidate.get(field)
        if isinstance(value, str) and value.strip():
            names.append(value.strip())
    aliases = match.get("matched_aliases")
    if isinstance(aliases, list):
        names.extend(alias.strip() for alias in aliases if isinstance(alias, str) and alias.strip())
    terms = match.get("matched_terms")
    if isinstance(terms, list):
        names.extend(term.strip() for term in terms if isinstance(term, str) and term.strip())
    return list(dict.fromkeys(names))


def _customer_identity_evidence(candidate: JSONDict, *, match: JSONDict, target_name: str) -> list[str]:
    evidence = _candidate_match_evidence(match)
    account_name = candidate.get("account_name")
    if isinstance(account_name, str) and account_name.strip():
        normalized_target = _normalize_identity_text(target_name)
        normalized_name = _normalize_identity_text(account_name)
        if normalized_target and (
            normalized_target == normalized_name
            or _contains_identity(normalized_name, normalized_target)
            or _contains_identity(normalized_target, normalized_name)
        ):
            evidence.insert(0, f"客户名称匹配「{account_name.strip()}」")
    return list(dict.fromkeys(evidence))[:3]


def _candidate_match_score(match: JSONDict) -> float:
    source = match.get("source")
    score = match.get("score")
    if isinstance(score, (int, float)):
        return min(max(float(score), 0.0), 1.0)
    if source == "customer_search":
        return 0.88
    if source == "hybrid":
        return 0.94
    if source in {"hybrid_identity", "customer_identity_term", "generated_match_term", "customer_alias_fact"}:
        return 0.9
    if source == "customer_knowledge":
        return 0.84
    return 0.5


def _candidate_match_evidence(match: JSONDict) -> list[str]:
    reason = match.get("reason")
    evidence = [reason] if isinstance(reason, str) and reason.strip() else []
    for item in match.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        snippet = item.get("snippet")
        if isinstance(title, str) and isinstance(snippet, str):
            evidence.append(f"{title}: {snippet}")
    return evidence[:3]


def _candidate_evidence_text(match: JSONDict) -> str:
    parts: list[str] = []
    reason = match.get("reason")
    if isinstance(reason, str):
        parts.append(reason)
    for item in match.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        for field in ("title", "snippet", "text"):
            value = item.get(field)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
    return " ".join(parts)


def _normalize_identity_text(value: object) -> str:
    text = re.sub(r"[\s·,，、.。/／()（）【】\\-]+", "", str(value or "").strip().lower())
    for suffix in ("股份有限公司", "有限责任公司", "集团有限公司", "有限公司", "股份公司", "集团", "公司"):
        if text.endswith(suffix) and len(text) > len(suffix) + 1:
            return text[: -len(suffix)]
    return text


def _contains_identity(container: str, needle: str) -> bool:
    return len(needle) >= 2 and needle in container

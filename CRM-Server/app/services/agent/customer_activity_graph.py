"""Customer-activity action-planning subgraph for the CRM Agent."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

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
from app.services.agent.state import (
    CustomerActivityPlanningGraphInput,
    CustomerActivityPlanningGraphResult,
    CustomerActivityPlanningGraphState,
    CustomerActivityPlanningRuntimeContext,
)
from app.services.agent.types import JSONDict, JSONValue, coerce_json_dict
from app.services.customer_activity_kinds import infer_activity_kind


CUSTOMER_ACTIVITY_CHECKPOINT_NS = "crm_agent_customer_activity"

CustomerActivityRoute = Literal[
    "missing_customer_name",
    "single_customer",
    "multiple_customers",
    "customer_not_found",
]


def build_customer_activity_thread_id(*, team_id: int, user_id: int, session_id: int) -> str:
    return f"crm_agent_customer_activity:{team_id}:{user_id}:{session_id}"


def build_customer_activity_graph_config(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": build_customer_activity_thread_id(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
            ),
        },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "runtime": "crm_agent_customer_activity",
            "runtime_namespace": CUSTOMER_ACTIVITY_CHECKPOINT_NS,
        },
    }


class CustomerActivityPlanningGraphService:
    """Plans customer-activity responses and HITL actions through explicit graph branches."""

    def __init__(self, *, checkpointer: object | None = None) -> None:
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(
            CustomerActivityPlanningGraphState,
            context_schema=CustomerActivityPlanningRuntimeContext,
        )
        graph.add_node("derive_customer_route", self._derive_customer_route)
        graph.add_node("missing_customer_name_response", self._missing_customer_name_response)
        graph.add_node("single_customer_response", self._single_customer_response)
        graph.add_node("multiple_customers_response", self._multiple_customers_response)
        graph.add_node("customer_not_found_response", self._customer_not_found_response)
        graph.add_edge(START, "derive_customer_route")
        graph.add_conditional_edges(
            "derive_customer_route",
            self._route_after_customer,
            {
                "missing_customer_name": "missing_customer_name_response",
                "single_customer": "single_customer_response",
                "multiple_customers": "multiple_customers_response",
                "customer_not_found": "customer_not_found_response",
            },
        )
        for node_name in [
            "missing_customer_name_response",
            "single_customer_response",
            "multiple_customers_response",
            "customer_not_found_response",
        ]:
            graph.add_edge(node_name, END)
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    async def run(self, input_state: CustomerActivityPlanningGraphInput) -> CustomerActivityPlanningGraphResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        context = CustomerActivityPlanningRuntimeContext(
            team_id=int(input_state.get("team_id") or 0),
            user_id=int(input_state.get("user_id") or 0),
            session_id=int(input_state.get("session_id") or 0),
        )
        config = build_customer_activity_graph_config(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
        )
        try:
            return await self._graph.ainvoke(checkpoint_state, config, context=context)
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            result = await self._fallback_graph.ainvoke(checkpoint_state, config, context=context)
            return with_checkpoint_unavailable_fallback_event(
                result,
                runtime="crm_agent_customer_activity",
                graph=CUSTOMER_ACTIVITY_CHECKPOINT_NS,
            )

    def _derive_customer_route(
        self,
        state: CustomerActivityPlanningGraphState,
        runtime: Runtime[CustomerActivityPlanningRuntimeContext],
    ) -> CustomerActivityPlanningGraphState:
        candidates = state.get("customer_candidates") or []
        if not state.get("customer_name"):
            return {"customer_route": "missing_customer_name"}
        if len(candidates) == 1:
            return {"customer_route": "single_customer", "selected_customer": candidates[0]}
        if len(candidates) > 1:
            return {"customer_route": "multiple_customers"}
        return {"customer_route": "customer_not_found"}

    def _route_after_customer(self, state: CustomerActivityPlanningGraphState) -> CustomerActivityRoute:
        route = state.get("customer_route")
        if route in {"missing_customer_name", "single_customer", "multiple_customers", "customer_not_found"}:
            return route
        return "customer_not_found"

    def _missing_customer_name_response(
        self,
        state: CustomerActivityPlanningGraphState,
    ) -> CustomerActivityPlanningGraphState:
        return {"response": "我识别到这是客户活动，但还缺少明确客户名称。请补充客户名称。", "action": {}}

    def _single_customer_response(self, state: CustomerActivityPlanningGraphState) -> CustomerActivityPlanningGraphState:
        customer = state.get("selected_customer") or {}
        activity_payload = state.get("activity_payload") or {}
        return {
            "response": f"我识别到客户「{customer.get('account_name')}」的客户活动。请确认是否创建这条客户活动？",
            "action": {
                "action": "create_customer_activity",
                "customer": customer,
                "payload": {
                    "customer_id": customer.get("id"),
                    **activity_payload,
                },
            },
        }

    def _multiple_customers_response(
        self,
        state: CustomerActivityPlanningGraphState,
    ) -> CustomerActivityPlanningGraphState:
        candidates = state.get("customer_candidates") or []
        candidate_lines = [
            f"{index}. {customer.get('account_name')}"
            for index, customer in enumerate(candidates, start=1)
        ]
        return {
            "response": "我找到了多个可能的客户，请告诉我要记录到哪一个客户：" + "；".join(candidate_lines),
            "action": {
                "action": "select_customer_for_activity",
                "customers": candidates,
                "payload": state.get("activity_payload") or {},
            },
        }

    def _customer_not_found_response(
        self,
        state: CustomerActivityPlanningGraphState,
    ) -> CustomerActivityPlanningGraphState:
        return {
            "response": business_rules.customer_not_found_response(state.get("customer_name") or ""),
            "action": {},
        }


def _checkpoint_state_from_input(input_state: CustomerActivityPlanningGraphInput) -> CustomerActivityPlanningGraphState:
    parsed = coerce_json_dict(input_state.get("parsed"))
    return {
        "team_id": int(input_state.get("team_id") or 0),
        "user_id": int(input_state.get("user_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "parsed": parsed,
        "customer_candidates": _json_dict_list(input_state.get("customer_candidates")),
        "customer_name": _optional_string(parsed.get("customer_name")),
        "selected_customer": {},
        "activity_payload": _customer_activity_payload(parsed),
        "customer_route": None,
        "response": None,
        "action": {},
    }


def _customer_activity_payload(parsed: JSONDict) -> JSONDict:
    content = _string_or_default(parsed.get("follow_up_content"), "")
    method = _string_or_default(parsed.get("method"), "AI录入")
    original_content = _string_or_default(parsed.get("original_content"), content)
    activity_kind = infer_activity_kind(method, original_content or content)
    return {
        "activity_kind": activity_kind,
        "source_content": original_content,
        "content": content,
        "method": method,
        "next_action": parsed.get("next_action"),
        "next_follow_time_text": parsed.get("next_follow_time_text"),
        "next_follow_time_iso": parsed.get("next_follow_time_iso"),
    }


def _json_dict_list(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    return [coerce_json_dict(item) for item in value if isinstance(item, Mapping)]


def _optional_string(value: JSONValue) -> str | None:
    return value if isinstance(value, str) else None


def _string_or_default(value: JSONValue, default: str) -> str:
    return value if isinstance(value, str) and value else default


customer_activity_planning_graph_service = CustomerActivityPlanningGraphService(checkpointer=agent_checkpoint_saver)

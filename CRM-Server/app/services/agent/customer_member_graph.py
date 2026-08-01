"""Customer-member action-planning subgraph for the CRM Agent."""
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
    CustomerMemberPlanningGraphInput,
    CustomerMemberPlanningGraphResult,
    CustomerMemberPlanningGraphState,
    CustomerMemberPlanningRuntimeContext,
)
from app.services.agent.types import JSONDict, JSONValue, coerce_json_dict


CUSTOMER_MEMBER_CHECKPOINT_NS = "crm_agent_customer_member"

CustomerMemberCustomerRoute = Literal[
    "missing_customer_name",
    "single_customer",
    "multiple_customers",
    "customer_not_found",
]
CustomerMemberBusinessRoute = Literal[
    "collect_fields",
    "member_resolution_error",
    "confirm_create",
]


def build_customer_member_thread_id(*, team_id: int, user_id: int, session_id: int) -> str:
    return f"crm_agent_customer_member:{team_id}:{user_id}:{session_id}"


def build_customer_member_graph_config(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
) -> RunnableConfig:
    return {
        "configurable": {
                "thread_id": build_customer_member_thread_id(
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session_id,
                ),
            },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "runtime": "crm_agent_customer_member",
            "runtime_namespace": CUSTOMER_MEMBER_CHECKPOINT_NS,
        },
    }


class CustomerMemberPlanningGraphService:
    """Plans customer-member responses and HITL actions through explicit graph branches."""

    def __init__(self, *, checkpointer: object | None = None) -> None:
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(
            CustomerMemberPlanningGraphState,
            context_schema=CustomerMemberPlanningRuntimeContext,
        )
        graph.add_node("derive_customer_route", self._derive_customer_route)
        graph.add_node("missing_customer_name_response", self._missing_customer_name_response)
        graph.add_node("multiple_customers_response", self._multiple_customers_response)
        graph.add_node("customer_not_found_response", self._customer_not_found_response)
        graph.add_node("derive_customer_member_context", self._derive_customer_member_context)
        graph.add_node("collect_fields_response", self._collect_fields_response)
        graph.add_node("member_resolution_error_response", self._member_resolution_error_response)
        graph.add_node("confirm_create_response", self._confirm_create_response)
        graph.add_edge(START, "derive_customer_route")
        graph.add_conditional_edges(
            "derive_customer_route",
            self._route_after_customer,
            {
                "missing_customer_name": "missing_customer_name_response",
                "single_customer": "derive_customer_member_context",
                "multiple_customers": "multiple_customers_response",
                "customer_not_found": "customer_not_found_response",
            },
        )
        graph.add_conditional_edges(
            "derive_customer_member_context",
            self._route_after_customer_member_context,
            {
                "collect_fields": "collect_fields_response",
                "member_resolution_error": "member_resolution_error_response",
                "confirm_create": "confirm_create_response",
            },
        )
        for node_name in [
            "missing_customer_name_response",
            "multiple_customers_response",
            "customer_not_found_response",
            "collect_fields_response",
            "member_resolution_error_response",
            "confirm_create_response",
        ]:
            graph.add_edge(node_name, END)
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    async def run(self, input_state: CustomerMemberPlanningGraphInput) -> CustomerMemberPlanningGraphResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        context = CustomerMemberPlanningRuntimeContext(
            team_id=int(input_state.get("team_id") or 0),
            user_id=int(input_state.get("user_id") or 0),
            session_id=int(input_state.get("session_id") or 0),
        )
        config = build_customer_member_graph_config(
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
                runtime="crm_agent_customer_member",
                graph=CUSTOMER_MEMBER_CHECKPOINT_NS,
            )

    def _derive_customer_route(
        self,
        state: CustomerMemberPlanningGraphState,
        runtime: Runtime[CustomerMemberPlanningRuntimeContext],
    ) -> CustomerMemberPlanningGraphState:
        candidates = state.get("customer_candidates") or []
        if not state.get("customer_name"):
            return {"customer_route": "missing_customer_name"}
        if len(candidates) == 1:
            return {"customer_route": "single_customer", "selected_customer": candidates[0]}
        if len(candidates) > 1:
            return {"customer_route": "multiple_customers"}
        return {"customer_route": "customer_not_found"}

    def _route_after_customer(self, state: CustomerMemberPlanningGraphState) -> CustomerMemberCustomerRoute:
        route = state.get("customer_route")
        if route in {"missing_customer_name", "single_customer", "multiple_customers", "customer_not_found"}:
            return route
        return "customer_not_found"

    def _missing_customer_name_response(self, state: CustomerMemberPlanningGraphState) -> CustomerMemberPlanningGraphState:
        return {"response": "我识别到这是设置客户成员，但还缺少明确客户名称。请补充客户名称。", "action": {}}

    def _multiple_customers_response(self, state: CustomerMemberPlanningGraphState) -> CustomerMemberPlanningGraphState:
        candidates = state.get("customer_candidates") or []
        candidate_lines = [
            f"{index}. {customer.get('account_name')}"
            for index, customer in enumerate(candidates, start=1)
        ]
        return {
            "response": "我找到了多个可能的客户，请告诉我要给哪一个客户设置成员：" + "；".join(candidate_lines),
            "action": {
                "action": "select_customer_for_customer_member",
                "customers": candidates,
                "payload": {
                    "customer_member": state.get("customer_member") or {},
                    "missing_fields": state.get("missing_fields") or [],
                },
            },
        }

    def _customer_not_found_response(self, state: CustomerMemberPlanningGraphState) -> CustomerMemberPlanningGraphState:
        return {
            "response": business_rules.customer_not_found_response(state.get("customer_name") or ""),
            "action": {},
        }

    def _derive_customer_member_context(
        self,
        state: CustomerMemberPlanningGraphState,
        runtime: Runtime[CustomerMemberPlanningRuntimeContext],
    ) -> CustomerMemberPlanningGraphState:
        member = state.get("customer_member") or {}
        missing_fields = business_rules.missing_customer_member_fields(member)
        if missing_fields:
            return {
                "missing_fields": missing_fields,
                "customer_member_route": "collect_fields",
                "member_error": None,
                "resolved_member": {},
            }
        resolved_member, member_error = business_rules.resolve_customer_member(
            member,
            state.get("business_context") or {},
        )
        if member_error:
            return {
                "missing_fields": ["user_name"],
                "customer_member_route": "member_resolution_error",
                "member_error": member_error,
                "resolved_member": {},
            }
        return {
            "missing_fields": [],
            "customer_member_route": "confirm_create",
            "member_error": None,
            "resolved_member": coerce_json_dict(resolved_member),
        }

    def _route_after_customer_member_context(
        self,
        state: CustomerMemberPlanningGraphState,
    ) -> CustomerMemberBusinessRoute:
        route = state.get("customer_member_route")
        if route in {"collect_fields", "member_resolution_error", "confirm_create"}:
            return route
        return "collect_fields"

    def _collect_fields_response(self, state: CustomerMemberPlanningGraphState) -> CustomerMemberPlanningGraphState:
        customer = state.get("selected_customer") or {}
        missing_fields = state.get("missing_fields") or []
        return {
            "response": (
                f"我识别到要为「{customer.get('account_name')}」设置客户成员，"
                f"还需要补充：{business_rules.format_customer_member_missing_fields(missing_fields)}。"
            ),
            "action": self._collect_fields_action(state, customer, missing_fields),
        }

    def _member_resolution_error_response(
        self,
        state: CustomerMemberPlanningGraphState,
    ) -> CustomerMemberPlanningGraphState:
        customer = state.get("selected_customer") or {}
        missing_fields = state.get("missing_fields") or ["user_name"]
        return {
            "response": state.get("member_error") or "请补充更明确的客户成员信息。",
            "action": self._collect_fields_action(state, customer, missing_fields),
        }

    def _confirm_create_response(self, state: CustomerMemberPlanningGraphState) -> CustomerMemberPlanningGraphState:
        customer = state.get("selected_customer") or {}
        resolved_member = state.get("resolved_member") or {}
        return {
            "response": (
                f"我识别到要为「{customer.get('account_name')}」添加客户成员"
                f"「{resolved_member.get('user_name') or resolved_member.get('user_id')}」。请确认是否添加？"
            ),
            "action": {
                "action": "create_customer_member",
                "customer": customer,
                "payload": {
                    "customer_id": customer.get("id"),
                    "member": resolved_member,
                },
            },
        }

    def _collect_fields_action(
        self,
        state: CustomerMemberPlanningGraphState,
        customer: JSONDict,
        missing_fields: list[str],
    ) -> JSONDict:
        return {
            "action": "collect_customer_member_fields",
            "customer": customer,
            "payload": {
                "customer_id": customer.get("id"),
                "customer_member": state.get("customer_member") or {},
                "missing_fields": missing_fields,
                "member_candidates": (state.get("business_context") or {}).get("member_candidates"),
            },
        }


def _checkpoint_state_from_input(input_state: CustomerMemberPlanningGraphInput) -> CustomerMemberPlanningGraphState:
    parsed = coerce_json_dict(input_state.get("parsed"))
    member = coerce_json_dict(parsed.get("customer_member"))
    missing_fields = business_rules.missing_customer_member_fields(member)
    return {
        "team_id": int(input_state.get("team_id") or 0),
        "user_id": int(input_state.get("user_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "parsed": parsed,
        "customer_candidates": _json_dict_list(input_state.get("customer_candidates")),
        "business_context": coerce_json_dict(input_state.get("business_context")),
        "customer_name": _optional_string(parsed.get("customer_name")),
        "selected_customer": {},
        "customer_member": member,
        "resolved_member": {},
        "member_error": None,
        "missing_fields": missing_fields,
        "customer_route": None,
        "customer_member_route": None,
        "response": None,
        "action": {},
    }


def _json_dict_list(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    return [coerce_json_dict(item) for item in value if isinstance(item, Mapping)]


def _optional_string(value: JSONValue) -> str | None:
    return value if isinstance(value, str) else None


customer_member_planning_graph_service = CustomerMemberPlanningGraphService(checkpointer=agent_checkpoint_saver)

"""Invoice-title action-planning subgraph for the CRM Agent."""
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
    InvoiceTitlePlanningGraphInput,
    InvoiceTitlePlanningGraphResult,
    InvoiceTitlePlanningGraphState,
    InvoiceTitlePlanningRuntimeContext,
)
from app.services.agent.types import JSONDict, JSONValue, coerce_json_dict


INVOICE_TITLE_CHECKPOINT_NS = "crm_agent_invoice_title"

InvoiceTitleCustomerRoute = Literal[
    "missing_customer_name",
    "single_customer",
    "multiple_customers",
    "customer_not_found",
]
InvoiceTitleBusinessRoute = Literal[
    "collect_fields",
    "confirm_create",
]


def build_invoice_title_thread_id(*, team_id: int, user_id: int, session_id: int) -> str:
    return f"crm_agent_invoice_title:{team_id}:{user_id}:{session_id}"


def build_invoice_title_graph_config(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
) -> RunnableConfig:
    return {
        "configurable": {
                "thread_id": build_invoice_title_thread_id(
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session_id,
                ),
            },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "runtime": "crm_agent_invoice_title",
            "runtime_namespace": INVOICE_TITLE_CHECKPOINT_NS,
        },
    }


class InvoiceTitlePlanningGraphService:
    """Plans invoice-title responses and HITL actions through explicit graph branches."""

    def __init__(self, *, checkpointer: object | None = None) -> None:
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(
            InvoiceTitlePlanningGraphState,
            context_schema=InvoiceTitlePlanningRuntimeContext,
        )
        graph.add_node("derive_customer_route", self._derive_customer_route)
        graph.add_node("missing_customer_name_response", self._missing_customer_name_response)
        graph.add_node("multiple_customers_response", self._multiple_customers_response)
        graph.add_node("customer_not_found_response", self._customer_not_found_response)
        graph.add_node("derive_invoice_title_context", self._derive_invoice_title_context)
        graph.add_node("collect_fields_response", self._collect_fields_response)
        graph.add_node("confirm_create_response", self._confirm_create_response)
        graph.add_edge(START, "derive_customer_route")
        graph.add_conditional_edges(
            "derive_customer_route",
            self._route_after_customer,
            {
                "missing_customer_name": "missing_customer_name_response",
                "single_customer": "derive_invoice_title_context",
                "multiple_customers": "multiple_customers_response",
                "customer_not_found": "customer_not_found_response",
            },
        )
        graph.add_conditional_edges(
            "derive_invoice_title_context",
            self._route_after_invoice_title_context,
            {
                "collect_fields": "collect_fields_response",
                "confirm_create": "confirm_create_response",
            },
        )
        for node_name in [
            "missing_customer_name_response",
            "multiple_customers_response",
            "customer_not_found_response",
            "collect_fields_response",
            "confirm_create_response",
        ]:
            graph.add_edge(node_name, END)
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    async def run(self, input_state: InvoiceTitlePlanningGraphInput) -> InvoiceTitlePlanningGraphResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        context = InvoiceTitlePlanningRuntimeContext(
            team_id=int(input_state.get("team_id") or 0),
            user_id=int(input_state.get("user_id") or 0),
            session_id=int(input_state.get("session_id") or 0),
        )
        config = build_invoice_title_graph_config(
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
                runtime="crm_agent_invoice_title",
                graph=INVOICE_TITLE_CHECKPOINT_NS,
            )

    def _derive_customer_route(
        self,
        state: InvoiceTitlePlanningGraphState,
        runtime: Runtime[InvoiceTitlePlanningRuntimeContext],
    ) -> InvoiceTitlePlanningGraphState:
        candidates = state.get("customer_candidates") or []
        if not state.get("customer_name"):
            return {"customer_route": "missing_customer_name"}
        if len(candidates) == 1:
            return {"customer_route": "single_customer", "selected_customer": candidates[0]}
        if len(candidates) > 1:
            return {"customer_route": "multiple_customers"}
        return {"customer_route": "customer_not_found"}

    def _route_after_customer(self, state: InvoiceTitlePlanningGraphState) -> InvoiceTitleCustomerRoute:
        route = state.get("customer_route")
        if route in {"missing_customer_name", "single_customer", "multiple_customers", "customer_not_found"}:
            return route
        return "customer_not_found"

    def _missing_customer_name_response(self, state: InvoiceTitlePlanningGraphState) -> InvoiceTitlePlanningGraphState:
        return {"response": "我识别到这是创建发票抬头，但还缺少明确客户名称。请补充客户名称。", "action": {}}

    def _multiple_customers_response(self, state: InvoiceTitlePlanningGraphState) -> InvoiceTitlePlanningGraphState:
        candidates = state.get("customer_candidates") or []
        candidate_lines = [
            f"{index}. {customer.get('account_name')}"
            for index, customer in enumerate(candidates, start=1)
        ]
        return {
            "response": "我找到了多个可能的客户，请告诉我要把发票抬头创建到哪一个客户：" + "；".join(candidate_lines),
            "action": {
                "action": "select_customer_for_invoice_title",
                "customers": candidates,
                "payload": {
                    "invoice_title": state.get("invoice_title") or {},
                    "missing_fields": state.get("missing_fields") or [],
                    "set_default": bool(state.get("set_default")),
                },
            },
        }

    def _customer_not_found_response(self, state: InvoiceTitlePlanningGraphState) -> InvoiceTitlePlanningGraphState:
        return {
            "response": business_rules.customer_not_found_response(state.get("customer_name") or ""),
            "action": {},
        }

    def _derive_invoice_title_context(
        self,
        state: InvoiceTitlePlanningGraphState,
        runtime: Runtime[InvoiceTitlePlanningRuntimeContext],
    ) -> InvoiceTitlePlanningGraphState:
        missing_fields = business_rules.missing_invoice_title_fields(state.get("invoice_title") or {})
        return {
            "missing_fields": missing_fields,
            "invoice_title_route": "collect_fields" if missing_fields else "confirm_create",
        }

    def _route_after_invoice_title_context(self, state: InvoiceTitlePlanningGraphState) -> InvoiceTitleBusinessRoute:
        route = state.get("invoice_title_route")
        if route in {"collect_fields", "confirm_create"}:
            return route
        return "collect_fields"

    def _collect_fields_response(self, state: InvoiceTitlePlanningGraphState) -> InvoiceTitlePlanningGraphState:
        customer = state.get("selected_customer") or {}
        missing_fields = state.get("missing_fields") or []
        return {
            "response": (
                f"我识别到要为「{customer.get('account_name')}」创建发票抬头，"
                f"还需要补充：{business_rules.format_invoice_title_missing_fields(missing_fields)}。"
            ),
            "action": {
                "action": "collect_invoice_title_fields",
                "customer": customer,
                "payload": {
                    "customer_id": customer.get("id"),
                    "invoice_title": state.get("invoice_title") or {},
                    "missing_fields": missing_fields,
                    "set_default": bool(state.get("set_default")),
                },
            },
        }

    def _confirm_create_response(self, state: InvoiceTitlePlanningGraphState) -> InvoiceTitlePlanningGraphState:
        customer = state.get("selected_customer") or {}
        invoice_title = state.get("invoice_title") or {}
        return {
            "response": (
                f"我识别到要为「{customer.get('account_name')}」创建发票抬头「{invoice_title.get('title')}」。"
                "请确认是否创建？"
            ),
            "action": {
                "action": "create_invoice_title",
                "customer": customer,
                "payload": {
                    "customer_id": customer.get("id"),
                    "invoice_title": invoice_title,
                    "set_default": bool(state.get("set_default")),
                },
            },
        }


def _checkpoint_state_from_input(input_state: InvoiceTitlePlanningGraphInput) -> InvoiceTitlePlanningGraphState:
    parsed = coerce_json_dict(input_state.get("parsed"))
    invoice_title = coerce_json_dict(parsed.get("invoice_title"))
    set_default = bool(invoice_title.pop("set_default", False))
    missing_fields = business_rules.missing_invoice_title_fields(invoice_title)
    return {
        "team_id": int(input_state.get("team_id") or 0),
        "user_id": int(input_state.get("user_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "parsed": parsed,
        "customer_candidates": _json_dict_list(input_state.get("customer_candidates")),
        "customer_name": _optional_string(parsed.get("customer_name")),
        "selected_customer": {},
        "invoice_title": invoice_title,
        "missing_fields": missing_fields,
        "set_default": set_default,
        "customer_route": None,
        "invoice_title_route": None,
        "response": None,
        "action": {},
    }


def _json_dict_list(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    return [coerce_json_dict(item) for item in value if isinstance(item, Mapping)]


def _optional_string(value: JSONValue) -> str | None:
    return value if isinstance(value, str) else None


invoice_title_planning_graph_service = InvoiceTitlePlanningGraphService(checkpointer=agent_checkpoint_saver)

"""Customer-creation action-planning subgraph for the CRM Agent."""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy.exc import SQLAlchemyError
from typing import Literal

from app.services.agent import business_rules
from app.services.agent.checkpointer import (
    agent_checkpoint_saver,
    is_checkpoint_storage_error,
    with_checkpoint_unavailable_fallback_event,
)
from app.services.agent.state import (
    CustomerCreationPlanningGraphInput,
    CustomerCreationPlanningGraphResult,
    CustomerCreationPlanningGraphState,
    CustomerCreationPlanningRuntimeContext,
)
from app.services.agent.types import coerce_json_dict


CUSTOMER_CREATION_CHECKPOINT_NS = "crm_agent_customer_creation"
CustomerCreateRoute = Literal["collect_fields", "confirm_create"]


def build_customer_creation_thread_id(*, team_id: int, user_id: int, session_id: int) -> str:
    return f"crm_agent_customer_creation:{team_id}:{user_id}:{session_id}"


def build_customer_creation_graph_config(*, team_id: int, user_id: int, session_id: int) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": build_customer_creation_thread_id(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
            ),
        },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "runtime": "crm_agent_customer_creation",
            "runtime_namespace": CUSTOMER_CREATION_CHECKPOINT_NS,
        },
    }


class CustomerCreationPlanningGraphService:
    """Plans customer-creation responses and HITL actions through explicit graph branches."""

    def __init__(self, *, checkpointer: object | None = None) -> None:
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(
            CustomerCreationPlanningGraphState,
            context_schema=CustomerCreationPlanningRuntimeContext,
        )
        graph.add_node("derive_customer_create_context", self._derive_customer_create_context)
        graph.add_node("collect_fields_response", self._collect_fields_response)
        graph.add_node("confirm_create_response", self._confirm_create_response)
        graph.add_edge(START, "derive_customer_create_context")
        graph.add_conditional_edges(
            "derive_customer_create_context",
            self._route_after_customer_create_context,
            {
                "collect_fields": "collect_fields_response",
                "confirm_create": "confirm_create_response",
            },
        )
        graph.add_edge("collect_fields_response", END)
        graph.add_edge("confirm_create_response", END)
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    async def run(self, input_state: CustomerCreationPlanningGraphInput) -> CustomerCreationPlanningGraphResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        context = CustomerCreationPlanningRuntimeContext(
            team_id=int(input_state.get("team_id") or 0),
            user_id=int(input_state.get("user_id") or 0),
            session_id=int(input_state.get("session_id") or 0),
        )
        config = build_customer_creation_graph_config(
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
                runtime="crm_agent_customer_creation",
                graph=CUSTOMER_CREATION_CHECKPOINT_NS,
            )

    def _derive_customer_create_context(
        self,
        state: CustomerCreationPlanningGraphState,
        runtime: Runtime[CustomerCreationPlanningRuntimeContext],
    ) -> CustomerCreationPlanningGraphState:
        missing_fields = business_rules.missing_customer_fields(state.get("customer_create") or {})
        return {
            "missing_fields": missing_fields,
            "customer_create_route": "collect_fields" if missing_fields else "confirm_create",
        }

    def _route_after_customer_create_context(self, state: CustomerCreationPlanningGraphState) -> CustomerCreateRoute:
        return "confirm_create" if state.get("customer_create_route") == "confirm_create" else "collect_fields"

    def _collect_fields_response(self, state: CustomerCreationPlanningGraphState) -> CustomerCreationPlanningGraphState:
        missing_fields = state.get("missing_fields") or []
        return {
            "response": (
                "我识别到要创建客户，"
                f"还需要补充：{business_rules.format_customer_missing_fields(missing_fields)}。"
            ),
            "action": {
                "action": "collect_customer_fields",
                "payload": {
                    "customer": state.get("customer_create") or {},
                    "customer_activity": state.get("customer_activity") or {},
                    "missing_fields": missing_fields,
                },
            },
        }

    def _confirm_create_response(self, state: CustomerCreationPlanningGraphState) -> CustomerCreationPlanningGraphState:
        customer_create = state.get("customer_create") or {}
        contact_name = customer_create.get("contact_name")
        contact_text = f"，主联系人「{contact_name}」" if contact_name else ""
        return {
            "response": (
                "我识别到要创建客户"
                f"「{customer_create.get('account_name')}」{contact_text}。"
                "请确认是否创建？"
            ),
            "action": {
                "action": "create_customer",
                "payload": {
                    "customer": customer_create,
                    "customer_activity": state.get("customer_activity") or {},
                },
            },
        }


def _checkpoint_state_from_input(
    input_state: CustomerCreationPlanningGraphInput,
) -> CustomerCreationPlanningGraphState:
    parsed = coerce_json_dict(input_state.get("parsed"))
    customer_create = coerce_json_dict(parsed.get("customer_create"))
    customer_activity = (
        coerce_json_dict(parsed.get("customer_activity"))
        or coerce_json_dict(parsed.get("customer_follow_up"))
    )
    missing_fields = business_rules.missing_customer_fields(customer_create)
    return {
        "team_id": int(input_state.get("team_id") or 0),
        "user_id": int(input_state.get("user_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "parsed": parsed,
        "customer_create": customer_create,
        "customer_activity": customer_activity,
        "missing_fields": missing_fields,
        "customer_create_route": None,
        "response": None,
        "action": {},
    }


customer_creation_planning_graph_service = CustomerCreationPlanningGraphService(checkpointer=agent_checkpoint_saver)

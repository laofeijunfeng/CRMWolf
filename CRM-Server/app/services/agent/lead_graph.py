"""Lead action-planning subgraph for the CRM Agent."""
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
    LeadPlanningGraphInput,
    LeadPlanningGraphResult,
    LeadPlanningGraphState,
    LeadPlanningRuntimeContext,
)
from app.services.agent.types import coerce_json_dict


LEAD_CHECKPOINT_NS = "crm_agent_lead"
LeadRoute = Literal["collect_fields", "confirm_create"]


def build_lead_thread_id(*, team_id: int, user_id: int, session_id: int) -> str:
    return f"crm_agent_lead:{team_id}:{user_id}:{session_id}"


def build_lead_graph_config(*, team_id: int, user_id: int, session_id: int) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": build_lead_thread_id(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
            ),
        },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "runtime": "crm_agent_lead",
            "runtime_namespace": LEAD_CHECKPOINT_NS,
        },
    }


class LeadPlanningGraphService:
    """Plans lead responses and HITL actions through explicit graph branches."""

    def __init__(self, *, checkpointer: object | None = None) -> None:
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(LeadPlanningGraphState, context_schema=LeadPlanningRuntimeContext)
        graph.add_node("derive_lead_context", self._derive_lead_context)
        graph.add_node("collect_fields_response", self._collect_fields_response)
        graph.add_node("confirm_create_response", self._confirm_create_response)
        graph.add_edge(START, "derive_lead_context")
        graph.add_conditional_edges(
            "derive_lead_context",
            self._route_after_lead_context,
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

    async def run(self, input_state: LeadPlanningGraphInput) -> LeadPlanningGraphResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        context = LeadPlanningRuntimeContext(
            team_id=int(input_state.get("team_id") or 0),
            user_id=int(input_state.get("user_id") or 0),
            session_id=int(input_state.get("session_id") or 0),
        )
        config = build_lead_graph_config(
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
                runtime="crm_agent_lead",
                graph=LEAD_CHECKPOINT_NS,
            )

    def _derive_lead_context(
        self,
        state: LeadPlanningGraphState,
        runtime: Runtime[LeadPlanningRuntimeContext],
    ) -> LeadPlanningGraphState:
        missing_fields = business_rules.missing_lead_fields(state.get("lead") or {})
        return {
            "missing_fields": missing_fields,
            "lead_route": "collect_fields" if missing_fields else "confirm_create",
        }

    def _route_after_lead_context(self, state: LeadPlanningGraphState) -> LeadRoute:
        return "confirm_create" if state.get("lead_route") == "confirm_create" else "collect_fields"

    def _collect_fields_response(self, state: LeadPlanningGraphState) -> LeadPlanningGraphState:
        missing_fields = state.get("missing_fields") or []
        return {
            "response": (
                "我识别到要创建线索，"
                f"还需要补充：{business_rules.format_lead_missing_fields(missing_fields)}。"
            ),
            "action": {
                "action": "collect_lead_fields",
                "payload": {
                    "lead": state.get("lead") or {},
                    "lead_follow_up": state.get("lead_follow_up") or {},
                    "missing_fields": missing_fields,
                },
            },
        }

    def _confirm_create_response(self, state: LeadPlanningGraphState) -> LeadPlanningGraphState:
        lead = state.get("lead") or {}
        return {
            "response": (
                "我识别到要创建线索"
                f"「{lead.get('lead_name')}」，联系人「{lead.get('contact_name')}」，电话「{lead.get('contact_phone')}」。"
                "请确认是否创建？"
            ),
            "action": {
                "action": "create_lead",
                "payload": {
                    "lead": lead,
                    "lead_follow_up": state.get("lead_follow_up") or {},
                },
            },
        }


def _checkpoint_state_from_input(input_state: LeadPlanningGraphInput) -> LeadPlanningGraphState:
    parsed = coerce_json_dict(input_state.get("parsed"))
    lead = coerce_json_dict(parsed.get("lead"))
    missing_fields = business_rules.missing_lead_fields(lead)
    return {
        "team_id": int(input_state.get("team_id") or 0),
        "user_id": int(input_state.get("user_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "parsed": parsed,
        "lead": lead,
        "lead_follow_up": coerce_json_dict(parsed.get("lead_follow_up")),
        "missing_fields": missing_fields,
        "lead_route": None,
        "response": None,
        "action": {},
    }


lead_planning_graph_service = LeadPlanningGraphService(checkpointer=agent_checkpoint_saver)

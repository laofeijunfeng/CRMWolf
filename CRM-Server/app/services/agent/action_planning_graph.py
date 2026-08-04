"""Action-planning domain subgraph for the CRM Agent."""
from __future__ import annotations

import json
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
from app.services.agent.contact_graph import ContactPlanningGraphService
from app.services.agent.customer_activity_graph import CustomerActivityPlanningGraphService
from app.services.agent.customer_creation_graph import CustomerCreationPlanningGraphService
from app.services.agent.customer_member_graph import CustomerMemberPlanningGraphService
from app.services.agent.deployment_info_graph import DeploymentInfoPlanningGraphService
from app.services.agent.invoice_title_graph import InvoiceTitlePlanningGraphService
from app.services.agent.lead_graph import LeadPlanningGraphService
from app.services.agent.opportunity_graph import OpportunityPlanningGraphService
from app.services.agent.payment_record_graph import PaymentRecordPlanningGraphService
from app.services.agent.resource_resolution_graph import ResourceResolutionGraphService
from app.services.agent.schemas import (
    AgentFollowUpQualityResult,
    AgentMemorySnapshot,
    AgentSemanticParseResult,
    AgentSuggestionResult,
)
from app.services.agent.state import (
    ActionPlanningGraphInput,
    ActionPlanningGraphResult,
    ActionPlanningGraphState,
    ActionPlanningRuntimeContext,
)
from app.services.agent.types import JSONDict, JSONValue, coerce_json_dict
from app.services.customer_activity_kinds import get_activity_category, infer_activity_kind


ACTION_PLANNING_CHECKPOINT_NS = "crm_agent_action_planning"

ResponseRoute = Literal[
    "semantic_error",
    "clarification",
    "creation_duplicate",
    "follow_up_quality",
    "business_action",
]
BusinessActionRoute = Literal[
    "customer_activity",
    "create_lead",
    "create_customer",
    "payment_record",
    "create_opportunity",
    "create_contact",
    "create_invoice_title",
    "create_deployment_info",
    "create_customer_member",
    "customer_query",
    "unknown",
]


def build_action_planning_thread_id(*, team_id: int, user_id: int, session_id: int) -> str:
    return f"crm_agent_action_planning:{team_id}:{user_id}:{session_id}"


def build_action_planning_graph_config(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": build_action_planning_thread_id(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
            ),
        },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "runtime": "crm_agent_action_planning",
            "runtime_namespace": ACTION_PLANNING_CHECKPOINT_NS,
        },
    }


class ActionPlanningGraphService:
    """Builds assistant response, HITL event, and final event through a graph."""

    def __init__(
        self,
        *,
        contact_planning_graph: ContactPlanningGraphService | None = None,
        customer_activity_planning_graph: CustomerActivityPlanningGraphService | None = None,
        customer_creation_planning_graph: CustomerCreationPlanningGraphService | None = None,
        customer_member_planning_graph: CustomerMemberPlanningGraphService | None = None,
        deployment_info_planning_graph: DeploymentInfoPlanningGraphService | None = None,
        invoice_title_planning_graph: InvoiceTitlePlanningGraphService | None = None,
        lead_planning_graph: LeadPlanningGraphService | None = None,
        opportunity_planning_graph: OpportunityPlanningGraphService | None = None,
        payment_record_planning_graph: PaymentRecordPlanningGraphService | None = None,
        resource_resolution_graph: ResourceResolutionGraphService | None = None,
        checkpointer: object | None = None,
    ) -> None:
        self.contact_planning_graph = contact_planning_graph or ContactPlanningGraphService(
            checkpointer=checkpointer,
        )
        self.customer_activity_planning_graph = (
            customer_activity_planning_graph
            or CustomerActivityPlanningGraphService(checkpointer=checkpointer)
        )
        self.customer_creation_planning_graph = (
            customer_creation_planning_graph
            or CustomerCreationPlanningGraphService(checkpointer=checkpointer)
        )
        self.customer_member_planning_graph = (
            customer_member_planning_graph
            or CustomerMemberPlanningGraphService(checkpointer=checkpointer)
        )
        self.deployment_info_planning_graph = (
            deployment_info_planning_graph
            or DeploymentInfoPlanningGraphService(checkpointer=checkpointer)
        )
        self.invoice_title_planning_graph = (
            invoice_title_planning_graph
            or InvoiceTitlePlanningGraphService(checkpointer=checkpointer)
        )
        self.lead_planning_graph = lead_planning_graph or LeadPlanningGraphService(
            checkpointer=checkpointer,
        )
        self.opportunity_planning_graph = opportunity_planning_graph or OpportunityPlanningGraphService(
            checkpointer=checkpointer,
        )
        self.payment_record_planning_graph = payment_record_planning_graph or PaymentRecordPlanningGraphService(
            checkpointer=checkpointer,
        )
        self.resource_resolution_graph = resource_resolution_graph or ResourceResolutionGraphService(
            checkpointer=checkpointer,
        )
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(ActionPlanningGraphState, context_schema=ActionPlanningRuntimeContext)
        graph.add_node("collect_trace_events", self._collect_trace_events)
        graph.add_node("route_response", self._route_response)
        graph.add_node("semantic_error_response", self._semantic_error_response)
        graph.add_node("clarification_response", self._clarification_response)
        graph.add_node("creation_duplicate_response", self._creation_duplicate_response)
        graph.add_node("follow_up_quality_response", self._follow_up_quality_response)
        graph.add_node("route_business_action", self._route_business_action)
        graph.add_node("customer_activity_action", self._customer_activity_action)
        graph.add_node("create_lead_action", self._create_lead_action)
        graph.add_node("create_customer_action", self._create_customer_action)
        graph.add_node("payment_record_action", self._payment_record_action)
        graph.add_node("create_opportunity_action", self._create_opportunity_action)
        graph.add_node("create_contact_action", self._create_contact_action)
        graph.add_node("create_invoice_title_action", self._create_invoice_title_action)
        graph.add_node("create_deployment_info_action", self._create_deployment_info_action)
        graph.add_node("create_customer_member_action", self._create_customer_member_action)
        graph.add_node("unknown_business_action", self._unknown_business_action)
        graph.add_node("apply_business_suggestions", self._apply_business_suggestions)
        graph.add_node("emit_business_interaction_event", self._emit_business_interaction_event)
        graph.add_node("finalize_response", self._finalize_response)
        graph.add_edge(START, "collect_trace_events")
        graph.add_edge("collect_trace_events", "route_response")
        graph.add_conditional_edges(
            "route_response",
            self._route_after_response_guard,
            {
                "semantic_error": "semantic_error_response",
                "clarification": "clarification_response",
                "creation_duplicate": "creation_duplicate_response",
                "follow_up_quality": "follow_up_quality_response",
                "business_action": "route_business_action",
            },
        )
        graph.add_edge("semantic_error_response", "finalize_response")
        graph.add_edge("clarification_response", "finalize_response")
        graph.add_edge("creation_duplicate_response", "finalize_response")
        graph.add_edge("follow_up_quality_response", "finalize_response")
        graph.add_conditional_edges(
            "route_business_action",
            self._route_after_business_action_guard,
            {
                "customer_activity": "customer_activity_action",
                "create_lead": "create_lead_action",
                "create_customer": "create_customer_action",
                "payment_record": "payment_record_action",
                "create_opportunity": "create_opportunity_action",
                "create_contact": "create_contact_action",
                "create_invoice_title": "create_invoice_title_action",
                "create_deployment_info": "create_deployment_info_action",
                "create_customer_member": "create_customer_member_action",
                "customer_query": "apply_business_suggestions",
                "unknown": "unknown_business_action",
            },
        )
        graph.add_edge("customer_activity_action", "apply_business_suggestions")
        graph.add_edge("create_lead_action", "apply_business_suggestions")
        graph.add_edge("create_customer_action", "apply_business_suggestions")
        graph.add_edge("payment_record_action", "apply_business_suggestions")
        graph.add_edge("create_opportunity_action", "apply_business_suggestions")
        graph.add_edge("create_contact_action", "apply_business_suggestions")
        graph.add_edge("create_invoice_title_action", "apply_business_suggestions")
        graph.add_edge("create_deployment_info_action", "apply_business_suggestions")
        graph.add_edge("create_customer_member_action", "apply_business_suggestions")
        graph.add_edge("unknown_business_action", "apply_business_suggestions")
        graph.add_edge("apply_business_suggestions", "emit_business_interaction_event")
        graph.add_edge("emit_business_interaction_event", "finalize_response")
        graph.add_edge("finalize_response", END)
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    async def run(self, input_state: ActionPlanningGraphInput) -> ActionPlanningGraphResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        context = _runtime_context_from_input(input_state)
        config = build_action_planning_graph_config(
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
                runtime="crm_agent_action_planning",
                graph=ACTION_PLANNING_CHECKPOINT_NS,
            )

    def _collect_trace_events(
        self,
        state: ActionPlanningGraphState,
        runtime: Runtime[ActionPlanningRuntimeContext],
    ) -> ActionPlanningGraphState:
        reset_event: JSONDict = {"event": "action_planning_events_started"}
        if state.get("suppress_trace_events"):
            return {"events": [reset_event]}

        events: list[JSONDict] = [
            reset_event,
            {"event": "intent", "intent": state.get("intent") or "UNKNOWN"},
        ]
        semantic_result = runtime.context.semantic_result
        if semantic_result:
            events.extend(_semantic_trace_events(state, semantic_result))

        suggestion_result = runtime.context.suggestion_result
        if state.get("business_context"):
            events.append({
                "event": "business_context_loaded",
                "customer_id": (state.get("selected_customer") or {}).get("id"),
                "customer": state.get("selected_customer"),
            })
        if suggestion_result:
            events.extend(_suggestion_trace_events(state, suggestion_result))
        if runtime.context.follow_up_quality_result or state.get("follow_up_quality_error"):
            events.extend(_follow_up_quality_trace_events(state, runtime.context.follow_up_quality_result))
        elif state.get("suggestion_error"):
            events.extend(_suggestion_error_events(state))

        events.extend(state.get("prior_events") or [])
        return {"events": events}

    def _route_response(
        self,
        state: ActionPlanningGraphState,
        runtime: Runtime[ActionPlanningRuntimeContext],
    ) -> ActionPlanningGraphState:
        semantic_result = runtime.context.semantic_result
        route = _response_route(
            state,
            semantic_result=semantic_result,
            memory=runtime.context.memory,
            follow_up_quality_result=runtime.context.follow_up_quality_result,
        )
        return {"response_route": route}

    def _route_after_response_guard(self, state: ActionPlanningGraphState) -> ResponseRoute:
        route = state.get("response_route")
        if route in {
            "semantic_error",
            "clarification",
            "creation_duplicate",
            "follow_up_quality",
            "business_action",
        }:
            return route
        return "business_action"

    def _semantic_error_response(self, state: ActionPlanningGraphState) -> ActionPlanningGraphState:
        return {"response": state.get("semantic_error") or "语义理解失败，请稍后重试。"}

    def _clarification_response(
        self,
        state: ActionPlanningGraphState,
        runtime: Runtime[ActionPlanningRuntimeContext],
    ) -> ActionPlanningGraphState:
        semantic_result = runtime.context.semantic_result
        response = (
            semantic_result.clarification_question
            if semantic_result and semantic_result.clarification_question
            else "我还不能可靠理解你的诉求，请补充客户名称、业务内容或要执行的动作。"
        )
        event: JSONDict = {
            "event": "clarification_required",
            "intent": state.get("intent") or "UNKNOWN",
            "content": response,
            "semantic": coerce_json_dict(semantic_result.model_dump(exclude_none=True)) if semantic_result else None,
        }
        return {"response": response, "events": [event]}

    def _creation_duplicate_response(self, state: ActionPlanningGraphState) -> ActionPlanningGraphState:
        duplicate_candidates = state.get("creation_duplicate_candidates") or {}
        response = business_rules.build_creation_duplicate_response(duplicate_candidates)
        return {
            "response": response,
            "events": [{
                "event": "creation_duplicate_detected",
                "intent": state.get("intent") or "UNKNOWN",
                "customers": _json_list_value(duplicate_candidates.get("customers")),
                "leads": _json_list_value(duplicate_candidates.get("leads")),
                "hidden_customer_count": _int_json_value(duplicate_candidates.get("hidden_customer_count")),
                "hidden_lead_count": _int_json_value(duplicate_candidates.get("hidden_lead_count")),
                "content": response,
            }],
        }

    def _follow_up_quality_response(
        self,
        state: ActionPlanningGraphState,
        runtime: Runtime[ActionPlanningRuntimeContext],
    ) -> ActionPlanningGraphState:
        quality = runtime.context.follow_up_quality_result
        if not quality:
            return {"response": "这条跟进还差一点关键信息，请补充后我再帮你记录。"}
        parsed = state.get("parsed") or {}
        response = quality.supplement_question or "这条跟进还差一点关键信息，请补充后我再帮你记录。"
        selected_customer = state.get("selected_customer") or {}
        return {
            "response": response,
            "events": [{
                "event": "follow_up_quality_required",
                "action": "collect_follow_up_quality_fields",
                "content": response,
                "score": quality.score,
                "reason": quality.reason,
                "missing_aspects": quality.missing_aspects,
                "customer": selected_customer,
                "payload": {
                    "customer_id": selected_customer.get("id"),
                    "content": parsed.get("follow_up_content"),
                    "source_content": parsed.get("original_content") or parsed.get("follow_up_content"),
                    "method": parsed.get("method") or "AI录入",
                    "next_action": parsed.get("next_action"),
                    "next_follow_time_text": parsed.get("next_follow_time_text"),
                    "next_follow_time_iso": parsed.get("next_follow_time_iso"),
                    "quality": coerce_json_dict(quality.model_dump(exclude_none=True)),
                },
            }],
        }

    def _route_business_action(self, state: ActionPlanningGraphState) -> ActionPlanningGraphState:
        return {"business_action_route": _business_action_route(state.get("intent") or "UNKNOWN")}

    def _route_after_business_action_guard(self, state: ActionPlanningGraphState) -> BusinessActionRoute:
        route = state.get("business_action_route")
        if route in {
            "customer_activity",
            "create_lead",
            "create_customer",
            "payment_record",
            "create_opportunity",
            "create_contact",
            "create_invoice_title",
            "create_deployment_info",
            "create_customer_member",
            "customer_query",
            "unknown",
        }:
            return route
        return "unknown"

    async def _customer_activity_action(
        self,
        state: ActionPlanningGraphState,
        runtime: Runtime[ActionPlanningRuntimeContext],
    ) -> ActionPlanningGraphState:
        parsed = _apply_follow_up_revision(state.get("parsed") or {}, runtime.context.follow_up_quality_result)
        result = await self.customer_activity_planning_graph.run({
            "team_id": state.get("team_id") or 0,
            "user_id": state.get("user_id") or 0,
            "session_id": state.get("session_id") or 0,
            "parsed": parsed,
            "customer_candidates": _resolved_customer_candidates(state),
        })
        return {
            "response": result.get("response") or "",
            "action": coerce_json_dict(result.get("action")),
        }

    async def _create_lead_action(
        self,
        state: ActionPlanningGraphState,
        runtime: Runtime[ActionPlanningRuntimeContext],
    ) -> ActionPlanningGraphState:
        parsed = _apply_follow_up_revision(state.get("parsed") or {}, runtime.context.follow_up_quality_result)
        result = await self.lead_planning_graph.run({
            "team_id": state.get("team_id") or 0,
            "user_id": state.get("user_id") or 0,
            "session_id": state.get("session_id") or 0,
            "parsed": parsed,
        })
        return {
            "response": result.get("response") or "",
            "action": coerce_json_dict(result.get("action")),
        }

    async def _create_customer_action(
        self,
        state: ActionPlanningGraphState,
        runtime: Runtime[ActionPlanningRuntimeContext],
    ) -> ActionPlanningGraphState:
        parsed = _apply_follow_up_revision(state.get("parsed") or {}, runtime.context.follow_up_quality_result)
        result = await self.customer_creation_planning_graph.run({
            "team_id": state.get("team_id") or 0,
            "user_id": state.get("user_id") or 0,
            "session_id": state.get("session_id") or 0,
            "parsed": parsed,
        })
        return {
            "response": result.get("response") or "",
            "action": coerce_json_dict(result.get("action")),
        }

    async def _payment_record_action(
        self,
        state: ActionPlanningGraphState,
        runtime: Runtime[ActionPlanningRuntimeContext],
    ) -> ActionPlanningGraphState:
        parsed = _apply_follow_up_revision(state.get("parsed") or {}, runtime.context.follow_up_quality_result)
        result = await self.payment_record_planning_graph.run({
            "team_id": state.get("team_id") or 0,
            "user_id": state.get("user_id") or 0,
            "session_id": state.get("session_id") or 0,
            "parsed": parsed,
            "customer_candidates": _resolved_customer_candidates(state),
            "business_context": state.get("business_context") or {},
        })
        return {
            "response": result.get("response") or "",
            "action": coerce_json_dict(result.get("action")),
        }

    async def _create_opportunity_action(
        self,
        state: ActionPlanningGraphState,
        runtime: Runtime[ActionPlanningRuntimeContext],
    ) -> ActionPlanningGraphState:
        parsed = _apply_follow_up_revision(state.get("parsed") or {}, runtime.context.follow_up_quality_result)
        result = await self.opportunity_planning_graph.run({
            "team_id": state.get("team_id") or 0,
            "user_id": state.get("user_id") or 0,
            "session_id": state.get("session_id") or 0,
            "parsed": parsed,
            "customer_candidates": _resolved_customer_candidates(state),
        })
        return {
            "response": result.get("response") or "",
            "action": coerce_json_dict(result.get("action")),
        }

    async def _create_contact_action(
        self,
        state: ActionPlanningGraphState,
        runtime: Runtime[ActionPlanningRuntimeContext],
    ) -> ActionPlanningGraphState:
        parsed = _apply_follow_up_revision(state.get("parsed") or {}, runtime.context.follow_up_quality_result)
        result = await self.contact_planning_graph.run({
            "team_id": state.get("team_id") or 0,
            "user_id": state.get("user_id") or 0,
            "session_id": state.get("session_id") or 0,
            "parsed": parsed,
            "customer_candidates": _resolved_customer_candidates(state),
        })
        return {
            "response": result.get("response") or "",
            "action": coerce_json_dict(result.get("action")),
        }

    async def _create_invoice_title_action(
        self,
        state: ActionPlanningGraphState,
        runtime: Runtime[ActionPlanningRuntimeContext],
    ) -> ActionPlanningGraphState:
        parsed = _apply_follow_up_revision(state.get("parsed") or {}, runtime.context.follow_up_quality_result)
        result = await self.invoice_title_planning_graph.run({
            "team_id": state.get("team_id") or 0,
            "user_id": state.get("user_id") or 0,
            "session_id": state.get("session_id") or 0,
            "parsed": parsed,
            "customer_candidates": _resolved_customer_candidates(state),
        })
        return {
            "response": result.get("response") or "",
            "action": coerce_json_dict(result.get("action")),
        }

    async def _create_deployment_info_action(
        self,
        state: ActionPlanningGraphState,
        runtime: Runtime[ActionPlanningRuntimeContext],
    ) -> ActionPlanningGraphState:
        parsed = _apply_follow_up_revision(state.get("parsed") or {}, runtime.context.follow_up_quality_result)
        result = await self.deployment_info_planning_graph.run({
            "team_id": state.get("team_id") or 0,
            "user_id": state.get("user_id") or 0,
            "session_id": state.get("session_id") or 0,
            "parsed": parsed,
            "customer_candidates": _resolved_customer_candidates(state),
        })
        return {
            "response": result.get("response") or "",
            "action": coerce_json_dict(result.get("action")),
        }

    async def _create_customer_member_action(
        self,
        state: ActionPlanningGraphState,
        runtime: Runtime[ActionPlanningRuntimeContext],
    ) -> ActionPlanningGraphState:
        parsed = _apply_follow_up_revision(state.get("parsed") or {}, runtime.context.follow_up_quality_result)
        result = await self.customer_member_planning_graph.run({
            "team_id": state.get("team_id") or 0,
            "user_id": state.get("user_id") or 0,
            "session_id": state.get("session_id") or 0,
            "parsed": parsed,
            "customer_candidates": _resolved_customer_candidates(state),
            "business_context": state.get("business_context") or {},
        })
        return {
            "response": result.get("response") or "",
            "action": coerce_json_dict(result.get("action")),
        }

    def _unknown_business_action(
        self,
        state: ActionPlanningGraphState,
        runtime: Runtime[ActionPlanningRuntimeContext],
    ) -> ActionPlanningGraphState:
        return {"response": "我还不能可靠理解这条消息，请补充客户名称、业务内容或你希望我执行的动作。", "action": {}}

    async def _apply_business_suggestions(
        self,
        state: ActionPlanningGraphState,
        runtime: Runtime[ActionPlanningRuntimeContext],
    ) -> ActionPlanningGraphState:
        suggestions = runtime.context.suggestion_result.suggestions if runtime.context.suggestion_result else []
        response = state.get("response") or ""
        action = coerce_json_dict(state.get("action"))
        parsed = _apply_follow_up_revision(
            state.get("parsed") or {},
            runtime.context.follow_up_quality_result,
        )
        stage_move_action = business_rules.stage_move_action_from_suggestions(
            suggestions,
            state.get("selected_customer") or {},
            state.get("business_context") or {},
        )
        stage_move_selection_action = business_rules.stage_move_selection_action_from_suggestions(
            suggestions,
            state.get("selected_customer") or {},
            state.get("business_context") or {},
        )
        resolution_events: list[JSONDict] = []
        if stage_move_selection_action:
            stage_move_selection_action, resolution_events = await self._resolve_stage_move_selection(
                state,
                runtime,
                stage_move_selection_action,
            )
        opportunity_next_task = business_rules.opportunity_next_task_from_suggestions(
            suggestions,
            parsed,
            state.get("selected_customer") or {},
        )

        if runtime.context.suggestion_result and not action and state.get("intent") != "CUSTOMER_QUERY":
            response = business_rules.append_suggestions_to_response(response, suggestions)

        stage_move = coerce_json_dict(stage_move_action)
        next_task = coerce_json_dict(opportunity_next_task)
        if state.get("intent") != "CUSTOMER_QUERY":
            if stage_move:
                if action.get("action") == "create_customer_activity":
                    _attach_next_task(action, stage_move)
                elif not action:
                    action = stage_move
                    payload = _json_dict_value(stage_move.get("payload"))
                    target_stage_name = _string_value(payload.get("target_stage_name"))
                    response = (
                        f"我识别到这次跟进可能已经推进了商机阶段"
                        f"{f'到「{target_stage_name}」' if target_stage_name else ''}。"
                        "请确认是否推进？"
                    )
            elif stage_move_selection_action:
                stage_selection = coerce_json_dict(stage_move_selection_action)
                if action.get("action") == "create_customer_activity":
                    _attach_next_task(action, stage_selection)
                elif not action:
                    action = stage_selection
                    response = _string_value(stage_selection.get("content")) or response
            elif next_task and action.get("action") == "create_customer_activity":
                _attach_next_task(action, next_task)

        return {
            "response": response,
            "action": action,
            "events": resolution_events,
        }

    async def _resolve_stage_move_selection(
        self,
        state: ActionPlanningGraphState,
        runtime: Runtime[ActionPlanningRuntimeContext],
        selection_action: dict[str, object],
    ) -> tuple[dict[str, object], list[JSONDict]]:
        candidates = business_rules.context_items(selection_action.get("opportunities"))
        if len(candidates) < 2:
            return selection_action, []
        raw_payload = selection_action.get("payload")
        payload = business_rules.drop_empty_values(raw_payload if isinstance(raw_payload, dict) else {})
        target_stage_name = payload.get("target_stage_name")
        resolution = await self.resource_resolution_graph.run({
            "team_id": runtime.context.team_id,
            "user_id": runtime.context.user_id,
            "session_id": runtime.context.session_id,
            "resource_kind": "opportunity",
            "action_name": "move_opportunity_stage",
            "content": str(state.get("content") or ""),
            "target": {
                "target_stage_name": target_stage_name,
                "stage_template_id": payload.get("stage_template_id"),
                "suggestion_title": payload.get("suggestion_title"),
                "suggestion_reason": payload.get("suggestion_reason"),
            },
            "candidates": candidates,
        })
        resolution_events = [
            coerce_json_dict(event)
            for event in resolution.get("events", [])
            if isinstance(event, dict)
        ]
        if resolution.get("resolution_status") != "selected":
            return selection_action, resolution_events
        selected = coerce_json_dict(resolution.get("selected_candidate"))
        if not selected:
            return selection_action, resolution_events
        stage_suggestion = next(
            (
                suggestion
                for suggestion in runtime.context.suggestion_result.suggestions
                if suggestion.action == "MOVE_OPPORTUNITY_STAGE"
            ),
            None,
        )
        if stage_suggestion is None:
            return selection_action, resolution_events
        stage_move_action = business_rules.stage_move_action_from_candidate(
            stage_suggestion=stage_suggestion,
            customer=state.get("selected_customer") or {},
            candidate=selected,
        )
        return stage_move_action or selection_action, resolution_events

    def _emit_business_interaction_event(self, state: ActionPlanningGraphState) -> ActionPlanningGraphState:
        action = coerce_json_dict(state.get("action"))
        update: ActionPlanningGraphState = {"action": action}
        if action:
            _attach_hitl_auto_execute_candidate(action, state)
            update["events"] = [{"event": _interaction_event_name(action), **action}]
        return update

    def _finalize_response(self, state: ActionPlanningGraphState) -> ActionPlanningGraphState:
        content_format = "text"
        if state.get("intent") == "CUSTOMER_QUERY" and not coerce_json_dict(state.get("action")):
            response = state.get("response") or _customer_query_context_response(state)
            content_format = "markdown"
        else:
            response = (
                state.get("response")
                or "我还不能可靠理解这条消息，请补充客户名称、业务内容或你希望我执行的动作。"
            )
        return {
            "response": response,
            "events": [{
                "event": "final",
                "intent": state.get("intent") or "UNKNOWN",
                "content": response,
                "content_format": content_format,
                "tool_execution_enabled": False,
            }],
        }


def _customer_query_context_response(state: ActionPlanningGraphState) -> str:
    business_context = coerce_json_dict(state.get("business_context"))
    if not business_context:
        return _customer_query_unresolved_response(state)

    customer = coerce_json_dict(business_context.get("customer")) or coerce_json_dict(state.get("selected_customer"))
    customer_name = _display_text(customer.get("account_name")) or _display_text(customer.get("name")) or "该客户"
    lines = [f"已读取「{customer_name}」的客户档案和业务上下文。", ""]

    profile_parts = []
    industry = _display_text(coerce_json_dict(customer.get("industry_info")).get("name")) or _display_text(customer.get("industry"))
    city = _display_text(customer.get("city"))
    company_scale = _display_text(customer.get("company_scale"))
    source = _display_text(customer.get("source"))
    if industry:
        profile_parts.append(f"行业：{industry}")
    if city:
        profile_parts.append(f"城市：{city}")
    if company_scale:
        profile_parts.append(f"规模：{company_scale}")
    if source:
        profile_parts.append(f"来源：{source}")
    if profile_parts:
        lines.append(f"- **基础档案**：{'；'.join(profile_parts)}。")

    brief = _customer_brief(customer)
    background = (
        _brief_content(brief, "overview", "enterprise_background")
        or _display_text(customer.get("company_background"))
        or _display_text(customer.get("main_business"))
    )
    if background:
        lines.append(f"- **业务背景**：{_truncate_sentence(background, 120)}")

    project_background = (
        _brief_content(brief, "overview", "project_need_background")
        or _display_text(customer.get("project_background"))
    )
    if project_background:
        lines.append(f"- **需求背景**：{_truncate_sentence(project_background, 140)}")

    contacts = _customer_contacts(customer)
    if contacts:
        contact_parts = []
        for contact in contacts[:3]:
            name = _display_text(contact.get("name")) or "未命名联系人"
            role_parts = []
            if contact.get("is_primary"):
                role_parts.append("主联系人")
            if contact.get("is_decision_maker"):
                role_parts.append("决策人")
            position = _display_text(contact.get("position"))
            if position:
                role_parts.append(position)
            mobile = _display_text(contact.get("mobile"))
            suffix = f"（{'，'.join(role_parts)}）" if role_parts else ""
            phone = f"，电话 {mobile}" if mobile else ""
            contact_parts.append(f"{name}{suffix}{phone}")
        lines.append(f"- **联系人**：{'；'.join(contact_parts)}。")

    opportunities = business_rules.context_items(business_context.get("opportunities"))
    if opportunities:
        opportunity_parts = []
        for opportunity in opportunities[:3]:
            name = _display_text(opportunity.get("opportunity_name")) or _display_text(opportunity.get("name")) or "未命名商机"
            stage = _display_text(opportunity.get("stage_name")) or _display_text(opportunity.get("current_stage_name"))
            amount = _display_amount(opportunity.get("expected_amount") or opportunity.get("amount"))
            close_date = _display_text(opportunity.get("expected_close_date") or opportunity.get("expected_deal_date"))
            detail = name
            if stage:
                detail += f"，阶段：{stage}"
            if amount:
                detail += f"，预计金额：{amount}"
            if close_date:
                detail += f"，预计成交：{close_date}"
            opportunity_parts.append(detail)
        lines.append(f"- **商机进展**：{'；'.join(opportunity_parts)}。")

    lines.extend(_customer_query_record_sections(business_context, customer))

    recent_progress = _brief_content(brief, "overview", "follow_up_progress") or _latest_activity_content(
        business_context.get("customer_activities")
    )
    if recent_progress:
        lines.append(f"- **最近进展**：{_truncate_sentence(recent_progress, 160)}")

    next_step = _brief_content(brief, "next_best_actions", "summary") or _next_action_from_activities(
        business_context.get("customer_activities")
    )
    if next_step:
        lines.append(f"- **下一步建议**：{_truncate_sentence(next_step, 140)}")
    else:
        lines.append("- **下一步建议**：围绕最近跟进结论确认采购、技术或商务侧的明确推进节点，并同步更新客户活动。")

    return "\n".join(lines)


def _customer_query_record_sections(business_context: JSONDict, customer: JSONDict) -> list[str]:
    return [
        _contracts_line(business_context.get("contracts")),
        _payment_plans_line(business_context.get("payment_plans")),
        _invoice_titles_line(business_context.get("invoice_titles")),
        _deployment_infos_line(business_context.get("deployment_infos")),
        _license_line(customer, business_context.get("contracts")),
    ]


def _contracts_line(value: object) -> str:
    error = _context_error(value)
    if error:
        return f"- **合同**：读取失败，原因：{_truncate_sentence(error, 80)}。"
    contracts = _context_records(value)
    if not contracts:
        return "- **合同**：暂无已读取到的合同记录。"
    parts = []
    for contract in contracts[:3]:
        name = _display_text(contract.get("contract_name")) or _display_text(contract.get("contract_number")) or "未命名合同"
        status = _display_text(contract.get("status"))
        amount = _display_amount(contract.get("total_amount"))
        expiry = _display_text(contract.get("expiry_date"))
        detail = name
        if status:
            detail += f"，状态：{status}"
        if amount:
            detail += f"，金额：{amount}"
        if expiry:
            detail += f"，到期：{expiry}"
        parts.append(detail)
    return f"- **合同**：{'；'.join(parts)}。"


def _payment_plans_line(value: object) -> str:
    error = _context_error(value)
    if error:
        return f"- **回款**：读取失败，原因：{_truncate_sentence(error, 80)}。"
    plans = _context_records(value)
    if not plans:
        return "- **回款**：暂无已读取到的回款计划。"
    parts = []
    for plan in plans[:3]:
        name = _display_text(plan.get("plan_name")) or _display_text(plan.get("payment_stage")) or "回款计划"
        amount = _display_amount(plan.get("planned_amount") or plan.get("amount"))
        date_text = _display_text(plan.get("planned_date") or plan.get("due_date"))
        status = _display_text(plan.get("status"))
        detail = name
        if amount:
            detail += f"，金额：{amount}"
        if date_text:
            detail += f"，计划日期：{date_text}"
        if status:
            detail += f"，状态：{status}"
        parts.append(detail)
    return f"- **回款**：{'；'.join(parts)}。"


def _invoice_titles_line(value: object) -> str:
    error = _context_error(value)
    if error:
        return f"- **发票**：读取失败，原因：{_truncate_sentence(error, 80)}。"
    titles = _context_records(value)
    if not titles:
        return "- **发票**：暂无已读取到的发票抬头。"
    parts = []
    for title in titles[:3]:
        name = _display_text(title.get("company_name")) or _display_text(title.get("title_name")) or "发票抬头"
        tax_no = _display_text(title.get("tax_number") or title.get("tax_no"))
        detail = name
        if tax_no:
            detail += f"，税号：{tax_no}"
        parts.append(detail)
    return f"- **发票**：{'；'.join(parts)}。"


def _deployment_infos_line(value: object) -> str:
    error = _context_error(value)
    if error:
        return f"- **部署**：读取失败，原因：{_truncate_sentence(error, 80)}。"
    deployments = _context_records(value)
    if not deployments:
        return "- **部署**：暂无已读取到的部署信息。"
    parts = []
    for deployment in deployments[:3]:
        name = _display_text(deployment.get("environment_name")) or _display_text(deployment.get("name")) or "部署信息"
        url = _display_text(deployment.get("server_url") or deployment.get("access_url"))
        detail = name
        if url:
            detail += f"，地址：{url}"
        parts.append(detail)
    return f"- **部署**：{'；'.join(parts)}。"


def _license_line(customer: JSONDict, contracts_value: object) -> str:
    license_type = _display_text(customer.get("license_type"))
    license_expiry = _display_text(customer.get("license_expiry_date"))
    if license_type or license_expiry:
        parts = []
        if license_type:
            parts.append(f"类型：{license_type}")
        if license_expiry:
            parts.append(f"到期：{license_expiry}")
        return f"- **License**：{'；'.join(parts)}。"
    contracts = _context_records(contracts_value)
    license_parts = []
    for contract in contracts[:3]:
        contract_license_type = _display_text(contract.get("license_type"))
        contract_expiry = _display_text(contract.get("license_expiry_date") or contract.get("expiry_date"))
        if contract_license_type or contract_expiry:
            name = _display_text(contract.get("contract_name")) or _display_text(contract.get("contract_number")) or "合同"
            detail = name
            if contract_license_type:
                detail += f"，类型：{contract_license_type}"
            if contract_expiry:
                detail += f"，到期：{contract_expiry}"
            license_parts.append(detail)
    if license_parts:
        return f"- **License**：{'；'.join(license_parts)}。"
    return "- **License**：暂无已读取到的 License 类型或到期信息。"


def _response_route(
    state: ActionPlanningGraphState,
    *,
    semantic_result: AgentSemanticParseResult | None,
    memory: AgentMemorySnapshot | None,
    follow_up_quality_result: AgentFollowUpQualityResult | None,
) -> ResponseRoute:
    intent = state.get("intent") or "UNKNOWN"
    if state.get("semantic_error"):
        return "semantic_error"
    if semantic_result and _requires_clarification(
        semantic_result,
        has_memory_customer=bool(_memory_current_customer(memory)),
    ):
        return "clarification"
    duplicate_candidates = state.get("creation_duplicate_candidates") or {}
    if intent in {"CREATE_LEAD", "CREATE_CUSTOMER"} and _has_duplicate_candidates(duplicate_candidates):
        return "creation_duplicate"
    if follow_up_quality_result and not follow_up_quality_result.passed:
        return "follow_up_quality"
    return "business_action"


def _business_action_route(intent: str) -> BusinessActionRoute:
    routes: dict[str, BusinessActionRoute] = {
        "CUSTOMER_ACTIVITY": "customer_activity",
        "CREATE_LEAD": "create_lead",
        "CREATE_CUSTOMER": "create_customer",
        "PAYMENT_RECORD": "payment_record",
        "CREATE_OPPORTUNITY": "create_opportunity",
        "CREATE_CONTACT": "create_contact",
        "CREATE_INVOICE_TITLE": "create_invoice_title",
        "CREATE_DEPLOYMENT_INFO": "create_deployment_info",
        "CREATE_CUSTOMER_MEMBER": "create_customer_member",
        "CUSTOMER_QUERY": "customer_query",
    }
    return routes.get(intent, "unknown")


def _customer_query_unresolved_response(state: ActionPlanningGraphState) -> str:
    selected_customer = coerce_json_dict(state.get("selected_customer"))
    if selected_customer.get("id"):
        return ""
    search_events = [
        *(state.get("events") or []),
        *(state.get("prior_events") or []),
    ]
    if _has_failed_customer_search(search_events):
        return "客户搜索暂时失败，当前无法读取客户情况。请稍后再试。"
    parsed = coerce_json_dict(state.get("parsed"))
    customer_name = parsed.get("customer_name")
    if isinstance(customer_name, str) and customer_name.strip():
        return f"我没能确定「{customer_name.strip()}」对应的客户。请补充客户全称或更多线索。"
    return "我没能确定你要查询的客户。请补充客户全称或更多线索。"


def _resolved_customer_candidates(state: ActionPlanningGraphState) -> list[JSONDict]:
    selected_customer = coerce_json_dict(state.get("selected_customer"))
    if selected_customer.get("id"):
        business_customer = coerce_json_dict(coerce_json_dict(state.get("business_context")).get("customer"))
        if _same_customer_identity(selected_customer, business_customer):
            return [{**business_customer, **selected_customer}]
        return [selected_customer]
    return _json_dict_list(state.get("customer_candidates"))


def _same_customer_identity(left: JSONDict, right: JSONDict) -> bool:
    if not left or not right:
        return False
    left_ids = {
        str(value)
        for value in (left.get("id"), left.get("public_id"))
        if value not in (None, "")
    }
    right_ids = {
        str(value)
        for value in (right.get("id"), right.get("public_id"))
        if value not in (None, "")
    }
    return bool(left_ids & right_ids)


def _customer_brief(customer: JSONDict) -> JSONDict:
    raw = customer.get("customer_brief_json")
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return coerce_json_dict(loaded)


def _brief_content(brief: JSONDict, section: str, key: str) -> str | None:
    value = coerce_json_dict(coerce_json_dict(brief.get(section)).get(key)).get("content")
    return _display_text(value)


def _customer_contacts(customer: JSONDict) -> list[JSONDict]:
    contacts = customer.get("contacts")
    if isinstance(contacts, list):
        return [coerce_json_dict(contact) for contact in contacts if isinstance(contact, Mapping)]
    return []


def _latest_activity_content(value: object) -> str | None:
    activities = business_rules.context_items(value)
    if not activities and isinstance(value, list):
        activities = [coerce_json_dict(item) for item in value if isinstance(item, Mapping)]
    for activity in activities:
        content = (
            _display_text(activity.get("content"))
            or _display_text(activity.get("summary"))
            or _display_text(activity.get("title"))
        )
        if content:
            return content
    return None


def _next_action_from_activities(value: object) -> str | None:
    activities = business_rules.context_items(value)
    if not activities and isinstance(value, list):
        activities = [coerce_json_dict(item) for item in value if isinstance(item, Mapping)]
    for activity in activities:
        next_action = _display_text(activity.get("next_action"))
        if next_action:
            return next_action
    return None


def _context_records(value: object) -> list[JSONDict]:
    if isinstance(value, list):
        return [coerce_json_dict(item) for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        items = value.get("items")
        if isinstance(items, list):
            return [coerce_json_dict(item) for item in items if isinstance(item, Mapping)]
    return []


def _context_error(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    error = value.get("error") or value.get("message")
    return _display_text(error)


def _display_text(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _display_amount(value: object) -> str | None:
    if isinstance(value, (int, float)):
        return f"{value:g}"
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _truncate_sentence(value: str, limit: int) -> str:
    stripped = " ".join(value.split())
    if len(stripped) <= limit:
        return stripped
    return stripped[:limit].rstrip("，。；,; ") + "..."


def _has_failed_customer_search(events: list[JSONDict]) -> bool:
    for event in events:
        if event.get("event") != "tool_result":
            continue
        if event.get("tool_name") == "search_customers" and event.get("success") is False:
            return True
    return False


def _semantic_trace_events(
    state: ActionPlanningGraphState,
    semantic_result: AgentSemanticParseResult,
) -> list[JSONDict]:
    metadata = state.get("semantic_metadata") or {}
    return [{
        "event": "semantic_parsed",
        "intent": semantic_result.intent,
        "confidence": semantic_result.intent_confidence,
        "parse_source": metadata.get("parse_source"),
        "model": metadata.get("model"),
        "fallback_reason": metadata.get("fallback_reason"),
        "fallback_error": metadata.get("fallback_error"),
        "need_clarification": semantic_result.need_clarification,
        "parsed": state.get("parsed") or {},
    }]


def _suggestion_trace_events(
    state: ActionPlanningGraphState,
    suggestion_result: AgentSuggestionResult,
) -> list[JSONDict]:
    metadata = state.get("suggestion_metadata") or {}
    return [{
        "event": "business_suggestions",
        "summary": suggestion_result.summary,
        "suggestions": [
            coerce_json_dict(suggestion.model_dump(exclude_none=True))
            for suggestion in suggestion_result.suggestions
        ],
        "need_user_choice": suggestion_result.need_user_choice,
        "clarification_question": suggestion_result.clarification_question,
        "suggestion_source": metadata.get("suggestion_source"),
        "model": metadata.get("model"),
        "structured_output_strategy": metadata.get("structured_output_strategy"),
        "fallback_reason": metadata.get("fallback_reason"),
        "fallback_error": metadata.get("fallback_error"),
        "fallback_error_message": metadata.get("fallback_error_message"),
    }]


def _suggestion_error_events(state: ActionPlanningGraphState) -> list[JSONDict]:
    error = state.get("suggestion_error")
    return [{"event": "suggestion_failed", "message": error}] if isinstance(error, str) else []


def _follow_up_quality_trace_events(
    state: ActionPlanningGraphState,
    quality: AgentFollowUpQualityResult | None,
) -> list[JSONDict]:
    if quality:
        metadata = state.get("follow_up_quality_metadata") or {}
        return [{
            "event": "follow_up_quality_evaluated",
            "score": quality.score,
            "passed": quality.passed,
            "reason": quality.reason,
            "missing_aspects": quality.missing_aspects,
            "quality_source": metadata.get("quality_source"),
            "model": metadata.get("model"),
            "fallback_reason": metadata.get("fallback_reason"),
            "fallback_error": metadata.get("fallback_error"),
        }]
    error = state.get("follow_up_quality_error")
    return [{"event": "follow_up_quality_failed", "message": error}] if isinstance(error, str) else []


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
            and semantic_result.intent != "CUSTOMER_QUERY"
            and semantic_result.intent not in {"CREATE_LEAD", "CREATE_CUSTOMER"}
            and not customer_from_memory
            and semantic_result.customer.confidence < 0.7
        )
    )


def _memory_current_customer(memory: AgentMemorySnapshot | None) -> JSONDict | None:
    context = memory.session_context if memory else None
    if not isinstance(context, Mapping):
        return None
    customer = context.get("current_customer")
    if isinstance(customer, Mapping) and customer.get("id") and customer.get("account_name"):
        return coerce_json_dict(customer)
    return None


def _has_duplicate_candidates(duplicate_candidates: JSONDict) -> bool:
    return bool(
        duplicate_candidates.get("customers")
        or duplicate_candidates.get("leads")
        or duplicate_candidates.get("hidden_customer_count")
        or duplicate_candidates.get("hidden_lead_count")
    )


def _apply_follow_up_revision(
    parsed: JSONDict,
    quality: AgentFollowUpQualityResult | None,
) -> JSONDict:
    revision = (quality.suggested_revision or "").strip() if quality else ""
    if not revision:
        return parsed
    activity_kind = infer_activity_kind(
        parsed.get("method") or "AI录入",
        parsed.get("original_content") or parsed.get("follow_up_content") or "",
    )
    if get_activity_category(activity_kind) == "MEETING":
        return parsed
    return {**parsed, "follow_up_content": revision}


def _has_deferred_next_task(action: JSONDict) -> bool:
    payload = action.get("payload")
    return isinstance(payload, dict) and isinstance(payload.get("_next_task"), dict)


def _attach_next_task(action: JSONDict, next_task: JSONDict) -> None:
    payload = action.get("payload")
    if not isinstance(payload, dict):
        payload = {}
        action["payload"] = payload
    payload["_next_task"] = next_task


def _attach_hitl_auto_execute_candidate(action: JSONDict, state: ActionPlanningGraphState) -> None:
    if action.get("action") not in {"create_customer_activity", "create_lead_follow_up"}:
        return
    semantic = coerce_json_dict(state.get("semantic"))
    raw_confidence = semantic.get("intent_confidence")
    intent_confidence = float(raw_confidence) if isinstance(raw_confidence, (int, float)) else 0.0
    payload = action.get("payload")
    if not isinstance(payload, dict):
        return
    if intent_confidence >= 0.88 and _payload_has_follow_up_target_and_content(action.get("action"), payload):
        action["hitl_auto_execute_candidate"] = True
        payload["hitl_auto_execute_candidate"] = True


def _payload_has_follow_up_target_and_content(action: object, payload: dict[str, object]) -> bool:
    if action == "create_customer_activity" and not payload.get("customer_id"):
        return False
    if action == "create_lead_follow_up" and not payload.get("lead_id"):
        return False
    for key in ("content", "source_content", "follow_up_content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _interaction_event_name(action: JSONDict) -> str:
    action_name = action.get("action")
    if action_name in {
        "select_customer_for_activity",
        "select_customer_for_contact",
        "select_customer_for_invoice_title",
        "select_customer_for_deployment_info",
        "select_customer_for_customer_member",
        "select_customer_for_payment_record",
        "select_customer_for_opportunity",
    }:
        return "customer_selection_required"
    if action_name == "collect_contact_fields":
        return "contact_fields_required"
    if action_name == "collect_opportunity_fields":
        return "opportunity_fields_required"
    if action_name == "collect_invoice_title_fields":
        return "invoice_title_fields_required"
    if action_name == "collect_deployment_info_fields":
        return "deployment_info_fields_required"
    if action_name == "collect_customer_member_fields":
        return "customer_member_fields_required"
    if action_name == "collect_payment_fields":
        return "payment_fields_required"
    if action_name == "collect_lead_fields":
        return "lead_fields_required"
    if action_name == "collect_customer_fields":
        return "customer_fields_required"
    if action_name in {"select_contract_for_payment_plan", "select_payment_plan_for_record", "select_opportunity_for_stage_move"}:
        return "business_selection_required"
    return "confirmation_required"


def _checkpoint_state_from_input(input_state: ActionPlanningGraphInput) -> ActionPlanningGraphState:
    state: ActionPlanningGraphState = {
        "team_id": int(input_state.get("team_id") or 0),
        "user_id": int(input_state.get("user_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "content": str(input_state.get("content") or ""),
        "intent": input_state.get("intent") or "UNKNOWN",
        "parsed": coerce_json_dict(input_state.get("parsed")),
        "customer_candidates": _json_dict_list(input_state.get("customer_candidates")),
        "selected_customer": _optional_json_dict(input_state.get("selected_customer")),
        "business_context": coerce_json_dict(input_state.get("business_context")),
        "semantic": coerce_json_dict(input_state.get("semantic")),
        "semantic_metadata": coerce_json_dict(input_state.get("semantic_metadata")),
        "semantic_error": _optional_string(input_state.get("semantic_error")),
        "follow_up_quality": coerce_json_dict(input_state.get("follow_up_quality")),
        "follow_up_quality_metadata": coerce_json_dict(input_state.get("follow_up_quality_metadata")),
        "follow_up_quality_error": _optional_string(input_state.get("follow_up_quality_error")),
        "creation_duplicate_candidates": coerce_json_dict(input_state.get("creation_duplicate_candidates")),
        "suggestion": coerce_json_dict(input_state.get("suggestion")),
        "suggestion_metadata": coerce_json_dict(input_state.get("suggestion_metadata")),
        "suggestion_error": _optional_string(input_state.get("suggestion_error")),
        "prior_events": _json_dict_list(input_state.get("events")),
        "suppress_trace_events": bool(input_state.get("suppress_trace_events")),
        "response_route": None,
        "business_action_route": None,
        "response": None,
        "action": {},
        "events": [],
    }
    return state


def _runtime_context_from_input(input_state: ActionPlanningGraphInput) -> ActionPlanningRuntimeContext:
    memory = input_state.get("memory")
    semantic_result = input_state.get("semantic_result")
    follow_up_quality_result = input_state.get("follow_up_quality_result")
    suggestion_result = input_state.get("suggestion_result")
    return ActionPlanningRuntimeContext(
        team_id=int(input_state.get("team_id") or 0),
        user_id=int(input_state.get("user_id") or 0),
        session_id=int(input_state.get("session_id") or 0),
        memory=memory if isinstance(memory, AgentMemorySnapshot) else None,
        semantic_result=semantic_result if isinstance(semantic_result, AgentSemanticParseResult) else None,
        follow_up_quality_result=(
            follow_up_quality_result
            if isinstance(follow_up_quality_result, AgentFollowUpQualityResult)
            else None
        ),
        suggestion_result=suggestion_result if isinstance(suggestion_result, AgentSuggestionResult) else None,
    )


def _json_dict_list(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    return [coerce_json_dict(item) for item in value if isinstance(item, Mapping)]


def _optional_json_dict(value: object) -> JSONDict | None:
    if isinstance(value, Mapping):
        return coerce_json_dict(value)
    return None


def _json_dict_value(value: JSONValue) -> JSONDict:
    return value if isinstance(value, dict) else {}


def _json_list_value(value: JSONValue) -> list[JSONValue]:
    return value if isinstance(value, list) else []


def _int_json_value(value: JSONValue) -> int:
    if isinstance(value, int):
        return value
    return 0


def _string_value(value: JSONValue) -> str | None:
    return value if isinstance(value, str) else None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


action_planning_graph_service = ActionPlanningGraphService(checkpointer=agent_checkpoint_saver)

"""CRM AI Agent response construction."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from app.services.agent.schemas import AgentFollowUpQualityResult
from app.services.agent.state import AgentGraphState


class AgentResponseBuilder:
    def __init__(
        self,
        *,
        requires_clarification: Callable[..., bool],
        memory_current_customer: Callable[[Optional[Any]], Optional[Dict[str, Any]]],
        follow_up_quality_blocks: Callable[[AgentGraphState], bool],
        apply_follow_up_revision: Callable[[Dict[str, Any], Optional[AgentFollowUpQualityResult]], Dict[str, Any]],
        build_creation_duplicate_response: Callable[[Dict[str, Any]], str],
        build_business_response: Callable[[str, Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]], Any],
        stage_move_action_from_suggestions: Callable[[List[Any], Dict[str, Any], Dict[str, Any]], Optional[Dict[str, Any]]],
        opportunity_next_task_from_suggestions: Callable[[List[Any], Dict[str, Any], Dict[str, Any]], Optional[Dict[str, Any]]],
        append_suggestions_to_response: Callable[[str, List[Any]], str],
        has_deferred_next_task: Callable[[Optional[Dict[str, Any]]], bool],
    ) -> None:
        self._requires_clarification = requires_clarification
        self._memory_current_customer = memory_current_customer
        self._follow_up_quality_blocks = follow_up_quality_blocks
        self._apply_follow_up_revision = apply_follow_up_revision
        self._build_creation_duplicate_response = build_creation_duplicate_response
        self._build_business_response = build_business_response
        self._stage_move_action_from_suggestions = stage_move_action_from_suggestions
        self._opportunity_next_task_from_suggestions = opportunity_next_task_from_suggestions
        self._append_suggestions_to_response = append_suggestions_to_response
        self._has_deferred_next_task = has_deferred_next_task

    def build(self, state: AgentGraphState) -> AgentGraphState:
        intent = state.get("intent") or "UNKNOWN"
        semantic_result = state.get("semantic_result")
        parsed = state.get("parsed") or {}
        candidates = state.get("customer_candidates") or []
        suppress_trace_events = bool(state.get("suppress_trace_events"))
        events = [] if suppress_trace_events else [{"event": "intent", "intent": intent}]

        if semantic_result and not suppress_trace_events:
            events.extend(self.build_semantic_trace_events(state)[1:])

        suggestion_result = state.get("suggestion_result")
        if state.get("business_context") and not suppress_trace_events:
            events.append({
                "event": "business_context_loaded",
                "customer_id": (state.get("selected_customer") or {}).get("id"),
                "customer": state.get("selected_customer"),
            })
        if not suppress_trace_events:
            if suggestion_result:
                events.extend(self.build_suggestion_trace_events(state))
            if state.get("follow_up_quality_result") or state.get("follow_up_quality_error"):
                events.extend(self.build_follow_up_quality_trace_events(state))
            elif state.get("suggestion_error"):
                events.extend(self.build_suggestion_trace_events(state))

        if state.get("events") and not suppress_trace_events:
            events.extend(state["events"])

        if state.get("semantic_error"):
            response = state["semantic_error"]
            events.append({"event": "final", "intent": intent, "content": response, "tool_execution_enabled": False})
            return {"response": response, "events": events}

        if self._requires_clarification(
            semantic_result,
            has_memory_customer=bool(self._memory_current_customer(state.get("memory"))),
        ):
            response = semantic_result.clarification_question or "我还不能可靠理解你的诉求，请补充客户名称、业务内容或要执行的动作。"
            events.append({
                "event": "clarification_required",
                "intent": intent,
                "content": response,
                "semantic": semantic_result.model_dump(exclude_none=True) if semantic_result else None,
            })
            events.append({"event": "final", "intent": intent, "content": response, "tool_execution_enabled": False})
            return {"response": response, "events": events}

        duplicate_candidates = state.get("creation_duplicate_candidates") or {}
        if intent in {"CREATE_LEAD", "CREATE_CUSTOMER"} and (
            duplicate_candidates.get("customers") or duplicate_candidates.get("leads")
            or duplicate_candidates.get("hidden_customer_count") or duplicate_candidates.get("hidden_lead_count")
        ):
            response = self._build_creation_duplicate_response(duplicate_candidates)
            events.append({
                "event": "creation_duplicate_detected",
                "intent": intent,
                "customers": duplicate_candidates.get("customers") or [],
                "leads": duplicate_candidates.get("leads") or [],
                "hidden_customer_count": duplicate_candidates.get("hidden_customer_count") or 0,
                "hidden_lead_count": duplicate_candidates.get("hidden_lead_count") or 0,
                "content": response,
            })
            events.append({"event": "final", "intent": intent, "content": response, "tool_execution_enabled": False})
            return {"response": response, "events": events}

        follow_up_quality_result = state.get("follow_up_quality_result")
        response, action = self._build_business_response(
            intent,
            self._apply_follow_up_revision(parsed, follow_up_quality_result),
            candidates,
            state.get("business_context") or {},
        )
        if self._follow_up_quality_blocks(state):
            quality = state["follow_up_quality_result"]
            response = quality.supplement_question or "这条跟进还差一点关键信息，请补充后我再帮你记录。"
            events.append({
                "event": "follow_up_quality_required",
                "action": "collect_follow_up_quality_fields",
                "content": response,
                "score": quality.score,
                "reason": quality.reason,
                "missing_aspects": quality.missing_aspects,
                "customer": state.get("selected_customer"),
                "payload": {
                    "customer_id": (state.get("selected_customer") or {}).get("id"),
                    "content": parsed.get("follow_up_content"),
                    "method": parsed.get("method") or "AI录入",
                    "next_action": parsed.get("next_action"),
                    "next_follow_time_text": parsed.get("next_follow_time_text"),
                    "next_follow_time_iso": parsed.get("next_follow_time_iso"),
                    "quality": quality.model_dump(exclude_none=True),
                },
            })
            events.append({"event": "final", "intent": intent, "content": response, "tool_execution_enabled": False})
            return {"response": response, "events": events}

        suggestions = suggestion_result.suggestions if suggestion_result else []
        stage_move_action = self._stage_move_action_from_suggestions(
            suggestions,
            state.get("selected_customer") or {},
            state.get("business_context") or {},
        )
        opportunity_next_task = self._opportunity_next_task_from_suggestions(
            suggestions,
            parsed,
            state.get("selected_customer") or {},
        )
        if suggestion_result and not action and not self._has_deferred_next_task(action):
            response = self._append_suggestions_to_response(response, suggestions)
        if stage_move_action:
            if action and action.get("action") == "create_customer_follow_up":
                action.setdefault("payload", {})["_next_task"] = stage_move_action
            elif not action:
                action = stage_move_action
                target_stage_name = stage_move_action["payload"].get("target_stage_name")
                response = (
                    f"我识别到这次跟进可能已经推进了商机阶段"
                    f"{f'到「{target_stage_name}」' if target_stage_name else ''}。"
                    "请确认是否推进？"
                )
        elif opportunity_next_task and action and action.get("action") == "create_customer_follow_up":
            action.setdefault("payload", {})["_next_task"] = opportunity_next_task
        if action:
            events.append({"event": self.interaction_event_name(action), **action})
        events.append({
            "event": "final",
            "intent": intent,
            "content": response,
            "tool_execution_enabled": False,
        })
        return {"response": response, "events": events}

    @staticmethod
    def build_semantic_trace_events(state: AgentGraphState) -> List[Dict[str, Any]]:
        semantic_result = state.get("semantic_result")
        if not semantic_result:
            return []
        semantic_metadata = state.get("semantic_metadata") or {}
        return [
            {"event": "intent", "intent": semantic_result.intent},
            {
                "event": "semantic_parsed",
                "intent": semantic_result.intent,
                "confidence": semantic_result.intent_confidence,
                "parse_source": semantic_metadata.get("parse_source"),
                "model": semantic_metadata.get("model"),
                "fallback_reason": semantic_metadata.get("fallback_reason"),
                "fallback_error": semantic_metadata.get("fallback_error"),
                "need_clarification": semantic_result.need_clarification,
                "parsed": state.get("parsed") or {},
            },
        ]

    @staticmethod
    def build_suggestion_trace_events(state: AgentGraphState) -> List[Dict[str, Any]]:
        suggestion_result = state.get("suggestion_result")
        if suggestion_result:
            suggestion_metadata = state.get("suggestion_metadata") or {}
            return [{
                "event": "business_suggestions",
                "summary": suggestion_result.summary,
                "suggestions": [
                    suggestion.model_dump(exclude_none=True)
                    for suggestion in suggestion_result.suggestions
                ],
                "need_user_choice": suggestion_result.need_user_choice,
                "clarification_question": suggestion_result.clarification_question,
                "suggestion_source": suggestion_metadata.get("suggestion_source"),
                "model": suggestion_metadata.get("model"),
                "fallback_reason": suggestion_metadata.get("fallback_reason"),
                "fallback_error": suggestion_metadata.get("fallback_error"),
            }]
        if state.get("suggestion_error"):
            return [{"event": "suggestion_failed", "message": state["suggestion_error"]}]
        return []

    @staticmethod
    def build_follow_up_quality_trace_events(state: AgentGraphState) -> List[Dict[str, Any]]:
        quality = state.get("follow_up_quality_result")
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
        if state.get("follow_up_quality_error"):
            return [{"event": "follow_up_quality_failed", "message": state["follow_up_quality_error"]}]
        return []

    @staticmethod
    def interaction_event_name(action: Dict[str, Any]) -> str:
        action_name = action.get("action")
        if action_name in {
            "select_customer_for_follow_up",
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
        if action_name in {"select_contract_for_payment_plan", "select_payment_plan_for_record"}:
            return "business_selection_required"
        return "confirmation_required"

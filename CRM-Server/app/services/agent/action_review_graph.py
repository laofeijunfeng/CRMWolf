"""LangGraph subgraph for risk-aware HITL action review."""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy.exc import SQLAlchemyError

from app.services.agent.checkpointer import (
    agent_checkpoint_saver,
    is_checkpoint_storage_error,
    with_checkpoint_unavailable_fallback_event,
)
from app.services.agent.state import (
    ActionReviewDecision,
    ActionReviewGraphInput,
    ActionReviewGraphResult,
    ActionReviewGraphState,
    ActionReviewRiskLevel,
    ActionReviewRuntimeContext,
    internal_graph_start_event,
    visible_graph_events,
)
from app.services.agent.types import JSONDict, coerce_json_dict


ACTION_REVIEW_CHECKPOINT_NS = "crm_agent_action_review"

_SELECTION_EVENTS = frozenset({
    "customer_selection_required",
    "business_selection_required",
})

_FIELD_EVENTS = frozenset({
    "contact_fields_required",
    "invoice_title_fields_required",
    "deployment_info_fields_required",
    "customer_member_fields_required",
    "payment_fields_required",
    "lead_fields_required",
    "customer_fields_required",
    "opportunity_fields_required",
    "follow_up_quality_required",
})

_LOW_RISK_ACTIONS = frozenset({
    "create_customer_activity",
    "create_lead_follow_up",
})

_MEDIUM_RISK_ACTIONS = frozenset({
    "move_opportunity_stage",
    "create_contact",
    "create_opportunity",
    "create_deployment_info",
})

_HIGH_RISK_ACTIONS = frozenset({
    "create_payment_record",
    "create_payment_plan",
    "create_invoice_title",
    "create_customer",
    "create_customer_member",
    "create_lead",
})


class ActionReviewGraphService:
    """Reviews write-action events before the runtime decides to interrupt."""

    def __init__(self, *, checkpointer: object | None = agent_checkpoint_saver) -> None:
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(ActionReviewGraphState, context_schema=ActionReviewRuntimeContext)
        graph.add_node("normalize_action_event", self._normalize_action_event)
        graph.add_node("classify_action_risk", self._classify_action_risk)
        graph.add_node("score_execution_confidence", self._score_execution_confidence)
        graph.add_node("apply_hitl_policy", self._apply_hitl_policy)
        graph.add_node("finish_review", self._finish_review)
        graph.add_edge(START, "normalize_action_event")
        graph.add_edge("normalize_action_event", "classify_action_risk")
        graph.add_edge("classify_action_risk", "score_execution_confidence")
        graph.add_edge("score_execution_confidence", "apply_hitl_policy")
        graph.add_edge("apply_hitl_policy", "finish_review")
        graph.add_edge("finish_review", END)
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    async def run(self, input_state: ActionReviewGraphInput) -> ActionReviewGraphResult:
        state = _checkpoint_state_from_input(input_state)
        context = ActionReviewRuntimeContext(
            team_id=input_state.get("team_id", 0),
            user_id=input_state.get("user_id", 0),
            session_id=input_state.get("session_id", 0),
        )
        config = build_action_review_graph_config(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            event=state.get("event", {}),
        )
        try:
            graph = self._graph if self._checkpoint_enabled else self._fallback_graph
            return _with_visible_events(await graph.ainvoke(state, config, context=context))
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            result = _with_visible_events(await self._fallback_graph.ainvoke(state, config, context=context))
            return with_checkpoint_unavailable_fallback_event(
                result,
                runtime="crm_agent_action_review",
                graph=ACTION_REVIEW_CHECKPOINT_NS,
            )

    def _normalize_action_event(self, state: ActionReviewGraphState) -> ActionReviewGraphState:
        event = coerce_json_dict(state.get("event"))
        action = event.get("action")
        payload = event.get("payload")
        normalized_action = action if isinstance(action, str) else ""
        normalized_payload = coerce_json_dict(payload)
        return {
            "event": event,
            "action": normalized_action,
            "payload": normalized_payload,
            "events": [{
                "event": "action_review_started",
                "action": normalized_action,
                "source_event": event.get("event"),
            }],
        }

    def _classify_action_risk(self, state: ActionReviewGraphState) -> ActionReviewGraphState:
        event = state.get("event", {})
        event_name = event.get("event")
        action = state.get("action", "")
        if event_name in _SELECTION_EVENTS:
            risk_level: ActionReviewRiskLevel = "medium"
        elif event_name in _FIELD_EVENTS:
            risk_level = "medium"
        elif action in _LOW_RISK_ACTIONS:
            risk_level = "low"
        elif action in _HIGH_RISK_ACTIONS:
            risk_level = "high"
        elif action in _MEDIUM_RISK_ACTIONS:
            risk_level = "medium"
        else:
            risk_level = "high"
        return {
            "risk_level": risk_level,
            "events": [{
                "event": "action_review_risk_classified",
                "risk_level": risk_level,
            }],
        }

    def _score_execution_confidence(self, state: ActionReviewGraphState) -> ActionReviewGraphState:
        event = state.get("event", {})
        event_name = event.get("event")
        payload = state.get("payload", {})
        action = state.get("action", "")
        if event_name in _SELECTION_EVENTS or event_name in _FIELD_EVENTS:
            confidence = 0.0
        else:
            confidence = _base_confidence_for_action(action, payload)
            confidence = min(confidence, _payload_confidence(payload))
        return {
            "execution_confidence": confidence,
            "events": [{
                "event": "action_review_confidence_scored",
                "execution_confidence": confidence,
            }],
        }

    def _apply_hitl_policy(
        self,
        state: ActionReviewGraphState,
        runtime: Runtime[ActionReviewRuntimeContext],
    ) -> ActionReviewGraphState:
        event = state.get("event", {})
        event_name = event.get("event")
        risk_level = state.get("risk_level", "high")
        confidence = state.get("execution_confidence", 0.0)
        if event_name in _SELECTION_EVENTS:
            decision: ActionReviewDecision = "require_choice"
            reason = "resource_choice_required"
        elif event_name in _FIELD_EVENTS:
            decision = "require_fields"
            reason = "required_fields_missing"
        elif (
            _is_auto_execute_candidate(event)
            and risk_level == "low"
            and confidence >= runtime.context.low_risk_auto_execute_threshold
        ):
            decision = "auto_execute"
            reason = "low_risk_high_confidence"
        elif not state.get("action"):
            decision = "block"
            reason = "missing_action"
        else:
            decision = "require_confirmation"
            reason = "confirmation_required_by_policy"
        return {
            "decision": decision,
            "reason": reason,
            "events": [{
                "event": "action_review_decided",
                "decision": decision,
                "risk_level": risk_level,
                "execution_confidence": confidence,
                "reason": reason,
            }],
        }

    def _finish_review(self, state: ActionReviewGraphState) -> ActionReviewGraphState:
        return {
            "events": [{
                "event": "action_review_finished",
                "decision": state.get("decision"),
            }],
        }


def build_action_review_thread_id(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    action: str,
) -> str:
    action_key = action or "action"
    return f"crm_agent_action_review:{team_id}:{user_id}:{session_id}:{action_key}"


def build_action_review_graph_config(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    event: JSONDict,
) -> RunnableConfig:
    action = event.get("action")
    action_key = action if isinstance(action, str) else "action"
    return {
        "configurable": {
            "thread_id": build_action_review_thread_id(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                action=action_key,
            ),
        },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "action": action_key,
            "runtime": "crm_agent_action_review",
            "runtime_namespace": ACTION_REVIEW_CHECKPOINT_NS,
        },
    }


def _checkpoint_state_from_input(input_state: ActionReviewGraphInput) -> ActionReviewGraphState:
    return {
        "team_id": input_state.get("team_id", 0),
        "user_id": input_state.get("user_id", 0),
        "session_id": input_state.get("session_id", 0),
        "event": coerce_json_dict(input_state.get("event")),
        "events": [
            internal_graph_start_event("action_review_graph_invocation_started"),
            *list(input_state.get("events", [])),
        ],
    }


def _with_visible_events(result: ActionReviewGraphResult) -> ActionReviewGraphResult:
    projected: ActionReviewGraphResult = dict(result)
    projected["events"] = visible_graph_events(projected.get("events"))
    return projected


def _base_confidence_for_action(action: str, payload: JSONDict) -> float:
    if action == "create_customer_activity":
        return 0.96 if _has_customer_id(payload) and _has_follow_up_content(payload) else 0.55
    if action == "create_lead_follow_up":
        return 0.94 if payload.get("lead_id") and _has_follow_up_content(payload) else 0.55
    return 0.72


def _is_auto_execute_candidate(event: JSONDict) -> bool:
    marker = event.get("hitl_auto_execute_candidate")
    if marker is True:
        return True
    payload = coerce_json_dict(event.get("payload"))
    return payload.get("hitl_auto_execute_candidate") is True


def _payload_confidence(payload: JSONDict) -> float:
    raw_confidence = payload.get("resolution_confidence")
    if isinstance(raw_confidence, (int, float)):
        return max(0.0, min(float(raw_confidence), 1.0))
    raw_confidence = payload.get("suggestion_confidence")
    if isinstance(raw_confidence, (int, float)):
        return max(0.0, min(float(raw_confidence), 1.0))
    return 1.0


def _has_customer_id(payload: JSONDict) -> bool:
    customer_id = payload.get("customer_id")
    return isinstance(customer_id, int) or (isinstance(customer_id, str) and customer_id.strip().isdigit())


def _has_follow_up_content(payload: JSONDict) -> bool:
    for key in ("content", "source_content", "follow_up_content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


action_review_graph_service = ActionReviewGraphService(checkpointer=agent_checkpoint_saver)

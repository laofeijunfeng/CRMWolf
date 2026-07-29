"""LangGraph orchestration for turns with a waiting task."""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.crud.agent import agent_task_crud
from app.models.agent import AgentTaskStatus
from app.services.agent import agent_copy
from app.services.agent import pending_tasks
from app.services.agent.pending_tasks import (
    PendingTaskInteractionPlanner,
    PendingTaskPreflightPlanner,
    pending_task_interaction_planner,
    pending_task_preflight_planner,
)
from app.services.agent.state import PendingTaskGraphState


class PendingTaskGraphService:
    """Runs pending-task routing as a small business state machine."""

    state_change_confidence_threshold = 0.75

    def __init__(
        self,
        *,
        preflight_planner: PendingTaskPreflightPlanner | None = None,
        interaction_planner: PendingTaskInteractionPlanner | None = None,
    ) -> None:
        self.preflight_planner = preflight_planner or pending_task_preflight_planner
        self.interaction_planner = interaction_planner or pending_task_interaction_planner
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(PendingTaskGraphState)
        graph.add_node("load_suspended_candidates", self._load_suspended_candidates)
        graph.add_node("classify_turn_relation", self._classify_turn_relation)
        graph.add_node("apply_turn_relation", self._apply_turn_relation)
        graph.add_node("preflight", self._preflight)
        graph.add_node("plan_interaction", self._plan_interaction)
        graph.add_edge(START, "load_suspended_candidates")
        graph.add_conditional_edges(
            "load_suspended_candidates",
            self._route_after_load_suspended_candidates,
            {
                "classify": "classify_turn_relation",
                "preflight": "preflight",
                "end": END,
            },
        )
        graph.add_edge("classify_turn_relation", "apply_turn_relation")
        graph.add_conditional_edges(
            "apply_turn_relation",
            self._route_after_apply_turn_relation,
            {
                "preflight": "preflight",
                "interaction": "plan_interaction",
                "end": END,
            },
        )
        graph.add_conditional_edges(
            "preflight",
            self._route_after_preflight,
            {
                "interaction": "plan_interaction",
                "end": END,
            },
        )
        graph.add_edge("plan_interaction", END)
        return graph.compile()

    async def run(self, input_state: PendingTaskGraphState) -> PendingTaskGraphState:
        return await self._graph.ainvoke(input_state)

    def _load_suspended_candidates(self, state: PendingTaskGraphState) -> PendingTaskGraphState:
        if state.get("task"):
            return {}
        candidates = pending_tasks.session_state._suspended_task_snapshots(
            state["db"],
            state["session"],
            state["team_id"],
            state["user_id"],
        )
        events = []
        if candidates:
            events.append({
                "event": "suspended_tasks_loaded",
                "task_ids": [candidate.get("id") for candidate in candidates],
            })
        return {"suspended_candidates": candidates, "events": events}

    def _route_after_load_suspended_candidates(self, state: PendingTaskGraphState) -> str:
        if state.get("task"):
            return "preflight"
        if state.get("suspended_candidates"):
            return "classify"
        return "end"

    async def _classify_turn_relation(self, state: PendingTaskGraphState) -> PendingTaskGraphState:
        selected_task_id = state["turn_input"].metadata.get("selected_task_id")
        if selected_task_id is not None:
            try:
                selected_task_id = int(selected_task_id)
            except (TypeError, ValueError):
                selected_task_id = None
        if selected_task_id is not None:
            decision = pending_tasks.session_state.AgentTurnRelationDecision(
                relation="RESUME_SUSPENDED_DRAFT",
                confidence=1.0,
                target_task_id=selected_task_id,
                reason="用户通过结构化草稿选择控件选择了要恢复的草稿。",
            )
            return {
                "turn_relation_decision": decision,
                "events": [{
                    "event": "turn_relation_classified",
                    "relation": decision.relation,
                    "confidence": decision.confidence,
                    "target_task_id": decision.target_task_id,
                    "detected_customer_name": decision.detected_customer_name,
                    "detected_intent": decision.detected_intent,
                    "reason": decision.reason,
                    "source": "interaction_metadata",
                }],
            }

        decision = await pending_tasks.session_state._assess_turn_relation(
            state["db"],
            team_id=state["team_id"],
            user_id=state["user_id"],
            session=state["session"],
            task=state.get("task"),
            user_message=state.get("content", ""),
        )
        return {
            "turn_relation_decision": decision,
            "events": [{
                "event": "turn_relation_classified",
                "relation": decision.relation,
                "confidence": decision.confidence,
                "target_task_id": decision.target_task_id,
                "detected_customer_name": decision.detected_customer_name,
                "detected_intent": decision.detected_intent,
                "reason": decision.reason,
            }],
        }

    def _apply_turn_relation(self, state: PendingTaskGraphState) -> PendingTaskGraphState:
        decision = state.get("turn_relation_decision")
        if not decision:
            return {}

        if decision.relation == "ASK_USER":
            return self._turn_relation_clarification(state, decision)

        if decision.relation not in {"RESUME_SUSPENDED_DRAFT", "PATCH_ACTIVE_DRAFT", "CONTINUE_ACTIVE_TASK"}:
            return {}

        target_task_id = decision.target_task_id
        if not target_task_id:
            return self._turn_relation_clarification(state, decision)
        if decision.confidence < self.state_change_confidence_threshold:
            return self._turn_relation_clarification(state, decision)

        candidate_ids = {
            int(candidate["id"])
            for candidate in state.get("suspended_candidates") or []
            if isinstance(candidate, dict) and candidate.get("id") is not None
        }
        if state.get("task") and getattr(state["task"], "id", None) is not None:
            candidate_ids.add(int(state["task"].id))
        if int(target_task_id) not in candidate_ids:
            return self._turn_relation_clarification(state, decision)

        task = agent_task_crud.get_by_id(
            state["db"],
            target_task_id,
            team_id=state["team_id"],
            user_id=state["user_id"],
        )
        if not task or task.status != AgentTaskStatus.SUSPENDED:
            return {}

        task = pending_tasks.session_state._resume_suspended_task(
            state["db"],
            state["session"],
            task,
        )
        return {
            "task": task,
            "resumed_task": task,
            "events": [{
                "event": "suspended_task_resumed",
                "task_id": task.id,
                "relation": decision.relation,
                "reason": decision.reason,
            }],
        }

    def _turn_relation_clarification(self, state: PendingTaskGraphState, decision) -> PendingTaskGraphState:
        assistant_content = decision.question or self._default_turn_relation_question(state)
        return {
            "handled": True,
            "assistant_content": assistant_content,
            "events": [
                {
                    "event": "turn_relation_clarification_required",
                    "content": assistant_content,
                    "decision": decision.model_dump(),
                    "candidates": state.get("suspended_candidates") or [],
                },
                {"event": "final", "content": assistant_content},
            ],
        }

    def _default_turn_relation_question(self, state: PendingTaskGraphState) -> str:
        candidates = state.get("suspended_candidates") or []
        summaries = [
            str(candidate.get("summary") or candidate.get("intent") or f"任务 {candidate.get('id')}")
            for candidate in candidates[:2]
            if isinstance(candidate, dict)
        ]
        if summaries:
            return agent_copy.turn_relation_clarification(summaries)
        return agent_copy.turn_relation_clarification()

    def _route_after_apply_turn_relation(self, state: PendingTaskGraphState) -> str:
        if state.get("handled"):
            return "end"
        if state.get("resumed_task"):
            return "interaction"
        if state.get("task"):
            return "preflight"
        return "end"

    async def _preflight(self, state: PendingTaskGraphState) -> PendingTaskGraphState:
        result = await self.preflight_planner.plan(
            state["db"],
            session=state["session"],
            task=state.get("task"),
            turn_input=state["turn_input"],
            team_id=state["team_id"],
        )
        return {
            "task": result.task,
            "handled": result.handled,
            "assistant_content": result.assistant_content,
            "switch_notice": result.switch_notice,
            "suspended_task": result.suspended_task,
            "suspend_reason": result.suspend_reason,
            "clear_pending_task_id": result.clear_pending_task_id,
            "confirmation_decision": result.confirmation_decision,
            "preflight_result": result,
            "events": result.events,
        }

    def _route_after_preflight(self, state: PendingTaskGraphState) -> str:
        if state.get("handled"):
            return "end"
        confirmation_decision = state.get("confirmation_decision")
        if confirmation_decision and confirmation_decision.intent == "confirm":
            return "end"
        if not state.get("task"):
            return "end"
        return "interaction"

    async def _plan_interaction(self, state: PendingTaskGraphState) -> PendingTaskGraphState:
        task = state.get("task")
        if not task:
            return {}
        result = await self.interaction_planner.plan(
            state["db"],
            task,
            state.get("content", ""),
            team_id=state["team_id"],
            user_id=state["user_id"],
            session_id=state["session_id"],
            authorization=state.get("authorization") or "",
        )
        update: dict[str, Any] = {
            "interaction_result": result,
            "events": result.events,
        }
        if result.handled:
            update.update({
                "handled": True,
                "assistant_content": result.assistant_content,
                "remember_pending_task": result.remember_pending_task,
                "clear_pending_task_id": result.clear_pending_task_id,
            })
            if result.selected_customer:
                update["selected_customer"] = result.selected_customer
        return update


pending_task_graph_service = PendingTaskGraphService()

"""Side effects emitted by the normal CRM Agent LangGraph flow."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.services.agent.active_task_ownership import active_task_ownership_projector
from app.services.agent.action_review_graph import (
    ActionReviewGraphService,
    action_review_graph_service as default_action_review_graph_service,
)
from app.services.agent import action_plan, action_workflow, interactions, session_state, task_display, task_execution, task_factory
from app.services.agent.interrupts import AgentInterruptPayload
from app.services.agent.state import AgentGraphInput, AgentGraphResult
from app.services.agent.types import JSONDict, coerce_json_dict


class NewFlowGraphStreamer(Protocol):
    """Minimal stream contract required by the root runtime."""

    def stream_events(self, input_state: AgentGraphInput) -> AsyncGenerator[JSONDict, None]:
        """Stream serializable events from the normal Agent graph."""


@runtime_checkable
class NewFlowGraphRunner(Protocol):
    """Graph-native invoke contract for the normal Agent graph."""

    async def run(self, input_state: AgentGraphInput) -> AgentGraphResult:
        """Return the final checkpointed graph state for one normal Agent turn."""


@dataclass
class NewFlowSideEffectContext:
    """Run-scoped CRM dependencies for side effects outside checkpoint state."""

    db: object
    session: object
    team_id: int
    user_id: int
    switch_notice: str | None = None
    assistant_content: str | None = None
    current_interrupt: AgentInterruptPayload | None = None
    active_task_snapshot: JSONDict | None = None
    ownership_rejection_event: JSONDict | None = None
    auto_execute_tasks: list[object] | None = None
    auto_execute_actions: list[action_plan.ActionPlanItem] | None = None
    review_events: list[JSONDict] | None = None


class NewFlowSideEffectHandler:
    """Applies CRM persistence effects for events from the new-flow graph."""

    def __init__(
        self,
        *,
        action_review_graph_service: ActionReviewGraphService | None = None,
    ) -> None:
        self.action_review_graph_service = action_review_graph_service or default_action_review_graph_service

    async def apply_async(self, event: JSONDict, context: NewFlowSideEffectContext) -> JSONDict:
        event_object: dict[str, object] = dict(event)
        if task_factory._is_waiting_task_event(event_object):
            review = await self.action_review_graph_service.run({
                "event": coerce_json_dict(event_object),
                "team_id": context.team_id,
                "user_id": context.user_id,
                "session_id": getattr(context.session, "id", 0) if context.session else 0,
                "events": [],
            })
            review_events = [coerce_json_dict(item) for item in review.get("events", [])]
            if context.review_events is None:
                context.review_events = []
            context.review_events.extend(review_events)
            decision = review.get("decision")
            event_object["hitl_review"] = {
                "decision": decision,
                "risk_level": review.get("risk_level"),
                "execution_confidence": review.get("execution_confidence"),
                "reason": review.get("reason"),
            }
            if decision == "auto_execute":
                workflow = action_workflow.mark_auto_executable(
                    action_workflow.ensure_event_workflow(event_object),
                    reason=review.get("reason"),
                    source="action_review",
                )
                event_object = action_workflow.attach_workflow(event_object, workflow)
                action_item = action_plan.item_from_workflow(
                    workflow,
                    payload=event_object.get("payload"),
                    target_type=_event_target_type(event_object),
                    target_id=_event_target_id(event_object),
                )
                if action_item is not None and task_execution.can_direct_execute_action_envelope(
                    task_execution.execution_envelope_from_plan_node(action_item)
                ):
                    if context.auto_execute_actions is None:
                        context.auto_execute_actions = []
                    context.auto_execute_actions.append(action_item)
                else:
                    task = task_factory._create_waiting_task_from_event(
                        context.db,
                        event_object,
                        context.team_id,
                        context.user_id,
                        context.session,
                    )
                    if task is not None:
                        if context.auto_execute_tasks is None:
                            context.auto_execute_tasks = []
                        context.auto_execute_tasks.append(task)
                        action_item = action_plan.item_from_workflow(
                            workflow,
                            payload=event_object.get("payload"),
                            task=task,
                            task_id=getattr(task, "id", None),
                            target_type=getattr(task, "target_type", None),
                            target_id=getattr(task, "target_id", None),
                        )
                        if action_item is not None:
                            if context.auto_execute_actions is None:
                                context.auto_execute_actions = []
                            context.auto_execute_actions.append(action_item)
                event_object["event"] = "action_auto_execution_queued"
                event_object["content"] = _auto_execution_content(event_object.get("action"))
            else:
                task = task_factory._create_waiting_task_from_event(
                    context.db,
                    event_object,
                    context.team_id,
                    context.user_id,
                    context.session,
                )
                event_with_interaction = interactions._with_interaction(
                    event_object,
                    db=context.db,
                    team_id=context.team_id,
                )
                ownership = active_task_ownership_projector.project_task(
                    task,
                    team_id=context.team_id,
                    user_id=context.user_id,
                    session_id=getattr(context.session, "id", 0) if context.session else 0,
                    source="new_flow_waiting_task",
                    interaction=event_with_interaction.get("interaction"),
                )
                context.current_interrupt = ownership.current_interrupt
                context.active_task_snapshot = ownership.active_task_snapshot
                context.ownership_rejection_event = ownership.rejection_event

        return self._apply_common(event_object, context)

    def apply(self, event: JSONDict, context: NewFlowSideEffectContext) -> JSONDict:
        event_object: dict[str, object] = dict(event)
        if task_factory._is_waiting_task_event(event_object):
            task = task_factory._create_waiting_task_from_event(
                context.db,
                event_object,
                context.team_id,
                context.user_id,
                context.session,
            )
            event_with_interaction = interactions._with_interaction(
                event_object,
                db=context.db,
                team_id=context.team_id,
            )
            ownership = active_task_ownership_projector.project_task(
                task,
                team_id=context.team_id,
                user_id=context.user_id,
                session_id=getattr(context.session, "id", 0) if context.session else 0,
                source="new_flow_waiting_task",
                interaction=event_with_interaction.get("interaction"),
            )
            context.current_interrupt = ownership.current_interrupt
            context.active_task_snapshot = ownership.active_task_snapshot
            context.ownership_rejection_event = ownership.rejection_event
        return self._apply_common(event_object, context)

    def _apply_common(self, event_object: dict[str, object], context: NewFlowSideEffectContext) -> JSONDict:
        if event_object.get("event") == "business_context_loaded":
            customer = event_object.get("customer")
            if isinstance(customer, dict):
                session_state._remember_current_customer(context.db, context.session, customer)

        if event_object.get("event") == "final":
            content = event_object.get("content")
            context.assistant_content = content if isinstance(content, str) else None
            if context.switch_notice and context.assistant_content:
                context.assistant_content = f"{context.switch_notice}\n\n{context.assistant_content}"
                event_object["content"] = context.assistant_content

        return coerce_json_dict(event_object)


def _auto_execution_content(action: object) -> str:
    label = task_display.readable_execution_label(action) or "业务操作"
    return f"已识别为明确的{label}，正在执行。"


def _event_target_type(event: dict[str, object]) -> str | None:
    target_type = event.get("target_type")
    if isinstance(target_type, str) and target_type.strip():
        return target_type.strip()
    payload = coerce_json_dict(event.get("payload"))
    if payload.get("customer_id") is not None:
        return "customer"
    return None


def _event_target_id(event: dict[str, object]) -> int | None:
    target_id = event.get("target_id")
    if isinstance(target_id, int):
        return target_id
    if isinstance(target_id, str) and target_id.strip():
        try:
            return int(target_id.strip())
        except ValueError:
            return None
    payload = coerce_json_dict(event.get("payload"))
    customer_id = payload.get("customer_id")
    if isinstance(customer_id, int):
        return customer_id
    if isinstance(customer_id, str) and customer_id.strip():
        try:
            return int(customer_id.strip())
        except ValueError:
            return None
    return None


new_flow_side_effect_handler = NewFlowSideEffectHandler()

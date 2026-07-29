"""Pending task turn planning for CRM AI Agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.agent import AgentTaskStatus
from app.services.agent import (
    agent_copy,
    customer_fields,
    customer_related_fields,
    follow_up_fields,
    lead_fields,
    opportunity_fields,
    payment_fields,
    selection,
    session_state,
)
from app.services.agent.confirmation_intent import agent_confirmation_intent_service
from app.services.agent.input import AgentTurnInput


@dataclass(frozen=True)
class PendingTaskTurnResult:
    handled: bool
    events: list[dict[str, Any]] = field(default_factory=list)
    assistant_content: Optional[str] = None
    selected_customer: Optional[dict[str, Any]] = None
    remember_pending_task: bool = False
    clear_pending_task_id: Optional[int] = None


@dataclass(frozen=True)
class PendingTaskPreflightResult:
    task: Any = None
    handled: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)
    assistant_content: Optional[str] = None
    switch_notice: Optional[str] = None
    suspended_task: Any = None
    suspend_reason: Optional[str] = None
    clear_pending_task_id: Optional[int] = None
    confirmation_decision: Any = None


class PendingTaskPreflightPlanner:
    """Routes a waiting task before normal turn execution."""

    async def plan(
        self,
        db: Session,
        *,
        session,
        task,
        turn_input: AgentTurnInput,
        team_id: int,
    ) -> PendingTaskPreflightResult:
        content = turn_input.content
        if not task:
            return PendingTaskPreflightResult(task=None)

        is_executable = agent_confirmation_intent_service.is_executable_confirmation_task(task)
        if not is_executable and session_state._is_rejection(content):
            return self._cancel_task(task)

        if not is_executable:
            return await self._route_interruption(
                db,
                session=session,
                task=task,
                content=content,
                team_id=team_id,
            )

        confirmation_decision = await agent_confirmation_intent_service.assess(
            db,
            team_id=team_id,
            turn_input=turn_input,
            task=task,
            memory=session_state._memory_snapshot_for_session(session, task),
        )
        assessed_event = {
            "event": "confirmation_intent_assessed",
            "task_id": task.id,
            "intent": confirmation_decision.intent,
            "confidence": confirmation_decision.confidence,
            "reason": confirmation_decision.reason,
        }
        if confirmation_decision.intent == "reject":
            result = self._cancel_task(task)
            return PendingTaskPreflightResult(
                task=result.task,
                handled=result.handled,
                events=[assessed_event, *result.events],
                assistant_content=result.assistant_content,
                suspended_task=result.suspended_task,
                suspend_reason=result.suspend_reason,
                clear_pending_task_id=result.clear_pending_task_id,
                confirmation_decision=confirmation_decision,
            )
        if confirmation_decision.intent == "confirm":
            return PendingTaskPreflightResult(
                task=task,
                events=[assessed_event],
                confirmation_decision=confirmation_decision,
            )

        interruption_result = await self._route_interruption(
            db,
            session=session,
            task=task,
            content=content,
            team_id=team_id,
        )
        if interruption_result.handled or interruption_result.task is None:
            return PendingTaskPreflightResult(
                task=interruption_result.task,
                handled=interruption_result.handled,
                events=[assessed_event, *interruption_result.events],
                assistant_content=interruption_result.assistant_content,
                switch_notice=interruption_result.switch_notice,
                suspended_task=interruption_result.suspended_task,
                suspend_reason=interruption_result.suspend_reason,
                clear_pending_task_id=interruption_result.clear_pending_task_id,
                confirmation_decision=confirmation_decision,
            )

        assistant_content = agent_copy.confirmation_unknown()
        return PendingTaskPreflightResult(
            task=task,
            handled=True,
            assistant_content=assistant_content,
            confirmation_decision=confirmation_decision,
            events=[
                assessed_event,
                *interruption_result.events,
                {
                    "event": "confirmation_intent_unknown",
                    "task_id": task.id,
                    "content": assistant_content,
                },
                {"event": "final", "content": assistant_content},
            ],
        )

    def _cancel_task(self, task) -> PendingTaskPreflightResult:
        assistant_content = agent_copy.task_put_aside()
        return PendingTaskPreflightResult(
            task=task,
            handled=True,
            assistant_content=assistant_content,
            suspended_task=task,
            suspend_reason="用户选择先不处理。",
            clear_pending_task_id=task.id,
            events=[
                {
                    "event": "task_cancelled",
                    "task_id": task.id,
                    "content": assistant_content,
                },
                {"event": "final", "content": assistant_content},
            ],
        )

    async def _route_interruption(
        self,
        db: Session,
        *,
        session,
        task,
        content: str,
        team_id: int,
    ) -> PendingTaskPreflightResult:
        decision = await session_state._assess_pending_interruption(
            db,
            team_id=team_id,
            session=session,
            task=task,
            user_message=content,
        )
        assessed_event = {
            "event": "pending_interruption_assessed",
            "decision": decision.decision,
            "confidence": decision.confidence,
            "detected_customer_name": decision.detected_customer_name,
            "detected_intent": decision.detected_intent,
            "reason": decision.reason,
        }
        if session_state._is_high_confidence_new_flow(decision):
            switch_notice = agent_copy.pending_switch_notice(decision.detected_customer_name)
            return PendingTaskPreflightResult(
                task=None,
                switch_notice=switch_notice,
                suspended_task=task,
                suspend_reason=decision.reason or "用户开启了新的业务流程",
                events=[
                    assessed_event,
                    {
                        "event": "pending_task_interrupted",
                        "content": switch_notice,
                        "suspended_task_id": task.id,
                    },
                ],
            )
        if session_state._is_ambiguous_pending_interruption(decision):
            assistant_content = decision.question or agent_copy.pending_interruption_clarification()
            return PendingTaskPreflightResult(
                task=task,
                handled=True,
                assistant_content=assistant_content,
                events=[
                    assessed_event,
                    {
                        "event": "pending_interruption_confirmation_required",
                        "task_id": task.id,
                        "content": assistant_content,
                        "decision": decision.model_dump(),
                    },
                    {"event": "final", "content": assistant_content},
                ],
            )
        return PendingTaskPreflightResult(task=task, events=[assessed_event])


class PendingTaskInteractionPlanner:
    """Plans the single next interaction for a waiting task."""

    async def plan(
        self,
        db: Session,
        task,
        content: str,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        authorization: str,
    ) -> PendingTaskTurnResult:
        field_result = await self._plan_field_collection(db, task, content)
        if field_result.handled:
            return field_result

        if selection._is_business_selection_task(task):
            selected, assistant_content = selection._apply_business_selection(db, task, content)
            return PendingTaskTurnResult(
                handled=True,
                assistant_content=assistant_content,
                remember_pending_task=True,
                events=[
                    {
                        "event": "business_selected" if selected else "business_selection_failed",
                        "task_id": task.id,
                        "content": assistant_content,
                        "selected": selected,
                    },
                    {"event": "final", "content": assistant_content},
                ],
            )

        if selection._is_customer_selection_task(task):
            customer, assistant_content = await selection._apply_customer_selection(
                db,
                task,
                content,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                authorization=authorization,
            )
            if customer:
                return PendingTaskTurnResult(
                    handled=True,
                    assistant_content=assistant_content,
                    selected_customer=customer,
                    remember_pending_task=task.status == AgentTaskStatus.WAITING_USER,
                    clear_pending_task_id=None if task.status == AgentTaskStatus.WAITING_USER else task.id,
                    events=[
                        {
                            "event": "customer_selected",
                            "task_id": task.id,
                            "customer": customer,
                            "content": assistant_content,
                        },
                        {"event": "final", "content": assistant_content},
                    ],
                )
            return PendingTaskTurnResult(
                handled=True,
                assistant_content=assistant_content,
                events=[
                    {
                        "event": "customer_selection_failed",
                        "task_id": task.id,
                        "content": assistant_content,
                    },
                    {"event": "final", "content": assistant_content},
                ],
            )

        return PendingTaskTurnResult(handled=False)

    async def _plan_field_collection(self, db: Session, task, content: str) -> PendingTaskTurnResult:
        for matcher, applier, pending_event in self._field_handlers():
            if not matcher(task):
                continue
            ready, assistant_content = await applier(db, task, content)
            return PendingTaskTurnResult(
                handled=True,
                assistant_content=assistant_content,
                remember_pending_task=True,
                events=[
                    {
                        "event": "confirmation_required" if ready else pending_event,
                        "task_id": task.id,
                        "content": assistant_content,
                        "payload": task.input_json or {},
                    },
                    {"event": "final", "content": assistant_content},
                ],
            )
        return PendingTaskTurnResult(handled=False)

    def _field_handlers(self):
        return (
            (
                follow_up_fields._is_follow_up_quality_fields_task,
                follow_up_fields._apply_follow_up_quality_fields,
                "follow_up_quality_required",
            ),
            (
                follow_up_fields._is_lead_follow_up_quality_fields_task,
                follow_up_fields._apply_lead_follow_up_quality_fields,
                "follow_up_quality_required",
            ),
            (
                customer_related_fields._is_contact_fields_task,
                customer_related_fields._apply_contact_fields,
                "contact_fields_required",
            ),
            (
                opportunity_fields._is_opportunity_fields_task,
                opportunity_fields._apply_opportunity_fields,
                "opportunity_fields_required",
            ),
            (
                customer_related_fields._is_invoice_title_fields_task,
                customer_related_fields._apply_invoice_title_fields,
                "invoice_title_fields_required",
            ),
            (
                customer_related_fields._is_deployment_info_fields_task,
                customer_related_fields._apply_deployment_info_fields,
                "deployment_info_fields_required",
            ),
            (
                customer_related_fields._is_customer_member_fields_task,
                customer_related_fields._apply_customer_member_fields,
                "customer_member_fields_required",
            ),
            (
                payment_fields._is_payment_fields_task,
                payment_fields._apply_payment_fields,
                "payment_fields_required",
            ),
            (
                lead_fields._is_lead_fields_task,
                lead_fields._apply_lead_fields,
                "lead_fields_required",
            ),
            (
                customer_fields._is_customer_fields_task,
                customer_fields._apply_customer_fields,
                "customer_fields_required",
            ),
        )


pending_task_interaction_planner = PendingTaskInteractionPlanner()
pending_task_preflight_planner = PendingTaskPreflightPlanner()

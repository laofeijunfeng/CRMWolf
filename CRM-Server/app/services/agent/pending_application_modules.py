"""Ordinary application modules for durable PendingTask application steps.

These modules intentionally do not own LangGraph state or checkpoints. They run
behind the durable application-step ledger, where ORM/LLM/API work can be
executed once and projected back into the owning graph as checkpoint-safe JSON.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.models.agent import AgentTaskStatus
from app.services.agent import (
    agent_copy,
    choice_resolution,
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
from app.services.agent.pending_effects import (
    PendingTaskSideEffectContext,
    project_pending_task_effect_intents,
)
from app.services.agent.state import PendingTaskPreflightResult, PendingTaskTurnResult
from app.services.agent.types import JSONDict, coerce_json_dict, coerce_json_value

if TYPE_CHECKING:
    from app.services.agent.pending_application_step_projection import (
        PendingApplicationStepExecutionRequest,
    )
    from app.services.agent.schemas import AgentTurnRelationDecision

FieldPredicate = Callable[[object], bool]
FieldCollector = Callable[[object, object, str], Awaitable[tuple[bool, str]]]
FieldCollectorFactory = Callable[[], FieldCollector]


@dataclass(frozen=True)
class PendingFieldInteraction:
    predicate: FieldPredicate
    collector_factory: FieldCollectorFactory
    pending_event: str


_PENDING_FIELD_INTERACTIONS: tuple[PendingFieldInteraction, ...] = (
    PendingFieldInteraction(
        predicate=follow_up_fields._is_follow_up_quality_fields_task,
        collector_factory=lambda: follow_up_fields._apply_follow_up_quality_fields,
        pending_event="follow_up_quality_required",
    ),
    PendingFieldInteraction(
        predicate=follow_up_fields._is_lead_follow_up_quality_fields_task,
        collector_factory=lambda: follow_up_fields._apply_lead_follow_up_quality_fields,
        pending_event="follow_up_quality_required",
    ),
    PendingFieldInteraction(
        predicate=customer_related_fields._is_contact_fields_task,
        collector_factory=lambda: customer_related_fields._apply_contact_fields,
        pending_event="contact_fields_required",
    ),
    PendingFieldInteraction(
        predicate=opportunity_fields._is_opportunity_fields_task,
        collector_factory=lambda: opportunity_fields._apply_opportunity_fields,
        pending_event="opportunity_fields_required",
    ),
    PendingFieldInteraction(
        predicate=customer_related_fields._is_invoice_title_fields_task,
        collector_factory=lambda: customer_related_fields._apply_invoice_title_fields,
        pending_event="invoice_title_fields_required",
    ),
    PendingFieldInteraction(
        predicate=customer_related_fields._is_deployment_info_fields_task,
        collector_factory=lambda: customer_related_fields._apply_deployment_info_fields,
        pending_event="deployment_info_fields_required",
    ),
    PendingFieldInteraction(
        predicate=customer_related_fields._is_customer_member_fields_task,
        collector_factory=lambda: customer_related_fields._apply_customer_member_fields,
        pending_event="customer_member_fields_required",
    ),
    PendingFieldInteraction(
        predicate=payment_fields._is_payment_fields_task,
        collector_factory=lambda: payment_fields._apply_payment_fields,
        pending_event="payment_fields_required",
    ),
    PendingFieldInteraction(
        predicate=lead_fields._is_lead_fields_task,
        collector_factory=lambda: lead_fields._apply_lead_fields,
        pending_event="lead_fields_required",
    ),
    PendingFieldInteraction(
        predicate=customer_fields._is_customer_fields_task,
        collector_factory=lambda: customer_fields._apply_customer_fields,
        pending_event="customer_fields_required",
    ),
)


class PendingTaskTransitionApplicationModule:
    """Make a graph-planned task transition durable before later app work."""

    async def execute(self, request: PendingApplicationStepExecutionRequest) -> object:
        if request.task is None:
            raise ValueError("pending task transition requires an owned task")
        intents = request.step.get("effect_intents")
        if not isinstance(intents, list) or not intents:
            raise ValueError("pending task transition requires effect intents")
        context = PendingTaskSideEffectContext(
            db=request.db,
            session=request.session,
            team_id=request.team_id,
            user_id=request.user_id,
            task=request.task,
            commit=False,
        )
        project_pending_task_effect_intents(intents, context)
        if context.task is None:
            raise ValueError("pending task transition produced no active task")
        return context.task


class PendingPreflightApplicationModule:
    """Assess one pending turn without introducing a second checkpoint owner."""

    async def execute(self, request: PendingApplicationStepExecutionRequest) -> PendingTaskPreflightResult:
        task = request.task
        turn_input = _turn_input(request)
        if task is None:
            return PendingTaskPreflightResult(task=None)

        confirmation_decision = None
        confirmation_events: list[JSONDict] = []
        is_executable = agent_confirmation_intent_service.is_executable_confirmation_task(task)
        if not is_executable and session_state._is_rejection(turn_input.content):
            return _cancel_task(task)

        if is_executable:
            confirmation_decision = await agent_confirmation_intent_service.assess(
                request.db,
                team_id=request.team_id,
                turn_input=turn_input,
                task=task,
                memory=session_state._memory_snapshot_for_session(request.session, task),
            )
            confirmation_event = {
                "event": "confirmation_intent_assessed",
                "task_id": coerce_json_value(getattr(task, "id", None)),
                "intent": coerce_json_value(confirmation_decision.intent),
                "confidence": coerce_json_value(confirmation_decision.confidence),
                "reason": coerce_json_value(confirmation_decision.reason),
            }
            confirmation_events.append(confirmation_event)
            if confirmation_decision.intent == "reject":
                cancelled = _cancel_task(task)
                return PendingTaskPreflightResult(
                    task=cancelled.task,
                    handled=cancelled.handled,
                    events=[confirmation_event, *cancelled.events],
                    assistant_content=cancelled.assistant_content,
                    suspended_task=cancelled.suspended_task,
                    suspend_reason=cancelled.suspend_reason,
                    suspension_kind=cancelled.suspension_kind,
                    clear_pending_task_id=cancelled.clear_pending_task_id,
                    confirmation_decision=confirmation_decision,
                )
            if confirmation_decision.intent == "confirm":
                return PendingTaskPreflightResult(
                    task=task,
                    events=confirmation_events,
                    confirmation_decision=confirmation_decision,
                )

        interruption = await session_state._assess_pending_interruption(
            request.db,
            team_id=request.team_id,
            session=request.session,
            task=task,
            user_message=turn_input.content,
        )
        interruption_event = {
            "event": "pending_interruption_assessed",
            "decision": coerce_json_value(interruption.decision),
            "confidence": coerce_json_value(interruption.confidence),
            "detected_customer_name": coerce_json_value(interruption.detected_customer_name),
            "detected_intent": coerce_json_value(interruption.detected_intent),
            "reason": coerce_json_value(interruption.reason),
        }
        if session_state._is_high_confidence_new_flow(interruption):
            switch_notice = agent_copy.pending_switch_notice(interruption.detected_customer_name)
            return PendingTaskPreflightResult(
                task=None,
                switch_notice=switch_notice,
                suspended_task=task,
                suspend_reason=interruption.reason or "用户开启了新的业务流程",
                suspension_kind="paused",
                events=[
                    *confirmation_events,
                    interruption_event,
                    {
                        "event": "pending_task_interrupted",
                        "content": switch_notice,
                        "suspended_task_id": coerce_json_value(getattr(task, "id", None)),
                    },
                ],
                confirmation_decision=confirmation_decision,
            )
        if session_state._is_ambiguous_pending_interruption(interruption):
            assistant_content = interruption.question or agent_copy.pending_interruption_clarification()
            return PendingTaskPreflightResult(
                task=task,
                handled=True,
                assistant_content=assistant_content,
                events=[
                    *confirmation_events,
                    interruption_event,
                    {
                        "event": "pending_interruption_confirmation_required",
                        "task_id": coerce_json_value(getattr(task, "id", None)),
                        "content": assistant_content,
                        "decision": coerce_json_dict(interruption.model_dump()),
                    },
                    {"event": "final", "content": assistant_content},
                ],
                confirmation_decision=confirmation_decision,
            )
        if confirmation_decision is not None and confirmation_decision.intent == "unknown":
            assistant_content = agent_copy.confirmation_unknown()
            return PendingTaskPreflightResult(
                task=task,
                handled=True,
                assistant_content=assistant_content,
                confirmation_decision=confirmation_decision,
                events=[
                    *confirmation_events,
                    interruption_event,
                    {
                        "event": "confirmation_intent_unknown",
                        "task_id": coerce_json_value(getattr(task, "id", None)),
                        "content": assistant_content,
                    },
                    {"event": "final", "content": assistant_content},
                ],
            )
        return PendingTaskPreflightResult(
            task=task,
            events=[*confirmation_events, interruption_event],
            confirmation_decision=confirmation_decision,
        )


class PendingInteractionApplicationModule:
    """Apply one field/choice interaction behind the application-step ledger."""

    async def execute(self, request: PendingApplicationStepExecutionRequest) -> PendingTaskTurnResult:
        task = request.task
        if task is None:
            return PendingTaskTurnResult(handled=False)
        content = str(request.step.get("content") or "")
        metadata = coerce_json_dict(request.step.get("interaction_metadata"))
        for interaction in _PENDING_FIELD_INTERACTIONS:
            if not interaction.predicate(task):
                continue
            ready, assistant_content = await interaction.collector_factory()(
                request.db,
                task,
                choice_resolution.append_structured_form_values(content, metadata),
            )
            return _field_collection_result(
                task,
                ready=ready,
                assistant_content=assistant_content,
                pending_event=interaction.pending_event,
            )
        if selection._is_business_selection_task(task):
            selected, assistant_content = await selection._apply_business_selection(
                request.db,
                task,
                content,
                team_id=request.team_id,
                user_id=request.user_id,
                session_id=request.session_id,
                metadata=metadata,
            )
            return PendingTaskTurnResult(
                handled=True,
                assistant_content=assistant_content,
                remember_pending_task=True,
                events=[
                    {
                        "event": "business_selected" if selected else "business_selection_failed",
                        "task_id": getattr(task, "id", None),
                        "content": assistant_content,
                        "selected": selected,
                    },
                    {"event": "final", "content": assistant_content},
                ],
            )
        if selection._is_customer_selection_task(task):
            customer, assistant_content = await selection._apply_customer_selection(
                request.db,
                task,
                content,
                team_id=request.team_id,
                user_id=request.user_id,
                session_id=request.session_id,
                authorization=request.authorization,
                metadata=metadata,
            )
            if customer:
                waiting_user = getattr(task, "status", None) == AgentTaskStatus.WAITING_USER
                return PendingTaskTurnResult(
                    handled=True,
                    assistant_content=assistant_content,
                    selected_customer=coerce_json_dict(customer),
                    remember_pending_task=waiting_user,
                    clear_pending_task_id=None if waiting_user else _optional_object_id(task),
                    events=[
                        {
                            "event": "customer_selected",
                            "task_id": getattr(task, "id", None),
                            "customer": coerce_json_value(customer),
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
                        "task_id": getattr(task, "id", None),
                        "content": assistant_content,
                    },
                    {"event": "final", "content": assistant_content},
                ],
            )
        return PendingTaskTurnResult(handled=False)


class PendingTurnRelationApplicationModule:
    """Run the semantic fallback used only when deterministic routing is inconclusive."""

    async def execute(
        self,
        request: PendingApplicationStepExecutionRequest,
    ) -> AgentTurnRelationDecision:
        return await session_state._assess_turn_relation(
            request.db,
            team_id=request.team_id,
            user_id=request.user_id,
            session=request.session,
            task=request.task,
            user_message=str(request.step.get("content") or ""),
        )


def _turn_input(request: PendingApplicationStepExecutionRequest) -> AgentTurnInput:
    payload = coerce_json_dict(request.step.get("turn_input"))
    if payload:
        return AgentTurnInput.model_validate(payload)
    return AgentTurnInput.text(str(request.step.get("content") or ""))


def _cancel_task(task: object) -> PendingTaskPreflightResult:
    assistant_content = agent_copy.task_put_aside()
    return PendingTaskPreflightResult(
        task=None,
        handled=True,
        assistant_content=assistant_content,
        suspended_task=task,
        suspend_reason="用户选择先不处理。",
        suspension_kind="dismissed",
        clear_pending_task_id=_optional_object_id(task),
        events=[
            {
                "event": "task_cancelled",
                "task_id": coerce_json_value(getattr(task, "id", None)),
                "content": assistant_content,
            },
            {"event": "final", "content": assistant_content},
        ],
    )


def _field_collection_result(
    task: object,
    *,
    ready: bool,
    assistant_content: str,
    pending_event: str,
) -> PendingTaskTurnResult:
    return PendingTaskTurnResult(
        handled=True,
        assistant_content=assistant_content,
        remember_pending_task=True,
        events=[
            {
                "event": "confirmation_required" if ready else pending_event,
                "task_id": getattr(task, "id", None),
                "content": assistant_content,
                "payload": getattr(task, "input_json", None) or {},
            },
            {"event": "final", "content": assistant_content},
        ],
    )


def _optional_object_id(value: object) -> int | None:
    raw_id = getattr(value, "id", None)
    if raw_id is None:
        return None
    try:
        return int(raw_id)
    except (TypeError, ValueError):
        return None

"""Canonical interaction semantics for durable Agent waiting tasks.

A waiting task persists the business action that will resume on the next turn.
This module is the single translation boundary from that action to the user
interaction event consumed by LangGraph routing, checkpoint interrupts, and
channel renderers.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


WAITING_TASK_EVENT_TYPES = frozenset({
    "confirmation_required",
    "customer_selection_required",
    "contact_fields_required",
    "invoice_title_fields_required",
    "deployment_info_fields_required",
    "customer_member_fields_required",
    "payment_fields_required",
    "lead_fields_required",
    "customer_fields_required",
    "opportunity_fields_required",
    "follow_up_quality_required",
    "business_selection_required",
})

_CUSTOMER_SELECTION_ACTIONS = frozenset({
    "select_customer_for_activity",
    "select_customer_for_opportunity",
    "select_customer_for_contact",
    "select_customer_for_invoice_title",
    "select_customer_for_deployment_info",
    "select_customer_for_customer_member",
    "select_customer_for_payment_record",
})

_BUSINESS_SELECTION_ACTIONS = frozenset({
    "select_contract_for_payment_plan",
    "select_payment_plan_for_record",
    "select_opportunity_for_stage_move",
})

_TASK_ACTION_EVENT_NAMES = {
    **dict.fromkeys(_CUSTOMER_SELECTION_ACTIONS, "customer_selection_required"),
    **dict.fromkeys(_BUSINESS_SELECTION_ACTIONS, "business_selection_required"),
    "collect_opportunity_fields": "opportunity_fields_required",
    "collect_contact_fields": "contact_fields_required",
    "collect_invoice_title_fields": "invoice_title_fields_required",
    "collect_deployment_info_fields": "deployment_info_fields_required",
    "collect_customer_member_fields": "customer_member_fields_required",
    "collect_payment_fields": "payment_fields_required",
    "collect_lead_fields": "lead_fields_required",
    "collect_customer_fields": "customer_fields_required",
    "collect_follow_up_quality_fields": "follow_up_quality_required",
    "collect_lead_follow_up_quality_fields": "follow_up_quality_required",
    "create_opportunity": "confirmation_required",
    "move_opportunity_stage": "confirmation_required",
    "create_customer_activity": "confirmation_required",
    "create_lead_follow_up": "confirmation_required",
    "create_payment_record": "confirmation_required",
    "create_payment_plan": "confirmation_required",
    "create_lead": "confirmation_required",
    "create_customer": "confirmation_required",
    "create_contact": "confirmation_required",
    "create_invoice_title": "confirmation_required",
    "create_deployment_info": "confirmation_required",
    "create_customer_member": "confirmation_required",
    "transition_follow_up_task": "confirmation_required",
}


def waiting_event_name_for_task_action(action: object) -> str | None:
    """Return the registered waiting event for one durable task action."""

    if not isinstance(action, str) or not action:
        return None
    return _TASK_ACTION_EVENT_NAMES.get(action)


def require_waiting_event_name_for_task_action(action: object) -> str:
    """Return registered semantics or fail closed for an unknown task action."""

    event_name = waiting_event_name_for_task_action(action)
    if event_name is None:
        raise ValueError("waiting task action has no registered interaction semantics")
    return event_name


def waiting_event_name_from_task_state(state: Mapping[str, object]) -> str | None:
    """Resolve and validate the interaction event carried by task state.

    New tasks persist ``source_event`` so replay does not have to infer user
    interaction semantics. Legacy tasks are upgraded in memory through the
    canonical action registry. When both fields exist they must agree; a
    conflicting durable record must fail closed rather than resume through the
    wrong LangGraph branch.
    """

    action = state.get("action")
    action_event = waiting_event_name_for_task_action(action)
    source_event = state.get("source_event")
    if source_event is not None and action_event is None:
        raise ValueError("waiting task action has no registered interaction semantics")
    if source_event is None:
        return action_event
    if not isinstance(source_event, str) or source_event not in WAITING_TASK_EVENT_TYPES:
        raise ValueError("waiting task has unsupported source_event")
    if action_event is not None and source_event != action_event:
        raise ValueError("waiting task action and source_event semantics conflict")
    return source_event


def normalize_waiting_task_state(state: Mapping[str, object]) -> dict[str, object]:
    """Return task state with canonical replay-safe interaction semantics."""

    normalized = dict(state)
    action = normalized.get("action")
    event_name = waiting_event_name_for_task_action(action)
    if event_name is not None:
        normalized["source_event"] = event_name
        return normalized
    source_event = normalized.get("source_event")
    if source_event is not None:
        raise ValueError("waiting task action has no registered interaction semantics")
    if source_event is not None and (
        not isinstance(source_event, str) or source_event not in WAITING_TASK_EVENT_TYPES
    ):
        raise ValueError("waiting task has unsupported source_event")
    return normalized

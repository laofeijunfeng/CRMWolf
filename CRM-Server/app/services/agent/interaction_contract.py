"""Stable Agent interaction contracts shared by web and IM channels."""
from __future__ import annotations

import uuid
from typing import Literal

SCHEMA_VERSION = "agent.interaction.v1"

INTERACTION_TYPE_CHOICE = "choice"
INTERACTION_TYPE_FORM = "form"
INTERACTION_TYPE_TEXT = "text"

STATUS_WAITING_USER_INPUT = "waiting_user_input"
STATUS_WAITING_CONFIRMATION = "waiting_confirmation"


EVENT_BUSINESS_ACTIONS = {
    "confirmation_required": "confirm_action",
    "customer_selection_required": "select_customer",
    "business_selection_required": "select_business_object",
    "opportunity_fields_required": "create_opportunity",
    "contact_fields_required": "create_contact",
    "invoice_title_fields_required": "create_invoice_title",
    "deployment_info_fields_required": "create_deployment_info",
    "customer_member_fields_required": "add_customer_member",
    "payment_fields_required": "create_payment_record",
    "lead_fields_required": "create_lead",
    "customer_fields_required": "create_customer",
    "follow_up_quality_required": "create_follow_up",
    "pending_interruption_confirmation_required": "switch_pending_task",
    "turn_relation_clarification_required": "select_suspended_task",
}


EVENT_TITLES = {
    "confirmation_required": "确认操作",
    "customer_selection_required": "选择客户",
    "business_selection_required": "选择业务对象",
    "opportunity_fields_required": "补充商机信息",
    "contact_fields_required": "补充联系人信息",
    "invoice_title_fields_required": "补充发票抬头信息",
    "deployment_info_fields_required": "补充部署信息",
    "customer_member_fields_required": "补充客户成员信息",
    "payment_fields_required": "补充回款信息",
    "lead_fields_required": "补充线索信息",
    "customer_fields_required": "补充客户信息",
    "follow_up_quality_required": "补充跟进记录",
    "pending_interruption_confirmation_required": "切换流程",
    "turn_relation_clarification_required": "选择处理方式",
}


def event_business_action(event_name: str | None, fallback: str | None = None) -> str | None:
    if fallback:
        return str(fallback)
    if not event_name:
        return None
    return EVENT_BUSINESS_ACTIONS.get(event_name)


def event_title(event_name: str | None, fallback: str | None = None) -> str:
    if fallback:
        return str(fallback)
    if not event_name:
        return "继续处理"
    return EVENT_TITLES.get(event_name, "继续处理")


def build_interaction(
    *,
    event_name: str | None,
    interaction_type: str,
    prompt: str,
    status: str,
    choices: list[dict[str, object]] | None = None,
    fields: list[dict[str, object]] | None = None,
    selection_mode: Literal["single", "multiple"] | None = None,
    min_selections: int | None = None,
    max_selections: int | None = None,
    placeholder: str | None = None,
    submit_label: str | None = None,
    allow_free_text: bool = True,
    allow_cancel: bool = True,
    title: str | None = None,
    business_action: str | None = None,
    payload: dict[str, object] | None = None,
    task_id: object | None = None,
    task_key: object | None = None,
    interaction_id: str | None = None,
) -> dict[str, object]:
    contract_payload = payload.copy() if isinstance(payload, dict) else {}
    interaction: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "interaction_id": interaction_id or f"int_{uuid.uuid4().hex}",
        "type": interaction_type,
        "business_action": event_business_action(event_name, business_action),
        "status": status,
        "title": event_title(event_name, title),
        "prompt": prompt,
        "payload": contract_payload,
        "allow_free_text": allow_free_text,
        "allow_cancel": allow_cancel,
    }
    if task_id is not None:
        interaction["task_id"] = task_id
    if task_key is not None:
        interaction["task_key"] = task_key
    if interaction_type == INTERACTION_TYPE_CHOICE:
        normalized_mode = selection_mode or "single"
        if normalized_mode == "single":
            normalized_min = 1 if min_selections is None else min_selections
            normalized_max = 1 if max_selections is None else max_selections
            if normalized_min != 1 or normalized_max != 1:
                raise ValueError("single choice interactions require exactly one selection")
        else:
            if min_selections is None or max_selections is None:
                raise ValueError("multiple choice interactions require explicit selection bounds")
            normalized_min = min_selections
            normalized_max = max_selections
        choice_count = len(choices or [])
        if (
            normalized_min < 0
            or normalized_max < 1
            or normalized_min > normalized_max
            or normalized_max > choice_count
        ):
            raise ValueError("choice interaction selection bounds are invalid")
        interaction["selection_mode"] = normalized_mode
        interaction["min_selections"] = normalized_min
        interaction["max_selections"] = normalized_max
    elif selection_mode is not None or min_selections is not None or max_selections is not None:
        raise ValueError("selection bounds are only valid for choice interactions")
    if choices is not None:
        interaction["choices"] = choices
    if fields is not None:
        interaction["fields"] = fields
    if placeholder:
        interaction["placeholder"] = placeholder
    if submit_label:
        interaction["submit_label"] = submit_label
    return interaction


def payload_from_event(event: dict[str, object], *, extra: dict[str, object] | None = None) -> dict[str, object]:
    result: dict[str, object] = {}
    payload = event.get("payload")
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(key, str):
                result[key] = value
    for key in ("action", "customer", "customers", "business", "contracts", "payment_plans"):
        value = event.get(key)
        if value is not None:
            result[key] = value
    if extra:
        result.update(extra)
    return result

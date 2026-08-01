"""LangGraph interrupt payload adapters for CRM Agent waiting states."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Mapping, NotRequired, Optional, Protocol, TypedDict

from app.services.agent.input import AgentInputKind, AgentTurnInput
from app.services.agent import task_display
from app.services.agent.interaction_contract import (
    STATUS_WAITING_CONFIRMATION,
    STATUS_WAITING_USER_INPUT,
)
from app.services.agent.task_factory import WAITING_TASK_EVENT_TYPES
from app.services.agent.types import JSONDict, JSONValue, coerce_json_dict, coerce_json_value


INTERRUPT_SCHEMA_VERSION = "agent.interrupt.v1"
TURN_RELATION_SOURCE_EVENT = "turn_relation_clarification_required"
TURN_RELATION_BUSINESS_ACTION = "select_suspended_task"
RUNTIME_WAITING_EVENT_TYPES = WAITING_TASK_EVENT_TYPES | frozenset({
    "pending_interruption_confirmation_required",
    TURN_RELATION_SOURCE_EVENT,
})

AgentInterruptType = Literal["choice", "form", "confirm", "text"]
AgentInterruptReason = Literal[
    "write_confirmation",
    "business_object_disambiguation",
    "missing_required_fields",
    "insufficient_follow_up_quality",
    "pending_flow_switch_confirmation",
    "user_input_required",
]
AgentResumeAction = Literal[
    "approve",
    "edit",
    "reject",
    "cancel",
    "select",
    "submit",
    "submit_fields",
    "submit_text",
    "resume",
]


class AgentInteractionPayload(TypedDict, total=False):
    schema_version: str
    interaction_id: str
    type: str
    business_action: str
    status: str
    title: str
    prompt: str
    payload: JSONDict
    allow_free_text: bool
    allow_cancel: bool
    choices: list[JSONDict]
    fields: list[JSONDict]
    placeholder: str
    submit_label: str
    task_id: int | str
    task_key: str


class AgentTargetRef(TypedDict):
    type: str
    id: int | str
    name: NotRequired[str]


class AgentInterruptPayload(TypedDict, total=False):
    schema_version: str
    type: AgentInterruptType
    reason: AgentInterruptReason
    business_action: str
    target_refs: list[AgentTargetRef]
    draft_payload: JSONDict
    allowed_resume_actions: list[AgentResumeAction]
    task_projection_id: int | str
    task_projection_key: str
    interaction: AgentInteractionPayload
    source_event: str
    runtime_events: list[JSONDict]


class AgentResumePayload(TypedDict, total=False):
    action: AgentResumeAction
    content: str
    source: str
    provider: str
    metadata: JSONDict
    task_projection_id: int | str
    task_projection_key: str
    interrupt_reason: AgentInterruptReason
    business_action: str


class AgentWaitingEvent(TypedDict, total=False):
    event: str
    action: str
    business_action: str
    payload: JSONDict
    customer: JSONDict
    customers: list[JSONDict]
    opportunities: list[JSONDict]
    contracts: list[JSONDict]
    payment_plans: list[JSONDict]
    task_id: int | str
    task_key: str
    target_type: str
    target_id: int | str
    content: str
    decision: JSONDict
    candidates: list[JSONDict]


class AgentWaitingTaskLike(Protocol):
    id: int | str
    task_key: str
    status: str
    intent: Optional[str]
    target_type: Optional[str]
    target_id: Optional[int | str]
    summary: Optional[str]
    state_json: Mapping[str, object] | None


def interrupt_from_waiting_task(
    task: AgentWaitingTaskLike,
    *,
    interaction: Optional[Mapping[str, object]] = None,
) -> AgentInterruptPayload:
    """Project a persisted waiting task into the LangGraph interrupt shape.

    The resulting payload is written into checkpoint state and becomes the
    resumable runtime boundary. ``crm_agent_tasks`` remains a display and audit
    projection, not an alternate runtime source.
    """

    state = task.state_json if isinstance(task.state_json, Mapping) else {}
    action = _as_optional_str(state.get("action"))
    payload = _as_json_dict(state.get("payload"))
    source_event = _source_event_from_task_action(action)
    event: AgentWaitingEvent = {
        "event": source_event,
        "payload": payload,
        "customers": _as_json_dict_list(state.get("customers")),
        "opportunities": _as_json_dict_list(state.get("opportunities")),
        "contracts": _as_json_dict_list(state.get("contracts")),
        "payment_plans": _as_json_dict_list(state.get("payment_plans")),
        "task_id": task.id,
        "task_key": task.task_key,
    }
    if action:
        event["action"] = action
    customer = _as_json_dict(state.get("customer"))
    if customer:
        event["customer"] = customer
    if task.target_type:
        event["target_type"] = task.target_type
    if task.target_id is not None:
        event["target_id"] = task.target_id
    return interrupt_from_waiting_event(event, interaction=interaction)


def interrupt_from_waiting_event(
    event: AgentWaitingEvent,
    *,
    interaction: Optional[Mapping[str, object]] = None,
) -> AgentInterruptPayload:
    event_name = event.get("event") or ""
    payload = event.get("payload") or {}
    interaction_payload = _as_interaction_payload(interaction)
    business_action = (
        interaction_payload.get("business_action")
        or event.get("business_action")
        or event.get("action")
        or "unknown"
    )
    result: AgentInterruptPayload = {
        "schema_version": INTERRUPT_SCHEMA_VERSION,
        "type": _interrupt_type_for_interaction(interaction_payload),
        "reason": reason_for_event(event_name, interaction=interaction_payload),
        "business_action": business_action,
        "target_refs": _target_refs_for_event(event, payload),
        "draft_payload": _draft_payload_for_event(event, payload),
        "allowed_resume_actions": allowed_resume_actions_for_interaction(interaction_payload),
        "interaction": interaction_payload,
        "source_event": event_name,
    }
    task_id = event.get("task_id")
    if isinstance(task_id, (int, str)):
        result["task_projection_id"] = task_id
    task_key = event.get("task_key")
    if isinstance(task_key, str) and task_key:
        result["task_projection_key"] = task_key
    return result


def interrupt_from_waiting_events(
    events: Sequence[JSONDict],
    *,
    interaction: Optional[Mapping[str, object]] = None,
) -> AgentInterruptPayload | None:
    """Project the final waiting event of a turn into checkpoint-safe state."""

    for event in reversed(events):
        event_name = event.get("event")
        if isinstance(event_name, str) and event_name in RUNTIME_WAITING_EVENT_TYPES:
            return interrupt_from_waiting_event(_waiting_event_from_json(event), interaction=interaction)
    return None


def resume_payload_from_turn_input(
    turn_input: AgentTurnInput,
    *,
    current_interrupt: AgentInterruptPayload,
) -> AgentResumePayload:
    metadata = _resume_metadata_for_turn(turn_input, current_interrupt=current_interrupt)
    payload: AgentResumePayload = {
        "action": _resume_action_for_turn(turn_input, current_interrupt=current_interrupt),
        "content": turn_input.content,
        "source": turn_input.source,
        "metadata": metadata,
    }
    if turn_input.provider:
        payload["provider"] = turn_input.provider
    if current_interrupt.get("task_projection_id") is not None:
        payload["task_projection_id"] = current_interrupt["task_projection_id"]
    if current_interrupt.get("task_projection_key"):
        payload["task_projection_key"] = current_interrupt["task_projection_key"]
    if current_interrupt.get("reason"):
        payload["interrupt_reason"] = current_interrupt["reason"]
    if current_interrupt.get("business_action"):
        payload["business_action"] = current_interrupt["business_action"]
    validate_resume_payload(payload, current_interrupt=current_interrupt)
    return payload


def validate_resume_payload(
    resume_payload: Mapping[str, object],
    *,
    current_interrupt: AgentInterruptPayload,
) -> None:
    """Validate a resume payload against the active graph interrupt contract."""

    action = resume_payload.get("action")
    if not isinstance(action, str):
        raise ValueError("resume payload requires an action")
    allowed_actions = current_interrupt.get("allowed_resume_actions") or []
    if allowed_actions and action not in allowed_actions:
        raise ValueError(f"resume action {action!r} is not allowed for current interrupt")

    interrupt_task_id = current_interrupt.get("task_projection_id")
    resume_task_id = resume_payload.get("task_projection_id")
    if interrupt_task_id is not None and resume_task_id is not None and resume_task_id != interrupt_task_id:
        raise ValueError("resume payload task_projection_id does not match current interrupt")

    interrupt_task_key = current_interrupt.get("task_projection_key")
    resume_task_key = resume_payload.get("task_projection_key")
    if interrupt_task_key and resume_task_key and resume_task_key != interrupt_task_key:
        raise ValueError("resume payload task_projection_key does not match current interrupt")

    interrupt_reason = current_interrupt.get("reason")
    resume_reason = resume_payload.get("interrupt_reason")
    if interrupt_reason and resume_reason and resume_reason != interrupt_reason:
        raise ValueError("resume payload interrupt_reason does not match current interrupt")

    interrupt_business_action = current_interrupt.get("business_action")
    resume_business_action = resume_payload.get("business_action")
    if interrupt_business_action and resume_business_action and resume_business_action != interrupt_business_action:
        raise ValueError("resume payload business_action does not match current interrupt")

    interrupt_type = current_interrupt.get("type")
    metadata = coerce_json_dict(resume_payload.get("metadata"))
    content = resume_payload.get("content")
    content_text = content.strip() if isinstance(content, str) else ""
    if action == "select" or interrupt_type == "choice":
        if action != "cancel" and not _has_choice_resume_value(metadata):
            if _is_turn_relation_choice_interrupt(current_interrupt):
                raise ValueError("choice interrupt resume requires a selected task id or turn_relation in metadata")
            raise ValueError("choice interrupt resume requires a selected id in metadata")
    if action == "submit_fields" or interrupt_type == "form":
        if action != "cancel" and not _has_form_resume_value(metadata) and not content_text:
            raise ValueError("form interrupt resume requires submitted fields or content")
    if action == "submit_text" or interrupt_type == "text":
        if action != "cancel" and not content_text:
            raise ValueError("text interrupt resume requires non-empty content")
    if action == "edit" and interrupt_type == "confirm" and not content_text:
        raise ValueError("confirm edit resume requires non-empty content")


def interrupt_payload_from_json(value: object) -> AgentInterruptPayload | None:
    """Project checkpoint/session JSON into the typed interrupt contract."""

    payload = coerce_json_dict(value)
    if not payload:
        return None

    interrupt_payload: AgentInterruptPayload = {}
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, str):
        interrupt_payload["schema_version"] = schema_version

    interrupt_type = payload.get("type")
    if interrupt_type in {"choice", "form", "confirm", "text"}:
        interrupt_payload["type"] = interrupt_type

    reason = payload.get("reason")
    if reason in {
        "write_confirmation",
        "business_object_disambiguation",
        "missing_required_fields",
        "insufficient_follow_up_quality",
        "pending_flow_switch_confirmation",
        "user_input_required",
    }:
        interrupt_payload["reason"] = reason

    business_action = payload.get("business_action")
    if isinstance(business_action, str):
        interrupt_payload["business_action"] = business_action

    target_refs = payload.get("target_refs")
    if isinstance(target_refs, list):
        refs: list[AgentTargetRef] = []
        for ref_value in target_refs:
            ref = coerce_json_dict(ref_value)
            ref_type = ref.get("type")
            ref_id = ref.get("id")
            if isinstance(ref_type, str) and _is_ref_id(ref_id):
                target_ref: AgentTargetRef = {"type": ref_type, "id": ref_id}
                ref_name = ref.get("name")
                if isinstance(ref_name, str):
                    target_ref["name"] = ref_name
                refs.append(target_ref)
        if refs:
            interrupt_payload["target_refs"] = refs

    draft_payload = coerce_json_dict(payload.get("draft_payload"))
    if draft_payload:
        interrupt_payload["draft_payload"] = draft_payload

    allowed_resume_actions = _resume_actions_from_json(payload.get("allowed_resume_actions"))
    if allowed_resume_actions:
        interrupt_payload["allowed_resume_actions"] = allowed_resume_actions

    task_projection_id = payload.get("task_projection_id")
    if _is_ref_id(task_projection_id):
        interrupt_payload["task_projection_id"] = task_projection_id

    task_projection_key = payload.get("task_projection_key")
    if isinstance(task_projection_key, str):
        interrupt_payload["task_projection_key"] = task_projection_key

    interaction = _as_interaction_payload(coerce_json_dict(payload.get("interaction")))
    if interaction:
        interrupt_payload["interaction"] = interaction

    source_event = payload.get("source_event")
    if isinstance(source_event, str):
        interrupt_payload["source_event"] = source_event

    return interrupt_payload or None


def allowed_resume_actions_for_interaction(
    interaction: Optional[Mapping[str, object]],
) -> list[AgentResumeAction]:
    interaction = interaction or {}
    status = interaction.get("status")
    interaction_type = interaction.get("type")
    if status == STATUS_WAITING_CONFIRMATION:
        return ["approve", "edit", "reject", "cancel"]
    if interaction_type == "form":
        return ["submit_fields", "cancel"]
    if interaction_type == "choice":
        return ["select", "cancel"]
    if interaction_type == "text":
        return ["submit_text", "cancel"]
    if status == STATUS_WAITING_USER_INPUT:
        return ["submit", "cancel"]
    return ["resume", "cancel"]


def reason_for_event(
    event_name: Optional[str],
    *,
    interaction: Optional[Mapping[str, object]] = None,
) -> AgentInterruptReason:
    interaction = interaction or {}
    if interaction.get("status") == STATUS_WAITING_CONFIRMATION or event_name == "confirmation_required":
        return "write_confirmation"
    if event_name in {
        "customer_selection_required",
        "business_selection_required",
        "turn_relation_clarification_required",
    }:
        return "business_object_disambiguation"
    if event_name and event_name.endswith("_fields_required"):
        return "missing_required_fields"
    if event_name == "follow_up_quality_required":
        return "insufficient_follow_up_quality"
    if event_name == "pending_interruption_confirmation_required":
        return "pending_flow_switch_confirmation"
    return "user_input_required"


def _resume_action_for_turn(
    turn_input: AgentTurnInput,
    *,
    current_interrupt: AgentInterruptPayload,
) -> AgentResumeAction:
    if turn_input.kind == AgentInputKind.CONFIRM:
        return "approve"
    if turn_input.kind == AgentInputKind.REJECT:
        if current_interrupt.get("type") == "choice":
            return "cancel"
        return "reject"
    metadata = coerce_json_dict(turn_input.metadata)
    if _has_choice_resume_value(metadata):
        return "select"
    if current_interrupt.get("type") == "choice" and _is_rejection_text(turn_input.content):
        return "cancel"
    if current_interrupt.get("type") == "choice":
        return "select"
    if current_interrupt.get("type") == "confirm":
        if _is_rejection_text(turn_input.content):
            return "reject"
        if _is_confirmation_text(turn_input.content):
            return "approve"
        return "edit"
    if current_interrupt.get("type") == "form":
        return "submit_fields"
    if current_interrupt.get("type") == "text":
        return "submit_text"
    return "submit"


def _resume_metadata_for_turn(
    turn_input: AgentTurnInput,
    *,
    current_interrupt: AgentInterruptPayload,
) -> JSONDict:
    metadata = coerce_json_dict(turn_input.metadata)
    if current_interrupt.get("type") != "choice":
        return metadata
    if _has_choice_resume_value(metadata):
        return metadata
    choice_metadata = _choice_metadata_from_text(turn_input.content, current_interrupt=current_interrupt)
    if choice_metadata:
        return {**metadata, **choice_metadata}
    selected_id = _selection_id_from_text(turn_input.content)
    if selected_id:
        return {**metadata, "selected_id": selected_id}
    if _is_turn_relation_choice_interrupt(current_interrupt) and _is_turn_relation_start_new_flow_text(turn_input.content):
        return {**metadata, "turn_relation": "START_NEW_FLOW"}
    if _is_turn_relation_choice_interrupt(current_interrupt) and _is_turn_relation_continue_text(turn_input.content):
        return {**metadata, "turn_relation": "ASK_USER"}
    if (
        _is_turn_relation_choice_interrupt(current_interrupt)
        and turn_input.content.strip()
        and not _is_rejection_text(turn_input.content)
    ):
        return {**metadata, "turn_relation": "START_NEW_FLOW"}
    return metadata


def _choice_metadata_from_text(
    content: str,
    *,
    current_interrupt: AgentInterruptPayload,
) -> JSONDict:
    interaction = current_interrupt.get("interaction") or {}
    choices = interaction.get("choices")
    if not isinstance(choices, list):
        return {}
    indexed_choice = _choice_from_index_text(content, choices)
    if indexed_choice:
        return _metadata_for_choice(indexed_choice)
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        label = choice.get("label")
        value = choice.get("value")
        if task_display.display_text_matches(content, label) or task_display.display_text_matches(content, value):
            return _metadata_for_choice(choice)
    return {}


def _choice_from_index_text(content: str, choices: list[object]) -> JSONDict:
    text = content.strip()
    if not text.isdigit():
        return {}
    index = int(text) - 1
    if index < 0 or index >= len(choices):
        return {}
    choice = choices[index]
    return coerce_json_dict(choice)


def _metadata_for_choice(choice: Mapping[object, object]) -> JSONDict:
    metadata = coerce_json_dict(choice.get("metadata"))
    if metadata:
        return metadata
    value = choice.get("value")
    if _is_ref_id(value):
        return {"selected_id": value}
    return {}


def _selection_id_from_text(content: str) -> str | None:
    text = content.strip()
    if text.isdigit():
        return text
    return None


def _is_confirmation_text(content: str) -> bool:
    return content.strip().lower() in {"确认", "确定", "是", "好的", "好", "可以", "执行", "继续", "yes", "y", "ok"}


def _is_rejection_text(content: str) -> bool:
    return content.strip().lower() in {"取消", "不", "否", "不要", "不用", "先不处理", "拒绝", "no", "n"}


def _is_turn_relation_start_new_flow_text(content: str) -> bool:
    normalized = "".join(char.lower() for char in content if char.isalnum())
    if not normalized:
        return False
    return any(marker in normalized for marker in ("作为新流程处理", "新流程", "重新开始", "不接上", "不要接上"))


def _is_turn_relation_continue_text(content: str) -> bool:
    normalized = "".join(char.lower() for char in content if char.isalnum())
    if not normalized:
        return False
    return normalized.startswith("继续") or normalized.startswith("接着") or normalized.startswith("恢复")


def _has_selection_resume_value(metadata: JSONDict) -> bool:
    for key in (
        "selected_id",
        "selected_task_id",
        "selected_customer_id",
        "selected_opportunity_id",
        "selected_contract_id",
        "selected_payment_plan_id",
        "selected_option_id",
        "choice_id",
    ):
        value = metadata.get(key)
        if _is_ref_id(value) and str(value).strip():
            return True
    selected = coerce_json_dict(metadata.get("selected"))
    selected_id = selected.get("id")
    return _is_ref_id(selected_id) and str(selected_id).strip()


def _has_choice_resume_value(metadata: JSONDict) -> bool:
    return _has_selection_resume_value(metadata) or _has_turn_relation_resume_value(metadata)


def _has_turn_relation_resume_value(metadata: JSONDict) -> bool:
    relation = metadata.get("turn_relation")
    return relation in {"START_NEW_FLOW", "RESUME_SUSPENDED_DRAFT", "ASK_USER"}


def _is_turn_relation_choice_interrupt(current_interrupt: AgentInterruptPayload) -> bool:
    if current_interrupt.get("type") != "choice":
        return False
    if current_interrupt.get("source_event") == TURN_RELATION_SOURCE_EVENT:
        return True
    if current_interrupt.get("business_action") == TURN_RELATION_BUSINESS_ACTION:
        return True
    interaction = current_interrupt.get("interaction") or {}
    return interaction.get("business_action") == TURN_RELATION_BUSINESS_ACTION


def _has_form_resume_value(metadata: JSONDict) -> bool:
    for key in ("fields", "field_values", "form_values", "payload"):
        if coerce_json_dict(metadata.get(key)):
            return True
    return False


def _interrupt_type_for_interaction(interaction: Mapping[str, object]) -> AgentInterruptType:
    if interaction.get("status") == STATUS_WAITING_CONFIRMATION:
        return "confirm"
    interaction_type = interaction.get("type")
    if interaction_type == "choice":
        return "choice"
    if interaction_type == "form":
        return "form"
    if interaction_type == "text":
        return "text"
    return "text"


def _resume_actions_from_json(value: object) -> list[AgentResumeAction]:
    if not isinstance(value, list):
        return []
    actions: list[AgentResumeAction] = []
    for action in value:
        if action in {
            "approve",
            "edit",
            "reject",
            "cancel",
            "select",
            "submit",
            "submit_fields",
            "submit_text",
            "resume",
        }:
            actions.append(action)
    return actions


def _target_refs_for_event(event: AgentWaitingEvent, payload: JSONDict) -> list[AgentTargetRef]:
    refs: list[AgentTargetRef] = []
    target_type = event.get("target_type")
    target_id = event.get("target_id")
    if target_type and target_id is not None:
        refs.append({"type": target_type, "id": target_id})
    customer = event.get("customer") or {}
    customer_id = customer.get("id") or payload.get("customer_id")
    if _is_ref_id(customer_id) and not _has_ref(refs, "customer", customer_id):
        ref: AgentTargetRef = {"type": "customer", "id": customer_id}
        account_name = customer.get("account_name")
        if isinstance(account_name, str):
            ref["name"] = account_name
        refs.append(ref)
    return refs


def _draft_payload_for_event(event: AgentWaitingEvent, payload: JSONDict) -> JSONDict:
    draft: JSONDict = dict(payload)
    for key in ("customer", "customers", "opportunities", "contracts", "payment_plans"):
        value = event.get(key)
        if value:
            draft[key] = value
    content = event.get("content")
    if isinstance(content, str) and content:
        draft["content"] = content
    decision = event.get("decision")
    if decision:
        draft["decision"] = decision
    candidates = event.get("candidates")
    if candidates:
        draft["candidates"] = candidates
    return draft


def _waiting_event_from_json(event: JSONDict) -> AgentWaitingEvent:
    result: AgentWaitingEvent = {}
    _copy_waiting_str(event, result, "event")
    _copy_waiting_str(event, result, "action")
    _copy_waiting_str(event, result, "business_action")
    _copy_waiting_str(event, result, "task_key")
    _copy_waiting_str(event, result, "target_type")
    _copy_waiting_str(event, result, "content")
    _copy_waiting_id(event, result, "task_id")
    _copy_waiting_id(event, result, "target_id")
    payload = _as_json_dict(event.get("payload"))
    if payload:
        result["payload"] = payload
    customer = _as_json_dict(event.get("customer"))
    if customer:
        result["customer"] = customer
    customers = _as_json_dict_list(event.get("customers"))
    if customers:
        result["customers"] = customers
    opportunities = _as_json_dict_list(event.get("opportunities"))
    if opportunities:
        result["opportunities"] = opportunities
    contracts = _as_json_dict_list(event.get("contracts"))
    if contracts:
        result["contracts"] = contracts
    payment_plans = _as_json_dict_list(event.get("payment_plans"))
    if payment_plans:
        result["payment_plans"] = payment_plans
    decision = _as_json_dict(event.get("decision"))
    if decision:
        result["decision"] = decision
    candidates = _as_json_dict_list(event.get("candidates"))
    if candidates:
        result["candidates"] = candidates
    return result


def _has_ref(refs: list[AgentTargetRef], ref_type: str, ref_id: int | str) -> bool:
    return any(ref.get("type") == ref_type and ref.get("id") == ref_id for ref in refs)


def _source_event_from_task_action(action: Optional[str]) -> str:
    event_names = {
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
        "select_opportunity_for_stage_move": "business_selection_required",
        "create_customer_activity": "confirmation_required",
        "create_lead_follow_up": "confirmation_required",
        "create_payment_record": "confirmation_required",
        "create_payment_plan": "confirmation_required",
        "create_lead": "confirmation_required",
        "create_customer": "confirmation_required",
    }
    return event_names.get(action or "", "confirmation_required")


def _as_interaction_payload(value: Optional[Mapping[str, object]]) -> AgentInteractionPayload:
    if not value:
        return {}
    payload: AgentInteractionPayload = {}
    _copy_str(value, payload, "schema_version")
    _copy_str(value, payload, "interaction_id")
    _copy_str(value, payload, "type")
    _copy_str(value, payload, "business_action")
    _copy_str(value, payload, "status")
    _copy_str(value, payload, "title")
    _copy_str(value, payload, "prompt")
    _copy_str(value, payload, "placeholder")
    _copy_str(value, payload, "submit_label")
    _copy_bool(value, payload, "allow_free_text")
    _copy_bool(value, payload, "allow_cancel")
    _copy_id(value, payload, "task_id")
    _copy_str(value, payload, "task_key")
    nested_payload = _as_json_dict(value.get("payload"))
    if nested_payload:
        payload["payload"] = nested_payload
    choices = _as_json_dict_list(value.get("choices"))
    if choices:
        payload["choices"] = choices
    fields = _as_json_dict_list(value.get("fields"))
    if fields:
        payload["fields"] = fields
    return payload


def _as_json_dict(value: object) -> JSONDict:
    return coerce_json_dict(value)


def _as_json_dict_list(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    return [_as_json_dict(item) for item in value if isinstance(item, Mapping)]


def _to_json_value(value: object) -> JSONValue:
    return coerce_json_value(value)


def _copy_str(source: Mapping[str, object], target: AgentInteractionPayload, key: str) -> None:
    value = source.get(key)
    if isinstance(value, str):
        target[key] = value


def _copy_bool(source: Mapping[str, object], target: AgentInteractionPayload, key: str) -> None:
    value = source.get(key)
    if isinstance(value, bool):
        target[key] = value


def _copy_id(source: Mapping[str, object], target: AgentInteractionPayload, key: str) -> None:
    value = source.get(key)
    if _is_ref_id(value):
        target[key] = value


def _copy_waiting_str(source: Mapping[str, object], target: AgentWaitingEvent, key: str) -> None:
    value = source.get(key)
    if isinstance(value, str):
        target[key] = value


def _copy_waiting_id(source: Mapping[str, object], target: AgentWaitingEvent, key: str) -> None:
    value = source.get(key)
    if _is_ref_id(value):
        target[key] = value


def _as_optional_str(value: object) -> Optional[str]:
    return value if isinstance(value, str) else None


def _is_ref_id(value: object) -> bool:
    return isinstance(value, (int, str))

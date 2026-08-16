"""Action-level workflow policy for Agent HITL decisions."""
from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache

from app.services.agent.types import JSONDict, coerce_json_dict

WORKFLOW_SCHEMA_VERSION = "agent.action_workflow.v1"
WORKFLOW_KEY = "workflow"

SCOPE_REQUIRED_WRITE = "required_write"
SCOPE_OPTIONAL_SUGGESTION = "optional_suggestion"
SCOPE_DERIVED_AUTOMATION = "derived_automation"

STATUS_PLANNED = "planned"
STATUS_WAITING_USER = "waiting_user"
STATUS_RUNNING = "running"
STATUS_EXECUTED = "executed"
STATUS_SKIPPED = "skipped"
STATUS_CANCELLED = "cancelled"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked"

ON_REJECT_CANCEL_ACTION = "cancel_action"
ON_REJECT_SKIP_CONTINUE = "skip_and_continue"
ON_REJECT_ASK_CLARIFICATION = "ask_clarification"
ON_REJECT_CANCEL_WORKFLOW = "cancel_workflow"

SOURCE_BUSINESS_SUGGESTION = "business_suggestion"
SOURCE_EXPLICIT_USER_REQUEST = "explicit_user_request"
SOURCE_SYSTEM_AUTOMATION = "system_automation"

EXECUTION_REQUIRES_CONFIRMATION = "requires_confirmation"
EXECUTION_AUTO_EXECUTE = "auto_execute"

ACTION_CAPABILITY_REQUIRES_USER_AUTHORIZATION = "requires_user_authorization"
ACTION_CAPABILITY_CRM_WRITE = "crm_write"
ACTION_CAPABILITY_REQUIRES_CONFIRMATION = "requires_confirmation"
ACTION_CAPABILITY_BACKGROUND_RECOVERABLE = "background_recoverable"
ACTION_CAPABILITY_PARALLEL_SAFE = "parallel_safe"
ACTION_CAPABILITY_REQUIRES_IDEMPOTENCY_KEY = "requires_idempotency_key"

_ALLOWED_SCOPES = {
    SCOPE_REQUIRED_WRITE,
    SCOPE_OPTIONAL_SUGGESTION,
    SCOPE_DERIVED_AUTOMATION,
}
_ALLOWED_STATUSES = {
    STATUS_PLANNED,
    STATUS_WAITING_USER,
    STATUS_RUNNING,
    STATUS_EXECUTED,
    STATUS_SKIPPED,
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_BLOCKED,
}
_ALLOWED_ON_REJECT = {
    ON_REJECT_CANCEL_ACTION,
    ON_REJECT_SKIP_CONTINUE,
    ON_REJECT_ASK_CLARIFICATION,
    ON_REJECT_CANCEL_WORKFLOW,
}
_ALLOWED_SOURCES = {
    SOURCE_BUSINESS_SUGGESTION,
    SOURCE_EXPLICIT_USER_REQUEST,
    SOURCE_SYSTEM_AUTOMATION,
}
_ALLOWED_EXECUTION_POLICIES = {
    EXECUTION_REQUIRES_CONFIRMATION,
    EXECUTION_AUTO_EXECUTE,
}
_ACTION_TOOL_NAMES: dict[str, str] = {
    "create_customer_activity": "create_customer_activity",
    "create_lead": "create_lead",
    "create_customer": "create_customer",
    "create_lead_follow_up": "create_lead_follow_up",
    "create_contact": "create_contact",
    "create_invoice_title": "create_invoice_title",
    "create_deployment_info": "create_deployment_info",
    "create_customer_member": "create_customer_member",
    "create_opportunity": "create_opportunity",
    "move_opportunity_stage": "move_opportunity_stage",
    "transition_follow_up_task": "transition_follow_up_task",
    "resolve_follow_up_task_confirmation_case": "resolve_follow_up_task_confirmation_case",
    "create_payment_plan": "create_payment_plan",
    "create_payment_record": "create_payment_record",
}


@dataclass(frozen=True)
class AgentActionCapabilityOverride:
    allows_background_recovery: bool | None = None
    parallel_safe: bool | None = None
    requires_idempotency_key: bool | None = None
    required_payload_fields: frozenset[str] = frozenset()


_ACTION_CAPABILITY_OVERRIDES: dict[str, AgentActionCapabilityOverride] = {
    # Internal system automations are not exposed as registry tools. They are
    # declared here so recovery/runtime policy still reads one action contract.
    "refresh_customer_profile": AgentActionCapabilityOverride(
        allows_background_recovery=True,
        parallel_safe=True,
    ),
    "project_next_follow_up_tasks": AgentActionCapabilityOverride(
        allows_background_recovery=True,
        parallel_safe=True,
    ),
}


@dataclass(frozen=True)
class AgentActionCapability:
    action_type: str
    tool_name: str | None = None
    is_write: bool = False
    requires_confirmation: bool = False
    requires_user_authorization: bool = False
    allows_background_recovery: bool = False
    parallel_safe: bool = False
    requires_idempotency_key: bool = False
    required_payload_fields: frozenset[str] = frozenset()

    @property
    def flags(self) -> frozenset[str]:
        values: set[str] = set()
        if self.is_write:
            values.add(ACTION_CAPABILITY_CRM_WRITE)
        if self.requires_confirmation:
            values.add(ACTION_CAPABILITY_REQUIRES_CONFIRMATION)
        if self.requires_user_authorization:
            values.add(ACTION_CAPABILITY_REQUIRES_USER_AUTHORIZATION)
        if self.allows_background_recovery:
            values.add(ACTION_CAPABILITY_BACKGROUND_RECOVERABLE)
        if self.parallel_safe:
            values.add(ACTION_CAPABILITY_PARALLEL_SAFE)
        if self.requires_idempotency_key:
            values.add(ACTION_CAPABILITY_REQUIRES_IDEMPOTENCY_KEY)
        return frozenset(values)


def new_workflow_contract(
    *,
    action: object,
    scope: str,
    source: str,
    risk_level: object = None,
    execution_policy: str = EXECUTION_REQUIRES_CONFIRMATION,
    on_reject: str | None = None,
    blocking: bool | None = None,
) -> JSONDict:
    """Build a checkpoint-safe action workflow contract.

    The contract lives in Agent-owned JSON state. It is intentionally small:
    LangGraph checkpoints and ``crm_agent_tasks.state_json`` can both carry it
    without requiring a persistence migration for the first architecture step.
    """

    action_name = str(action) if isinstance(action, str) and action else "unknown"
    effective_on_reject = on_reject or (
        ON_REJECT_SKIP_CONTINUE if scope == SCOPE_OPTIONAL_SUGGESTION else ON_REJECT_CANCEL_ACTION
    )
    effective_blocking = blocking if blocking is not None else scope != SCOPE_OPTIONAL_SUGGESTION
    policy: JSONDict = {
        "scope": scope,
        "source": source,
        "execution_policy": execution_policy,
        "on_reject": effective_on_reject,
        "blocking": effective_blocking,
    }
    if isinstance(risk_level, str) and risk_level:
        policy["risk_level"] = risk_level
    return {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "workflow_id": f"wf_{uuid.uuid4().hex}",
        "action_id": f"act_{uuid.uuid4().hex}",
        "action_type": action_name,
        "status": STATUS_PLANNED if execution_policy == EXECUTION_AUTO_EXECUTE else STATUS_WAITING_USER,
        "policy": policy,
    }


def optional_suggestion_contract(*, action: object, source: str = SOURCE_BUSINESS_SUGGESTION) -> JSONDict:
    return new_workflow_contract(
        action=action,
        scope=SCOPE_OPTIONAL_SUGGESTION,
        source=source,
        on_reject=ON_REJECT_SKIP_CONTINUE,
        blocking=False,
    )


def derived_automation_contract(*, action: object, source: str = SOURCE_SYSTEM_AUTOMATION) -> JSONDict:
    return new_workflow_contract(
        action=action,
        scope=SCOPE_DERIVED_AUTOMATION,
        source=source,
        execution_policy=EXECUTION_AUTO_EXECUTE,
        on_reject=ON_REJECT_ASK_CLARIFICATION,
        blocking=False,
    )


def required_write_contract(
    *,
    action: object,
    source: str = SOURCE_EXPLICIT_USER_REQUEST,
    risk_level: object = None,
) -> JSONDict:
    return new_workflow_contract(
        action=action,
        scope=SCOPE_REQUIRED_WRITE,
        source=source,
        risk_level=risk_level,
        on_reject=ON_REJECT_CANCEL_ACTION,
        blocking=True,
    )


def stable_child_required_write_contract(
    *,
    parent_workflow: object,
    parent_action_id: str,
    slot: str,
    action: object,
    source: str = SOURCE_EXPLICIT_USER_REQUEST,
    risk_level: object = None,
) -> JSONDict:
    """Build one replay-stable child action for a semantic workflow slot.

    The child identity deliberately excludes the generated payload. A retried
    parent execution must resolve to the first durable child projection; a
    changed payload is treated as a projection conflict instead of silently
    creating a second user-visible task.
    """

    normalized_parent = workflow_from_mapping(parent_workflow)
    normalized_parent_action_id = str(parent_action_id or "").strip()
    normalized_slot = str(slot or "").strip()
    if not normalized_parent_action_id:
        raise ValueError("stable child workflow requires parent_action_id")
    if not normalized_slot:
        raise ValueError("stable child workflow requires slot")
    parent_workflow_id = str(normalized_parent.get("workflow_id") or "").strip()
    if not parent_workflow_id:
        parent_workflow_id = _stable_identifier("wf", {"parent_action_id": normalized_parent_action_id})
    child = required_write_contract(action=action, source=source, risk_level=risk_level)
    child["workflow_id"] = parent_workflow_id
    child["action_id"] = _stable_identifier(
        "act",
        {"parent_action_id": normalized_parent_action_id, "slot": normalized_slot},
    )
    child["parent_action_id"] = normalized_parent_action_id
    return child


def _stable_identifier(prefix: str, identity: Mapping[str, object]) -> str:
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"{prefix}_{digest[:60]}"


def workflow_from_mapping(value: object) -> JSONDict:
    workflow = coerce_json_dict(value)
    if workflow.get("schema_version") != WORKFLOW_SCHEMA_VERSION:
        return {}
    policy = coerce_json_dict(workflow.get("policy"))
    if not policy:
        return {}
    if not _is_valid_workflow_contract(workflow, policy):
        return {}
    return {**workflow, "policy": policy}


def workflow_from_event(event: Mapping[str, object]) -> JSONDict:
    workflow = workflow_from_mapping(event.get(WORKFLOW_KEY))
    if workflow:
        return workflow
    payload = coerce_json_dict(event.get("payload"))
    return workflow_from_mapping(payload.get(WORKFLOW_KEY))


def workflow_from_task_state(state: Mapping[str, object] | None) -> JSONDict:
    if not isinstance(state, Mapping):
        return {}
    workflow = workflow_from_mapping(state.get(WORKFLOW_KEY))
    if workflow:
        return workflow
    payload = coerce_json_dict(state.get("payload"))
    return workflow_from_mapping(payload.get(WORKFLOW_KEY))


def ensure_event_workflow(event: Mapping[str, object], *, default_source: str = SOURCE_EXPLICIT_USER_REQUEST) -> JSONDict:
    workflow = workflow_from_event(event)
    if workflow:
        return workflow
    hitl_review = coerce_json_dict(event.get("hitl_review"))
    action = event.get("action")
    return required_write_contract(
        action=action,
        source=default_source,
        risk_level=hitl_review.get("risk_level"),
    )


def attach_workflow(target: JSONDict, workflow: Mapping[str, object]) -> JSONDict:
    copied = deepcopy(target)
    copied[WORKFLOW_KEY] = deepcopy(dict(workflow))
    payload = copied.get("payload")
    if isinstance(payload, dict):
        payload[WORKFLOW_KEY] = deepcopy(dict(workflow))
    return copied


def mark_auto_executable(
    workflow: Mapping[str, object],
    *,
    reason: object = None,
    source: object = None,
) -> JSONDict:
    """Convert a reviewed action contract into a system-authorized auto action."""

    current = workflow_from_mapping(workflow)
    if not current:
        return {}
    copied = deepcopy(dict(current))
    policy = deepcopy(coerce_json_dict(copied.get("policy")))
    policy["execution_policy"] = EXECUTION_AUTO_EXECUTE
    copied["policy"] = policy
    copied["status"] = STATUS_PLANNED
    if isinstance(reason, str) and reason.strip():
        copied["status_reason"] = reason.strip()
    if isinstance(source, str) and source.strip():
        copied["status_source"] = source.strip()
    return copied


def is_auto_execute_workflow(workflow: object) -> bool:
    workflow_json = workflow_from_mapping(workflow)
    policy = coerce_json_dict(workflow_json.get("policy"))
    return (
        workflow_json.get("status") in {STATUS_PLANNED, STATUS_RUNNING}
        and policy.get("execution_policy") == EXECUTION_AUTO_EXECUTE
    )


def mark_skipped(workflow: Mapping[str, object], *, reason: object = None, source: object = None) -> JSONDict:
    copied = deepcopy(dict(workflow))
    copied["status"] = STATUS_SKIPPED
    if isinstance(reason, str) and reason.strip():
        copied["status_reason"] = reason.strip()
    if isinstance(source, str) and source.strip():
        copied["status_source"] = source.strip()
    return copied


def mark_cancelled(workflow: Mapping[str, object], *, reason: object = None, source: object = None) -> JSONDict:
    copied = deepcopy(dict(workflow))
    copied["status"] = STATUS_CANCELLED
    if isinstance(reason, str) and reason.strip():
        copied["status_reason"] = reason.strip()
    if isinstance(source, str) and source.strip():
        copied["status_source"] = source.strip()
    return copied


def is_optional_skip_workflow(workflow: object) -> bool:
    workflow_json = workflow_from_mapping(workflow)
    policy = coerce_json_dict(workflow_json.get("policy"))
    return (
        policy.get("scope") == SCOPE_OPTIONAL_SUGGESTION
        and policy.get("on_reject") == ON_REJECT_SKIP_CONTINUE
        and policy.get("blocking") is False
    )


def is_optional_skip_interrupt(interrupt_payload: Mapping[str, object] | None) -> bool:
    if not isinstance(interrupt_payload, Mapping):
        return False
    return is_optional_skip_workflow(interrupt_payload.get(WORKFLOW_KEY))


def tool_name_for_action(action_type: object) -> str | None:
    if not isinstance(action_type, str):
        return None
    return _ACTION_TOOL_NAMES.get(action_type)


def action_capability(action_type: object) -> AgentActionCapability:
    action_name = action_type if isinstance(action_type, str) and action_type else "unknown"
    tool_name = tool_name_for_action(action_name)
    tool_spec = _tool_spec_for_action(action_name)
    is_write = bool(getattr(tool_spec, "is_write", False))
    requires_confirmation = bool(getattr(tool_spec, "requires_confirmation", False))
    override = _ACTION_CAPABILITY_OVERRIDES.get(action_name)
    default_requires_idempotency_key = is_write
    return AgentActionCapability(
        action_type=action_name,
        tool_name=tool_name,
        is_write=is_write,
        requires_confirmation=requires_confirmation,
        requires_user_authorization=is_write,
        allows_background_recovery=bool(
            override.allows_background_recovery
            if override and override.allows_background_recovery is not None
            else False
        ),
        parallel_safe=bool(
            override.parallel_safe
            if override and override.parallel_safe is not None
            else False
        ),
        requires_idempotency_key=bool(
            override.requires_idempotency_key
            if override and override.requires_idempotency_key is not None
            else default_requires_idempotency_key
        ),
        required_payload_fields=(
            override.required_payload_fields
            if override is not None
            else frozenset()
        ),
    )


def action_capabilities(action_type: object) -> frozenset[str]:
    return action_capability(action_type).flags


def action_requires_user_authorization(action_type: object) -> bool:
    return action_capability(action_type).requires_user_authorization


def action_allows_background_recovery(action_type: object) -> bool:
    return action_capability(action_type).allows_background_recovery


def action_is_parallel_safe(action_type: object) -> bool:
    return action_capability(action_type).parallel_safe


def action_requires_idempotency_key(action_type: object) -> bool:
    return action_capability(action_type).requires_idempotency_key


@lru_cache(maxsize=128)
def _tool_spec_for_action(action_type: str) -> object | None:
    tool_name = tool_name_for_action(action_type)
    if not tool_name:
        return None
    from app.services.agent.tool_registry import AgentToolRegistry

    try:
        return AgentToolRegistry().get(tool_name)
    except KeyError:
        return None


def _is_valid_workflow_contract(workflow: JSONDict, policy: JSONDict) -> bool:
    workflow_id = workflow.get("workflow_id")
    action_id = workflow.get("action_id")
    action_type = workflow.get("action_type")
    status = workflow.get("status")
    scope = policy.get("scope")
    source = policy.get("source")
    execution_policy = policy.get("execution_policy")
    on_reject = policy.get("on_reject")
    blocking = policy.get("blocking")
    return (
        isinstance(workflow_id, str)
        and workflow_id.startswith("wf_")
        and isinstance(action_id, str)
        and action_id.startswith("act_")
        and isinstance(action_type, str)
        and bool(action_type.strip())
        and status in _ALLOWED_STATUSES
        and scope in _ALLOWED_SCOPES
        and source in _ALLOWED_SOURCES
        and execution_policy in _ALLOWED_EXECUTION_POLICIES
        and on_reject in _ALLOWED_ON_REJECT
        and isinstance(blocking, bool)
    )

"""Checkpoint-safe contract for hidden PendingTask application steps.

LangGraph owns routing and durable continuation. Database/LLM/API work is
represented as an authenticated, deterministic interrupt and executed by the
application projection layer before the same child continuation is resumed.
"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import TYPE_CHECKING, Literal, TypedDict

from app.services.agent.types import JSONDict, coerce_json_dict, coerce_json_value

if TYPE_CHECKING:
    from app.services.agent.pending_continuation import PendingTaskContinuationRef
    from app.services.agent.state import PendingTaskEffectIntent

PENDING_APPLICATION_STEP_SCHEMA = "agent.pending_application_step.v1"
PENDING_APPLICATION_STEP_REASON = "pending_task_application_step"
PendingApplicationStepType = Literal[
    "task_transition",
    "preflight",
    "interaction",
    "turn_relation_assessment",
]


class PendingApplicationStepRequest(TypedDict):
    schema_version: str
    type: Literal["confirm"]
    reason: str
    internal: Literal[True]
    source_event: str
    business_action: Literal["execute_pending_application_step"]
    step_id: str
    step_type: PendingApplicationStepType
    checkpoint_ref: PendingTaskContinuationRef
    task_snapshot: JSONDict
    content: str
    turn_input: JSONDict
    interaction_metadata: JSONDict
    effect_intents: list[PendingTaskEffectIntent]


class PendingApplicationStepAcknowledgement(TypedDict, total=False):
    schema_version: str
    status: Literal["COMPLETED", "FAILED"]
    step_id: str
    result: JSONDict
    replayed: bool
    failure_reason: str
    retryable: bool


def build_pending_application_step_request(
    *,
    step_type: PendingApplicationStepType,
    continuation: PendingTaskContinuationRef,
    task_snapshot: object,
    content: str,
    turn_input: object = None,
    interaction_metadata: object = None,
    effect_intents: object = None,
) -> PendingApplicationStepRequest:
    request: PendingApplicationStepRequest = {
        "schema_version": PENDING_APPLICATION_STEP_SCHEMA,
        "type": "confirm",
        "reason": PENDING_APPLICATION_STEP_REASON,
        "internal": True,
        "source_event": "pending_task_application_step_requested",
        "business_action": "execute_pending_application_step",
        "step_id": "",
        "step_type": step_type,
        "checkpoint_ref": continuation,
        "task_snapshot": coerce_json_dict(task_snapshot),
        "content": str(content or ""),
        "turn_input": coerce_json_dict(turn_input),
        "interaction_metadata": coerce_json_dict(interaction_metadata),
        "effect_intents": [
            coerce_json_dict(intent)
            for intent in effect_intents or []
            if isinstance(intent, dict)
        ],
    }
    request["step_id"] = pending_application_step_id(request)
    return request


def pending_application_step_id(value: object) -> str:
    payload = coerce_json_dict(value)
    identity = {
        "schema_version": payload.get("schema_version"),
        "step_type": payload.get("step_type"),
        "checkpoint_ref": coerce_json_dict(payload.get("checkpoint_ref")),
        "task_snapshot": coerce_json_dict(payload.get("task_snapshot")),
        "content": payload.get("content"),
        "turn_input": coerce_json_dict(payload.get("turn_input")),
        "interaction_metadata": coerce_json_dict(payload.get("interaction_metadata")),
        "effect_intents": [
            coerce_json_dict(intent)
            for intent in payload.get("effect_intents") or []
            if isinstance(intent, dict)
        ],
    }
    digest = sha256(
        json.dumps(
            coerce_json_value(identity),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return f"pending_application_step:v1:{digest}"


def is_pending_application_step_request(value: object) -> bool:
    payload = coerce_json_dict(value)
    return (
        payload.get("schema_version") == PENDING_APPLICATION_STEP_SCHEMA
        and payload.get("reason") == PENDING_APPLICATION_STEP_REASON
        and payload.get("internal") is True
        and payload.get("business_action") == "execute_pending_application_step"
        and payload.get("step_type")
        in {"task_transition", "preflight", "interaction", "turn_relation_assessment"}
        and payload.get("step_id") == pending_application_step_id(payload)
    )


def completed_application_step_acknowledgement(
    request: PendingApplicationStepRequest,
    *,
    result: object,
    replayed: bool,
) -> PendingApplicationStepAcknowledgement:
    return {
        "schema_version": PENDING_APPLICATION_STEP_SCHEMA,
        "status": "COMPLETED",
        "step_id": request["step_id"],
        "result": coerce_json_dict(result),
        "replayed": replayed,
        "retryable": False,
    }

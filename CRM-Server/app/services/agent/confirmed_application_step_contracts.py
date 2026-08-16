"""Checkpoint-safe execution intent for user-confirmed Agent writes."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Literal, TypedDict

from app.services.agent.types import JSONDict, coerce_json_dict, coerce_json_value

CONFIRMED_APPLICATION_STEP_SCHEMA = "agent.confirmed_application_step.v1"
CONFIRMED_APPLICATION_STEP_TYPE = "confirmed_task_execution"


class ConfirmedApplicationStepRequest(TypedDict):
    schema_version: str
    step_id: str
    step_type: Literal["confirmed_task_execution"]
    action: str
    task_snapshot: JSONDict


def build_confirmed_application_step_request(
    *,
    task_snapshot: object,
    action: str,
) -> ConfirmedApplicationStepRequest:
    request: ConfirmedApplicationStepRequest = {
        "schema_version": CONFIRMED_APPLICATION_STEP_SCHEMA,
        "step_id": "",
        "step_type": CONFIRMED_APPLICATION_STEP_TYPE,
        "action": str(action or ""),
        "task_snapshot": coerce_json_dict(task_snapshot),
    }
    request["step_id"] = confirmed_application_step_id(request)
    return request


def confirmed_application_step_id(value: object) -> str:
    payload = coerce_json_dict(value)
    identity = {
        "schema_version": payload.get("schema_version"),
        "step_type": payload.get("step_type"),
        "action": payload.get("action"),
        "task_snapshot": coerce_json_dict(payload.get("task_snapshot")),
    }
    digest = sha256(
        json.dumps(
            coerce_json_value(identity),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return f"confirmed_application_step:v1:{digest}"


def is_confirmed_application_step_request(value: object) -> bool:
    payload = coerce_json_dict(value)
    return (
        payload.get("schema_version") == CONFIRMED_APPLICATION_STEP_SCHEMA
        and payload.get("step_type") == CONFIRMED_APPLICATION_STEP_TYPE
        and isinstance(payload.get("action"), str)
        and bool(payload.get("action"))
        and bool(coerce_json_dict(payload.get("task_snapshot")))
        and payload.get("step_id") == confirmed_application_step_id(payload)
    )

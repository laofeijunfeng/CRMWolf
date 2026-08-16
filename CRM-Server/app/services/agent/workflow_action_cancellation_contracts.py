"""Checkpoint-safe optimistic contract for cancelling one Agent workflow action."""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.agent import action_workflow
from app.services.agent.types import JSONDict, coerce_json_dict, coerce_json_value

if TYPE_CHECKING:
    from collections.abc import Mapping


def expected_task_cancellation_snapshot(task: object) -> JSONDict:
    """Capture only task fields that cancellation is allowed to compare/mutate."""

    status = getattr(task, "status", None)
    state = coerce_json_dict(getattr(task, "state_json", None))
    payload = coerce_json_dict(state.get("payload"))
    workflow = action_workflow.workflow_from_mapping(state.get("workflow"))
    payload_workflow = action_workflow.workflow_from_mapping(payload.get("workflow"))
    if not isinstance(status, str) or not status or not workflow:
        return {}
    return {
        "status": status,
        "workflow": workflow,
        "payload_workflow": payload_workflow,
    }


def expected_ledger_cancellation_snapshot(
    workflow: Mapping[str, object],
    *,
    task_id: int,
) -> JSONDict:
    """Derive the expected durable ledger state from the checkpointed workflow."""

    workflow_json = action_workflow.workflow_from_mapping(workflow)
    if not workflow_json:
        return {}
    status = workflow_json.get("status")
    if not isinstance(status, str) or not status:
        return {}
    return {
        "workflow_id": str(workflow_json["workflow_id"]),
        "action_id": str(workflow_json["action_id"]),
        "task_id": task_id,
        "status": status.upper(),
    }


def normalize_task_cancellation_snapshot(value: object) -> JSONDict:
    snapshot = coerce_json_dict(value)
    status = snapshot.get("status")
    workflow = action_workflow.workflow_from_mapping(snapshot.get("workflow"))
    payload_workflow = action_workflow.workflow_from_mapping(snapshot.get("payload_workflow"))
    if not isinstance(status, str) or not status or not workflow:
        return {}
    return {
        "status": status,
        "workflow": workflow,
        "payload_workflow": payload_workflow,
    }


def normalize_ledger_cancellation_snapshot(value: object) -> JSONDict:
    snapshot = coerce_json_dict(value)
    workflow_id = snapshot.get("workflow_id")
    action_id = snapshot.get("action_id")
    task_id = snapshot.get("task_id")
    status = snapshot.get("status")
    if (
        not isinstance(workflow_id, str)
        or not workflow_id
        or not isinstance(action_id, str)
        or not action_id
        or not isinstance(task_id, int)
        or not isinstance(status, str)
        or not status
    ):
        return {}
    return {
        "workflow_id": workflow_id,
        "action_id": action_id,
        "task_id": task_id,
        "status": status,
    }


def cancelled_task_snapshot(
    expected: Mapping[str, object],
    *,
    workflow: Mapping[str, object],
    reason: str,
) -> JSONDict:
    expected_json = normalize_task_cancellation_snapshot(expected)
    workflow_json = action_workflow.workflow_from_mapping(workflow)
    if not expected_json or not workflow_json:
        return {}
    cancelled = action_workflow.mark_cancelled(
        workflow_json,
        reason=reason,
        source="langgraph_resume",
    )
    return {
        "status": expected_json["status"],
        "workflow": cancelled,
        "payload_workflow": cancelled if expected_json.get("payload_workflow") else {},
    }


def task_snapshot_matches_workflow(snapshot: Mapping[str, object], workflow: Mapping[str, object]) -> bool:
    snapshot_json = normalize_task_cancellation_snapshot(snapshot)
    workflow_json = action_workflow.workflow_from_mapping(workflow)
    if not snapshot_json or not workflow_json:
        return False
    if snapshot_json.get("workflow") != workflow_json:
        return False
    payload_workflow = coerce_json_dict(snapshot_json.get("payload_workflow"))
    return not payload_workflow or payload_workflow == workflow_json


def cancellation_decision(
    decision: object,
    *,
    source_type: object,
) -> JSONDict:
    decision_json = coerce_json_dict(coerce_json_value(decision))
    if isinstance(source_type, str) and source_type:
        decision_json.setdefault("source_type", source_type)
    return decision_json

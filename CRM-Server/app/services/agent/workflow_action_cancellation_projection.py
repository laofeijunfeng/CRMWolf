"""Atomic optimistic projection for pending workflow cancellation intents."""
from __future__ import annotations

from dataclasses import dataclass

from app.crud.agent import agent_task_crud, agent_workflow_action_crud
from app.models.agent import AgentWorkflowActionStatus
from app.schemas.agent import AgentTaskUpdate, AgentWorkflowActionUpdate
from app.services.agent import action_workflow
from app.services.agent.types import JSONDict, coerce_json_dict
from app.services.agent.workflow_action_cancellation_contracts import (
    cancellation_decision,
    cancelled_task_snapshot,
    expected_ledger_cancellation_snapshot,
    expected_task_cancellation_snapshot,
    normalize_ledger_cancellation_snapshot,
    normalize_task_cancellation_snapshot,
    task_snapshot_matches_workflow,
)
from app.utils.time import business_now


class WorkflowActionCancellationConflict(ValueError):
    """The durable task/ledger no longer matches the checkpointed expectation."""


@dataclass
class WorkflowActionCancellationProjectionContext:
    db: object
    session: object
    team_id: int
    user_id: int
    commit: bool = True


@dataclass
class WorkflowActionCancellationProjectionResult:
    task: object
    ledger: object
    task_replayed: bool
    ledger_replayed: bool


def project_workflow_action_cancellation(
    intent: JSONDict,
    context: WorkflowActionCancellationProjectionContext,
) -> WorkflowActionCancellationProjectionResult:
    workflow = action_workflow.workflow_from_mapping(intent.get("workflow"))
    task_id = intent.get("task_id")
    reason = intent.get("reason")
    expected_task = normalize_task_cancellation_snapshot(intent.get("expected_task"))
    expected_ledger = normalize_ledger_cancellation_snapshot(intent.get("expected_ledger"))
    if not workflow or not isinstance(task_id, int) or not isinstance(reason, str):
        raise ValueError("pending workflow cancellation intent is invalid")
    if context.team_id <= 0 or context.user_id <= 0:
        raise ValueError("pending workflow cancellation requires exact team and user ownership")
    if not expected_task or not expected_ledger:
        raise ValueError("pending workflow cancellation intent lacks expected snapshots")
    if not task_snapshot_matches_workflow(expected_task, workflow):
        raise ValueError("pending workflow cancellation task snapshot does not match workflow")
    if expected_ledger != expected_ledger_cancellation_snapshot(workflow, task_id=task_id):
        raise ValueError("pending workflow cancellation ledger snapshot does not match workflow")

    task = agent_task_crud.get_by_id_for_update(
        context.db,
        task_id,
        team_id=context.team_id,
        user_id=context.user_id,
    )
    if task is None:
        raise WorkflowActionCancellationConflict("workflow cancellation optimistic conflict: task missing")
    if getattr(task, "team_id", None) != context.team_id or getattr(task, "user_id", None) != context.user_id:
        raise WorkflowActionCancellationConflict("workflow cancellation optimistic conflict: task ownership mismatch")
    session_id = getattr(context.session, "id", None)
    if not isinstance(session_id, int) or getattr(task, "session_id", None) != session_id:
        raise WorkflowActionCancellationConflict("workflow cancellation optimistic conflict: task session mismatch")

    ledger = agent_workflow_action_crud.get_by_action_id_for_update(
        context.db,
        str(workflow["action_id"]),
        team_id=context.team_id,
        user_id=context.user_id,
    )
    if ledger is None:
        raise WorkflowActionCancellationConflict("workflow cancellation optimistic conflict: ledger missing")
    if getattr(ledger, "team_id", None) != context.team_id or getattr(ledger, "user_id", None) != context.user_id:
        raise WorkflowActionCancellationConflict("workflow cancellation optimistic conflict: ledger ownership mismatch")
    if getattr(ledger, "workflow_id", None) != workflow["workflow_id"]:
        raise WorkflowActionCancellationConflict("workflow cancellation optimistic conflict: ledger workflow mismatch")
    if getattr(ledger, "session_id", None) != session_id:
        raise WorkflowActionCancellationConflict("workflow cancellation optimistic conflict: ledger session mismatch")

    desired_task = cancelled_task_snapshot(expected_task, workflow=workflow, reason=reason)
    current_task = expected_task_cancellation_snapshot(task)
    task_replayed = current_task == desired_task
    if not task_replayed and current_task != expected_task:
        raise WorkflowActionCancellationConflict("workflow cancellation optimistic conflict: task changed")

    decision = cancellation_decision(intent.get("decision"), source_type=intent.get("source_type"))
    current_ledger = _ledger_snapshot(ledger)
    desired_ledger = {
        **expected_ledger,
        "status": AgentWorkflowActionStatus.CANCELLED,
        "decision": decision,
        "reason": reason or None,
    }
    ledger_replayed = current_ledger == desired_ledger
    if not ledger_replayed and _expected_ledger_state(current_ledger) != expected_ledger:
        raise WorkflowActionCancellationConflict("workflow cancellation optimistic conflict: ledger changed")

    task_changed = not task_replayed
    ledger_changed = not ledger_replayed
    try:
        projected_task = task
        if task_changed:
            state = coerce_json_dict(getattr(task, "state_json", None))
            state["workflow"] = desired_task["workflow"]
            payload = coerce_json_dict(state.get("payload"))
            if expected_task.get("payload_workflow"):
                payload["workflow"] = desired_task["payload_workflow"]
                state["payload"] = payload
            projected_task = agent_task_crud.update(
                context.db,
                task,
                AgentTaskUpdate(state_json=state),
                commit=False,
            )
        if ledger_changed:
            ledger = agent_workflow_action_crud.update(
                context.db,
                ledger,
                AgentWorkflowActionUpdate(
                    task_id=task_id,
                    status=AgentWorkflowActionStatus.CANCELLED,
                    decision_json=decision or None,
                    status_reason=reason or None,
                    finished_time=business_now(),
                ),
                commit=False,
            )
        if context.commit and (task_changed or ledger_changed):
            context.db.commit()
            if task_changed:
                context.db.refresh(projected_task)
            if ledger_changed:
                context.db.refresh(ledger)
    except Exception:
        rollback = getattr(context.db, "rollback", None)
        if callable(rollback):
            rollback()
        raise

    return WorkflowActionCancellationProjectionResult(
        task=projected_task,
        ledger=ledger,
        task_replayed=task_replayed,
        ledger_replayed=ledger_replayed,
    )


def _expected_ledger_state(snapshot: JSONDict) -> JSONDict:
    return {
        key: snapshot.get(key)
        for key in ("workflow_id", "action_id", "task_id", "status")
    }


def _ledger_snapshot(ledger: object) -> JSONDict:
    return {
        "workflow_id": getattr(ledger, "workflow_id", None),
        "action_id": getattr(ledger, "action_id", None),
        "task_id": getattr(ledger, "task_id", None),
        "status": getattr(ledger, "status", None),
        "decision": coerce_json_dict(getattr(ledger, "decision_json", None)),
        "reason": getattr(ledger, "status_reason", None),
    }

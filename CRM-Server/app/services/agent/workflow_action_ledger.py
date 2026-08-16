"""Durable ledger for Agent workflow actions."""
from __future__ import annotations

import uuid
from collections.abc import Mapping

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.crud.agent import agent_workflow_action_crud
from app.models.agent import AgentWorkflowAction, AgentWorkflowActionStatus
from app.schemas.agent import AgentWorkflowActionCreate, AgentWorkflowActionUpdate
from app.services.agent import action_workflow
from app.services.agent.types import JSONDict, coerce_json_dict
from app.utils.time import business_now

SOURCE_AGENT_PLANNING = "agent_planning"
SOURCE_POST_COMMIT_PROJECTION = "post_commit_projection"
SOURCE_POST_COMMIT_RECONCILIATION = "post_commit_reconciliation"
SOURCE_PENDING_RESUME = "pending_resume"
SOURCE_MANUAL_RETRY = "manual_retry"
SOURCE_BACKGROUND_RECOVERY = "background_recovery"


def execution_state_for_action_ids(
    db: Session,
    *,
    action_ids: list[str],
    team_id: int,
    user_id: int | None,
    include_system_actions: bool = True,
) -> JSONDict:
    """Return durable action ids that are satisfied or terminal.

    Only EXECUTED actions satisfy dependencies. Other terminal statuses stop
    duplicate execution but do not unlock downstream actions.
    """

    actions = agent_workflow_action_crud.list_by_action_ids(
        db,
        action_ids,
        team_id=team_id,
        user_id=user_id,
        include_system_actions=include_system_actions,
    )
    satisfied: set[str] = set()
    running: set[str] = set()
    terminal: set[str] = set()
    for action in actions:
        if action.status == AgentWorkflowActionStatus.EXECUTED:
            satisfied.add(action.action_id)
        elif action.status == AgentWorkflowActionStatus.RUNNING:
            running.add(action.action_id)
        elif action.status in _EXECUTION_STOP_STATUSES:
            terminal.add(action.action_id)
    return {
        "satisfied_action_ids": sorted(satisfied),
        "running_action_ids": sorted(running),
        "terminal_action_ids": sorted(terminal),
    }


def create_or_update_waiting_action(
    db: Session,
    *,
    workflow: Mapping[str, object],
    team_id: int,
    user_id: int | None,
    session_id: int | None,
    task_id: int | None,
    source_type: str,
    payload: Mapping[str, object] | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    source_message_id: int | None = None,
) -> AgentWorkflowAction | None:
    workflow_json = action_workflow.workflow_from_mapping(workflow)
    if not workflow_json:
        return None
    policy = coerce_json_dict(workflow_json.get("policy"))
    action_id = str(workflow_json["action_id"])
    payload_json = coerce_json_dict(payload)
    dependency_json = coerce_json_dict(workflow_json.get("dependency_json"))
    create_in = AgentWorkflowActionCreate(
        workflow_id=str(workflow_json["workflow_id"]),
        action_id=action_id,
        parent_action_id=_optional_str(workflow_json.get("parent_action_id")),
        team_id=team_id,
        user_id=user_id,
        session_id=session_id,
        task_id=task_id,
        source_message_id=source_message_id,
        source_type=source_type,
        action_type=str(workflow_json["action_type"]),
        status=AgentWorkflowActionStatus.WAITING_USER,
        scope=str(policy["scope"]),
        source=str(policy["source"]),
        execution_policy=str(policy["execution_policy"]),
        on_reject=str(policy["on_reject"]),
        blocking=bool(policy["blocking"]),
        target_type=target_type,
        target_id=target_id,
        dependency_json=dependency_json or None,
        payload_json=payload_json or None,
    )
    try:
        db_obj = agent_workflow_action_crud.get_or_create(db, create_in)
        update_in = AgentWorkflowActionUpdate(
            task_id=task_id,
            source_message_id=source_message_id,
            status=AgentWorkflowActionStatus.WAITING_USER,
            target_type=target_type,
            target_id=target_id,
            dependency_json=dependency_json or None,
            payload_json=payload_json or None,
        )
        return agent_workflow_action_crud.update(db, db_obj, update_in)
    except SQLAlchemyError:
        db.rollback()
        raise


def mark_action_skipped(
    db: Session,
    *,
    workflow: Mapping[str, object],
    team_id: int,
    user_id: int | None,
    task_id: int | None = None,
    reason: str | None = None,
    source_type: str = SOURCE_PENDING_RESUME,
    decision: Mapping[str, object] | None = None,
    commit: bool = True,
) -> AgentWorkflowAction | None:
    workflow_json = action_workflow.workflow_from_mapping(workflow)
    if not workflow_json:
        return None
    db_obj = agent_workflow_action_crud.get_by_action_id(
        db,
        str(workflow_json["action_id"]),
        team_id=team_id,
        user_id=user_id,
    )
    if db_obj is None:
        return None
    decision_json = coerce_json_dict(decision)
    if source_type:
        decision_json.setdefault("source_type", source_type)
    update = AgentWorkflowActionUpdate(
        task_id=task_id,
        status=AgentWorkflowActionStatus.SKIPPED,
        decision_json=decision_json or None,
        status_reason=reason,
        finished_time=business_now(),
    )
    try:
        return agent_workflow_action_crud.update(db, db_obj, update, commit=commit)
    except SQLAlchemyError:
        db.rollback()
        raise


def mark_action_cancelled(
    db: Session,
    *,
    workflow: Mapping[str, object],
    team_id: int,
    user_id: int | None,
    task_id: int | None = None,
    reason: str | None = None,
    source_type: str = SOURCE_PENDING_RESUME,
    decision: Mapping[str, object] | None = None,
    commit: bool = True,
) -> AgentWorkflowAction | None:
    workflow_json = action_workflow.workflow_from_mapping(workflow)
    if not workflow_json:
        return None
    db_obj = agent_workflow_action_crud.get_by_action_id(
        db,
        str(workflow_json["action_id"]),
        team_id=team_id,
        user_id=user_id,
    )
    if db_obj is None:
        return None
    decision_json = coerce_json_dict(decision)
    if source_type:
        decision_json.setdefault("source_type", source_type)
    update = AgentWorkflowActionUpdate(
        task_id=task_id,
        status=AgentWorkflowActionStatus.CANCELLED,
        decision_json=decision_json or None,
        status_reason=reason,
        finished_time=business_now(),
    )
    try:
        return agent_workflow_action_crud.update(db, db_obj, update, commit=commit)
    except SQLAlchemyError:
        db.rollback()
        raise


def mark_action_running(
    db: Session,
    *,
    workflow: Mapping[str, object],
    team_id: int,
    user_id: int | None,
    session_id: int | None = None,
    task_id: int | None = None,
    source_type: str = SOURCE_AGENT_PLANNING,
    payload: Mapping[str, object] | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    reason: str | None = None,
) -> AgentWorkflowAction | None:
    return _upsert_action_status(
        db,
        workflow=workflow,
        team_id=team_id,
        user_id=user_id,
        session_id=session_id,
        task_id=task_id,
        source_type=source_type,
        status=AgentWorkflowActionStatus.RUNNING,
        payload=payload,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        started_time=business_now(),
        clear_finished_time=True,
    )


def mark_action_blocked(
    db: Session,
    *,
    workflow: Mapping[str, object],
    team_id: int,
    user_id: int | None,
    session_id: int | None = None,
    task_id: int | None = None,
    source_type: str = SOURCE_AGENT_PLANNING,
    payload: Mapping[str, object] | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    reason: str | None = None,
) -> AgentWorkflowAction | None:
    return _upsert_action_status(
        db,
        workflow=workflow,
        team_id=team_id,
        user_id=user_id,
        session_id=session_id,
        task_id=task_id,
        source_type=source_type,
        status=AgentWorkflowActionStatus.BLOCKED,
        payload=payload,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        finished_time=business_now(),
    )


def mark_action_executed(
    db: Session,
    *,
    workflow: Mapping[str, object],
    team_id: int,
    user_id: int | None,
    result: Mapping[str, object] | None = None,
    task_id: int | None = None,
) -> AgentWorkflowAction | None:
    workflow_json = action_workflow.workflow_from_mapping(workflow)
    if not workflow_json:
        return None
    db_obj = agent_workflow_action_crud.get_by_action_id(
        db,
        str(workflow_json["action_id"]),
        team_id=team_id,
        user_id=user_id,
    )
    if db_obj is None:
        return None
    try:
        return agent_workflow_action_crud.update(
            db,
            db_obj,
            AgentWorkflowActionUpdate(
                task_id=task_id,
                status=AgentWorkflowActionStatus.EXECUTED,
                result_json=coerce_json_dict(result) or None,
                finished_time=business_now(),
            ),
        )
    except SQLAlchemyError:
        db.rollback()
        raise


def mark_action_failed(
    db: Session,
    *,
    workflow: Mapping[str, object],
    team_id: int,
    user_id: int | None,
    error_message: str,
    task_id: int | None = None,
    result: Mapping[str, object] | None = None,
) -> AgentWorkflowAction | None:
    workflow_json = action_workflow.workflow_from_mapping(workflow)
    if not workflow_json:
        return None
    db_obj = agent_workflow_action_crud.get_by_action_id(
        db,
        str(workflow_json["action_id"]),
        team_id=team_id,
        user_id=user_id,
    )
    if db_obj is None:
        return None
    try:
        return agent_workflow_action_crud.update(
            db,
            db_obj,
            AgentWorkflowActionUpdate(
                task_id=task_id,
                status=AgentWorkflowActionStatus.FAILED,
                result_json=coerce_json_dict(result) or None,
                status_reason=error_message[:300],
                error_message=error_message,
                finished_time=business_now(),
            ),
        )
    except SQLAlchemyError:
        db.rollback()
        raise


def prepare_action_retry(
    db: Session,
    action: AgentWorkflowAction,
    *,
    retry_source: str = SOURCE_MANUAL_RETRY,
    reason: str | None = None,
) -> AgentWorkflowAction:
    """Move a failed or blocked action back to a recoverable state.

    This does not execute the CRM mutation. It only updates the durable action
    ledger so the normal LangGraph planner/HITL path can pick the action up
    again with its original risk policy intact.
    """

    if action.status not in _RETRYABLE_STATUSES:
        raise ValueError(f"Action status {action.status} cannot be retried")

    previous_status = action.status
    previous_error = action.error_message
    previous_reason = action.status_reason
    previous_result = coerce_json_dict(action.result_json)
    decision_json = _append_retry_decision(
        action.decision_json,
        retry_source=retry_source,
        reason=reason,
        previous_status=previous_status,
        previous_error=previous_error,
        previous_reason=previous_reason,
        previous_result=previous_result,
    )
    next_status = _retry_status_for_action(action)
    update = AgentWorkflowActionUpdate(
        status=next_status,
        decision_json=decision_json,
        result_json=None,
        status_reason=reason or f"retry_requested_from:{previous_status}",
        error_message=None,
        started_time=None,
        finished_time=None,
    )
    try:
        return agent_workflow_action_crud.update(db, action, update)
    except SQLAlchemyError:
        db.rollback()
        raise


def record_system_action(
    db: Session,
    *,
    team_id: int,
    action_type: str,
    source_type: str,
    status: str,
    workflow_id: str | None = None,
    action_id: str | None = None,
    user_id: int | None = None,
    session_id: int | None = None,
    task_id: int | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    parent_action_id: str | None = None,
    dependency: Mapping[str, object] | None = None,
    payload: Mapping[str, object] | None = None,
    result: Mapping[str, object] | None = None,
    reason: str | None = None,
    commit: bool = True,
) -> AgentWorkflowAction:
    resolved_workflow_id = workflow_id or f"wf_{uuid.uuid4().hex}"
    resolved_action_id = action_id or f"act_{uuid.uuid4().hex}"
    existing = agent_workflow_action_crud.get_by_action_id(
        db,
        resolved_action_id,
        team_id=team_id,
        user_id=user_id,
    )
    create_in = AgentWorkflowActionCreate(
        workflow_id=resolved_workflow_id,
        action_id=resolved_action_id,
        parent_action_id=_optional_str(parent_action_id),
        team_id=team_id,
        user_id=user_id,
        session_id=session_id,
        task_id=task_id,
        source_type=source_type,
        action_type=action_type,
        status=status,
        scope=action_workflow.SCOPE_DERIVED_AUTOMATION,
        source="system_automation",
        execution_policy="auto_execute",
        on_reject=action_workflow.ON_REJECT_ASK_CLARIFICATION,
        blocking=False,
        target_type=target_type,
        target_id=target_id,
        dependency_json=coerce_json_dict(dependency) or None,
        payload_json=coerce_json_dict(payload) or None,
        result_json=coerce_json_dict(result) or None,
        status_reason=reason,
    )
    try:
        db_obj = existing or agent_workflow_action_crud.create(db, create_in, commit=commit)
        return agent_workflow_action_crud.update(
            db,
            db_obj,
            AgentWorkflowActionUpdate(
                parent_action_id=_optional_str(parent_action_id),
                status=status,
                dependency_json=coerce_json_dict(dependency) or None,
                payload_json=coerce_json_dict(payload) or None,
                result_json=coerce_json_dict(result) or None,
                status_reason=reason,
                finished_time=business_now() if status in _TERMINAL_STATUSES else None,
            ),
            commit=commit,
        )
    except SQLAlchemyError:
        db.rollback()
        raise


def action_status_projection(action: AgentWorkflowAction) -> JSONDict:
    return {
        "id": action.id,
        "workflow_id": action.workflow_id,
        "action_id": action.action_id,
        "action_type": action.action_type,
        "status": action.status,
        "scope": action.scope,
        "blocking": action.blocking,
        "source_type": action.source_type,
        "task_id": action.task_id,
        "status_reason": action.status_reason,
    }


def _upsert_action_status(
    db: Session,
    *,
    workflow: Mapping[str, object],
    team_id: int,
    user_id: int | None,
    session_id: int | None,
    task_id: int | None,
    source_type: str,
    status: str,
    payload: Mapping[str, object] | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    reason: str | None = None,
    started_time: object | None = None,
    finished_time: object | None = None,
    clear_finished_time: bool = False,
) -> AgentWorkflowAction | None:
    workflow_json = action_workflow.workflow_from_mapping(workflow)
    if not workflow_json:
        return None
    policy = coerce_json_dict(workflow_json.get("policy"))
    action_id = str(workflow_json["action_id"])
    dependency_json = coerce_json_dict(workflow_json.get("dependency_json"))
    payload_json = coerce_json_dict(payload)
    create_in = AgentWorkflowActionCreate(
        workflow_id=str(workflow_json["workflow_id"]),
        action_id=action_id,
        parent_action_id=_optional_str(workflow_json.get("parent_action_id")),
        team_id=team_id,
        user_id=user_id,
        session_id=session_id,
        task_id=task_id,
        source_type=source_type,
        action_type=str(workflow_json["action_type"]),
        status=status,
        scope=str(policy["scope"]),
        source=str(policy["source"]),
        execution_policy=str(policy["execution_policy"]),
        on_reject=str(policy["on_reject"]),
        blocking=bool(policy["blocking"]),
        target_type=target_type,
        target_id=target_id,
        dependency_json=dependency_json or None,
        payload_json=payload_json or None,
        status_reason=reason,
    )
    try:
        db_obj = agent_workflow_action_crud.get_or_create(db, create_in)
        update_in = AgentWorkflowActionUpdate(
            task_id=task_id,
            status=status,
            target_type=target_type,
            target_id=target_id,
            dependency_json=dependency_json or None,
            payload_json=payload_json or None,
            status_reason=reason,
        )
        if started_time is not None:
            update_in.started_time = started_time  # type: ignore[assignment]
        if finished_time is not None:
            update_in.finished_time = finished_time  # type: ignore[assignment]
        if clear_finished_time:
            update_in.finished_time = None
        if _action_status_update_is_noop(db_obj, update_in):
            return db_obj
        return agent_workflow_action_crud.update(db, db_obj, update_in)
    except SQLAlchemyError:
        db.rollback()
        raise


def _action_status_update_is_noop(
    db_obj: AgentWorkflowAction,
    update_in: AgentWorkflowActionUpdate,
) -> bool:
    update_data = update_in.model_dump(exclude_unset=True)
    if not update_data:
        return True
    for field, value in update_data.items():
        current_value = getattr(db_obj, field)
        if field in {"started_time", "finished_time"} and current_value is not None and value is not None:
            continue
        if field in {"dependency_json", "payload_json", "result_json", "decision_json"}:
            if coerce_json_dict(current_value) != coerce_json_dict(value):
                return False
            continue
        if current_value != value:
            return False
    return True


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _retry_status_for_action(action: AgentWorkflowAction) -> str:
    if action.execution_policy == "auto_execute" or action.scope == action_workflow.SCOPE_DERIVED_AUTOMATION:
        return AgentWorkflowActionStatus.PLANNED
    return AgentWorkflowActionStatus.WAITING_USER


def _append_retry_decision(
    current_decision: object,
    *,
    retry_source: str,
    reason: str | None,
    previous_status: str,
    previous_error: str | None,
    previous_reason: str | None,
    previous_result: Mapping[str, object] | None,
) -> JSONDict:
    decision_json = coerce_json_dict(current_decision)
    retry_history = decision_json.get("retry_history")
    if not isinstance(retry_history, list):
        retry_history = []
    retry_entry: JSONDict = {
        "retry_source": retry_source,
        "requested_time": business_now().isoformat(),
        "previous_status": previous_status,
    }
    if reason:
        retry_entry["reason"] = reason
    if previous_error:
        retry_entry["previous_error_message"] = previous_error
    if previous_reason:
        retry_entry["previous_status_reason"] = previous_reason
    if previous_result:
        retry_entry["previous_result_json"] = previous_result
    retry_history.append(retry_entry)
    decision_json["retry_history"] = retry_history[-10:]
    decision_json["last_retry"] = retry_entry
    return decision_json


_TERMINAL_STATUSES = {
    AgentWorkflowActionStatus.EXECUTED,
    AgentWorkflowActionStatus.SKIPPED,
    AgentWorkflowActionStatus.FAILED,
    AgentWorkflowActionStatus.CANCELLED,
    AgentWorkflowActionStatus.BLOCKED,
}

_EXECUTION_STOP_STATUSES = {
    AgentWorkflowActionStatus.SKIPPED,
    AgentWorkflowActionStatus.FAILED,
    AgentWorkflowActionStatus.CANCELLED,
}

_RETRYABLE_STATUSES = {
    AgentWorkflowActionStatus.FAILED,
    AgentWorkflowActionStatus.BLOCKED,
}

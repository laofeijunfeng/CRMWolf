"""Durable audit ledger for system-owned Agent workflow actions."""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.crud.agent import agent_workflow_action_crud
from app.models.agent import AgentWorkflowAction, AgentWorkflowActionStatus
from app.schemas.agent import AgentWorkflowActionCreate, AgentWorkflowActionUpdate
from app.services.agent import action_workflow
from app.services.agent.types import coerce_json_dict
from app.utils.time import business_now

SOURCE_POST_COMMIT_PROJECTION = "post_commit_projection"
SOURCE_POST_COMMIT_RECONCILIATION = "post_commit_reconciliation"


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
    target_type: str | None = None,
    target_id: int | None = None,
    parent_action_id: str | None = None,
    dependency: Mapping[str, object] | None = None,
    payload: Mapping[str, object] | None = None,
    result: Mapping[str, object] | None = None,
    reason: str | None = None,
    commit: bool = True,
) -> AgentWorkflowAction:
    """Create or update one idempotent system-action audit record."""

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


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


_TERMINAL_STATUSES = {
    AgentWorkflowActionStatus.EXECUTED,
    AgentWorkflowActionStatus.SKIPPED,
    AgentWorkflowActionStatus.FAILED,
    AgentWorkflowActionStatus.CANCELLED,
    AgentWorkflowActionStatus.BLOCKED,
}

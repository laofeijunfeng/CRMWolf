"""Replay-safe projection of user-visible child tasks after confirmed writes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from app.crud.agent import AgentTaskCRUD, agent_task_crud
from app.models.agent import AgentTaskStatus
from app.schemas.agent import AgentTaskCreate
from app.services.agent import action_workflow, workflow_action_ledger
from app.services.agent.schemas import AgentHITLPolicy
from app.services.agent.types import JSONDict, coerce_json_dict, coerce_json_value
from app.services.agent.waiting_task_semantics import normalize_waiting_task_state


class NextWaitingTaskProjectionConflict(RuntimeError):
    """The same durable child slot was projected with a different contract."""


@dataclass(frozen=True)
class NextWaitingTaskSpec:
    slot: str
    action: str
    intent: str | None
    target_type: str | None
    target_id: int | None
    summary: str
    payload: JSONDict = field(default_factory=dict)
    state_context: JSONDict = field(default_factory=dict)
    required_tools: tuple[str, ...] = ()
    confirmation_summary: str = "等待确认业务操作"
    source_type: str = workflow_action_ledger.SOURCE_AGENT_PLANNING


@dataclass(frozen=True)
class NextWaitingTaskProjectionRequest:
    db: object
    parent_task: object
    team_id: int
    user_id: int
    session_id: int
    spec: NextWaitingTaskSpec


@dataclass(frozen=True)
class NextWaitingTaskProjectionResult:
    task: object
    workflow: JSONDict
    replayed: bool = False


class NextWaitingTaskProjector:
    """Own stable child workflow identity, task creation, and ledger binding."""

    def __init__(self, *, task_crud: AgentTaskCRUD | None = None) -> None:
        self.task_crud = task_crud or agent_task_crud

    def project(self, request: NextWaitingTaskProjectionRequest) -> NextWaitingTaskProjectionResult:
        _validate_parent_ownership(request)
        parent_state = coerce_json_dict(getattr(request.parent_task, "state_json", None))
        parent_workflow = action_workflow.workflow_from_task_state(parent_state)
        parent_action_id = str(parent_workflow.get("action_id") or "").strip()
        if not parent_action_id:
            parent_action_id = _fallback_parent_action_id(request.parent_task)

        workflow = action_workflow.stable_child_required_write_contract(
            parent_workflow=parent_workflow,
            parent_action_id=parent_action_id,
            slot=request.spec.slot,
            action=request.spec.action,
        )
        task_key = stable_task_key_for_action(str(workflow["action_id"]))
        state_json = normalize_waiting_task_state({
            "action": request.spec.action,
            "payload": coerce_json_dict(request.spec.payload),
            **coerce_json_dict(request.spec.state_context),
            "workflow": workflow,
            "hitl": AgentHITLPolicy(
                required_for_tools=list(request.spec.required_tools),
                confirmation_summary=request.spec.confirmation_summary,
            ).model_dump(exclude_none=True),
        })
        create_in = AgentTaskCreate(
            task_key=task_key,
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
            intent=request.spec.intent,
            status=AgentTaskStatus.WAITING_USER,
            target_type=request.spec.target_type,
            target_id=request.spec.target_id,
            summary=request.spec.summary,
            input_json=coerce_json_dict(request.spec.payload),
            state_json=state_json,
        )
        task, created = self.task_crud.get_or_create_by_task_key(request.db, create_in)
        _validate_existing_task(task, create_in)
        action = workflow_action_ledger.create_or_update_waiting_action(
            request.db,
            workflow=workflow,
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
            task_id=int(task.id),
            source_type=request.spec.source_type,
            payload=request.spec.payload,
            target_type=request.spec.target_type,
            target_id=request.spec.target_id,
        )
        if action is None:
            raise NextWaitingTaskProjectionConflict("next_task_workflow_projection_failed")
        if getattr(action, "task_id", None) != getattr(task, "id", None):
            raise NextWaitingTaskProjectionConflict("next_task_workflow_task_mismatch")
        return NextWaitingTaskProjectionResult(task=task, workflow=workflow, replayed=not created)


def stable_task_key_for_action(action_id: str) -> str:
    digest = hashlib.sha256(str(action_id).encode()).hexdigest()
    return f"task_{digest[:48]}"


def _fallback_parent_action_id(parent_task: object) -> str:
    task_key = str(getattr(parent_task, "task_key", "") or "").strip()
    task_id = getattr(parent_task, "id", None)
    if not task_key or not isinstance(task_id, int):
        raise NextWaitingTaskProjectionConflict("parent_task_missing_workflow_identity")
    digest = hashlib.sha256(f"{task_id}:{task_key}".encode()).hexdigest()
    return f"act_{digest[:60]}"


def _validate_parent_ownership(request: NextWaitingTaskProjectionRequest) -> None:
    task = request.parent_task
    if (
        getattr(task, "team_id", None) != request.team_id
        or getattr(task, "user_id", None) != request.user_id
    ):
        raise NextWaitingTaskProjectionConflict("parent_task_owner_mismatch")
    if getattr(task, "session_id", None) != request.session_id:
        raise NextWaitingTaskProjectionConflict("parent_task_session_mismatch")
    if not str(request.spec.slot or "").strip() or not str(request.spec.action or "").strip():
        raise NextWaitingTaskProjectionConflict("invalid_next_task_spec")


def _validate_existing_task(task: object, expected: AgentTaskCreate) -> None:
    expected_values = expected.model_dump()
    actual_values = {
        key: coerce_json_value(getattr(task, key, None))
        for key in expected_values
    }
    normalized_expected = {
        key: coerce_json_value(value)
        for key, value in expected_values.items()
    }
    if actual_values != normalized_expected:
        raise NextWaitingTaskProjectionConflict(
            "next_task_contract_mismatch:" + json.dumps(
                {
                    "task_key": expected.task_key,
                    "different_fields": sorted(
                        key for key in normalized_expected if actual_values.get(key) != normalized_expected.get(key)
                    ),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )


next_waiting_task_projector = NextWaitingTaskProjector()

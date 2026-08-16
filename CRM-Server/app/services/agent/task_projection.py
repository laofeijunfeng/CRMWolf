"""Checkpoint-safe Agent task mutation planning and durable projection contracts.

Pending-task LangGraph nodes operate on :class:`RuntimeAgentTaskView` instead of
mutating SQLAlchemy entities. Existing field collectors can use
``update_agent_task`` in both runtime modes: ORM tasks are persisted normally,
while runtime views stage a replay-safe ``AgentTaskUpdate`` for the application
projection layer.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Protocol, runtime_checkable

from app.crud.agent import agent_task_crud
from app.schemas.agent import AgentTaskUpdate
from app.services.agent.types import JSONDict, JSONValue, coerce_json_dict, coerce_json_value
from app.services.agent.waiting_task_semantics import normalize_waiting_task_state

TASK_UPDATE_FIELDS = (
    "intent",
    "status",
    "target_type",
    "target_id",
    "summary",
    "input_json",
    "state_json",
    "result_json",
    "error_message",
)

TASK_SNAPSHOT_FIELDS = (
    "id",
    "task_key",
    "team_id",
    "user_id",
    "session_id",
    "intent",
    "status",
    "target_type",
    "target_id",
    "summary",
    "input_json",
    "state_json",
    "result_json",
    "error_message",
    "created_time",
    "updated_time",
)

_SNAPSHOT_ALIASES = {
    "input_json": "input",
    "state_json": "state",
    "result_json": "result",
}


@runtime_checkable
class StagedAgentTask(Protocol):
    """Task facade capable of recording a graph-local durable update."""

    def stage_agent_task_update(self, update: AgentTaskUpdate) -> object:
        """Apply an update to the runtime view without touching the database."""


class RuntimeAgentTaskView:
    """Non-ORM task facade that records an optimistic durable projection."""

    def __init__(self, source: object) -> None:
        object.__setattr__(self, "_source", source)
        object.__setattr__(self, "_overrides", {})
        object.__setattr__(self, "_expected", {})
        object.__setattr__(self, "_update", {})

    @property
    def source_task(self) -> object:
        return object.__getattribute__(self, "_source")

    def __getattr__(self, name: str) -> object:
        overrides = object.__getattribute__(self, "_overrides")
        if name in overrides:
            return deepcopy(overrides[name])
        value = _source_value(object.__getattribute__(self, "_source"), name)
        return deepcopy(value) if name in TASK_UPDATE_FIELDS else value

    def __setattr__(self, name: str, value: object) -> None:
        if name in TASK_UPDATE_FIELDS:
            self.stage_agent_task_update(AgentTaskUpdate.model_validate({name: value}))
            return
        object.__getattribute__(self, "_overrides")[name] = deepcopy(value)

    def stage_agent_task_update(self, update: AgentTaskUpdate) -> RuntimeAgentTaskView:
        update_data = update.model_dump(exclude_unset=True)
        if isinstance(update_data.get("state_json"), Mapping):
            update_data["state_json"] = normalize_waiting_task_state(update_data["state_json"])
        expected = object.__getattribute__(self, "_expected")
        projected = object.__getattribute__(self, "_update")
        overrides = object.__getattribute__(self, "_overrides")
        source = object.__getattribute__(self, "_source")
        for field, value in update_data.items():
            if field not in TASK_UPDATE_FIELDS:
                raise ValueError(f"unsupported Agent task projection field: {field}")
            if field not in expected:
                expected[field] = _checkpoint_value(_source_value(source, field, None))
            checkpoint_value = _checkpoint_value(value)
            projected[field] = checkpoint_value
            overrides[field] = deepcopy(checkpoint_value)
        return self

    def projection_contract(self) -> tuple[JSONDict, JSONDict]:
        """Return expected/current values used for replay and conflict checks."""

        expected = object.__getattribute__(self, "_expected")
        projected = object.__getattribute__(self, "_update")
        return coerce_json_dict(deepcopy(expected)), coerce_json_dict(deepcopy(projected))


def runtime_agent_task_view(task: object) -> RuntimeAgentTaskView:
    """Return one stable runtime mutation facade for an Agent task."""

    if isinstance(task, RuntimeAgentTaskView):
        return task
    return RuntimeAgentTaskView(task)


def agent_task_snapshot(task: object | None) -> JSONDict:
    """Serialize the complete task view required by checkpointed workflows.

    The snapshot is the only task representation that may cross from the
    application/runtime boundary into PendingTask LangGraph state. It includes
    optimistic-concurrency fields as well as the payload used by field and
    choice workflows.
    """

    if task is None:
        return {}
    if isinstance(task, RuntimeAgentTaskView):
        task = task.source_task
    snapshot: JSONDict = {}
    for field in TASK_SNAPSHOT_FIELDS:
        value = _source_value(task, field, None)
        if value is not None:
            snapshot[field] = _checkpoint_value(value)
    return snapshot


def materialized_agent_task_snapshot(task: object | None) -> JSONDict:
    """Serialize the graph-visible task state, including staged mutations.

    ``agent_task_snapshot`` deliberately snapshots the owned application model
    behind a runtime view.  That is the correct representation when entering a
    graph.  Once a graph has staged an optimistic task transition, however, a
    following application step must receive the *materialized* graph state so
    its checkpoint identity and explicit task ownership remain stable across
    LangGraph node replay.
    """

    if task is None:
        return {}
    snapshot: JSONDict = {}
    for field in TASK_SNAPSHOT_FIELDS:
        value = _source_value(task, field, None)
        if value is not None:
            snapshot[field] = _checkpoint_value(value)
    return snapshot


def source_agent_task(task: object | None) -> object | None:
    """Return the owned ORM task behind a graph-local runtime facade."""

    if isinstance(task, RuntimeAgentTaskView):
        return task.source_task
    return task


def update_agent_task(
    db: object,
    task: object,
    update: AgentTaskUpdate,
    *,
    commit: bool = True,
) -> object:
    """Stage graph-local task changes or persist ordinary application changes."""

    update_data = update.model_dump(exclude_unset=True)
    if isinstance(update_data.get("state_json"), Mapping):
        update = AgentTaskUpdate.model_validate({
            **update_data,
            "state_json": normalize_waiting_task_state(update_data["state_json"]),
        })
    if isinstance(task, StagedAgentTask):
        return task.stage_agent_task_update(update)
    if commit:
        return agent_task_crud.update(db, task, update)
    return agent_task_crud.update(db, task, update, commit=False)


def task_projection_intent(task: object) -> JSONDict | None:
    """Build a stable checkpoint-safe intent for staged task mutations."""

    if not isinstance(task, RuntimeAgentTaskView):
        return None
    expected_task, task_update = task.projection_contract()
    if not task_update:
        return None
    task_id = _task_id(task)
    payload = {
        "expected_task": expected_task,
        "task_update": task_update,
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "intent_id": f"project_pending_task_state:{task_id}:{digest}",
        "intent_type": "project_pending_task_state",
        "task_id": task_id,
        **payload,
    }


def validate_task_projection_contract(
    expected_value: object,
    desired_value: object,
) -> tuple[JSONDict, JSONDict, AgentTaskUpdate]:
    """Validate one complete optimistic mutation contract from a checkpoint."""

    expected = coerce_json_dict(expected_value)
    desired = coerce_json_dict(desired_value)
    update = task_update_from_projection(desired)
    unknown_expected = sorted(set(expected) - set(TASK_UPDATE_FIELDS))
    if unknown_expected:
        raise ValueError("pending task projection has unsupported expected fields: " + ", ".join(unknown_expected))
    missing_expected = sorted(set(desired) - set(expected))
    if missing_expected:
        raise ValueError("pending task projection missing expected fields: " + ", ".join(missing_expected))
    unused_expected = sorted(set(expected) - set(desired))
    if unused_expected:
        raise ValueError("pending task projection has unused expected fields: " + ", ".join(unused_expected))
    return expected, desired, update


def task_matches_projection(task: object, values: JSONDict) -> bool:
    """Return whether all explicitly projected fields match durable task state."""

    return all(_checkpoint_value(getattr(task, field, None)) == value for field, value in values.items())


def task_projection_conflicts(task: object, expected: JSONDict, desired: JSONDict) -> list[str]:
    """Find fields changed concurrently to values outside expected/desired states."""

    conflicts: list[str] = []
    for field, desired_value in desired.items():
        current_value = _checkpoint_value(getattr(task, field, None))
        expected_value = expected.get(field)
        if current_value not in (expected_value, desired_value):
            conflicts.append(field)
    return conflicts


def task_update_from_projection(value: object) -> AgentTaskUpdate:
    """Validate a checkpoint payload at the application projection boundary."""

    payload = coerce_json_dict(value)
    unknown_fields = sorted(set(payload) - set(TASK_UPDATE_FIELDS))
    if unknown_fields:
        raise ValueError(f"pending task projection has unsupported fields: {', '.join(unknown_fields)}")
    if not payload:
        raise ValueError("pending task projection requires task_update")
    return AgentTaskUpdate.model_validate(payload)


def _task_id(task: object) -> int:
    value = getattr(task, "id", None)
    if not isinstance(value, int):
        raise ValueError("pending task projection requires integer task id")
    return value


def _source_value(source: object, field: str, default: object = ...) -> object:
    if isinstance(source, Mapping):
        if field in source:
            return source[field]
        alias = _SNAPSHOT_ALIASES.get(field)
        if alias is not None and alias in source:
            return source[alias]
        if default is not ...:
            return default
        raise AttributeError(field)
    if default is ...:
        return getattr(source, field)
    return getattr(source, field, default)


def _checkpoint_value(value: object) -> JSONValue:
    return coerce_json_value(deepcopy(value))

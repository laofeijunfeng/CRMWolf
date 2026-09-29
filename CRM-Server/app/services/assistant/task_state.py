"""Single write entry for assistant task state.

Every mutation of ``crm_assistant_tasks`` goes through
:func:`apply_task_update` with optimistic locking. Nothing else writes the
table. Actions are appended in the same transaction so the log stays a
faithful history of transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import ValidationError
from sqlalchemy import update as sql_update

from app.models.assistant import AssistantAction, AssistantTask, AssistantTaskStatus
from app.services.assistant.contracts import (
    Actor,
    TaskAuthority,
    TaskDraft,
    TaskStatus,
    TaskWaiting,
)
from app.utils.public_id import generate_public_id
from app.utils.time import business_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session


class TaskStateConflictError(RuntimeError):
    """Database compare-and-swap predicate failed; caller must re-read state."""


class InvalidTaskTransitionError(ValueError):
    """The requested transition is not allowed from the current state."""


_TERMINAL_STATUSES: frozenset[str] = frozenset({"COMPLETED", "CANCELLED", "FAILED"})


@dataclass(frozen=True)
class TaskUpdate:
    """One validated transition; all fields default to 'unchanged'."""

    status: TaskStatus | None = None
    # Require absence of a durable turn claim in the same database CAS.
    require_no_active_turn: bool = False
    activity_kind: str | None = None
    draft: TaskDraft | None = None
    waiting: TaskWaiting | None = None
    # Sentinel-free removal: clear_waiting=True sets waiting to None.
    clear_waiting: bool = False
    authority: TaskAuthority | None = None
    clear_frozen_activity_command: bool = False
    append_committed: list[dict[str, object]] | None = None
    error_code: str | None = None
    # Required audit trail entry for this transition.
    action_actor: Actor | None = None
    action_name: str | None = None
    action_input: dict[str, object] = field(default_factory=dict)
    action_result: dict[str, object] = field(default_factory=dict)
    event_type: str | None = None
    event_key: str | None = None
    correlation_id: str | None = None


@dataclass(frozen=True)
class TaskTransitionResult:
    task: AssistantTask
    action: AssistantAction


def load_draft(task: AssistantTask) -> TaskDraft:
    try:
        return TaskDraft.model_validate(task.draft_json or {})
    except ValidationError as exc:
        raise InvalidTaskTransitionError("task draft payload is not a valid TaskDraft") from exc


def load_waiting(task: AssistantTask) -> TaskWaiting | None:
    if task.waiting_type is None:
        return None
    payload: dict[str, object] = {"type": task.waiting_type, "field": task.waiting_field}
    stored = (task.waiting_json or {}).get("payload")
    if isinstance(stored, dict):
        payload.update({key: value for key, value in stored.items() if key in TaskWaiting.model_fields})
    payload.setdefault("question_id", f"q_{task.public_id}")
    payload.setdefault("prompt", f"请补充{task.waiting_field or '信息'}")
    payload["action_id"] = (task.waiting_json or {}).get("action_id")
    payload["expected_version"] = task.version
    return TaskWaiting.model_validate(payload)


def load_authority(task: AssistantTask) -> TaskAuthority:
    return TaskAuthority.model_validate(task.authority_json or {})


def _require_action(update: TaskUpdate) -> tuple[Actor, str]:
    if update.action_actor is None or not update.action_name:
        raise InvalidTaskTransitionError("every transition must record an action actor and name")
    return update.action_actor, update.action_name


def apply_task_update(db: Session, task: AssistantTask, update: TaskUpdate) -> TaskTransitionResult:
    """Persist one transition and its audit row in the caller's transaction.

    The database predicate, not the Session identity map or a prior SELECT,
    decides which competing writer owns a version.
    """

    actor, action_name = _require_action(update)
    if update.waiting is not None and update.clear_waiting:
        raise InvalidTaskTransitionError("cannot set and clear waiting in one transition")
    if task.status in _TERMINAL_STATUSES:
        raise InvalidTaskTransitionError(
            f"task {task.public_id} is terminal ({task.status}); no further transitions"
        )
    committed_activity = any(item.get("kind") == "customer_activity" for item in task.committed_json or [])
    if committed_activity:
        if update.activity_kind is not None and update.activity_kind != task.activity_kind:
            raise InvalidTaskTransitionError("committed activity kind cannot change")
        if update.draft is not None and update.draft.model_dump(mode="json") != task.draft_json:
            raise InvalidTaskTransitionError("committed activity draft cannot change")
        if update.append_committed and any(item.get("kind") == "customer_activity" for item in update.append_committed):
            raise InvalidTaskTransitionError("customer activity has already been committed")
    if update.status == AssistantTaskStatus.COMPLETED and not committed_activity and not any(
        item.get("kind") == "customer_activity" for item in update.append_committed or []
    ):
        raise InvalidTaskTransitionError("task cannot complete without a committed customer activity")

    now: datetime = business_now()
    values: dict[str, object] = {
        "version": task.version + 1,
        "last_modified_time": now,
    }
    if update.status is not None:
        values["status"] = update.status
    if update.activity_kind is not None:
        values["activity_kind"] = update.activity_kind
    if update.draft is not None:
        values["draft_json"] = update.draft.model_dump(mode="json")
    if update.clear_waiting:
        values.update(waiting_type=None, waiting_field=None, waiting_json={})
    elif update.waiting is not None:
        values.update(
            waiting_type=update.waiting.type,
            waiting_field=update.waiting.field,
            waiting_json={
                "payload": update.waiting.model_dump(mode="json", exclude={"type", "field", "expected_version"}),
                "action_id": update.waiting.action_id or generate_public_id("awa"),
            },
        )
    if update.authority is not None or update.clear_frozen_activity_command:
        merged = dict(task.authority_json or {})
        if update.authority is not None:
            merged.update(update.authority.model_dump(mode="json", exclude_none=True))
        if update.clear_frozen_activity_command:
            merged.pop("frozen_activity_command", None)
        values["authority_json"] = merged
    if update.append_committed:
        values["committed_json"] = [*(task.committed_json or []), *update.append_committed]
    if update.error_code is not None:
        values["last_error_code"] = update.error_code
    # Count chooser reservations before the model call, not every model-authored observation.
    if action_name == "chooser_nomination":
        if actor != "SYSTEM":
            raise InvalidTaskTransitionError("chooser reservation must be system-authored")
        if task.budget_steps >= task.budget_max_steps:
            raise InvalidTaskTransitionError("chooser nomination budget exhausted")
        values["budget_steps"] = task.budget_steps + 1

    statement = sql_update(AssistantTask).where(
        AssistantTask.id == task.id,
        AssistantTask.team_id == task.team_id,
        AssistantTask.version == task.version,
        AssistantTask.status == AssistantTaskStatus.ACTIVE,
    )
    if update.require_no_active_turn:
        statement = statement.where(AssistantTask.active_turn_id.is_(None))
    changed = db.execute(statement.values(**values).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise TaskStateConflictError(f"task {task.public_id} version/status/turn ownership changed")

    db.refresh(task)
    action = AssistantAction(
        public_id=generate_public_id("asa"),
        task_id=task.id,
        team_id=task.team_id,
        actor=actor,
        action=action_name,
        input_json=update.action_input,
        result_json=update.action_result,
        event_type=update.event_type,
        event_key=update.event_key,
        correlation_id=update.correlation_id,
        created_time=now,
    )
    db.add(action)
    db.flush()
    return TaskTransitionResult(task=task, action=action)

"""Shared task transitions; no HTTP transport or conversation persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.assistant.contracts import DraftField
from app.services.assistant.task_state import InvalidTaskTransitionError, TaskUpdate, apply_task_update, load_draft

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.assistant import AssistantTask


def reset_activity_kind(db: Session, task: AssistantTask, kind: str) -> AssistantTask:
    """Keep the pre-existing reset semantics and customer binding in one CAS."""
    if (
        task.status != "ACTIVE"
        or task.active_turn_id is not None
        or any(item.get("kind") == "customer_activity" for item in task.committed_json or [])
    ):
        raise InvalidTaskTransitionError("当前任务不能修改活动类型")
    if kind not in {"FOLLOW_UP", "ONLINE_MEETING", "OFFLINE_MEETING"}:
        raise InvalidTaskTransitionError("未知活动类型")
    draft = load_draft(task)
    reset = draft.model_copy(
        update={
            **{
                name: DraftField(status="MISSING")
                for name in (
                    "content",
                    "next_action",
                    "next_follow_time",
                    "meeting_subject",
                    "participants",
                    "quality_score",
                )
            },
            "content_json": {},
            "score_reason": None,
            "score_detail": {},
        }
    )
    return apply_task_update(
        db,
        task,
        TaskUpdate(
            require_no_active_turn=True,
            activity_kind=kind,
            draft=reset,
            clear_frozen_activity_command=True,
            clear_waiting=True,
            action_actor="USER",
            action_name="change_kind",
            action_input={"kind": kind},
            action_result={"accepted": True, "cleared": ["content", "next_action", "meeting_subject", "participants"]},
        ),
    ).task

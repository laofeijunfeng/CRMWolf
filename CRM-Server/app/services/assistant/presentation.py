"""Server-owned task projection, independent from HTTP and model runtimes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.assistant_turn import AssistantTurn
from app.schemas.assistant import AssistantTaskView

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.assistant import AssistantTask


def task_view(task: AssistantTask, db: Session) -> AssistantTaskView:
    from app.services.assistant.task_state import load_draft, load_waiting

    turn = None
    if task.active_turn_id is not None:
        turn = (
            db.query(AssistantTurn)
            .filter_by(
                id=task.active_turn_id,
                task_id=task.id,
                team_id=task.team_id,
                user_id=task.user_id,
            )
            .one_or_none()
        )
        if turn is None:
            raise ValueError("active assistant turn does not belong to the task")
    from app.services.assistant.turns import reprocess_allowed

    candidate = turn
    if candidate is None:
        candidate = (
            db.query(AssistantTurn)
            .filter_by(task_id=task.id, team_id=task.team_id, user_id=task.user_id)
            .order_by(AssistantTurn.id.desc())
            .first()
        )
    reprocess_turn_id = (
        candidate.public_id if candidate is not None and reprocess_allowed(db, task, candidate) else None
    )

    # Validate persistence values (including closed statuses and receipt unions) at this boundary.
    return AssistantTaskView.model_validate(
        {
            "last_modified_time": task.last_modified_time.isoformat() if task.last_modified_time else None,
            "public_id": task.public_id,
            "status": task.status,
            "goal": task.goal,
            "activity_kind": task.activity_kind,
            "draft": load_draft(task),
            "waiting": load_waiting(task),
            "committed": task.committed_json or [],
            "budget_steps": task.budget_steps,
            "budget_max_steps": task.budget_max_steps,
            "version": task.version,
            "processing_turn_id": turn.public_id if turn is not None else None,
            "processing_turn_status": turn.status if turn is not None else None,
            "reprocess_turn_id": reprocess_turn_id,
        }
    )

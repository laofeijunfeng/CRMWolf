"""Server-owned task projection, independent from HTTP and model runtimes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.assistant_turn import AssistantTurn
from app.schemas.assistant import AssistantTaskView
from app.services.assistant.open_follow_up_disposition import public_disposition

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.assistant import AssistantTask


def task_view(task: AssistantTask, db: Session) -> AssistantTaskView:
    from app.services.assistant.proposals import has_unresolved_proposal_claim
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
    reconciliation_required = task.last_error_code == "UNKNOWN_COMMIT_RESULT" or has_unresolved_proposal_claim(db, task)

    # Validate persistence values (including closed statuses and receipt unions) at this boundary.
    return AssistantTaskView.model_validate(
        {
            "last_modified_time": task.last_modified_time.isoformat() if task.last_modified_time else None,
            "public_id": task.public_id,
            "status": task.status,
            "goal": task.goal,
            "activity_kind": task.activity_kind,
            "task_kind": task.task_kind,
            "draft": load_draft(task),
            "waiting": None if reconciliation_required else load_waiting(task),
            "committed": task.committed_json or [],
            "budget_steps": task.budget_steps,
            "budget_max_steps": task.budget_max_steps,
            "version": task.version,
            "processing_turn_id": turn.public_id if turn is not None else None,
            "processing_turn_status": turn.status if turn is not None else None,
            "reprocess_turn_id": reprocess_turn_id,
            "follow_up_disposition": public_disposition(task),
            "proposal_outcome": (task.authority_json or {}).get("proposal_outcome"),
            "reconciliation_required": reconciliation_required,
            "profile_proposals": _profile_rows(task, db),
        }
    )


def _profile_rows(task: AssistantTask, db: Session) -> list[dict[str, object]] | None:
    """Each accepted item shows its own child task's status and receipt; the list never merges them."""

    from app.models.assistant import AssistantTask as TaskRow
    from app.services.assistant.profile_proposals import format_extracted_summary, profile_row_label
    from app.services.assistant.task_state import load_authority, load_waiting

    items = load_authority(task).profile_proposals
    if not items:
        return None
    ids = [item.child_task_public_id for item in items if item.child_task_public_id]
    children = {
        child.public_id: child
        for child in db.query(TaskRow).filter(
            TaskRow.team_id == task.team_id, TaskRow.user_id == task.user_id, TaskRow.parent_task_id == task.id,
            TaskRow.public_id.in_(ids),
        )
    } if ids else {}
    rows: list[dict[str, object]] = []
    for index, item in enumerate(items):
        child = children.get(item.child_task_public_id or "")
        waiting = load_waiting(child) if child is not None else None
        receipt = (child.committed_json or [None])[0] if child is not None else None
        label = profile_row_label(item.kind)
        rows.append({
            "index": index, "kind": item.kind, "label": label, "summary": item.summary,
            "quote": item.quote, "extracted_summary": format_extracted_summary(item.kind, item.extracted),
            "decision": item.decision, "child_task_public_id": item.child_task_public_id,
            "child_status": child.status if child is not None else None,
            "child_waiting_type": waiting.type if waiting is not None else None,
            "child_receipt": receipt,
        })
    return rows

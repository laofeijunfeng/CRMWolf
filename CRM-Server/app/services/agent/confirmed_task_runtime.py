"""Runtime for executing user-confirmed Agent tasks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.agent import interactions, session_state, task_execution


@dataclass
class ConfirmedTaskExecutionResult:
    tool_event: Optional[dict[str, Any]]
    task_event: dict[str, Any]
    assistant_content: str


class AgentConfirmedTaskRuntime:
    """Executes confirmed write tasks and returns transport-neutral events."""

    async def execute(
        self,
        db: Session,
        task,
        *,
        session,
        team_id: int,
        user_id: int,
        authorization: str,
    ) -> ConfirmedTaskExecutionResult:
        result, assistant_content = await task_execution._execute_waiting_task(
            db,
            task,
            session=session,
            team_id=team_id,
            user_id=user_id,
            authorization=authorization,
        )
        if result and result.success:
            session_state._clear_pending_task(db, session, task.id)

        task_event: dict[str, Any] = {
            "event": "task_completed" if result and result.success else "task_failed",
            "task_id": task.id,
            "content": assistant_content,
        }
        task_action = (task.state_json or {}).get("action")
        next_task = (
            session_state._get_current_waiting_task(db, session, team_id, user_id)
            if result and result.success and interactions._should_offer_next_pending_task(task_action)
            else None
        )
        if next_task and next_task.id != task.id:
            task_event["next_task_id"] = next_task.id
            task_event["interaction"] = interactions._pending_task_interaction(
                next_task,
                assistant_content,
                db=db,
                team_id=team_id,
            )

        return ConfirmedTaskExecutionResult(
            tool_event=result.to_event() if result else None,
            task_event=task_event,
            assistant_content=assistant_content,
        )


agent_confirmed_task_runtime = AgentConfirmedTaskRuntime()

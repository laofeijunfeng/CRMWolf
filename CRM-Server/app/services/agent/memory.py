"""Memory helpers for CRM AI Agent."""
from __future__ import annotations

from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.crud.agent import agent_message_crud, agent_task_crud
from app.models.agent import AgentTaskStatus
from app.services.agent.schemas import AgentMemorySnapshot


class AgentMemoryService:
    """Builds compact Agent memory from Agent-owned persistence only."""

    def load_snapshot(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        session_context: Optional[Dict[str, object]] = None,
        message_limit: int = 12,
    ) -> AgentMemorySnapshot:
        messages, total = agent_message_crud.list_by_session(
            db,
            session_id=session_id,
            team_id=team_id,
            user_id=user_id,
            skip=0,
            limit=message_limit,
        )
        if total > message_limit:
            messages, _ = agent_message_crud.list_by_session(
                db,
                session_id=session_id,
                team_id=team_id,
                user_id=user_id,
                skip=total - message_limit,
                limit=message_limit,
            )
        recent_messages = [
            {
                "role": message.role,
                "event_type": message.event_type,
                "content": message.content,
                "created_time": message.created_time.isoformat() if message.created_time else None,
            }
            for message in messages[-message_limit:]
            if message.content
        ]
        recent_follow_up_tasks = _recent_follow_up_tasks_from_messages(messages)
        pending_task = agent_task_crud.get_latest_waiting(
            db,
            session_id=session_id,
            team_id=team_id,
            user_id=user_id,
        )
        pending_task_json = None
        if pending_task and pending_task.status == AgentTaskStatus.WAITING_USER:
            pending_task_json = {
                "id": pending_task.id,
                "intent": pending_task.intent,
                "target_type": pending_task.target_type,
                "target_id": pending_task.target_id,
                "summary": pending_task.summary,
                "state": pending_task.state_json,
            }
        return AgentMemorySnapshot(
            recent_messages=recent_messages,
            pending_task=pending_task_json,
            session_context=session_context or {},
            recent_follow_up_tasks=recent_follow_up_tasks,
        )


agent_memory_service = AgentMemoryService()


def _recent_follow_up_tasks_from_messages(messages: list[object]) -> list[dict[str, object]]:
    tasks: list[dict[str, object]] = []
    seen: set[str] = set()
    for message in reversed(messages):
        payload = getattr(message, "payload_json", None)
        if not isinstance(payload, dict):
            continue
        for event in reversed(_dict_list(payload.get("trace_events"))):
            for task in reversed(_dict_list(event.get("recent_follow_up_tasks"))):
                task_id = str(task.get("id") or task.get("task_id") or "").strip()
                if not task_id.startswith("fut_") or task_id in seen:
                    continue
                seen.add(task_id)
                tasks.append({
                    "id": task_id,
                    "title": str(task.get("title") or "").strip(),
                    "customer_name": str(task.get("customer_name") or "").strip(),
                    "status": str(task.get("status") or "").strip(),
                    "due_at": task.get("due_at"),
                    "source": "agent_read_tool",
                })
                if len(tasks) >= 20:
                    return tasks
    return tasks


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]

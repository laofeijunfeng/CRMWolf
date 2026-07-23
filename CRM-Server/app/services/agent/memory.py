"""Memory helpers for CRM AI Agent."""
from __future__ import annotations

from typing import Any, Dict, Optional

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
        session_context: Optional[Dict[str, Any]] = None,
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
        )


agent_memory_service = AgentMemoryService()


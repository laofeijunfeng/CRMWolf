"""Runtime for normal Agent turns without an active pending task."""
from __future__ import annotations

from typing import Any, AsyncGenerator, Optional

from sqlalchemy.orm import Session

from app.services.agent import crm_agent_graph_service, session_state, task_factory


class AgentNewFlowRuntime:
    """Streams main graph events and applies CRM-side event effects."""

    async def stream_events(
        self,
        db: Session,
        *,
        session,
        team_id: int,
        user_id: int,
        content: str,
        authorization: str,
        switch_notice: Optional[str],
        assistant_ref: dict[str, Any],
        graph_service=None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        graph = graph_service or crm_agent_graph_service
        async for event in graph.stream_events({
            "db": db,
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session.id,
            "session_context": session.context_json or {},
            "content": content,
            "authorization": authorization,
        }):
            if task_factory._is_waiting_task_event(event):
                task_factory._create_waiting_task_from_event(db, event, team_id, user_id, session)
            if event.get("event") == "business_context_loaded":
                session_state._remember_current_customer(db, session, event.get("customer"))
            if event.get("event") == "final":
                assistant_ref["content"] = event.get("content")
                if switch_notice and assistant_ref["content"]:
                    event = {**event, "content": f"{switch_notice}\n\n{assistant_ref['content']}"}
                    assistant_ref["content"] = event["content"]
            yield event


agent_new_flow_runtime = AgentNewFlowRuntime()

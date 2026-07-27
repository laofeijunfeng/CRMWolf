"""Non-browser Agent conversation adapter for IM channels."""
import json
from datetime import timedelta
from typing import Any, Dict, List, Optional

from fastapi.security import HTTPAuthorizationCredentials

from app.core.security import create_access_token
from app.schemas.agent import AgentChatRequest


class AgentIMConversationService:
    """Collect the existing Agent SSE turn into an IM-friendly result."""

    process_events = {
        "agent_step",
        "business_context_loaded",
        "pending_interruption_assessed",
        "pending_task_interrupted",
        "tool_result",
        "message",
        "session",
        "done",
    }

    async def handle_message(
        self,
        *,
        content: str,
        team_id: int,
        user_id: int,
        session_id: Optional[int] = None,
        session_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        from app.api.agent import stream_agent_chat

        token = create_access_token(
            {"sub": str(user_id), "team_id": team_id},
            expires_delta=timedelta(minutes=10),
        )
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        response = await stream_agent_chat(
            AgentChatRequest(content=content, session_id=session_id, session_key=session_key),
            team_id=team_id,
            current_user=type("AgentUser", (), {"id": user_id})(),
            credentials=credentials,
        )

        events: List[Dict[str, Any]] = []
        final_content = ""
        interaction = None
        session_payload = None

        async for chunk in response.body_iterator:
            text = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
            for block in text.split("\n\n"):
                if not block.startswith("data: "):
                    continue
                try:
                    event = json.loads(block[6:])
                except ValueError:
                    continue
                events.append(event)
                if event.get("event") == "session":
                    session_payload = event
                if event.get("event") == "final":
                    final_content = str(event.get("content") or "")
                    interaction = event.get("interaction") or interaction
                elif event.get("interaction"):
                    interaction = event.get("interaction")

        return {
            "session": session_payload,
            "final_content": final_content or "Agent 已完成处理。",
            "interaction": interaction,
            "events": events,
            "im_events": [event for event in events if event.get("event") not in self.process_events],
        }


agent_im_conversation_service = AgentIMConversationService()

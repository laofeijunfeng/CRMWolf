"""Non-browser Agent conversation adapter for IM channels."""
from datetime import timedelta
from typing import Dict, List, Optional

from app.core.security import create_access_token
from app.services.agent import agent_copy
from app.services.agent.application import agent_application_service
from app.services.agent.input import AgentTurnInput


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
        turn_input: Optional[AgentTurnInput] = None,
    ) -> Dict[str, object]:
        token = create_access_token(
            {"sub": str(user_id), "team_id": team_id},
            expires_delta=timedelta(minutes=10),
        )
        authorization = f"Bearer {token}"

        events: List[Dict[str, object]] = []
        final_content = ""
        interaction = None
        session_payload = None

        async for event in agent_application_service.stream_chat_events(
            content=content,
            team_id=team_id,
            user_id=user_id,
            authorization=authorization,
            session_id=session_id,
            session_key=session_key,
            turn_input=turn_input,
        ):
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
            "final_content": final_content or agent_copy.generic_completed(),
            "interaction": interaction,
            "events": events,
            "im_events": [event for event in events if event.get("event") not in self.process_events],
        }


agent_im_conversation_service = AgentIMConversationService()

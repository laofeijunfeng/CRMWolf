"""Non-browser adapter over the single Agent UI application protocol."""
from datetime import timedelta
from typing import Dict, List, Optional
from uuid import UUID

from app.core.security import create_access_token
from app.schemas.agent import AgentSSEAgentUIFinalEvent, AgentSSESessionEvent
from app.services.agent import agent_copy
from app.services.agent.application import agent_application_service
from app.services.agent.input import AgentChannelContext
from app.services.agent.ui.schemas import (
    AgentChatInput,
    AgentUIFinalStreamEvent,
    InteractionBlock,
    TextBlock,
)


class AgentIMConversationService:
    """Collect one Agent UI stream turn into an IM-friendly projection."""

    async def handle_message(
        self,
        *,
        request_input: AgentChatInput,
        client_request_id: UUID,
        channel_context: AgentChannelContext,
        team_id: int,
        user_id: int,
        session_id: Optional[int] = None,
        session_key: Optional[str] = None,
    ) -> Dict[str, object]:
        token = create_access_token(
            {"sub": str(user_id), "team_id": team_id},
            expires_delta=timedelta(minutes=10),
        )
        authorization = f"Bearer {token}"

        events: List[Dict[str, object]] = []
        final_event: AgentUIFinalStreamEvent | None = None
        session_payload: Dict[str, object] | None = None

        async for event in agent_application_service.stream_chat_events(
            request_input=request_input,
            client_request_id=client_request_id,
            channel_context=channel_context,
            team_id=team_id,
            user_id=user_id,
            authorization=authorization,
            session_id=session_id,
            session_key=session_key,
        ):
            payload = event.model_dump(mode="json", exclude_none=True)
            events.append(payload)
            if isinstance(event.root, AgentSSESessionEvent):
                session_payload = payload
            elif isinstance(event.root, AgentSSEAgentUIFinalEvent):
                final_event = AgentUIFinalStreamEvent.model_validate(payload)

        if final_event is None:
            return {
                "session": session_payload,
                "message": None,
                "final_content": agent_copy.generic_completed(),
                "interaction": None,
                "events": events,
            }

        message = final_event.message
        interaction = next(
            (block.model_dump(mode="json") for block in message.blocks if isinstance(block, InteractionBlock)),
            None,
        )
        final_content = message.metadata.accessibility_label or next(
            (block.text for block in message.blocks if isinstance(block, TextBlock)),
            agent_copy.generic_completed(),
        )
        return {
            "session": session_payload,
            "message": message.model_dump(mode="json"),
            "final_content": final_content,
            "interaction": interaction,
            "events": events,
        }


agent_im_conversation_service = AgentIMConversationService()

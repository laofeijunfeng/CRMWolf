"""Unified IM entrypoint for Agent conversations."""
import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.crud.im_bot import agent_channel_session_crud, im_inbound_event_crud
from app.services.agent.input import AgentTurnInput
from app.services.agent.im_conversation import agent_im_conversation_service


logger = logging.getLogger(__name__)


class IMAgentGateway:
    """Normalize IM channel events before entering the Agent."""

    confirmation_emojis = {"Get", "Yes", "CheckMark", "OK", "THUMBSUP", "DONE", "JIAYI", "LGTM"}
    rejection_emojis = {"No", "CrossMark", "ThumbsDown", "MinusOne"}

    async def handle_text(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        provider: str,
        session_id: int,
        user_text: str,
        agent_content: str,
    ) -> Dict[str, Any]:
        return await agent_im_conversation_service.handle_message(
            content=agent_content,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            turn_input=AgentTurnInput.text(
                agent_content,
                source="im",
                provider=provider,
                metadata={"raw_text": user_text},
            ),
        )

    async def handle_reaction(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        provider: str,
        response_message_id: str,
        emoji_type: str,
    ) -> Optional[Dict[str, Any]]:
        intent = self.intent_from_emoji(emoji_type)
        if not intent:
            return None

        source_event = im_inbound_event_crud.get_by_response_message_id(
            db,
            provider=provider,
            response_message_id=response_message_id,
            team_id=team_id,
        )
        source_message = (((source_event.raw_event or {}) if source_event else {}).get("message") or {})
        chat_id = source_message.get("chat_id")
        thread_id = source_message.get("thread_id") or source_message.get("root_id") or ""
        if not chat_id:
            logger.info("IM 表情未命中机器人回复消息，跳过: provider=%s message_id=%s", provider, response_message_id)
            return None

        channel_session = agent_channel_session_crud.get_by_scope(
            db,
            team_id=team_id,
            user_id=user_id,
            provider=provider,
            chat_id=chat_id,
            thread_id=thread_id,
        )
        if not channel_session:
            logger.info("IM 表情未找到 Agent 会话，跳过: provider=%s message_id=%s chat_id=%s", provider, response_message_id, chat_id)
            return None
        return await agent_im_conversation_service.handle_message(
            content="确认" if intent == "confirm" else "取消",
            team_id=team_id,
            user_id=user_id,
            session_id=channel_session.agent_session_id,
            turn_input=(
                AgentTurnInput.confirm(source="im", provider=provider, metadata={"emoji_type": emoji_type})
                if intent == "confirm"
                else AgentTurnInput.reject(source="im", provider=provider, metadata={"emoji_type": emoji_type})
            ),
        )

    def intent_from_emoji(self, emoji_type: str) -> Optional[str]:
        if emoji_type in self.confirmation_emojis:
            return "confirm"
        if emoji_type in self.rejection_emojis:
            return "reject"
        return None


im_agent_gateway = IMAgentGateway()

"""Unified IM entrypoint for Agent conversations."""
from datetime import datetime, timedelta
import logging
from typing import Any, Dict, Optional, Sequence

from sqlalchemy.orm import Session

from app.crud.agent import agent_task_crud
from app.crud.im_bot import agent_channel_session_crud, im_inbound_event_crud
from app.models.agent import AgentTaskStatus
from app.services.agent.confirmation_intent import agent_confirmation_intent_service
from app.services.agent.input import AgentTurnInput
from app.services.agent.im_conversation import agent_im_conversation_service


logger = logging.getLogger(__name__)


class IMAgentGateway:
    """Normalize IM channel events before entering the Agent."""

    confirmation_emojis = {"Get", "Yes", "CheckMark", "OK", "THUMBSUP", "DONE", "JIAYI", "LGTM"}
    rejection_emojis = {"No", "CrossMark", "ThumbsDown", "MinusOne"}
    direct_confirmation_window = timedelta(minutes=30)

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
        chat_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        referenced_message_ids: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        direct_intent = agent_confirmation_intent_service._direct_confirmation_intent(user_text)
        if direct_intent:
            resolved_session_id = self._resolve_text_confirmation_session_id(
                db,
                team_id=team_id,
                user_id=user_id,
                provider=provider,
                current_session_id=session_id,
                chat_id=chat_id,
                thread_id=thread_id,
                referenced_message_ids=referenced_message_ids or [],
            )
            turn_input = (
                AgentTurnInput.confirm(source="im", provider=provider, metadata={"raw_text": user_text})
                if direct_intent == "confirm"
                else AgentTurnInput.reject(source="im", provider=provider, metadata={"raw_text": user_text})
            )
            return await agent_im_conversation_service.handle_message(
                content=turn_input.content,
                team_id=team_id,
                user_id=user_id,
                session_id=resolved_session_id or session_id,
                turn_input=turn_input,
            )

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

    def _resolve_text_confirmation_session_id(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        provider: str,
        current_session_id: int,
        chat_id: Optional[str],
        thread_id: Optional[str],
        referenced_message_ids: Sequence[str],
    ) -> Optional[int]:
        for message_id in referenced_message_ids:
            session_id = self._session_id_for_response_message(
                db,
                team_id=team_id,
                user_id=user_id,
                provider=provider,
                response_message_id=message_id,
            )
            if session_id and self._has_executable_waiting_task(db, session_id, team_id, user_id):
                return session_id

        if self._has_executable_waiting_task(db, current_session_id, team_id, user_id):
            return current_session_id

        if chat_id:
            session_id = self._latest_unambiguous_chat_confirmation_session_id(
                db,
                team_id=team_id,
                user_id=user_id,
                provider=provider,
                chat_id=chat_id,
            )
            if session_id:
                return session_id

        if chat_id and thread_id is not None:
            channel_session = agent_channel_session_crud.get_by_scope(
                db,
                team_id=team_id,
                user_id=user_id,
                provider=provider,
                chat_id=chat_id,
                thread_id=thread_id,
            )
            if channel_session and self._has_executable_waiting_task(
                db,
                channel_session.agent_session_id,
                team_id,
                user_id,
            ):
                return channel_session.agent_session_id

        return None

    def _session_id_for_response_message(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        provider: str,
        response_message_id: str,
    ) -> Optional[int]:
        source_event = im_inbound_event_crud.get_by_response_message_id(
            db,
            provider=provider,
            response_message_id=response_message_id,
            team_id=team_id,
        )
        source_message = (((source_event.raw_event or {}) if source_event else {}).get("message") or {})
        source_chat_id = source_message.get("chat_id")
        source_thread_id = source_message.get("thread_id") or source_message.get("root_id") or ""
        if not source_chat_id:
            return None
        channel_session = agent_channel_session_crud.get_by_scope(
            db,
            team_id=team_id,
            user_id=user_id,
            provider=provider,
            chat_id=source_chat_id,
            thread_id=source_thread_id,
        )
        return channel_session.agent_session_id if channel_session else None

    def _latest_unambiguous_chat_confirmation_session_id(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        provider: str,
        chat_id: str,
    ) -> Optional[int]:
        candidates = []
        cutoff = datetime.utcnow() - self.direct_confirmation_window
        for channel_session in agent_channel_session_crud.list_by_chat(
            db,
            team_id=team_id,
            user_id=user_id,
            provider=provider,
            chat_id=chat_id,
        ):
            task = self._latest_executable_waiting_task(db, channel_session.agent_session_id, team_id, user_id)
            if not task:
                continue
            created_time = getattr(task, "created_time", None)
            if created_time and created_time < cutoff:
                continue
            candidates.append((channel_session.agent_session_id, task))

        if len(candidates) == 1:
            return candidates[0][0]
        return None

    def _has_executable_waiting_task(self, db: Session, session_id: int, team_id: int, user_id: int) -> bool:
        return self._latest_executable_waiting_task(db, session_id, team_id, user_id) is not None

    def _latest_executable_waiting_task(self, db: Session, session_id: int, team_id: int, user_id: int):
        task = agent_task_crud.get_latest_waiting(db, session_id=session_id, team_id=team_id, user_id=user_id)
        if not task or task.status != AgentTaskStatus.WAITING_USER:
            return None
        if not agent_confirmation_intent_service.is_executable_confirmation_task(task):
            return None
        return task


im_agent_gateway = IMAgentGateway()

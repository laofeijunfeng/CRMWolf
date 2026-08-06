"""Unified IM entrypoint for Agent conversations."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Sequence

from sqlalchemy.orm import Session

from app.crud.agent import agent_session_crud, agent_task_crud
from app.crud.im_bot import agent_channel_session_crud, im_inbound_event_crud
from app.models.agent import AgentMessage, AgentMessageRole, AgentTaskStatus
from app.services.agent.confirmation_intent import agent_confirmation_intent_service
from app.services.agent.im_conversation import agent_im_conversation_service
from app.services.agent.input import AgentTurnInput
from app.services.follow_up_task_confirmation_channel_service import FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION

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
        referenced_pending_session_id = self._resolve_referenced_pending_session_id(
            db,
            team_id=team_id,
            user_id=user_id,
            provider=provider,
            referenced_message_ids=referenced_message_ids or [],
        )
        referenced_confirmation_session_id = self._resolve_referenced_follow_up_confirmation_session_id(
            db,
            team_id=team_id,
            user_id=user_id,
            provider=provider,
            referenced_message_ids=referenced_message_ids or [],
        )
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
            if not resolved_session_id and referenced_confirmation_session_id:
                turn_input = self._follow_up_confirmation_turn_input_from_latest_interaction(
                    db,
                    session_id=referenced_confirmation_session_id,
                    team_id=team_id,
                    user_id=user_id,
                    provider=provider,
                    user_text=user_text,
                    metadata={
                        "raw_text": user_text,
                        "reply_to_message_ids": list(referenced_message_ids or []),
                        "quoted_agent_content": agent_content if agent_content != user_text else None,
                    },
                ) or turn_input
            return await agent_im_conversation_service.handle_message(
                content=turn_input.content,
                team_id=team_id,
                user_id=user_id,
                session_id=(
                    resolved_session_id
                    or referenced_pending_session_id
                    or referenced_confirmation_session_id
                    or session_id
                ),
                turn_input=turn_input,
            )

        if referenced_pending_session_id:
            turn_input = self._choice_turn_input_from_latest_interaction(
                db,
                session_id=referenced_pending_session_id,
                team_id=team_id,
                user_id=user_id,
                provider=provider,
                user_text=user_text,
                metadata={
                    "raw_text": user_text,
                    "reply_to_message_ids": list(referenced_message_ids or []),
                    "quoted_agent_content": agent_content if agent_content != user_text else None,
                },
            ) or AgentTurnInput.text(
                user_text,
                source="im",
                provider=provider,
                metadata={
                    "raw_text": user_text,
                    "reply_to_message_ids": list(referenced_message_ids or []),
                    "quoted_agent_content": agent_content if agent_content != user_text else None,
                },
            )
            return await agent_im_conversation_service.handle_message(
                content=turn_input.content,
                team_id=team_id,
                user_id=user_id,
                session_id=referenced_pending_session_id,
                turn_input=turn_input,
            )

        if referenced_confirmation_session_id:
            turn_input = self._choice_turn_input_from_latest_interaction(
                db,
                session_id=referenced_confirmation_session_id,
                team_id=team_id,
                user_id=user_id,
                provider=provider,
                user_text=user_text,
                metadata={
                    "raw_text": user_text,
                    "reply_to_message_ids": list(referenced_message_ids or []),
                    "quoted_agent_content": agent_content if agent_content != user_text else None,
                },
            ) or self._follow_up_confirmation_turn_input_from_latest_interaction(
                db,
                session_id=referenced_confirmation_session_id,
                team_id=team_id,
                user_id=user_id,
                provider=provider,
                user_text=user_text,
                metadata={
                    "raw_text": user_text,
                    "reply_to_message_ids": list(referenced_message_ids or []),
                    "quoted_agent_content": agent_content if agent_content != user_text else None,
                },
            )
            if turn_input:
                return await agent_im_conversation_service.handle_message(
                    content=turn_input.content,
                    team_id=team_id,
                    user_id=user_id,
                    session_id=referenced_confirmation_session_id,
                    turn_input=turn_input,
                )

        turn_input = self._choice_turn_input_from_latest_interaction(
            db,
            session_id=session_id,
            team_id=team_id,
            user_id=user_id,
            provider=provider,
            user_text=user_text,
            metadata={"raw_text": user_text},
        )
        if turn_input:
            return await agent_im_conversation_service.handle_message(
                content=turn_input.content,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                turn_input=turn_input,
            )
        turn_input = self._follow_up_confirmation_turn_input_from_latest_interaction(
            db,
            session_id=session_id,
            team_id=team_id,
            user_id=user_id,
            provider=provider,
            user_text=user_text,
            metadata={"raw_text": user_text},
        )
        if turn_input:
            return await agent_im_conversation_service.handle_message(
                content=turn_input.content,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
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

        session_id = self._session_id_for_response_message(
            db,
            team_id=team_id,
            user_id=user_id,
            provider=provider,
            response_message_id=response_message_id,
        )
        if not session_id:
            logger.info("IM 表情未命中机器人回复消息，跳过: provider=%s message_id=%s", provider, response_message_id)
            return None
        return await agent_im_conversation_service.handle_message(
            content="确认" if intent == "confirm" else "取消",
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
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

    def _resolve_referenced_pending_session_id(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        provider: str,
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
            if session_id and self._has_waiting_task(db, session_id, team_id, user_id):
                return session_id
        return None

    def _resolve_referenced_follow_up_confirmation_session_id(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        provider: str,
        referenced_message_ids: Sequence[str],
    ) -> Optional[int]:
        if db is None:
            return None
        for message_id in referenced_message_ids:
            session_id = self._session_id_for_response_message(
                db,
                team_id=team_id,
                user_id=user_id,
                provider=provider,
                response_message_id=message_id,
            )
            if not session_id:
                continue
            interaction = self._latest_waiting_interaction(
                db,
                session_id=session_id,
                team_id=team_id,
                user_id=user_id,
            )
            if interaction and interaction.get("business_action") == FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION:
                return session_id
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
        if not source_event:
            return None

        bound_session_id = self._verified_bound_session_id(
            db,
            source_event=source_event,
            team_id=team_id,
            user_id=user_id,
        )
        if bound_session_id:
            return bound_session_id
        if getattr(source_event, "agent_task_id", None):
            logger.info(
                "IM 回复命中的 Agent task 已不再等待用户，跳过旧回复绑定: provider=%s response_message_id=%s task_id=%s",
                provider,
                response_message_id,
                source_event.agent_task_id,
            )
            return None

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

    def _verified_bound_session_id(
        self,
        db: Session,
        *,
        source_event,
        team_id: int,
        user_id: int,
    ) -> Optional[int]:
        session_id = getattr(source_event, "agent_session_id", None)
        task_id = getattr(source_event, "agent_task_id", None)
        if task_id:
            task = agent_task_crud.get_by_id(db, task_id, team_id=team_id, user_id=user_id)
            if (
                task
                and task.status == AgentTaskStatus.WAITING_USER
                and (not session_id or task.session_id == session_id)
            ):
                return task.session_id
            return None
        if session_id and agent_session_crud.get_by_id(db, session_id, team_id=team_id, user_id=user_id):
            return session_id
        return None

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

    def _has_waiting_task(self, db: Session, session_id: int, team_id: int, user_id: int) -> bool:
        task = agent_task_crud.get_latest_waiting(db, session_id=session_id, team_id=team_id, user_id=user_id)
        return bool(task and task.status == AgentTaskStatus.WAITING_USER)

    def _latest_executable_waiting_task(self, db: Session, session_id: int, team_id: int, user_id: int):
        task = agent_task_crud.get_latest_waiting(db, session_id=session_id, team_id=team_id, user_id=user_id)
        if not task or task.status != AgentTaskStatus.WAITING_USER:
            return None
        if not agent_confirmation_intent_service.is_executable_confirmation_task(task):
            return None
        return task

    def _choice_turn_input_from_latest_interaction(
        self,
        db: Session,
        *,
        session_id: int,
        team_id: int,
        user_id: int,
        provider: str,
        user_text: str,
        metadata: Dict[str, Any],
    ) -> Optional[AgentTurnInput]:
        interaction = self._latest_waiting_interaction(db, session_id=session_id, team_id=team_id, user_id=user_id)
        if not interaction or interaction.get("type") != "choice":
            return None
        choice = self._match_choice(interaction.get("choices"), user_text)
        if not choice:
            return None
        choice_metadata = choice.get("metadata") if isinstance(choice.get("metadata"), dict) else {}
        return AgentTurnInput.text(
            str(choice.get("value") or choice.get("label") or user_text),
            source="im",
            provider=provider,
            metadata={
                **metadata,
                **choice_metadata,
                "interaction_id": interaction.get("interaction_id"),
                "interaction_type": interaction.get("type"),
                "business_action": interaction.get("business_action"),
                "choice_value": choice.get("value"),
                "choice_label": choice.get("label"),
            },
        )

    def _follow_up_confirmation_turn_input_from_latest_interaction(
        self,
        db: Session,
        *,
        session_id: int,
        team_id: int,
        user_id: int,
        provider: str,
        user_text: str,
        metadata: Dict[str, Any],
    ) -> Optional[AgentTurnInput]:
        interaction = self._latest_waiting_interaction(db, session_id=session_id, team_id=team_id, user_id=user_id)
        if not interaction or interaction.get("business_action") != FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION:
            return None
        case_public_id = self._case_public_id_from_interaction(interaction)
        if not case_public_id:
            return None
        return AgentTurnInput.text(
            user_text,
            source="im",
            provider=provider,
            metadata={
                **metadata,
                "interaction_id": interaction.get("interaction_id"),
                "interaction_type": interaction.get("type"),
                "business_action": interaction.get("business_action"),
                "case_public_id": case_public_id,
                "follow_up_confirmation_case_public_id": case_public_id,
            },
        )

    def _latest_waiting_interaction(
        self,
        db: Session,
        *,
        session_id: int,
        team_id: int,
        user_id: int,
    ) -> Optional[Dict[str, Any]]:
        if db is None:
            return None
        messages = (
            db.query(AgentMessage)
            .filter(
                AgentMessage.session_id == session_id,
                AgentMessage.team_id == team_id,
                AgentMessage.user_id == user_id,
                AgentMessage.role == AgentMessageRole.ASSISTANT,
            )
            .order_by(AgentMessage.created_time.desc(), AgentMessage.id.desc())
            .limit(10)
            .all()
        )
        for message in messages:
            payload = message.payload_json if isinstance(message.payload_json, dict) else {}
            trace_events = payload.get("trace_events") if isinstance(payload.get("trace_events"), list) else []
            for event in reversed(trace_events):
                if not isinstance(event, dict):
                    continue
                interaction = event.get("interaction")
                if self._is_waiting_interaction(interaction):
                    return interaction
        return None

    def _is_waiting_interaction(self, interaction: Any) -> bool:
        if not isinstance(interaction, dict):
            return False
        status = interaction.get("status")
        return status in {None, "waiting_user_input", "waiting_confirmation"}

    def _match_choice(self, choices: Any, user_text: str) -> Optional[Dict[str, Any]]:
        if not isinstance(choices, list):
            return None
        normalized_text = self._normalize_choice_text(user_text)
        if normalized_text.isdigit():
            index = int(normalized_text) - 1
            if 0 <= index < len(choices) and isinstance(choices[index], dict):
                return choices[index]
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            label = self._normalize_choice_text(str(choice.get("label") or ""))
            value = self._normalize_choice_text(str(choice.get("value") or ""))
            if normalized_text and normalized_text in {label, value}:
                return choice
        return None

    def _case_public_id_from_interaction(self, interaction: Dict[str, Any]) -> Optional[str]:
        payload = interaction.get("payload")
        if not isinstance(payload, dict):
            return None
        value = payload.get("case_public_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
        case = payload.get("case")
        if isinstance(case, dict):
            case_public_id = case.get("public_id") or case.get("id")
            if isinstance(case_public_id, str) and case_public_id.strip():
                return case_public_id.strip()
        return None

    def _normalize_choice_text(self, value: str) -> str:
        return value.strip().strip("「」\"'“”")


im_agent_gateway = IMAgentGateway()

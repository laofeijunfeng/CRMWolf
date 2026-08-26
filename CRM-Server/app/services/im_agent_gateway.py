"""Unified IM entrypoint for Agent conversations."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.orm import Session

from app.crud.agent import agent_session_crud
from app.crud.im_bot import im_inbound_event_crud
from app.crud.sales_commitment import (
    follow_up_task_confirmation_case_crud,
    follow_up_task_confirmation_prompt_delivery_crud,
)
from app.models.sales_commitment import (
    FollowUpTaskConfirmationDeliveryPurpose,
    FollowUpTaskConfirmationPromptStatus,
    FollowUpTaskConfirmationStatus,
)
from app.services.agent.im_conversation import agent_im_conversation_service
from app.services.agent.input import AgentChannelContext, AgentInputKind
from app.services.agent.ui.schemas import TextAgentInput
from app.services.follow_up_task_confirmation_channel_service import FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION

logger = logging.getLogger(__name__)


def im_client_request_id(*, provider: str, provider_event_id: str) -> UUID:
    """Derive one stable Agent turn idempotency key from the provider event identity."""

    normalized_provider = provider.strip().lower()
    normalized_event_id = provider_event_id.strip()
    if not normalized_provider or not normalized_event_id:
        raise ValueError("provider and provider_event_id are required")
    return uuid5(NAMESPACE_URL, f"urn:crmwolf:agent:im:{normalized_provider}:{normalized_event_id}")


@dataclass(frozen=True)
class IMConfirmationReplyTarget:
    """Exact durable binding between one provider message and one confirmation case."""

    session_id: int
    delivery_public_id: str
    case_public_id: str
    interaction_id: str | None
    prompt_delivery_key: str | None


class IMAgentGateway:
    """Normalize IM channel events before entering the Agent.

    A reply re-enters a prior Agent session only when the referenced provider
    message carries a durable session or confirmation-delivery binding. Chat
    recency and latest-interaction inference are not routing authorities.
    """

    confirmation_emojis = {"Get", "Yes", "CheckMark", "OK", "THUMBSUP", "DONE", "JIAYI", "LGTM"}
    rejection_emojis = {"No", "CrossMark", "ThumbsDown", "MinusOne"}

    async def handle_text(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        provider: str,
        provider_event_id: str,
        session_id: int,
        user_text: str,
        agent_content: str,
        chat_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        referenced_message_ids: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        del chat_id, thread_id  # Scope metadata is not an authority for continuation routing.
        referenced_ids = list(referenced_message_ids or [])
        reply_metadata = {
            "raw_text": user_text,
            "reply_to_message_ids": referenced_ids,
            "quoted_agent_content": agent_content if agent_content != user_text else None,
        }

        confirmation_target = self._resolve_referenced_confirmation_target(
            db,
            team_id=team_id,
            user_id=user_id,
            provider=provider,
            referenced_message_ids=referenced_ids,
        )
        if confirmation_target is not None:
            channel_context = self._confirmation_channel_context(
                confirmation_target,
                provider=provider,
                metadata=reply_metadata,
            )
            return await agent_im_conversation_service.handle_message(
                request_input=TextAgentInput(type="text", text=user_text),
                client_request_id=im_client_request_id(
                    provider=provider,
                    provider_event_id=provider_event_id,
                ),
                channel_context=channel_context,
                team_id=team_id,
                user_id=user_id,
                session_id=confirmation_target.session_id,
            )

        referenced_session_id = self._resolve_referenced_session_id(
            db,
            team_id=team_id,
            user_id=user_id,
            provider=provider,
            referenced_message_ids=referenced_ids,
        )
        if referenced_session_id is not None:
            return await agent_im_conversation_service.handle_message(
                request_input=TextAgentInput(type="text", text=user_text),
                client_request_id=im_client_request_id(
                    provider=provider,
                    provider_event_id=provider_event_id,
                ),
                channel_context=AgentChannelContext(
                    source="im",
                    provider=provider,
                    metadata=reply_metadata,
                ),
                team_id=team_id,
                user_id=user_id,
                session_id=referenced_session_id,
            )

        return await agent_im_conversation_service.handle_message(
            request_input=TextAgentInput(
                type="text",
                text=user_text if referenced_ids else agent_content,
            ),
            client_request_id=im_client_request_id(
                provider=provider,
                provider_event_id=provider_event_id,
            ),
            channel_context=AgentChannelContext(
                source="im",
                provider=provider,
                metadata=reply_metadata if referenced_ids else {"raw_text": user_text},
            ),
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
        )

    async def handle_reaction(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        provider: str,
        provider_event_id: str,
        response_message_id: str,
        emoji_type: str,
    ) -> Optional[Dict[str, Any]]:
        intent = self.intent_from_emoji(emoji_type)
        if not intent:
            return None

        confirmation_target = self._resolve_confirmation_target_for_response_message(
            db,
            team_id=team_id,
            user_id=user_id,
            provider=provider,
            response_message_id=response_message_id,
        )
        if confirmation_target is not None:
            reply_text = "已完成" if intent == "confirm" else "先放着"
            channel_context = self._confirmation_channel_context(
                confirmation_target,
                provider=provider,
                metadata={
                    "emoji_type": emoji_type,
                    "response_message_id": response_message_id,
                },
            )
            return await agent_im_conversation_service.handle_message(
                request_input=TextAgentInput(type="text", text=reply_text),
                client_request_id=im_client_request_id(
                    provider=provider,
                    provider_event_id=provider_event_id,
                ),
                channel_context=channel_context,
                team_id=team_id,
                user_id=user_id,
                session_id=confirmation_target.session_id,
            )

        session_id = self._session_id_for_response_message(
            db,
            team_id=team_id,
            user_id=user_id,
            provider=provider,
            response_message_id=response_message_id,
        )
        if not session_id:
            logger.info(
                "IM 表情未命中精确机器人回复绑定，跳过: provider=%s message_id=%s", provider, response_message_id
            )
            return None
        return await agent_im_conversation_service.handle_message(
            request_input=TextAgentInput(
                type="text",
                text="确认" if intent == "confirm" else "取消",
            ),
            client_request_id=im_client_request_id(
                provider=provider,
                provider_event_id=provider_event_id,
            ),
            channel_context=AgentChannelContext(
                source="im",
                provider=provider,
                input_kind=(AgentInputKind.CONFIRM if intent == "confirm" else AgentInputKind.REJECT),
                metadata={"emoji_type": emoji_type},
            ),
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
        )

    def intent_from_emoji(self, emoji_type: str) -> Optional[str]:
        if emoji_type in self.confirmation_emojis:
            return "confirm"
        if emoji_type in self.rejection_emojis:
            return "reject"
        return None

    def _resolve_referenced_confirmation_target(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        provider: str,
        referenced_message_ids: Sequence[str],
    ) -> IMConfirmationReplyTarget | None:
        if db is None:
            return None
        for message_id in referenced_message_ids:
            target = self._resolve_confirmation_target_for_response_message(
                db,
                team_id=team_id,
                user_id=user_id,
                provider=provider,
                response_message_id=message_id,
            )
            if target is not None:
                return target
        return None

    def _resolve_confirmation_target_for_response_message(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        provider: str,
        response_message_id: str,
    ) -> IMConfirmationReplyTarget | None:
        if db is None:
            return None
        source_event = im_inbound_event_crud.get_by_response_message_id(
            db,
            provider=provider,
            response_message_id=response_message_id,
            team_id=team_id,
        )
        if source_event is None:
            return None

        delivery_public_id = self._clean_string(getattr(source_event, "confirmation_delivery_public_id", None))
        case_public_id = self._clean_string(getattr(source_event, "confirmation_case_public_id", None))
        if not delivery_public_id or not case_public_id:
            return None

        delivery = follow_up_task_confirmation_prompt_delivery_crud.get_by_public_id(
            db,
            team_id=team_id,
            public_id=delivery_public_id,
        )
        case = follow_up_task_confirmation_case_crud.get_by_public_id(db, case_public_id, team_id=team_id)
        if delivery is None or case is None:
            return None
        if delivery.case_id != case.id:
            return None
        if delivery.owner_id != str(user_id) or case.owner_id != str(user_id):
            return None
        if delivery.provider and delivery.provider != provider:
            return None
        if delivery.purpose != FollowUpTaskConfirmationDeliveryPurpose.IM_PROMPT:
            return None
        if delivery.status != FollowUpTaskConfirmationPromptStatus.SENT:
            return None
        if case.status != FollowUpTaskConfirmationStatus.PENDING:
            return None

        source_session_id = getattr(source_event, "agent_session_id", None)
        delivery_session_id = getattr(delivery, "agent_session_id", None)
        if not source_session_id or not delivery_session_id or source_session_id != delivery_session_id:
            return None
        if (
            agent_session_crud.get_by_id(
                db,
                source_session_id,
                team_id=team_id,
                user_id=user_id,
            )
            is None
        ):
            return None

        source_interaction_id = self._clean_string(getattr(source_event, "agent_interaction_id", None))
        delivery_interaction_id = self._clean_string(getattr(delivery, "interaction_id", None))
        if source_interaction_id and delivery_interaction_id and source_interaction_id != delivery_interaction_id:
            return None
        source_prompt_key = self._clean_string(getattr(source_event, "prompt_delivery_key", None))
        delivery_prompt_key = self._clean_string(getattr(delivery, "prompt_key", None))
        if source_prompt_key and delivery_prompt_key and source_prompt_key != delivery_prompt_key:
            return None

        return IMConfirmationReplyTarget(
            session_id=source_session_id,
            delivery_public_id=delivery.public_id,
            case_public_id=case.public_id,
            interaction_id=source_interaction_id or delivery_interaction_id,
            prompt_delivery_key=source_prompt_key or delivery_prompt_key,
        )

    def _resolve_referenced_session_id(
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
            if session_id is not None:
                return session_id
        return None

    def _confirmation_channel_context(
        self,
        target: IMConfirmationReplyTarget,
        *,
        provider: str,
        metadata: Dict[str, Any],
    ) -> AgentChannelContext:
        return AgentChannelContext(
            source="im",
            provider=provider,
            metadata={
                **metadata,
                "business_action": FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION,
                "case_public_id": target.case_public_id,
                "follow_up_confirmation_case_public_id": target.case_public_id,
                "confirmation_delivery_public_id": target.delivery_public_id,
                "interaction_id": target.interaction_id,
                "prompt_delivery_key": target.prompt_delivery_key,
            },
        )

    def _session_id_for_response_message(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        provider: str,
        response_message_id: str,
    ) -> Optional[int]:
        if db is None:
            return None
        source_event = im_inbound_event_crud.get_by_response_message_id(
            db,
            provider=provider,
            response_message_id=response_message_id,
            team_id=team_id,
        )
        if not source_event:
            return None
        if getattr(source_event, "confirmation_delivery_public_id", None):
            return None

        session_id = getattr(source_event, "agent_session_id", None)
        if session_id and agent_session_crud.get_by_id(
            db,
            session_id,
            team_id=team_id,
            user_id=user_id,
        ):
            return session_id

        logger.info(
            "IM 回复消息缺少有效 Agent session 绑定，跳过: provider=%s response_message_id=%s",
            provider,
            response_message_id,
        )
        return None

    @staticmethod
    def _clean_string(value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        return cleaned or None


im_agent_gateway = IMAgentGateway()

"""CRUD helpers for IM bot integrations."""
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agent import AgentSession
from app.models.im_bot import AgentChannelSession, IMInboundEvent
from app.schemas.agent import AgentSessionCreate
from app.utils.time import business_now


class AgentChannelSessionCRUD:
    def get_or_create(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        provider: str,
        chat_id: str,
        thread_id: str,
        external_tenant_key: Optional[str],
        session_create: AgentSessionCreate,
    ) -> AgentChannelSession:
        thread_id = thread_id or ""
        channel_session = db.query(AgentChannelSession).filter(
            AgentChannelSession.provider == provider,
            AgentChannelSession.team_id == team_id,
            AgentChannelSession.user_id == user_id,
            AgentChannelSession.chat_id == chat_id,
            AgentChannelSession.thread_id == thread_id,
        ).first()
        if channel_session:
            return channel_session

        agent_session = AgentSession(**session_create.model_dump())
        db.add(agent_session)
        db.flush()
        channel_session = AgentChannelSession(
            team_id=team_id,
            user_id=user_id,
            provider=provider,
            external_tenant_key=external_tenant_key,
            chat_id=chat_id,
            thread_id=thread_id,
            agent_session_id=agent_session.id,
        )
        db.add(channel_session)
        db.commit()
        db.refresh(channel_session)
        return channel_session

    def get_by_scope(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        provider: str,
        chat_id: str,
        thread_id: str = "",
    ) -> Optional[AgentChannelSession]:
        return db.query(AgentChannelSession).filter(
            AgentChannelSession.provider == provider,
            AgentChannelSession.team_id == team_id,
            AgentChannelSession.user_id == user_id,
            AgentChannelSession.chat_id == chat_id,
            AgentChannelSession.thread_id == (thread_id or ""),
        ).first()

    def get_by_agent_session(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        provider: str,
        agent_session_id: int,
    ) -> Optional[AgentChannelSession]:
        return db.query(AgentChannelSession).filter(
            AgentChannelSession.provider == provider,
            AgentChannelSession.team_id == team_id,
            AgentChannelSession.user_id == user_id,
            AgentChannelSession.agent_session_id == agent_session_id,
        ).first()

    def list_by_chat(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        provider: str,
        chat_id: str,
    ) -> list[AgentChannelSession]:
        return db.query(AgentChannelSession).filter(
            AgentChannelSession.provider == provider,
            AgentChannelSession.team_id == team_id,
            AgentChannelSession.user_id == user_id,
            AgentChannelSession.chat_id == chat_id,
            AgentChannelSession.status == "active",
        ).order_by(AgentChannelSession.updated_time.desc(), AgentChannelSession.id.desc()).all()

    def mark_message(self, db: Session, db_obj: AgentChannelSession, message_id: str) -> AgentChannelSession:
        db_obj.last_message_id = message_id
        db.commit()
        db.refresh(db_obj)
        return db_obj


class IMInboundEventCRUD:
    def create_received(
        self,
        db: Session,
        *,
        provider: str,
        event_id: str,
        message_id: Optional[str],
        request_hash: str,
        team_id: Optional[int],
        raw_event: Optional[dict],
    ) -> tuple[IMInboundEvent, bool]:
        db_obj = IMInboundEvent(
            provider=provider,
            event_id=event_id,
            message_id=message_id,
            request_hash=request_hash,
            team_id=team_id,
            raw_event=raw_event,
        )
        db.add(db_obj)
        try:
            db.commit()
            db.refresh(db_obj)
            return db_obj, False
        except IntegrityError:
            db.rollback()
            existing = db.query(IMInboundEvent).filter(
                IMInboundEvent.provider == provider,
                IMInboundEvent.event_id == event_id,
            ).first()
            return existing, True

    def mark_status(
        self,
        db: Session,
        db_obj: IMInboundEvent,
        status: str,
        *,
        response_message_id: Optional[str] = None,
        agent_session_id: Optional[int] = None,
        agent_task_id: Optional[int] = None,
        agent_interaction_type: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> IMInboundEvent:
        db_obj.status = status
        db_obj.response_message_id = response_message_id
        db_obj.agent_session_id = agent_session_id
        db_obj.agent_task_id = agent_task_id
        db_obj.agent_interaction_type = agent_interaction_type
        db_obj.error_message = error_message
        db_obj.processed_time = business_now()
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_by_response_message_id(
        self,
        db: Session,
        *,
        provider: str,
        response_message_id: str,
        team_id: Optional[int] = None,
    ) -> Optional[IMInboundEvent]:
        query = db.query(IMInboundEvent).filter(
            IMInboundEvent.provider == provider,
            IMInboundEvent.response_message_id == response_message_id,
        )
        if team_id is not None:
            query = query.filter(IMInboundEvent.team_id == team_id)
        return query.order_by(IMInboundEvent.created_time.desc(), IMInboundEvent.id.desc()).first()


agent_channel_session_crud = AgentChannelSessionCRUD()
im_inbound_event_crud = IMInboundEventCRUD()

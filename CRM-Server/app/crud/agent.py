"""CRM AI Agent CRUD.

This module only manages Agent-owned state. CRM business actions must go
through existing API endpoints in the tool layer.
"""
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.agent import (
    AgentIdempotencyKey,
    AgentMessage,
    AgentSession,
    AgentTask,
    AgentToolCall,
)
from app.schemas.agent import (
    AgentIdempotencyKeyCreate,
    AgentIdempotencyKeyUpdate,
    AgentMessageCreate,
    AgentSessionCreate,
    AgentSessionUpdate,
    AgentTaskCreate,
    AgentTaskUpdate,
    AgentToolCallCreate,
    AgentToolCallUpdate,
)


class AgentSessionCRUD:
    def get_by_id(
        self,
        db: Session,
        session_id: int,
        team_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> Optional[AgentSession]:
        query = db.query(AgentSession).filter(AgentSession.id == session_id)
        if team_id is not None:
            query = query.filter(AgentSession.team_id == team_id)
        if user_id is not None:
            query = query.filter(AgentSession.user_id == user_id)
        return query.first()

    def get_by_key(
        self,
        db: Session,
        session_key: str,
        team_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> Optional[AgentSession]:
        query = db.query(AgentSession).filter(AgentSession.session_key == session_key)
        if team_id is not None:
            query = query.filter(AgentSession.team_id == team_id)
        if user_id is not None:
            query = query.filter(AgentSession.user_id == user_id)
        return query.first()

    def list_by_user(
        self,
        db: Session,
        team_id: int,
        user_id: int,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[AgentSession], int]:
        query = db.query(AgentSession).filter(
            AgentSession.team_id == team_id,
            AgentSession.user_id == user_id,
        )
        if status:
            query = query.filter(AgentSession.status == status)

        total = query.count()
        items = (
            query.order_by(AgentSession.last_modified_time.desc(), AgentSession.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return items, total

    def create(self, db: Session, obj_in: AgentSessionCreate) -> AgentSession:
        db_obj = AgentSession(**obj_in.model_dump())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_or_create(self, db: Session, obj_in: AgentSessionCreate) -> AgentSession:
        db_obj = self.get_by_key(db, obj_in.session_key, obj_in.team_id, obj_in.user_id)
        if db_obj:
            return db_obj
        return self.create(db, obj_in)

    def update(self, db: Session, db_obj: AgentSession, obj_in: AgentSessionUpdate) -> AgentSession:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj


class AgentMessageCRUD:
    def create(self, db: Session, obj_in: AgentMessageCreate) -> AgentMessage:
        db_obj = AgentMessage(**obj_in.model_dump())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def list_by_session(
        self,
        db: Session,
        session_id: int,
        team_id: Optional[int] = None,
        user_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[AgentMessage], int]:
        query = db.query(AgentMessage).filter(AgentMessage.session_id == session_id)
        if team_id is not None:
            query = query.filter(AgentMessage.team_id == team_id)
        if user_id is not None:
            query = query.filter(AgentMessage.user_id == user_id)

        total = query.count()
        items = (
            query.order_by(AgentMessage.created_time.asc(), AgentMessage.id.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return items, total


class AgentTaskCRUD:
    def get_by_id(
        self,
        db: Session,
        task_id: int,
        team_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> Optional[AgentTask]:
        query = db.query(AgentTask).filter(AgentTask.id == task_id)
        if team_id is not None:
            query = query.filter(AgentTask.team_id == team_id)
        if user_id is not None:
            query = query.filter(AgentTask.user_id == user_id)
        return query.first()

    def get_by_key(
        self,
        db: Session,
        task_key: str,
        team_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> Optional[AgentTask]:
        query = db.query(AgentTask).filter(AgentTask.task_key == task_key)
        if team_id is not None:
            query = query.filter(AgentTask.team_id == team_id)
        if user_id is not None:
            query = query.filter(AgentTask.user_id == user_id)
        return query.first()

    def create(self, db: Session, obj_in: AgentTaskCreate) -> AgentTask:
        db_obj = AgentTask(**obj_in.model_dump())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def list_by_session(
        self,
        db: Session,
        session_id: int,
        team_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> List[AgentTask]:
        query = db.query(AgentTask).filter(AgentTask.session_id == session_id)
        if team_id is not None:
            query = query.filter(AgentTask.team_id == team_id)
        if user_id is not None:
            query = query.filter(AgentTask.user_id == user_id)
        return query.order_by(AgentTask.created_time.desc(), AgentTask.id.desc()).all()

    def update(self, db: Session, db_obj: AgentTask, obj_in: AgentTaskUpdate) -> AgentTask:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj


class AgentToolCallCRUD:
    def get_by_key(
        self,
        db: Session,
        call_key: str,
        team_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> Optional[AgentToolCall]:
        query = db.query(AgentToolCall).filter(AgentToolCall.call_key == call_key)
        if team_id is not None:
            query = query.filter(AgentToolCall.team_id == team_id)
        if user_id is not None:
            query = query.filter(AgentToolCall.user_id == user_id)
        return query.first()

    def create(self, db: Session, obj_in: AgentToolCallCreate) -> AgentToolCall:
        db_obj = AgentToolCall(**obj_in.model_dump())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def mark_started(self, db: Session, db_obj: AgentToolCall) -> AgentToolCall:
        db_obj.started_time = datetime.now()
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, db_obj: AgentToolCall, obj_in: AgentToolCallUpdate) -> AgentToolCall:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def list_by_task(
        self,
        db: Session,
        task_id: int,
        team_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> List[AgentToolCall]:
        query = db.query(AgentToolCall).filter(AgentToolCall.task_id == task_id)
        if team_id is not None:
            query = query.filter(AgentToolCall.team_id == team_id)
        if user_id is not None:
            query = query.filter(AgentToolCall.user_id == user_id)
        return query.order_by(AgentToolCall.created_time.asc(), AgentToolCall.id.asc()).all()


class AgentIdempotencyKeyCRUD:
    def get_by_action_key(
        self,
        db: Session,
        team_id: int,
        user_id: int,
        action_key: str,
    ) -> Optional[AgentIdempotencyKey]:
        return db.query(AgentIdempotencyKey).filter(
            AgentIdempotencyKey.team_id == team_id,
            AgentIdempotencyKey.user_id == user_id,
            AgentIdempotencyKey.action_key == action_key,
        ).first()

    def create(self, db: Session, obj_in: AgentIdempotencyKeyCreate) -> AgentIdempotencyKey:
        db_obj = AgentIdempotencyKey(**obj_in.model_dump())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_or_create(self, db: Session, obj_in: AgentIdempotencyKeyCreate) -> AgentIdempotencyKey:
        db_obj = self.get_by_action_key(db, obj_in.team_id, obj_in.user_id, obj_in.action_key)
        if db_obj:
            return db_obj
        return self.create(db, obj_in)

    def update(
        self,
        db: Session,
        db_obj: AgentIdempotencyKey,
        obj_in: AgentIdempotencyKeyUpdate,
    ) -> AgentIdempotencyKey:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj


agent_session_crud = AgentSessionCRUD()
agent_message_crud = AgentMessageCRUD()
agent_task_crud = AgentTaskCRUD()
agent_tool_call_crud = AgentToolCallCRUD()
agent_idempotency_key_crud = AgentIdempotencyKeyCRUD()

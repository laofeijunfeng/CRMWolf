"""CRM AI Agent CRUD.

This module only manages Agent-owned state. CRM business actions must go
through existing API endpoints in the tool layer.
"""

from typing import List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agent import (
    AgentIdempotencyKey,
    AgentMessage,
    AgentSession,
    AgentToolCall,
    AgentWorkflowAction,
)
from app.schemas.agent import (
    AgentIdempotencyKeyCreate,
    AgentIdempotencyKeyUpdate,
    AgentMessageCreate,
    AgentSessionCreate,
    AgentSessionUpdate,
    AgentToolCallCreate,
    AgentToolCallUpdate,
    AgentWorkflowActionCreate,
    AgentWorkflowActionUpdate,
)
from app.utils.time import business_now


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

    def update(
        self,
        db: Session,
        db_obj: AgentSession,
        obj_in: AgentSessionUpdate,
        *,
        commit: bool = True,
    ) -> AgentSession:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        if commit:
            db.commit()
            db.refresh(db_obj)
        else:
            db.flush()
        return db_obj


class AgentMessageCRUD:
    def create(
        self,
        db: Session,
        obj_in: AgentMessageCreate,
        *,
        commit: bool = True,
    ) -> AgentMessage:
        db_obj = AgentMessage(**obj_in.model_dump())
        db.add(db_obj)
        session = db.query(AgentSession).filter(AgentSession.id == obj_in.session_id).first()
        if session is not None:
            session.last_modified_time = business_now()
        if commit:
            db.commit()
            db.refresh(db_obj)
        else:
            db.flush()
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
        if team_id is not None and user_id is not None:
            query = query.with_hint(
                AgentMessage,
                "FORCE INDEX (idx_agent_message_history_owner_order)",
                dialect_name="mysql",
            )
        items = query.order_by(AgentMessage.created_time.asc(), AgentMessage.id.asc()).offset(skip).limit(limit).all()
        return items, total


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
        db_obj.started_time = business_now()
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


class AgentIdempotencyKeyCRUD:
    def get_by_action_key(
        self,
        db: Session,
        team_id: int,
        user_id: int,
        action_key: str,
    ) -> Optional[AgentIdempotencyKey]:
        return (
            db.query(AgentIdempotencyKey)
            .filter(
                AgentIdempotencyKey.team_id == team_id,
                AgentIdempotencyKey.user_id == user_id,
                AgentIdempotencyKey.action_key == action_key,
            )
            .first()
        )

    def create(
        self,
        db: Session,
        obj_in: AgentIdempotencyKeyCreate,
        *,
        commit: bool = True,
    ) -> AgentIdempotencyKey:
        db_obj = AgentIdempotencyKey(**obj_in.model_dump())
        db.add(db_obj)
        if commit:
            db.commit()
            db.refresh(db_obj)
        else:
            db.flush()
        return db_obj

    def ensure(
        self,
        db: Session,
        obj_in: AgentIdempotencyKeyCreate,
        *,
        commit: bool = True,
    ) -> tuple[AgentIdempotencyKey, bool]:
        db_obj = self.get_by_action_key(db, obj_in.team_id, obj_in.user_id, obj_in.action_key)
        if db_obj:
            return db_obj, False

        candidate = AgentIdempotencyKey(**obj_in.model_dump())
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
        except IntegrityError:
            db_obj = self.get_by_action_key(db, obj_in.team_id, obj_in.user_id, obj_in.action_key)
            if db_obj is None:
                raise
            return db_obj, False
        if commit:
            db.commit()
            db.refresh(candidate)
        return candidate, True

    def get_or_create(
        self,
        db: Session,
        obj_in: AgentIdempotencyKeyCreate,
        *,
        commit: bool = True,
    ) -> AgentIdempotencyKey:
        db_obj, _ = self.ensure(db, obj_in, commit=commit)
        return db_obj

    def update(
        self,
        db: Session,
        db_obj: AgentIdempotencyKey,
        obj_in: AgentIdempotencyKeyUpdate,
        *,
        commit: bool = True,
    ) -> AgentIdempotencyKey:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        if commit:
            db.commit()
            db.refresh(db_obj)
        else:
            db.flush()
        return db_obj


class AgentWorkflowActionCRUD:
    def get_by_action_id(
        self,
        db: Session,
        action_id: str,
        team_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> Optional[AgentWorkflowAction]:
        query = db.query(AgentWorkflowAction).filter(AgentWorkflowAction.action_id == action_id)
        if team_id is not None:
            query = query.filter(AgentWorkflowAction.team_id == team_id)
        if user_id is not None:
            query = query.filter(AgentWorkflowAction.user_id == user_id)
        return query.first()

    def get_by_action_id_for_update(
        self,
        db: Session,
        action_id: str,
        *,
        team_id: int,
        user_id: int,
    ) -> Optional[AgentWorkflowAction]:
        return (
            db.query(AgentWorkflowAction)
            .filter(
                AgentWorkflowAction.action_id == action_id,
                AgentWorkflowAction.team_id == team_id,
                AgentWorkflowAction.user_id == user_id,
            )
            .populate_existing()
            .with_for_update()
            .first()
        )

    def create(
        self,
        db: Session,
        obj_in: AgentWorkflowActionCreate,
        *,
        commit: bool = True,
    ) -> AgentWorkflowAction:
        db_obj = AgentWorkflowAction(**obj_in.model_dump())
        db.add(db_obj)
        if commit:
            db.commit()
            db.refresh(db_obj)
        else:
            db.flush()
        return db_obj

    def update(
        self,
        db: Session,
        db_obj: AgentWorkflowAction,
        obj_in: AgentWorkflowActionUpdate,
        *,
        commit: bool = True,
    ) -> AgentWorkflowAction:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        if commit:
            db.commit()
            db.refresh(db_obj)
        else:
            db.flush()
        return db_obj

    def list_by_session(
        self,
        db: Session,
        session_id: int,
        team_id: Optional[int] = None,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: Optional[int] = None,
    ) -> List[AgentWorkflowAction]:
        query = db.query(AgentWorkflowAction).filter(AgentWorkflowAction.session_id == session_id)
        if team_id is not None:
            query = query.filter(AgentWorkflowAction.team_id == team_id)
        if user_id is not None:
            query = query.filter(AgentWorkflowAction.user_id == user_id)
        if status is not None:
            query = query.filter(AgentWorkflowAction.status == status)
        query = query.order_by(AgentWorkflowAction.created_time.asc(), AgentWorkflowAction.id.asc()).offset(skip)
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    def count_by_session(
        self,
        db: Session,
        session_id: int,
        team_id: Optional[int] = None,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> int:
        query = db.query(AgentWorkflowAction).filter(AgentWorkflowAction.session_id == session_id)
        if team_id is not None:
            query = query.filter(AgentWorkflowAction.team_id == team_id)
        if user_id is not None:
            query = query.filter(AgentWorkflowAction.user_id == user_id)
        if status is not None:
            query = query.filter(AgentWorkflowAction.status == status)
        return query.count()

    def list_actions(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: Optional[int] = None,
        include_system_actions: bool = True,
        session_id: Optional[int] = None,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
        source_type: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[int] = None,
        skip: int = 0,
        limit: Optional[int] = None,
    ) -> List[AgentWorkflowAction]:
        query = self._filtered_actions_query(
            db,
            team_id=team_id,
            user_id=user_id,
            include_system_actions=include_system_actions,
            session_id=session_id,
            workflow_id=workflow_id,
            status=status,
            source_type=source_type,
            target_type=target_type,
            target_id=target_id,
        )
        query = query.order_by(AgentWorkflowAction.created_time.desc(), AgentWorkflowAction.id.desc()).offset(skip)
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    def count_actions(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: Optional[int] = None,
        include_system_actions: bool = True,
        session_id: Optional[int] = None,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
        source_type: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[int] = None,
    ) -> int:
        return self._filtered_actions_query(
            db,
            team_id=team_id,
            user_id=user_id,
            include_system_actions=include_system_actions,
            session_id=session_id,
            workflow_id=workflow_id,
            status=status,
            source_type=source_type,
            target_type=target_type,
            target_id=target_id,
        ).count()

    def _filtered_actions_query(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: Optional[int],
        include_system_actions: bool,
        session_id: Optional[int],
        workflow_id: Optional[str],
        status: Optional[str],
        source_type: Optional[str],
        target_type: Optional[str],
        target_id: Optional[int],
    ):
        query = db.query(AgentWorkflowAction).filter(AgentWorkflowAction.team_id == team_id)
        if user_id is not None:
            if include_system_actions:
                query = query.filter(or_(AgentWorkflowAction.user_id == user_id, AgentWorkflowAction.user_id.is_(None)))
            else:
                query = query.filter(AgentWorkflowAction.user_id == user_id)
        if session_id is not None:
            query = query.filter(AgentWorkflowAction.session_id == session_id)
        if workflow_id:
            query = query.filter(AgentWorkflowAction.workflow_id == workflow_id)
        if status:
            query = query.filter(AgentWorkflowAction.status == status)
        if source_type:
            query = query.filter(AgentWorkflowAction.source_type == source_type)
        if target_type:
            query = query.filter(AgentWorkflowAction.target_type == target_type)
        if target_id is not None:
            query = query.filter(AgentWorkflowAction.target_id == target_id)
        return query

    def list_by_workflow(
        self,
        db: Session,
        workflow_id: str,
        team_id: Optional[int] = None,
        user_id: Optional[int] = None,
        include_system_actions: bool = False,
    ) -> List[AgentWorkflowAction]:
        query = db.query(AgentWorkflowAction).filter(AgentWorkflowAction.workflow_id == workflow_id)
        if team_id is not None:
            query = query.filter(AgentWorkflowAction.team_id == team_id)
        if user_id is not None:
            if include_system_actions:
                query = query.filter(or_(AgentWorkflowAction.user_id == user_id, AgentWorkflowAction.user_id.is_(None)))
            else:
                query = query.filter(AgentWorkflowAction.user_id == user_id)
        return query.order_by(AgentWorkflowAction.created_time.asc(), AgentWorkflowAction.id.asc()).all()


agent_session_crud = AgentSessionCRUD()
agent_message_crud = AgentMessageCRUD()
agent_tool_call_crud = AgentToolCallCRUD()
agent_idempotency_key_crud = AgentIdempotencyKeyCRUD()
agent_workflow_action_crud = AgentWorkflowActionCRUD()

"""CRM AI Agent CRUD.

This module only manages Agent-owned state. CRM business actions must go
through existing API endpoints in the tool layer.
"""
from typing import List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agent import (
    AgentIdempotencyKey,
    AgentMessage,
    AgentSession,
    AgentTask,
    AgentTaskStatus,
    AgentToolCall,
    AgentWorkflowAction,
    AgentWorkflowActionStatus,
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

    def get_by_id_for_update(
        self,
        db: Session,
        task_id: int,
        *,
        team_id: int,
        user_id: int,
    ) -> Optional[AgentTask]:
        return (
            db.query(AgentTask)
            .filter(
                AgentTask.id == task_id,
                AgentTask.team_id == team_id,
                AgentTask.user_id == user_id,
            )
            .populate_existing()
            .with_for_update()
            .first()
        )

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

    def get_or_create_by_task_key(self, db: Session, obj_in: AgentTaskCreate) -> tuple[AgentTask, bool]:
        """Return one globally unique task projection for a stable task key."""

        existing = self.get_by_key(db, obj_in.task_key)
        if existing is not None:
            return existing, False
        candidate = AgentTask(**obj_in.model_dump())
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
        except IntegrityError:
            existing = self.get_by_key(db, obj_in.task_key)
            if existing is None:
                raise
            return existing, False
        db.commit()
        db.refresh(candidate)
        return candidate, True

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

    def get_latest_waiting(
        self,
        db: Session,
        session_id: int,
        team_id: int,
        user_id: int,
    ) -> Optional[AgentTask]:
        return db.query(AgentTask).filter(
            AgentTask.session_id == session_id,
            AgentTask.team_id == team_id,
            AgentTask.user_id == user_id,
            AgentTask.status == AgentTaskStatus.WAITING_USER,
        ).order_by(AgentTask.created_time.desc(), AgentTask.id.desc()).first()

    def update(
        self,
        db: Session,
        db_obj: AgentTask,
        obj_in: AgentTaskUpdate,
        *,
        commit: bool = True,
    ) -> AgentTask:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        if commit:
            db.commit()
            db.refresh(db_obj)
        else:
            db.flush()
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

    def get_by_workflow_action(
        self,
        db: Session,
        *,
        workflow_id: str,
        action_id: str,
        team_id: Optional[int] = None,
        user_id: Optional[int] = None,
        include_system_actions: bool = False,
    ) -> Optional[AgentWorkflowAction]:
        query = db.query(AgentWorkflowAction).filter(
            AgentWorkflowAction.workflow_id == workflow_id,
            AgentWorkflowAction.action_id == action_id,
        )
        if team_id is not None:
            query = query.filter(AgentWorkflowAction.team_id == team_id)
        if user_id is not None:
            if include_system_actions:
                query = query.filter(or_(AgentWorkflowAction.user_id == user_id, AgentWorkflowAction.user_id.is_(None)))
            else:
                query = query.filter(AgentWorkflowAction.user_id == user_id)
        return query.first()

    def list_by_action_ids(
        self,
        db: Session,
        action_ids: List[str],
        team_id: Optional[int] = None,
        user_id: Optional[int] = None,
        include_system_actions: bool = False,
    ) -> List[AgentWorkflowAction]:
        normalized_ids = [action_id for action_id in action_ids if isinstance(action_id, str) and action_id]
        if not normalized_ids:
            return []
        query = db.query(AgentWorkflowAction).filter(AgentWorkflowAction.action_id.in_(normalized_ids))
        if team_id is not None:
            query = query.filter(AgentWorkflowAction.team_id == team_id)
        if user_id is not None:
            if include_system_actions:
                query = query.filter(or_(AgentWorkflowAction.user_id == user_id, AgentWorkflowAction.user_id.is_(None)))
            else:
                query = query.filter(AgentWorkflowAction.user_id == user_id)
        return query.order_by(AgentWorkflowAction.created_time.asc(), AgentWorkflowAction.id.asc()).all()

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

    def get_or_create(
        self,
        db: Session,
        obj_in: AgentWorkflowActionCreate,
        *,
        commit: bool = True,
    ) -> AgentWorkflowAction:
        db_obj = self.get_by_action_id(db, obj_in.action_id, team_id=obj_in.team_id, user_id=obj_in.user_id)
        if db_obj:
            return db_obj
        return self.create(db, obj_in, commit=commit)

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

    def count_by_status_for_session(
        self,
        db: Session,
        session_id: int,
        team_id: Optional[int] = None,
        user_id: Optional[int] = None,
        include_system_actions: bool = False,
    ) -> dict[str, int]:
        query = db.query(AgentWorkflowAction.status, func.count(AgentWorkflowAction.id)).filter(
            AgentWorkflowAction.session_id == session_id
        )
        if team_id is not None:
            query = query.filter(AgentWorkflowAction.team_id == team_id)
        if user_id is not None:
            if include_system_actions:
                query = query.filter(or_(AgentWorkflowAction.user_id == user_id, AgentWorkflowAction.user_id.is_(None)))
            else:
                query = query.filter(AgentWorkflowAction.user_id == user_id)
        return {status: int(count) for status, count in query.group_by(AgentWorkflowAction.status).all()}

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

    def list_retryable_workflow_candidates(
        self,
        db: Session,
        *,
        team_id: Optional[int] = None,
        user_id: Optional[int] = None,
        include_system_actions: bool = True,
        limit: int = 20,
    ) -> List[AgentWorkflowAction]:
        retryable_statuses = [
            AgentWorkflowActionStatus.FAILED,
            AgentWorkflowActionStatus.BLOCKED,
        ]
        query = db.query(AgentWorkflowAction).filter(AgentWorkflowAction.status.in_(retryable_statuses))
        if team_id is not None:
            query = query.filter(AgentWorkflowAction.team_id == team_id)
        if user_id is not None:
            if include_system_actions:
                query = query.filter(or_(AgentWorkflowAction.user_id == user_id, AgentWorkflowAction.user_id.is_(None)))
            else:
                query = query.filter(AgentWorkflowAction.user_id == user_id)
        return query.order_by(AgentWorkflowAction.last_modified_time.asc(), AgentWorkflowAction.id.asc()).limit(
            max(1, limit)
        ).all()


agent_session_crud = AgentSessionCRUD()
agent_message_crud = AgentMessageCRUD()
agent_task_crud = AgentTaskCRUD()
agent_tool_call_crud = AgentToolCallCRUD()
agent_idempotency_key_crud = AgentIdempotencyKeyCRUD()
agent_workflow_action_crud = AgentWorkflowActionCRUD()

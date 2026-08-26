"""Deep persistence module for immutable CRM query result sets."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from app.models.agent import AgentMessage, AgentMessageRole
from app.models.agent_persistence import AgentQueryResultSet
from app.schemas.agent_persistence import (
    AgentQueryResultSetCreate,
    AgentQueryResultSetRecord,
    AgentResultPage,
)
from app.services.agent.query.schemas import CRMQuerySpec, CRMResource, EntityRef
from app.utils.time import business_now

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_RESULT_SET_TTL = timedelta(hours=24)
_RESULT_SET_RETENTION = timedelta(days=7)
_ENTITY_REFS_ADAPTER = TypeAdapter(list[EntityRef])
_RESOURCE_ADAPTER: TypeAdapter[CRMResource] = TypeAdapter(CRMResource)


class ResultSetError(RuntimeError):
    """Base result-set registry error."""


class ResultSetNotFoundError(ResultSetError):
    """The caller does not own a result set with the supplied public ID."""


class ResultSetExpiredError(ResultSetError):
    """The owned result set exists but can no longer be reused."""


class ResultSetOwnershipError(ResultSetError):
    """A source message or parent result set does not match the requested owner."""


class AgentQueryResultSetRepository:
    """Create and resolve immutable query continuation snapshots."""

    def create(
        self,
        db: Session,
        request: AgentQueryResultSetCreate,
        *,
        now: datetime | None = None,
    ) -> AgentQueryResultSetRecord:
        created_at = now or business_now()
        self._require_owned_source_message(db, request)
        parent = self._resolve_parent(db, request)
        expires_at = request.expires_at or created_at + _RESULT_SET_TTL

        row = AgentQueryResultSet(
            public_id=request.public_id,
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
            source_message_id=request.source_message_id,
            parent_result_set_id=parent.id if parent is not None else None,
            resource=request.resource,
            query_json=request.query.model_dump(mode="json"),
            ordered_entity_refs_json=[],
            page_json=request.page.model_dump(mode="json"),
            row_count=len(request.ordered_entity_refs),
            expires_at=expires_at,
            created_time=created_at,
        )
        db.add(row)
        db.flush()

        refs = [ref.model_copy(update={"result_set_id": str(row.public_id)}) for ref in request.ordered_entity_refs]
        row.ordered_entity_refs_json = [ref.model_dump(mode="json") for ref in refs]
        db.flush()
        return self._to_record(row, parent_public_id=str(parent.public_id) if parent is not None else None)

    def get_active(
        self,
        db: Session,
        *,
        public_id: str,
        team_id: int,
        user_id: int,
        session_id: int,
        now: datetime | None = None,
    ) -> AgentQueryResultSetRecord:
        row = self._get_owned(
            db,
            public_id=public_id,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
        )
        if row is None:
            raise ResultSetNotFoundError("result set not found")
        if row.expires_at <= (now or business_now()):
            raise ResultSetExpiredError("result set expired")
        return self._to_record(row, parent_public_id=self._parent_public_id(db, row))

    def get_latest_active(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        now: datetime | None = None,
    ) -> AgentQueryResultSetRecord | None:
        row = (
            db.query(AgentQueryResultSet)
            .filter(
                AgentQueryResultSet.team_id == team_id,
                AgentQueryResultSet.user_id == user_id,
                AgentQueryResultSet.session_id == session_id,
                AgentQueryResultSet.expires_at > (now or business_now()),
            )
            .order_by(
                AgentQueryResultSet.created_time.desc(),
                AgentQueryResultSet.id.desc(),
            )
            .first()
        )
        if row is None:
            return None
        return self._to_record(row, parent_public_id=self._parent_public_id(db, row))

    def purge_expired(
        self,
        db: Session,
        *,
        team_id: int,
        now: datetime | None = None,
    ) -> int:
        cutoff = (now or business_now()) - _RESULT_SET_RETENTION
        return int(
            db.query(AgentQueryResultSet)
            .filter(
                AgentQueryResultSet.team_id == team_id,
                AgentQueryResultSet.expires_at <= cutoff,
            )
            .delete(synchronize_session=False)
        )

    @staticmethod
    def _require_owned_source_message(db: Session, request: AgentQueryResultSetCreate) -> None:
        owned = (
            db.query(AgentMessage.id)
            .filter(
                AgentMessage.id == request.source_message_id,
                AgentMessage.team_id == request.team_id,
                AgentMessage.user_id == request.user_id,
                AgentMessage.session_id == request.session_id,
                AgentMessage.role == AgentMessageRole.ASSISTANT,
            )
            .first()
        )
        if owned is None:
            raise ResultSetOwnershipError("source message must be an assistant message owned by the result set owner")

    def _resolve_parent(
        self,
        db: Session,
        request: AgentQueryResultSetCreate,
    ) -> AgentQueryResultSet | None:
        if request.parent_result_set_id is None:
            return None
        parent = self._get_owned(
            db,
            public_id=request.parent_result_set_id,
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
        )
        if parent is None:
            raise ResultSetOwnershipError("parent result set does not belong to result set owner")
        return parent

    @staticmethod
    def _get_owned(
        db: Session,
        *,
        public_id: str,
        team_id: int,
        user_id: int,
        session_id: int,
    ) -> AgentQueryResultSet | None:
        return (
            db.query(AgentQueryResultSet)
            .filter(
                AgentQueryResultSet.public_id == public_id,
                AgentQueryResultSet.team_id == team_id,
                AgentQueryResultSet.user_id == user_id,
                AgentQueryResultSet.session_id == session_id,
            )
            .one_or_none()
        )

    @staticmethod
    def _parent_public_id(db: Session, row: AgentQueryResultSet) -> str | None:
        if row.parent_result_set_id is None:
            return None
        parent = (
            db.query(AgentQueryResultSet.public_id)
            .filter(
                AgentQueryResultSet.id == row.parent_result_set_id,
                AgentQueryResultSet.team_id == row.team_id,
                AgentQueryResultSet.user_id == row.user_id,
                AgentQueryResultSet.session_id == row.session_id,
            )
            .one_or_none()
        )
        if parent is None:
            raise ResultSetOwnershipError("parent result set does not belong to result set owner")
        return str(parent.public_id)

    @staticmethod
    def _to_record(
        row: AgentQueryResultSet,
        *,
        parent_public_id: str | None,
    ) -> AgentQueryResultSetRecord:
        return AgentQueryResultSetRecord(
            public_id=str(row.public_id),
            team_id=int(row.team_id),
            user_id=int(row.user_id),
            session_id=int(row.session_id),
            source_message_id=int(row.source_message_id),
            parent_result_set_id=parent_public_id,
            resource=_RESOURCE_ADAPTER.validate_python(row.resource),
            query=CRMQuerySpec.model_validate(row.query_json),
            ordered_entity_refs=_ENTITY_REFS_ADAPTER.validate_python(row.ordered_entity_refs_json),
            page=AgentResultPage.model_validate(row.page_json),
            row_count=int(row.row_count),
            expires_at=row.expires_at,
            created_time=row.created_time,
        )

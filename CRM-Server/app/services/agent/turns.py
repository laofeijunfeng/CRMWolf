"""Idempotent turn and target-message persistence for the unified Agent runtime."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import JsonValue, TypeAdapter
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.models.agent import AgentMessage, AgentMessageRole, AgentSession
from app.schemas.agent_persistence import (
    AgentAssistantMessageCreate,
    AgentAssistantMessageWriteResult,
    AgentAssistantProjectionCreate,
    AgentPersistedMessageRecord,
    AgentPersistedMessageRole,
    AgentTurnBeginResult,
    AgentTurnStart,
    AgentUIMessageBody,
)
from app.services.agent.ui.schemas import AgentUIEnvelope, InteractionBlock
from app.utils.public_id import generate_public_id
from app.utils.time import business_now

if TYPE_CHECKING:
    from sqlalchemy.orm import Query, Session

_MESSAGE_ROLE_ADAPTER: TypeAdapter[AgentPersistedMessageRole] = TypeAdapter(AgentPersistedMessageRole)
_DIAGNOSTICS_ADAPTER: TypeAdapter[dict[str, JsonValue] | None] = TypeAdapter(dict[str, JsonValue] | None)


class AgentTurnError(RuntimeError):
    """Base turn repository error."""


class AgentTurnOwnershipError(AgentTurnError):
    """The session or turn does not belong to the supplied owner."""


class AgentTurnIdempotencyConflictError(AgentTurnError):
    """A client request ID or turn was reused with different immutable input."""


class AgentTurnPersistenceError(AgentTurnError):
    """Persisted target-message data violates the frozen Agent UI contract."""


@dataclass(frozen=True)
class AgentTurnMessageSnapshot:
    """Minimal owned message data used by background projection recovery."""

    id: int
    turn_id: str
    diagnostics: dict[str, JsonValue] | None


class AgentTurnRepository:
    """Own turn identity, request replay, and final message uniqueness behind one interface."""

    def begin(
        self,
        db: Session,
        request: AgentTurnStart,
    ) -> AgentTurnBeginResult:
        self._require_owned_session(
            db,
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
        )
        request_id = str(request.client_request_id)
        # A locking read for an absent request key creates a MySQL gap lock.
        # Two first attempts can then deadlock when both insert the same unique key.
        # Use a snapshot read here; the unique constraint arbitrates creation, and
        # the duplicate-key path below performs a current locking read for replay.
        existing = self._get_by_request(
            db,
            team_id=request.team_id,
            user_id=request.user_id,
            client_request_id=request_id,
            lock=False,
        )
        if existing is not None:
            return self._replay_begin(db, existing, request)

        now = business_now()
        candidate = AgentMessage(
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
            role=AgentMessageRole.USER,
            event_type=None,
            content=request.content,
            payload_json=None,
            turn_id=generate_public_id("turn"),
            client_request_id=request_id,
            ui_json=None,
            diagnostics_json={"request_input_fingerprint": request.input_fingerprint},
            created_time=now,
            last_modified_time=now,
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
                candidate.ui_json = self._build_envelope(
                    message_id=int(candidate.id),
                    turn_id=self._required_turn_id(candidate),
                    role="user",
                    body=request.ui,
                ).model_dump(mode="json")
                db.flush()
        except IntegrityError:
            existing = self._get_by_request(
                db,
                team_id=request.team_id,
                user_id=request.user_id,
                client_request_id=request_id,
                lock=True,
            )
            if existing is None:
                raise
            return self._replay_begin(db, existing, request)

        return AgentTurnBeginResult(outcome="CREATED", user_message=self._to_record(candidate))

    def complete(
        self,
        db: Session,
        request: AgentAssistantMessageCreate,
    ) -> AgentAssistantMessageWriteResult:
        user_message = self._get_turn_message(
            db,
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
            turn_id=request.turn_id,
            role=AgentMessageRole.USER,
            lock=True,
        )
        if user_message is None:
            raise AgentTurnOwnershipError("owned user turn not found")

        existing = self._get_turn_message(
            db,
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
            turn_id=request.turn_id,
            role=AgentMessageRole.ASSISTANT,
            lock=True,
        )
        if existing is not None:
            self._assert_same_assistant(existing, request)
            return AgentAssistantMessageWriteResult(outcome="REPLAY", message=self._to_record(existing))

        now = business_now()
        candidate = AgentMessage(
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
            role=AgentMessageRole.ASSISTANT,
            event_type=None,
            content=request.content,
            payload_json=None,
            turn_id=request.turn_id,
            client_request_id=None,
            ui_json=None,
            diagnostics_json=request.diagnostics,
            created_time=now,
            last_modified_time=now,
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
                candidate.ui_json = self._build_envelope(
                    message_id=int(candidate.id),
                    turn_id=request.turn_id,
                    role="assistant",
                    body=request.ui,
                ).model_dump(mode="json")
                db.flush()
        except IntegrityError:
            existing = self._get_turn_message(
                db,
                team_id=request.team_id,
                user_id=request.user_id,
                session_id=request.session_id,
                turn_id=request.turn_id,
                role=AgentMessageRole.ASSISTANT,
                lock=True,
            )
            if existing is None:
                raise
            self._assert_same_assistant(existing, request)
            return AgentAssistantMessageWriteResult(outcome="REPLAY", message=self._to_record(existing))

        return AgentAssistantMessageWriteResult(outcome="CREATED", message=self._to_record(candidate))

    def list_assistant_messages_with_diagnostics(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
    ) -> list[AgentTurnMessageSnapshot]:
        """Return owned assistant turns that can carry durable-work receipts."""

        rows = (
            db.query(AgentMessage)
            .filter(
                AgentMessage.team_id == team_id,
                AgentMessage.user_id == user_id,
                AgentMessage.session_id == session_id,
                AgentMessage.role == AgentMessageRole.ASSISTANT,
                AgentMessage.turn_id.is_not(None),
                AgentMessage.diagnostics_json.is_not(None),
            )
            .order_by(AgentMessage.id.asc())
            .all()
        )
        return [self._to_snapshot(row) for row in rows]

    def list_user_messages_by_turn_ids(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        turn_ids: set[str],
    ) -> list[AgentTurnMessageSnapshot]:
        """Return owned user messages for the exact durable-work turn identities."""

        if not turn_ids:
            return []
        rows = (
            db.query(AgentMessage)
            .filter(
                AgentMessage.team_id == team_id,
                AgentMessage.user_id == user_id,
                AgentMessage.session_id == session_id,
                AgentMessage.role == AgentMessageRole.USER,
                AgentMessage.turn_id.in_(turn_ids),
            )
            .all()
        )
        return [self._to_snapshot(row) for row in rows]

    def get_assistant_projection(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        projection_key: str,
        lock: bool = False,
    ) -> AgentPersistedMessageRecord | None:
        self._require_owned_session(
            db,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
        )
        row = self._get_turn_message(
            db,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            turn_id=self._projection_turn_id(projection_key),
            role=AgentMessageRole.ASSISTANT,
            lock=lock,
        )
        return self._to_record(row) if row is not None else None

    def project_assistant(
        self,
        db: Session,
        request: AgentAssistantProjectionCreate,
    ) -> AgentAssistantMessageWriteResult:
        self._require_owned_session(
            db,
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
        )
        turn_id = self._projection_turn_id(request.projection_key)
        assistant_request = AgentAssistantMessageCreate(
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
            turn_id=turn_id,
            content=request.content,
            ui=request.ui,
            diagnostics={
                **(request.diagnostics or {}),
                "projection_key": request.projection_key,
            },
        )
        existing = self._get_turn_message(
            db,
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
            turn_id=turn_id,
            role=AgentMessageRole.ASSISTANT,
            lock=True,
        )
        if existing is not None:
            self._assert_same_assistant(existing, assistant_request)
            return AgentAssistantMessageWriteResult(outcome="REPLAY", message=self._to_record(existing))

        now = business_now()
        candidate = AgentMessage(
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
            role=AgentMessageRole.ASSISTANT,
            event_type=None,
            content=request.content,
            payload_json=None,
            turn_id=turn_id,
            client_request_id=None,
            ui_json=None,
            diagnostics_json=assistant_request.diagnostics,
            created_time=now,
            last_modified_time=now,
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
                candidate.ui_json = self._build_envelope(
                    message_id=int(candidate.id),
                    turn_id=turn_id,
                    role="assistant",
                    body=request.ui,
                ).model_dump(mode="json")
                db.flush()
        except IntegrityError:
            existing = self._get_turn_message(
                db,
                team_id=request.team_id,
                user_id=request.user_id,
                session_id=request.session_id,
                turn_id=turn_id,
                role=AgentMessageRole.ASSISTANT,
                lock=True,
            )
            if existing is None:
                raise
            self._assert_same_assistant(existing, assistant_request)
            return AgentAssistantMessageWriteResult(outcome="REPLAY", message=self._to_record(existing))
        return AgentAssistantMessageWriteResult(outcome="CREATED", message=self._to_record(candidate))

    def get_owned_message(
        self,
        db: Session,
        *,
        message_id: int,
        team_id: int,
        user_id: int,
        session_id: int,
    ) -> AgentPersistedMessageRecord:
        row = (
            db.query(AgentMessage)
            .filter(
                AgentMessage.id == message_id,
                AgentMessage.team_id == team_id,
                AgentMessage.user_id == user_id,
                AgentMessage.session_id == session_id,
            )
            .one_or_none()
        )
        if row is None:
            raise AgentTurnOwnershipError("owned message not found")
        return self._to_record(row)

    def list_visible_by_session(
        self,
        db: Session,
        *,
        session_id: int,
        team_id: int,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
        exclude_message_ids: list[int] | None = None,
    ) -> tuple[list[AgentPersistedMessageRecord], int]:
        """Page only user-visible conversation messages."""

        self._require_owned_session(
            db,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
        )
        display = AgentMessage.ui_json["metadata"]["display"].as_string()
        query = db.query(AgentMessage).filter(
            AgentMessage.session_id == session_id,
            AgentMessage.team_id == team_id,
            AgentMessage.user_id == user_id,
            func.coalesce(display, "MESSAGE") != "STATE_UPDATE",
        )
        if exclude_message_ids:
            query = query.filter(AgentMessage.id.notin_(exclude_message_ids))
        total = int(query.count())
        query = query.with_hint(
            AgentMessage,
            "FORCE INDEX (idx_agent_message_history_owner_order)",
            dialect_name="mysql",
        )
        rows = (
            query.order_by(AgentMessage.created_time.asc(), AgentMessage.id.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [self._to_record(row) for row in rows], total

    def list_visible_message_ids_by_session(
        self,
        db: Session,
        *,
        session_id: int,
        team_id: int,
        user_id: int,
    ) -> list[int]:
        """Return visible message IDs for read-time history projections.

        This intentionally returns IDs only.  Callers can use the IDs to
        resolve immutable message actions before applying a projection, while
        keeping the normal history query paginated.
        """

        self._require_owned_session(
            db,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
        )
        display = AgentMessage.ui_json["metadata"]["display"].as_string()
        rows = (
            db.query(AgentMessage.id)
            .filter(
                AgentMessage.session_id == session_id,
                AgentMessage.team_id == team_id,
                AgentMessage.user_id == user_id,
                func.coalesce(display, "MESSAGE") != "STATE_UPDATE",
            )
            .order_by(AgentMessage.created_time.asc(), AgentMessage.id.asc())
            .all()
        )
        return [int(row[0]) for row in rows]

    def _replay_begin(
        self,
        db: Session,
        row: AgentMessage,
        request: AgentTurnStart,
    ) -> AgentTurnBeginResult:
        self._assert_same_start(row, request)
        turn_id = self._required_turn_id(row)
        assistant = self._get_turn_message(
            db,
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
            turn_id=turn_id,
            role=AgentMessageRole.ASSISTANT,
            lock=False,
        )
        return AgentTurnBeginResult(
            outcome="COMPLETED" if assistant is not None else "IN_PROGRESS",
            user_message=self._to_record(row),
            assistant_message=self._to_record(assistant) if assistant is not None else None,
        )

    @staticmethod
    def _require_owned_session(
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
    ) -> None:
        owned = (
            db.query(AgentSession.id)
            .filter(
                AgentSession.id == session_id,
                AgentSession.team_id == team_id,
                AgentSession.user_id == user_id,
            )
            .first()
        )
        if owned is None:
            raise AgentTurnOwnershipError("owned session not found")

    @staticmethod
    def _get_by_request(
        db: Session,
        *,
        team_id: int,
        user_id: int,
        client_request_id: str,
        lock: bool,
    ) -> AgentMessage | None:
        query = db.query(AgentMessage).filter(
            AgentMessage.team_id == team_id,
            AgentMessage.user_id == user_id,
            AgentMessage.client_request_id == client_request_id,
        )
        return AgentTurnRepository._finish_query(query, lock=lock)

    @staticmethod
    def _get_turn_message(
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        turn_id: str,
        role: str,
        lock: bool,
    ) -> AgentMessage | None:
        query = db.query(AgentMessage).filter(
            AgentMessage.team_id == team_id,
            AgentMessage.user_id == user_id,
            AgentMessage.session_id == session_id,
            AgentMessage.turn_id == turn_id,
            AgentMessage.role == role,
        )
        return AgentTurnRepository._finish_query(query, lock=lock)

    @staticmethod
    def _finish_query(query: Query[AgentMessage], *, lock: bool) -> AgentMessage | None:
        if lock:
            query = query.populate_existing().with_for_update()
        return query.one_or_none()

    def _assert_same_start(self, row: AgentMessage, request: AgentTurnStart) -> None:
        if int(row.session_id) != request.session_id or row.role != AgentMessageRole.USER:
            raise AgentTurnIdempotencyConflictError("client request ID belongs to a different turn")
        expected = self._build_envelope(
            message_id=int(row.id),
            turn_id=self._required_turn_id(row),
            role="user",
            body=request.ui,
        )
        diagnostics = row.diagnostics_json
        persisted_fingerprint = (
            diagnostics.get("request_input_fingerprint")
            if isinstance(diagnostics, dict)
            else None
        )
        if (
            persisted_fingerprint != request.input_fingerprint
            or row.content != request.content
            or self._validated_envelope(row) != expected
        ):
            raise AgentTurnIdempotencyConflictError("client request ID was reused with different input")

    def _assert_same_assistant(self, row: AgentMessage, request: AgentAssistantMessageCreate) -> None:
        expected = self._build_envelope(
            message_id=int(row.id),
            turn_id=request.turn_id,
            role="assistant",
            body=request.ui,
        )
        if (
            row.content != request.content
            or row.diagnostics_json != request.diagnostics
            or self._validated_envelope(row) != expected
        ):
            raise AgentTurnIdempotencyConflictError("assistant turn was completed with different output")

    @staticmethod
    def _build_envelope(
        *,
        message_id: int,
        turn_id: str,
        role: str,
        body: AgentUIMessageBody,
    ) -> AgentUIEnvelope:
        return AgentUIEnvelope.model_validate(
            {
                "schema_version": "crm.agent.ui.v1",
                "message_id": message_id,
                "turn_id": turn_id,
                "role": role,
                **body.model_dump(mode="json"),
            }
        )

    @staticmethod
    def _projection_turn_id(projection_key: str) -> str:
        digest = hashlib.sha256(projection_key.encode("utf-8")).hexdigest()[:32]
        return f"turn_{digest}"

    @staticmethod
    def _required_turn_id(row: AgentMessage) -> str:
        if not row.turn_id:
            raise AgentTurnPersistenceError("target message is missing turn_id")
        return row.turn_id

    @staticmethod
    def _validated_envelope(row: AgentMessage) -> AgentUIEnvelope:
        if row.ui_json is None:
            raise AgentTurnPersistenceError("target message is missing ui_json")
        envelope = AgentUIEnvelope.model_validate(row.ui_json)
        if row.role != AgentMessageRole.ASSISTANT:
            return envelope

        blocks = [
            block.model_copy(
                update={
                    "prompt": block.prompt,
                }
            )
            if isinstance(block, InteractionBlock) and block.presentation == "COMPACT_TASK_COMPLETION"
            else block
            for block in envelope.blocks
        ]
        if blocks == envelope.blocks:
            return envelope
        return envelope.model_copy(update={"blocks": blocks})

    @staticmethod
    def _to_snapshot(row: AgentMessage) -> AgentTurnMessageSnapshot:
        if not row.turn_id:
            raise AgentTurnPersistenceError("target message is missing turn_id")
        return AgentTurnMessageSnapshot(
            id=int(row.id),
            turn_id=str(row.turn_id),
            diagnostics=_DIAGNOSTICS_ADAPTER.validate_python(row.diagnostics_json),
        )

    def _to_record(self, row: AgentMessage) -> AgentPersistedMessageRecord:
        if row.content is None:
            raise AgentTurnPersistenceError("target message is missing content")
        if row.last_modified_time is None:
            raise AgentTurnPersistenceError("target message is missing last_modified_time")
        return AgentPersistedMessageRecord(
            id=int(row.id),
            team_id=int(row.team_id),
            user_id=int(row.user_id),
            session_id=int(row.session_id),
            role=_MESSAGE_ROLE_ADAPTER.validate_python(row.role),
            turn_id=self._required_turn_id(row),
            client_request_id=row.client_request_id,
            content=row.content,
            ui=self._validated_envelope(row),
            diagnostics=_DIAGNOSTICS_ADAPTER.validate_python(row.diagnostics_json),
            created_time=row.created_time,
            last_modified_time=row.last_modified_time,
        )

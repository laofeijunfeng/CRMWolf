"""Atomic registration and consumption of server-owned Agent UI actions."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import JsonValue, TypeAdapter
from sqlalchemy import or_

from app.models.agent import AgentMessage
from app.models.agent_persistence import (
    AgentUIAction,
    AgentUIActionConsumptionMode,
    AgentUIActionStatus,
)
from app.schemas.agent_persistence import (
    AgentUIActionConsumption,
    AgentUIActionRecord,
    AgentUIActionRegistration,
    AgentUIActionType,
)
from app.schemas.agent_persistence import (
    AgentUIActionConsumptionMode as UIActionConsumptionMode,
)
from app.schemas.agent_persistence import (
    AgentUIActionStatus as UIActionStatus,
)
from app.services.agent.orchestrator.contracts import WorkflowContinuation
from app.utils.time import business_now

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_ACTION_TTL = timedelta(hours=24)
logger = logging.getLogger(__name__)
_ACTION_TERMINAL_RETENTION = timedelta(days=30)
_ACTION_TYPE_ADAPTER: TypeAdapter[AgentUIActionType] = TypeAdapter(AgentUIActionType)
_CONSUMPTION_MODE_ADAPTER: TypeAdapter[UIActionConsumptionMode] = TypeAdapter(UIActionConsumptionMode)
_ACTION_STATUS_ADAPTER: TypeAdapter[UIActionStatus] = TypeAdapter(UIActionStatus)


class AgentUIActionError(RuntimeError):
    """Base Agent UI action registry error."""


class ActionNotFoundError(AgentUIActionError):
    """No action is visible to the supplied owner."""


class ActionExpiredError(AgentUIActionError):
    """The action TTL elapsed before consumption."""


class ActionUnavailableError(AgentUIActionError):
    """The action was revoked or is otherwise unavailable."""


class ActionAlreadyConsumedError(AgentUIActionError):
    """A different request already claimed this one-shot action."""


class ActionStateConflictError(AgentUIActionError):
    """The requested transition does not match the current action state."""


class ActionOwnershipError(AgentUIActionError):
    """A message referenced by an action does not match its owner."""


class AgentUIActionRepository:
    """Hide locking, replay, TTL, and ownership rules behind one interface."""

    def get_owned(
        self,
        db: Session,
        *,
        public_id: str,
        team_id: int,
        user_id: int,
        session_id: int,
    ) -> AgentUIActionRecord | None:
        row = (
            db.query(AgentUIAction)
            .filter(
                AgentUIAction.public_id == public_id,
                AgentUIAction.team_id == team_id,
                AgentUIAction.user_id == user_id,
                AgentUIAction.session_id == session_id,
            )
            .one_or_none()
        )
        return self._to_record(row) if row is not None else None

    def list_owned_for_messages(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        message_ids: list[int],
    ) -> list[AgentUIActionRecord]:
        if not message_ids:
            return []
        rows = (
            db.query(AgentUIAction)
            .filter(
                AgentUIAction.team_id == team_id,
                AgentUIAction.user_id == user_id,
                AgentUIAction.session_id == session_id,
                AgentUIAction.message_id.in_(message_ids),
            )
            .all()
        )
        return [self._to_record(row) for row in rows]

    def list_active_workflow_continuations(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        now: datetime | None = None,
    ) -> list[WorkflowContinuation]:
        """Return only explicitly resumable native Workflow continuations.

        Pending confirmation Cases are deliberately excluded.  They are business
        work items projected into the conversation, not an active conversational
        Workflow.  A later turn may reference such a Case explicitly, but an
        ignored card must never become implicit Root context.
        """

        effective_now = now or business_now()
        rows = (
            db.query(AgentUIAction)
            .filter(
                AgentUIAction.team_id == team_id,
                AgentUIAction.user_id == user_id,
                AgentUIAction.session_id == session_id,
                AgentUIAction.action_type == "submit_interaction",
                AgentUIAction.root_context_role == "RESUMABLE_WORKFLOW",
                AgentUIAction.status == AgentUIActionStatus.ACTIVE,
                AgentUIAction.expires_at > effective_now,
            )
            .order_by(
                AgentUIAction.created_time.desc(),
                AgentUIAction.id.desc(),
            )
            .limit(20)
            .all()
        )
        continuations: list[WorkflowContinuation] = []
        seen_workflow_ids: set[str] = set()
        for row in rows:
            target = row.target_json if isinstance(row.target_json, dict) else {}
            continuation = WorkflowContinuation.model_validate(
                target.get("workflow_continuation")
            )
            # The action ledger owns the interaction contract. Enrich the
            # checkpoint locator from the signed action target so Root can
            # reject free-text resumes for confirmation/form/choice waits.
            interaction_type = target.get("interaction_type")
            if continuation.waiting_interaction_type is None and isinstance(
                interaction_type, str
            ):
                continuation = continuation.model_copy(
                    update={"waiting_interaction_type": interaction_type}
                )
            workflow_id = continuation.workflow_ref.workflow_id
            if workflow_id in seen_workflow_ids:
                continue
            seen_workflow_ids.add(workflow_id)
            continuations.append(continuation)
        return continuations

    def revoke_for_follow_up_confirmation_case(
        self,
        db: Session,
        *,
        team_id: int,
        case_public_id: str,
        reason: str,
        now: datetime | None = None,
    ) -> int:
        """Revoke live UI actions owned by one follow-up confirmation Case.

        A Case is the authoritative business state. UI actions are only a
        durable projection of that state, so cancellation must close every
        still-live action without deleting the historical row. Target JSON is
        intentionally not mutated: it is the signed, immutable action target.
        """

        revoked_at = now or business_now()
        rows = (
            db.query(AgentUIAction)
            .filter(
                AgentUIAction.team_id == team_id,
                # The Case public id is part of the signed projection target.
                # Filter it in SQL before locking rows; loading every live
                # action for a team turns Case cancellation into an avoidable
                # team-wide scan as Agent UI traffic grows.
                AgentUIAction.target_json["follow_up_confirmation_case_public_id"].as_string()
                == case_public_id,
                AgentUIAction.status.in_(
                    [AgentUIActionStatus.ACTIVE, AgentUIActionStatus.CONSUMING]
                ),
            )
            .populate_existing()
            .with_for_update()
            .all()
        )
        revoked_count = 0
        for row in rows:
            row.status = AgentUIActionStatus.REVOKED
            row.last_modified_time = revoked_at
            row.lock_version = int(row.lock_version) + 1
            revoked_count += 1

        if revoked_count:
            db.flush()
            logger.info(
                "Revoked Agent UI actions for follow-up confirmation Case",
                extra={
                    "team_id": team_id,
                    "case_public_id": case_public_id,
                    "reason": reason,
                    "revoked_count": revoked_count,
                },
            )
        return revoked_count

    def register(
        self,
        db: Session,
        request: AgentUIActionRegistration,
        *,
        now: datetime | None = None,
    ) -> AgentUIActionRecord:
        created_at = now or business_now()
        self._require_owned_message(
            db,
            message_id=request.message_id,
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
        )
        row = AgentUIAction(
            public_id=request.public_id,
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
            message_id=request.message_id,
            action_type=request.action_type,
            root_context_role=request.root_context_role,
            target_json=request.target,
            consumption_mode=request.consumption_mode,
            status=AgentUIActionStatus.ACTIVE,
            expires_at=request.expires_at or created_at + _ACTION_TTL,
            lock_version=0,
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(row)
        db.flush()
        return self._to_record(row)

    def begin_consumption(
        self,
        db: Session,
        *,
        public_id: str,
        team_id: int,
        user_id: int,
        session_id: int,
        client_request_id: UUID | str,
        now: datetime | None = None,
    ) -> AgentUIActionConsumption:
        requested_at = now or business_now()
        request_id = self._request_id(client_request_id)
        row = self._lock_owned(
            db,
            public_id=public_id,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
        )
        if row is None:
            raise ActionNotFoundError("action not found")
        if row.status == AgentUIActionStatus.REVOKED:
            raise ActionUnavailableError("action revoked")
        if row.expires_at <= requested_at and row.status not in {
            AgentUIActionStatus.CONSUMED,
            AgentUIActionStatus.REVOKED,
        }:
            row.status = AgentUIActionStatus.EXPIRED
            row.last_modified_time = requested_at
            row.lock_version = int(row.lock_version) + 1
            db.flush()
            raise ActionExpiredError("action expired")
        if row.status == AgentUIActionStatus.EXPIRED:
            raise ActionExpiredError("action expired")
        if row.consumption_mode == AgentUIActionConsumptionMode.REUSABLE:
            return AgentUIActionConsumption(outcome="REUSABLE", action=self._to_record(row))
        if row.status == AgentUIActionStatus.ACTIVE:
            row.status = AgentUIActionStatus.CONSUMING
            row.consumed_request_id = request_id
            row.last_modified_time = requested_at
            row.lock_version = int(row.lock_version) + 1
            db.flush()
            return AgentUIActionConsumption(outcome="ACQUIRED", action=self._to_record(row))
        if row.consumed_request_id == request_id and row.status in {
            AgentUIActionStatus.CONSUMING,
            AgentUIActionStatus.CONSUMED,
        }:
            return AgentUIActionConsumption(outcome="REPLAY", action=self._to_record(row))
        raise ActionAlreadyConsumedError("one-shot action already consumed by another request")

    def complete_consumption(
        self,
        db: Session,
        *,
        public_id: str,
        team_id: int,
        user_id: int,
        session_id: int,
        client_request_id: UUID | str,
        result_message_id: int,
        submitted_values: dict[str, JsonValue] | None = None,
        now: datetime | None = None,
    ) -> AgentUIActionRecord:
        completed_at = now or business_now()
        request_id = self._request_id(client_request_id)
        row = self._require_locked_owned(
            db,
            public_id=public_id,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
        )
        if row.consumed_request_id != request_id:
            raise ActionAlreadyConsumedError("one-shot action belongs to another request")
        if row.status == AgentUIActionStatus.CONSUMED:
            if row.result_message_id != result_message_id:
                raise ActionStateConflictError("completed action result message cannot change")
            return self._to_record(row)
        if row.status != AgentUIActionStatus.CONSUMING:
            raise ActionStateConflictError("action is not being consumed")
        self._require_owned_message(
            db,
            message_id=result_message_id,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
        )
        row.status = AgentUIActionStatus.CONSUMED
        row.submitted_values = submitted_values
        row.result_message_id = result_message_id
        row.consumed_at = completed_at
        row.last_modified_time = completed_at
        row.lock_version = int(row.lock_version) + 1
        db.flush()
        return self._to_record(row)

    def release_consumption(
        self,
        db: Session,
        *,
        public_id: str,
        team_id: int,
        user_id: int,
        session_id: int,
        client_request_id: UUID | str,
        now: datetime | None = None,
    ) -> AgentUIActionRecord:
        released_at = now or business_now()
        request_id = self._request_id(client_request_id)
        row = self._require_locked_owned(
            db,
            public_id=public_id,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
        )
        if row.status != AgentUIActionStatus.CONSUMING or row.consumed_request_id != request_id:
            raise ActionStateConflictError("only the claiming request can release an uncommitted action")
        row.status = AgentUIActionStatus.ACTIVE
        row.consumed_request_id = None
        row.last_modified_time = released_at
        row.lock_version = int(row.lock_version) + 1
        db.flush()
        return self._to_record(row)

    def purge_terminal(
        self,
        db: Session,
        *,
        team_id: int,
        now: datetime | None = None,
    ) -> int:
        cutoff = (now or business_now()) - _ACTION_TERMINAL_RETENTION
        return int(
            db.query(AgentUIAction)
            .filter(
                AgentUIAction.team_id == team_id,
                AgentUIAction.status.in_(
                    [
                        AgentUIActionStatus.CONSUMED,
                        AgentUIActionStatus.EXPIRED,
                        AgentUIActionStatus.REVOKED,
                    ]
                ),
                AgentUIAction.last_modified_time <= cutoff,
                or_(AgentUIAction.consumed_at.is_(None), AgentUIAction.consumed_at <= cutoff),
            )
            .delete(synchronize_session=False)
        )

    def _require_locked_owned(
        self,
        db: Session,
        *,
        public_id: str,
        team_id: int,
        user_id: int,
        session_id: int,
    ) -> AgentUIAction:
        row = self._lock_owned(
            db,
            public_id=public_id,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
        )
        if row is None:
            raise ActionNotFoundError("action not found")
        return row

    @staticmethod
    def _lock_owned(
        db: Session,
        *,
        public_id: str,
        team_id: int,
        user_id: int,
        session_id: int,
    ) -> AgentUIAction | None:
        return (
            db.query(AgentUIAction)
            .filter(
                AgentUIAction.public_id == public_id,
                AgentUIAction.team_id == team_id,
                AgentUIAction.user_id == user_id,
                AgentUIAction.session_id == session_id,
            )
            .populate_existing()
            .with_for_update()
            .one_or_none()
        )

    @staticmethod
    def _require_owned_message(
        db: Session,
        *,
        message_id: int,
        team_id: int,
        user_id: int,
        session_id: int,
    ) -> None:
        message = (
            db.query(AgentMessage.id)
            .filter(
                AgentMessage.id == message_id,
                AgentMessage.team_id == team_id,
                AgentMessage.user_id == user_id,
                AgentMessage.session_id == session_id,
            )
            .first()
        )
        if message is None:
            raise ActionOwnershipError("message does not belong to action owner")

    @staticmethod
    def _request_id(value: UUID | str) -> str:
        return str(UUID(str(value)))

    @staticmethod
    def _to_record(row: AgentUIAction) -> AgentUIActionRecord:
        return AgentUIActionRecord(
            public_id=str(row.public_id),
            team_id=int(row.team_id),
            user_id=int(row.user_id),
            session_id=int(row.session_id),
            message_id=int(row.message_id),
            action_type=_ACTION_TYPE_ADAPTER.validate_python(row.action_type),
            root_context_role=row.root_context_role,
            target=row.target_json,
            consumption_mode=_CONSUMPTION_MODE_ADAPTER.validate_python(row.consumption_mode),
            status=_ACTION_STATUS_ADAPTER.validate_python(row.status),
            expires_at=row.expires_at,
            consumed_at=row.consumed_at,
            submitted_values=row.submitted_values,
            consumed_request_id=row.consumed_request_id,
            result_message_id=int(row.result_message_id) if row.result_message_id is not None else None,
            lock_version=int(row.lock_version),
            created_time=row.created_time,
            last_modified_time=row.last_modified_time,
        )

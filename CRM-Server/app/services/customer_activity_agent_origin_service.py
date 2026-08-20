"""Establish and safely backfill immutable Agent origins for activities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.crud.customer_activity_agent_origin import customer_activity_agent_origin_crud
from app.models.agent import AgentMessage, AgentMessageRole
from app.models.agent_async_operation import AgentAsyncOperation
from app.models.customer_activity import CustomerActivity

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.customer_activity_agent_origin import CustomerActivityAgentOrigin


@dataclass(frozen=True)
class _OriginCandidate:
    team_id: int
    activity_id: int
    owner_id: str
    agent_session_id: int
    source_user_message_id: int | None
    source_assistant_message_id: int
    agent_operation_public_id: str

    @property
    def causal_identity(self) -> tuple[int, int, str, int, int | None, int]:
        """Fields that identify the originating Agent turn, not a job revision."""

        return (
            self.team_id,
            self.activity_id,
            self.owner_id,
            self.agent_session_id,
            self.source_user_message_id,
            self.source_assistant_message_id,
        )


class CustomerActivityAgentOriginService:
    """Own the stable causal link from a customer activity to an Agent turn."""

    def ensure_from_bound_operation(
        self,
        db: Session,
        *,
        operation: AgentAsyncOperation,
    ) -> CustomerActivityAgentOrigin | None:
        """Persist an origin when the current turn binds its assistant message.

        The operation is only an evidence source. Once created, the origin is
        never updated by later post-commit revisions or operation projections.
        """

        candidate = self._candidate_from_operation(db, operation)
        if candidate is None:
            return None
        return customer_activity_agent_origin_crud.ensure(
            db,
            team_id=candidate.team_id,
            activity_id=candidate.activity_id,
            owner_id=candidate.owner_id,
            agent_session_id=candidate.agent_session_id,
            source_user_message_id=candidate.source_user_message_id,
            source_assistant_message_id=candidate.source_assistant_message_id,
            agent_operation_public_id=candidate.agent_operation_public_id,
        )

    def ensure_session_origins(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
    ) -> int:
        """Safely backfill historical origins with unambiguous operation evidence.

        A legacy activity is backfilled only when every candidate operation for
        it in this turn identifies the same Agent source. We deliberately do
        not infer a missing message from surrounding chat history.
        """

        operations = (
            db.query(AgentAsyncOperation)
            .filter(
                AgentAsyncOperation.team_id == team_id,
                AgentAsyncOperation.user_id == user_id,
                AgentAsyncOperation.session_id == session_id,
                AgentAsyncOperation.operation_type == "customer_activity_post_commit",
                AgentAsyncOperation.resource_type == "customer_activity",
                AgentAsyncOperation.resource_id.is_not(None),
                AgentAsyncOperation.source_assistant_message_id.is_not(None),
            )
            .order_by(AgentAsyncOperation.id.asc())
            .all()
        )
        operations_by_activity: dict[int, list[AgentAsyncOperation]] = {}
        for operation in operations:
            if operation.resource_id is None:
                continue
            operations_by_activity.setdefault(int(operation.resource_id), []).append(operation)

        created_count = 0
        for activity_operations in operations_by_activity.values():
            candidates = [self._candidate_from_operation(db, operation) for operation in activity_operations]
            if any(candidate is None for candidate in candidates):
                continue
            resolved_candidates = [candidate for candidate in candidates if candidate is not None]
            if len({candidate.causal_identity for candidate in resolved_candidates}) != 1:
                continue
            first_candidate = resolved_candidates[0]
            existing = customer_activity_agent_origin_crud.get_by_activity(
                db,
                team_id=first_candidate.team_id,
                activity_id=first_candidate.activity_id,
            )
            origin = customer_activity_agent_origin_crud.ensure(
                db,
                team_id=first_candidate.team_id,
                activity_id=first_candidate.activity_id,
                owner_id=first_candidate.owner_id,
                agent_session_id=first_candidate.agent_session_id,
                source_user_message_id=first_candidate.source_user_message_id,
                source_assistant_message_id=first_candidate.source_assistant_message_id,
                agent_operation_public_id=first_candidate.agent_operation_public_id,
            )
            if origin is not None and existing is None:
                created_count += 1
        return created_count

    @staticmethod
    def _candidate_from_operation(
        db: Session,
        operation: AgentAsyncOperation,
    ) -> _OriginCandidate | None:
        if (
            operation.resource_type != "customer_activity"
            or operation.resource_id is None
            or operation.session_id is None
            or operation.source_assistant_message_id is None
        ):
            return None
        team_id = int(operation.team_id)
        user_id = int(operation.user_id)
        activity_id = int(operation.resource_id)
        session_id = int(operation.session_id)
        assistant_message_id = int(operation.source_assistant_message_id)
        source_user_message_id = (
            int(operation.source_user_message_id) if operation.source_user_message_id is not None else None
        )
        if not str(operation.public_id):
            return None

        activity = (
            db.query(CustomerActivity)
            .filter(CustomerActivity.id == activity_id, CustomerActivity.team_id == team_id)
            .one_or_none()
        )
        if activity is None:
            return None
        assistant_message = (
            db.query(AgentMessage)
            .filter(
                AgentMessage.id == assistant_message_id,
                AgentMessage.team_id == team_id,
                AgentMessage.user_id == user_id,
                AgentMessage.session_id == session_id,
                AgentMessage.role == AgentMessageRole.ASSISTANT,
            )
            .one_or_none()
        )
        if assistant_message is None:
            return None
        if source_user_message_id is not None:
            source_user_message = (
                db.query(AgentMessage)
                .filter(
                    AgentMessage.id == source_user_message_id,
                    AgentMessage.team_id == team_id,
                    AgentMessage.user_id == user_id,
                    AgentMessage.session_id == session_id,
                    AgentMessage.role == AgentMessageRole.USER,
                )
                .one_or_none()
            )
            if source_user_message is None:
                return None
            if source_user_message.created_time > assistant_message.created_time or (
                source_user_message.created_time == assistant_message.created_time
                and int(source_user_message.id) > int(assistant_message.id)
            ):
                return None

        return _OriginCandidate(
            team_id=team_id,
            activity_id=activity_id,
            owner_id=str(user_id),
            agent_session_id=session_id,
            source_user_message_id=source_user_message_id,
            source_assistant_message_id=assistant_message_id,
            agent_operation_public_id=str(operation.public_id),
        )


customer_activity_agent_origin_service = CustomerActivityAgentOriginService()

"""Project actionable opportunity suggestions into durable Agent UI messages."""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

from app.crud.customer_opportunity_suggestion_job import (
    customer_opportunity_suggestion_job_crud,
)
from app.models.agent_async_operation import AgentAsyncOperation, AgentAsyncOperationStatus
from app.schemas.agent_persistence import AgentAssistantProjectionCreate, AgentUIActionRegistration
from app.services.agent.turns import AgentTurnRepository
from app.services.agent.types import coerce_json_dict
from app.services.agent.ui.actions import AgentUIActionRepository
from app.services.agent.ui.composer import AgentUIComposer

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_OPERATION_TYPE = "customer_opportunity_suggestion"
_CREATE = "CREATE_OPPORTUNITY"
_MOVE = "MOVE_OPPORTUNITY_STAGE"
_PROJECTION_PREFIX = "customer-opportunity-suggestion-ui:"


class CustomerOpportunitySuggestionAgentUIProjection:
    """Materialize one actionable suggestion exactly once per Agent session.

    The durable suggestion job remains authoritative.  This projector only
    creates a chat message and a one-shot signed action; it never performs CRM
    writes and never makes a background task wait for a user.
    """

    def __init__(
        self,
        *,
        turn_repository: AgentTurnRepository | None = None,
        action_repository: AgentUIActionRepository | None = None,
        ui_composer: AgentUIComposer | None = None,
    ) -> None:
        self.turn_repository = turn_repository or AgentTurnRepository()
        self.action_repository = action_repository or AgentUIActionRepository()
        self.ui_composer = ui_composer or AgentUIComposer()

    def project_operation(
        self,
        db: Session,
        *,
        operation: AgentAsyncOperation,
    ) -> int | None:
        """Create/recover the Agent UI projection for a WAITING_USER operation."""
        if operation.operation_type != _OPERATION_TYPE:
            return None
        if operation.status != AgentAsyncOperationStatus.WAITING_USER:
            return None
        if operation.session_id is None:
            logger.warning(
                "Skipping opportunity suggestion UI projection without session",
                extra={"operation_public_id": str(operation.public_id)},
            )
            return None

        result = coerce_json_dict(operation.result_json)
        decision = str(result.get("decision") or "")
        if decision not in {_CREATE, _MOVE} or result.get("requires_user_action") is not True:
            # NO_ACTION, high-confidence existing opportunities, skipped and
            # exhausted jobs intentionally produce no clickable UI.
            return None
        job_public_id = str(result.get("job_public_id") or operation.request_id)
        job = customer_opportunity_suggestion_job_crud.get_by_public_id(
            db,
            team_id=int(operation.team_id),
            public_id=job_public_id,
        )
        if job is None or str(job.status) != "COMPLETED":
            return None

        projection_key = f"{_PROJECTION_PREFIX}{job_public_id}"
        action_public_id = self._action_public_id(job_public_id)
        composition = self.ui_composer.compose_customer_opportunity_suggestion(
            decision=decision,
            job_public_id=job_public_id,
            action_public_id=action_public_id,
        )
        projected = self.turn_repository.project_assistant(
            db,
            AgentAssistantProjectionCreate(
                team_id=int(operation.team_id),
                user_id=int(operation.user_id),
                session_id=int(operation.session_id),
                projection_key=projection_key,
                content=composition.content,
                ui=composition.body,
                diagnostics={
                    "dispatch_type": "workflow",
                    "reason_code": "CUSTOMER_OPPORTUNITY_SUGGESTION",
                    "suggestion_job_public_id": job_public_id,
                    "suggestion_decision": decision,
                },
            ),
        )
        message_id = int(projected.message.id)
        # A crash can occur after the assistant message commit boundary but
        # before action registration.  Stable action IDs plus get_owned make
        # replay repair safe without creating a second message or action.
        existing_action = self.action_repository.get_owned(
            db,
            public_id=action_public_id,
            team_id=int(operation.team_id),
            user_id=int(operation.user_id),
            session_id=int(operation.session_id),
        )
        if existing_action is None:
            draft = composition.action_drafts[0]
            self.action_repository.register(
                db,
                AgentUIActionRegistration(
                    public_id=draft.public_id,
                    team_id=int(operation.team_id),
                    user_id=int(operation.user_id),
                    session_id=int(operation.session_id),
                    message_id=message_id,
                    action_type=draft.action_type,
                    root_context_role=draft.root_context_role,
                    target=draft.target,
                    consumption_mode=draft.consumption_mode,
                ),
            )
        elif int(existing_action.message_id) != message_id:
            raise ValueError("opportunity suggestion action is bound to another message")
        db.flush()
        return message_id

    def project_request(
        self,
        db: Session,
        *,
        team_id: int,
        operation_public_id: str,
    ) -> int | None:
        operation = (
            db.query(AgentAsyncOperation)
            .filter(
                AgentAsyncOperation.team_id == team_id,
                AgentAsyncOperation.public_id == operation_public_id,
            )
            .populate_existing()
            .with_for_update()
            .one_or_none()
        )
        if operation is None:
            return None
        return self.project_operation(db, operation=operation)

    @staticmethod
    def _action_public_id(job_public_id: str) -> str:
        digest = hashlib.sha256(job_public_id.encode("utf-8")).hexdigest()
        return f"act_{digest[:32]}"


customer_opportunity_suggestion_agent_ui_projection = CustomerOpportunitySuggestionAgentUIProjection()

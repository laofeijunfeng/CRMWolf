"""Project pending follow-up confirmation Cases into native Agent UI turns."""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

from pydantic import ValidationError
from sqlalchemy import and_, exists

from app.crud.sales_commitment import follow_up_task_confirmation_prompt_delivery_crud
from app.models.customer_activity_agent_origin import CustomerActivityAgentOrigin
from app.models.sales_commitment import (
    FollowUpTaskConfirmationCase,
    FollowUpTaskConfirmationDeliveryPurpose,
    FollowUpTaskConfirmationPromptDelivery,
    FollowUpTaskConfirmationStatus,
)
from app.schemas.agent_persistence import (
    AgentAssistantProjectionCreate,
    AgentUIActionRegistration,
)
from app.services.agent.orchestrator import (
    RootOrchestrator,
    RootRuntimeContext,
    RootTurnInput,
    WorkflowDispatchResult,
    WorkflowTriggerTurnInput,
)
from app.services.agent.orchestrator.runtime import get_root_orchestrator
from app.services.agent.turns import AgentTurnRepository
from app.services.agent.ui.actions import AgentUIActionRepository
from app.services.agent.ui.composer import AgentUIComposer
from app.utils.time import business_now

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_MAX_CONFIRMATIONS_PER_MESSAGE = 30


class FollowUpConfirmationAgentUIProjection:
    """Own Case selection, Root dispatch, Agent UI persistence, and delivery audit."""

    def __init__(
        self,
        *,
        root_orchestrator: RootOrchestrator | None = None,
        turn_repository: AgentTurnRepository | None = None,
        action_repository: AgentUIActionRepository | None = None,
        ui_composer: AgentUIComposer | None = None,
    ) -> None:
        self.root_orchestrator = root_orchestrator or get_root_orchestrator()
        self.turn_repository = turn_repository or AgentTurnRepository()
        self.action_repository = action_repository or AgentUIActionRepository()
        self.ui_composer = ui_composer or AgentUIComposer()

    async def project_pending(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        authorization: str,
        permission_codes: frozenset[str],
    ) -> int:
        """Persist all newly pending Cases as one assistant message with independent actions."""

        try:
            cases = self._unprojected_cases(
                db,
                cases=self._lock_pending_cases(
                    db,
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session_id,
                ),
                team_id=team_id,
                session_id=session_id,
            )
            dispatched: list[tuple[FollowUpTaskConfirmationCase, WorkflowDispatchResult]] = []
            for confirmation_case in cases:
                try:
                    trigger = WorkflowTriggerTurnInput(
                        type="workflow_trigger",
                        workflow="follow_up_task_confirmation",
                        resource_id=str(confirmation_case.public_id),
                    )
                except ValidationError:
                    logger.warning(
                        "Skipping invalid follow-up confirmation Case public ID",
                        extra={
                            "team_id": team_id,
                            "session_id": session_id,
                            "case_database_id": int(confirmation_case.id),
                        },
                    )
                    continue

                dispatch = await self.root_orchestrator.dispatch(
                    RootTurnInput(
                        team_id=team_id,
                        user_id=user_id,
                        session_id=session_id,
                        client_request_id=self._projection_key([str(confirmation_case.public_id)]),
                        input=trigger,
                    ),
                    runtime=RootRuntimeContext(
                        db=db,
                        authorization=authorization,
                        permission_codes=permission_codes,
                        root_model_config=None,
                        query_model_config=None,
                        metadata={
                            "source": "web",
                            "trigger": "follow_up_task_confirmation",
                            "case_id": str(confirmation_case.public_id),
                        },
                    ),
                )
                if isinstance(dispatch, WorkflowDispatchResult) and dispatch.workflow_result.status == "WAITING":
                    dispatched.append((confirmation_case, dispatch))

            dispatched = self._retain_current_pending_cases(db, dispatched)
            if not dispatched:
                return 0

            projected_cases = [item[0] for item in dispatched]
            projection_key = self._projection_key([str(item.public_id) for item in projected_cases])
            if (
                self.turn_repository.get_assistant_projection(
                    db,
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session_id,
                    projection_key=projection_key,
                    lock=True,
                )
                is not None
            ):
                return 0

            composition = self.ui_composer.compose_follow_up_task_confirmations(
                [item[1] for item in dispatched],
                case_public_ids=[str(item.public_id) for item in projected_cases],
            )
            completed = self.turn_repository.project_assistant(
                db,
                AgentAssistantProjectionCreate(
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session_id,
                    projection_key=projection_key,
                    content=composition.content,
                    ui=composition.body,
                    diagnostics={
                        "dispatch_type": "workflow",
                        "reason_code": "FOLLOW_UP_TASK_CONFIRMATION_BATCH",
                        "case_public_ids": [str(item.public_id) for item in projected_cases],
                    },
                ),
            )
            if completed.outcome != "CREATED":
                return 0

            for draft in composition.action_drafts:
                self.action_repository.register(
                    db,
                    AgentUIActionRegistration(
                        public_id=draft.public_id,
                        team_id=team_id,
                        user_id=user_id,
                        session_id=session_id,
                        message_id=completed.message.id,
                        action_type=draft.action_type,
                        root_context_role=draft.root_context_role,
                        target=draft.target,
                        consumption_mode=draft.consumption_mode,
                    ),
                )
            for confirmation_case in projected_cases:
                self._record_visible_delivery(
                    db,
                    confirmation_case=confirmation_case,
                    session_id=session_id,
                    turn_id=completed.message.turn_id,
                    message_id=completed.message.id,
                )

            db.commit()
            return len(projected_cases)

        except Exception:
            db.rollback()
            raise

    @staticmethod
    def _retain_current_pending_cases(
        db: Session,
        dispatched: list[tuple[FollowUpTaskConfirmationCase, WorkflowDispatchResult]],
    ) -> list[tuple[FollowUpTaskConfirmationCase, WorkflowDispatchResult]]:
        """Recheck Case state before persisting any message or Action.

        Root dispatch can cross a transaction boundary (for example when it
        resolves a Case through the internal CRM API). A Case may therefore be
        cancelled or expired after the initial selection. Re-locking the
        authoritative rows immediately before projection makes message and
        Action registration fail closed; the row lock also prevents a
        concurrent cancellation from committing between this check and the
        surrounding projection transaction.
        """

        now = business_now()
        retained: list[tuple[FollowUpTaskConfirmationCase, WorkflowDispatchResult]] = []
        for confirmation_case, dispatch in dispatched:
            current_case = (
                db.query(FollowUpTaskConfirmationCase)
                .filter(
                    FollowUpTaskConfirmationCase.id == confirmation_case.id,
                    FollowUpTaskConfirmationCase.team_id == confirmation_case.team_id,
                    FollowUpTaskConfirmationCase.status == FollowUpTaskConfirmationStatus.PENDING,
                    (
                        FollowUpTaskConfirmationCase.expires_at.is_(None)
                        | (FollowUpTaskConfirmationCase.expires_at > now)
                    ),
                )
                .populate_existing()
                .with_for_update()
                .one_or_none()
            )
            if current_case is not None:
                retained.append((current_case, dispatch))
        return retained

    @staticmethod
    def _unprojected_cases(
        db: Session,
        *,
        cases: list[FollowUpTaskConfirmationCase],
        team_id: int,
        session_id: int,
    ) -> list[FollowUpTaskConfirmationCase]:
        if not cases:
            return []
        prompt_keys = {
            f"agent-turn-prompt:{confirmation_case.public_id}:{session_id}"
            for confirmation_case in cases
        }
        delivered_keys = {
            str(prompt_key)
            for (prompt_key,) in (
                db.query(FollowUpTaskConfirmationPromptDelivery.prompt_key)
                .filter(
                    FollowUpTaskConfirmationPromptDelivery.team_id == team_id,
                    FollowUpTaskConfirmationPromptDelivery.agent_session_id == session_id,
                    FollowUpTaskConfirmationPromptDelivery.purpose
                    == FollowUpTaskConfirmationDeliveryPurpose.AGENT_TURN_PROMPT,
                    FollowUpTaskConfirmationPromptDelivery.prompt_key.in_(prompt_keys),
                )
                .all()
            )
        }
        return [
            confirmation_case
            for confirmation_case in cases
            if f"agent-turn-prompt:{confirmation_case.public_id}:{session_id}" not in delivered_keys
        ]

    @staticmethod
    def _lock_pending_cases(
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
    ) -> list[FollowUpTaskConfirmationCase]:
        now = business_now()
        return (
            db.query(FollowUpTaskConfirmationCase)
            .join(
                CustomerActivityAgentOrigin,
                CustomerActivityAgentOrigin.activity_id == FollowUpTaskConfirmationCase.source_activity_id,
            )
            .filter(
                CustomerActivityAgentOrigin.team_id == team_id,
                CustomerActivityAgentOrigin.owner_id == str(user_id),
                CustomerActivityAgentOrigin.agent_session_id == session_id,
                FollowUpTaskConfirmationCase.team_id == team_id,
                FollowUpTaskConfirmationCase.owner_id == str(user_id),
                FollowUpTaskConfirmationCase.status == FollowUpTaskConfirmationStatus.PENDING,
                (FollowUpTaskConfirmationCase.expires_at.is_(None) | (FollowUpTaskConfirmationCase.expires_at > now)),
                ~exists().where(
                    and_(
                        FollowUpTaskConfirmationPromptDelivery.case_id == FollowUpTaskConfirmationCase.id,
                        FollowUpTaskConfirmationPromptDelivery.team_id == team_id,
                        FollowUpTaskConfirmationPromptDelivery.agent_session_id == session_id,
                        FollowUpTaskConfirmationPromptDelivery.purpose
                        == FollowUpTaskConfirmationDeliveryPurpose.AGENT_TURN_PROMPT,
                    )
                ),
            )
            .order_by(
                FollowUpTaskConfirmationCase.created_time.asc(),
                FollowUpTaskConfirmationCase.id.asc(),
            )
            .limit(_MAX_CONFIRMATIONS_PER_MESSAGE)
            .populate_existing()
            .with_for_update()
            .all()
        )

    @staticmethod
    def _projection_key(case_public_ids: list[str]) -> str:
        digest = hashlib.sha256("\n".join(sorted(case_public_ids)).encode("utf-8")).hexdigest()
        return f"follow-up-confirmation-batch:{digest}"

    @staticmethod
    def _record_visible_delivery(
        db: Session,
        *,
        confirmation_case: FollowUpTaskConfirmationCase,
        session_id: int,
        turn_id: str,
        message_id: int,
    ) -> None:
        prompt_key = f"agent-turn-prompt:{confirmation_case.public_id}:{session_id}"
        delivery = follow_up_task_confirmation_prompt_delivery_crud.ensure_queued(
            db,
            team_id=int(confirmation_case.team_id),
            case_id=int(confirmation_case.id),
            owner_id=str(confirmation_case.owner_id),
            channel="web",
            purpose=FollowUpTaskConfirmationDeliveryPurpose.AGENT_TURN_PROMPT,
            provider="web-agent-ui",
            recipient_id=str(confirmation_case.owner_id),
            agent_session_id=session_id,
            interaction_id=f"agent-turn-prompt:{confirmation_case.public_id}",
            prompt_key=prompt_key,
            origin_turn_id=turn_id,
            origin_message_id=str(message_id),
            source_activity_id=(
                int(confirmation_case.source_activity_id) if confirmation_case.source_activity_id is not None else None
            ),
            expected_activity_revision=(
                int(confirmation_case.source_activity_revision)
                if confirmation_case.source_activity_revision is not None
                else None
            ),
            payload_json={
                "case_public_id": str(confirmation_case.public_id),
                "assistant_message_id": message_id,
            },
            reason_code="AGENT_UI_WORKFLOW_PROMPT_PERSISTED",
            commit=False,
        )
        follow_up_task_confirmation_prompt_delivery_crud.acknowledge_sent(
            db,
            delivery,
            provider_message_id=f"agent_message:{message_id}",
            reason_code="AGENT_UI_WORKFLOW_PROMPT_VISIBLE",
            commit=False,
        )


follow_up_confirmation_agent_ui_projection = FollowUpConfirmationAgentUIProjection()

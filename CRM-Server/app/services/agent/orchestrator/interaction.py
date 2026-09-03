"""Authoritative Agent UI interaction claims for the Root Orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionLocal
from app.services.agent.orchestrator.contracts import (
    InteractionResolution,
    InteractionTurnInput,
    ResolvedAgentAction,
    WorkflowContinuation,
    WorkflowTriggerTurnInput,
)
from app.services.agent.orchestrator.errors import InteractionResolutionUnavailableError
from app.services.agent.ui.actions import (
    ActionAlreadyConsumedError,
    ActionExpiredError,
    ActionNotFoundError,
    ActionStateConflictError,
    ActionUnavailableError,
    AgentUIActionRepository,
)
from app.services.agent.ui.input_resolver import (
    AgentUIInputResolutionError,
    InteractionInputResolver,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from app.schemas.agent_persistence import AgentUIActionConsumption
    from app.services.agent.orchestrator.contracts import (
        RootContextSnapshot,
        RootRuntimeContext,
        RootTurnInput,
    )

_REJECTION_CODES = {
    ActionNotFoundError: "ACTION_NOT_FOUND",
    ActionExpiredError: "ACTION_EXPIRED",
    ActionUnavailableError: "ACTION_UNAVAILABLE",
    ActionAlreadyConsumedError: "ACTION_ALREADY_CONSUMED",
    ActionStateConflictError: "ACTION_STATE_CONFLICT",
}


class DatabaseInteractionResolver:
    """Claim one owned action and return only its server-authorized resume payload."""

    def __init__(
        self,
        *,
        action_repository: AgentUIActionRepository | None = None,
        input_resolver: InteractionInputResolver | None = None,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self._action_repository = action_repository or AgentUIActionRepository()
        self._input_resolver = input_resolver or InteractionInputResolver()
        self._session_factory = session_factory or SessionLocal

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> InteractionResolution:
        del context, runtime
        if not isinstance(turn.input, InteractionTurnInput):
            raise InteractionResolutionUnavailableError("Interaction resolver received a non-interaction turn")

        # The action ledger is an independent durability boundary. Claim and
        # validate it in a short transaction, then commit before LangGraph resumes
        # or any CRM side effect can run. This makes a user's first submission
        # immediately and permanently read-only to every channel.
        try:
            db = self._session_factory()
        except Exception as exc:
            raise InteractionResolutionUnavailableError(
                "Action claim transaction could not be opened"
            ) from exc
        try:
            try:
                consumption = self._action_repository.begin_consumption(
                    db,
                    public_id=turn.input.action_id,
                    team_id=turn.team_id,
                    user_id=turn.user_id,
                    session_id=turn.session_id,
                    client_request_id=turn.client_request_id,
                )
            except tuple(_REJECTION_CODES) as exc:
                db.commit()
                return InteractionResolution(
                    status="REJECTED",
                    reason_code=_REJECTION_CODES[type(exc)],
                )
            except ValueError:
                db.rollback()
                return InteractionResolution(
                    status="REJECTED",
                    reason_code="ACTION_REQUEST_ID_INVALID",
                )

            continuation, workflow_trigger, rejection = self._resolve_binding(consumption)
            if rejection is not None or (continuation is None and workflow_trigger is None):
                self._release_if_acquired(db, turn=turn, consumption=consumption)
                db.commit()
                return InteractionResolution(
                    status="REJECTED",
                    reason_code=rejection or "ACTION_WORKFLOW_BINDING_INVALID",
                )

            try:
                resolved_input = self._input_resolver.resolve_interaction_values(
                    consumption.action.target,
                    turn.input.values,
                )
            except AgentUIInputResolutionError:
                self._release_if_acquired(db, turn=turn, consumption=consumption)
                db.commit()
                return InteractionResolution(
                    status="REJECTED",
                    reason_code="ACTION_VALUES_INVALID",
                )

            if workflow_trigger is not None:
                # ``content`` is deliberately user-facing (for example,
                # ``确认``/``取消``). Use the resolver's typed protocol kind
                # instead of comparing display text so a signed confirmation
                # can safely authorize a server-side trigger.
                if resolved_input.kind not in {"confirm", "reject"}:
                    self._release_if_acquired(db, turn=turn, consumption=consumption)
                    db.commit()
                    return InteractionResolution(
                        status="REJECTED",
                        reason_code="ACTION_VALUES_INVALID",
                    )
                workflow_trigger = workflow_trigger.model_copy(
                    update={
                        "action": (
                            workflow_trigger.action
                            if resolved_input.kind == "confirm"
                            else "CANCEL"
                        )
                    }
                )
                reason_code = "SERVER_WORKFLOW_TRIGGER"
            else:
                reason_code = "STRUCTURED_WORKFLOW_CONTINUATION"

            resolution = InteractionResolution(
                status="RESOLVED",
                reason_code=reason_code,
                resolved_action=ResolvedAgentAction(
                    action_id=consumption.action.public_id,
                    action_type="submit_interaction",
                    continuation=continuation,
                    workflow_trigger=workflow_trigger,
                    claim_outcome=cast("str", consumption.outcome),
                    resume_payload=(
                        {}
                        if workflow_trigger is not None
                        else resolved_input.model_dump(mode="json")
                    ),
                    replay_message_id=consumption.action.result_message_id,
                ),
            )
            db.commit()
            return resolution
        except InteractionResolutionUnavailableError:
            db.rollback()
            raise
        except (SQLAlchemyError, ValidationError) as exc:
            db.rollback()
            raise InteractionResolutionUnavailableError("Action claim could not be persisted safely") from exc
        finally:
            db.close()

    @staticmethod
    def _resolve_binding(
        consumption: AgentUIActionConsumption,
    ) -> tuple[WorkflowContinuation | None, WorkflowTriggerTurnInput | None, str | None]:
        action = consumption.action
        if action.action_type != "submit_interaction":
            return None, None, "ACTION_TYPE_INVALID"

        raw_trigger = action.target.get("workflow_trigger")
        if raw_trigger is not None:
            try:
                trigger = WorkflowTriggerTurnInput.model_validate(raw_trigger)
            except ValidationError:
                return None, None, "ACTION_WORKFLOW_BINDING_INVALID"
            if trigger.workflow != "customer_opportunity_suggestion":
                return None, None, "ACTION_WORKFLOW_BINDING_INVALID"
            if trigger.action not in {"CREATE_OPPORTUNITY", "MOVE_OPPORTUNITY_STAGE"}:
                return None, None, "ACTION_WORKFLOW_BINDING_INVALID"
            return None, trigger, None

        try:
            continuation = WorkflowContinuation.model_validate(
                action.target.get("workflow_continuation")
            )
        except ValidationError:
            return None, None, "ACTION_WORKFLOW_BINDING_INVALID"
        return continuation, None, None

    def _release_if_acquired(
        self,
        db: Session,
        *,
        turn: RootTurnInput,
        consumption: AgentUIActionConsumption,
    ) -> None:
        if consumption.outcome != "ACQUIRED":
            return
        try:
            self._action_repository.release_consumption(
                db,
                public_id=consumption.action.public_id,
                team_id=turn.team_id,
                user_id=turn.user_id,
                session_id=turn.session_id,
                client_request_id=turn.client_request_id,
            )
        except (SQLAlchemyError, ValueError, ActionStateConflictError) as exc:
            raise InteractionResolutionUnavailableError("Rejected action claim could not be released safely") from exc

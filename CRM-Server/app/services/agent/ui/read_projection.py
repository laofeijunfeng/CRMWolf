"""Read-time projection of mutable Agent UI action state onto immutable messages."""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.agent.ui.schemas import AgentUIEnvelope, InteractionBlock
from app.utils.time import business_now

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from app.schemas.agent_persistence import AgentUIActionRecord

_TERMINAL_INTERACTION_STATES = {
    "CONSUMED": "SUBMITTED",
    "EXPIRED": "EXPIRED",
    "REVOKED": "CANCELLED",
    "CONSUMING": "READ_ONLY",
}
_FOLLOW_UP_CONFIRMATION_CASE_STATES = {
    "PENDING": None,
    "RESOLVED": "SUBMITTED",
    "EXPIRED": "EXPIRED",
    "CANCELLED": "CANCELLED",
}
_FOLLOW_UP_CONFIRMATION_CASE_TARGET_KEY = "follow_up_confirmation_case_public_id"


def _case_state_for_action(
    action: AgentUIActionRecord,
    case_statuses: Mapping[str, str],
) -> str | None:
    case_public_id = action.target.get(_FOLLOW_UP_CONFIRMATION_CASE_TARGET_KEY)
    if not isinstance(case_public_id, str) or not case_public_id:
        return None
    # A signed follow-up action must have a current Case. Missing rows fail closed
    # so a deleted or inaccessible Case can never remain clickable in history.
    return _FOLLOW_UP_CONFIRMATION_CASE_STATES.get(case_statuses.get(case_public_id), "READ_ONLY")


def project_interaction_action_states(
    envelopes: list[AgentUIEnvelope],
    actions: list[AgentUIActionRecord],
    *,
    now: datetime | None = None,
    follow_up_confirmation_case_statuses: Mapping[str, str] | None = None,
    follow_up_confirmation_case_statuses_by_action: Mapping[str, str] | None = None,
) -> list[AgentUIEnvelope]:
    """Overlay action-ledger truth without mutating persisted message snapshots."""
    effective_now = now or business_now()
    by_id = {action.public_id: action for action in actions}
    projected: list[AgentUIEnvelope] = []
    for envelope in envelopes:
        blocks = []
        for block in envelope.blocks:
            if not isinstance(block, InteractionBlock) or block.submit_action_id is None:
                blocks.append(block)
                continue
            action = by_id.get(block.submit_action_id)
            if action is None:
                state = "READ_ONLY"
            else:
                state = _TERMINAL_INTERACTION_STATES.get(action.status)
                if state is None and action.status == "ACTIVE" and action.expires_at <= effective_now:
                    state = "EXPIRED"
                if state is None and follow_up_confirmation_case_statuses_by_action is not None:
                    case_status = follow_up_confirmation_case_statuses_by_action.get(action.public_id)
                    if case_status is not None:
                        state = _FOLLOW_UP_CONFIRMATION_CASE_STATES.get(case_status, "READ_ONLY")
                if state is None and follow_up_confirmation_case_statuses is not None:
                    state = _case_state_for_action(action, follow_up_confirmation_case_statuses)
            blocks.append(
                block.model_copy(
                    update={
                        "state": state,
                        "submit_action_id": None,
                        "submitted_values": action.submitted_values if state == "SUBMITTED" else None,
                    }
                )
                if state is not None
                else block
            )
        projected.append(envelope.model_copy(update={"blocks": blocks}))
    return projected

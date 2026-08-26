"""Read-time projection of mutable Agent UI action state onto immutable messages."""
from __future__ import annotations

from datetime import datetime

from app.schemas.agent_persistence import AgentUIActionRecord
from app.services.agent.ui.schemas import AgentUIEnvelope, InteractionBlock
from app.utils.time import business_now

_TERMINAL_INTERACTION_STATES = {
    "CONSUMED": "SUBMITTED",
    "EXPIRED": "EXPIRED",
    "REVOKED": "CANCELLED",
    "CONSUMING": "READ_ONLY",
}


def project_interaction_action_states(
    envelopes: list[AgentUIEnvelope],
    actions: list[AgentUIActionRecord],
    *,
    now: datetime | None = None,
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
            blocks.append(
                block.model_copy(update={"state": state, "submit_action_id": None})
                if state is not None
                else block
            )
        projected.append(envelope.model_copy(update={"blocks": blocks}))
    return projected

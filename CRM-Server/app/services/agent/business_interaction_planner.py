"""Deterministic final-turn interaction arbitration.

The planner is intentionally pure: persistence, channel delivery, and graph
checkpointing stay behind their own seams. It only decides which normalized
candidate, if any, is allowed to block this Agent turn.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.services.agent.interrupts import AgentInterruptPayload
    from app.services.agent.state import AgentTurnScope, InteractionCandidate
    from app.services.agent.types import JSONDict

InteractionActionKind = Literal["keep_current_interrupt", "follow_up_confirmation", "none"]
_NON_INTERRUPTIBLE_OPERATION_STATUSES = {"failed", "blocked", "cancelled"}


@dataclass(frozen=True)
class InteractionPlan:
    action: InteractionActionKind
    candidate: JSONDict
    reason: str


class BusinessInteractionPlanner:
    """Select exactly one current-turn response target from normalized candidates."""

    def plan(
        self,
        *,
        turn_scope: AgentTurnScope,
        current_interrupt: AgentInterruptPayload | None,
        candidates: list[InteractionCandidate],
    ) -> InteractionPlan:
        if current_interrupt:
            return InteractionPlan(
                action="keep_current_interrupt",
                candidate={},
                reason="higher_priority_interaction_already_selected",
            )

        operation_status = str(turn_scope.get("operation_status") or "active").lower()
        if operation_status in _NON_INTERRUPTIBLE_OPERATION_STATUSES:
            return InteractionPlan(
                action="none",
                candidate={},
                reason="current_operation_not_interruptible",
            )

        eligible = [candidate for candidate in candidates if self._may_block(turn_scope, candidate)]
        if not eligible:
            return InteractionPlan(
                action="none",
                candidate={},
                reason="no_current_turn_blocking_interaction",
            )

        selected = max(eligible, key=lambda item: int(item.get("priority") or 0))
        if selected.get("kind") == "follow_up_confirmation":
            return InteractionPlan(
                action="follow_up_confirmation",
                candidate=dict(selected),
                reason="current_turn_confirmation_requires_user_input",
            )
        return InteractionPlan(action="none", candidate={}, reason="unsupported_blocking_interaction")

    @staticmethod
    def _may_block(turn_scope: AgentTurnScope, candidate: InteractionCandidate) -> bool:
        if candidate.get("origin") != "current_turn":
            return False
        if candidate.get("presentation") != "blocking_interrupt":
            return False

        scope_customer_id = turn_scope.get("customer_id")
        candidate_customer_id = candidate.get("customer_id")
        if scope_customer_id is not None and candidate_customer_id is not None:
            if scope_customer_id != candidate_customer_id:
                return False

        scope_public_id = turn_scope.get("customer_public_id")
        candidate_public_id = candidate.get("customer_public_id")
        if scope_public_id and candidate_public_id and scope_public_id != candidate_public_id:
            return False
        return True


business_interaction_planner = BusinessInteractionPlanner()

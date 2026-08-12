"""Deterministic final-turn interaction arbitration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.services.agent.interrupts import AgentInterruptPayload
    from app.services.agent.types import JSONDict

InteractionActionKind = Literal["keep_current_interrupt", "follow_up_confirmation", "none"]


@dataclass(frozen=True)
class InteractionPlan:
    action: InteractionActionKind
    candidate: JSONDict
    reason: str


class BusinessInteractionPlanner:
    """Select exactly one user-response target using the documented priority order."""

    def plan(
        self,
        *,
        semantic: JSONDict,
        business_context: JSONDict,
        suggestions: JSONDict,
        current_interrupt: AgentInterruptPayload | None,
        pending_task_projection: JSONDict,
        tool_capability: JSONDict,
        follow_up_confirmation_candidate: JSONDict,
    ) -> InteractionPlan:
        del semantic, business_context, suggestions, pending_task_projection, tool_capability
        if current_interrupt:
            return InteractionPlan(
                action="keep_current_interrupt",
                candidate={},
                reason="higher_priority_interaction_already_selected",
            )
        if follow_up_confirmation_candidate:
            return InteractionPlan(
                action="follow_up_confirmation",
                candidate=follow_up_confirmation_candidate,
                reason="durable_owner_confirmation_pending",
            )
        return InteractionPlan(action="none", candidate={}, reason="no_user_response_target")


business_interaction_planner = BusinessInteractionPlanner()

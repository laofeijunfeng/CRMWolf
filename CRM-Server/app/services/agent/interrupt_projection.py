"""Ownership contract for checkpoint-visible Agent interrupts.

Root and child graphs share LangGraph's native ``interrupt`` mechanism, but
only child-owned interrupts require a second checkpoint lookup.  This module
keeps that ownership decision explicit and tenant-authenticated so the root
runtime never guesses from graph topology or business reason strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from app.services.agent.pending_continuation import pending_task_continuation_from_json

if TYPE_CHECKING:
    from app.services.agent.interrupts import AgentInterruptPayload
    from app.services.agent.pending_continuation import PendingTaskContinuationRef

InterruptOwner = Literal["root", "pending_task", "invalid_pending_task"]


@dataclass(frozen=True)
class InterruptProjectionTarget:
    """Authenticated owner and continuation for one native interrupt."""

    owner: InterruptOwner
    interrupt: AgentInterruptPayload
    continuation: PendingTaskContinuationRef | None = None
    failure_reason: str | None = None


def classify_interrupt_projection(
    interrupt: AgentInterruptPayload,
    *,
    team_id: int | None = None,
    user_id: int | None = None,
    session_id: int | None = None,
    thread_id: str | None = None,
) -> InterruptProjectionTarget:
    """Classify an interrupt without inferring child state from business data.

    Absence of ``checkpoint_ref`` means the interrupt belongs to the root
    graph.  Presence is an explicit claim of child ownership and therefore
    must authenticate as an exact PendingTask continuation; malformed or
    cross-tenant claims fail closed rather than falling back to root handling.
    """

    if interrupt.get("checkpoint_ref_error"):
        return InterruptProjectionTarget(
            owner="invalid_pending_task",
            interrupt=interrupt,
            failure_reason="invalid_continuation",
        )

    raw_continuation = interrupt.get("checkpoint_ref")
    if raw_continuation is None:
        return InterruptProjectionTarget(owner="root", interrupt=interrupt)
    continuation = pending_task_continuation_from_json(
        raw_continuation,
        expected_team_id=team_id,
        expected_user_id=user_id,
        expected_session_id=session_id,
        expected_thread_id=thread_id,
    )
    if continuation is None:
        return InterruptProjectionTarget(
            owner="invalid_pending_task",
            interrupt=interrupt,
            failure_reason="invalid_continuation",
        )
    return InterruptProjectionTarget(
        owner="pending_task",
        interrupt=interrupt,
        continuation=continuation,
    )

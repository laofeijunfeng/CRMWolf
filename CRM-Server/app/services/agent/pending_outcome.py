"""Authoritative business outcome contract for the pending-task graph.

Streaming updates are progress signals.  This module is the single seam that
turns a durable LangGraph snapshot (plus optional live trace events) into the
business outcome consumed by the root runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from langgraph.types import Interrupt

from app.services.agent.state import PendingTaskGraphResult, PendingTaskGraphState, visible_graph_events
from app.services.agent.types import JSONDict, coerce_json_dict, coerce_json_value

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from app.services.agent.interrupts import AgentInterruptPayload
    from app.services.agent.pending_continuation import PendingTaskContinuationRef


@dataclass(frozen=True)
class PendingTaskAbortVerificationRequest:
    """Authenticated proof request for one root-owned terminal abort."""

    continuation: PendingTaskContinuationRef
    expected_interrupt: AgentInterruptPayload
    team_id: int
    user_id: int
    session_id: int


@dataclass(frozen=True)
class PendingTaskOutcomeRecovery:
    """Result of resolving one suspended child continuation."""

    outcome: PendingTaskGraphResult | None = None
    failure_reason: str | None = None

    @property
    def recovered(self) -> bool:
        return self.outcome is not None


class PendingTaskOutcomeAssembler:
    """Assemble one authoritative child outcome for every execution path."""

    def assemble(
        self,
        *,
        observed_state: Mapping[str, object] | None = None,
        checkpoint_values: Mapping[str, object] | None = None,
        trace_events: Sequence[JSONDict] = (),
        interrupts: object | None = None,
    ) -> PendingTaskGraphResult:
        state = _merge_authoritative_state(observed_state or {}, checkpoint_values or {})
        result: PendingTaskGraphResult = dict(state)
        authoritative_events = visible_graph_events(state.get("events"))
        result["events"] = _reconcile_trace_events(
            trace_events=list(trace_events),
            authoritative_events=authoritative_events,
        )
        native_interrupts = interrupt_sequence(interrupts or state.get("__interrupt__"))
        if native_interrupts:
            result["__interrupt__"] = native_interrupts
            current_interrupt = coerce_json_dict(native_interrupts[0].value)
            if current_interrupt:
                result["current_interrupt"] = current_interrupt  # type: ignore[typeddict-item]
        return result


def interrupt_sequence(interrupts: object) -> list[Interrupt]:
    if not isinstance(interrupts, tuple | list):
        return []
    return [item for item in interrupts if isinstance(item, Interrupt)]


def _merge_authoritative_state(
    observed_state: Mapping[str, object],
    checkpoint_values: Mapping[str, object],
) -> PendingTaskGraphState:
    merged: PendingTaskGraphState = {
        str(key): coerce_json_value(value) for key, value in observed_state.items() if isinstance(key, str)
    }
    for key, value in checkpoint_values.items():
        if not isinstance(key, str):
            continue
        if key == "events":
            merged["events"] = visible_graph_events(value)
            continue
        merged[key] = coerce_json_value(value)
    return merged


def _reconcile_trace_events(
    *,
    trace_events: list[JSONDict],
    authoritative_events: list[JSONDict],
) -> list[JSONDict]:
    """Keep live step timing while restoring domain events from the snapshot."""

    if not authoritative_events:
        return trace_events
    remaining = list(authoritative_events)
    reconciled: list[JSONDict] = []
    for event in trace_events:
        reconciled.append(event)
        if event.get("event") == "agent_step":
            continue
        try:
            remaining.remove(event)
        except ValueError:
            continue
    if not remaining:
        return reconciled

    last_domain_index = max(
        (index for index, event in enumerate(reconciled) if event.get("event") != "agent_step"),
        default=-1,
    )
    insertion_index = last_domain_index + 1
    return [*reconciled[:insertion_index], *remaining, *reconciled[insertion_index:]]


pending_task_outcome_assembler = PendingTaskOutcomeAssembler()

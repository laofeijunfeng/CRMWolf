"""Reusable LangGraph HITL helpers for CRM Agent runtime nodes."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.services.agent import interactions
from app.services.agent.interrupts import (
    AgentInterruptPayload,
    RUNTIME_WAITING_EVENT_TYPES,
    interrupt_from_waiting_event,
)
from app.services.agent.types import JSONDict, coerce_json_dict


def interrupt_from_runtime_events(
    events: Sequence[Mapping[str, object]],
    *,
    db: object | None,
    team_id: int,
) -> AgentInterruptPayload | None:
    """Build the current graph interrupt from the final waiting event in a node update."""

    for raw_event in reversed(events):
        event_name = raw_event.get("event")
        if not isinstance(event_name, str) or event_name not in RUNTIME_WAITING_EVENT_TYPES:
            continue
        event = coerce_json_dict(raw_event)
        event_with_interaction = coerce_json_dict(
            interactions._with_interaction(event, db=db, team_id=team_id)
        )
        interaction = event_with_interaction.get("interaction")
        return interrupt_from_waiting_event(
            event_with_interaction,
            interaction=coerce_json_dict(interaction),
        )
    return None

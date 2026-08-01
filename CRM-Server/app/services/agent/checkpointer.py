"""LangGraph checkpointing primitives for the CRM Agent runtime."""
from __future__ import annotations

from app.services.customer_activity_ai.checkpointer import SQLAlchemyCheckpointSaver
from app.services.agent.types import JSONDict, coerce_json_dict
from sqlalchemy.exc import SQLAlchemyError


agent_checkpoint_saver = SQLAlchemyCheckpointSaver()


def checkpoint_unavailable_fallback_event(*, runtime: str, graph: str) -> JSONDict:
    return {
        "event": "agent_checkpoint_unavailable_fallback_started",
        "runtime": runtime,
        "graph": graph,
        "checkpoint_unavailable": True,
        "fallback_reason": "checkpoint_storage_error",
        "content": f"{runtime} checkpoint storage is unavailable; using explicit no-checkpointer fallback.",
    }


def with_checkpoint_unavailable_fallback_event(result: object, *, runtime: str, graph: str) -> JSONDict:
    projected = coerce_json_dict(result)
    events = projected.get("events")
    event_list = events if isinstance(events, list) else []
    projected["events"] = [
        checkpoint_unavailable_fallback_event(runtime=runtime, graph=graph),
        *[coerce_json_dict(event) for event in event_list if isinstance(event, dict)],
    ]
    return projected


def is_checkpoint_storage_error(error: SQLAlchemyError) -> bool:
    traceback = error.__traceback__
    while traceback is not None:
        module = traceback.tb_frame.f_globals.get("__name__")
        if module == "app.services.customer_activity_ai.checkpointer":
            return True
        traceback = traceback.tb_next
    return False

"""User-facing trace projection for customer intelligence runtime."""
from __future__ import annotations

from typing import TypedDict

from app.services.agent.types import JSONDict, coerce_json_dict


class CustomerIntelligenceTraceStep(TypedDict):
    title: str
    content: str


def customer_intelligence_step_event(step: CustomerIntelligenceTraceStep) -> JSONDict:
    return {
        "event": "agent_step",
        "step": "customer_intelligence",
        "status": "completed",
        "content": f"{step['title']}：{step['content']}",
    }


def visible_trace_events(state: object) -> list[JSONDict]:
    result = coerce_json_dict(state)
    visible_trace = result.get("visible_trace")
    events: list[JSONDict] = []
    if not isinstance(visible_trace, list):
        return events
    for item in visible_trace:
        step = _trace_step_from_item(item)
        if step is not None:
            events.append(customer_intelligence_step_event(step))
    return events


def _trace_step_from_item(item: object) -> CustomerIntelligenceTraceStep | None:
    step = coerce_json_dict(item)
    title = step.get("title")
    content = step.get("content")
    if not isinstance(title, str) or not isinstance(content, str):
        return None
    if not title.strip() or not content.strip():
        return None
    return {"title": title.strip(), "content": content.strip()}

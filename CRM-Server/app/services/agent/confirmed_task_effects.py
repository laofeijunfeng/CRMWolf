"""Side effects emitted by the confirmed-task LangGraph subgraph."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.services.agent import interactions
from app.services.agent.types import JSONDict, coerce_json_dict, coerce_json_value

if TYPE_CHECKING:
    from app.services.agent.state import ConfirmedTaskExecutionResult


@dataclass
class ConfirmedTaskSideEffectContext:
    """Run-scoped CRM dependencies for confirmed-task persistence effects."""

    db: object
    session: object
    task: object
    team_id: int
    user_id: int
    execution: ConfirmedTaskExecutionResult
    channel: str = "web"
    provider: str | None = None


@dataclass
class ConfirmedTaskSideEffectResult:
    """Application-facing outputs from confirmed-task effects."""

    task_event: JSONDict = field(default_factory=dict)
    output_events: list[JSONDict] = field(default_factory=list)
    assistant_content: str | None = None


class ConfirmedTaskSideEffectHandler:
    """Applies CRM persistence effects after confirmed task execution."""

    def apply(self, context: ConfirmedTaskSideEffectContext) -> ConfirmedTaskSideEffectResult:
        execution = context.execution
        task_event = coerce_json_dict(execution.task_event)

        if _should_offer_next_task(context.task, execution, task_event):
            next_task = execution.next_task
            if next_task:
                task_event["next_task_id"] = coerce_json_value(_task_id(next_task))
                task_event["interaction"] = interactions._pending_task_interaction(
                    next_task,
                    execution.assistant_content,
                    db=context.db,
                    team_id=context.team_id,
                )

        output_events: list[JSONDict] = []
        if execution.tool_event:
            output_events.append(coerce_json_dict(execution.tool_event))
        output_events.append(task_event)
        assistant_content = execution.assistant_content
        output_events.append({"event": "final", "content": assistant_content})
        return ConfirmedTaskSideEffectResult(
            task_event=task_event,
            output_events=output_events,
            assistant_content=assistant_content,
        )


def _task_completed(task_event: JSONDict) -> bool:
    return task_event.get("event") == "task_completed"


def _should_offer_next_task(
    task: object,
    execution: ConfirmedTaskExecutionResult,
    task_event: JSONDict,
) -> bool:
    if not _task_completed(task_event) or not execution.next_task:
        return False
    if _task_id(execution.next_task) == _task_id(task):
        return False
    state_json = getattr(task, "state_json", None)
    if not isinstance(state_json, dict):
        return False
    task_action = state_json.get("action")
    return interactions._should_offer_next_pending_task(task_action)


def _task_id(task: object) -> int | None:
    raw_id = getattr(task, "id", None)
    if isinstance(raw_id, int):
        return raw_id
    if isinstance(raw_id, str):
        try:
            return int(raw_id)
        except ValueError:
            return None
    return None



confirmed_task_side_effect_handler = ConfirmedTaskSideEffectHandler()

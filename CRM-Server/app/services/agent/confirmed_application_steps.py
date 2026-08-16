"""Application executor for confirmed Agent write intents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.agent import task_execution
from app.services.agent.confirmed_task_effects import (
    ConfirmedTaskSideEffectContext,
    ConfirmedTaskSideEffectHandler,
    confirmed_task_side_effect_handler,
)
from app.services.agent.state import ConfirmedTaskExecutionResult
from app.services.agent.types import JSONDict, coerce_json_dict

if TYPE_CHECKING:
    from app.services.agent.confirmed_application_step_projection import (
        ConfirmedApplicationStepExecutionRequest,
    )


class DefaultConfirmedApplicationStepExecutor:
    """Executes CRM work and returns the complete durable graph hydration result."""

    def __init__(self, *, side_effect_handler: ConfirmedTaskSideEffectHandler | None = None) -> None:
        self.side_effect_handler = side_effect_handler or confirmed_task_side_effect_handler

    async def execute(self, request: ConfirmedApplicationStepExecutionRequest) -> JSONDict:
        execution = await task_execution._execute_waiting_task(
            request.db,
            request.task,
            session=request.session,
            team_id=request.team_id,
            user_id=request.user_id,
            authorization=request.authorization,
            event_sink=request.event_sink,
        )
        result = execution.tool_result
        assistant_content = execution.assistant_content
        task_event: JSONDict = {
            "event": "task_completed" if result and result.success else "task_failed",
            "task_id": getattr(request.task, "id", None),
            "content": assistant_content,
        }
        confirmed_execution = ConfirmedTaskExecutionResult(
            tool_event=coerce_json_dict(result.to_event()) if result else None,
            task_event=coerce_json_dict(task_event),
            assistant_content=assistant_content,
            next_task=execution.next_task,
            progress_events=execution.progress_events,
        )
        effect_result = self.side_effect_handler.apply(ConfirmedTaskSideEffectContext(
            db=request.db,
            session=request.session,
            task=request.task,
            team_id=request.team_id,
            user_id=request.user_id,
            execution=confirmed_execution,
            channel=request.channel,
            provider=request.provider,
        ))
        return {
            "execution_status": (
                "completed" if effect_result.task_event.get("event") == "task_completed" else "failed"
            ),
            "tool_result": coerce_json_dict(confirmed_execution.tool_event),
            "task_event": coerce_json_dict(effect_result.task_event),
            "assistant_content": effect_result.assistant_content,
            "output_events": [coerce_json_dict(event) for event in effect_result.output_events],
            "executed_task_snapshot": coerce_json_dict(effect_result.executed_task_snapshot),
            "active_task_snapshot": coerce_json_dict(effect_result.active_task_snapshot),
            "progress_events": [coerce_json_dict(event) for event in execution.progress_events],
        }


confirmed_application_step_executor = DefaultConfirmedApplicationStepExecutor()

"""Side effects emitted by the confirmed-task LangGraph subgraph."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.services.agent import interactions
from app.services.agent.state import ConfirmedTaskExecutionResult
from app.services.agent.types import JSONDict, coerce_json_dict, coerce_json_value
from app.services.follow_up_task_confirmation_channel_service import follow_up_task_confirmation_channel_service


logger = logging.getLogger(__name__)


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
        prompt_events = self._current_activity_confirmation_prompt_events(context)
        output_events.extend(prompt_events)
        assistant_content = _assistant_content_with_prompts(execution.assistant_content, prompt_events)
        output_events.append({"event": "final", "content": assistant_content})
        return ConfirmedTaskSideEffectResult(
            task_event=task_event,
            output_events=output_events,
            assistant_content=assistant_content,
        )

    def _current_activity_confirmation_prompt_events(
        self,
        context: ConfirmedTaskSideEffectContext,
    ) -> list[JSONDict]:
        case_public_ids = _post_commit_confirmation_case_public_ids(context.execution.tool_event)
        if not case_public_ids:
            return []
        try:
            return [
                coerce_json_dict(event)
                for event in follow_up_task_confirmation_channel_service.prompt_cases_by_public_ids(
                    context.db,
                    team_id=context.team_id,
                    user_id=context.user_id,
                    case_public_ids=case_public_ids,
                    channel=context.channel or "web",
                    provider=context.provider,
                    agent_session_id=_session_id(context.session),
                )
            ]
        except Exception:
            rollback = getattr(context.db, "rollback", None)
            if callable(rollback):
                rollback()
            logger.exception(
                "Current activity follow-up confirmation prompt failed: team_id=%s user_id=%s case_public_ids=%s",
                context.team_id,
                context.user_id,
                case_public_ids,
            )
            return []


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


def _session_id(session: object) -> int | None:
    raw_id = getattr(session, "id", None)
    return raw_id if isinstance(raw_id, int) else None


def _post_commit_confirmation_case_public_ids(tool_event: JSONDict | None) -> list[str]:
    if not isinstance(tool_event, dict):
        return []
    data = tool_event.get("data")
    if not isinstance(data, dict):
        return []
    post_commit = data.get("post_commit")
    if not isinstance(post_commit, dict) or not post_commit.get("needs_user_confirmation"):
        return []
    public_ids = post_commit.get("confirmation_case_public_ids")
    if not isinstance(public_ids, list):
        return []
    return [str(public_id) for public_id in public_ids if public_id]


def _assistant_content_with_prompts(assistant_content: str, prompt_events: list[JSONDict]) -> str:
    prompt_contents = [
        str(event.get("content")).strip()
        for event in prompt_events
        if isinstance(event.get("content"), str) and str(event.get("content")).strip()
    ]
    if not prompt_contents:
        return assistant_content
    return "\n\n".join([assistant_content, *prompt_contents])


confirmed_task_side_effect_handler = ConfirmedTaskSideEffectHandler()

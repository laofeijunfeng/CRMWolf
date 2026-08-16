"""Application-layer executor for hidden PendingTask steps.

LangGraph requests a stable application-step intent. This deep module owns the
ordinary application modules, converts their runtime results into
checkpoint-safe JSON, and builds any user-visible business interrupt before the
owning graph continuation resumes.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Protocol

from app.models.agent import AgentTaskStatus
from app.services.agent import interactions
from app.services.agent.hitl_runtime import interrupt_from_runtime_events
from app.services.agent.interrupts import interrupt_from_waiting_task
from app.services.agent.pending_application_modules import (
    PendingInteractionApplicationModule,
    PendingPreflightApplicationModule,
    PendingTaskTransitionApplicationModule,
    PendingTurnRelationApplicationModule,
)
from app.services.agent.task_projection import (
    agent_task_snapshot,
    materialized_agent_task_snapshot,
    runtime_agent_task_view,
    task_projection_intent,
)
from app.services.agent.types import JSONDict, coerce_json_dict, coerce_json_value

if TYPE_CHECKING:
    from app.services.agent.pending_application_step_projection import (
        PendingApplicationStepExecutionRequest,
    )
    from app.services.agent.schemas import AgentTurnRelationDecision
    from app.services.agent.state import PendingTaskPreflightResult, PendingTaskTurnResult


class PendingTaskTransitionModule(Protocol):
    async def execute(self, request: PendingApplicationStepExecutionRequest) -> object: ...


class PendingPreflightModule(Protocol):
    async def execute(
        self,
        request: PendingApplicationStepExecutionRequest,
    ) -> PendingTaskPreflightResult: ...


class PendingInteractionModule(Protocol):
    async def execute(
        self,
        request: PendingApplicationStepExecutionRequest,
    ) -> PendingTaskTurnResult: ...


class PendingTurnRelationModule(Protocol):
    async def execute(
        self,
        request: PendingApplicationStepExecutionRequest,
    ) -> AgentTurnRelationDecision: ...


class DefaultPendingApplicationStepExecutor:
    """Execute one durable application step through a single stable interface."""

    def __init__(
        self,
        *,
        task_transition_module: PendingTaskTransitionModule | None = None,
        preflight_module: PendingPreflightModule | None = None,
        interaction_module: PendingInteractionModule | None = None,
        turn_relation_module: PendingTurnRelationModule | None = None,
    ) -> None:
        self.task_transition_module = (
            task_transition_module or PendingTaskTransitionApplicationModule()
        )
        self.preflight_module = preflight_module or PendingPreflightApplicationModule()
        self.interaction_module = interaction_module or PendingInteractionApplicationModule()
        self.turn_relation_module = turn_relation_module or PendingTurnRelationApplicationModule()

    async def execute(self, request: PendingApplicationStepExecutionRequest) -> JSONDict:
        step_type = request.step["step_type"]
        if step_type == "task_transition":
            return await self._execute_task_transition(request)
        if step_type == "preflight":
            return await self._execute_preflight(request)
        if step_type == "interaction":
            return await self._execute_interaction(request)
        if step_type == "turn_relation_assessment":
            return await self._execute_turn_relation(request)
        raise ValueError(f"unsupported pending application step: {step_type}")

    async def _execute_task_transition(
        self,
        request: PendingApplicationStepExecutionRequest,
    ) -> JSONDict:
        task = await self.task_transition_module.execute(request)
        return {
            "step_type": "task_transition",
            "task_snapshot": agent_task_snapshot(task),
            "result": {
                "consumed_intent_ids": [
                    str(intent.get("intent_id"))
                    for intent in request.step.get("effect_intents") or []
                    if isinstance(intent, dict) and intent.get("intent_id")
                ],
            },
        }

    async def _execute_preflight(self, request: PendingApplicationStepExecutionRequest) -> JSONDict:
        result = await self.preflight_module.execute(request)
        return {
            "step_type": "preflight",
            "task_snapshot": agent_task_snapshot(getattr(result, "task", None)),
            "suspended_task_snapshot": agent_task_snapshot(getattr(result, "suspended_task", None)),
            "result": {
                "handled": bool(getattr(result, "handled", False)),
                "events": _events(getattr(result, "events", None)),
                "assistant_content": _optional_text(getattr(result, "assistant_content", None)),
                "switch_notice": _optional_text(getattr(result, "switch_notice", None)),
                "suspend_reason": _optional_text(getattr(result, "suspend_reason", None)),
                "suspension_kind": _optional_text(getattr(result, "suspension_kind", None)),
                "clear_pending_task_id": coerce_json_value(getattr(result, "clear_pending_task_id", None)),
                "confirmation_decision": _model_projection(getattr(result, "confirmation_decision", None)),
            },
        }

    async def _execute_interaction(self, request: PendingApplicationStepExecutionRequest) -> JSONDict:
        runtime_task = runtime_agent_task_view(request.task) if request.task is not None else None
        interaction_request = replace(request, task=runtime_task)
        result = await self.interaction_module.execute(interaction_request)
        events = _events(getattr(result, "events", None))
        current_interrupt = _business_interrupt_from_interaction(
            result,
            task=runtime_task,
            events=events,
            db=request.db,
            team_id=request.team_id,
        )
        projection_intent = task_projection_intent(runtime_task) if runtime_task is not None else None
        return {
            "step_type": "interaction",
            "task_snapshot": materialized_agent_task_snapshot(runtime_task),
            "application_effect_intents": [projection_intent] if projection_intent else [],
            "result": {
                "handled": bool(getattr(result, "handled", False)),
                "events": events,
                "assistant_content": _optional_text(getattr(result, "assistant_content", None)),
                "selected_customer": coerce_json_dict(getattr(result, "selected_customer", None)),
                "remember_pending_task": bool(getattr(result, "remember_pending_task", False)),
                "clear_pending_task_id": coerce_json_value(getattr(result, "clear_pending_task_id", None)),
                "current_interrupt": coerce_json_dict(current_interrupt),
            },
        }

    async def _execute_turn_relation(self, request: PendingApplicationStepExecutionRequest) -> JSONDict:
        decision = await self.turn_relation_module.execute(request)
        return {
            "step_type": "turn_relation_assessment",
            "task_snapshot": agent_task_snapshot(request.task),
            "result": {"decision": _model_projection(decision)},
        }


def _business_interrupt_from_interaction(
    result: object,
    *,
    task: object | None,
    events: list[JSONDict],
    db: object | None,
    team_id: int,
) -> JSONDict | None:
    current_interrupt = interrupt_from_runtime_events(events, db=db, team_id=team_id)
    if current_interrupt or not bool(getattr(result, "remember_pending_task", False)):
        return current_interrupt
    if task is None or getattr(task, "status", None) != AgentTaskStatus.WAITING_USER:
        return None
    if getattr(task, "id", None) is None or not getattr(task, "task_key", None):
        return None
    interaction = interactions._pending_task_interaction(
        task,
        getattr(result, "assistant_content", None) or "",
        db=db,
        team_id=team_id,
    )
    return interrupt_from_waiting_task(task, interaction=interaction)


def _model_projection(value: object) -> JSONDict:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return coerce_json_dict(model_dump(mode="json"))
    return coerce_json_dict(value)


def _events(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    return [coerce_json_dict(event) for event in value if isinstance(event, dict)]


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


pending_application_step_executor = DefaultPendingApplicationStepExecutor()

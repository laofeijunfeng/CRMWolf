"""Native durable LangGraph Workflow subgraph."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import ValidationError

from app.services.agent.workflow.contracts import (
    WorkflowActionPlan,
    WorkflowCancelledResult,
    WorkflowSkippedResult,
    WorkflowCompletedResult,
    WorkflowEffectResult,
    WorkflowFailedResult,
    WorkflowInteraction,
    WorkflowInterruptPayload,
    WorkflowRef,
    WorkflowResolvedCustomer,
    WorkflowResumeInput,
    WorkflowRuntimeContext,
    WorkflowSupplement,
    WorkflowTurnInput,
)
from app.services.agent.workflow.planning import (
    WorkflowPlanningError,
    WorkflowPlanningNeedsInput,
)
from app.services.agent.workflow.progress import (
    awaiting_confirmation_progress,
    awaiting_required_input_progress,
    confirmation_cancelled_progress,
    confirmation_failed_progress,
    execution_progress,
    input_failed_progress,
    planning_failed_progress,
    planning_progress,
    required_input_cancelled_progress,
    required_input_failed_progress,
    skipped_progress,
    understanding_progress,
)

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.runtime import Runtime


class WorkflowPlanner(Protocol):
    async def plan(
        self,
        request: WorkflowTurnInput,
        *,
        workflow_id: str,
        runtime: WorkflowRuntimeContext,
    ) -> WorkflowActionPlan: ...


class WorkflowEffectExecutor(Protocol):
    async def execute(
        self,
        plan: WorkflowActionPlan,
        *,
        workflow_id: str,
        request: WorkflowTurnInput,
        runtime: WorkflowRuntimeContext,
    ) -> WorkflowEffectResult: ...


class WorkflowSubgraphState(TypedDict, total=False):
    workflow_input: dict[str, object]
    workflow_id: str
    workflow_plan: dict[str, object] | None
    workflow_interaction: dict[str, object] | None
    workflow_resume: dict[str, object] | None
    workflow_result: dict[str, object] | None


class WorkflowSubgraph:
    """Own planning, HITL, canonical resume validation, and CRM effects."""

    def __init__(
        self,
        *,
        planner: WorkflowPlanner,
        effect_executor: WorkflowEffectExecutor,
    ) -> None:
        self._planner = planner
        self._effect_executor = effect_executor

    def compile(self) -> CompiledStateGraph:
        graph = StateGraph(WorkflowSubgraphState, context_schema=WorkflowRuntimeContext)
        graph.add_node("initialize", self._initialize)
        graph.add_node("plan", self._plan)
        graph.add_node("await_required_input", self._await_required_input)
        graph.add_node("apply_supplement", self._apply_supplement)
        graph.add_node("cancel_required_input", self._cancel_required_input)
        graph.add_node("await_confirmation", self._await_confirmation)
        graph.add_node("execute", self._execute)
        graph.add_node("cancel", self._cancel)
        graph.add_node("cancel_terminal", self._cancel_terminal)
        graph.add_node("skip_terminal", self._skip_terminal)
        graph.add_edge(START, "initialize")
        graph.add_edge("initialize", "plan")
        graph.add_conditional_edges(
            "plan",
            self._route_after_plan,
            {
                "NEEDS_INPUT": "await_required_input",
                "CONFIRM": "await_confirmation",
                "EXECUTE": "execute",
                "CANCELLED": "cancel_terminal",
                "SKIPPED": "skip_terminal",
                "END": END,
            },
        )
        graph.add_conditional_edges(
            "await_required_input",
            self._route_after_required_input,
            {
                "SUPPLEMENT": "apply_supplement",
                "CANCEL": "cancel_required_input",
                "END": END,
            },
        )
        graph.add_edge("apply_supplement", "plan")
        graph.add_edge("cancel_required_input", END)
        graph.add_conditional_edges(
            "await_confirmation",
            self._route_after_confirmation,
            {
                "EXECUTE": "execute",
                "CANCEL": "cancel",
                "END": END,
            },
        )
        graph.add_edge("execute", END)
        graph.add_edge("cancel", END)
        graph.add_edge("cancel_terminal", END)
        graph.add_edge("skip_terminal", END)
        # Inherit Root's checkpointer so LangGraph assigns a task-scoped child
        # namespace to every Workflow execution. ``checkpointer=True`` creates a
        # shared ``workflow_subgraph`` namespace and allows independent suspended
        # Workflows in one Root thread to enter the same checkpoint chain.
        return graph.compile(checkpointer=None)

    @staticmethod
    def _initialize(state: WorkflowSubgraphState) -> WorkflowSubgraphState:
        writer = get_stream_writer()
        writer(understanding_progress().model_dump(mode="json"))
        raw_request = state.get("workflow_input")
        try:
            request = WorkflowTurnInput.model_validate(raw_request)
        except ValidationError:
            writer(input_failed_progress().model_dump(mode="json"))
            return {
                "workflow_plan": None,
                "workflow_interaction": None,
                "workflow_resume": None,
                "workflow_result": WorkflowFailedResult(
                    workflow_ref=None,
                    code="WORKFLOW_INPUT_INVALID",
                    message="工作流输入无效。",
                    progress=input_failed_progress(),
                ).model_dump(mode="json"),
            }
        writer(
            planning_progress(has_supplements=bool(request.supplements)).model_dump(mode="json")
        )
        return {
            "workflow_id": request.workflow_id,
            "workflow_plan": None,
            "workflow_interaction": None,
            "workflow_resume": None,
            "workflow_result": None,
        }

    async def _plan(
        self,
        state: WorkflowSubgraphState,
        runtime: Runtime[WorkflowRuntimeContext],
    ) -> WorkflowSubgraphState:
        if state.get("workflow_result") is not None:
            return {}
        workflow_id = state["workflow_id"]
        writer = get_stream_writer()
        raw_request = state.get("workflow_input")
        if raw_request is None:
            writer(input_failed_progress().model_dump(mode="json"))
            return {
                "workflow_result": WorkflowFailedResult(
                    workflow_ref=WorkflowRef(workflow_id=workflow_id),
                    code="WORKFLOW_INPUT_MISSING",
                    message="工作流输入缺失。",
                    progress=input_failed_progress(),
                ).model_dump(mode="json")
            }
        try:
            request = WorkflowTurnInput.model_validate(raw_request)
        except ValidationError:
            writer(input_failed_progress().model_dump(mode="json"))
            return {
                "workflow_result": WorkflowFailedResult(
                    workflow_ref=WorkflowRef(workflow_id=workflow_id),
                    code="WORKFLOW_INPUT_INVALID",
                    message="工作流输入无效。",
                    progress=input_failed_progress(),
                ).model_dump(mode="json")
            }
        writer(
            planning_progress(has_supplements=bool(request.supplements)).model_dump(mode="json")
        )
        try:
            plan = await self._planner.plan(
                request,
                workflow_id=workflow_id,
                runtime=runtime.context,
            )
        except WorkflowPlanningNeedsInput as exc:
            writer(awaiting_required_input_progress().model_dump(mode="json"))
            return {
                "workflow_input": (
                    exc.checkpoint_request.model_dump(mode="json")
                    if exc.checkpoint_request is not None
                    else raw_request
                ),
                "workflow_plan": None,
                "workflow_interaction": exc.interaction.model_dump(mode="json"),
                "workflow_resume": None,
                "workflow_result": None,
            }
        except WorkflowPlanningError as exc:
            writer(planning_failed_progress().model_dump(mode="json"))
            return {
                "workflow_plan": None,
                "workflow_interaction": None,
                "workflow_result": WorkflowFailedResult(
                    workflow_ref=WorkflowRef(workflow_id=workflow_id),
                    code=exc.code,
                    message=exc.message,
                    retryable=exc.retryable,
                    progress=planning_failed_progress(),
                ).model_dump(mode="json")
            }
        if plan.execution_authorization == "CONFIRMATION_REQUIRED":
            writer(awaiting_confirmation_progress().model_dump(mode="json"))
        else:
            writer(
                execution_progress(
                    confirmation_required=False,
                    has_supplements=bool(request.supplements),
                    outcome="RUNNING",
                ).model_dump(mode="json")
            )
        request = self._cache_resolved_customer(request, plan)
        return {
            "workflow_input": request.model_dump(mode="json"),
            "workflow_plan": plan.model_dump(mode="json"),
            "workflow_interaction": None,
            "workflow_resume": None,
            "workflow_result": None,
        }

    @staticmethod
    def _cache_resolved_customer(
        request: WorkflowTurnInput,
        plan: WorkflowActionPlan,
    ) -> WorkflowTurnInput:
        """Persist the resolved customer in checkpoint state, not in tool payloads."""

        for command in plan.commands:
            customer_id = command.payload.get("customer_id")
            customer_name = command.payload.get("customer_name")
            if not isinstance(customer_id, str) or not customer_id.startswith("cus_"):
                continue
            if not isinstance(customer_name, str) or not customer_name.strip():
                continue
            lookup_name = request.resolved_customer.lookup_name if request.resolved_customer else None
            if lookup_name is None:
                lookup_name = customer_name.strip()
            return request.model_copy(
                update={
                    "resolved_customer": WorkflowResolvedCustomer(
                        customer_id=customer_id,
                        customer_name=customer_name.strip(),
                        lookup_name=lookup_name,
                    )
                }
            )
        return request

    @staticmethod
    def _route_after_plan(state: WorkflowSubgraphState) -> str:
        if state.get("workflow_result") is not None:
            return "END"
        if state.get("workflow_interaction") is not None:
            return "NEEDS_INPUT"
        try:
            plan = WorkflowActionPlan.model_validate(state["workflow_plan"])
        except (KeyError, ValidationError):
            return "END"
        if plan.terminal_outcome == "CANCELLED":
            return "CANCELLED"
        if plan.terminal_outcome == "SKIPPED":
            return "SKIPPED"
        if plan.execution_authorization == "CONFIRMATION_REQUIRED":
            return "CONFIRM"
        if plan.execution_authorization in {"AUTO_EXECUTE_AUTHORIZED", "RESUME_AUTHORIZED"}:
            return "EXECUTE"
        return "END"

    @staticmethod
    def _await_required_input(state: WorkflowSubgraphState) -> WorkflowSubgraphState:
        workflow_id = state["workflow_id"]
        writer = get_stream_writer()
        try:
            interaction = WorkflowInteraction.model_validate(state["workflow_interaction"])
        except (KeyError, ValidationError):
            return {
                "workflow_result": WorkflowFailedResult(
                    workflow_ref=WorkflowRef(workflow_id=workflow_id),
                    code="WORKFLOW_INTERACTION_INVALID",
                    message="工作流补充信息请求无效。",
                    progress=required_input_failed_progress(),
                ).model_dump(mode="json")
            }
        progress = awaiting_required_input_progress()
        writer(progress.model_dump(mode="json"))
        raw_resume = interrupt(
            WorkflowInterruptPayload(
                workflow_id=workflow_id,
                interaction=interaction,
                progress=progress,
            ).model_dump(mode="json")
        )
        try:
            resume = WorkflowResumeInput.model_validate(raw_resume)
        except ValidationError:
            return {
                "workflow_result": WorkflowFailedResult(
                    workflow_ref=WorkflowRef(workflow_id=workflow_id),
                    code="WORKFLOW_RESUME_INVALID",
                    message="工作流恢复数据无效, 请刷新后重试。",
                    progress=required_input_failed_progress(),
                ).model_dump(mode="json")
            }
        if resume.kind == "confirm":
            return {
                "workflow_result": WorkflowFailedResult(
                    workflow_ref=WorkflowRef(workflow_id=workflow_id),
                    code="WORKFLOW_SUPPLEMENT_REQUIRED",
                    message="当前工作流需要补充文本或表单内容。",
                    progress=required_input_failed_progress(),
                ).model_dump(mode="json")
            }
        return {"workflow_resume": resume.model_dump(mode="json")}

    @staticmethod
    def _route_after_required_input(state: WorkflowSubgraphState) -> str:
        if state.get("workflow_result") is not None:
            return "END"
        try:
            resume = WorkflowResumeInput.model_validate(state["workflow_resume"])
        except (KeyError, ValidationError):
            return "END"
        return "SUPPLEMENT" if resume.kind == "text" else "CANCEL"

    @staticmethod
    def _apply_supplement(state: WorkflowSubgraphState) -> WorkflowSubgraphState:
        workflow_id = state["workflow_id"]
        try:
            resume = WorkflowResumeInput.model_validate(state["workflow_resume"])
            if resume.kind != "text" or not resume.content.strip():
                raise ValueError("text supplement is required")
            request = WorkflowTurnInput.model_validate(state["workflow_input"])
            supplements = list(request.supplements)
            supplements.append(
                WorkflowSupplement(
                    content=resume.content.strip(),
                    source=resume.source,
                    provider=resume.provider,
                    metadata=resume.metadata,
                )
            )
            if len(supplements) > 20:
                raise ValueError("supplement limit exceeded")
        except (KeyError, ValidationError, ValueError):
            return {
                "workflow_result": WorkflowFailedResult(
                    workflow_ref=WorkflowRef(workflow_id=workflow_id),
                    code="WORKFLOW_SUPPLEMENT_INVALID",
                    message="工作流补充信息无效。",
                    progress=required_input_failed_progress(),
                ).model_dump(mode="json")
            }
        request = request.model_copy(update={"supplements": supplements})
        return {
            "workflow_input": request.model_dump(mode="json"),
            "workflow_interaction": None,
            "workflow_resume": None,
            "workflow_result": None,
        }

    @staticmethod
    def _cancel_required_input(state: WorkflowSubgraphState) -> WorkflowSubgraphState:
        workflow_id = state["workflow_id"]
        return {
            "workflow_result": WorkflowCancelledResult(
                workflow_ref=WorkflowRef(workflow_id=workflow_id),
                assistant_text="已取消当前工作流。",
                progress=required_input_cancelled_progress(),
            ).model_dump(mode="json")
        }

    @staticmethod
    def _await_confirmation(state: WorkflowSubgraphState) -> WorkflowSubgraphState:
        workflow_id = state["workflow_id"]
        writer = get_stream_writer()
        try:
            plan = WorkflowActionPlan.model_validate(state["workflow_plan"])
        except (KeyError, ValidationError):
            return {
                "workflow_result": WorkflowFailedResult(
                    workflow_ref=WorkflowRef(workflow_id=workflow_id),
                    code="WORKFLOW_PLAN_INVALID",
                    message="工作流计划无效。",
                    progress=planning_failed_progress(),
                ).model_dump(mode="json")
            }
        if plan.interaction is None:
            return {
                "workflow_result": WorkflowFailedResult(
                    workflow_ref=WorkflowRef(workflow_id=workflow_id),
                    code="WORKFLOW_PLAN_INVALID",
                    message="工作流计划无效。",
                    progress=planning_failed_progress(),
                ).model_dump(mode="json")
            }
        progress = awaiting_confirmation_progress()
        writer(progress.model_dump(mode="json"))
        raw_resume = interrupt(
            WorkflowInterruptPayload(
                workflow_id=workflow_id,
                interaction=plan.interaction,
                progress=progress,
            ).model_dump(mode="json")
        )
        try:
            resume = WorkflowResumeInput.model_validate(raw_resume)
        except ValidationError:
            return {
                "workflow_result": WorkflowFailedResult(
                    workflow_ref=WorkflowRef(workflow_id=workflow_id),
                    code="WORKFLOW_RESUME_INVALID",
                    message="工作流恢复数据无效, 请刷新后重试。",
                    progress=confirmation_failed_progress(),
                ).model_dump(mode="json")
            }
        return {"workflow_resume": resume.model_dump(mode="json")}

    @staticmethod
    def _route_after_confirmation(state: WorkflowSubgraphState) -> str:
        if state.get("workflow_result") is not None:
            return "END"
        try:
            resume = WorkflowResumeInput.model_validate(state["workflow_resume"])
        except (KeyError, ValidationError):
            return "END"
        return "EXECUTE" if resume.kind == "confirm" else "CANCEL"

    async def _execute(
        self,
        state: WorkflowSubgraphState,
        runtime: Runtime[WorkflowRuntimeContext],
    ) -> WorkflowSubgraphState:
        workflow_id = state["workflow_id"]
        try:
            plan = WorkflowActionPlan.model_validate(state["workflow_plan"])
        except (KeyError, ValidationError):
            return {
                "workflow_result": WorkflowFailedResult(
                    workflow_ref=WorkflowRef(workflow_id=workflow_id),
                    code="WORKFLOW_PLAN_INVALID",
                    message="工作流计划无效。",
                    progress=planning_failed_progress(),
                ).model_dump(mode="json")
            }
        try:
            request = WorkflowTurnInput.model_validate(state["workflow_input"])
        except (KeyError, ValidationError):
            return {
                "workflow_result": WorkflowFailedResult(
                    workflow_ref=WorkflowRef(workflow_id=workflow_id),
                    code="WORKFLOW_INPUT_INVALID",
                    message="工作流输入无效。",
                    progress=input_failed_progress(),
                ).model_dump(mode="json")
            }
        writer = get_stream_writer()
        running_progress = execution_progress(
            confirmation_required=plan.execution_authorization == "CONFIRMATION_REQUIRED",
            has_supplements=bool(request.supplements),
            outcome="RUNNING",
        )
        writer(running_progress.model_dump(mode="json"))
        effect_result = await self._effect_executor.execute(
            plan,
            workflow_id=workflow_id,
            request=request,
            runtime=runtime.context,
        )
        if effect_result.success:
            completed_progress = execution_progress(
                confirmation_required=plan.execution_authorization == "CONFIRMATION_REQUIRED",
                has_supplements=bool(request.supplements),
                outcome="COMPLETED",
            )
            writer(completed_progress.model_dump(mode="json"))
            return {
                "workflow_result": WorkflowCompletedResult(
                    workflow_ref=WorkflowRef(workflow_id=workflow_id),
                    assistant_text=effect_result.message,
                    progress=completed_progress,
                    durable_work=effect_result.durable_work,
                ).model_dump(mode="json")
            }
        failed_progress = execution_progress(
            confirmation_required=plan.execution_authorization == "CONFIRMATION_REQUIRED",
            has_supplements=bool(request.supplements),
            outcome="FAILED",
        )
        writer(failed_progress.model_dump(mode="json"))
        return {
            "workflow_result": WorkflowFailedResult(
                workflow_ref=WorkflowRef(workflow_id=workflow_id),
                code=effect_result.code or "WORKFLOW_EFFECT_FAILED",
                message=effect_result.message,
                retryable=effect_result.retryable,
                progress=failed_progress,
            ).model_dump(mode="json")
        }

    @staticmethod
    def _cancel_terminal(state: WorkflowSubgraphState) -> WorkflowSubgraphState:
        workflow_id = state["workflow_id"]
        try:
            plan = WorkflowActionPlan.model_validate(state["workflow_plan"])
        except (KeyError, ValidationError):
            return {
                "workflow_result": WorkflowFailedResult(
                    workflow_ref=WorkflowRef(workflow_id=workflow_id),
                    code="WORKFLOW_PLAN_INVALID",
                    message="工作流计划无效。",
                    progress=planning_failed_progress(),
                ).model_dump(mode="json")
            }
        return {
            "workflow_result": WorkflowCancelledResult(
                workflow_ref=WorkflowRef(workflow_id=workflow_id),
                assistant_text=plan.cancelled_text,
                progress=confirmation_cancelled_progress(),
            ).model_dump(mode="json")
        }

    @staticmethod
    def _skip_terminal(state: WorkflowSubgraphState) -> WorkflowSubgraphState:
        workflow_id = state["workflow_id"]
        try:
            plan = WorkflowActionPlan.model_validate(state["workflow_plan"])
        except (KeyError, ValidationError):
            return {
                "workflow_result": WorkflowFailedResult(
                    workflow_ref=WorkflowRef(workflow_id=workflow_id),
                    code="WORKFLOW_PLAN_INVALID",
                    message="工作流计划无效。",
                    progress=planning_failed_progress(),
                ).model_dump(mode="json")
            }
        return {
            "workflow_result": WorkflowSkippedResult(
                workflow_ref=WorkflowRef(workflow_id=workflow_id),
                progress=skipped_progress(),
                reason=plan.terminal_reason or "workflow_terminal_noop",
            ).model_dump(mode="json")
        }

    @staticmethod
    def _cancel(state: WorkflowSubgraphState) -> WorkflowSubgraphState:
        workflow_id = state["workflow_id"]
        try:
            plan = WorkflowActionPlan.model_validate(state["workflow_plan"])
        except (KeyError, ValidationError):
            return {
                "workflow_result": WorkflowFailedResult(
                    workflow_ref=WorkflowRef(workflow_id=workflow_id),
                    code="WORKFLOW_PLAN_INVALID",
                    message="工作流计划无效。",
                    progress=planning_failed_progress(),
                ).model_dump(mode="json")
            }
        return {
            "workflow_result": WorkflowCancelledResult(
                workflow_ref=WorkflowRef(workflow_id=workflow_id),
                assistant_text=plan.cancelled_text,
                progress=confirmation_cancelled_progress(),
            ).model_dump(mode="json")
        }


def build_workflow_subgraph(
    *,
    planner: WorkflowPlanner,
    effect_executor: WorkflowEffectExecutor,
) -> CompiledStateGraph:
    """Build the only production Workflow graph interface consumed by Root."""

    return WorkflowSubgraph(
        planner=planner,
        effect_executor=effect_executor,
    ).compile()

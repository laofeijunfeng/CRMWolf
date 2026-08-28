"""Tracer tests for native LangGraph Workflow subgraphs through Root dispatch."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.services.agent.orchestrator import (
    ContextPolicy,
    InteractionResolution,
    InteractionTurnInput,
    QueryExecutionInput,
    ResolvedAgentAction,
    RootContextSnapshot,
    RootDecision,
    RootOrchestrator,
    RootRuntimeContext,
    RootTurnInput,
    TextTurnInput,
    WorkflowCompletedResult,
    WorkflowContinuation,
    WorkflowDispatchResult,
    WorkflowInteraction,
    WorkflowInteractionOption,
    WorkflowInterruptPayload,
    WorkflowWaitingResult,
)
from app.services.agent.workflow import WorkflowRef, WorkflowTextStart, WorkflowTurnInput
from app.services.agent.workflow.progress import (
    awaiting_confirmation_progress,
    execution_progress,
)

if TYPE_CHECKING:
    from app.services.agent.query import CRMQueryAgentResult


class EmptyContextResolver:
    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        runtime: RootRuntimeContext,
    ) -> RootContextSnapshot:
        return RootContextSnapshot()


class WorkflowDecisionClassifier:
    def __init__(self) -> None:
        self.calls = 0

    async def classify(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> RootDecision:
        self.calls += 1
        return RootDecision(
            task_relation="NEW_TASK",
            route="WORKFLOW",
            risk="WRITE",
            context_policy=ContextPolicy(
                selected_entity="IGNORE",
                previous_query="IGNORE",
                result_set="IGNORE",
                active_workflow="NONE",
            ),
            confidence=1.0,
            reason_code="CREATE_FOLLOW_UP",
        )


class FailingQueryExecutor:
    async def execute(self, request: object, *, runtime: object) -> CRMQueryAgentResult:
        raise AssertionError("workflow turn must not execute Query Agent")


class BoundInteractionResolver:
    def __init__(self) -> None:
        self.continuation: WorkflowContinuation | None = None

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> InteractionResolution:
        assert self.continuation is not None
        return InteractionResolution(
            status="RESOLVED",
            reason_code="STRUCTURED_WORKFLOW_CONTINUATION",
            resolved_action=ResolvedAgentAction(
                action_id="act_confirm_follow_up",
                action_type="submit_interaction",
                continuation=self.continuation,
                claim_outcome="ACQUIRED",
                resume_payload={"action": "confirm"},
            ),
        )


class NativeWorkflowState(TypedDict, total=False):
    workflow_input: dict[str, object]
    workflow_id: str
    workflow_result: dict[str, object]


def native_confirmation_workflow(effect_calls: list[dict[str, object]]):
    async def initialize(_state: NativeWorkflowState) -> NativeWorkflowState:
        return {"workflow_id": "wf_native_follow_up"}

    async def confirm(state: NativeWorkflowState) -> NativeWorkflowState:
        interaction = WorkflowInteraction(
            interaction_id="interaction_confirm_follow_up",
            interaction_type="confirmation",
            business_action="confirm_create_follow_up",
            title="确认创建跟进任务",
            prompt="确认创建这条跟进任务吗?",
            options=[
                WorkflowInteractionOption(value="confirm", label="确认"),
                WorkflowInteractionOption(value="cancel", label="取消"),
            ],
            selection_mode="single",
            min_selections=1,
            max_selections=1,
            submit_label="确认",
        )
        resume_payload = interrupt(
            WorkflowInterruptPayload(
                workflow_id=state["workflow_id"],
                interaction=interaction,
                progress=awaiting_confirmation_progress(),
            ).model_dump(mode="json")
        )
        if resume_payload != {"action": "confirm"}:
            raise AssertionError("only the canonical server-authorized payload may resume")
        effect_calls.append(resume_payload)
        return {
            "workflow_result": WorkflowCompletedResult(
                workflow_ref=WorkflowRef(workflow_id=state["workflow_id"]),
                assistant_text="跟进任务已创建。",
                progress=execution_progress(
                    confirmation_required=True,
                    has_supplements=False,
                    outcome="COMPLETED",
                ),
            ).model_dump(mode="json")
        }

    graph = StateGraph(NativeWorkflowState)
    graph.add_node("initialize", initialize)
    graph.add_node("confirm", confirm)
    graph.add_edge(START, "initialize")
    graph.add_edge("initialize", "confirm")
    graph.add_edge("confirm", END)
    return graph.compile(checkpointer=True)


async def test_root_dispatch_resumes_native_workflow_subgraph_after_authoritative_preflight() -> None:
    classifier = WorkflowDecisionClassifier()
    interaction_resolver = BoundInteractionResolver()
    effect_calls: list[dict[str, object]] = []
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=classifier,
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=native_confirmation_workflow(effect_calls),
    )
    runtime = RootRuntimeContext()

    waiting_dispatch = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_start_native_workflow",
            input=TextTurnInput(type="text", text="帮我创建一条跟进任务"),
        ),
        runtime=runtime,
    )

    assert isinstance(waiting_dispatch, WorkflowDispatchResult)
    assert isinstance(waiting_dispatch.workflow_result, WorkflowWaitingResult)
    assert waiting_dispatch.workflow_result.workflow_ref.workflow_id == "wf_native_follow_up"
    assert waiting_dispatch.workflow_result.workflow_ref.interrupt_id
    assert waiting_dispatch.workflow_result.interaction.business_action == "confirm_create_follow_up"
    assert waiting_dispatch.continuation is not None
    interaction_resolver.continuation = waiting_dispatch.continuation
    assert effect_calls == []

    completed_dispatch = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_confirm_native_workflow",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_follow_up",
                values={"action": "forged-client-value"},
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(completed_dispatch, WorkflowDispatchResult)
    assert isinstance(completed_dispatch.workflow_result, WorkflowCompletedResult)
    assert completed_dispatch.workflow_result.assistant_text == "跟进任务已创建。"
    assert classifier.calls == 1
    assert effect_calls == [{"action": "confirm"}]


class RejectingInteractionResolver:
    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> InteractionResolution:
        return InteractionResolution(
            status="REJECTED",
            reason_code="ACTION_WORKFLOW_BINDING_MISMATCH",
        )


class UnavailableInteractionResolver:
    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> InteractionResolution:
        from app.services.agent.orchestrator import InteractionResolutionUnavailableError

        raise InteractionResolutionUnavailableError("action storage unavailable")


class ReplayInteractionResolver:
    def __init__(self) -> None:
        self.continuation: WorkflowContinuation | None = None

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> InteractionResolution:
        assert self.continuation is not None
        return InteractionResolution(
            status="RESOLVED",
            reason_code="STRUCTURED_WORKFLOW_CONTINUATION",
            resolved_action=ResolvedAgentAction(
                action_id="act_confirm_follow_up",
                action_type="submit_interaction",
                continuation=self.continuation,
                claim_outcome="REPLAY",
                resume_payload={"action": "confirm"},
                replay_message_id=991,
            ),
        )


async def _start_waiting_workflow(
    *,
    interaction_resolver: object,
    effect_calls: list[dict[str, object]],
) -> tuple[RootOrchestrator, WorkflowDispatchResult]:
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=WorkflowDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=native_confirmation_workflow(effect_calls),
    )
    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_start_waiting_workflow",
            input=TextTurnInput(type="text", text="帮我创建一条跟进任务"),
        ),
        runtime=RootRuntimeContext(),
    )
    assert isinstance(result, WorkflowDispatchResult)
    assert isinstance(result.workflow_result, WorkflowWaitingResult)
    return orchestrator, result


async def test_rejected_action_returns_typed_failure_without_resuming_durable_workflow() -> None:
    effect_calls: list[dict[str, object]] = []
    orchestrator, _waiting = await _start_waiting_workflow(
        interaction_resolver=RejectingInteractionResolver(),
        effect_calls=effect_calls,
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_rejected_action",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_wrong_workflow",
                values={"action": "confirm"},
            ),
        ),
        runtime=RootRuntimeContext(),
    )

    from app.services.agent.orchestrator import FailureDispatchResult

    assert isinstance(result, FailureDispatchResult)
    assert result.error.code == "ACTION_INVALID"
    assert result.action_claim_id is None
    assert effect_calls == []


async def test_interaction_storage_failure_returns_typed_failure_without_resuming() -> None:
    effect_calls: list[dict[str, object]] = []
    orchestrator, _waiting = await _start_waiting_workflow(
        interaction_resolver=UnavailableInteractionResolver(),
        effect_calls=effect_calls,
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_unavailable_action_storage",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_follow_up",
                values={"action": "confirm"},
            ),
        ),
        runtime=RootRuntimeContext(),
    )

    from app.services.agent.orchestrator import FailureDispatchResult

    assert isinstance(result, FailureDispatchResult)
    assert result.error.code == "INTERACTION_RESOLUTION_UNAVAILABLE"
    assert effect_calls == []


async def test_replayed_action_returns_prior_message_without_resuming_again() -> None:
    from app.services.agent.orchestrator import WorkflowReplayResult

    effect_calls: list[dict[str, object]] = []
    interaction_resolver = ReplayInteractionResolver()
    orchestrator, waiting = await _start_waiting_workflow(
        interaction_resolver=interaction_resolver,
        effect_calls=effect_calls,
    )
    assert waiting.continuation is not None
    interaction_resolver.continuation = waiting.continuation

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_replayed_action",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_follow_up",
                values={"action": "confirm"},
            ),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, WorkflowDispatchResult)
    assert isinstance(result.workflow_result, WorkflowReplayResult)
    assert result.action_claim_id is None
    assert result.workflow_result.message_id == 991
    assert result.workflow_result.workflow_ref == waiting.workflow_result.workflow_ref
    assert effect_calls == []


class SwitchAwareDecisionClassifier:
    async def classify(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> RootDecision:
        assert isinstance(turn.input, TextTurnInput)
        if turn.input.text.startswith("查询"):
            return RootDecision(
                task_relation="SWITCH_TASK",
                route="QUERY",
                risk="READ_ONLY",
                context_policy=ContextPolicy(
                    selected_entity="IGNORE",
                    previous_query="IGNORE",
                    result_set="IGNORE",
                    active_workflow="SUSPEND" if context.active_workflow is not None else "NONE",
                ),
                confidence=1.0,
                reason_code="SWITCH_TO_QUERY",
            )
        return RootDecision(
            task_relation="SWITCH_TASK" if context.active_workflow is not None else "NEW_TASK",
            route="WORKFLOW",
            risk="WRITE",
            context_policy=ContextPolicy(
                selected_entity="IGNORE",
                previous_query="IGNORE",
                result_set="IGNORE",
                active_workflow="SUSPEND" if context.active_workflow is not None else "NONE",
            ),
            confidence=1.0,
            reason_code="START_NAMED_WORKFLOW",
        )


class SuccessfulQueryExecutor:
    async def execute(
        self,
        request: QueryExecutionInput,
        *,
        runtime: RootRuntimeContext,
    ) -> CRMQueryAgentResult:
        from app.services.agent.query import (
            CRMQueryAgentResponse,
            CRMQueryAgentResult,
            CRMQueryAgentTrace,
        )

        return CRMQueryAgentResult(
            response=CRMQueryAgentResponse(
                status="CLARIFICATION_REQUIRED",
                clarification_question="查询完成",
            ),
            trace=CRMQueryAgentTrace(
                model="test-query-model",
                tool_names=[],
                tool_calls=[],
                tool_call_count=0,
                total_entity_count=0,
                elapsed_ms=0,
                stop_reason="CLARIFICATION_REQUIRED",
            ),
        )


class WorkflowContinuationInteractionResolver:
    def __init__(self) -> None:
        self.continuations_by_action_id: dict[str, WorkflowContinuation] = {}

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> InteractionResolution:
        assert isinstance(turn.input, InteractionTurnInput)
        continuation = self.continuations_by_action_id[turn.input.action_id]
        return InteractionResolution(
            status="RESOLVED",
            reason_code="STRUCTURED_WORKFLOW_CONTINUATION",
            resolved_action=ResolvedAgentAction(
                action_id=turn.input.action_id,
                action_type="submit_interaction",
                continuation=continuation,
                claim_outcome="ACQUIRED",
                resume_payload={"action": "confirm"},
            ),
        )


def named_confirmation_workflow(effect_calls: list[str]):
    async def initialize(state: NativeWorkflowState) -> NativeWorkflowState:
        workflow_input = WorkflowTurnInput.model_validate(state["workflow_input"])
        assert isinstance(workflow_input.start, WorkflowTextStart)
        return {"workflow_id": f"wf_{workflow_input.start.text}"}

    async def confirm(state: NativeWorkflowState) -> NativeWorkflowState:
        interaction = WorkflowInteraction(
            interaction_id=f"interaction_{state['workflow_id']}",
            interaction_type="confirmation",
            business_action="confirm_named_workflow",
            title="确认执行",
            prompt=f"确认执行 {state['workflow_id']} 吗?",
            options=[
                WorkflowInteractionOption(value="confirm", label="确认"),
                WorkflowInteractionOption(value="cancel", label="取消"),
            ],
            selection_mode="single",
            min_selections=1,
            max_selections=1,
        )
        resume_payload = interrupt(
            WorkflowInterruptPayload(
                workflow_id=state["workflow_id"],
                interaction=interaction,
                progress=awaiting_confirmation_progress(),
            ).model_dump(mode="json")
        )
        assert resume_payload == {"action": "confirm"}
        effect_calls.append(state["workflow_id"])
        return {
            "workflow_result": WorkflowCompletedResult(
                workflow_ref=WorkflowRef(workflow_id=state["workflow_id"]),
                assistant_text=f"{state['workflow_id']} 已完成。",
                progress=execution_progress(
                    confirmation_required=True,
                    has_supplements=False,
                    outcome="COMPLETED",
                ),
            ).model_dump(mode="json")
        }

    graph = StateGraph(NativeWorkflowState)
    graph.add_node("initialize", initialize)
    graph.add_node("confirm", confirm)
    graph.add_edge(START, "initialize")
    graph.add_edge("initialize", "confirm")
    graph.add_edge("confirm", END)
    return graph.compile(checkpointer=True)


async def test_suspended_workflow_resumes_after_switching_to_query() -> None:
    effects: list[str] = []
    interaction_resolver = WorkflowContinuationInteractionResolver()
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=SwitchAwareDecisionClassifier(),
        query_executor=SuccessfulQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=named_confirmation_workflow(effects),
    )
    runtime = RootRuntimeContext()

    waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_start_workflow_a",
            input=TextTurnInput(type="text", text="A"),
        ),
        runtime=runtime,
    )
    assert isinstance(waiting, WorkflowDispatchResult)
    assert isinstance(waiting.workflow_result, WorkflowWaitingResult)
    assert waiting.continuation is not None
    interaction_resolver.continuations_by_action_id["act_confirm_a"] = waiting.continuation

    query = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_switch_to_query",
            input=TextTurnInput(type="text", text="查询上海客户"),
        ),
        runtime=runtime,
    )
    from app.services.agent.orchestrator import QueryDispatchResult

    assert isinstance(query, QueryDispatchResult)

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_resume_workflow_a",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_a",
                values={"action": "forged"},
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert completed.workflow_result.workflow_ref.workflow_id == "wf_A"
    assert effects == ["wf_A"]


async def test_switching_between_two_workflows_keeps_each_native_checkpoint_isolated() -> None:
    effects: list[str] = []
    interaction_resolver = WorkflowContinuationInteractionResolver()
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=SwitchAwareDecisionClassifier(),
        query_executor=SuccessfulQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=named_confirmation_workflow(effects),
    )
    runtime = RootRuntimeContext()

    workflow_a = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_start_isolated_a",
            input=TextTurnInput(type="text", text="A"),
        ),
        runtime=runtime,
    )
    assert isinstance(workflow_a, WorkflowDispatchResult)
    assert isinstance(workflow_a.workflow_result, WorkflowWaitingResult)
    assert workflow_a.continuation is not None
    interaction_resolver.continuations_by_action_id["act_isolated_a"] = workflow_a.continuation

    workflow_b = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_start_isolated_b",
            input=TextTurnInput(type="text", text="B"),
        ),
        runtime=runtime,
    )
    assert isinstance(workflow_b, WorkflowDispatchResult)
    assert isinstance(workflow_b.workflow_result, WorkflowWaitingResult)
    assert workflow_b.workflow_result.workflow_ref.workflow_id == "wf_B"
    assert workflow_b.continuation is not None
    interaction_resolver.continuations_by_action_id["act_isolated_b"] = workflow_b.continuation

    completed_a = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_complete_isolated_a",
            input=InteractionTurnInput(type="interaction", action_id="act_isolated_a", values={}),
        ),
        runtime=runtime,
    )
    assert isinstance(completed_a, WorkflowDispatchResult)
    assert isinstance(completed_a.workflow_result, WorkflowCompletedResult)
    assert completed_a.workflow_result.workflow_ref.workflow_id == "wf_A"

    completed_b = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_complete_isolated_b",
            input=InteractionTurnInput(type="interaction", action_id="act_isolated_b", values={}),
        ),
        runtime=runtime,
    )
    assert isinstance(completed_b, WorkflowDispatchResult)
    assert isinstance(completed_b.workflow_result, WorkflowCompletedResult)
    assert completed_b.workflow_result.workflow_ref.workflow_id == "wf_B"
    assert effects == ["wf_A", "wf_B"]

class MutableContinuationContextResolver:
    def __init__(self) -> None:
        self.continuation: WorkflowContinuation | None = None

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        runtime: RootRuntimeContext,
    ) -> RootContextSnapshot:
        if self.continuation is None:
            return RootContextSnapshot()
        return RootContextSnapshot(
            active_workflow=self.continuation.workflow_ref,
            resumable_workflows=[self.continuation.workflow_ref],
            resumable_workflow_continuations=[self.continuation],
        )


def native_text_input_workflow(received: list[dict[str, object]]):
    async def initialize(_state: NativeWorkflowState) -> NativeWorkflowState:
        return {"workflow_id": "wf_native_text_input"}

    async def request_input(state: NativeWorkflowState) -> NativeWorkflowState:
        interaction = WorkflowInteraction(
            interaction_id="interaction_text_input",
            interaction_type="text_input",
            business_action="supply_workflow_input",
            title="补充信息",
            prompt="请补充信息。",
            allow_blank=False,
            submit_label="提交",
        )
        raw_resume = interrupt(
            WorkflowInterruptPayload(
                workflow_id=state["workflow_id"],
                interaction=interaction,
                progress=awaiting_confirmation_progress(),
            ).model_dump(mode="json")
        )
        assert isinstance(raw_resume, dict)
        received.append(raw_resume)
        return {
            "workflow_result": WorkflowCompletedResult(
                workflow_ref=WorkflowRef(workflow_id=state["workflow_id"]),
                assistant_text="补充信息已接收。",
                progress=execution_progress(
                    confirmation_required=False,
                    has_supplements=True,
                    outcome="COMPLETED",
                ),
            ).model_dump(mode="json")
        }

    graph = StateGraph(NativeWorkflowState)
    graph.add_node("initialize", initialize)
    graph.add_node("request_input", request_input)
    graph.add_edge(START, "initialize")
    graph.add_edge("initialize", "request_input")
    graph.add_edge("request_input", END)
    return graph.compile(checkpointer=True)


async def test_explicit_text_continuation_resumes_original_checkpoint_instead_of_starting_new_workflow() -> None:
    received: list[dict[str, object]] = []
    context_resolver = MutableContinuationContextResolver()
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=context_resolver,
        decision_classifier=WorkflowDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=BoundInteractionResolver(),
        workflow_subgraph=native_text_input_workflow(received),
    )

    waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_start_text_input_workflow",
            input=TextTurnInput(type="text", text="启动一个需要补充信息的流程"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(waiting, WorkflowDispatchResult)
    assert isinstance(waiting.workflow_result, WorkflowWaitingResult)
    assert waiting.continuation is not None
    context_resolver.continuation = waiting.continuation

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_resume_text_input_workflow",
            input=TextTurnInput(type="text", text="补充刚才的信息：客户确认周四部署"),  # noqa: RUF001
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert completed.workflow_result.assistant_text == "补充信息已接收。"
    assert received == [
        {
            "kind": "text",
            "content": "补充刚才的信息：客户确认周四部署",  # noqa: RUF001
            "source": "agent_text",
            "provider": None,
            "metadata": {"continuation": "explicit"},
        }
    ]

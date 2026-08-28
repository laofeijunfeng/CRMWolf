"""Behavioral tests for the RootOrchestrator public seam."""

from __future__ import annotations

import json
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.services.agent.orchestrator import (
    ClarificationDispatchResult,
    ContextPolicy,
    CRMQueryAgentExecutor,
    FailureDispatchResult,
    InteractionResolution,
    InteractionTurnInput,
    LangChainRootDecisionClassifier,
    QueryDispatchResult,
    ResolvedAgentAction,
    ResultSetContext,
    RootContextSnapshot,
    RootDecision,
    RootDecisionModelConfig,
    RootOrchestrator,
    RootRuntimeContext,
    RootTurnInput,
    TextTurnInput,
    WorkflowCompletedResult,
    WorkflowContinuation,
    WorkflowDispatchResult,
    WorkflowRef,
    build_root_graph_config,
)
from app.services.agent.orchestrator.contracts import PendingCaseContext
from app.services.agent.query import (
    CRMFilter,
    CRMQueryAgentExecutionError,
    CRMQueryAgentModelConfig,
    CRMQueryAgentResponse,
    CRMQueryAgentResult,
    CRMQueryAgentTrace,
    CRMQuerySpec,
    EntityRef,
    QueryError,
)
from app.services.agent.workflow import WorkflowTurnInput
from app.services.agent.workflow.progress import execution_progress


def test_root_graph_config_is_stable_per_turn_and_isolated_within_session() -> None:
    first_turn = RootTurnInput(
        team_id=9,
        user_id=18,
        session_id=556,
        client_request_id="req_checkpoint_identity",
        input=TextTurnInput(type="text", text="上海有哪些客户"),
    )
    second_turn = first_turn.model_copy(update={"client_request_id": "req_other_turn"})
    config = build_root_graph_config(first_turn)
    second_config = build_root_graph_config(second_turn)

    assert config["configurable"]["thread_id"].startswith("crm_agent_turn:9:18:556:")
    assert config["configurable"]["thread_id"] == build_root_graph_config(first_turn)["configurable"]["thread_id"]
    assert config["configurable"]["thread_id"] != second_config["configurable"]["thread_id"]
    assert config["metadata"] == {
        "team_id": 9,
        "user_id": 18,
        "session_id": 556,
        "client_request_id": "req_checkpoint_identity",
        "turn_token": config["metadata"]["turn_token"],
        "runtime": "crm_agent_root",
        "runtime_namespace": "crm_agent",
    }


class StaticContextResolver:
    def __init__(self, snapshot: RootContextSnapshot | None = None) -> None:
        self.snapshot = snapshot or RootContextSnapshot()
        self.calls: list[RootTurnInput] = []

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        runtime: RootRuntimeContext,
    ) -> RootContextSnapshot:
        self.calls.append(turn)
        return self.snapshot


class StubDecisionClassifier:
    def __init__(self, decision: RootDecision) -> None:
        self.decision = decision
        self.calls: list[tuple[RootTurnInput, RootContextSnapshot]] = []

    async def classify(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> RootDecision:
        self.calls.append((turn, context))
        return self.decision


class FailingClassifier:
    async def classify(self, **kwargs: object) -> RootDecision:
        raise AssertionError("deterministic interaction must not call decision model")


class FailingInteractionResolver:
    async def resolve(self, **kwargs: object) -> InteractionResolution:
        raise AssertionError("text turn must not resolve an interaction")


class RecordingInteractionResolver:
    def __init__(self, resolution: InteractionResolution) -> None:
        self.resolution = resolution
        self.calls: list[tuple[RootTurnInput, RootContextSnapshot]] = []

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> InteractionResolution:
        self.calls.append((turn, context))
        return self.resolution


class RecordingQueryExecutor:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def execute(self, request: object, *, runtime: object) -> CRMQueryAgentResult:
        self.calls.append(request)
        return CRMQueryAgentResult(
            response=CRMQueryAgentResponse(
                status="ANSWERED",
                answer="上海客户查询完成",
                evidence_refs=["query_shanghai_customers"],
            ),
            trace=CRMQueryAgentTrace(
                model="test-model",
                tool_names=["query_customers"],
                tool_call_count=1,
                total_entity_count=0,
                elapsed_ms=1,
                stop_reason="COMPLETED",
            ),
        )


class WorkflowTestState(TypedDict, total=False):
    workflow_input: object
    workflow_result: dict[str, object]


def failing_workflow_subgraph():
    async def fail(_state: WorkflowTestState) -> WorkflowTestState:
        raise AssertionError("read-only query must not execute workflow")

    graph = StateGraph(WorkflowTestState)
    graph.add_node("fail", fail)
    graph.add_edge(START, "fail")
    graph.add_edge("fail", END)
    return graph.compile()


def recording_workflow_subgraph(calls: list[object]):
    async def record(state: WorkflowTestState) -> WorkflowTestState:
        workflow_input = WorkflowTurnInput.model_validate(state["workflow_input"])
        calls.append(workflow_input.model_dump(mode="json"))
        workflow_ref = WorkflowRef(workflow_id=workflow_input.workflow_id)
        return {
            "workflow_result": WorkflowCompletedResult(
                workflow_ref=workflow_ref,
                assistant_text="工作流已完成。",
                progress=execution_progress(
                    confirmation_required=False,
                    has_supplements=False,
                    outcome="COMPLETED",
                ),
            )
        }

    graph = StateGraph(WorkflowTestState)
    graph.add_node("record", record)
    graph.add_edge(START, "record")
    graph.add_edge("record", END)
    return graph.compile()


def query_decision(
    *,
    task_relation: str = "NEW_TASK",
    active_workflow: str = "NONE",
    selected_entity: str = "IGNORE",
    previous_query: str = "IGNORE",
    result_set: str = "IGNORE",
    confidence: float = 0.99,
    reason_code: str = "NEW_QUERY",
) -> RootDecision:
    return RootDecision.model_validate(
        {
            "task_relation": task_relation,
            "route": "QUERY",
            "risk": "READ_ONLY",
            "context_policy": {
                "selected_entity": selected_entity,
                "previous_query": previous_query,
                "result_set": result_set,
                "active_workflow": active_workflow,
            },
            "confidence": confidence,
            "reason_code": reason_code,
        }
    )


def workflow_decision(
    *,
    task_relation: str = "NEW_TASK",
    active_workflow: str = "NONE",
    selected_entity: str = "IGNORE",
    result_set: str = "IGNORE",
    confidence: float = 0.99,
    reason_code: str = "NEW_WORKFLOW",
) -> RootDecision:
    return RootDecision.model_validate(
        {
            "task_relation": task_relation,
            "route": "WORKFLOW",
            "risk": "WRITE",
            "context_policy": {
                "selected_entity": selected_entity,
                "previous_query": "IGNORE",
                "result_set": result_set,
                "active_workflow": active_workflow,
            },
            "confidence": confidence,
            "reason_code": reason_code,
        }
    )


async def test_explicit_customer_query_overrides_misclassified_session_context() -> None:
    selected_customer = EntityRef(
        ref_id="eref_customer_selected",
        resource="customer",
        public_id="cus_00000000000000000000000000000001",
        display_name="广州睿狐科技有限公司",
    )
    previous_query = CRMQuerySpec(
        resource="customer",
        projection=["public_id", "account_name", "city"],
        filters=[CRMFilter(field="city", operator="eq", value="广州")],
    )
    query_executor = RecordingQueryExecutor()
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(RootContextSnapshot(previous_query=previous_query)),
        decision_classifier=StubDecisionClassifier(
            query_decision(
                task_relation="CONTINUE_TASK",
                selected_entity="USE",
                previous_query="USE",
                reason_code="MISCLASSIFIED_CONTEXT_CONTINUATION",
            )
        ),
        query_executor=query_executor,
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=failing_workflow_subgraph(),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_explicit_query_context_override",
            input=TextTurnInput(type="text", text="上海有哪些客户"),
            selected_entity_ref=selected_customer,
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, QueryDispatchResult)
    assert result.decision.task_relation == "NEW_TASK"
    assert result.decision.context_policy == ContextPolicy(
        selected_entity="IGNORE",
        previous_query="IGNORE",
        result_set="IGNORE",
        active_workflow="NONE",
    )
    assert len(query_executor.calls) == 1
    query_request = query_executor.calls[0]
    assert query_request.selected_entity is None
    assert query_request.previous_query is None
    assert query_request.result_set is None


async def test_explicit_follow_up_record_overrides_invalid_model_clarification() -> None:
    workflow_calls: list[object] = []
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=StubDecisionClassifier(
            RootDecision.model_validate(
                {
                    "task_relation": "NEW_TASK",
                    "route": "CLARIFY",
                    "risk": "WRITE",
                    "context_policy": {
                        "selected_entity": "IGNORE",
                        "previous_query": "IGNORE",
                        "result_set": "IGNORE",
                        "active_workflow": "SUSPEND",
                    },
                    "confidence": 0.99,
                    "reason_code": "ACTIVE_WORKFLOW_CONTEXT_MISSING",
                }
            )
        ),
        query_executor=RecordingQueryExecutor(),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=recording_workflow_subgraph(workflow_calls),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_explicit_follow_up_record",
            input=TextTurnInput(
                type="text",
                text=(
                    "微信联系了凡亚信息，技术经理张总反馈项目正在走立项流程；"  # noqa: RUF001
                    "下周三继续跟进立项流程"
                ),
            ),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, WorkflowDispatchResult)
    assert result.decision.task_relation == "NEW_TASK"
    assert result.decision.route == "WORKFLOW"
    assert result.decision.risk == "WRITE"
    assert result.decision.context_policy == ContextPolicy(
        selected_entity="IGNORE",
        previous_query="IGNORE",
        result_set="IGNORE",
        active_workflow="NONE",
    )
    assert result.decision.confidence == 1.0
    assert result.decision.reason_code == "EXPLICIT_FOLLOW_UP_WORKFLOW"
    assert len(workflow_calls) == 1


async def test_normal_follow_up_does_not_resume_pending_confirmation_case() -> None:
    workflow_calls: list[object] = []
    pending_case = PendingCaseContext(
        case_public_id="fuc_" + "1" * 32,
        customer_name="广州凡亚信息科技有限公司",
        customer_aliases=["凡亚信息"],
        task_title="跟进 POC 环境部署情况",
        task_description="确认客户 POC 环境部署进度",
        due_at_text="周四",
        question_text="是否完成该待办？",  # noqa: RUF001
    )
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(RootContextSnapshot(pending_cases=[pending_case])),
        decision_classifier=StubDecisionClassifier(
            workflow_decision(
                task_relation="CONTINUE_TASK",
                active_workflow="RESUME",
                reason_code="MODEL_TRIED_TO_RESUME_PENDING_CASE",
            )
        ),
        query_executor=RecordingQueryExecutor(),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=recording_workflow_subgraph(workflow_calls),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_new_follow_up_with_pending_case",
            input=TextTurnInput(type="text", text="今天联系了凡亚信息，客户反馈项目正在评估"),  # noqa: RUF001
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, WorkflowDispatchResult)
    assert result.decision.pending_case_relation == "NONE"
    assert result.decision.context_policy.active_workflow == "NONE"
    assert workflow_calls[0]["start"] == {
        "kind": "text",
        "text": "今天联系了凡亚信息，客户反馈项目正在评估",  # noqa: RUF001
    }


async def test_model_cannot_turn_an_unrelated_text_turn_into_workflow_resume() -> None:
    workflow_calls: list[object] = []
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=StubDecisionClassifier(
            workflow_decision(
                task_relation="CONTINUE_TASK",
                active_workflow="NONE",
                reason_code="MODEL_TRIED_TO_RESUME_WORKFLOW",
            )
        ),
        query_executor=RecordingQueryExecutor(),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=recording_workflow_subgraph(workflow_calls),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_model_resume_without_explicit_reference",
            input=TextTurnInput(type="text", text="请处理这个客户的跟进情况"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, ClarificationDispatchResult)
    assert result.decision.reason_code == "MODEL_TRIED_TO_RESUME_WORKFLOW"
    assert workflow_calls == []


async def test_text_continuation_cannot_bypass_confirmation_interaction() -> None:
    workflow_ref = WorkflowRef(
        workflow_id="wf_confirmation_waiting",
        interrupt_id="int_confirmation_waiting",
    )
    continuation = WorkflowContinuation(
        root_thread_id="crm_agent_turn:1:1:556:confirmation",
        workflow_ref=workflow_ref,
        parent_checkpoint_id="cp_root_confirmation",
        subgraph_checkpoint_ns="workflow_subgraph:confirmation",
        subgraph_checkpoint_id="cp_subgraph_confirmation",
        waiting_interaction_type="confirmation",
    )
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(
            RootContextSnapshot(
                active_workflow=workflow_ref,
                resumable_workflows=[workflow_ref],
                resumable_workflow_continuations=[continuation],
            )
        ),
        decision_classifier=FailingClassifier(),
        query_executor=RecordingQueryExecutor(),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=failing_workflow_subgraph(),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_text_cannot_confirm_workflow",
            input=TextTurnInput(type="text", text="继续刚才的任务"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, ClarificationDispatchResult)
    assert result.decision.reason_code == "WORKFLOW_CONFIRMATION_REQUIRES_STRUCTURED_ACTION"


async def test_explicit_pending_case_reference_starts_resource_workflow() -> None:
    workflow_calls: list[object] = []
    pending_case = PendingCaseContext(
        case_public_id="fuc_" + "1" * 32,
        customer_name="广州凡亚信息科技有限公司",
        customer_aliases=["凡亚信息"],
        task_title="跟进 POC 环境部署情况",
        task_description="确认客户 POC 环境部署进度",
        due_at_text="周四",
        question_text="是否完成该待办？",  # noqa: RUF001
    )
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(RootContextSnapshot(pending_cases=[pending_case])),
        decision_classifier=FailingClassifier(),
        query_executor=RecordingQueryExecutor(),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=recording_workflow_subgraph(workflow_calls),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_explicit_pending_case",
            input=TextTurnInput(type="text", text="完成凡亚信息的待办"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, WorkflowDispatchResult)
    assert result.decision.pending_case_relation == "EXPLICIT_REFERENCE"
    assert workflow_calls[0]["start"] == {
        "kind": "resource",
        "workflow": "follow_up_task_confirmation",
        "resource_id": pending_case.case_public_id,
    }


async def test_text_resume_clarifies_when_multiple_workflows_are_resumable() -> None:
    first_workflow = WorkflowRef(
        workflow_id="wf_first_waiting",
        interrupt_id="int_first_waiting",
    )
    second_workflow = WorkflowRef(
        workflow_id="wf_second_waiting",
        interrupt_id="int_second_waiting",
    )
    workflow_calls: list[object] = []
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(
            RootContextSnapshot(
                active_workflow=first_workflow,
                resumable_workflows=[first_workflow, second_workflow],
            )
        ),
        decision_classifier=StubDecisionClassifier(
            workflow_decision(
                task_relation="CONTINUE_TASK",
                active_workflow="RESUME",
                reason_code="TEXT_WORKFLOW_RESUME",
            )
        ),
        query_executor=RecordingQueryExecutor(),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=recording_workflow_subgraph(workflow_calls),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_ambiguous_text_resume",
            input=TextTurnInput(type="text", text="继续刚才的任务"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, ClarificationDispatchResult)
    assert result.decision.reason_code == "ACTIVE_WORKFLOW_RESUME_AMBIGUOUS"
    assert workflow_calls == []


async def test_text_resume_clarifies_when_resumable_workflow_index_is_inconsistent() -> None:
    active_workflow = WorkflowRef(
        workflow_id="wf_active_but_not_indexed",
        interrupt_id="int_active_but_not_indexed",
    )
    workflow_calls: list[object] = []
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(
            RootContextSnapshot(active_workflow=active_workflow)
        ),
        decision_classifier=StubDecisionClassifier(
            workflow_decision(
                task_relation="CONTINUE_TASK",
                active_workflow="RESUME",
                reason_code="TEXT_WORKFLOW_RESUME",
            )
        ),
        query_executor=RecordingQueryExecutor(),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=recording_workflow_subgraph(workflow_calls),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_inconsistent_text_resume",
            input=TextTurnInput(type="text", text="继续刚才的任务"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, ClarificationDispatchResult)
    assert result.decision.reason_code == "ACTIVE_WORKFLOW_RESUME_AMBIGUOUS"
    assert workflow_calls == []


async def test_explicit_query_suspends_active_workflow_even_when_model_requests_resume() -> None:
    active_workflow = WorkflowRef(
        workflow_id="wf_active_confirmation",
        interrupt_id="int_active_confirmation",
    )
    query_executor = RecordingQueryExecutor()
    workflow_calls: list[object] = []
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(
            RootContextSnapshot(active_workflow=active_workflow)
        ),
        decision_classifier=StubDecisionClassifier(
            workflow_decision(
                task_relation="CONTINUE_TASK",
                active_workflow="RESUME",
                reason_code="MISCLASSIFIED_WORKFLOW_RESUME",
            )
        ),
        query_executor=query_executor,
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=recording_workflow_subgraph(workflow_calls),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_explicit_query_suspends_workflow",
            input=TextTurnInput(type="text", text="上海有哪些客户"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, QueryDispatchResult)
    assert result.decision.task_relation == "SWITCH_TASK"
    assert result.decision.context_policy.active_workflow == "SUSPEND"
    assert len(query_executor.calls) == 1
    assert workflow_calls == []


async def test_new_city_query_ignores_selected_customer_context() -> None:
    selected_customer = EntityRef(
        ref_id="eref_customer_selected",
        resource="customer",
        public_id="cus_00000000000000000000000000000001",
        display_name="广州睿狐科技有限公司",
    )
    query_executor = RecordingQueryExecutor()
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=StubDecisionClassifier(query_decision(reason_code="NEW_CITY_CUSTOMER_QUERY")),
        query_executor=query_executor,
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=failing_workflow_subgraph(),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_shanghai_customers",
            input=TextTurnInput(type="text", text="上海有哪些客户"),
            selected_entity_ref=selected_customer,
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, QueryDispatchResult)
    assert result.decision.task_relation == "NEW_TASK"
    assert result.decision.context_policy == ContextPolicy(
        selected_entity="IGNORE",
        previous_query="IGNORE",
        result_set="IGNORE",
        active_workflow="NONE",
    )
    assert len(query_executor.calls) == 1
    query_request = query_executor.calls[0]
    assert query_request.text == "上海有哪些客户"
    assert query_request.selected_entity is None
    assert query_request.previous_query is None
    assert query_request.result_set is None


class RecordingStructuredDecisionModel:
    def __init__(self, decision: RootDecision) -> None:
        self.decision = decision
        self.calls: list[object] = []

    async def ainvoke(self, messages: object) -> RootDecision:
        self.calls.append(messages)
        return self.decision


class RecordingDecisionChatModel:
    def __init__(self, structured_model: RecordingStructuredDecisionModel) -> None:
        self.structured_model = structured_model
        self.structured_output_calls: list[tuple[object, dict[str, object]]] = []

    def with_structured_output(
        self,
        schema: object,
        **kwargs: object,
    ) -> RecordingStructuredDecisionModel:
        self.structured_output_calls.append((schema, kwargs))
        return self.structured_model


async def test_root_uses_structured_decision_model_with_authoritative_context() -> None:
    selected_customer = EntityRef(
        ref_id="eref_customer_selected",
        resource="customer",
        public_id="cus_00000000000000000000000000000001",
        display_name="广州睿狐科技有限公司",
    )
    structured_model = RecordingStructuredDecisionModel(query_decision(reason_code="NEW_CITY_CUSTOMER_QUERY"))
    chat_model = RecordingDecisionChatModel(structured_model)
    factory_calls: list[dict[str, object]] = []

    def model_factory(**kwargs: object) -> RecordingDecisionChatModel:
        factory_calls.append(kwargs)
        return chat_model

    query_executor = RecordingQueryExecutor()
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=LangChainRootDecisionClassifier(chat_model_factory=model_factory),
        query_executor=query_executor,
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=failing_workflow_subgraph(),
    )
    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_structured_decision",
            input=TextTurnInput(type="text", text="帮我看看这个客户"),
            selected_entity_ref=selected_customer,
        ),
        runtime=RootRuntimeContext(
            root_model_config=RootDecisionModelConfig(
                api_host="https://ai.example.com/v1",
                api_key="test-key",
                model="test-model",
                temperature=0.0,
            ),
        ),
    )

    assert isinstance(result, QueryDispatchResult)
    assert result.decision.context_policy.selected_entity == "IGNORE"
    assert factory_calls == [
        {
            "model": "test-model",
            "api_key": "test-key",
            "base_url": "https://ai.example.com/v1",
            "temperature": 0.0,
            "max_retries": 0,
        }
    ]
    assert len(structured_model.calls) == 1
    messages = structured_model.calls[0]
    payload = json.loads(messages[1]["content"])
    assert payload["input"] == {"type": "text", "text": "帮我看看这个客户"}
    assert payload["selected_entity_ref"]["display_name"] == "广州睿狐科技有限公司"
    assert payload["context_snapshot"] == {}


async def test_rejected_structured_interaction_returns_typed_failure_without_model_or_workflow() -> None:
    resolver = RecordingInteractionResolver(
        InteractionResolution(status="REJECTED", reason_code="ACTION_ALREADY_CONSUMED")
    )
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=FailingClassifier(),
        query_executor=RecordingQueryExecutor(),
        interaction_resolver=resolver,
        workflow_subgraph=failing_workflow_subgraph(),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_consumed_interaction",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_consumed",
                values={"choice": "cancel"},
            ),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, FailureDispatchResult)
    assert result.decision is None
    assert result.error.code == "ACTION_ALREADY_CONSUMED"
    assert result.error.retryable is False
    assert len(resolver.calls) == 1


async def test_invalid_structured_interaction_returns_action_invalid_failure() -> None:
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=FailingClassifier(),
        query_executor=RecordingQueryExecutor(),
        interaction_resolver=RecordingInteractionResolver(
            InteractionResolution(status="REJECTED", reason_code="ACTION_VALUES_INVALID")
        ),
        workflow_subgraph=failing_workflow_subgraph(),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_invalid_interaction",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_active",
                values={"choice": "unsupported"},
            ),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, FailureDispatchResult)
    assert result.error.code == "ACTION_INVALID"
    assert result.error.retryable is False


async def test_claimed_interaction_failure_preserves_action_claim_identity() -> None:
    continuation = WorkflowContinuation(
        root_thread_id="crm_agent_turn:test",
        workflow_ref=WorkflowRef(
            workflow_id="wf_customer_follow_up",
            interrupt_id="intr_customer_choice",
        ),
        parent_checkpoint_id="missing_parent_checkpoint",
        subgraph_checkpoint_ns="workflow:customer_follow_up",
        subgraph_checkpoint_id="missing_child_checkpoint",
    )
    action_id = "act_claimed_interaction"
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=FailingClassifier(),
        query_executor=RecordingQueryExecutor(),
        interaction_resolver=RecordingInteractionResolver(
            InteractionResolution(
                status="RESOLVED",
                reason_code="STRUCTURED_WORKFLOW_CONTINUATION",
                resolved_action=ResolvedAgentAction(
                    action_id=action_id,
                    action_type="submit_interaction",
                    continuation=continuation,
                    claim_outcome="ACQUIRED",
                    resume_payload={"choice": "cus_shanghai_1"},
                ),
            )
        ),
        workflow_subgraph=failing_workflow_subgraph(),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_claimed_interaction_failure",
            input=InteractionTurnInput(
                type="interaction",
                action_id=action_id,
                values={"choice": "cus_shanghai_1"},
            ),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, FailureDispatchResult)
    assert result.error.code in {
        "WORKFLOW_CHECKPOINT_UNAVAILABLE",
        "WORKFLOW_EXECUTION_FAILED",
    }
    assert result.action_claim_id == action_id


class RecordingCRMQueryAgent:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object, object]] = []

    async def run(self, request: object, tool_context: object, model_config: object) -> CRMQueryAgentResult:
        self.calls.append((request, tool_context, model_config))
        return CRMQueryAgentResult(
            response=CRMQueryAgentResponse(
                status="ANSWERED",
                answer="找到了 2 家上海客户",
                evidence_refs=["query_customers"],
            ),
            trace=CRMQueryAgentTrace(
                model="test-model",
                tool_names=["query_customers"],
                tool_call_count=1,
                total_entity_count=2,
                elapsed_ms=3,
                stop_reason="COMPLETED",
            ),
        )


async def test_root_query_route_uses_existing_stateless_query_agent_contract() -> None:
    query_agent = RecordingCRMQueryAgent()
    query_model_config = CRMQueryAgentModelConfig(
        api_host="https://ai.example.com/v1",
        api_key="test-key",
        model="test-model",
        temperature=0.0,
    )
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=StubDecisionClassifier(query_decision(reason_code="NEW_CITY_CUSTOMER_QUERY")),
        query_executor=CRMQueryAgentExecutor(query_agent=query_agent),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=failing_workflow_subgraph(),
    )
    db = object()

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=9,
            user_id=18,
            session_id=556,
            client_request_id="req_real_query_adapter",
            input=TextTurnInput(type="text", text="上海有哪些客户"),
        ),
        runtime=RootRuntimeContext(
            permission_codes=frozenset({"customer:read"}),
            db=db,
            authorization="Bearer test-token",
            query_model_config=query_model_config,
        ),
    )

    assert isinstance(result, QueryDispatchResult)
    assert len(query_agent.calls) == 1
    request, tool_context, received_model_config = query_agent.calls[0]
    assert request.user_message == "上海有哪些客户"
    assert request.previous_query is None
    assert request.entity_refs == []
    assert tool_context.db is db
    assert tool_context.team_id == 9
    assert tool_context.user_id == 18
    assert tool_context.session_id == 556
    assert tool_context.authorization == "Bearer test-token"
    assert tool_context.permission_codes == frozenset({"customer:read"})
    assert received_model_config == query_model_config


async def test_result_set_ordinal_binds_only_the_referenced_customer() -> None:
    first_customer = EntityRef(
        ref_id="eref_customer_first",
        resource="customer",
        public_id="cus_00000000000000000000000000000011",
        display_name="上海甲客户",
        result_set_id="rs_shanghai",
    )
    second_customer = EntityRef(
        ref_id="eref_customer_second",
        resource="customer",
        public_id="cus_00000000000000000000000000000012",
        display_name="上海乙客户",
        result_set_id="rs_shanghai",
    )
    query_executor = RecordingQueryExecutor()
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(
            RootContextSnapshot(
                result_set=ResultSetContext(
                    result_set_id="rs_shanghai",
                    ordered_entity_refs=[first_customer, second_customer],
                )
            )
        ),
        decision_classifier=StubDecisionClassifier(
            query_decision(
                task_relation="CONTINUE_TASK",
                result_set="USE",
                reason_code="RESULT_SET_ORDINAL_QUERY",
            )
        ),
        query_executor=query_executor,
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=failing_workflow_subgraph(),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_result_ordinal",
            input=TextTurnInput(type="text", text="第一个客户最近发生了什么"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, QueryDispatchResult)
    assert len(query_executor.calls) == 1
    query_request = query_executor.calls[0]
    assert query_request.selected_entity == first_customer
    assert query_request.result_set is None


async def test_result_set_ordinal_binds_only_the_referenced_customer_to_workflow() -> None:
    first_customer = EntityRef(
        ref_id="eref_customer_first",
        resource="customer",
        public_id="cus_00000000000000000000000000000011",
        display_name="上海甲客户",
        result_set_id="rs_shanghai",
    )
    second_customer = EntityRef(
        ref_id="eref_customer_second",
        resource="customer",
        public_id="cus_00000000000000000000000000000012",
        display_name="上海乙客户",
        result_set_id="rs_shanghai",
    )
    workflow_calls: list[object] = []
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(
            RootContextSnapshot(
                result_set=ResultSetContext(
                    result_set_id="rs_shanghai",
                    ordered_entity_refs=[first_customer, second_customer],
                )
            )
        ),
        decision_classifier=StubDecisionClassifier(
            workflow_decision(
                task_relation="CONTINUE_TASK",
                result_set="USE",
                reason_code="RESULT_SET_ORDINAL_WORKFLOW",
            )
        ),
        query_executor=RecordingQueryExecutor(),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=recording_workflow_subgraph(workflow_calls),
    )

    await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_result_ordinal_workflow",
            input=TextTurnInput(type="text", text="给第一个客户创建下周跟进任务"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert len(workflow_calls) == 1
    workflow_input = workflow_calls[0]
    assert workflow_input["selected_entity"] == first_customer.model_dump(mode="json")


async def test_out_of_range_result_set_ordinal_clarifies_before_workflow() -> None:
    first_customer = EntityRef(
        ref_id="eref_customer_first",
        resource="customer",
        public_id="cus_00000000000000000000000000000011",
        display_name="上海甲客户",
        result_set_id="rs_shanghai",
    )
    second_customer = EntityRef(
        ref_id="eref_customer_second",
        resource="customer",
        public_id="cus_00000000000000000000000000000012",
        display_name="上海乙客户",
        result_set_id="rs_shanghai",
    )
    workflow_calls: list[object] = []
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(
            RootContextSnapshot(
                result_set=ResultSetContext(
                    result_set_id="rs_shanghai",
                    ordered_entity_refs=[first_customer, second_customer],
                )
            )
        ),
        decision_classifier=StubDecisionClassifier(
            workflow_decision(
                task_relation="CONTINUE_TASK",
                result_set="USE",
                reason_code="RESULT_SET_ORDINAL_WORKFLOW",
            )
        ),
        query_executor=RecordingQueryExecutor(),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=recording_workflow_subgraph(workflow_calls),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_result_ordinal_workflow_out_of_range",
            input=TextTurnInput(type="text", text="给第三个客户创建下周跟进任务"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, ClarificationDispatchResult)
    assert result.decision.route == "CLARIFY"
    assert result.decision.reason_code == "RESULT_SET_REFERENCE_OUT_OF_RANGE"
    assert result.clarification.reason_code == "RESULT_SET_REFERENCE_OUT_OF_RANGE"
    assert workflow_calls == []


async def test_write_intent_cannot_be_executed_as_read_only_query() -> None:
    query_executor = RecordingQueryExecutor()
    workflow_calls: list[object] = []
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=StubDecisionClassifier(query_decision(reason_code="MISCLASSIFIED_READ_QUERY")),
        query_executor=query_executor,
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=recording_workflow_subgraph(workflow_calls),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_mixed_write",
            input=TextTurnInput(
                type="text",
                text="查询上海客户后, 顺便帮我把负责人改成张三",
            ),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, ClarificationDispatchResult)
    assert result.decision.reason_code == "WRITE_INTENT_ROUTE_MISMATCH"
    assert query_executor.calls == []
    assert workflow_calls == []


async def test_opportunity_stage_write_intent_cannot_be_routed_to_query() -> None:
    query_executor = RecordingQueryExecutor()
    workflow_calls: list[object] = []
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=StubDecisionClassifier(query_decision(reason_code="MISCLASSIFIED_OPPORTUNITY_STAGE_QUERY")),
        query_executor=query_executor,
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=recording_workflow_subgraph(workflow_calls),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_move_opportunity_stage_misclassified",
            input=TextTurnInput(
                type="text",
                text="把星云企业版采购推进到方案评估",
            ),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, ClarificationDispatchResult)
    assert result.decision.reason_code == "WRITE_INTENT_ROUTE_MISMATCH"
    assert query_executor.calls == []
    assert workflow_calls == []


async def test_dispatch_loads_authoritative_context_inside_root() -> None:
    context_resolver = StaticContextResolver(RootContextSnapshot())
    query_executor = RecordingQueryExecutor()
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=context_resolver,
        decision_classifier=StubDecisionClassifier(query_decision()),
        query_executor=query_executor,
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=failing_workflow_subgraph(),
    )
    turn = RootTurnInput(
        team_id=1,
        user_id=1,
        session_id=556,
        client_request_id="req_root_context",
        input=TextTurnInput(type="text", text="上海有哪些客户"),
    )

    result = await orchestrator.dispatch(turn, runtime=RootRuntimeContext())

    assert isinstance(result, QueryDispatchResult)
    assert context_resolver.calls == [turn]


async def test_follow_up_query_inherits_previous_canonical_query() -> None:
    previous_query = CRMQuerySpec(
        resource="customer",
        projection=["public_id", "customer_name", "city"],
        filters=[CRMFilter(field="city", operator="eq", value="上海")],
    )
    query_executor = RecordingQueryExecutor()
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(RootContextSnapshot(previous_query=previous_query)),
        decision_classifier=StubDecisionClassifier(
            query_decision(
                task_relation="CONTINUE_TASK",
                previous_query="USE",
                reason_code="FOLLOW_UP_QUERY",
            )
        ),
        query_executor=query_executor,
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=failing_workflow_subgraph(),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_follow_up_query",
            input=TextTurnInput(type="text", text="重点客户呢"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, QueryDispatchResult)
    assert query_executor.calls[0].previous_query == previous_query


class UnavailableDecisionClassifier:
    async def classify(self, **kwargs: object) -> RootDecision:
        from app.services.agent.orchestrator import RootDecisionModelUnavailableError

        raise RootDecisionModelUnavailableError("decision model unavailable")


async def test_explicit_query_bypasses_unavailable_decision_model() -> None:
    query_executor = RecordingQueryExecutor()
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=UnavailableDecisionClassifier(),
        query_executor=query_executor,
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=failing_workflow_subgraph(),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_explicit_query_without_root_model",
            input=TextTurnInput(type="text", text="上海有哪些客户"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, QueryDispatchResult)
    assert result.decision.reason_code == "EXPLICIT_INDEPENDENT_READ_QUERY"
    assert len(query_executor.calls) == 1


async def test_explicit_follow_up_bypasses_unavailable_decision_model() -> None:
    workflow_calls: list[object] = []
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=UnavailableDecisionClassifier(),
        query_executor=RecordingQueryExecutor(),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=recording_workflow_subgraph(workflow_calls),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_explicit_follow_up_without_root_model",
            input=TextTurnInput(
                type="text",
                text=(
                    "微信联系了凡亚信息，技术经理张总反馈项目正在走立项流程；"  # noqa: RUF001
                    "下周三继续跟进立项流程"
                ),
            ),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, WorkflowDispatchResult)
    assert result.decision.reason_code == "EXPLICIT_FOLLOW_UP_WORKFLOW"
    assert len(workflow_calls) == 1


async def test_ambiguous_intent_with_unavailable_decision_model_returns_typed_failure() -> None:
    from app.services.agent.orchestrator import FailureDispatchResult

    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=UnavailableDecisionClassifier(),
        query_executor=RecordingQueryExecutor(),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=failing_workflow_subgraph(),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_model_unavailable",
            input=TextTurnInput(type="text", text="帮我处理一下这个"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, FailureDispatchResult)
    assert result.decision is None
    assert result.error.code == "ROOT_DECISION_MODEL_UNAVAILABLE"
    assert result.error.retryable is True


class InvalidStructuredDecisionModel:
    async def ainvoke(self, messages: object) -> dict[str, object]:
        return {"route": "QUERY"}


async def test_invalid_structured_decision_returns_typed_failure() -> None:
    from app.services.agent.orchestrator import FailureDispatchResult

    chat_model = RecordingDecisionChatModel(InvalidStructuredDecisionModel())
    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=LangChainRootDecisionClassifier(chat_model_factory=lambda **kwargs: chat_model),
        query_executor=RecordingQueryExecutor(),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=failing_workflow_subgraph(),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_invalid_decision_output",
            input=TextTurnInput(type="text", text="帮我看看这个"),
        ),
        runtime=RootRuntimeContext(
            root_model_config=RootDecisionModelConfig(
                api_host="https://ai.example.com/v1",
                api_key="test-key",
                model="test-model",
            )
        ),
    )

    assert isinstance(result, FailureDispatchResult)
    assert result.error.code == "ROOT_DECISION_INVALID_OUTPUT"
    assert result.error.retryable is False


class FailingQueryExecutor:
    async def execute(self, request: object, *, runtime: object) -> CRMQueryAgentResult:
        raise RuntimeError("query backend failed")


class TypedFailingQueryExecutor:
    async def execute(self, request: object, *, runtime: object) -> CRMQueryAgentResult:
        raise CRMQueryAgentExecutionError(
            QueryError(
                code="QUERY_INVALID",
                message="internal query parser detail",
                retryable=False,
            )
        )


async def test_query_execution_error_returns_failure_with_root_decision() -> None:
    from app.services.agent.orchestrator import FailureDispatchResult

    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=StubDecisionClassifier(query_decision()),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=failing_workflow_subgraph(),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_query_failure",
            input=TextTurnInput(type="text", text="上海有哪些客户"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, FailureDispatchResult)
    assert result.decision is not None
    assert result.decision.route == "QUERY"
    assert result.error.code == "QUERY_EXECUTION_FAILED"
    assert result.error.retryable is True


async def test_typed_query_execution_error_preserves_code_and_hides_internal_message() -> None:
    from app.services.agent.orchestrator import FailureDispatchResult

    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=StubDecisionClassifier(query_decision()),
        query_executor=TypedFailingQueryExecutor(),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=failing_workflow_subgraph(),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_typed_query_failure",
            input=TextTurnInput(type="text", text="上海有哪些客户"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, FailureDispatchResult)
    assert result.error.code == "QUERY_INVALID"
    assert result.error.message == "查询条件无法识别，请换一种说法或补充筛选条件。"  # noqa: RUF001
    assert result.error.message != "internal query parser detail"
    assert result.error.retryable is False


class UnavailableContextResolver:
    async def resolve(self, **kwargs: object) -> RootContextSnapshot:
        from app.services.agent.orchestrator import RootContextUnavailableError

        raise RootContextUnavailableError("context storage unavailable")


async def test_context_storage_unavailable_returns_typed_failure() -> None:
    from app.services.agent.orchestrator import FailureDispatchResult

    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=UnavailableContextResolver(),
        decision_classifier=FailingClassifier(),
        query_executor=RecordingQueryExecutor(),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=failing_workflow_subgraph(),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_context_unavailable",
            input=TextTurnInput(type="text", text="上海有哪些客户"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, FailureDispatchResult)
    assert result.error.code == "ROOT_CONTEXT_UNAVAILABLE"
    assert result.error.retryable is True


class UnavailableInteractionResolver:
    async def resolve(self, **kwargs: object) -> InteractionResolution:
        from app.services.agent.orchestrator import InteractionResolutionUnavailableError

        raise InteractionResolutionUnavailableError("action storage unavailable")


class UnconfiguredQueryExecutor:
    async def execute(self, request: object, *, runtime: object) -> CRMQueryAgentResult:
        from app.services.agent.orchestrator import QueryExecutionConfigurationError

        raise QueryExecutionConfigurationError("query model config missing")


async def test_query_configuration_error_returns_non_retryable_failure() -> None:
    from app.services.agent.orchestrator import FailureDispatchResult

    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=StubDecisionClassifier(query_decision()),
        query_executor=UnconfiguredQueryExecutor(),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=failing_workflow_subgraph(),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_query_unconfigured",
            input=TextTurnInput(type="text", text="上海有哪些客户"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, FailureDispatchResult)
    assert result.decision is not None
    assert result.error.code == "QUERY_EXECUTION_NOT_CONFIGURED"
    assert result.error.retryable is False


def unavailable_checkpoint_subgraph():
    async def fail(_state: WorkflowTestState) -> WorkflowTestState:
        from app.services.agent.orchestrator import WorkflowCheckpointUnavailableError

        raise WorkflowCheckpointUnavailableError("checkpoint unavailable")

    graph = StateGraph(WorkflowTestState)
    graph.add_node("fail", fail)
    graph.add_edge(START, "fail")
    graph.add_edge("fail", END)
    return graph.compile()


async def test_workflow_checkpoint_unavailable_returns_typed_failure() -> None:
    from app.services.agent.orchestrator import FailureDispatchResult

    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=StubDecisionClassifier(workflow_decision()),
        query_executor=RecordingQueryExecutor(),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=unavailable_checkpoint_subgraph(),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_checkpoint_unavailable",
            input=TextTurnInput(type="text", text="帮我创建一个跟进任务"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, FailureDispatchResult)
    assert result.error.code == "WORKFLOW_CHECKPOINT_UNAVAILABLE"
    assert result.error.retryable is True


def unavailable_workflow_subgraph():
    async def fail(_state: WorkflowTestState) -> WorkflowTestState:
        from app.services.agent.orchestrator import WorkflowExecutionFailedError

        raise WorkflowExecutionFailedError("workflow execution failed")

    graph = StateGraph(WorkflowTestState)
    graph.add_node("fail", fail)
    graph.add_edge(START, "fail")
    graph.add_edge("fail", END)
    return graph.compile()


async def test_workflow_execution_error_returns_typed_failure() -> None:
    from app.services.agent.orchestrator import FailureDispatchResult

    orchestrator = RootOrchestrator(
        checkpointer=InMemorySaver(),
        context_resolver=StaticContextResolver(),
        decision_classifier=StubDecisionClassifier(workflow_decision()),
        query_executor=RecordingQueryExecutor(),
        interaction_resolver=FailingInteractionResolver(),
        workflow_subgraph=unavailable_workflow_subgraph(),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=1,
            session_id=556,
            client_request_id="req_workflow_failure",
            input=TextTurnInput(type="text", text="帮我创建一个跟进任务"),
        ),
        runtime=RootRuntimeContext(),
    )

    assert isinstance(result, FailureDispatchResult)
    assert result.error.code == "WORKFLOW_EXECUTION_FAILED"
    assert result.error.retryable is True

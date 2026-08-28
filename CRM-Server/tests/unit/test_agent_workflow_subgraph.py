"""Production Workflow subgraph behavior through the Root public seam."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    create_engine,
    text,
)
from sqlalchemy.pool import StaticPool

from app.services.agent.checkpoint_serde_inspection import CheckpointSerdeInspector
from app.services.agent.durable_work_contracts import CustomerActivityDurableWorkReceipt
from app.services.agent.guardrails import AgentToolGuardrailError
from app.services.agent.input import AgentTurnInput
from app.services.agent.orchestrator import (
    ContextPolicy,
    InteractionResolution,
    InteractionTurnInput,
    ResolvedAgentAction,
    RootContextSnapshot,
    RootDecision,
    RootOrchestrator,
    RootRuntimeContext,
    RootTurnInput,
    TextTurnInput,
    WorkflowCancelledResult,
    WorkflowCompletedResult,
    WorkflowContinuation,
    WorkflowDispatchResult,
    WorkflowFailedResult,
    WorkflowRef,
    WorkflowTriggerTurnInput,
    WorkflowWaitingResult,
)
from app.services.agent.orchestrator.errors import WorkflowExecutionFailedError
from app.services.agent.query import (
    CRMQueryAgentResponse,
    CRMQueryAgentResult,
    CRMQueryAgentTrace,
    EntityRef,
)
from app.services.agent.schemas import AgentSemanticParseResult
from app.services.agent.semantic import AgentSemanticParseEnvelope
from app.services.agent.tools.base import AgentToolContext, AgentToolResult
from app.services.agent.workflow.contracts import (
    WorkflowActionPlan,
    WorkflowAuthorizationScope,
    WorkflowCommand,
    WorkflowCommandBinding,
    WorkflowInteraction,
    WorkflowInteractionOption,
    WorkflowRuntimeContext,
    WorkflowTurnInput,
)
from app.services.agent.workflow.execution import CRMWorkflowEffectExecutor
from app.services.agent.workflow.graph import build_workflow_subgraph
from app.services.agent.workflow.planning import CRMWorkflowPlanner
from app.services.agent.workflow.resources import (
    CustomerMemberCandidate,
    CustomerMemberResolution,
    FollowUpTaskCandidate,
    FollowUpTaskConfirmationCaseCandidate,
    FollowUpTaskConfirmationCaseResolution,
    FollowUpTaskResolution,
    OpportunityStageCandidate,
    OpportunityStageResolution,
    OpportunityStageTransitionStep,
    ProcurementMethodCandidate,
    ProcurementMethodResolution,
)
from app.services.customer_activity_ai.checkpointer import SQLAlchemyCheckpointSaver

if TYPE_CHECKING:
    from collections.abc import Callable

    from langgraph.checkpoint.base import BaseCheckpointSaver


class JsonSafeCheckpointSerializer(JsonPlusSerializer):
    """Reject application-specific constructors in durable graph state."""

    def dumps_typed(self, obj: object) -> tuple[str, bytes]:
        serialized = super().dumps_typed(obj)
        inspector = CheckpointSerdeInspector()
        inspector.loads_typed(serialized)
        if inspector.custom_type_occurrences:
            raise AssertionError(f"checkpoint contains custom constructors: {inspector.custom_type_occurrences}")
        return serialized


def json_safe_checkpointer() -> InMemorySaver:
    return InMemorySaver(
        serde=JsonSafeCheckpointSerializer(allowed_msgpack_modules=None),
    )


def sql_checkpointer() -> SQLAlchemyCheckpointSaver:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata = MetaData()
    Table(
        "crm_langgraph_checkpoints",
        metadata,
        Column("thread_id", String(191), primary_key=True),
        Column("checkpoint_ns", String(191), primary_key=True, default=""),
        Column("checkpoint_id", String(191), primary_key=True),
        Column("parent_checkpoint_id", String(191)),
        Column("checkpoint_type", String(100), nullable=False),
        Column("checkpoint_blob", LargeBinary, nullable=False),
        Column("metadata_type", String(100), nullable=False),
        Column("metadata_blob", LargeBinary, nullable=False),
        Column("created_time", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    Table(
        "crm_langgraph_checkpoint_blobs",
        metadata,
        Column("thread_id", String(191), primary_key=True),
        Column("checkpoint_ns", String(191), primary_key=True),
        Column("channel", String(191), primary_key=True),
        Column("version", String(191), primary_key=True),
        Column("serde_type", String(100), nullable=False),
        Column("blob", LargeBinary, nullable=False),
        Column("created_time", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    Table(
        "crm_langgraph_checkpoint_writes",
        metadata,
        Column("thread_id", String(191), primary_key=True),
        Column("checkpoint_ns", String(191), primary_key=True),
        Column("checkpoint_id", String(191), primary_key=True),
        Column("task_id", String(191), primary_key=True),
        Column("write_idx", Integer, primary_key=True),
        Column("task_path", String(255), nullable=False, default=""),
        Column("channel", String(191), nullable=False),
        Column("serde_type", String(100), nullable=False),
        Column("blob", LargeBinary, nullable=False),
        Column("created_time", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    metadata.create_all(engine)
    return SQLAlchemyCheckpointSaver(engine)


CUSTOMER_REF = EntityRef(
    ref_id="eref_customer_cus_shanghai_001",
    resource="customer",
    public_id="cus_shanghai_001",
    display_name="上海星云科技有限公司",
)


class EmptyContextResolver:
    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        runtime: RootRuntimeContext,
    ) -> RootContextSnapshot:
        return RootContextSnapshot()


class ActiveWorkflowContextResolver:
    def __init__(self) -> None:
        self.active_workflow: WorkflowRef | None = None

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        runtime: RootRuntimeContext,
    ) -> RootContextSnapshot:
        active_workflow = self.active_workflow
        return RootContextSnapshot(
            active_workflow=active_workflow,
            resumable_workflows=([active_workflow] if active_workflow is not None else []),
        )


class CreateFollowUpDecisionClassifier:
    async def classify(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> RootDecision:
        return RootDecision(
            task_relation="NEW_TASK",
            route="WORKFLOW",
            risk="WRITE",
            context_policy=ContextPolicy(
                selected_entity="USE",
                previous_query="IGNORE",
                result_set="IGNORE",
                active_workflow="NONE",
            ),
            confidence=1.0,
            reason_code="CREATE_FOLLOW_UP_TASK",
        )


class FailingQueryExecutor:
    async def execute(self, request: object, *, runtime: object) -> CRMQueryAgentResult:
        raise AssertionError("Workflow turn must not execute Query Agent")


class CanonicalConfirmationResolver:
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
                action_id="act_confirm_create_follow_up",
                action_type="submit_interaction",
                continuation=self.continuation,
                claim_outcome="ACQUIRED",
                resume_payload=AgentTurnInput.confirm(source="web").model_dump(mode="json"),
            ),
        )


class CanonicalRejectionResolver:
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
                action_id="act_reject_create_follow_up",
                action_type="submit_interaction",
                continuation=self.continuation,
                claim_outcome="ACQUIRED",
                resume_payload=AgentTurnInput.reject(source="web").model_dump(mode="json"),
            ),
        )


class FakeSemanticParser:
    def __init__(self, *, intent_confidence: float = 0.99) -> None:
        self.intent_confidence = intent_confidence

    async def parse_with_metadata(
        self,
        db: object,
        *,
        team_id: int,
        user_message: str,
        memory: object = None,
        current_date: object = None,
    ) -> AgentSemanticParseEnvelope:
        assert team_id == 1
        assert user_message == "为上海星云科技创建跟进任务,内容是确认技术评估结论,下周三上午10点跟进"
        return AgentSemanticParseEnvelope(
            result=AgentSemanticParseResult.model_validate(
                {
                    "intent": "CUSTOMER_ACTIVITY",
                    "intent_confidence": self.intent_confidence,
                    "customer": {
                        "name_text": CUSTOMER_REF.display_name,
                        "confidence": 0.99,
                        "resolution_source": "EXPLICIT",
                    },
                    "follow_up": {
                        "content": "确认技术评估结论",
                        "method": "电话",
                        "next_follow_time_text": "下周三上午10点",
                        "next_follow_time": {
                            "raw_text": "下周三上午10点",
                            "kind": "RELATIVE_WEEKDAY",
                            "direction": "next",
                            "weekday": 3,
                            "hour": 10,
                            "minute": 0,
                            "confidence": 0.99,
                        },
                    },
                }
            ),
            parse_source="langchain_structured_output",
            model="test-model",
        )


class FixedTemporalResolver:
    def resolve_follow_up_time(self, expression: object, *, base_datetime: datetime | None = None) -> str:
        assert base_datetime == datetime(2026, 8, 23, 9, 0, 0)
        return "2026-08-26T10:00:00"

    def resolve_date(
        self,
        expression: object,
        *,
        base_datetime: datetime | None = None,
    ) -> str | None:
        assert base_datetime == datetime(2026, 8, 23, 9, 0, 0)
        if expression is None:
            return None
        return "2026-09-30"


class CapturingToolRegistry:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(
        self,
        name: str,
        context: object,
        payload: dict[str, object],
        *,
        policy: object,
    ) -> AgentToolResult:
        self.calls.append(
            {
                "name": name,
                "context": context,
                "payload": payload,
                "policy": policy,
            }
        )
        result_ids = {
            "create_lead": "lead_001",
            "create_customer": "cust_001",
            "create_lead_follow_up": "lfu_001",
            "create_customer_activity": "actv_001",
        }
        return AgentToolResult(
            tool_name=name,
            success=True,
            data={"id": result_ids.get(name, "resource_001")},
            durable_work=(
                CustomerActivityDurableWorkReceipt(
                    activity_id=241,
                    post_commit_job_public_id="pcj_workflow_001",
                    customer_intelligence_request_id="cir_workflow_001",
                ),
            )
            if name == "create_customer_activity"
            else (),
        )


class RaisingToolRegistry:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def execute(
        self,
        name: str,
        context: object,
        payload: dict[str, object],
        *,
        policy: object,
    ) -> AgentToolResult:
        raise self.error


class ResolvedExplicitWorkflowCustomerResolver:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def resolve(
        self,
        *,
        customer_lookup_name: str | None,
        trusted_context_customer: EntityRef | None,
        selected_customer_id: str | None,
        authorization: str,
    ) -> object:
        self.calls.append(
            {
                "customer_lookup_name": customer_lookup_name,
                "trusted_context_customer": trusted_context_customer,
                "selected_customer_id": selected_customer_id,
                "authorization": authorization,
            }
        )
        return SimpleNamespace(
            status="RESOLVED",
            customer=SimpleNamespace(
                customer_id="cus_fanya_001",
                customer_name="广州凡亚信息科技有限公司",
            ),
            candidates=(),
        )


class ExplicitOnlyWorkflowCustomerResolver:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def resolve(
        self,
        *,
        customer_lookup_name: str | None,
        trusted_context_customer: EntityRef | None,
        selected_customer_id: str | None,
        authorization: str,
    ) -> object:
        self.calls.append(
            {
                "customer_lookup_name": customer_lookup_name,
                "trusted_context_customer": trusted_context_customer,
                "selected_customer_id": selected_customer_id,
                "authorization": authorization,
            }
        )
        if customer_lookup_name is None:
            return SimpleNamespace(status="MISSING", customer=None, candidates=())
        return SimpleNamespace(
            status="RESOLVED",
            customer=SimpleNamespace(
                customer_id="cus_fanya_001",
                customer_name="广州凡亚信息科技有限公司",
            ),
            candidates=(),
        )


class NotFoundExplicitWorkflowCustomerResolver:
    def __init__(self) -> None:
        self.calls: list[str | None] = []

    async def resolve(
        self,
        *,
        customer_lookup_name: str | None,
        trusted_context_customer: EntityRef | None,
        selected_customer_id: str | None,
        authorization: str,
    ) -> object:
        self.calls.append(customer_lookup_name)
        return SimpleNamespace(status="NOT_FOUND", customer=None, candidates=())


class ContextWorkflowCustomerResolver:
    """Deterministic resolver for tests whose explicit text names the selected page customer."""

    async def resolve(
        self,
        *,
        customer_lookup_name: str | None,
        trusted_context_customer: EntityRef | None,
        selected_customer_id: str | None,
        authorization: str,
    ) -> object:
        assert authorization == "Bearer test-token"
        assert trusted_context_customer is not None
        assert trusted_context_customer.resource == "customer"
        assert customer_lookup_name in {None, trusted_context_customer.display_name}
        assert selected_customer_id in {None, trusted_context_customer.public_id}
        return SimpleNamespace(
            status="RESOLVED",
            customer=SimpleNamespace(
                customer_id=trusted_context_customer.public_id,
                customer_name=trusted_context_customer.display_name,
            ),
            candidates=(),
        )


async def test_customer_lookup_name_is_resolved_without_page_selected_entity() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CUSTOMER_ACTIVITY",
                "intent_confidence": 0.99,
                "customer": {
                    "name_text": "凡亚信息",
                    "confidence": 0.99,
                    "resolution_source": "EXPLICIT",
                },
                "follow_up": {
                    "content": "技术经理张总反馈项目正在走立项流程",
                    "method": "微信",
                    "next_action": "继续跟进立项流程",
                    "next_follow_time_text": "下周三",
                    "next_follow_time": {
                        "raw_text": "下周三",
                        "kind": "RELATIVE_WEEKDAY",
                        "direction": "next",
                        "weekday": 3,
                        "confidence": 0.99,
                    },
                },
            }
        )
    )
    customer_resolver = ResolvedExplicitWorkflowCustomerResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateStandaloneWriteDecisionClassifier(
            reason_code="CREATE_CUSTOMER_ACTIVITY"
        ),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=CanonicalConfirmationResolver(),
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
                customer_resolver=customer_resolver,
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=CapturingToolRegistry()),
        ),
    )

    progress_events = []
    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=850,
            client_request_id="req_explicit_customer_without_page_context",
            input=TextTurnInput(
                type="text",
                text=(
                    "微信联系了凡亚信息，技术经理张总反馈项目正在走立项流程；"
                    "下周三再继续跟进立项流程"
                ),
            ),
        ),
        runtime=RootRuntimeContext(
            db=object(),
            authorization="Bearer test-token",
            metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
        ),
        on_progress=progress_events.append,
    )

    assert isinstance(result, WorkflowDispatchResult)
    assert isinstance(result.workflow_result, WorkflowCompletedResult)
    assert result.workflow_result.assistant_text == "已记录广州凡亚信息科技有限公司的本次跟进。"
    progress_snapshots = [
        [(step.key, step.status) for step in progress.steps]
        for progress in progress_events
    ]
    assert [("understand_request", "RUNNING")] in progress_snapshots
    assert [
        ("understand_request", "COMPLETED"),
        ("prepare_plan", "RUNNING"),
    ] in progress_snapshots
    assert any(snapshot[-1] == ("execute_action", "RUNNING") for snapshot in progress_snapshots)
    assert progress_snapshots[-1][-2:] == [
        ("execute_action", "COMPLETED"),
        ("prepare_result", "COMPLETED"),
    ]
    assert customer_resolver.calls == [
        {
            "customer_lookup_name": "凡亚信息",
            "trusted_context_customer": None,
            "selected_customer_id": None,
            "authorization": "Bearer test-token",
        }
    ]


async def test_contact_workflow_uses_the_same_explicit_customer_resolution_seam() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CREATE_CONTACT",
                "intent_confidence": 0.99,
                "customer": {
                    "name_text": "凡亚信息",
                    "confidence": 0.99,
                    "resolution_source": "EXPLICIT",
                },
                "contact": {
                    "name": "张总",
                    "position": "技术经理",
                    "mobile": "13800138000",
                    "gender": "1",
                },
            }
        )
    )
    customer_resolver = ResolvedExplicitWorkflowCustomerResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateStandaloneWriteDecisionClassifier(reason_code="CREATE_CONTACT"),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=CanonicalConfirmationResolver(),
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
                customer_resolver=customer_resolver,
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=CapturingToolRegistry()),
        ),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=851,
            client_request_id="req_contact_explicit_customer",
            input=TextTurnInput(type="text", text="给凡亚信息创建联系人张总，技术经理，13800138000"),
        ),
        runtime=RootRuntimeContext(
            db=object(),
            authorization="Bearer test-token",
            metadata={"current_datetime": datetime(2026, 8, 24, 9, 0, 0)},
        ),
    )

    assert isinstance(result, WorkflowDispatchResult)
    assert isinstance(result.workflow_result, WorkflowWaitingResult)
    assert result.workflow_result.interaction.business_action == "create_contact"
    assert "广州凡亚信息科技有限公司" in result.workflow_result.interaction.prompt


class AmbiguousThenSelectedWorkflowCustomerResolver:
    def __init__(self) -> None:
        self.calls: list[str | None] = []
        self.candidates = (
            SimpleNamespace(
                customer_id="cus_fanya_guangzhou",
                customer_name="广州凡亚信息科技有限公司",
                city="广州",
            ),
            SimpleNamespace(
                customer_id="cus_fanya_shenzhen",
                customer_name="深圳凡亚信息科技有限公司",
                city="深圳",
            ),
        )

    async def resolve(
        self,
        *,
        customer_lookup_name: str | None,
        trusted_context_customer: EntityRef | None,
        selected_customer_id: str | None,
        authorization: str,
    ) -> object:
        assert customer_lookup_name == "凡亚信息"
        assert trusted_context_customer is None
        assert authorization == "Bearer test-token"
        self.calls.append(selected_customer_id)
        if selected_customer_id is None:
            return SimpleNamespace(
                status="SELECTION_REQUIRED",
                customer=None,
                candidates=self.candidates,
            )
        selected = next(
            (candidate for candidate in self.candidates if candidate.customer_id == selected_customer_id),
            None,
        )
        if selected is None:
            return SimpleNamespace(
                status="SELECTION_REQUIRED",
                customer=None,
                candidates=self.candidates,
            )
        return SimpleNamespace(status="RESOLVED", customer=selected, candidates=())


class WorkflowCustomerChoiceInteractionResolver:
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
        assert isinstance(turn.input, InteractionTurnInput)
        return InteractionResolution(
            status="RESOLVED",
            reason_code="STRUCTURED_WORKFLOW_CONTINUATION",
            resolved_action=ResolvedAgentAction(
                action_id=turn.input.action_id,
                action_type="submit_interaction",
                continuation=self.continuation,
                claim_outcome="ACQUIRED",
                resume_payload=AgentTurnInput.text(
                    "cus_fanya_shenzhen",
                    source="web",
                    metadata={
                        "business_action": "select_workflow_customer",
                        "customer_id": "cus_fanya_shenzhen",
                        "customer_name": "深圳凡亚信息科技有限公司",
                    },
                ).model_dump(mode="json"),
            ),
        )


async def test_ambiguous_explicit_customer_selection_executes_follow_up_record_without_second_confirmation() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CUSTOMER_ACTIVITY",
                "intent_confidence": 0.99,
                "customer": {
                    "name_text": "凡亚信息",
                    "confidence": 0.99,
                    "resolution_source": "EXPLICIT",
                },
                "follow_up": {
                    "content": "项目正在走立项流程",
                    "method": "微信",
                    "next_follow_time_text": "下周三",
                    "next_follow_time": {
                        "raw_text": "下周三",
                        "kind": "RELATIVE_WEEKDAY",
                        "direction": "next",
                        "weekday": 3,
                        "confidence": 0.99,
                    },
                },
            }
        )
    )
    customer_resolver = AmbiguousThenSelectedWorkflowCustomerResolver()
    interaction_resolver = WorkflowCustomerChoiceInteractionResolver()
    tool_registry = CapturingToolRegistry()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateStandaloneWriteDecisionClassifier(reason_code="CREATE_CUSTOMER_ACTIVITY"),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
                customer_resolver=customer_resolver,
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    choice = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=852,
            client_request_id="req_ambiguous_explicit_customer",
            input=TextTurnInput(
                type="text",
                text="微信联系了凡亚信息，项目正在走立项流程；下周三再继续跟进",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(choice, WorkflowDispatchResult)
    assert isinstance(choice.workflow_result, WorkflowWaitingResult)
    assert choice.workflow_result.interaction.business_action == "select_workflow_customer"
    assert [option.value for option in choice.workflow_result.interaction.options] == [
        "cus_fanya_guangzhou",
        "cus_fanya_shenzhen",
    ]
    assert choice.workflow_result.interaction.options[1].metadata == {
        "customer_id": "cus_fanya_shenzhen",
        "customer_name": "深圳凡亚信息科技有限公司",
    }
    assert choice.continuation is not None
    interaction_resolver.continuation = choice.continuation

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=852,
            client_request_id="req_selected_explicit_customer",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_select_workflow_customer",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert completed.continuation is None
    assert len(tool_registry.calls) == 1
    call = tool_registry.calls[0]
    assert call["name"] == "create_customer_activity"
    assert call["payload"]["customer_id"] == "cus_fanya_shenzhen"
    assert call["payload"]["source_content"] == "项目正在走立项流程"
    assert customer_resolver.calls == [None, "cus_fanya_shenzhen"]


async def test_create_follow_up_workflow_auto_executes_high_confidence_low_risk_action() -> None:
    tool_registry = CapturingToolRegistry()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateFollowUpDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=CanonicalConfirmationResolver(),
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=FakeSemanticParser(intent_confidence=0.99),
                temporal_resolver=FixedTemporalResolver(),
                customer_resolver=ContextWorkflowCustomerResolver(),
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
        ),
    )
    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_create_follow_up_auto_execute",
            input=TextTurnInput(
                type="text",
                text="为上海星云科技创建跟进任务,内容是确认技术评估结论,下周三上午10点跟进",
            ),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=RootRuntimeContext(
            db=object(),
            authorization="Bearer test-token",
            metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
        ),
    )

    assert isinstance(result, WorkflowDispatchResult)
    assert isinstance(result.workflow_result, WorkflowCompletedResult)
    assert result.continuation is None
    assert len(tool_registry.calls) == 1
    call = tool_registry.calls[0]
    assert call["name"] == "create_customer_activity"
    context = call["context"]
    assert isinstance(context, AgentToolContext)
    assert context.execution_policy == "auto_execute"
    assert context.authorization_source == "semantic_auto_execute_low_risk"
    assert context.auto_execute_authorized is True
    assert context.confirmed_by_user is False
    assert context.allowed_customer_ids == ["cus_shanghai_001"]
    assert len(result.workflow_result.durable_work) == 1
    assert result.workflow_result.durable_work[0].activity_id == 241


async def test_create_follow_up_workflow_rejects_without_executing_effect() -> None:
    tool_registry = CapturingToolRegistry()
    workflow_subgraph = build_workflow_subgraph(
        planner=CRMWorkflowPlanner(
            semantic_parser=FakeSemanticParser(intent_confidence=0.80),
            temporal_resolver=FixedTemporalResolver(),
            customer_resolver=ContextWorkflowCustomerResolver(),
        ),
        effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
    )
    interaction_resolver = CanonicalRejectionResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateFollowUpDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=workflow_subgraph,
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_create_follow_up_waiting_before_reject",
            input=TextTurnInput(
                type="text",
                text="为上海星云科技创建跟进任务,内容是确认技术评估结论,下周三上午10点跟进",
            ),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(waiting, WorkflowDispatchResult)
    assert isinstance(waiting.workflow_result, WorkflowWaitingResult)
    assert waiting.workflow_result.interaction.business_action == "create_customer_activity"
    assert waiting.workflow_result.interaction.title == "确认记录客户跟进"
    assert "记录本次跟进" in waiting.workflow_result.interaction.prompt
    assert waiting.continuation is not None
    interaction_resolver.continuation = waiting.continuation

    cancelled = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_create_follow_up_rejected",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_reject_create_follow_up",
                values={"choice": "forged-client-value"},
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(cancelled, WorkflowDispatchResult)
    assert isinstance(cancelled.workflow_result, WorkflowCancelledResult)
    assert cancelled.workflow_result.assistant_text == "已取消记录上海星云科技有限公司的本次跟进。"
    assert cancelled.workflow_result.workflow_ref.workflow_id == waiting.workflow_result.workflow_ref.workflow_id
    assert tool_registry.calls == []


async def test_confirmed_workflow_returns_non_retryable_failure_when_guardrail_rejects_effect() -> None:
    workflow_subgraph = build_workflow_subgraph(
        planner=CRMWorkflowPlanner(
            semantic_parser=FakeSemanticParser(intent_confidence=0.80),
            temporal_resolver=FixedTemporalResolver(),
            customer_resolver=ContextWorkflowCustomerResolver(),
        ),
        effect_executor=CRMWorkflowEffectExecutor(
            tool_registry=RaisingToolRegistry(AgentToolGuardrailError("forged authorization"))
        ),
    )
    interaction_resolver = CanonicalConfirmationResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateFollowUpDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=workflow_subgraph,
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_guardrail_waiting",
            input=TextTurnInput(
                type="text",
                text="为上海星云科技创建跟进任务,内容是确认技术评估结论,下周三上午10点跟进",
            ),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )
    assert isinstance(waiting, WorkflowDispatchResult)
    assert isinstance(waiting.workflow_result, WorkflowWaitingResult)
    assert waiting.continuation is not None
    interaction_resolver.continuation = waiting.continuation

    failed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_guardrail_confirmed",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_create_follow_up",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(failed, WorkflowDispatchResult)
    assert isinstance(failed.workflow_result, WorkflowFailedResult)
    assert failed.workflow_result.code == "WORKFLOW_AUTHORIZATION_REJECTED"
    assert failed.workflow_result.retryable is False


async def test_confirmed_workflow_does_not_hide_unexpected_programming_error() -> None:
    workflow_subgraph = build_workflow_subgraph(
        planner=CRMWorkflowPlanner(
            semantic_parser=FakeSemanticParser(intent_confidence=0.80),
            temporal_resolver=FixedTemporalResolver(),
            customer_resolver=ContextWorkflowCustomerResolver(),
        ),
        effect_executor=CRMWorkflowEffectExecutor(
            tool_registry=RaisingToolRegistry(RuntimeError("unexpected implementation defect"))
        ),
    )
    interaction_resolver = CanonicalConfirmationResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateFollowUpDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=workflow_subgraph,
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_programming_error_waiting",
            input=TextTurnInput(
                type="text",
                text="为上海星云科技创建跟进任务,内容是确认技术评估结论,下周三上午10点跟进",
            ),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )
    assert isinstance(waiting, WorkflowDispatchResult)
    assert isinstance(waiting.workflow_result, WorkflowWaitingResult)
    assert waiting.continuation is not None
    interaction_resolver.continuation = waiting.continuation

    with pytest.raises(RuntimeError, match="unexpected implementation defect"):
        await orchestrator.dispatch(
            RootTurnInput(
                team_id=1,
                user_id=2,
                session_id=556,
                client_request_id="req_programming_error_confirmed",
                input=InteractionTurnInput(
                    type="interaction",
                    action_id="act_confirm_create_follow_up",
                ),
            ),
            runtime=runtime,
        )


class MissingContentThenCompleteSemanticParser:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def parse_with_metadata(
        self,
        db: object,
        *,
        team_id: int,
        user_message: str,
        memory: object = None,
        current_date: object = None,
    ) -> AgentSemanticParseEnvelope:
        self.messages.append(user_message)
        content = "确认技术评估结论" if "确认技术评估结论" in user_message else None
        return AgentSemanticParseEnvelope(
            result=AgentSemanticParseResult.model_validate(
                {
                    "intent": "CUSTOMER_ACTIVITY",
                    "intent_confidence": 0.99,
                    "customer": {
                        "name_text": CUSTOMER_REF.display_name,
                        "confidence": 0.99,
                        "resolution_source": "EXPLICIT",
                    },
                    "follow_up": {
                        "content": content,
                        "method": "电话",
                        "next_follow_time_text": "下周三上午10点",
                        "next_follow_time": {
                            "raw_text": "下周三上午10点",
                            "kind": "RELATIVE_WEEKDAY",
                            "direction": "next",
                            "weekday": 3,
                            "hour": 10,
                            "minute": 0,
                            "confidence": 0.99,
                        },
                    },
                }
            ),
            parse_source="langchain_structured_output",
            model="test-model",
        )


class SupplementThenConfirmationResolver:
    def __init__(self) -> None:
        self.continuations: dict[str, WorkflowContinuation] = {}

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> InteractionResolution:
        assert isinstance(turn.input, InteractionTurnInput)
        continuation = self.continuations[turn.input.action_id]
        resume = (
            AgentTurnInput.text("确认技术评估结论", source="web")
            if turn.input.action_id == "act_supply_follow_up_content"
            else AgentTurnInput.confirm(source="web")
        )
        return InteractionResolution(
            status="RESOLVED",
            reason_code="STRUCTURED_WORKFLOW_CONTINUATION",
            resolved_action=ResolvedAgentAction(
                action_id=turn.input.action_id,
                action_type="submit_interaction",
                continuation=continuation,
                claim_outcome="ACQUIRED",
                resume_payload=resume.model_dump(mode="json"),
            ),
        )


async def test_missing_follow_up_content_interrupts_then_executes_after_required_input() -> None:
    semantic_parser = MissingContentThenCompleteSemanticParser()
    tool_registry = CapturingToolRegistry()
    interaction_resolver = SupplementThenConfirmationResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateFollowUpDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=semantic_parser,
                temporal_resolver=FixedTemporalResolver(),
                customer_resolver=ContextWorkflowCustomerResolver(),
            ),
            effect_executor=CRMWorkflowEffectExecutor(
                tool_registry=tool_registry,
            ),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    needs_input = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_missing_content",
            input=TextTurnInput(
                type="text",
                text="为上海星云科技创建跟进任务,下周三上午10点电话跟进",
            ),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(needs_input, WorkflowDispatchResult)
    assert isinstance(needs_input.workflow_result, WorkflowWaitingResult)
    assert needs_input.workflow_result.interaction.interaction_type == "text_input"
    assert needs_input.workflow_result.interaction.business_action == "provide_follow_up_content"
    assert needs_input.continuation is not None
    interaction_resolver.continuations["act_supply_follow_up_content"] = needs_input.continuation
    assert tool_registry.calls == []

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=556,
            client_request_id="req_supply_content",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_supply_follow_up_content",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert completed.continuation is None
    assert "补充信息: 确认技术评估结论" in semantic_parser.messages[-1]
    assert len(tool_registry.calls) == 1


class TwoSupplementsThenCompleteSemanticParser:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def parse_with_metadata(
        self,
        db: object,
        *,
        team_id: int,
        user_message: str,
        memory: object = None,
        current_date: object = None,
    ) -> AgentSemanticParseEnvelope:
        self.messages.append(user_message)
        has_conclusion = "确认技术评估结论" in user_message
        has_scope = "补充验收范围" in user_message
        content = "确认技术评估结论并补充验收范围" if has_conclusion and has_scope else None
        return AgentSemanticParseEnvelope(
            result=AgentSemanticParseResult.model_validate(
                {
                    "intent": "CUSTOMER_ACTIVITY",
                    "intent_confidence": 0.99,
                    "customer": {
                        "name_text": CUSTOMER_REF.display_name,
                        "confidence": 0.99,
                        "resolution_source": "EXPLICIT",
                    },
                    "follow_up": {
                        "content": content,
                        "method": "电话",
                        "next_follow_time_text": "下周三上午10点",
                        "next_follow_time": {
                            "raw_text": "下周三上午10点",
                            "kind": "RELATIVE_WEEKDAY",
                            "direction": "next",
                            "weekday": 3,
                            "hour": 10,
                            "minute": 0,
                            "confidence": 0.99,
                        },
                    },
                }
            ),
            parse_source="langchain_structured_output",
            model="test-model",
        )


class SwitchingAfterMultipleSupplementsClassifier:
    async def classify(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> RootDecision:
        if isinstance(turn.input, TextTurnInput) and turn.input.text == "上海有哪些客户":
            assert context.active_workflow is not None
            return RootDecision(
                task_relation="SWITCH_TASK",
                route="QUERY",
                risk="READ_ONLY",
                context_policy=ContextPolicy(
                    selected_entity="IGNORE",
                    previous_query="IGNORE",
                    result_set="IGNORE",
                    active_workflow="SUSPEND",
                ),
                confidence=1.0,
                reason_code="SWITCH_TO_CITY_CUSTOMER_QUERY",
            )
        return await CreateFollowUpDecisionClassifier().classify(
            turn=turn,
            context=context,
            runtime=runtime,
        )


class SuccessfulCityQueryExecutor:
    async def execute(self, request: object, *, runtime: object) -> CRMQueryAgentResult:
        return CRMQueryAgentResult(
            response=CRMQueryAgentResponse(
                status="ANSWERED",
                answer="找到了上海客户。",
                evidence_refs=["query_customers"],
            ),
            trace=CRMQueryAgentTrace(
                model="test-model",
                tool_names=["query_customers"],
                tool_call_count=1,
                total_entity_count=1,
                elapsed_ms=1,
                stop_reason="COMPLETED",
            ),
        )


class WorkflowRefScriptedResolver:
    def __init__(self) -> None:
        self.continuations: dict[str, WorkflowContinuation] = {}

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> InteractionResolution:
        assert isinstance(turn.input, InteractionTurnInput)
        continuation = self.continuations[turn.input.action_id]
        if turn.input.action_id == "act_supply_conclusion":
            resume = AgentTurnInput.text("确认技术评估结论", source="web")
        elif turn.input.action_id == "act_supply_scope":
            resume = AgentTurnInput.text("补充验收范围", source="web")
        else:
            resume = AgentTurnInput.confirm(source="web")
        return InteractionResolution(
            status="RESOLVED",
            reason_code="STRUCTURED_WORKFLOW_CONTINUATION",
            resolved_action=ResolvedAgentAction(
                action_id=turn.input.action_id,
                action_type="submit_interaction",
                continuation=continuation,
                claim_outcome="ACQUIRED",
                resume_payload=resume.model_dump(mode="json"),
            ),
        )


async def test_suspended_workflow_resumes_after_multiple_required_inputs() -> None:
    semantic_parser = TwoSupplementsThenCompleteSemanticParser()
    tool_registry = CapturingToolRegistry()
    interaction_resolver = WorkflowRefScriptedResolver()
    context_resolver = ActiveWorkflowContextResolver()
    checkpointer = json_safe_checkpointer()
    orchestrator = RootOrchestrator(
        checkpointer=checkpointer,
        context_resolver=context_resolver,
        decision_classifier=SwitchingAfterMultipleSupplementsClassifier(),
        query_executor=SuccessfulCityQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=semantic_parser,
                temporal_resolver=FixedTemporalResolver(),
                customer_resolver=ContextWorkflowCustomerResolver(),
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    first_waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=557,
            client_request_id="req_multiple_missing_fields",
            input=TextTurnInput(
                type="text",
                text="为上海星云科技创建跟进任务,下周三上午10点电话跟进",
            ),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )
    assert isinstance(first_waiting, WorkflowDispatchResult)
    assert isinstance(first_waiting.workflow_result, WorkflowWaitingResult)
    assert first_waiting.continuation is not None
    interaction_resolver.continuations["act_supply_conclusion"] = first_waiting.continuation

    second_waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=557,
            client_request_id="req_supply_conclusion",
            input=InteractionTurnInput(type="interaction", action_id="act_supply_conclusion"),
        ),
        runtime=runtime,
    )
    assert isinstance(second_waiting, WorkflowDispatchResult)
    assert isinstance(second_waiting.workflow_result, WorkflowWaitingResult)
    assert second_waiting.workflow_result.interaction.interaction_type == "text_input"
    assert second_waiting.continuation is not None
    interaction_resolver.continuations["act_supply_scope"] = second_waiting.continuation
    context_resolver.active_workflow = second_waiting.continuation.workflow_ref

    query = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=557,
            client_request_id="req_query_while_waiting_for_scope",
            input=TextTurnInput(type="text", text="上海有哪些客户"),
        ),
        runtime=runtime,
    )
    assert query.type == "query"

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=557,
            client_request_id="req_supply_scope_after_query",
            input=InteractionTurnInput(type="interaction", action_id="act_supply_scope"),
        ),
        runtime=runtime,
    )
    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert completed.continuation is None
    assert len(tool_registry.calls) == 1


class CreateStandaloneWriteDecisionClassifier:
    def __init__(self, *, reason_code: str) -> None:
        self.reason_code = reason_code

    async def classify(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> RootDecision:
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
            reason_code=self.reason_code,
        )


class StaticSemanticParser:
    def __init__(self, result: AgentSemanticParseResult) -> None:
        self.result = result
        self.messages: list[str] = []

    async def parse_with_metadata(
        self,
        db: object,
        *,
        team_id: int,
        user_message: str,
        memory: object = None,
        current_date: object = None,
    ) -> AgentSemanticParseEnvelope:
        self.messages.append(user_message)
        return AgentSemanticParseEnvelope(
            result=self.result,
            parse_source="langchain_structured_output",
            model="test-model",
        )


class SequencedSemanticParser:
    def __init__(self, *results: AgentSemanticParseResult) -> None:
        self.results = list(results)
        self.messages: list[str] = []

    async def parse_with_metadata(
        self,
        db: object,
        *,
        team_id: int,
        user_message: str,
        memory: object = None,
        current_date: object = None,
    ) -> AgentSemanticParseEnvelope:
        self.messages.append(user_message)
        if not self.results:
            raise AssertionError("semantic parser received more calls than expected")
        return AgentSemanticParseEnvelope(
            result=self.results.pop(0),
            parse_source="langchain_structured_output",
            model="test-model",
        )


async def test_create_lead_workflow_confirms_and_executes_through_root_dispatch() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CREATE_LEAD",
                "intent_confidence": 0.99,
                "lead": {
                    "lead_name": "上海云图科技",
                    "city": "上海",
                    "contact_name": "王敏",
                    "contact_phone": "13800138000",
                },
            }
        )
    )
    tool_registry = CapturingToolRegistry()
    interaction_resolver = CanonicalConfirmationResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateStandaloneWriteDecisionClassifier(reason_code="CREATE_LEAD"),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=560,
            client_request_id="req_create_lead_waiting",
            input=TextTurnInput(
                type="text",
                text="创建上海云图科技线索,联系人王敏,电话13800138000",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(waiting, WorkflowDispatchResult)
    assert isinstance(waiting.workflow_result, WorkflowWaitingResult)
    assert waiting.workflow_result.interaction.business_action == "create_lead"
    assert waiting.continuation is not None
    interaction_resolver.continuation = waiting.continuation

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=560,
            client_request_id="req_create_lead_confirmed",
            input=InteractionTurnInput(type="interaction", action_id="act_confirm_create_lead"),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert completed.workflow_result.assistant_text == "已创建线索“上海云图科技”。"
    assert len(tool_registry.calls) == 1
    call = tool_registry.calls[0]
    assert call["name"] == "create_lead"
    assert call["payload"] == {
        "lead": {
            "lead_name": "上海云图科技",
            "city": "上海",
            "contact_name": "王敏",
            "contact_phone": "13800138000",
        },
        "idempotency_suffix": f"{waiting.workflow_result.workflow_ref.workflow_id}:create_lead",
    }


async def test_create_customer_workflow_normalizes_primary_contact_before_execution() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CREATE_CUSTOMER",
                "intent_confidence": 0.99,
                "customer_create": {
                    "account_name": "上海星图信息技术有限公司",
                    "city": "上海",
                    "industry": "软件",
                    "contact_name": "李华",
                    "contact_phone": "13900139000",
                    "contact_position": "CTO",
                    "contact_gender": "1",
                    "contact_email": "lihua@example.com",
                },
            }
        )
    )
    tool_registry = CapturingToolRegistry()
    interaction_resolver = CanonicalConfirmationResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateStandaloneWriteDecisionClassifier(reason_code="CREATE_CUSTOMER"),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=561,
            client_request_id="req_create_customer_waiting",
            input=TextTurnInput(
                type="text",
                text="创建客户上海星图信息技术有限公司,上海软件行业,联系人李华,CTO,13900139000",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(waiting, WorkflowDispatchResult)
    assert isinstance(waiting.workflow_result, WorkflowWaitingResult)
    assert waiting.workflow_result.interaction.business_action == "create_customer"
    assert waiting.continuation is not None
    interaction_resolver.continuation = waiting.continuation

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=561,
            client_request_id="req_create_customer_confirmed",
            input=InteractionTurnInput(type="interaction", action_id="act_confirm_create_customer"),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert completed.workflow_result.assistant_text == "已创建客户“上海星图信息技术有限公司”。"
    assert len(tool_registry.calls) == 1
    call = tool_registry.calls[0]
    assert call["name"] == "create_customer"
    assert call["payload"] == {
        "customer": {
            "account_name": "上海星图信息技术有限公司",
            "city": "上海",
            "industry": "软件",
            "primary_contact": {
                "name": "李华",
                "mobile": "13900139000",
                "position": "CTO",
                "gender": "1",
                "email": "lihua@example.com",
            },
        },
        "idempotency_suffix": f"{waiting.workflow_result.workflow_ref.workflow_id}:create_customer",
    }


async def test_create_lead_with_follow_up_confirms_once_and_binds_created_lead_id() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CREATE_LEAD",
                "intent_confidence": 0.99,
                "lead": {
                    "lead_name": "上海云图科技",
                    "city": "上海",
                    "contact_name": "王敏",
                    "contact_phone": "13800138000",
                    "follow_up_content": "已确认需要安排产品演示",
                    "follow_up_method": "电话",
                    "next_action": "安排产品演示",
                    "next_follow_time": {
                        "raw_text": "明天上午10点",
                        "kind": "RELATIVE_DAY",
                        "direction": "next",
                        "amount": 1,
                        "unit": "day",
                        "hour": 10,
                        "minute": 0,
                        "confidence": 0.99,
                    },
                },
            }
        )
    )
    tool_registry = CapturingToolRegistry()
    interaction_resolver = CanonicalConfirmationResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateStandaloneWriteDecisionClassifier(reason_code="CREATE_LEAD"),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=562,
            client_request_id="req_create_lead_follow_up_waiting",
            input=TextTurnInput(
                type="text",
                text=(
                    "创建上海云图科技线索,联系人王敏,电话13800138000,已电话确认需要安排产品演示,明天上午10点继续跟进"
                ),
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(waiting, WorkflowDispatchResult)
    assert isinstance(waiting.workflow_result, WorkflowWaitingResult)
    assert waiting.workflow_result.interaction.business_action == "create_lead_with_follow_up"
    assert waiting.continuation is not None
    interaction_resolver.continuation = waiting.continuation
    assert tool_registry.calls == []

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=562,
            client_request_id="req_create_lead_follow_up_confirmed",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_create_lead_with_follow_up",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert completed.workflow_result.assistant_text == "已创建线索“上海云图科技”并记录首次跟进。"
    assert [call["name"] for call in tool_registry.calls] == [
        "create_lead",
        "create_lead_follow_up",
    ]
    workflow_id = waiting.workflow_result.workflow_ref.workflow_id
    assert tool_registry.calls[0]["payload"] == {
        "lead": {
            "lead_name": "上海云图科技",
            "city": "上海",
            "contact_name": "王敏",
            "contact_phone": "13800138000",
        },
        "idempotency_suffix": f"{workflow_id}:create_lead",
    }
    assert tool_registry.calls[1]["payload"] == {
        "lead_id": "lead_001",
        "content": "已确认需要安排产品演示",
        "method": "电话",
        "next_action": "安排产品演示",
        "next_follow_time": "2026-08-26T10:00:00",
        "idempotency_suffix": f"{workflow_id}:create_lead_follow_up",
    }


async def test_create_customer_with_activity_confirms_once_and_binds_created_customer_id() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CREATE_CUSTOMER",
                "intent_confidence": 0.99,
                "customer_create": {
                    "account_name": "上海星图信息技术有限公司",
                    "city": "上海",
                    "industry": "软件",
                    "contact_name": "李华",
                    "contact_phone": "13900139000",
                    "contact_position": "CTO",
                    "contact_gender": "1",
                    "follow_up_content": "已确认进入技术评估阶段",
                    "follow_up_method": "微信",
                    "next_action": "发送技术评估材料",
                    "next_follow_time": {
                        "raw_text": "下周三上午10点",
                        "kind": "RELATIVE_WEEKDAY",
                        "direction": "next",
                        "weekday": 3,
                        "hour": 10,
                        "minute": 0,
                        "confidence": 0.99,
                    },
                },
            }
        )
    )
    tool_registry = CapturingToolRegistry()
    interaction_resolver = CanonicalConfirmationResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateStandaloneWriteDecisionClassifier(reason_code="CREATE_CUSTOMER"),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=563,
            client_request_id="req_create_customer_activity_waiting",
            input=TextTurnInput(
                type="text",
                text=(
                    "创建客户上海星图信息技术有限公司,联系人李华,电话13900139000,"
                    "已微信确认进入技术评估阶段,下周三上午10点继续跟进"
                ),
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(waiting, WorkflowDispatchResult)
    assert isinstance(waiting.workflow_result, WorkflowWaitingResult)
    assert waiting.workflow_result.interaction.business_action == "create_customer_with_activity"
    assert waiting.continuation is not None
    interaction_resolver.continuation = waiting.continuation
    assert tool_registry.calls == []

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=563,
            client_request_id="req_create_customer_activity_confirmed",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_create_customer_with_activity",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert completed.workflow_result.assistant_text == ("已创建客户“上海星图信息技术有限公司”并记录首次跟进。")
    assert [call["name"] for call in tool_registry.calls] == [
        "create_customer",
        "create_customer_activity",
    ]
    workflow_id = waiting.workflow_result.workflow_ref.workflow_id
    assert tool_registry.calls[0]["payload"] == {
        "customer": {
            "account_name": "上海星图信息技术有限公司",
            "city": "上海",
            "industry": "软件",
            "primary_contact": {
                "name": "李华",
                "mobile": "13900139000",
                "position": "CTO",
                "gender": "1",
            },
        },
        "idempotency_suffix": f"{workflow_id}:create_customer",
    }
    assert tool_registry.calls[1]["payload"] == {
        "customer_id": "cust_001",
        "customer_name": "上海星图信息技术有限公司",
        "activity_kind": "WECHAT_FOLLOW_UP",
        "source_content": "已确认进入技术评估阶段",
        "title": "已确认进入技术评估阶段",
        "next_action": "发送技术评估材料",
        "next_follow_time": "2026-08-26T10:00:00",
        "idempotency_suffix": f"{workflow_id}:create_customer_activity",
    }


async def test_create_contact_uses_selected_customer_public_id_through_root_dispatch() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CREATE_CONTACT",
                "intent_confidence": 0.99,
                "contact": {
                    "name": "周敏",
                    "mobile": "13700137000",
                    "position": "采购总监",
                    "gender": "2",
                    "is_decision_maker": True,
                    "email": "zhoumin@example.com",
                },
            }
        )
    )
    tool_registry = CapturingToolRegistry()
    interaction_resolver = CanonicalConfirmationResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateFollowUpDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=564,
            client_request_id="req_create_contact_waiting",
            input=TextTurnInput(
                type="text",
                text="为上海星云科技创建联系人周敏,采购总监,13700137000,女,是决策人",
            ),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(waiting, WorkflowDispatchResult)
    assert isinstance(waiting.workflow_result, WorkflowWaitingResult)
    assert waiting.workflow_result.interaction.business_action == "create_contact"
    assert waiting.continuation is not None
    interaction_resolver.continuation = waiting.continuation

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=564,
            client_request_id="req_create_contact_confirmed",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_create_contact",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert completed.workflow_result.assistant_text == "已为上海星云科技有限公司创建联系人“周敏”。"
    workflow_id = waiting.workflow_result.workflow_ref.workflow_id
    assert len(tool_registry.calls) == 1
    assert tool_registry.calls[0]["name"] == "create_contact"
    assert tool_registry.calls[0]["payload"] == {
        "customer_id": CUSTOMER_REF.public_id,
        "contact": {
            "name": "周敏",
            "mobile": "13700137000",
            "position": "采购总监",
            "gender": "2",
            "is_decision_maker": True,
            "email": "zhoumin@example.com",
        },
        "idempotency_suffix": f"{workflow_id}:create_contact",
    }


async def test_create_invoice_title_uses_company_title_as_customer_identity_evidence() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CREATE_INVOICE_TITLE",
                "intent_confidence": 0.99,
                "invoice_title": {
                    "title_type": "COMPANY",
                    "title": "广州凡亚信息科技有限公司",
                    "taxpayer_id": "91440101TEST000001",
                    "bank_name": "招商银行广州分行",
                    "bank_account": "6225888800000001",
                    "address": "广州市天河区测试路1号",
                    "phone": "020-88880000",
                    "set_default": True,
                },
            }
        )
    )
    customer_resolver = ExplicitOnlyWorkflowCustomerResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateStandaloneWriteDecisionClassifier(reason_code="CREATE_INVOICE_TITLE"),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=CanonicalConfirmationResolver(),
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
                customer_resolver=customer_resolver,
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=CapturingToolRegistry()),
        ),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=566,
            client_request_id="req_invoice_title_customer_evidence",
            input=TextTurnInput(
                type="text",
                text=(
                    "创建发票抬头：公司名称广州凡亚信息科技有限公司，"
                    "税号91440101TEST000001，开户行招商银行广州分行，"
                    "账号6225888800000001，地址广州市天河区测试路1号，"
                    "电话020-88880000"
                ),
            ),
        ),
        runtime=RootRuntimeContext(
            db=object(),
            authorization="Bearer test-token",
            metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
        ),
    )

    assert isinstance(result, WorkflowDispatchResult)
    assert isinstance(result.workflow_result, WorkflowWaitingResult)
    assert result.workflow_result.interaction.business_action == "create_invoice_title"
    assert customer_resolver.calls == [
        {
            "customer_lookup_name": "广州凡亚信息科技有限公司",
            "trusted_context_customer": None,
            "selected_customer_id": None,
            "authorization": "Bearer test-token",
        }
    ]


async def test_create_invoice_title_reports_unresolved_company_instead_of_missing_customer() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CREATE_INVOICE_TITLE",
                "intent_confidence": 0.99,
                "invoice_title": {
                    "title_type": "COMPANY",
                    "title": "尚未录入客户库的测试公司有限公司",
                    "taxpayer_id": "91440101TEST000099",
                    "bank_name": "测试银行广州分行",
                    "bank_account": "6225888800000099",
                    "address": "广州市天河区测试路99号",
                    "phone": "020-88880099",
                },
            }
        )
    )
    customer_resolver = NotFoundExplicitWorkflowCustomerResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateStandaloneWriteDecisionClassifier(reason_code="CREATE_INVOICE_TITLE"),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=CanonicalConfirmationResolver(),
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
                customer_resolver=customer_resolver,
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=CapturingToolRegistry()),
        ),
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=567,
            client_request_id="req_invoice_title_customer_not_found",
            input=TextTurnInput(type="text", text="为尚未录入客户库的测试公司有限公司创建发票抬头"),
        ),
        runtime=RootRuntimeContext(
            db=object(),
            authorization="Bearer test-token",
            metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
        ),
    )

    assert isinstance(result, WorkflowDispatchResult)
    assert isinstance(result.workflow_result, WorkflowWaitingResult)
    assert result.workflow_result.interaction.business_action == "provide_workflow_customer"
    assert "尚未录入客户库的测试公司有限公司" in result.workflow_result.interaction.prompt
    assert customer_resolver.calls == ["尚未录入客户库的测试公司有限公司"]


async def test_create_invoice_title_uses_canonical_payload_and_selected_customer() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CREATE_INVOICE_TITLE",
                "intent_confidence": 0.99,
                "invoice_title": {
                    "title_type": "COMPANY",
                    "title": "上海星云集团有限公司",
                    "taxpayer_id": "91310000TEST000001",
                    "bank_name": "招商银行上海分行",
                    "bank_account": "6225888800000000",
                    "address": "上海市浦东新区测试路1号",
                    "phone": "021-68880000",
                    "set_default": True,
                },
            }
        )
    )
    tool_registry = CapturingToolRegistry()
    interaction_resolver = CanonicalConfirmationResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateFollowUpDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=565,
            client_request_id="req_create_invoice_title_waiting",
            input=TextTurnInput(type="text", text="为当前客户创建默认公司发票抬头"),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(waiting, WorkflowDispatchResult)
    assert isinstance(waiting.workflow_result, WorkflowWaitingResult)
    assert waiting.workflow_result.interaction.business_action == "create_invoice_title"
    assert waiting.continuation is not None
    interaction_resolver.continuation = waiting.continuation

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=565,
            client_request_id="req_create_invoice_title_confirmed",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_create_invoice_title",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert completed.workflow_result.assistant_text == ("已为上海星云科技有限公司创建发票抬头“上海星云集团有限公司”。")
    workflow_id = waiting.workflow_result.workflow_ref.workflow_id
    assert len(tool_registry.calls) == 1
    assert tool_registry.calls[0]["name"] == "create_invoice_title"
    assert tool_registry.calls[0]["payload"] == {
        "customer_id": CUSTOMER_REF.public_id,
        "invoice_title": {
            "title_type": "COMPANY",
            "title": "上海星云集团有限公司",
            "taxpayer_id": "91310000TEST000001",
            "bank_name": "招商银行上海分行",
            "bank_account": "6225888800000000",
            "address": "上海市浦东新区测试路1号",
            "phone": "021-68880000",
        },
        "set_default": True,
        "idempotency_suffix": f"{workflow_id}:create_invoice_title",
    }


async def test_create_deployment_info_uses_canonical_payload_and_selected_customer() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CREATE_DEPLOYMENT_INFO",
                "intent_confidence": 0.99,
                "deployment_info": {
                    "deployment_name": "上海生产环境",
                    "server_address": "https://crm.shanghai.example.com",
                    "authorized_users": 80,
                    "is_default": True,
                    "customer_id": "forged_customer_id",
                    "unexpected": "must_be_dropped",
                },
            }
        )
    )
    tool_registry = CapturingToolRegistry()
    interaction_resolver = CanonicalConfirmationResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateFollowUpDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=566,
            client_request_id="req_create_deployment_info_waiting",
            input=TextTurnInput(type="text", text="为当前客户创建默认部署信息"),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(waiting, WorkflowDispatchResult)
    assert isinstance(waiting.workflow_result, WorkflowWaitingResult)
    assert waiting.workflow_result.interaction.business_action == "create_deployment_info"
    assert waiting.continuation is not None
    interaction_resolver.continuation = waiting.continuation

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=566,
            client_request_id="req_create_deployment_info_confirmed",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_create_deployment_info",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert completed.workflow_result.assistant_text == ("已为上海星云科技有限公司创建部署信息“上海生产环境”。")
    workflow_id = waiting.workflow_result.workflow_ref.workflow_id
    assert len(tool_registry.calls) == 1
    assert tool_registry.calls[0]["name"] == "create_deployment_info"
    assert tool_registry.calls[0]["payload"] == {
        "deployment_info": {
            "customer_id": CUSTOMER_REF.public_id,
            "deployment_name": "上海生产环境",
            "server_address": "https://crm.shanghai.example.com",
            "authorized_users": 80,
            "is_default": True,
        },
        "idempotency_suffix": f"{workflow_id}:create_deployment_info",
    }


class StaticWorkflowPlanner:
    def __init__(self, plan: WorkflowActionPlan) -> None:
        self._plan = plan

    async def plan(
        self,
        request: WorkflowTurnInput,
        *,
        workflow_id: str,
        runtime: WorkflowRuntimeContext,
    ) -> WorkflowActionPlan:
        return self._plan.model_copy(
            update={
                "action_id": f"workflow:{workflow_id}",
                "interaction": self._plan.interaction.model_copy(
                    update={"interaction_id": f"interaction:{workflow_id}"}
                ),
            }
        )


class MissingCreatedIdToolRegistry(CapturingToolRegistry):
    async def execute(
        self,
        name: str,
        context: object,
        payload: dict[str, object],
        *,
        policy: object,
    ) -> AgentToolResult:
        self.calls.append(
            {
                "name": name,
                "context": context,
                "payload": payload,
                "policy": policy,
            }
        )
        if name != "create_lead":
            raise AssertionError("A command with an unresolved binding must not execute")
        return AgentToolResult(tool_name=name, success=True, data={})


def confirmation_plan(commands: list[WorkflowCommand]) -> WorkflowActionPlan:
    return WorkflowActionPlan(
        action_id="workflow:template",
        execution_authorization="CONFIRMATION_REQUIRED",
        commands=commands,
        interaction=WorkflowInteraction(
            interaction_id="interaction:template",
            interaction_type="confirmation",
            business_action="test_workflow_plan",
            title="确认执行",
            prompt="确认执行测试工作流吗?",
            options=[
                WorkflowInteractionOption(value="confirm", label="确认"),
                WorkflowInteractionOption(value="reject", label="取消"),
            ],
            selection_mode="single",
        ),
        completed_text="测试工作流已完成。",
        cancelled_text="测试工作流已取消。",
    )


async def dispatch_confirmed_static_plan(
    *,
    plan: WorkflowActionPlan,
    tool_registry: CapturingToolRegistry,
    session_id: int,
) -> tuple[WorkflowWaitingResult, WorkflowDispatchResult]:
    interaction_resolver = CanonicalConfirmationResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateStandaloneWriteDecisionClassifier(reason_code="STATIC_WRITE_PLAN"),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=StaticWorkflowPlanner(plan),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )
    waiting_dispatch = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=session_id,
            client_request_id=f"req_static_plan_{session_id}_waiting",
            input=TextTurnInput(type="text", text="执行测试工作流"),
        ),
        runtime=runtime,
    )
    assert isinstance(waiting_dispatch, WorkflowDispatchResult)
    assert isinstance(waiting_dispatch.workflow_result, WorkflowWaitingResult)
    assert waiting_dispatch.continuation is not None
    interaction_resolver.continuation = waiting_dispatch.continuation

    completed_dispatch = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=session_id,
            client_request_id=f"req_static_plan_{session_id}_confirmed",
            input=InteractionTurnInput(
                type="interaction",
                action_id=f"act_static_plan_{session_id}",
            ),
        ),
        runtime=runtime,
    )
    assert isinstance(completed_dispatch, WorkflowDispatchResult)
    return waiting_dispatch.workflow_result, completed_dispatch


async def test_workflow_fails_closed_when_prior_command_result_cannot_be_bound() -> None:
    tool_registry = MissingCreatedIdToolRegistry()
    _, completed = await dispatch_confirmed_static_plan(
        plan=confirmation_plan(
            [
                WorkflowCommand(
                    command_id="create_lead",
                    tool_name="create_lead",
                    payload={"lead": {"lead_name": "上海云图科技"}},
                    authorization_scope=WorkflowAuthorizationScope(customer_ids=[]),
                ),
                WorkflowCommand(
                    command_id="create_lead_follow_up",
                    tool_name="create_lead_follow_up",
                    payload={"content": "首次联系"},
                    authorization_scope=WorkflowAuthorizationScope(customer_ids=[]),
                    bindings=[
                        WorkflowCommandBinding(
                            target_path=["lead_id"],
                            source_command_id="create_lead",
                            source_path=["id"],
                        )
                    ],
                ),
            ]
        ),
        tool_registry=tool_registry,
        session_id=567,
    )

    assert isinstance(completed.workflow_result, WorkflowFailedResult)
    assert completed.workflow_result.code == "WORKFLOW_COMMAND_BINDING_FAILED"
    assert [call["name"] for call in tool_registry.calls] == ["create_lead"]


async def test_workflow_preflights_every_command_before_any_effect_executes() -> None:
    tool_registry = CapturingToolRegistry()
    _, completed = await dispatch_confirmed_static_plan(
        plan=confirmation_plan(
            [
                WorkflowCommand(
                    command_id="create_customer",
                    tool_name="create_customer",
                    payload={"customer": {"account_name": "上海云图科技"}},
                    authorization_scope=WorkflowAuthorizationScope(customer_ids=[]),
                ),
                WorkflowCommand(
                    command_id="unsupported_mutation",
                    tool_name="unsupported_mutation",
                    payload={},
                    authorization_scope=WorkflowAuthorizationScope(customer_ids=[]),
                ),
            ]
        ),
        tool_registry=tool_registry,
        session_id=568,
    )

    assert isinstance(completed.workflow_result, WorkflowFailedResult)
    assert completed.workflow_result.code == "WORKFLOW_ACTION_UNSUPPORTED"
    assert tool_registry.calls == []


class FakeCustomerMemberResolver:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def resolve(
        self,
        *,
        customer_id: str,
        user_name: str,
        authorization: str,
        selected_user_id: str | None = None,
    ) -> CustomerMemberResolution:
        self.calls.append(
            {
                "customer_id": customer_id,
                "user_name": user_name,
                "authorization": authorization,
                "selected_user_id": selected_user_id,
            }
        )
        return CustomerMemberResolution(
            status="RESOLVED",
            user_id="9",
            user_name="张三",
        )


async def test_create_customer_member_resolves_server_candidate_before_confirmation() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CREATE_CUSTOMER_MEMBER",
                "intent_confidence": 0.99,
                "customer_member": {
                    "user_id": "forged-user-id",
                    "user_name": "张三",
                    "member_role": "PRESALES",
                    "access_level": "FOLLOW_UP",
                    "remark": "负责售前协作",
                    "unexpected": "must_be_dropped",
                },
            }
        )
    )
    member_resolver = FakeCustomerMemberResolver()
    tool_registry = CapturingToolRegistry()
    interaction_resolver = CanonicalConfirmationResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateFollowUpDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
                customer_member_resolver=member_resolver,
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=569,
            client_request_id="req_create_customer_member_waiting",
            input=TextTurnInput(type="text", text="把张三加为当前客户的售前协作成员,可跟进"),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(waiting, WorkflowDispatchResult)
    assert isinstance(waiting.workflow_result, WorkflowWaitingResult)
    assert waiting.workflow_result.interaction.business_action == "create_customer_member"
    assert waiting.continuation is not None
    interaction_resolver.continuation = waiting.continuation
    assert member_resolver.calls == [
        {
            "customer_id": CUSTOMER_REF.public_id,
            "user_name": "张三",
            "authorization": "Bearer test-token",
            "selected_user_id": None,
        }
    ]
    assert tool_registry.calls == []

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=569,
            client_request_id="req_create_customer_member_confirmed",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_create_customer_member",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert completed.workflow_result.assistant_text == ("已为上海星云科技有限公司添加客户成员“张三”。")
    workflow_id = waiting.workflow_result.workflow_ref.workflow_id
    assert len(tool_registry.calls) == 1
    assert tool_registry.calls[0]["name"] == "create_customer_member"
    assert tool_registry.calls[0]["payload"] == {
        "customer_id": CUSTOMER_REF.public_id,
        "member": {
            "user_id": "9",
            "member_role": "PRESALES",
            "access_level": "FOLLOW_UP",
            "remark": "负责售前协作",
        },
        "idempotency_suffix": f"{workflow_id}:create_customer_member",
    }


class AmbiguousThenSelectedCustomerMemberResolver:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def resolve(
        self,
        *,
        customer_id: str,
        user_name: str,
        authorization: str,
        selected_user_id: str | None = None,
    ) -> CustomerMemberResolution:
        self.calls.append(
            {
                "customer_id": customer_id,
                "user_name": user_name,
                "authorization": authorization,
                "selected_user_id": selected_user_id,
            }
        )
        if selected_user_id == "10":
            return CustomerMemberResolution(
                status="RESOLVED",
                user_id="10",
                user_name="张三",
            )
        return CustomerMemberResolution(
            status="AMBIGUOUS",
            candidates=(
                CustomerMemberCandidate(
                    user_id="9",
                    user_name="张三",
                    roles=("sales",),
                    already_member=False,
                ),
                CustomerMemberCandidate(
                    user_id="10",
                    user_name="张三",
                    roles=("presales",),
                    already_member=False,
                ),
            ),
        )


class CustomerMemberChoiceResolver:
    def __init__(self) -> None:
        self.continuations: dict[str, WorkflowContinuation] = {}

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> InteractionResolution:
        assert isinstance(turn.input, InteractionTurnInput)
        continuation = self.continuations[turn.input.action_id]
        if turn.input.action_id == "act_select_customer_member":
            resume = AgentTurnInput.text(
                "10",
                source="web",
                metadata={
                    "customer_member_user_id": "10",
                    "customer_member_user_name": "张三",
                },
            )
        else:
            resume = AgentTurnInput.confirm(source="web")
        return InteractionResolution(
            status="RESOLVED",
            reason_code="STRUCTURED_WORKFLOW_CONTINUATION",
            resolved_action=ResolvedAgentAction(
                action_id=turn.input.action_id,
                action_type="submit_interaction",
                continuation=continuation,
                claim_outcome="ACQUIRED",
                resume_payload=resume.model_dump(mode="json"),
            ),
        )


async def test_create_customer_member_uses_server_signed_choice_for_ambiguous_names() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CREATE_CUSTOMER_MEMBER",
                "intent_confidence": 0.99,
                "customer_member": {
                    "user_name": "张三",
                    "member_role": "PRESALES",
                    "access_level": "FOLLOW_UP",
                },
            }
        )
    )
    member_resolver = AmbiguousThenSelectedCustomerMemberResolver()
    tool_registry = CapturingToolRegistry()
    interaction_resolver = CustomerMemberChoiceResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateFollowUpDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
                customer_member_resolver=member_resolver,
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    choice = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=570,
            client_request_id="req_customer_member_choice",
            input=TextTurnInput(type="text", text="把张三加为当前客户的售前协作成员,可跟进"),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(choice, WorkflowDispatchResult)
    assert isinstance(choice.workflow_result, WorkflowWaitingResult)
    assert choice.workflow_result.interaction.interaction_type == "choice"
    assert [option.value for option in choice.workflow_result.interaction.options] == ["9", "10"]
    assert choice.workflow_result.interaction.options[1].metadata == {
        "customer_member_user_id": "10",
        "customer_member_user_name": "张三",
    }
    assert choice.continuation is not None
    interaction_resolver.continuations["act_select_customer_member"] = choice.continuation

    confirmation = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=570,
            client_request_id="req_customer_member_selected",
            input=InteractionTurnInput(type="interaction", action_id="act_select_customer_member"),
        ),
        runtime=runtime,
    )

    assert isinstance(confirmation, WorkflowDispatchResult)
    assert isinstance(confirmation.workflow_result, WorkflowWaitingResult)
    assert confirmation.workflow_result.interaction.interaction_type == "confirmation"
    assert confirmation.continuation is not None
    interaction_resolver.continuations["act_confirm_selected_customer_member"] = confirmation.continuation

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=570,
            client_request_id="req_customer_member_selected_confirmed",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_selected_customer_member",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert [call["selected_user_id"] for call in member_resolver.calls] == [None, "10"]
    assert tool_registry.calls[0]["payload"]["member"]["user_id"] == "10"


class ResolvedOpportunityProcurementResolver:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def resolve(
        self,
        *,
        customer_id: str,
        authorization: str,
        selected_method_id: int | None = None,
    ) -> ProcurementMethodResolution:
        self.calls.append(
            {
                "customer_id": customer_id,
                "authorization": authorization,
                "selected_method_id": selected_method_id,
            }
        )
        return ProcurementMethodResolution(
            status="RESOLVED",
            method_id=8,
            method_name="公开招标",
        )


class OpportunityFormThenConfirmationResolver:
    def __init__(self, *, form_values: dict[str, object] | None = None) -> None:
        self.continuations: dict[str, WorkflowContinuation] = {}
        self.form_values = form_values or {
            "total_amount": 500000,
            "user_count": 100,
            "license_type": "SUBSCRIPTION",
            "subscription_years": 2,
            "purchase_type": "NEW",
            "expected_closing_date": "2026-09-30",
        }

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> InteractionResolution:
        assert isinstance(turn.input, InteractionTurnInput)
        continuation = self.continuations[turn.input.action_id]
        if turn.input.action_id == "act_submit_opportunity_fields":
            resume = AgentTurnInput.text(
                '{"expected_closing_date":"2026-09-30","license_type":"SUBSCRIPTION",'
                '"purchase_type":"NEW","subscription_years":2,"total_amount":500000,'
                '"user_count":100}',
                source="web",
                metadata={
                    "business_action": "collect_opportunity_fields",
                    "form_values": self.form_values,
                },
            )
        else:
            resume = AgentTurnInput.confirm(source="web")
        return InteractionResolution(
            status="RESOLVED",
            reason_code="STRUCTURED_WORKFLOW_CONTINUATION",
            resolved_action=ResolvedAgentAction(
                action_id=turn.input.action_id,
                action_type="submit_interaction",
                continuation=continuation,
                claim_outcome="ACQUIRED",
                resume_payload=resume.model_dump(mode="json"),
            ),
        )


async def test_create_opportunity_collects_signed_fields_and_uses_authoritative_default() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CREATE_OPPORTUNITY",
                "intent_confidence": 0.99,
                "opportunity": {
                    "procurement_method_id": 999,
                },
            }
        )
    )
    procurement_resolver = ResolvedOpportunityProcurementResolver()
    tool_registry = CapturingToolRegistry()
    interaction_resolver = OpportunityFormThenConfirmationResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateFollowUpDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
                opportunity_procurement_method_resolver=procurement_resolver,
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    form = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=571,
            client_request_id="req_opportunity_fields",
            input=TextTurnInput(type="text", text="为当前客户创建一个商机"),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(form, WorkflowDispatchResult)
    assert isinstance(form.workflow_result, WorkflowWaitingResult)
    assert form.workflow_result.interaction.interaction_type == "form"
    assert form.workflow_result.interaction.business_action == "collect_opportunity_fields"
    assert [field.key for field in form.workflow_result.interaction.fields] == [
        "total_amount",
        "user_count",
        "license_type",
        "subscription_years",
        "purchase_type",
        "expected_closing_date",
    ]
    assert form.continuation is not None
    interaction_resolver.continuations["act_submit_opportunity_fields"] = form.continuation
    assert procurement_resolver.calls == []

    confirmation = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=571,
            client_request_id="req_opportunity_confirmation",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_submit_opportunity_fields",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(confirmation, WorkflowDispatchResult)
    assert isinstance(confirmation.workflow_result, WorkflowWaitingResult)
    assert confirmation.workflow_result.interaction.interaction_type == "confirmation"
    assert "公开招标" in confirmation.workflow_result.interaction.prompt
    assert confirmation.continuation is not None
    interaction_resolver.continuations["act_confirm_opportunity"] = confirmation.continuation

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=571,
            client_request_id="req_opportunity_completed",
            input=InteractionTurnInput(type="interaction", action_id="act_confirm_opportunity"),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert completed.workflow_result.assistant_text == "已为上海星云科技有限公司创建商机。"
    assert procurement_resolver.calls == [
        {
            "customer_id": CUSTOMER_REF.public_id,
            "authorization": "Bearer test-token",
            "selected_method_id": None,
        }
    ]
    workflow_id = form.workflow_result.workflow_ref.workflow_id
    assert tool_registry.calls[0]["name"] == "create_opportunity"
    assert tool_registry.calls[0]["payload"] == {
        "opportunity": {
            "customer_id": CUSTOMER_REF.public_id,
            "total_amount": 500000.0,
            "user_count": 100,
            "license_type": "SUBSCRIPTION",
            "subscription_years": 2,
            "purchase_type": "NEW",
            "expected_closing_date": "2026-09-30",
            "procurement_method_id": 8,
        },
        "idempotency_suffix": f"{workflow_id}:create_opportunity",
    }


async def test_create_opportunity_rejects_unsigned_form_fields_without_executing() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CREATE_OPPORTUNITY",
                "intent_confidence": 0.99,
                "opportunity": {},
            }
        )
    )
    tool_registry = CapturingToolRegistry()
    interaction_resolver = OpportunityFormThenConfirmationResolver(
        form_values={
            "total_amount": 500000,
            "user_count": 100,
            "license_type": "PERPETUAL",
            "purchase_type": "NEW",
            "expected_closing_date": "2026-09-30",
            "customer_id": "cus_forged",
            "procurement_method_id": 999,
        }
    )
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateFollowUpDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
                opportunity_procurement_method_resolver=(ResolvedOpportunityProcurementResolver()),
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    form = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=573,
            client_request_id="req_opportunity_forged_fields",
            input=TextTurnInput(type="text", text="为当前客户创建一个商机"),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(form, WorkflowDispatchResult)
    assert isinstance(form.workflow_result, WorkflowWaitingResult)
    assert form.continuation is not None
    interaction_resolver.continuations["act_submit_opportunity_fields"] = form.continuation

    failed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=573,
            client_request_id="req_opportunity_forged_fields_rejected",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_submit_opportunity_fields",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(failed, WorkflowDispatchResult)
    assert isinstance(failed.workflow_result, WorkflowFailedResult)
    assert failed.workflow_result.code == "WORKFLOW_OPPORTUNITY_FIELDS_INVALID"
    assert failed.workflow_result.message == "提交的商机信息包含未授权字段。"
    assert tool_registry.calls == []


class SelectableOpportunityProcurementResolver:
    def __init__(self) -> None:
        self.calls: list[int | None] = []

    async def resolve(
        self,
        *,
        customer_id: str,
        authorization: str,
        selected_method_id: int | None = None,
    ) -> ProcurementMethodResolution:
        assert customer_id == CUSTOMER_REF.public_id
        assert authorization == "Bearer test-token"
        self.calls.append(selected_method_id)
        if selected_method_id == 9:
            return ProcurementMethodResolution(
                status="RESOLVED",
                method_id=9,
                method_name="直接采购",
            )
        return ProcurementMethodResolution(
            status="SELECTION_REQUIRED",
            candidates=(
                ProcurementMethodCandidate(
                    method_id=8,
                    method_code="PUBLIC_BIDDING",
                    method_name="公开招标",
                ),
                ProcurementMethodCandidate(
                    method_id=9,
                    method_code="DIRECT_PURCHASE",
                    method_name="直接采购",
                ),
            ),
        )


class ExpiringOpportunityProcurementResolver:
    def __init__(self) -> None:
        self.calls: list[int | None] = []

    async def resolve(
        self,
        *,
        customer_id: str,
        authorization: str,
        selected_method_id: int | None = None,
    ) -> ProcurementMethodResolution:
        assert customer_id == CUSTOMER_REF.public_id
        assert authorization == "Bearer test-token"
        self.calls.append(selected_method_id)
        current_candidates = (
            ProcurementMethodCandidate(
                method_id=8,
                method_code="PUBLIC_BIDDING",
                method_name="公开招标",
            ),
        )
        if selected_method_id is not None:
            return ProcurementMethodResolution(
                status="NOT_FOUND",
                candidates=current_candidates,
            )
        return ProcurementMethodResolution(
            status="SELECTION_REQUIRED",
            candidates=(
                *current_candidates,
                ProcurementMethodCandidate(
                    method_id=9,
                    method_code="DIRECT_PURCHASE",
                    method_name="直接采购",
                ),
            ),
        )


class OpportunityChoiceThenConfirmationResolver:
    def __init__(self) -> None:
        self.continuations: dict[str, WorkflowContinuation] = {}

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> InteractionResolution:
        assert isinstance(turn.input, InteractionTurnInput)
        continuation = self.continuations[turn.input.action_id]
        if turn.input.action_id == "act_select_procurement_method":
            resume = AgentTurnInput.text(
                "9",
                source="web",
                metadata={
                    "business_action": "select_opportunity_procurement_method",
                    "procurement_method_id": 9,
                    "procurement_method_name": "直接采购",
                },
            )
        else:
            resume = AgentTurnInput.confirm(source="web")
        return InteractionResolution(
            status="RESOLVED",
            reason_code="STRUCTURED_WORKFLOW_CONTINUATION",
            resolved_action=ResolvedAgentAction(
                action_id=turn.input.action_id,
                action_type="submit_interaction",
                continuation=continuation,
                claim_outcome="ACQUIRED",
                resume_payload=resume.model_dump(mode="json"),
            ),
        )


async def test_create_opportunity_revalidates_server_signed_procurement_choice() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CREATE_OPPORTUNITY",
                "intent_confidence": 0.99,
                "opportunity": {
                    "procurement_method_id": 999,
                    "total_amount": 300000,
                    "user_count": 50,
                    "license_type": "PERPETUAL",
                    "purchase_type": "EXPANSION",
                    "expected_closing_date": {
                        "raw_text": "9月30日",
                        "kind": "MONTH_DAY",
                        "direction": "future",
                        "month": 9,
                        "day": 30,
                        "confidence": 0.99,
                    },
                },
            }
        )
    )
    procurement_resolver = SelectableOpportunityProcurementResolver()
    tool_registry = CapturingToolRegistry()
    interaction_resolver = OpportunityChoiceThenConfirmationResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateFollowUpDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
                opportunity_procurement_method_resolver=procurement_resolver,
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    choice = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=572,
            client_request_id="req_opportunity_procurement_choice",
            input=TextTurnInput(type="text", text="创建30万元50人买断增购商机,9月30日成交"),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(choice, WorkflowDispatchResult)
    assert isinstance(choice.workflow_result, WorkflowWaitingResult)
    assert choice.workflow_result.interaction.interaction_type == "choice"
    assert [option.value for option in choice.workflow_result.interaction.options] == ["8", "9"]
    assert choice.workflow_result.interaction.options[1].metadata == {
        "procurement_method_id": 9,
        "procurement_method_name": "直接采购",
    }
    assert choice.continuation is not None
    interaction_resolver.continuations["act_select_procurement_method"] = choice.continuation

    confirmation = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=572,
            client_request_id="req_opportunity_procurement_selected",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_select_procurement_method",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(confirmation, WorkflowDispatchResult)
    assert isinstance(confirmation.workflow_result, WorkflowWaitingResult)
    assert confirmation.workflow_result.interaction.interaction_type == "confirmation"
    assert confirmation.continuation is not None
    interaction_resolver.continuations["act_confirm_selected_procurement"] = confirmation.continuation

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=572,
            client_request_id="req_opportunity_procurement_completed",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_selected_procurement",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert procurement_resolver.calls == [None, 9]
    opportunity_payload = tool_registry.calls[0]["payload"]["opportunity"]
    assert opportunity_payload["customer_id"] == CUSTOMER_REF.public_id
    assert opportunity_payload["procurement_method_id"] == 9
    assert 999 not in opportunity_payload.values()


async def test_create_opportunity_reprompts_when_signed_procurement_choice_expires() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CREATE_OPPORTUNITY",
                "intent_confidence": 0.99,
                "opportunity": {
                    "total_amount": 300000,
                    "user_count": 50,
                    "license_type": "PERPETUAL",
                    "purchase_type": "EXPANSION",
                    "expected_closing_date": {
                        "raw_text": "9月30日",
                        "kind": "MONTH_DAY",
                        "direction": "future",
                        "month": 9,
                        "day": 30,
                        "confidence": 0.99,
                    },
                },
            }
        )
    )
    procurement_resolver = ExpiringOpportunityProcurementResolver()
    tool_registry = CapturingToolRegistry()
    interaction_resolver = OpportunityChoiceThenConfirmationResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateFollowUpDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
                opportunity_procurement_method_resolver=procurement_resolver,
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    choice = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=574,
            client_request_id="req_opportunity_expiring_procurement",
            input=TextTurnInput(type="text", text="创建30万元50人买断增购商机,9月30日成交"),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(choice, WorkflowDispatchResult)
    assert isinstance(choice.workflow_result, WorkflowWaitingResult)
    assert [option.value for option in choice.workflow_result.interaction.options] == [
        "8",
        "9",
    ]
    assert choice.continuation is not None
    interaction_resolver.continuations["act_select_procurement_method"] = choice.continuation

    refreshed_choice = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=574,
            client_request_id="req_opportunity_expired_procurement_reprompted",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_select_procurement_method",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(refreshed_choice, WorkflowDispatchResult)
    assert isinstance(refreshed_choice.workflow_result, WorkflowWaitingResult)
    assert refreshed_choice.workflow_result.interaction.interaction_type == "choice"
    assert refreshed_choice.workflow_result.interaction.prompt == ("之前选择的采购方式已失效,请重新选择。")
    assert [option.value for option in refreshed_choice.workflow_result.interaction.options] == ["8"]
    assert procurement_resolver.calls == [None, 9]
    assert tool_registry.calls == []


class ResolvedOpportunityStageResolver:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def resolve(
        self,
        *,
        customer_id: str,
        authorization: str,
        opportunity_id: str | None = None,
        opportunity_reference_text: str | None = None,
        target_stage_name: str | None = None,
        selected_opportunity_id: str | None = None,
        selected_stage_id: int | None = None,
    ) -> OpportunityStageResolution:
        self.calls.append(
            {
                "customer_id": customer_id,
                "authorization": authorization,
                "opportunity_id": opportunity_id,
                "opportunity_reference_text": opportunity_reference_text,
                "target_stage_name": target_stage_name,
                "selected_opportunity_id": selected_opportunity_id,
                "selected_stage_id": selected_stage_id,
            }
        )
        return OpportunityStageResolution(
            status="RESOLVED",
            opportunity=OpportunityStageCandidate(
                opportunity_id="opp_shanghai_001",
                opportunity_name="星云企业版采购",
                current_stage_name="需求确认",
            ),
            target_stage=OpportunityStageTransitionStep(
                stage_template_id=23,
                stage_name="方案评估",
            ),
            steps=(
                OpportunityStageTransitionStep(
                    stage_template_id=23,
                    stage_name="方案评估",
                ),
            ),
        )


class OpportunityBecomesUnauthorizedBeforeExecutionResolver:
    def __init__(self) -> None:
        self.calls = 0

    async def resolve(
        self,
        *,
        customer_id: str,
        authorization: str,
        opportunity_id: str | None = None,
        opportunity_reference_text: str | None = None,
        target_stage_name: str | None = None,
        selected_opportunity_id: str | None = None,
        selected_stage_id: int | None = None,
    ) -> OpportunityStageResolution:
        assert customer_id == CUSTOMER_REF.public_id
        assert authorization == "Bearer test-token"
        self.calls += 1
        if self.calls > 1:
            return OpportunityStageResolution(status="NOT_FOUND")
        target = OpportunityStageTransitionStep(
            stage_template_id=23,
            stage_name="方案评估",
        )
        return OpportunityStageResolution(
            status="RESOLVED",
            opportunity=OpportunityStageCandidate(
                opportunity_id="opp_shanghai_001",
                opportunity_name="星云企业版采购",
                current_stage_name="需求确认",
            ),
            target_stage=target,
            steps=(target,),
        )


async def test_move_opportunity_stage_uses_authoritative_ids_and_selected_customer_scope() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "MOVE_OPPORTUNITY_STAGE",
                "intent_confidence": 0.99,
                "opportunity_stage_transition": {
                    "opportunity_id": "opp_model_forged",
                    "opportunity_reference_text": "星云企业版采购",
                    "target_stage_name": "方案评估",
                },
            }
        )
    )
    stage_resolver = ResolvedOpportunityStageResolver()
    tool_registry = CapturingToolRegistry()
    interaction_resolver = CanonicalConfirmationResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateFollowUpDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
                opportunity_stage_resolver=stage_resolver,
            ),
            effect_executor=CRMWorkflowEffectExecutor(
                tool_registry=tool_registry,
                opportunity_stage_resolver=stage_resolver,
            ),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=575,
            client_request_id="req_move_opportunity_stage_waiting",
            input=TextTurnInput(type="text", text="把星云企业版采购推进到方案评估"),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(waiting, WorkflowDispatchResult)
    assert isinstance(waiting.workflow_result, WorkflowWaitingResult)
    assert waiting.workflow_result.interaction.interaction_type == "confirmation"
    assert "星云企业版采购" in waiting.workflow_result.interaction.prompt
    assert "方案评估" in waiting.workflow_result.interaction.prompt
    assert waiting.continuation is not None
    interaction_resolver.continuation = waiting.continuation
    assert tool_registry.calls == []

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=575,
            client_request_id="req_move_opportunity_stage_completed",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_move_opportunity_stage",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert completed.workflow_result.assistant_text == "已将商机“星云企业版采购”推进到“方案评估”。"
    assert len(tool_registry.calls) == 1
    workflow_id = waiting.workflow_result.workflow_ref.workflow_id
    assert tool_registry.calls[0]["payload"] == {
        "opportunity_id": "opp_shanghai_001",
        "stage_template_id": 23,
        "idempotency_suffix": f"{workflow_id}:move_opportunity_stage_1",
    }
    context = tool_registry.calls[0]["context"]
    assert context.allowed_customer_ids == [CUSTOMER_REF.public_id]
    assert "opp_model_forged" not in str(tool_registry.calls[0]["payload"])
    assert stage_resolver.calls == [
        {
            "customer_id": CUSTOMER_REF.public_id,
            "authorization": "Bearer test-token",
            "opportunity_id": "opp_model_forged",
            "opportunity_reference_text": "星云企业版采购",
            "target_stage_name": "方案评估",
            "selected_opportunity_id": None,
            "selected_stage_id": None,
        },
        {
            "customer_id": CUSTOMER_REF.public_id,
            "authorization": "Bearer test-token",
            "opportunity_id": None,
            "opportunity_reference_text": None,
            "target_stage_name": None,
            "selected_opportunity_id": "opp_shanghai_001",
            "selected_stage_id": 23,
        },
    ]


async def test_move_opportunity_stage_revalidates_customer_scope_before_effect() -> None:
    stage_resolver = OpportunityBecomesUnauthorizedBeforeExecutionResolver()
    tool_registry = CapturingToolRegistry()
    interaction_resolver = CanonicalConfirmationResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateFollowUpDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=StaticSemanticParser(
                    AgentSemanticParseResult.model_validate(
                        {
                            "intent": "MOVE_OPPORTUNITY_STAGE",
                            "intent_confidence": 0.99,
                            "opportunity_stage_transition": {
                                "opportunity_reference_text": "星云企业版采购",
                                "target_stage_name": "方案评估",
                            },
                        }
                    )
                ),
                temporal_resolver=FixedTemporalResolver(),
                opportunity_stage_resolver=stage_resolver,
            ),
            effect_executor=CRMWorkflowEffectExecutor(
                tool_registry=tool_registry,
                opportunity_stage_resolver=stage_resolver,
            ),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=575,
            client_request_id="req_move_opportunity_scope_waiting",
            input=TextTurnInput(type="text", text="把星云企业版采购推进到方案评估"),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(waiting, WorkflowDispatchResult)
    assert isinstance(waiting.workflow_result, WorkflowWaitingResult)
    assert waiting.continuation is not None
    interaction_resolver.continuation = waiting.continuation

    failed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=575,
            client_request_id="req_move_opportunity_scope_confirmed",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_move_opportunity_scope",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(failed, WorkflowDispatchResult)
    assert isinstance(failed.workflow_result, WorkflowFailedResult)
    assert failed.workflow_result.code == "WORKFLOW_RESOURCE_STALE"
    assert stage_resolver.calls == 2
    assert tool_registry.calls == []


class OpportunityStageInteractionResolver:
    def __init__(
        self,
        *,
        opportunity_id: str = "opp_shanghai_002",
        opportunity_name: str = "星云企业版采购",
        stage_template_id: int = 23,
        stage_name: str = "方案评估",
    ) -> None:
        self.continuations: dict[str, WorkflowContinuation] = {}
        self.opportunity_id = opportunity_id
        self.opportunity_name = opportunity_name
        self.stage_template_id = stage_template_id
        self.stage_name = stage_name

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> InteractionResolution:
        assert isinstance(turn.input, InteractionTurnInput)
        continuation = self.continuations[turn.input.action_id]
        if turn.input.action_id == "act_select_opportunity_for_stage_transition":
            resume = AgentTurnInput.text(
                "星云企业版采购",
                source="web",
                metadata={
                    "business_action": "select_opportunity_for_stage_transition",
                    "opportunity_id": self.opportunity_id,
                    "opportunity_name": self.opportunity_name,
                },
            )
        elif turn.input.action_id == "act_select_opportunity_stage":
            resume = AgentTurnInput.text(
                self.stage_name,
                source="web",
                metadata={
                    "business_action": "select_opportunity_stage",
                    "stage_template_id": self.stage_template_id,
                    "stage_name": self.stage_name,
                },
            )
        else:
            resume = AgentTurnInput.confirm(source="web")
        return InteractionResolution(
            status="RESOLVED",
            reason_code="STRUCTURED_WORKFLOW_CONTINUATION",
            resolved_action=ResolvedAgentAction(
                action_id=turn.input.action_id,
                action_type="submit_interaction",
                continuation=continuation,
                claim_outcome="ACQUIRED",
                resume_payload=resume.model_dump(mode="json"),
            ),
        )


class OpportunitySelectionThenResolvedStageResolver:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def resolve(
        self,
        *,
        customer_id: str,
        authorization: str,
        opportunity_id: str | None = None,
        opportunity_reference_text: str | None = None,
        target_stage_name: str | None = None,
        selected_opportunity_id: str | None = None,
        selected_stage_id: int | None = None,
    ) -> OpportunityStageResolution:
        self.calls.append(
            {
                "customer_id": customer_id,
                "authorization": authorization,
                "opportunity_id": opportunity_id,
                "opportunity_reference_text": opportunity_reference_text,
                "target_stage_name": target_stage_name,
                "selected_opportunity_id": selected_opportunity_id,
                "selected_stage_id": selected_stage_id,
            }
        )
        candidates = (
            OpportunityStageCandidate(
                opportunity_id="opp_shanghai_001",
                opportunity_name="星云续购项目",
                current_stage_name="需求确认",
            ),
            OpportunityStageCandidate(
                opportunity_id="opp_shanghai_002",
                opportunity_name="星云企业版采购",
                current_stage_name="需求确认",
            ),
        )
        if selected_opportunity_id != "opp_shanghai_002":
            return OpportunityStageResolution(
                status="OPPORTUNITY_SELECTION_REQUIRED",
                opportunity_candidates=candidates,
            )
        selected = candidates[1]
        target = OpportunityStageTransitionStep(
            stage_template_id=23,
            stage_name="方案评估",
        )
        return OpportunityStageResolution(
            status="RESOLVED",
            opportunity=selected,
            target_stage=target,
            steps=(target,),
        )


def opportunity_stage_semantic(
    *,
    opportunity_reference_text: str | None = "星云采购",
    target_stage_name: str | None = "方案评估",
) -> AgentSemanticParseResult:
    return AgentSemanticParseResult.model_validate(
        {
            "intent": "MOVE_OPPORTUNITY_STAGE",
            "intent_confidence": 0.99,
            "opportunity_stage_transition": {
                "opportunity_reference_text": opportunity_reference_text,
                "target_stage_name": target_stage_name,
            },
        }
    )


def build_opportunity_stage_orchestrator(
    *,
    stage_resolver: object,
    interaction_resolver: object,
    tool_registry: object,
) -> RootOrchestrator:
    return RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateFollowUpDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=StaticSemanticParser(opportunity_stage_semantic()),
                temporal_resolver=FixedTemporalResolver(),
                opportunity_stage_resolver=stage_resolver,
            ),
            effect_executor=CRMWorkflowEffectExecutor(
                tool_registry=tool_registry,
                opportunity_stage_resolver=stage_resolver,
            ),
        ),
    )


async def test_move_opportunity_stage_revalidates_server_signed_opportunity_choice() -> None:
    stage_resolver = OpportunitySelectionThenResolvedStageResolver()
    interaction_resolver = OpportunityStageInteractionResolver()
    tool_registry = CapturingToolRegistry()
    orchestrator = build_opportunity_stage_orchestrator(
        stage_resolver=stage_resolver,
        interaction_resolver=interaction_resolver,
        tool_registry=tool_registry,
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    choice = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=576,
            client_request_id="req_stage_opportunity_choice",
            input=TextTurnInput(type="text", text="把星云采购推进到方案评估"),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(choice, WorkflowDispatchResult)
    assert isinstance(choice.workflow_result, WorkflowWaitingResult)
    assert choice.workflow_result.interaction.business_action == ("select_opportunity_for_stage_transition")
    assert [option.metadata for option in choice.workflow_result.interaction.options] == [
        {
            "opportunity_id": "opp_shanghai_001",
            "opportunity_name": "星云续购项目",
        },
        {
            "opportunity_id": "opp_shanghai_002",
            "opportunity_name": "星云企业版采购",
        },
    ]
    assert choice.continuation is not None
    interaction_resolver.continuations["act_select_opportunity_for_stage_transition"] = choice.continuation

    confirmation = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=576,
            client_request_id="req_stage_opportunity_selected",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_select_opportunity_for_stage_transition",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(confirmation, WorkflowDispatchResult)
    assert isinstance(confirmation.workflow_result, WorkflowWaitingResult)
    assert confirmation.workflow_result.interaction.interaction_type == "confirmation"
    assert confirmation.continuation is not None
    interaction_resolver.continuations["act_confirm_move_opportunity_stage"] = confirmation.continuation

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=576,
            client_request_id="req_stage_opportunity_confirmed",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_move_opportunity_stage",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert [call["selected_opportunity_id"] for call in stage_resolver.calls] == [
        None,
        "opp_shanghai_002",
        "opp_shanghai_002",
    ]
    assert len(tool_registry.calls) == 1
    assert tool_registry.calls[0]["payload"]["opportunity_id"] == "opp_shanghai_002"


class StageSelectionThenResolvedStageResolver:
    def __init__(self) -> None:
        self.calls: list[int | None] = []

    async def resolve(
        self,
        *,
        customer_id: str,
        authorization: str,
        opportunity_id: str | None = None,
        opportunity_reference_text: str | None = None,
        target_stage_name: str | None = None,
        selected_opportunity_id: str | None = None,
        selected_stage_id: int | None = None,
    ) -> OpportunityStageResolution:
        assert customer_id == CUSTOMER_REF.public_id
        assert authorization == "Bearer test-token"
        self.calls.append(selected_stage_id)
        opportunity = OpportunityStageCandidate(
            opportunity_id="opp_shanghai_002",
            opportunity_name="星云企业版采购",
            current_stage_name="需求确认",
        )
        candidates = (
            OpportunityStageTransitionStep(
                stage_template_id=23,
                stage_name="方案评估",
            ),
            OpportunityStageTransitionStep(
                stage_template_id=24,
                stage_name="方案确认",
            ),
        )
        if selected_stage_id != 23:
            return OpportunityStageResolution(
                status="STAGE_SELECTION_REQUIRED",
                opportunity=opportunity,
                stage_candidates=candidates,
            )
        return OpportunityStageResolution(
            status="RESOLVED",
            opportunity=opportunity,
            target_stage=candidates[0],
            steps=(candidates[0],),
        )


async def test_move_opportunity_stage_revalidates_server_signed_stage_choice() -> None:
    stage_resolver = StageSelectionThenResolvedStageResolver()
    interaction_resolver = OpportunityStageInteractionResolver()
    tool_registry = CapturingToolRegistry()
    orchestrator = build_opportunity_stage_orchestrator(
        stage_resolver=stage_resolver,
        interaction_resolver=interaction_resolver,
        tool_registry=tool_registry,
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    choice = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=577,
            client_request_id="req_stage_choice",
            input=TextTurnInput(type="text", text="把星云采购推进到方案阶段"),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(choice, WorkflowDispatchResult)
    assert isinstance(choice.workflow_result, WorkflowWaitingResult)
    assert choice.workflow_result.interaction.business_action == "select_opportunity_stage"
    assert [option.metadata for option in choice.workflow_result.interaction.options] == [
        {"stage_template_id": 23, "stage_name": "方案评估"},
        {"stage_template_id": 24, "stage_name": "方案确认"},
    ]
    assert choice.continuation is not None
    interaction_resolver.continuations["act_select_opportunity_stage"] = choice.continuation

    confirmation = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=577,
            client_request_id="req_stage_selected",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_select_opportunity_stage",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(confirmation, WorkflowDispatchResult)
    assert isinstance(confirmation.workflow_result, WorkflowWaitingResult)
    assert confirmation.workflow_result.interaction.interaction_type == "confirmation"
    assert stage_resolver.calls == [None, 23]
    assert tool_registry.calls == []


class ExpiringOpportunityStageSelectionResolver:
    def __init__(self) -> None:
        self.calls: list[str | None] = []

    async def resolve(
        self,
        *,
        customer_id: str,
        authorization: str,
        opportunity_id: str | None = None,
        opportunity_reference_text: str | None = None,
        target_stage_name: str | None = None,
        selected_opportunity_id: str | None = None,
        selected_stage_id: int | None = None,
    ) -> OpportunityStageResolution:
        assert customer_id == CUSTOMER_REF.public_id
        assert authorization == "Bearer test-token"
        self.calls.append(selected_opportunity_id)
        current = OpportunityStageCandidate(
            opportunity_id="opp_shanghai_current",
            opportunity_name="星云当前采购",
            current_stage_name="需求确认",
        )
        if selected_opportunity_id is not None:
            return OpportunityStageResolution(
                status="OPPORTUNITY_SELECTION_REQUIRED",
                opportunity_candidates=(current,),
            )
        return OpportunityStageResolution(
            status="OPPORTUNITY_SELECTION_REQUIRED",
            opportunity_candidates=(
                OpportunityStageCandidate(
                    opportunity_id="opp_shanghai_expired",
                    opportunity_name="星云已失效采购",
                    current_stage_name="需求确认",
                ),
                current,
            ),
        )


async def test_move_opportunity_stage_reprompts_when_signed_opportunity_expires() -> None:
    stage_resolver = ExpiringOpportunityStageSelectionResolver()
    interaction_resolver = OpportunityStageInteractionResolver(
        opportunity_id="opp_shanghai_expired",
        opportunity_name="星云已失效采购",
    )
    tool_registry = CapturingToolRegistry()
    orchestrator = build_opportunity_stage_orchestrator(
        stage_resolver=stage_resolver,
        interaction_resolver=interaction_resolver,
        tool_registry=tool_registry,
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    choice = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=578,
            client_request_id="req_expiring_stage_opportunity",
            input=TextTurnInput(type="text", text="把星云采购推进到方案评估"),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(choice, WorkflowDispatchResult)
    assert isinstance(choice.workflow_result, WorkflowWaitingResult)
    assert choice.continuation is not None
    interaction_resolver.continuations["act_select_opportunity_for_stage_transition"] = choice.continuation

    refreshed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=578,
            client_request_id="req_expired_stage_opportunity_reprompted",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_select_opportunity_for_stage_transition",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(refreshed, WorkflowDispatchResult)
    assert isinstance(refreshed.workflow_result, WorkflowWaitingResult)
    assert refreshed.workflow_result.interaction.business_action == ("select_opportunity_for_stage_transition")
    assert [option.value for option in refreshed.workflow_result.interaction.options] == ["opp_shanghai_current"]
    assert stage_resolver.calls == [None, "opp_shanghai_expired"]
    assert tool_registry.calls == []


class ExpiringOpportunityStageTargetResolver:
    def __init__(self) -> None:
        self.calls: list[int | None] = []

    async def resolve(
        self,
        *,
        customer_id: str,
        authorization: str,
        opportunity_id: str | None = None,
        opportunity_reference_text: str | None = None,
        target_stage_name: str | None = None,
        selected_opportunity_id: str | None = None,
        selected_stage_id: int | None = None,
    ) -> OpportunityStageResolution:
        assert customer_id == CUSTOMER_REF.public_id
        assert authorization == "Bearer test-token"
        self.calls.append(selected_stage_id)
        opportunity = OpportunityStageCandidate(
            opportunity_id="opp_shanghai_002",
            opportunity_name="星云企业版采购",
            current_stage_name="需求确认",
        )
        current = OpportunityStageTransitionStep(
            stage_template_id=24,
            stage_name="方案确认",
        )
        if selected_stage_id is not None:
            return OpportunityStageResolution(
                status="STAGE_SELECTION_REQUIRED",
                opportunity=opportunity,
                stage_candidates=(current,),
            )
        return OpportunityStageResolution(
            status="STAGE_SELECTION_REQUIRED",
            opportunity=opportunity,
            stage_candidates=(
                OpportunityStageTransitionStep(
                    stage_template_id=23,
                    stage_name="方案评估",
                ),
                current,
            ),
        )


async def test_move_opportunity_stage_reprompts_when_signed_stage_expires() -> None:
    stage_resolver = ExpiringOpportunityStageTargetResolver()
    interaction_resolver = OpportunityStageInteractionResolver(
        stage_template_id=23,
        stage_name="方案评估",
    )
    tool_registry = CapturingToolRegistry()
    orchestrator = build_opportunity_stage_orchestrator(
        stage_resolver=stage_resolver,
        interaction_resolver=interaction_resolver,
        tool_registry=tool_registry,
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    choice = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=579,
            client_request_id="req_expiring_stage_target",
            input=TextTurnInput(type="text", text="把星云采购推进到方案阶段"),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(choice, WorkflowDispatchResult)
    assert isinstance(choice.workflow_result, WorkflowWaitingResult)
    assert choice.continuation is not None
    interaction_resolver.continuations["act_select_opportunity_stage"] = choice.continuation

    refreshed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=579,
            client_request_id="req_expired_stage_target_reprompted",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_select_opportunity_stage",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(refreshed, WorkflowDispatchResult)
    assert isinstance(refreshed.workflow_result, WorkflowWaitingResult)
    assert refreshed.workflow_result.interaction.business_action == "select_opportunity_stage"
    assert [option.value for option in refreshed.workflow_result.interaction.options] == ["24"]
    assert stage_resolver.calls == [None, 23]
    assert tool_registry.calls == []


class MultiStepOpportunityStageResolver:
    def __init__(self, *, step_count: int = 2) -> None:
        self.step_count = step_count

    async def resolve(
        self,
        *,
        customer_id: str,
        authorization: str,
        opportunity_id: str | None = None,
        opportunity_reference_text: str | None = None,
        target_stage_name: str | None = None,
        selected_opportunity_id: str | None = None,
        selected_stage_id: int | None = None,
    ) -> OpportunityStageResolution:
        assert customer_id == CUSTOMER_REF.public_id
        assert authorization == "Bearer test-token"
        available = (
            OpportunityStageTransitionStep(
                stage_template_id=23,
                stage_name="方案评估",
            ),
            OpportunityStageTransitionStep(
                stage_template_id=24,
                stage_name="方案确认",
            ),
            OpportunityStageTransitionStep(
                stage_template_id=25,
                stage_name="商务谈判",
            ),
        )
        steps = available[: self.step_count]
        if selected_stage_id is not None:
            target_index = next(
                (index for index, step in enumerate(steps) if step.stage_template_id == selected_stage_id),
                None,
            )
            if target_index is None:
                return OpportunityStageResolution(status="NOT_FOUND")
            steps = steps[: target_index + 1]
        return OpportunityStageResolution(
            status="RESOLVED",
            opportunity=OpportunityStageCandidate(
                opportunity_id="opp_shanghai_002",
                opportunity_name="星云企业版采购",
                current_stage_name="需求确认",
            ),
            target_stage=steps[-1],
            steps=steps,
        )


class FailSecondStageToolRegistry:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(
        self,
        name: str,
        context: object,
        payload: dict[str, object],
        *,
        policy: object,
    ) -> AgentToolResult:
        self.calls.append(
            {
                "name": name,
                "context": context,
                "payload": payload,
                "policy": policy,
            }
        )
        if len(self.calls) == 2:
            return AgentToolResult(
                tool_name=name,
                success=False,
                error_message="采购阶段状态已变化。",
                status_code=409,
            )
        return AgentToolResult(
            tool_name=name,
            success=True,
            data={"id": f"stage_move_{len(self.calls)}"},
        )


async def test_move_opportunity_stage_confirms_once_and_executes_all_intermediate_stages() -> None:
    interaction_resolver = OpportunityStageInteractionResolver()
    tool_registry = CapturingToolRegistry()
    orchestrator = build_opportunity_stage_orchestrator(
        stage_resolver=MultiStepOpportunityStageResolver(step_count=2),
        interaction_resolver=interaction_resolver,
        tool_registry=tool_registry,
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    confirmation = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=580,
            client_request_id="req_multistep_stage_confirmation",
            input=TextTurnInput(type="text", text="把星云采购推进到方案确认"),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(confirmation, WorkflowDispatchResult)
    assert isinstance(confirmation.workflow_result, WorkflowWaitingResult)
    assert confirmation.workflow_result.interaction.interaction_type == "confirmation"
    assert "方案评估" in confirmation.workflow_result.interaction.prompt
    assert "方案确认" in confirmation.workflow_result.interaction.prompt
    assert confirmation.continuation is not None
    interaction_resolver.continuations["act_confirm_multistep_move_opportunity_stage"] = confirmation.continuation

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=580,
            client_request_id="req_multistep_stage_confirmed",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_multistep_move_opportunity_stage",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    workflow_id = confirmation.workflow_result.workflow_ref.workflow_id
    assert [call["payload"] for call in tool_registry.calls] == [
        {
            "opportunity_id": "opp_shanghai_002",
            "stage_template_id": 23,
            "idempotency_suffix": f"{workflow_id}:move_opportunity_stage_1",
        },
        {
            "opportunity_id": "opp_shanghai_002",
            "stage_template_id": 24,
            "idempotency_suffix": f"{workflow_id}:move_opportunity_stage_2",
        },
    ]
    assert all(call["context"].allowed_customer_ids == [CUSTOMER_REF.public_id] for call in tool_registry.calls)


async def test_move_opportunity_stage_stops_after_first_failed_intermediate_stage() -> None:
    interaction_resolver = OpportunityStageInteractionResolver()
    tool_registry = FailSecondStageToolRegistry()
    orchestrator = build_opportunity_stage_orchestrator(
        stage_resolver=MultiStepOpportunityStageResolver(step_count=3),
        interaction_resolver=interaction_resolver,
        tool_registry=tool_registry,
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    confirmation = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=581,
            client_request_id="req_failing_multistep_stage_confirmation",
            input=TextTurnInput(type="text", text="把星云采购推进到商务谈判"),
            selected_entity_ref=CUSTOMER_REF,
        ),
        runtime=runtime,
    )

    assert isinstance(confirmation, WorkflowDispatchResult)
    assert isinstance(confirmation.workflow_result, WorkflowWaitingResult)
    assert confirmation.continuation is not None
    interaction_resolver.continuations["act_confirm_failing_multistep_move_opportunity_stage"] = (
        confirmation.continuation
    )

    failed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=581,
            client_request_id="req_failing_multistep_stage_confirmed",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_failing_multistep_move_opportunity_stage",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(failed, WorkflowDispatchResult)
    assert isinstance(failed.workflow_result, WorkflowFailedResult)
    assert failed.workflow_result.code == "WORKFLOW_TOOL_REJECTED"
    assert failed.workflow_result.message == "采购阶段状态已变化。"
    assert [call["payload"]["stage_template_id"] for call in tool_registry.calls] == [
        23,
        24,
    ]


class FollowUpTaskInteractionResolver:
    def __init__(self, *, task_id: str = "fut_00000000000000000000000000000002") -> None:
        self.continuations: dict[str, WorkflowContinuation] = {}
        self.task_id = task_id

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> InteractionResolution:
        assert isinstance(turn.input, InteractionTurnInput)
        continuation = self.continuations[turn.input.action_id]
        if turn.input.action_id == "act_select_follow_up_task":
            resume = AgentTurnInput.text(
                "确认预算审批",
                source="web",
                metadata={
                    "business_action": "select_follow_up_task",
                    "task_id": self.task_id,
                    "task_title": "确认预算审批",
                },
            )
        else:
            resume = AgentTurnInput.confirm(source="web")
        return InteractionResolution(
            status="RESOLVED",
            reason_code="STRUCTURED_WORKFLOW_CONTINUATION",
            resolved_action=ResolvedAgentAction(
                action_id=turn.input.action_id,
                action_type="submit_interaction",
                continuation=continuation,
                claim_outcome="ACQUIRED",
                resume_payload=resume.model_dump(mode="json"),
            ),
        )


class FollowUpTaskDelayInteractionResolver:
    def __init__(self) -> None:
        self.continuations: dict[str, WorkflowContinuation] = {}

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> InteractionResolution:
        assert isinstance(turn.input, InteractionTurnInput)
        continuation = self.continuations[turn.input.action_id]
        if turn.input.action_id == "act_supply_follow_up_postpone":
            resume = AgentTurnInput.text(
                "下周三上午十点",
                source="web",
                metadata={
                    "business_action": "collect_follow_up_task_postpone_due_at",
                },
            )
        else:
            resume = AgentTurnInput.confirm(source="web")
        return InteractionResolution(
            status="RESOLVED",
            reason_code="STRUCTURED_WORKFLOW_CONTINUATION",
            resolved_action=ResolvedAgentAction(
                action_id=turn.input.action_id,
                action_type="submit_interaction",
                continuation=continuation,
                claim_outcome="ACQUIRED",
                resume_payload=resume.model_dump(mode="json"),
            ),
        )


class NullAwareTemporalResolver:
    def __init__(self) -> None:
        self.follow_up_expressions: list[object] = []

    def resolve_follow_up_time(
        self,
        expression: object,
        *,
        base_datetime: datetime | None = None,
    ) -> str | None:
        assert base_datetime == datetime(2026, 8, 23, 9, 0, 0)
        self.follow_up_expressions.append(expression)
        if expression is None:
            return None
        return "2026-08-26T10:00:00"

    def resolve_date(
        self,
        expression: object,
        *,
        base_datetime: datetime | None = None,
    ) -> str | None:
        assert base_datetime == datetime(2026, 8, 23, 9, 0, 0)
        return None


class FollowUpTaskSelectionResolver:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.candidates = (
            FollowUpTaskCandidate(
                task_id="fut_00000000000000000000000000000001",
                title="确认合同条款",
                customer_id="cus_shanghai_001",
                customer_name="上海星云科技有限公司",
                owner_id="2",
                status="open",
                due_at="2026-08-24T10:00:00",
            ),
            FollowUpTaskCandidate(
                task_id="fut_00000000000000000000000000000002",
                title="确认预算审批",
                customer_id="cus_shanghai_001",
                customer_name="上海星云科技有限公司",
                owner_id="2",
                status="open",
                due_at="2026-08-25T10:00:00",
            ),
        )

    async def resolve(
        self,
        *,
        authorization: str,
        user_id: int,
        task_id: str | None = None,
        task_reference_text: str | None = None,
        selected_task_id: str | None = None,
    ) -> FollowUpTaskResolution:
        self.calls.append(
            {
                "authorization": authorization,
                "user_id": user_id,
                "task_id": task_id,
                "task_reference_text": task_reference_text,
                "selected_task_id": selected_task_id,
            }
        )
        authoritative_id = selected_task_id or task_id
        if authoritative_id is None:
            return FollowUpTaskResolution(
                status="SELECTION_REQUIRED",
                candidates=self.candidates,
            )
        task = next(
            (candidate for candidate in self.candidates if candidate.task_id == authoritative_id),
            None,
        )
        if task is None:
            return FollowUpTaskResolution(status="NOT_FOUND")
        return FollowUpTaskResolution(status="RESOLVED", task=task)


class FollowUpTaskNotFoundResolver:
    def __init__(self) -> None:
        self.calls: list[str | None] = []

    async def resolve(
        self,
        *,
        authorization: str,
        user_id: int,
        task_id: str | None = None,
        task_reference_text: str | None = None,
        selected_task_id: str | None = None,
    ) -> FollowUpTaskResolution:
        self.calls.append(selected_task_id or task_id)
        return FollowUpTaskResolution(status="NOT_FOUND")


class FollowUpTaskBecomesStaleResolver:
    def __init__(self) -> None:
        self.calls = 0
        self.task = FollowUpTaskCandidate(
            task_id="fut_00000000000000000000000000000002",
            title="确认预算审批",
            customer_id="cus_shanghai_001",
            customer_name="上海星云科技有限公司",
            owner_id="2",
            status="open",
            due_at="2026-08-25T10:00:00",
        )

    async def resolve(
        self,
        *,
        authorization: str,
        user_id: int,
        task_id: str | None = None,
        task_reference_text: str | None = None,
        selected_task_id: str | None = None,
    ) -> FollowUpTaskResolution:
        self.calls += 1
        if self.calls == 1:
            return FollowUpTaskResolution(status="RESOLVED", task=self.task)
        return FollowUpTaskResolution(status="NOT_FOUND")


def follow_up_transition_semantic(
    *,
    action: str = "complete",
    task_id: str | None = None,
    task_reference_text: str | None = None,
    proposed_due_at: dict[str, object] | None = None,
) -> AgentSemanticParseResult:
    return AgentSemanticParseResult.model_validate(
        {
            "intent": "FOLLOW_UP_TASK_TRANSITION",
            "intent_confidence": 0.99,
            "follow_up_task_transition": {
                "action": action,
                "task_id": task_id,
                "task_reference_text": task_reference_text,
                "proposed_due_at": proposed_due_at,
            },
        }
    )


def build_follow_up_task_orchestrator(
    *,
    semantic: AgentSemanticParseResult | None = None,
    semantic_parser: object | None = None,
    temporal_resolver: object | None = None,
    task_resolver: object,
    interaction_resolver: object,
    tool_registry: object,
) -> RootOrchestrator:
    if semantic_parser is None:
        assert semantic is not None
        semantic_parser = StaticSemanticParser(semantic)
    return RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateStandaloneWriteDecisionClassifier(
            reason_code="FOLLOW_UP_TASK_TRANSITION"
        ),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=semantic_parser,
                temporal_resolver=temporal_resolver or FixedTemporalResolver(),
                follow_up_task_resolver=task_resolver,
            ),
            effect_executor=CRMWorkflowEffectExecutor(
                tool_registry=tool_registry,
                follow_up_task_resolver=task_resolver,
            ),
        ),
    )


async def test_follow_up_task_transition_rejects_model_task_id_not_found_by_authoritative_resolver() -> None:
    task_resolver = FollowUpTaskNotFoundResolver()
    tool_registry = CapturingToolRegistry()
    orchestrator = build_follow_up_task_orchestrator(
        semantic=follow_up_transition_semantic(
            action="complete",
            task_id="fut_ffffffffffffffffffffffffffffffff",
        ),
        task_resolver=task_resolver,
        interaction_resolver=CanonicalConfirmationResolver(),
        tool_registry=tool_registry,
    )

    result = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=580,
            client_request_id="req_follow_up_task_forged_id",
            input=TextTurnInput(type="text", text="把 fut_ffffffffffffffffffffffffffffffff 标记完成"),
        ),
        runtime=RootRuntimeContext(
            db=object(),
            authorization="Bearer test-token",
            metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
        ),
    )

    assert isinstance(result, WorkflowDispatchResult)
    assert isinstance(result.workflow_result, WorkflowFailedResult)
    assert result.workflow_result.code == "WORKFLOW_FOLLOW_UP_TASK_NOT_FOUND"
    assert task_resolver.calls == ["fut_ffffffffffffffffffffffffffffffff"]
    assert tool_registry.calls == []


async def test_follow_up_task_transition_uses_server_signed_choice_and_revalidates_before_effect() -> None:
    task_resolver = FollowUpTaskSelectionResolver()
    interaction_resolver = FollowUpTaskInteractionResolver()
    tool_registry = CapturingToolRegistry()
    orchestrator = build_follow_up_task_orchestrator(
        semantic=follow_up_transition_semantic(
            action="complete",
            task_reference_text="这个跟进任务",
        ),
        task_resolver=task_resolver,
        interaction_resolver=interaction_resolver,
        tool_registry=tool_registry,
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    choice = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=581,
            client_request_id="req_follow_up_task_choice",
            input=TextTurnInput(type="text", text="把这个跟进任务标记完成"),
        ),
        runtime=runtime,
    )

    assert isinstance(choice, WorkflowDispatchResult)
    assert isinstance(choice.workflow_result, WorkflowWaitingResult)
    assert choice.workflow_result.interaction.business_action == "select_follow_up_task"
    assert [option.value for option in choice.workflow_result.interaction.options] == [
        "fut_00000000000000000000000000000001",
        "fut_00000000000000000000000000000002",
    ]
    assert choice.workflow_result.interaction.options[1].metadata == {
        "task_id": "fut_00000000000000000000000000000002",
        "task_title": "确认预算审批",
    }
    assert choice.continuation is not None
    interaction_resolver.continuations["act_select_follow_up_task"] = choice.continuation

    confirmation = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=581,
            client_request_id="req_follow_up_task_selected",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_select_follow_up_task",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(confirmation, WorkflowDispatchResult)
    assert isinstance(confirmation.workflow_result, WorkflowWaitingResult)
    assert confirmation.workflow_result.interaction.interaction_type == "confirmation"
    assert confirmation.workflow_result.interaction.prompt == (
        "确认要将上海星云科技有限公司的跟进任务“确认预算审批”标记为完成吗?"
    )
    assert confirmation.continuation is not None
    interaction_resolver.continuations["act_confirm_follow_up_task"] = confirmation.continuation

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=581,
            client_request_id="req_follow_up_task_confirmed",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_follow_up_task",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert completed.workflow_result.assistant_text == "已将跟进任务“确认预算审批”标记为完成。"
    assert [call["selected_task_id"] or call["task_id"] for call in task_resolver.calls] == [
        None,
        "fut_00000000000000000000000000000002",
        "fut_00000000000000000000000000000002",
    ]
    assert len(tool_registry.calls) == 1
    workflow_id = completed.workflow_result.workflow_ref.workflow_id
    assert tool_registry.calls[0]["name"] == "transition_follow_up_task"
    assert tool_registry.calls[0]["payload"] == {
        "task_id": "fut_00000000000000000000000000000002",
        "action": "complete",
        "proposed_due_at": None,
        "reason": None,
        "idempotency_suffix": f"{workflow_id}:transition_follow_up_task",
    }
    context = tool_registry.calls[0]["context"]
    assert isinstance(context, AgentToolContext)
    assert context.allowed_customer_ids == ["cus_shanghai_001"]


async def test_follow_up_task_transition_stops_when_task_becomes_stale_after_confirmation() -> None:
    task_resolver = FollowUpTaskBecomesStaleResolver()
    interaction_resolver = CanonicalConfirmationResolver()
    tool_registry = CapturingToolRegistry()
    orchestrator = build_follow_up_task_orchestrator(
        semantic=follow_up_transition_semantic(
            action="complete",
            task_id="fut_00000000000000000000000000000002",
        ),
        task_resolver=task_resolver,
        interaction_resolver=interaction_resolver,
        tool_registry=tool_registry,
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=582,
            client_request_id="req_follow_up_task_before_stale",
            input=TextTurnInput(type="text", text="把 fut_00000000000000000000000000000002 标记完成"),
        ),
        runtime=runtime,
    )
    assert isinstance(waiting, WorkflowDispatchResult)
    assert isinstance(waiting.workflow_result, WorkflowWaitingResult)
    assert waiting.continuation is not None
    interaction_resolver.continuation = waiting.continuation

    failed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=582,
            client_request_id="req_follow_up_task_after_stale",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_follow_up_task",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(failed, WorkflowDispatchResult)
    assert isinstance(failed.workflow_result, WorkflowFailedResult)
    assert failed.workflow_result.code == "WORKFLOW_RESOURCE_STALE"
    assert task_resolver.calls == 2
    assert tool_registry.calls == []


async def test_follow_up_task_postpone_collects_time_then_uses_system_resolved_iso() -> None:
    task_id = "fut_00000000000000000000000000000002"
    parser = SequencedSemanticParser(
        follow_up_transition_semantic(
            action="postpone",
            task_id=task_id,
        ),
        follow_up_transition_semantic(
            action="postpone",
            task_id=task_id,
            proposed_due_at={
                "raw_text": "下周三上午十点",
                "kind": "RELATIVE_WEEKDAY",
                "direction": "next",
                "weekday": 3,
                "hour": 10,
                "minute": 0,
                "confidence": 0.99,
            },
        ),
    )
    temporal_resolver = NullAwareTemporalResolver()
    task_resolver = FollowUpTaskSelectionResolver()
    interaction_resolver = FollowUpTaskDelayInteractionResolver()
    tool_registry = CapturingToolRegistry()
    orchestrator = build_follow_up_task_orchestrator(
        semantic_parser=parser,
        temporal_resolver=temporal_resolver,
        task_resolver=task_resolver,
        interaction_resolver=interaction_resolver,
        tool_registry=tool_registry,
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    missing_time = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=583,
            client_request_id="req_follow_up_task_postpone_missing_time",
            input=TextTurnInput(type="text", text=f"把 {task_id} 延期"),
        ),
        runtime=runtime,
    )

    assert isinstance(missing_time, WorkflowDispatchResult)
    assert isinstance(missing_time.workflow_result, WorkflowWaitingResult)
    assert missing_time.workflow_result.interaction.interaction_type == "text_input"
    assert (
        missing_time.workflow_result.interaction.business_action
        == "collect_follow_up_task_postpone_due_at"
    )
    assert missing_time.continuation is not None
    interaction_resolver.continuations["act_supply_follow_up_postpone"] = missing_time.continuation

    confirmation = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=583,
            client_request_id="req_follow_up_task_postpone_supplied",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_supply_follow_up_postpone",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(confirmation, WorkflowDispatchResult)
    assert isinstance(confirmation.workflow_result, WorkflowWaitingResult)
    assert confirmation.workflow_result.interaction.interaction_type == "confirmation"
    assert confirmation.workflow_result.interaction.prompt == (
        "确认要将上海星云科技有限公司的跟进任务“确认预算审批”"
        "延期到 2026-08-26T10:00:00吗?"
    )
    assert parser.messages == [
        f"把 {task_id} 延期",
        f"把 {task_id} 延期\n补充信息: 下周三上午十点",
    ]
    assert temporal_resolver.follow_up_expressions[0] is None
    assert temporal_resolver.follow_up_expressions[1] is not None
    assert confirmation.continuation is not None
    interaction_resolver.continuations["act_confirm_follow_up_postpone"] = confirmation.continuation

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=583,
            client_request_id="req_follow_up_task_postpone_confirmed",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_follow_up_postpone",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert completed.workflow_result.assistant_text == (
        "已将跟进任务“确认预算审批”延期到 2026-08-26T10:00:00。"
    )
    assert len(tool_registry.calls) == 1
    assert tool_registry.calls[0]["payload"]["proposed_due_at"] == "2026-08-26T10:00:00"


class FailingDecisionClassifier:
    async def classify(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> RootDecision:
        raise AssertionError("typed Workflow triggers must not call the decision model")


class FollowUpConfirmationCaseResolver:
    def __init__(self) -> None:
        self.calls = 0
        self.case = FollowUpTaskConfirmationCaseCandidate(
            case_id="fuc_00000000000000000000000000000001",
            status="PENDING",
            owner_id="2",
            question_text="跟进任务“确认技术评估结论”是否已经完成?",
            suggested_action="COMPLETE",
            customer_id="cus_shanghai_001",
            task_id="fut_00000000000000000000000000000001",
            expires_at="2026-08-24T09:00:00",
        )

    async def resolve(
        self,
        *,
        authorization: str,
        user_id: int,
        case_id: str,
    ) -> FollowUpTaskConfirmationCaseResolution:
        self.calls += 1
        assert authorization == "Bearer test-token"
        assert user_id == 2
        assert case_id == self.case.case_id
        return FollowUpTaskConfirmationCaseResolution(status="RESOLVED", case=self.case)


class FollowUpConfirmationReplyResolver:
    def __init__(self) -> None:
        self.continuation: WorkflowContinuation | None = None
        self.interaction_id: str | None = None

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> InteractionResolution:
        assert self.continuation is not None
        assert self.interaction_id is not None
        return InteractionResolution(
            status="RESOLVED",
            reason_code="STRUCTURED_WORKFLOW_CONTINUATION",
            resolved_action=ResolvedAgentAction(
                action_id="act_resolve_follow_up_confirmation_case",
                action_type="submit_interaction",
                continuation=self.continuation,
                claim_outcome="ACQUIRED",
                resume_payload=AgentTurnInput.text(
                    "已完成",
                    source="web",
                    metadata={
                        "business_action": "resolve_follow_up_task_confirmation_case",
                        "interaction_id": self.interaction_id,
                    },
                ).model_dump(mode="json"),
            ),
        )


async def test_follow_up_confirmation_case_reply_resumes_native_workflow_without_second_confirmation() -> None:
    case_resolver = FollowUpConfirmationCaseResolver()
    interaction_resolver = FollowUpConfirmationReplyResolver()
    tool_registry = CapturingToolRegistry()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=FailingDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=FakeSemanticParser(intent_confidence=0.80),
                temporal_resolver=FixedTemporalResolver(),
                follow_up_confirmation_case_resolver=case_resolver,
            ),
            effect_executor=CRMWorkflowEffectExecutor(
                tool_registry=tool_registry,
                follow_up_confirmation_case_resolver=case_resolver,
            ),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )

    waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=584,
            client_request_id="req_follow_up_confirmation_case_prompt",
            input=WorkflowTriggerTurnInput(
                type="workflow_trigger",
                workflow="follow_up_task_confirmation",
                resource_id="fuc_00000000000000000000000000000001",
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(waiting, WorkflowDispatchResult)
    assert isinstance(waiting.workflow_result, WorkflowWaitingResult)
    assert waiting.workflow_result.interaction.interaction_type == "choice"
    assert waiting.workflow_result.interaction.submit_on_select is True
    assert [option.value for option in waiting.workflow_result.interaction.options] == [
        "已完成",
        "先放着",
        "不管了",
    ]
    assert (
        waiting.workflow_result.interaction.business_action
        == "resolve_follow_up_task_confirmation_case"
    )
    assert waiting.continuation is not None
    interaction_resolver.continuation = waiting.continuation
    interaction_resolver.interaction_id = waiting.workflow_result.interaction.interaction_id

    completed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=584,
            client_request_id="req_follow_up_confirmation_case_reply",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_resolve_follow_up_confirmation_case",
                values={"text": "forged-client-value"},
            ),
        ),
        runtime=runtime,
    )

    assert isinstance(completed, WorkflowDispatchResult)
    assert isinstance(completed.workflow_result, WorkflowCompletedResult)
    assert completed.workflow_result.assistant_text == "已处理该跟进任务确认事项。"
    assert case_resolver.calls == 3
    assert len(tool_registry.calls) == 1
    call = tool_registry.calls[0]
    assert call["name"] == "resolve_follow_up_task_confirmation_case"
    assert call["payload"] == {
        "case_id": "fuc_00000000000000000000000000000001",
        "reply_text": "已完成",
        "idempotency_suffix": (
            f"{completed.workflow_result.workflow_ref.workflow_id}:"
            "resolve_follow_up_task_confirmation_case"
        ),
    }
    context = call["context"]
    assert isinstance(context, AgentToolContext)
    assert context.authorization_source == "workflow_resume_authorized"
    assert context.confirmed_by_user is False
    assert context.hitl_decision is None
    assert context.allowed_customer_ids == ["cus_shanghai_001"]


class MultipleFollowUpConfirmationCaseResolver:
    def __init__(self, case_ids: list[str]) -> None:
        self.cases = {
            case_id: FollowUpTaskConfirmationCaseCandidate(
                case_id=case_id,
                status="PENDING",
                owner_id="2",
                question_text=f"跟进任务“{index}”是否已经完成?",
                suggested_action="COMPLETE",
                customer_id="cus_shanghai_001",
                task_id=f"fut_{index:032x}",
                expires_at="2026-08-26T09:00:00",
            )
            for index, case_id in enumerate(case_ids, start=1)
        }

    async def resolve(
        self,
        *,
        authorization: str,
        user_id: int,
        case_id: str,
    ) -> FollowUpTaskConfirmationCaseResolution:
        assert authorization == "Bearer test-token"
        assert user_id == 2
        return FollowUpTaskConfirmationCaseResolution(
            status="RESOLVED",
            case=self.cases[case_id],
        )


class MultipleFollowUpConfirmationReplyResolver:
    def __init__(self) -> None:
        self.actions: dict[str, tuple[WorkflowContinuation, str]] = {}

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> InteractionResolution:
        del context, runtime
        assert isinstance(turn.input, InteractionTurnInput)
        continuation, interaction_id = self.actions[turn.input.action_id]
        return InteractionResolution(
            status="RESOLVED",
            reason_code="STRUCTURED_WORKFLOW_CONTINUATION",
            resolved_action=ResolvedAgentAction(
                action_id=turn.input.action_id,
                action_type="submit_interaction",
                continuation=continuation,
                claim_outcome="ACQUIRED",
                resume_payload=AgentTurnInput.text(
                    "已完成",
                    source="web",
                    metadata={
                        "business_action": "resolve_follow_up_task_confirmation_case",
                        "interaction_id": interaction_id,
                    },
                ).model_dump(mode="json"),
            ),
        )


class IdempotencyEnforcingToolRegistry:
    def __init__(self) -> None:
        self.requests: dict[str, dict[str, object]] = {}

    async def execute(
        self,
        name: str,
        context: object,
        payload: dict[str, object],
        *,
        policy: object,
    ) -> AgentToolResult:
        del context, policy
        key = f"{name}:{payload['idempotency_suffix']}"
        previous = self.requests.get(key)
        if previous is not None and previous != payload:
            return AgentToolResult(
                tool_name=name,
                success=False,
                error_message="idempotency_request_mismatch",
                status_code=409,
            )
        self.requests[key] = dict(payload)
        return AgentToolResult(
            tool_name=name,
            success=True,
            data={"id": payload["case_id"]},
        )


@pytest.mark.parametrize(
    "checkpointer_factory",
    [json_safe_checkpointer, sql_checkpointer],
    ids=["memory", "production-sql"],
)
async def test_independent_workflow_triggers_in_one_session_use_distinct_execution_identities(
    checkpointer_factory: Callable[[], BaseCheckpointSaver],
) -> None:
    case_ids = [f"fuc_{index:032x}" for index in range(1, 4)]
    case_resolver = MultipleFollowUpConfirmationCaseResolver(case_ids)
    interaction_resolver = MultipleFollowUpConfirmationReplyResolver()
    tool_registry = IdempotencyEnforcingToolRegistry()
    checkpointer = checkpointer_factory()
    orchestrator = RootOrchestrator(
        checkpointer=checkpointer,
        context_resolver=EmptyContextResolver(),
        decision_classifier=FailingDecisionClassifier(),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=FakeSemanticParser(intent_confidence=0.80),
                temporal_resolver=FixedTemporalResolver(),
                follow_up_confirmation_case_resolver=case_resolver,
            ),
            effect_executor=CRMWorkflowEffectExecutor(
                tool_registry=tool_registry,
                follow_up_confirmation_case_resolver=case_resolver,
            ),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 25, 19, 0, 0)},
    )

    waiting_results: list[WorkflowDispatchResult] = []
    for index, case_id in enumerate(case_ids, start=1):
        waiting = await orchestrator.dispatch(
            RootTurnInput(
                team_id=1,
                user_id=2,
                session_id=923,
                client_request_id=f"follow-up-confirmation:{case_id}",
                input=WorkflowTriggerTurnInput(
                    type="workflow_trigger",
                    workflow="follow_up_task_confirmation",
                    resource_id=case_id,
                ),
            ),
            runtime=runtime,
        )
        assert isinstance(waiting, WorkflowDispatchResult)
        assert isinstance(waiting.workflow_result, WorkflowWaitingResult)
        assert waiting.continuation is not None
        action_id = f"act_confirmation_{index}"
        interaction_resolver.actions[action_id] = (
            waiting.continuation,
            waiting.workflow_result.interaction.interaction_id,
        )
        waiting_results.append(waiting)

    continuations = [result.continuation for result in waiting_results]
    assert all(continuation is not None for continuation in continuations)
    checkpoint_namespaces = {
        continuation.subgraph_checkpoint_ns
        for continuation in continuations
        if continuation is not None
    }
    assert len(checkpoint_namespaces) == 3

    for case_id, waiting in zip(case_ids, waiting_results, strict=True):
        continuation = waiting.continuation
        assert continuation is not None
        checkpoint = checkpointer.get_tuple(
            {
                "configurable": {
                    "thread_id": continuation.root_thread_id,
                    "checkpoint_ns": continuation.subgraph_checkpoint_ns,
                    "checkpoint_id": continuation.subgraph_checkpoint_id,
                }
            }
        )
        assert checkpoint is not None
        child_state = checkpoint.checkpoint["channel_values"]
        child_input = WorkflowTurnInput.model_validate(child_state["workflow_input"])
        assert child_state["workflow_id"] == continuation.workflow_ref.workflow_id
        assert child_input.workflow_id == continuation.workflow_ref.workflow_id
        assert child_input.start.kind == "resource"
        assert child_input.start.resource_id == case_id
        assert child_state["workflow_result"] is None

    completed_results: list[WorkflowDispatchResult] = []
    for index in range(1, 4):
        completed = await orchestrator.dispatch(
            RootTurnInput(
                team_id=1,
                user_id=2,
                session_id=923,
                client_request_id=f"complete-confirmation:{index}",
                input=InteractionTurnInput(
                    type="interaction",
                    action_id=f"act_confirmation_{index}",
                ),
            ),
            runtime=runtime,
        )
        assert isinstance(completed, WorkflowDispatchResult)
        assert isinstance(completed.workflow_result, WorkflowCompletedResult)
        completed_results.append(completed)

    workflow_ids = {
        result.workflow_result.workflow_ref.workflow_id
        for result in waiting_results
    }
    assert len(workflow_ids) == 3
    assert len(tool_registry.requests) == 3


def test_root_rejects_terminal_workflow_result_from_another_execution() -> None:
    expected_workflow_id = "wf_00000000000000000000000000000001"
    unexpected_workflow_id = "wf_00000000000000000000000000000002"
    workflow_input = WorkflowTurnInput(
        workflow_id=expected_workflow_id,
        start={
            "kind": "resource",
            "workflow": "follow_up_task_confirmation",
            "resource_id": "fuc_00000000000000000000000000000001",
        },
        principal={"team_id": 1, "user_id": 2, "session_id": 923},
    )
    workflow_result = WorkflowCompletedResult.model_validate(
        {
            "workflow_ref": {"workflow_id": unexpected_workflow_id},
            "assistant_text": "错误地返回了另一个工作流的结果。",
            "progress": {
                "steps": [
                    {
                        "key": "execute",
                        "title": "执行操作",
                        "status": "COMPLETED",
                    }
                ]
            },
        }
    )
    decision = RootDecision(
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
        reason_code="FOLLOW_UP_TASK_CONFIRMATION_TRIGGER",
    )

    with pytest.raises(WorkflowExecutionFailedError):
        RootOrchestrator._finalize_workflow(
            {
                "decision": decision.model_dump(mode="json"),
                "resolved_action": None,
                "workflow_input": workflow_input.model_dump(mode="json"),
                "workflow_result": workflow_result.model_dump(mode="json"),
            }
        )

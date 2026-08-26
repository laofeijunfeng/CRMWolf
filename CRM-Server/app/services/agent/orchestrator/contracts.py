"""Stable contracts at the Root Orchestrator seam."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, Protocol, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, model_validator

from app.services.agent.principal import AgentPrincipal  # noqa: TC001
from app.services.agent.query import (  # noqa: TC001
    CRMQueryAgentModelConfig,
    CRMQueryAgentResult,
    CRMQuerySpec,
    EntityRef,
)
from app.services.agent.workflow import (
    WorkflowRef,
    WorkflowResult,
    WorkflowRuntimeContext,
)

TaskRelation: TypeAlias = Literal["NEW_TASK", "CONTINUE_TASK", "SWITCH_TASK"]
Route: TypeAlias = Literal["QUERY", "WORKFLOW", "CLARIFY"]
Risk: TypeAlias = Literal["READ_ONLY", "WRITE"]


class OrchestratorContractModel(BaseModel):
    """Closed-world base for Root Orchestrator contracts."""

    model_config = ConfigDict(extra="forbid", strict=True)


class TextTurnInput(OrchestratorContractModel):
    type: Literal["text"]
    text: str = Field(min_length=1, max_length=20_000)


class InteractionTurnInput(OrchestratorContractModel):
    type: Literal["interaction"]
    action_id: str = Field(min_length=1, max_length=128)
    values: dict[str, JsonValue] = Field(default_factory=dict)


class WorkflowTriggerTurnInput(OrchestratorContractModel):
    """Internal typed trigger for starting one authoritative system Workflow."""

    type: Literal["workflow_trigger"]
    workflow: Literal["follow_up_task_confirmation"]
    resource_id: str = Field(pattern=r"^fuc_[0-9a-f]{32}$")


RootUserInput: TypeAlias = Annotated[
    TextTurnInput | InteractionTurnInput | WorkflowTriggerTurnInput,
    Field(discriminator="type"),
]


class RootTurnInput(OrchestratorContractModel):
    team_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    session_id: int = Field(gt=0)
    client_request_id: str = Field(min_length=1, max_length=128)
    input: RootUserInput
    selected_entity_ref: EntityRef | None = None


class RootDecisionModelConfig(OrchestratorContractModel):
    api_host: str = Field(min_length=1, max_length=2048)
    api_key: str = Field(min_length=1, max_length=4096)
    model: str = Field(min_length=1, max_length=256)
    temperature: float = Field(default=0.0, ge=0, le=2)
    enable_thinking: bool | None = None


class ResultSetContext(OrchestratorContractModel):
    result_set_id: str = Field(min_length=1, max_length=128)
    ordered_entity_refs: list[EntityRef] = Field(default_factory=list, max_length=100)


class WorkflowContinuation(OrchestratorContractModel):
    """Exact durable continuation for one native Workflow interrupt."""

    workflow_ref: WorkflowRef
    parent_checkpoint_id: str = Field(min_length=1, max_length=128)
    subgraph_checkpoint_ns: str = Field(min_length=1, max_length=512)
    subgraph_checkpoint_id: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def require_interrupt_identity(self) -> Self:
        if self.workflow_ref.interrupt_id is None:
            raise ValueError("suspended Workflow locator requires interrupt_id")
        return self


class ResolvedAgentAction(OrchestratorContractModel):
    """Server-authorized action claim and canonical Workflow resume payload."""

    action_id: str = Field(min_length=1, max_length=128)
    action_type: Literal["submit_interaction"]
    continuation: WorkflowContinuation
    claim_outcome: Literal["ACQUIRED", "REPLAY"]
    resume_payload: dict[str, JsonValue]
    replay_message_id: int | None = Field(default=None, gt=0)

    @property
    def workflow_ref(self) -> WorkflowRef:
        return self.continuation.workflow_ref

    @model_validator(mode="after")
    def validate_replay(self) -> Self:
        if self.claim_outcome == "REPLAY" and self.replay_message_id is None:
            raise ValueError("replayed action requires replay_message_id")
        if self.claim_outcome == "ACQUIRED" and self.replay_message_id is not None:
            raise ValueError("newly acquired action cannot include replay_message_id")
        return self


class InteractionResolution(OrchestratorContractModel):
    """Authoritative binding outcome for one structured interaction."""

    status: Literal["RESOLVED", "REJECTED"]
    reason_code: str = Field(min_length=1, max_length=128)
    resolved_action: ResolvedAgentAction | None = None

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        if self.status == "RESOLVED" and self.resolved_action is None:
            raise ValueError("resolved interaction requires resolved_action")
        if self.status == "REJECTED" and self.resolved_action is not None:
            raise ValueError("rejected interaction cannot include resolved_action")
        return self


class RootContextSnapshot(OrchestratorContractModel):
    previous_query: CRMQuerySpec | None = None
    result_set: ResultSetContext | None = None
    active_workflow: WorkflowRef | None = None
    resumable_workflows: list[WorkflowRef] = Field(default_factory=list, max_length=20)


class ContextPolicy(OrchestratorContractModel):
    selected_entity: Literal["USE", "IGNORE"]
    previous_query: Literal["USE", "IGNORE"]
    result_set: Literal["USE", "IGNORE"]
    active_workflow: Literal["RESUME", "SUSPEND", "NONE"]


class RootDecision(OrchestratorContractModel):
    task_relation: TaskRelation
    route: Route
    risk: Risk
    context_policy: ContextPolicy
    confidence: float = Field(ge=0, le=1)
    reason_code: str = Field(min_length=1, max_length=128)
    evidence: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_route_risk(self) -> RootDecision:
        if self.route == "QUERY" and self.risk != "READ_ONLY":
            raise ValueError("QUERY route requires READ_ONLY risk")
        if self.route == "WORKFLOW" and self.risk != "WRITE":
            raise ValueError("WORKFLOW route requires WRITE risk")
        return self


class QueryExecutionInput(OrchestratorContractModel):
    text: str = Field(min_length=1, max_length=20_000)
    principal: AgentPrincipal
    selected_entity: EntityRef | None = None
    previous_query: CRMQuerySpec | None = None
    result_set: ResultSetContext | None = None


class ClarificationRequest(OrchestratorContractModel):
    question: str = Field(min_length=1, max_length=2000)
    reason_code: str = Field(min_length=1, max_length=128)


class AgentExecutionError(OrchestratorContractModel):
    code: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)
    retryable: bool = False


class QueryDispatchResult(OrchestratorContractModel):
    type: Literal["query"] = "query"
    decision: RootDecision
    query_result: CRMQueryAgentResult


class WorkflowDispatchResult(OrchestratorContractModel):
    type: Literal["workflow"] = "workflow"
    decision: RootDecision
    workflow_result: WorkflowResult
    continuation: WorkflowContinuation | None = Field(default=None, exclude=True)
    action_claim_id: str | None = Field(default=None, min_length=1, max_length=128, exclude=True)

    @model_validator(mode="after")
    def validate_continuation(self) -> Self:
        is_waiting = self.workflow_result.status == "WAITING"
        if is_waiting and self.continuation is None:
            raise ValueError("waiting Workflow result requires a continuation")
        if not is_waiting and self.continuation is not None:
            raise ValueError("terminal Workflow result cannot include a continuation")
        if self.continuation is not None and self.continuation.workflow_ref != self.workflow_result.workflow_ref:
            raise ValueError("Workflow continuation must match the waiting result")
        if self.workflow_result.status == "REPLAY" and self.action_claim_id is not None:
            raise ValueError("replayed Workflow result cannot consume an action again")
        return self


class ClarificationDispatchResult(OrchestratorContractModel):
    type: Literal["clarification"] = "clarification"
    decision: RootDecision
    clarification: ClarificationRequest


class FailureDispatchResult(OrchestratorContractModel):
    type: Literal["failure"] = "failure"
    decision: RootDecision | None = None
    error: AgentExecutionError
    action_claim_id: str | None = Field(default=None, min_length=1, max_length=128, exclude=True)


RootDispatchResult: TypeAlias = Annotated[
    QueryDispatchResult | WorkflowDispatchResult | ClarificationDispatchResult | FailureDispatchResult,
    Field(discriminator="type"),
]

root_dispatch_result_adapter: TypeAdapter[RootDispatchResult] = TypeAdapter(RootDispatchResult)


@dataclass(frozen=True)
class RootRuntimeContext(WorkflowRuntimeContext):
    """Root-specific runtime dependencies layered on the Workflow context."""

    permission_codes: frozenset[str] = frozenset()
    root_model_config: RootDecisionModelConfig | None = None
    query_model_config: CRMQueryAgentModelConfig | None = None


class RootContextResolver(Protocol):
    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        runtime: RootRuntimeContext,
    ) -> RootContextSnapshot: ...


class RootDecisionClassifier(Protocol):
    async def classify(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> RootDecision: ...


class QueryExecutor(Protocol):
    async def execute(
        self,
        request: QueryExecutionInput,
        *,
        runtime: RootRuntimeContext,
    ) -> CRMQueryAgentResult: ...


class InteractionResolver(Protocol):
    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> InteractionResolution: ...

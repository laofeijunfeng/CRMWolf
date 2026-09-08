"""Stable contracts at the Root Orchestrator seam."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Literal, Protocol, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, model_validator

from app.services.agent.principal import AgentPrincipal  # noqa: TC001
from app.services.agent.query import (  # noqa: TC001
    CRMQueryAgentModelConfig,
    CRMQueryAgentResult,
    CRMQuerySpec,
    EntityRef,
)
from app.services.agent.query.semantic_intent import CRMQuerySemanticIntent  # noqa: TC001
from app.services.agent.semantic_plan import AgentSemanticPlan
from app.services.agent.workflow import (
    WorkflowRef,
    WorkflowResolvedCustomer,
    WorkflowResult,
    WorkflowRuntimeContext,
)

TaskRelation: TypeAlias = Literal["NEW_TASK", "CONTINUE_TASK", "SWITCH_TASK"]
PendingCaseRelation: TypeAlias = Literal[
    "NONE", "EXPLICIT_REFERENCE", "RELATED_TO_CURRENT_ACTIVITY", "UNRELATED", "AMBIGUOUS"
]
Route: TypeAlias = Literal["QUERY", "WORKFLOW", "CLARIFY"]
Risk: TypeAlias = Literal["READ_ONLY", "WRITE"]
# Backwards-compatible names for callers of the Root contract module.
RootSemanticPlan = AgentSemanticPlan



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
    """Internal typed trigger for starting one authoritative system Workflow.

    Follow-up confirmation and opportunity-suggestion triggers deliberately
    share one transport shape.  The workflow-specific fields are validated
    together here so callers cannot manufacture a partially bound trigger.
    """

    type: Literal["workflow_trigger"]
    workflow: Literal["follow_up_task_confirmation", "customer_opportunity_suggestion"]
    resource_id: str | None = Field(default=None, pattern=r"^fuc_[0-9a-f]{32}$")
    job_public_id: str | None = Field(default=None, pattern=r"^cosj_[A-Za-z0-9_-]+$")
    action: Literal["CREATE_OPPORTUNITY", "MOVE_OPPORTUNITY_STAGE", "CANCEL"] | None = None

    @model_validator(mode="after")
    def validate_workflow_binding(self) -> Self:
        if self.workflow == "follow_up_task_confirmation":
            if self.resource_id is None or self.job_public_id is not None or self.action is not None:
                raise ValueError("follow-up trigger requires only resource_id")
            return self
        if self.resource_id is not None or self.job_public_id is None or self.action is None:
            raise ValueError("opportunity suggestion trigger requires job_public_id and action")
        return self


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
    max_tokens: int | None = Field(default=None, ge=1)


class ResultSetContext(OrchestratorContractModel):
    result_set_id: str = Field(min_length=1, max_length=128)
    ordered_entity_refs: list[EntityRef] = Field(default_factory=list, max_length=100)


class PendingCaseContext(OrchestratorContractModel):
    """Read-only context for explicitly matching a pending confirmation Case.

    The Root may use these fields to understand a user reference, but only the
    server-side matcher can turn the reference into ``case_public_id``.
    """

    case_public_id: str = Field(pattern=r"^fuc_[0-9a-f]{32}$")
    customer_name: str = Field(min_length=1, max_length=255)
    customer_aliases: list[str] = Field(default_factory=list, max_length=20)
    task_title: str = Field(min_length=1, max_length=255)
    task_description: str | None = Field(default=None, max_length=20000)
    due_at_text: str | None = Field(default=None, max_length=255)
    question_text: str = Field(min_length=1, max_length=20000)


class ConversationMessageContext(OrchestratorContractModel):
    """Small, owned slice of recent conversation supplied to Root LLM."""

    role: Literal["USER", "ASSISTANT"]
    content: str = Field(min_length=1, max_length=6000)


class RootConversationMemory(OrchestratorContractModel):
    """Durable short-term memory for one Agent session.

    This is a working memory, not a CRM fact store.  CRM identity is still
    revalidated by the Workflow planner before any business mutation.
    """

    schema_version: Literal["crm.agent.root-memory.v1"] = "crm.agent.root-memory.v1"
    resolved_customer: WorkflowResolvedCustomer | None = None
    current_task: str | None = Field(default=None, max_length=1000)
    known_activity_content: str | None = Field(default=None, max_length=12000)
    known_next_action: str | None = Field(default=None, max_length=4000)
    pending_question: str | None = Field(default=None, max_length=4000)
    last_agent_plan: str | None = Field(default=None, max_length=1000)
    user_corrections: list[str] = Field(default_factory=list, max_length=20)


class WorkflowContinuation(OrchestratorContractModel):
    """Exact durable continuation for one native Workflow interrupt.

    ``root_thread_id`` is the LangGraph thread that owns the checkpoint. A
    session may contain many independent turns, so a resumed interaction must
    return to the owning thread instead of the current turn thread.
    """

    workflow_ref: WorkflowRef
    root_thread_id: str = Field(min_length=1, max_length=512)
    parent_checkpoint_id: str = Field(min_length=1, max_length=128)
    subgraph_checkpoint_ns: str = Field(min_length=1, max_length=512)
    subgraph_checkpoint_id: str = Field(min_length=1, max_length=128)
    waiting_interaction_type: Literal[
        "choice", "form", "confirmation", "text_input"
    ] | None = None

    @model_validator(mode="after")
    def require_interrupt_identity(self) -> Self:
        if self.workflow_ref.interrupt_id is None:
            raise ValueError("suspended Workflow locator requires interrupt_id")
        return self


class ResolvedAgentAction(OrchestratorContractModel):
    """Server-authorized action claim and canonical Workflow resume payload."""

    action_id: str = Field(min_length=1, max_length=128)
    action_type: Literal["submit_interaction"]
    continuation: WorkflowContinuation | None = None
    workflow_trigger: WorkflowTriggerTurnInput | None = None
    claim_outcome: Literal["ACQUIRED", "REPLAY"]
    resume_payload: dict[str, JsonValue] = Field(default_factory=dict)
    replay_message_id: int | None = Field(default=None, gt=0)

    @property
    def workflow_ref(self) -> WorkflowRef | None:
        return self.continuation.workflow_ref if self.continuation is not None else None

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        if (self.continuation is None) == (self.workflow_trigger is None):
            raise ValueError("action requires exactly one Workflow continuation or server trigger")
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
    resumable_workflow_continuations: list[WorkflowContinuation] = Field(default_factory=list, max_length=20)
    pending_cases: list[PendingCaseContext] = Field(default_factory=list, max_length=100)
    conversation_memory: RootConversationMemory = Field(default_factory=RootConversationMemory)
    recent_messages: list[ConversationMessageContext] = Field(default_factory=list, max_length=12)


class ContextPolicy(OrchestratorContractModel):
    selected_entity: Literal["USE", "IGNORE"]
    previous_query: Literal["USE", "IGNORE"]
    result_set: Literal["USE", "IGNORE"]
    active_workflow: Literal["RESUME", "SUSPEND", "NONE"]
    conversation_memory: Literal["USE", "IGNORE"] = "USE"


class RootDecision(OrchestratorContractModel):
    task_relation: TaskRelation
    route: Route
    risk: Risk
    context_policy: ContextPolicy
    confidence: float = Field(ge=0, le=1)
    reason_code: str = Field(min_length=1, max_length=128)
    evidence: list[str] = Field(default_factory=list, max_length=20)
    # The semantic plan is required on every decision. It is the only
    # model-authored meaning shared by Root and the selected capability; a
    # missing plan must fail closed instead of silently becoming a read.
    semantic_plan: RootSemanticPlan
    # The model may provide one user-facing question when it deliberately
    # chooses CLARIFY. It is guidance only: the server still owns all
    # capability, entity, permission, and checkpoint validation.
    clarification_question: str | None = Field(default=None, max_length=2000)
    pending_case_relation: PendingCaseRelation = "NONE"
    pending_case_reference: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_route_risk(self) -> RootDecision:
        if self.route == "QUERY" and self.risk != "READ_ONLY":
            raise ValueError("QUERY route requires READ_ONLY risk")
        if self.route == "WORKFLOW" and self.risk != "WRITE":
            raise ValueError("WORKFLOW route requires WRITE risk")
        return self


class RootRoutingPlan(OrchestratorContractModel):
    """Server-owned plan for the invocation that must follow Root preflight.

    The plan is produced by the Root Graph, not by the application adapter.
    It exists because a durable Workflow resume must be invoked with the
    checkpoint locator owned by the original turn, while a new turn always
    starts on its own isolated Root thread.
    """

    kind: Literal["INTERACTION_RESUME", "INTERACTION_REPLAY", "TEXT_WORKFLOW_RESUME"]
    context: RootContextSnapshot
    decision: RootDecision
    resolved_action: ResolvedAgentAction | None = None
    continuation: WorkflowContinuation | None = None

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        if self.kind.startswith("INTERACTION") and self.resolved_action is None:
            raise ValueError("interaction routing plan requires resolved action")
        if (
            self.kind == "INTERACTION_RESUME"
            and self.resolved_action is not None
            and self.resolved_action.claim_outcome != "ACQUIRED"
        ):
            raise ValueError("interaction resume requires an acquired action")
        if (
            self.kind == "INTERACTION_REPLAY"
            and self.resolved_action is not None
            and self.resolved_action.claim_outcome != "REPLAY"
        ):
            raise ValueError("interaction replay requires a replay action")
        if self.kind == "TEXT_WORKFLOW_RESUME" and self.continuation is None:
            raise ValueError("text Workflow resume requires continuation")
        if (
            self.continuation is not None
            and self.resolved_action is not None
            and self.resolved_action.continuation is not None
            and self.continuation != self.resolved_action.continuation
        ):
            raise ValueError("routing continuation does not match resolved action")
        return self


class QueryExecutionInput(OrchestratorContractModel):
    """Server-authorized query input, optionally carrying Root semantic preflight."""

    text: str = Field(min_length=1, max_length=20_000)
    principal: AgentPrincipal
    selected_entity: EntityRef | None = None
    previous_query: CRMQuerySpec | None = None
    result_set: ResultSetContext | None = None
    semantic_intent: CRMQuerySemanticIntent | None = None
    resolved_customer: WorkflowResolvedCustomer | None = None


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
    """Root-specific runtime dependencies layered on the Workflow context.

    The semantic resolver is shared by Root and Query during one turn. These
    run-scoped registers prevent a failed preflight from being called again by
    Query, while keeping the cache isolated from other concurrent turns.
    """

    permission_codes: frozenset[str] = frozenset()
    root_model_config: RootDecisionModelConfig | None = None
    query_model_config: CRMQueryAgentModelConfig | None = None
    semantic_intent_cache: dict[str, CRMQuerySemanticIntent] = field(default_factory=dict)
    semantic_intent_failures: set[str] = field(default_factory=set)
    # A single turn may pass through Root validation more than once. Keep the
    # canonical intake result run-scoped so recovery never causes a second
    # semantic interpretation for the same user message.
    semantic_plan_cache: dict[str, AgentSemanticPlan] = field(default_factory=dict)
    semantic_plan_failures: set[str] = field(default_factory=set)


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


class SemanticIntentResolver(Protocol):
    async def resolve(
        self,
        text: str,
        *,
        model_config: CRMQueryAgentModelConfig,
        runtime: RootRuntimeContext,
    ) -> CRMQuerySemanticIntent: ...


class SemanticPlanResolver(Protocol):
    """Resolve the canonical business meaning used to recover Root routing."""

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> AgentSemanticPlan | None: ...


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

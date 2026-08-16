"""CRM AI Agent LangGraph state types."""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Annotated, Literal, Optional, TypedDict

from langgraph.types import Interrupt

from app.services.agent.input import AgentTurnInput
from app.services.agent.interrupts import AgentInterruptPayload, AgentResumePayload
from app.services.agent.pending_continuation import PendingTaskContinuationRef
from app.services.agent.schemas import (
    AgentConfirmationIntentDecision,
    AgentFollowUpQualityResult,
    AgentMemorySnapshot,
    AgentSemanticParseResult,
    AgentSuggestionResult,
    AgentTurnRelationDecision,
)
from app.services.agent.types import AgentRuntimeEventSink, JSONDict, JSONValue  # noqa: F401

AgentRuntimeApplicationAction = Literal[
    "pending_handled",
    "execute_confirmed_task",
    "run_new_flow",
    "no_pending_confirmation",
    "finish",
]


def merge_runtime_events(left: list[JSONDict], right: list[JSONDict]) -> list[JSONDict]:
    """Keep root graph events scoped to one Agent turn."""

    if right and right[0].get("event") == "agent_root_graph_started":
        return list(right)
    return [*left, *right]


_GRAPH_EVENT_RESET_MARKERS = {
    "agent_graph_invocation_started",
    "customer_resolution_graph_invocation_started",
    "creation_duplicate_graph_invocation_started",
    "business_context_graph_invocation_started",
    "follow_up_quality_graph_invocation_started",
    "pending_task_graph_invocation_started",
    "pending_preflight_graph_invocation_started",
    "pending_interaction_graph_invocation_started",
    "confirmed_task_graph_invocation_started",
    "action_review_graph_invocation_started",
    "customer_intelligence_graph_invocation_started",
}


def merge_turn_scoped_events(left: list[JSONDict], right: list[JSONDict]) -> list[JSONDict]:
    """Keep checkpointed subgraph events scoped to the current invocation."""

    if right and right[0].get("event") in _GRAPH_EVENT_RESET_MARKERS:
        return list(right)
    return [*left, *right]


def internal_graph_start_event(event_name: str) -> JSONDict:
    return {"event": event_name, "internal": True}


def visible_graph_events(events: object) -> list[JSONDict]:
    if not isinstance(events, list):
        return []
    return [
        event for event in events
        if isinstance(event, dict)
        and event.get("event") not in _GRAPH_EVENT_RESET_MARKERS
    ]


def merge_action_planning_events(left: list[JSONDict], right: list[JSONDict]) -> list[JSONDict]:
    """Keep action-planning events scoped to one Agent turn."""

    if right and right[0].get("event") == "action_planning_events_started":
        return list(right[1:])
    return [*left, *right]


class AgentGraphState(TypedDict, total=False):
    team_id: int
    user_id: int
    session_id: int
    has_db: bool
    has_authorization: bool
    content: str
    current_date: Optional[str]
    intent: Optional[str]
    memory_snapshot: JSONDict
    semantic: JSONDict
    semantic_metadata: JSONDict
    semantic_error: Optional[str]
    follow_up_quality: JSONDict
    follow_up_quality_metadata: JSONDict
    follow_up_quality_error: Optional[str]
    parsed: JSONDict
    customer_candidates: list[JSONDict]
    creation_duplicate_candidates: JSONDict
    selected_customer: JSONDict | None
    business_context: JSONDict
    read_tool_name: Optional[str]
    read_tool_payload: JSONDict
    read_tool_result: JSONDict
    read_query_type: Optional[str]
    read_query_trace_label: Optional[str]
    suggestion: JSONDict
    suggestion_metadata: JSONDict
    suggestion_error: Optional[str]
    suppress_trace_events: bool
    response: Optional[str]
    events: Annotated[list[JSONDict], merge_turn_scoped_events]


class AgentGraphInput(TypedDict, total=False):
    """Application input for one normal new-flow graph invocation."""

    db: object
    team_id: int
    user_id: int
    session_id: int
    session_context: JSONDict
    content: str
    authorization: str
    current_datetime: datetime
    events: list[JSONDict]


class AgentGraphResult(AgentGraphState, total=False):
    """Application-facing new-flow graph result."""


@dataclass
class AgentGraphSideEffects:
    """Non-serializable new-flow objects kept outside LangGraph checkpoints."""

    current_datetime: datetime | None = None
    memory: AgentMemorySnapshot | None = None
    semantic_result: AgentSemanticParseResult | None = None
    follow_up_quality_result: AgentFollowUpQualityResult | None = None
    suggestion_result: AgentSuggestionResult | None = None


class CustomerResolutionGraphState(TypedDict, total=False):
    """Serializable state for customer resolution domain workflow."""

    team_id: int
    user_id: int
    session_id: int
    has_db: bool
    has_authorization: bool
    content: str
    intent: Optional[str]
    customer_search_requested: bool
    parsed: JSONDict
    customer_candidates: list[JSONDict]
    selected_customer: JSONDict
    events: Annotated[list[JSONDict], merge_turn_scoped_events]


class CustomerResolutionGraphInput(TypedDict, total=False):
    """Application input for one customer resolution subgraph invocation."""

    db: object
    team_id: int
    user_id: int
    session_id: int
    content: str
    authorization: str
    intent: Optional[str]
    memory: AgentMemorySnapshot
    semantic_result: AgentSemanticParseResult
    parsed: JSONDict
    events: list[JSONDict]


class CustomerResolutionGraphResult(CustomerResolutionGraphState, total=False):
    """Application-facing customer resolution graph result."""


class CreationDuplicateGraphState(TypedDict, total=False):
    """Serializable state for create-lead/customer duplicate checking."""

    team_id: int
    user_id: int
    session_id: int
    has_db: bool
    has_authorization: bool
    content: str
    intent: Optional[str]
    parsed: JSONDict
    duplicate_search_requested: bool
    duplicate_skip_reason: Optional[str]
    duplicate_search_payload: JSONDict
    creation_duplicate_candidates: JSONDict
    events: Annotated[list[JSONDict], merge_turn_scoped_events]


class CreationDuplicateGraphInput(TypedDict, total=False):
    """Application input for one creation duplicate-check subgraph invocation."""

    db: object
    team_id: int
    user_id: int
    session_id: int
    content: str
    authorization: str
    semantic_result: AgentSemanticParseResult
    parsed: JSONDict
    events: list[JSONDict]


class CreationDuplicateGraphResult(CreationDuplicateGraphState, total=False):
    """Application-facing duplicate-check graph result."""


@dataclass
class CreationDuplicateRuntimeContext:
    """Run-scoped dependencies for duplicate checking."""

    db: object | None = None
    team_id: int = 0
    user_id: int = 0
    session_id: int = 0
    authorization: str | None = None
    semantic_result: AgentSemanticParseResult | None = None


class BusinessContextGraphState(TypedDict, total=False):
    """Serializable state for customer business-context workflow."""

    team_id: int
    user_id: int
    session_id: int
    has_db: bool
    has_authorization: bool
    content: str
    intent: Optional[str]
    current_date: Optional[str]
    selected_customer: JSONDict
    business_context: JSONDict
    suggestion_metadata: JSONDict
    suggestion_error: Optional[str]
    events: Annotated[list[JSONDict], merge_turn_scoped_events]


class BusinessContextGraphInput(TypedDict, total=False):
    """Application input for one business-context subgraph invocation."""

    db: object
    team_id: int
    user_id: int
    session_id: int
    content: str
    authorization: str
    current_date: str | date
    selected_customer: JSONDict
    semantic_result: AgentSemanticParseResult
    business_context: JSONDict
    events: list[JSONDict]


class BusinessContextGraphResult(BusinessContextGraphState, total=False):
    """Application-facing business-context graph result."""

    suggestion_result: AgentSuggestionResult


@dataclass
class BusinessContextGraphSideEffects:
    """Non-serializable business-context outputs kept outside checkpoints."""

    suggestion_result: AgentSuggestionResult | None = None


@dataclass
class BusinessContextRuntimeContext:
    """Run-scoped dependencies for business-context workflow."""

    db: object | None = None
    team_id: int = 0
    user_id: int = 0
    session_id: int = 0
    authorization: str | None = None
    semantic_result: AgentSemanticParseResult | None = None
    side_effects: BusinessContextGraphSideEffects = field(default_factory=BusinessContextGraphSideEffects)


class FollowUpQualityGraphState(TypedDict, total=False):
    """Serializable state for follow-up quality evaluation."""

    team_id: int
    user_id: int
    session_id: int
    has_db: bool
    content: str
    current_date: Optional[str]
    intent: Optional[str]
    has_single_customer: bool
    has_memory_customer: bool
    quality_evaluation_requested: bool
    quality_skip_reason: Optional[str]
    follow_up_quality: JSONDict
    follow_up_quality_metadata: JSONDict
    follow_up_quality_error: Optional[str]
    events: Annotated[list[JSONDict], merge_turn_scoped_events]


class FollowUpQualityGraphInput(TypedDict, total=False):
    """Application input for one follow-up quality subgraph invocation."""

    db: object
    team_id: int
    user_id: int
    session_id: int
    content: str
    current_date: str | date
    semantic_result: AgentSemanticParseResult
    memory: AgentMemorySnapshot
    has_single_customer: bool
    has_memory_customer: bool
    events: list[JSONDict]


class FollowUpQualityGraphResult(FollowUpQualityGraphState, total=False):
    """Application-facing follow-up quality graph result."""

    follow_up_quality_result: AgentFollowUpQualityResult


@dataclass
class FollowUpQualityGraphSideEffects:
    """Non-serializable follow-up quality outputs kept outside checkpoints."""

    follow_up_quality_result: AgentFollowUpQualityResult | None = None


@dataclass
class FollowUpQualityRuntimeContext:
    """Run-scoped dependencies for follow-up quality evaluation."""

    db: object | None = None
    team_id: int = 0
    user_id: int = 0
    session_id: int = 0
    semantic_result: AgentSemanticParseResult | None = None
    memory: AgentMemorySnapshot | None = None
    side_effects: FollowUpQualityGraphSideEffects = field(default_factory=FollowUpQualityGraphSideEffects)


class ActionPlanningGraphState(TypedDict, total=False):
    """Serializable state for response/action planning."""

    team_id: int
    user_id: int
    session_id: int
    content: str
    intent: Optional[str]
    parsed: JSONDict
    customer_candidates: list[JSONDict]
    selected_customer: JSONDict | None
    business_context: JSONDict
    read_tool_name: Optional[str]
    read_tool_payload: JSONDict
    read_tool_result: JSONDict
    read_query_type: Optional[str]
    read_query_trace_label: Optional[str]
    semantic: JSONDict
    semantic_metadata: JSONDict
    semantic_error: Optional[str]
    follow_up_quality: JSONDict
    follow_up_quality_metadata: JSONDict
    follow_up_quality_error: Optional[str]
    creation_duplicate_candidates: JSONDict
    suggestion: JSONDict
    suggestion_metadata: JSONDict
    suggestion_error: Optional[str]
    prior_events: list[JSONDict]
    suppress_trace_events: bool
    response_route: Optional[str]
    business_action_route: Optional[str]
    response: Optional[str]
    action: JSONDict
    events: Annotated[list[JSONDict], merge_action_planning_events]


class ActionPlanningGraphInput(TypedDict, total=False):
    """Application input for one action-planning subgraph invocation."""

    team_id: int
    user_id: int
    session_id: int
    content: str
    intent: Optional[str]
    parsed: JSONDict
    customer_candidates: list[JSONDict]
    selected_customer: JSONDict | None
    business_context: JSONDict
    semantic: JSONDict
    semantic_metadata: JSONDict
    semantic_error: Optional[str]
    follow_up_quality: JSONDict
    follow_up_quality_metadata: JSONDict
    follow_up_quality_error: Optional[str]
    creation_duplicate_candidates: JSONDict
    suggestion: JSONDict
    suggestion_metadata: JSONDict
    suggestion_error: Optional[str]
    events: list[JSONDict]
    suppress_trace_events: bool
    memory: AgentMemorySnapshot
    semantic_result: AgentSemanticParseResult
    follow_up_quality_result: AgentFollowUpQualityResult
    suggestion_result: AgentSuggestionResult


class ActionPlanningGraphResult(ActionPlanningGraphState, total=False):
    """Application-facing response/action planning graph result."""


class ResourceResolutionGraphState(TypedDict, total=False):
    """Serializable state for reusable business-resource resolution."""

    team_id: int
    user_id: int
    session_id: int
    resource_kind: str
    action_name: str
    content: str
    target: JSONDict
    candidates: list[JSONDict]
    ranked_candidates: list[JSONDict]
    selected_candidate: JSONDict
    resolution_status: str
    resolution_reason: Optional[str]
    events: list[JSONDict]


class ResourceResolutionGraphInput(TypedDict, total=False):
    """Application input for one resource-resolution graph invocation."""

    team_id: int
    user_id: int
    session_id: int
    resource_kind: str
    action_name: str
    content: str
    target: JSONDict
    candidates: list[JSONDict]


class ResourceResolutionGraphResult(ResourceResolutionGraphState, total=False):
    """Application-facing reusable resource-resolution graph result."""


ResourceResolutionRanker = Callable[[ResourceResolutionGraphState], Awaitable[list[JSONDict]]]


@dataclass
class ResourceResolutionRuntimeContext:
    """Run-scoped dependencies for reusable business-resource resolution."""

    team_id: int = 0
    user_id: int = 0
    session_id: int = 0
    ranker: ResourceResolutionRanker | None = None


class CustomerActivityPlanningGraphState(TypedDict, total=False):
    """Serializable state for customer-activity action planning."""

    team_id: int
    user_id: int
    session_id: int
    parsed: JSONDict
    customer_candidates: list[JSONDict]
    customer_name: Optional[str]
    selected_customer: JSONDict
    activity_payload: JSONDict
    customer_route: Optional[str]
    response: Optional[str]
    action: JSONDict


class CustomerActivityPlanningGraphInput(TypedDict, total=False):
    """Application input for one customer-activity planning subgraph invocation."""

    team_id: int
    user_id: int
    session_id: int
    parsed: JSONDict
    customer_candidates: list[JSONDict]


class CustomerActivityPlanningGraphResult(CustomerActivityPlanningGraphState, total=False):
    """Application-facing customer-activity planning graph result."""


@dataclass
class CustomerActivityPlanningRuntimeContext:
    """Run-scoped dependencies for customer-activity planning."""

    team_id: int = 0
    user_id: int = 0
    session_id: int = 0


class LeadPlanningGraphState(TypedDict, total=False):
    """Serializable state for lead action planning."""

    team_id: int
    user_id: int
    session_id: int
    parsed: JSONDict
    lead: JSONDict
    lead_follow_up: JSONDict
    missing_fields: list[str]
    lead_route: Optional[str]
    response: Optional[str]
    action: JSONDict


class LeadPlanningGraphInput(TypedDict, total=False):
    """Application input for one lead planning subgraph invocation."""

    team_id: int
    user_id: int
    session_id: int
    parsed: JSONDict


class LeadPlanningGraphResult(LeadPlanningGraphState, total=False):
    """Application-facing lead planning graph result."""


@dataclass
class LeadPlanningRuntimeContext:
    """Run-scoped dependencies for lead planning."""

    team_id: int = 0
    user_id: int = 0
    session_id: int = 0


class CustomerCreationPlanningGraphState(TypedDict, total=False):
    """Serializable state for customer-creation action planning."""

    team_id: int
    user_id: int
    session_id: int
    parsed: JSONDict
    customer_create: JSONDict
    customer_activity: JSONDict
    missing_fields: list[str]
    customer_create_route: Optional[str]
    response: Optional[str]
    action: JSONDict


class CustomerCreationPlanningGraphInput(TypedDict, total=False):
    """Application input for one customer-creation planning subgraph invocation."""

    team_id: int
    user_id: int
    session_id: int
    parsed: JSONDict


class CustomerCreationPlanningGraphResult(CustomerCreationPlanningGraphState, total=False):
    """Application-facing customer-creation planning graph result."""


@dataclass
class CustomerCreationPlanningRuntimeContext:
    """Run-scoped dependencies for customer-creation planning."""

    team_id: int = 0
    user_id: int = 0
    session_id: int = 0


class PaymentRecordPlanningGraphState(TypedDict, total=False):
    """Serializable state for payment-record action planning."""

    team_id: int
    user_id: int
    session_id: int
    parsed: JSONDict
    customer_candidates: list[JSONDict]
    business_context: JSONDict
    customer_name: Optional[str]
    selected_customer: JSONDict
    payment: JSONDict
    contracts: list[JSONDict]
    opportunities: list[JSONDict]
    payment_plans: list[JSONDict]
    missing_fields: list[str]
    commission_member_id: Optional[str]
    customer_route: Optional[str]
    payment_route: Optional[str]
    response: Optional[str]
    action: JSONDict


class PaymentRecordPlanningGraphInput(TypedDict, total=False):
    """Application input for one payment-record planning subgraph invocation."""

    team_id: int
    user_id: int
    session_id: int
    parsed: JSONDict
    customer_candidates: list[JSONDict]
    business_context: JSONDict


class PaymentRecordPlanningGraphResult(PaymentRecordPlanningGraphState, total=False):
    """Application-facing payment-record planning graph result."""


@dataclass
class PaymentRecordPlanningRuntimeContext:
    """Run-scoped dependencies for payment-record planning."""

    team_id: int = 0
    user_id: int = 0
    session_id: int = 0


class OpportunityPlanningGraphState(TypedDict, total=False):
    """Serializable state for opportunity action planning."""

    team_id: int
    user_id: int
    session_id: int
    parsed: JSONDict
    customer_candidates: list[JSONDict]
    customer_name: Optional[str]
    selected_customer: JSONDict
    opportunity: JSONDict
    missing_fields: list[str]
    interaction_fields: list[str]
    field_defaults: JSONDict
    customer_route: Optional[str]
    opportunity_route: Optional[str]
    response: Optional[str]
    action: JSONDict


class OpportunityPlanningGraphInput(TypedDict, total=False):
    """Application input for one opportunity planning subgraph invocation."""

    team_id: int
    user_id: int
    session_id: int
    parsed: JSONDict
    customer_candidates: list[JSONDict]


class OpportunityPlanningGraphResult(OpportunityPlanningGraphState, total=False):
    """Application-facing opportunity planning graph result."""


@dataclass
class OpportunityPlanningRuntimeContext:
    """Run-scoped dependencies for opportunity planning."""

    team_id: int = 0
    user_id: int = 0
    session_id: int = 0


class ContactPlanningGraphState(TypedDict, total=False):
    """Serializable state for contact action planning."""

    team_id: int
    user_id: int
    session_id: int
    parsed: JSONDict
    customer_candidates: list[JSONDict]
    customer_name: Optional[str]
    selected_customer: JSONDict
    contact: JSONDict
    missing_fields: list[str]
    customer_route: Optional[str]
    contact_route: Optional[str]
    response: Optional[str]
    action: JSONDict


class ContactPlanningGraphInput(TypedDict, total=False):
    """Application input for one contact planning subgraph invocation."""

    team_id: int
    user_id: int
    session_id: int
    parsed: JSONDict
    customer_candidates: list[JSONDict]


class ContactPlanningGraphResult(ContactPlanningGraphState, total=False):
    """Application-facing contact planning graph result."""


@dataclass
class ContactPlanningRuntimeContext:
    """Run-scoped dependencies for contact planning."""

    team_id: int = 0
    user_id: int = 0
    session_id: int = 0


class InvoiceTitlePlanningGraphState(TypedDict, total=False):
    """Serializable state for invoice-title action planning."""

    team_id: int
    user_id: int
    session_id: int
    parsed: JSONDict
    customer_candidates: list[JSONDict]
    customer_name: Optional[str]
    selected_customer: JSONDict
    invoice_title: JSONDict
    missing_fields: list[str]
    set_default: bool
    customer_route: Optional[str]
    invoice_title_route: Optional[str]
    response: Optional[str]
    action: JSONDict


class InvoiceTitlePlanningGraphInput(TypedDict, total=False):
    """Application input for one invoice-title planning subgraph invocation."""

    team_id: int
    user_id: int
    session_id: int
    parsed: JSONDict
    customer_candidates: list[JSONDict]


class InvoiceTitlePlanningGraphResult(InvoiceTitlePlanningGraphState, total=False):
    """Application-facing invoice-title planning graph result."""


@dataclass
class InvoiceTitlePlanningRuntimeContext:
    """Run-scoped dependencies for invoice-title planning."""

    team_id: int = 0
    user_id: int = 0
    session_id: int = 0


class DeploymentInfoPlanningGraphState(TypedDict, total=False):
    """Serializable state for deployment-info action planning."""

    team_id: int
    user_id: int
    session_id: int
    parsed: JSONDict
    customer_candidates: list[JSONDict]
    customer_name: Optional[str]
    selected_customer: JSONDict
    deployment_info: JSONDict
    missing_fields: list[str]
    customer_route: Optional[str]
    deployment_info_route: Optional[str]
    response: Optional[str]
    action: JSONDict


class DeploymentInfoPlanningGraphInput(TypedDict, total=False):
    """Application input for one deployment-info planning subgraph invocation."""

    team_id: int
    user_id: int
    session_id: int
    parsed: JSONDict
    customer_candidates: list[JSONDict]


class DeploymentInfoPlanningGraphResult(DeploymentInfoPlanningGraphState, total=False):
    """Application-facing deployment-info planning graph result."""


@dataclass
class DeploymentInfoPlanningRuntimeContext:
    """Run-scoped dependencies for deployment-info planning."""

    team_id: int = 0
    user_id: int = 0
    session_id: int = 0


class CustomerMemberPlanningGraphState(TypedDict, total=False):
    """Serializable state for customer-member action planning."""

    team_id: int
    user_id: int
    session_id: int
    parsed: JSONDict
    customer_candidates: list[JSONDict]
    business_context: JSONDict
    customer_name: Optional[str]
    selected_customer: JSONDict
    customer_member: JSONDict
    resolved_member: JSONDict
    member_error: Optional[str]
    missing_fields: list[str]
    customer_route: Optional[str]
    customer_member_route: Optional[str]
    response: Optional[str]
    action: JSONDict


class CustomerMemberPlanningGraphInput(TypedDict, total=False):
    """Application input for one customer-member planning subgraph invocation."""

    team_id: int
    user_id: int
    session_id: int
    parsed: JSONDict
    customer_candidates: list[JSONDict]
    business_context: JSONDict


class CustomerMemberPlanningGraphResult(CustomerMemberPlanningGraphState, total=False):
    """Application-facing customer-member planning graph result."""


@dataclass
class CustomerMemberPlanningRuntimeContext:
    """Run-scoped dependencies for customer-member planning."""

    team_id: int = 0
    user_id: int = 0
    session_id: int = 0


@dataclass
class ActionPlanningRuntimeContext:
    """Run-scoped dependencies for response/action planning."""

    team_id: int = 0
    user_id: int = 0
    session_id: int = 0
    memory: AgentMemorySnapshot | None = None
    semantic_result: AgentSemanticParseResult | None = None
    follow_up_quality_result: AgentFollowUpQualityResult | None = None
    suggestion_result: AgentSuggestionResult | None = None


@dataclass
class CustomerResolutionRuntimeContext:
    """Run-scoped dependencies for customer resolution."""

    db: object | None = None
    team_id: int = 0
    user_id: int = 0
    session_id: int = 0
    authorization: str | None = None
    memory: AgentMemorySnapshot | None = None
    semantic_result: AgentSemanticParseResult | None = None


@dataclass
class AgentGraphRuntimeContext:
    """Run-scoped dependencies for the new-flow LangGraph."""

    db: object | None = None
    team_id: int = 0
    user_id: int = 0
    session_id: int = 0
    session_context: JSONDict = field(default_factory=dict)
    authorization: str | None = None
    current_datetime: datetime | None = None
    side_effects: AgentGraphSideEffects = field(default_factory=AgentGraphSideEffects)


class PendingTaskEffectIntent(TypedDict, total=False):
    """Checkpoint-safe request for durable PendingTask business projection."""

    intent_id: str
    intent_type: Literal[
        "project_pending_task_state",
        "resume_suspended_task",
        "cancel_workflow_action",
    ]
    task_id: int
    expected_task: JSONDict
    task_update: JSONDict
    workflow: JSONDict
    reason: str
    source_type: str
    decision: JSONDict


class PendingTaskInternalResumePayload(TypedDict):
    """Root-owned control command for releasing a hidden child interrupt."""

    action: Literal["abort_projection"]


PendingTaskResumePayload = AgentResumePayload | PendingTaskInternalResumePayload


@dataclass(frozen=True)
class PendingTaskInternalCommand:
    """Non-checkpointed command routed through the owning root graph."""

    action: Literal["abort_projection", "resume_application_step"]
    continuation: PendingTaskContinuationRef
    expected_interrupt: AgentInterruptPayload


class PendingTaskGraphState(TypedDict, total=False):
    """Checkpoint-safe state owned by the pending-task graph.

    Application-step request identity must be derived exclusively from these
    serialized values. Runtime context may hydrate dependencies and mutable
    application models, but it is not replay-authoritative after an interrupt.
    """

    has_active_task: bool
    task_snapshot: JSONDict
    turn_input: JSONDict
    task_projection: JSONDict
    current_interrupt: AgentInterruptPayload | None
    pending_interrupt_requested: bool
    resume_payload: PendingTaskResumePayload
    resume_route: str
    suspended_candidates: list[JSONDict]
    turn_relation_decision: JSONDict
    resumed_task_id: int
    effect_intents: list[PendingTaskEffectIntent]
    projection_aborted: bool
    projection_abort_interrupt: AgentInterruptPayload
    content: str
    team_id: int
    user_id: int
    session_id: int
    handled: bool
    assistant_content: Optional[str]
    switch_notice: Optional[str]
    suspended_task_id: int
    suspend_reason: Optional[str]
    suspension_kind: Optional[str]
    selected_customer: JSONDict
    remember_pending_task: bool
    clear_pending_task_id: Optional[int]
    confirmation_decision: JSONDict
    preflight_result: JSONDict
    interaction_result: JSONDict
    events: Annotated[list[JSONDict], merge_turn_scoped_events]


class PendingTaskGraphInput(TypedDict, total=False):
    """Application input for one pending-task subgraph invocation.

    ``task_snapshot`` is the only task representation allowed across the
    application-to-graph seam. Runtime-only services may still be supplied in
    the graph context while their migration to explicit application-step
    intents is completed.
    """

    db: object
    session: object
    task_snapshot: JSONDict
    turn_input: AgentTurnInput
    content: str
    team_id: int
    user_id: int
    session_id: int
    authorization: str
    continuation_ref: PendingTaskContinuationRef
    resume_payload: PendingTaskResumePayload
    projected_resume_payload: AgentResumePayload
    suspended_candidates: list[JSONDict]
    events: list[JSONDict]


class PendingTaskGraphResult(PendingTaskGraphState, total=False):
    """Checkpoint-safe pending-task graph result."""

    __interrupt__: list[Interrupt]


@dataclass
class PendingTaskPreflightResult:
    """Runtime result from the ordinary pending preflight application module."""

    task: object = None
    handled: bool = False
    events: list[JSONDict] = field(default_factory=list)
    assistant_content: Optional[str] = None
    switch_notice: Optional[str] = None
    suspended_task: object = None
    suspend_reason: Optional[str] = None
    suspension_kind: Optional[str] = None
    clear_pending_task_id: Optional[int] = None
    confirmation_decision: object = None


@dataclass(frozen=True)
class PendingTaskTurnResult:
    """Application-facing result from one pending interaction subgraph pass."""

    handled: bool
    events: list[JSONDict] = field(default_factory=list)
    assistant_content: Optional[str] = None
    selected_customer: Optional[JSONDict] = None
    remember_pending_task: bool = False
    clear_pending_task_id: Optional[int] = None


@dataclass
class PendingTaskGraphSideEffects:
    """Non-serializable pending-task outputs kept outside graph checkpoint state."""

    task: object | None = None
    resumed_task: object | None = None
    suspended_task: object | None = None
    turn_relation_decision: AgentTurnRelationDecision | None = None
    confirmation_decision: AgentConfirmationIntentDecision | None = None
    preflight_result: object | None = None
    interaction_result: object | None = None
    event_sink: AgentRuntimeEventSink | None = None
    checkpoint_ref: PendingTaskContinuationRef | None = None


@dataclass
class PendingTaskRuntimeContext:
    """Run-scoped dependencies for the pending-task graph."""

    db: object | None = None
    session: object | None = None
    task: object | None = None
    turn_input: AgentTurnInput | None = None
    content: str = ""
    team_id: int = 0
    user_id: int = 0
    session_id: int = 0
    authorization: str | None = None
    side_effects: PendingTaskGraphSideEffects = field(default_factory=PendingTaskGraphSideEffects)


class ConfirmedTaskGraphState(TypedDict, total=False):
    """Serializable state for confirmed write execution."""

    team_id: int
    user_id: int
    session_id: int
    task_projection: JSONDict
    tool_request: JSONDict
    application_step: JSONDict
    application_step_result: JSONDict
    tool_result: JSONDict
    task_event: JSONDict
    execution_status: str
    assistant_content: Optional[str]
    executed_task_snapshot: JSONDict
    active_task_snapshot: JSONDict
    events: Annotated[list[JSONDict], merge_turn_scoped_events]


class ConfirmedTaskGraphInput(TypedDict, total=False):
    """Application input for one confirmed-task subgraph invocation."""

    db: object
    session: object
    task: object
    team_id: int
    user_id: int
    session_id: int
    authorization: str
    channel: str
    provider: str | None
    events: list[JSONDict]
    event_sink: AgentRuntimeEventSink


class ConfirmedTaskGraphResult(ConfirmedTaskGraphState, total=False):
    """Confirmed-task graph result enriched with application-facing events."""

    output_events: list[JSONDict]


@dataclass
class ConfirmedTaskExecutionResult:
    """Transport-neutral result produced inside the confirmed-task graph."""

    tool_event: JSONDict | None
    task_event: JSONDict
    assistant_content: str
    next_task: object | None = None
    progress_events: list[JSONDict] = field(default_factory=list)


@dataclass
class ConfirmedTaskGraphSideEffects:
    """Non-checkpointed outputs from confirmed-task execution."""

    execution: ConfirmedTaskExecutionResult | None = None
    tool_event: JSONDict | None = None
    task_event: JSONDict = field(default_factory=dict)
    assistant_content: str | None = None
    output_events: list[JSONDict] = field(default_factory=list)
    executed_task_snapshot: JSONDict = field(default_factory=dict)
    active_task_snapshot: JSONDict = field(default_factory=dict)


@dataclass
class ConfirmedTaskRuntimeContext:
    """Run-scoped dependencies for confirmed-task graph execution."""

    db: object | None = None
    session: object | None = None
    task: object | None = None
    team_id: int = 0
    user_id: int = 0
    session_id: int = 0
    authorization: str | None = None
    channel: str = "web"
    provider: str | None = None
    side_effects: ConfirmedTaskGraphSideEffects = field(default_factory=ConfirmedTaskGraphSideEffects)
    event_sink: AgentRuntimeEventSink | None = None


ActionReviewDecision = Literal[
    "auto_execute",
    "require_confirmation",
    "require_fields",
    "require_choice",
    "block",
]

ActionReviewRiskLevel = Literal["low", "medium", "high"]


class ActionReviewGraphState(TypedDict, total=False):
    """Serializable state for risk-aware HITL policy review."""

    team_id: int
    user_id: int
    session_id: int
    event: JSONDict
    action: str
    payload: JSONDict
    risk_level: ActionReviewRiskLevel
    execution_confidence: float
    decision: ActionReviewDecision
    reason: str
    events: Annotated[list[JSONDict], merge_turn_scoped_events]


class ActionReviewGraphInput(TypedDict, total=False):
    """Application input for one HITL policy review graph invocation."""

    event: JSONDict
    team_id: int
    user_id: int
    session_id: int
    events: list[JSONDict]


class ActionReviewGraphResult(ActionReviewGraphState, total=False):
    """Checkpoint-safe HITL policy review result."""


@dataclass
class ActionReviewRuntimeContext:
    """Run-scoped policy parameters for action review."""

    team_id: int = 0
    user_id: int = 0
    session_id: int = 0
    low_risk_auto_execute_threshold: float = 0.92


class AgentPostWriteEffects(TypedDict, total=False):
    """Durable business effects emitted by any successful write path."""

    follow_up_confirmation_case_public_ids: list[str]


class AgentTurnScope(TypedDict, total=False):
    """Checkpoint-safe identity and business ownership for one Agent turn.

    This is the authority used when deciding whether a durable business item may
    become a blocking interaction in the current LangGraph thread.
    """

    turn_id: str
    session_id: int
    channel: str
    provider: str | None
    source_message_id: str | int | None
    intent: str
    customer_id: int | None
    customer_public_id: str | None
    business_object_type: str | None
    business_object_id: str | int | None
    operation_status: str
    operation_error: str | None


class InteractionCandidate(TypedDict, total=False):
    """Normalized candidate considered by final-turn interaction arbitration."""

    interaction_id: str
    kind: str
    origin: Literal["current_turn", "durable_inbox", "channel_notification"]
    presentation: Literal["blocking_interrupt", "inline_notice", "notification_only"]
    customer_id: int | None
    customer_public_id: str | None
    case_public_id: str | None
    business_action: str
    priority: int
    payload: JSONDict


class AgentRuntimeState(TypedDict, total=False):
    """Serializable state owned by the LangGraph-native Agent root runtime."""

    team_id: int
    user_id: int
    session_id: int
    session_key: str
    channel: str
    content: str
    turn_kind: str
    turn_scope: AgentTurnScope
    interaction_candidates: list[InteractionCandidate]
    current_interrupt: AgentInterruptPayload | None
    turn_intent: JSONDict
    task_projection: JSONDict
    pending_task_snapshot: JSONDict
    suspended_candidates: list[JSONDict]
    pending_task_requested: bool
    current_customer: JSONDict
    semantic: JSONDict
    candidates: dict[str, list[JSONDict]]
    drafts: dict[str, JSONDict]
    guardrails: JSONDict
    tool_requests: list[JSONDict]
    tool_results: list[JSONDict]
    post_write_effects: AgentPostWriteEffects
    resume_payload: AgentResumePayload
    pending_task_result: JSONDict
    pending_task_outcome_intent: JSONDict
    pending_task_continuation_ref: PendingTaskContinuationRef | None
    pending_task_resume_error: str | None
    new_flow_result: JSONDict
    customer_intelligence_requested: bool
    customer_intelligence_event: JSONDict
    customer_intelligence_requests: list[JSONDict]
    customer_intelligence_schedule_intent: JSONDict
    customer_intelligence_result: JSONDict
    runtime_status: str
    runtime_retryable: bool
    pending_interrupt_projection: JSONDict
    route: str
    application_action: AgentRuntimeApplicationAction
    pending_task_handled: bool
    checkpoint_unavailable: bool
    fallback_reason: str
    assistant_content: Optional[str]
    switch_notice: Optional[str]
    deferred_final_events: list[JSONDict]
    follow_up_confirmation_projection_suppressed: bool
    follow_up_confirmation_discard_reason: Optional[str]
    events: Annotated[list[JSONDict], merge_runtime_events]


class AgentRuntimeStateHistoryItem(TypedDict, total=False):
    """Checkpoint-safe projection of one root graph state snapshot."""

    checkpoint_id: str
    parent_checkpoint_id: str
    thread_id: str
    checkpoint_ns: str
    created_at: str
    source: str
    step: int
    next_nodes: list[str]
    has_interrupt: bool
    interrupts: list[JSONDict]
    values: JSONDict


@dataclass(frozen=True)
class AgentSessionRuntimeProjection:
    """Checkpoint-safe projection of non-HITL session memory for one Agent turn."""

    session_context: JSONDict = field(default_factory=dict)
    current_customer: JSONDict = field(default_factory=dict)


class AgentRuntimeInvokeResult(AgentRuntimeState, total=False):
    __interrupt__: list[Interrupt]


@dataclass
class AgentRootRuntimeSideEffects:
    """Non-checkpointed outputs produced by root graph runtime nodes."""

    pending_task_result: PendingTaskGraphResult | None = None
    confirmed_task_result: ConfirmedTaskGraphResult | None = None
    pending_task_events: list[JSONDict] = field(default_factory=list)
    pending_task_assistant_content: str | None = None
    pending_task_switch_notice: str | None = None
    new_flow_events: list[JSONDict] = field(default_factory=list)
    new_flow_assistant_content: str | None = None
    current_interrupt: AgentInterruptPayload | None = None
    customer_intelligence_result: JSONDict | None = None
    customer_intelligence_events: list[JSONDict] = field(default_factory=list)
    customer_intelligence_assistant_content: str | None = None
    confirmed_task_events: list[JSONDict] = field(default_factory=list)
    confirmed_task_assistant_content: str | None = None
    no_pending_confirmation_events: list[JSONDict] = field(default_factory=list)
    no_pending_confirmation_assistant_content: str | None = None
    business_interaction_events: list[JSONDict] = field(default_factory=list)
    business_interaction_assistant_content: str | None = None
    pending_task_graph_side_effects: PendingTaskGraphSideEffects | None = None


@dataclass
class AgentRuntimeTurnOutput:
    """Application-facing event stream and final assistant text for one turn."""

    events: list[JSONDict] = field(default_factory=list)
    assistant_content: str | None = None
    switch_notice: str | None = None


@dataclass
class AgentApplicationRuntimeResult:
    """Application-facing projection of one root graph invocation."""

    state: AgentRuntimeState = field(default_factory=dict)
    turn_output: AgentRuntimeTurnOutput = field(default_factory=AgentRuntimeTurnOutput)
    pending_task_result: PendingTaskGraphResult = field(default_factory=dict)
    checkpoint_unavailable: bool = False


@dataclass
class AgentRuntimeContext:
    """Run-scoped context for non-serializable dependencies.

    LangGraph state remains checkpoint-safe JSON-ish data. DB sessions, ORM
    objects, and transport credentials live here for the duration of one invoke.
    """

    db: object | None = None
    session: object | None = None
    task: object | None = None
    turn_input: AgentTurnInput | None = None
    content: str = ""
    team_id: int = 0
    user_id: int = 0
    session_id: int = 0
    user_message_id: int | None = None
    authorization: str | None = None
    switch_notice: str | None = None
    customer_intelligence_event: object | None = None
    customer_intelligence_requests: list[JSONDict] = field(default_factory=list)
    side_effects: AgentRootRuntimeSideEffects = field(default_factory=AgentRootRuntimeSideEffects)
    event_sink: AgentRuntimeEventSink | None = None
    internal_pending_command: PendingTaskInternalCommand | None = None

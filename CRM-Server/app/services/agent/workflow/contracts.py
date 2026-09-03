"""Typed contracts owned by the durable Workflow module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, model_serializer, model_validator

from app.services.agent.durable_work_contracts import AgentDurableWorkReceipt  # noqa: TC001
from app.services.agent.principal import AgentPrincipal  # noqa: TC001
from app.services.agent.query.schemas import EntityRef  # noqa: TC001
from app.services.agent.semantic_plan import AgentSemanticPlan  # noqa: TC001

if TYPE_CHECKING:
    from pydantic.functional_serializers import SerializerFunctionWrapHandler


class WorkflowContractModel(BaseModel):
    """Closed-world base for Workflow inputs, interrupts, and results."""

    model_config = ConfigDict(extra="forbid", strict=True)


@dataclass(frozen=True)
class WorkflowRuntimeContext:
    """Run-scoped dependencies required by Workflow planning and execution."""

    db: object | None = None
    authorization: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    deadline_at: float | None = None


class WorkflowRef(WorkflowContractModel):
    """Durable identity of one Workflow and its current interrupt, if any."""

    workflow_id: str = Field(min_length=1, max_length=128)
    interrupt_id: str | None = Field(default=None, min_length=1, max_length=128)


class WorkflowInteractionOption(WorkflowContractModel):
    value: str = Field(min_length=1, max_length=500)
    label: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    disabled: bool = False
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class WorkflowInteractionField(WorkflowContractModel):
    key: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=200)
    field_type: Literal[
        "text",
        "textarea",
        "number",
        "date",
        "datetime",
        "select",
        "multi_select",
        "boolean",
    ]
    required: bool = False
    placeholder: str | None = Field(default=None, max_length=200)
    default_value: JsonValue = None
    min_length: int | None = Field(default=None, ge=0, le=10_000)
    max_length: int | None = Field(default=None, ge=1, le=10_000)
    minimum: float | None = None
    maximum: float | None = None
    options: list[WorkflowInteractionOption] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_constraints(self) -> Self:
        if self.min_length is not None and self.max_length is not None and self.min_length > self.max_length:
            raise ValueError("min_length cannot exceed max_length")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum cannot exceed maximum")
        if self.field_type in {"select", "multi_select"} and not self.options:
            raise ValueError("select fields require options")
        if self.field_type not in {"select", "multi_select"} and self.options:
            raise ValueError("options are only valid for select fields")
        return self


class WorkflowInteraction(WorkflowContractModel):
    """Channel-neutral request for the next user interaction."""

    interaction_id: str = Field(min_length=1, max_length=128)
    interaction_type: Literal["choice", "form", "confirmation", "text_input"]
    business_action: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=10_000)
    options: list[WorkflowInteractionOption] = Field(default_factory=list, max_length=50)
    fields: list[WorkflowInteractionField] = Field(default_factory=list, max_length=20)
    selection_mode: Literal["single", "multiple"] | None = None
    min_selections: int | None = Field(default=None, ge=0, le=50)
    max_selections: int | None = Field(default=None, ge=1, le=50)
    allow_blank: bool | None = None
    submit_on_select: bool = False
    submit_label: str = Field(default="提交", min_length=1, max_length=200)
    allow_cancel: bool = True

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        if len({option.value for option in self.options}) != len(self.options):
            raise ValueError("interaction option values must be unique")
        if (
            self.min_selections is not None
            and self.max_selections is not None
            and self.min_selections > self.max_selections
        ):
            raise ValueError("min_selections cannot exceed max_selections")
        if self.interaction_type in {"choice", "confirmation"}:
            if not self.options:
                raise ValueError("choice interactions require options")
            if self.selection_mode is None:
                raise ValueError("choice interactions require selection_mode")
        elif self.options or self.selection_mode is not None:
            raise ValueError("options are only valid for choice interactions")
        if self.interaction_type == "form" and not self.fields:
            raise ValueError("form interactions require fields")
        if self.interaction_type != "form" and self.fields:
            raise ValueError("fields are only valid for form interactions")
        if self.interaction_type == "text_input" and self.allow_blank is None:
            raise ValueError("text input interactions require allow_blank")
        if self.interaction_type != "text_input" and self.allow_blank is not None:
            raise ValueError("allow_blank is only valid for text input interactions")
        if self.submit_on_select and (
            self.interaction_type != "choice"
            or self.selection_mode != "single"
            or self.min_selections != 1
            or self.max_selections != 1
        ):
            raise ValueError("submit_on_select requires an exact single-choice interaction")
        return self


WorkflowProgressStatus: TypeAlias = Literal[
    "PENDING",
    "RUNNING",
    "COMPLETED",
    "WAITING",
    "FAILED",
    "CANCELLED",
]


class WorkflowProgressStep(WorkflowContractModel):
    """One business-readable Workflow stage, independent of transport and UI."""

    key: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    title: str = Field(min_length=1, max_length=200)
    status: WorkflowProgressStatus
    description: str | None = Field(default=None, max_length=2_000)


class WorkflowProgress(WorkflowContractModel):
    """Authoritative progress snapshot persisted with Workflow state and results."""

    steps: list[WorkflowProgressStep] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def require_unique_step_keys(self) -> Self:
        keys = [step.key for step in self.steps]
        if len(keys) != len(set(keys)):
            raise ValueError("Workflow progress step keys must be unique")
        return self


class WorkflowInterruptPayload(WorkflowContractModel):
    """Payload persisted by LangGraph when a Workflow waits for user input."""

    schema_version: Literal["crm.workflow.interrupt.v2"] = "crm.workflow.interrupt.v2"
    workflow_id: str = Field(min_length=1, max_length=128)
    interaction: WorkflowInteraction
    progress: WorkflowProgress


class WorkflowSupplement(WorkflowContractModel):
    """One canonical text or form response supplied while a Workflow is suspended."""

    content: str = Field(min_length=1, max_length=20_000)
    source: str = Field(min_length=1, max_length=128)
    provider: str | None = Field(default=None, max_length=128)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class WorkflowResolvedCustomer(WorkflowContractModel):
    """Customer identity cached in the Workflow checkpoint after resolution.

    ``lookup_name`` is only a comparison hint for deciding whether a later
    supplement still refers to this customer. Authorization and existence are
    revalidated by the CRM resolver before the next plan is built.
    """

    customer_id: str = Field(pattern=r"^cus_[A-Za-z0-9_-]+$", min_length=5, max_length=128)
    customer_name: str = Field(min_length=1, max_length=255)
    lookup_name: str | None = Field(default=None, min_length=1, max_length=255)


class WorkflowTextStart(WorkflowContractModel):
    kind: Literal["text"]
    text: str = Field(min_length=1, max_length=20_000)
    # The Root has already understood this turn.  The Workflow may use this
    # hint for consistency, but still owns detailed field extraction and CRM
    # command validation.
    semantic_plan: AgentSemanticPlan | None = None

    @model_serializer(mode="wrap")
    def serialize_without_empty_plan(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        payload = handler(self)
        if self.semantic_plan is None:
            payload.pop("semantic_plan", None)
        return payload


class WorkflowResourceStart(WorkflowContractModel):
    kind: Literal["resource"]
    workflow: Literal["follow_up_task_confirmation"]
    resource_id: str = Field(pattern=r"^fuc_[0-9a-f]{32}$")


class WorkflowOpportunitySuggestionStart(WorkflowContractModel):
    """Start a customer-scoped opportunity action from a durable suggestion."""

    kind: Literal["opportunity_suggestion"]
    action: Literal["CREATE_OPPORTUNITY", "MOVE_OPPORTUNITY_STAGE", "CANCEL"]
    job_public_id: str = Field(pattern=r"^cosj_[A-Za-z0-9_-]+$", min_length=6, max_length=128)


WorkflowStart: TypeAlias = Annotated[
    WorkflowTextStart | WorkflowResourceStart | WorkflowOpportunitySuggestionStart,
    Field(discriminator="kind"),
]


class WorkflowTurnInput(WorkflowContractModel):
    """Canonical identity, typed start, and signed supplements for one Workflow."""

    workflow_id: str = Field(pattern=r"^wf_[0-9a-f]{32}$")
    start: WorkflowStart
    principal: AgentPrincipal
    selected_entity: EntityRef | None = None
    resolved_customer: WorkflowResolvedCustomer | None = None
    supplements: list[WorkflowSupplement] = Field(default_factory=list, max_length=20)


class WorkflowWaitingResult(WorkflowContractModel):
    status: Literal["WAITING"] = "WAITING"
    workflow_ref: WorkflowRef
    assistant_text: str = Field(min_length=1, max_length=10_000)
    interaction: WorkflowInteraction
    progress: WorkflowProgress


class WorkflowCompletedResult(WorkflowContractModel):
    status: Literal["COMPLETED"] = "COMPLETED"
    workflow_ref: WorkflowRef
    assistant_text: str = Field(min_length=1, max_length=10_000)
    progress: WorkflowProgress
    durable_work: list[AgentDurableWorkReceipt] = Field(default_factory=list, max_length=20)


class WorkflowFailedResult(WorkflowContractModel):
    status: Literal["FAILED"] = "FAILED"
    workflow_ref: WorkflowRef | None = None
    code: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2_000)
    retryable: bool = False
    progress: WorkflowProgress


class WorkflowReplayResult(WorkflowContractModel):
    status: Literal["REPLAY"] = "REPLAY"
    workflow_ref: WorkflowRef
    message_id: int = Field(gt=0)


class WorkflowCancelledResult(WorkflowContractModel):
    status: Literal["CANCELLED"] = "CANCELLED"
    workflow_ref: WorkflowRef
    assistant_text: str = Field(min_length=1, max_length=10_000)
    progress: WorkflowProgress


class WorkflowSkippedResult(WorkflowContractModel):
    """A successful no-op when the target has already changed or been handled.

    Skips are intentionally not user-facing business messages.  The progress
    snapshot remains available to the UI and audit layers, while the composer
    renders no assistant text.
    """

    status: Literal["SKIPPED"] = "SKIPPED"
    workflow_ref: WorkflowRef
    progress: WorkflowProgress
    reason: str = Field(min_length=1, max_length=2_000)


class WorkflowCommandBinding(WorkflowContractModel):
    """Bind one earlier command result into a later command payload."""

    target_path: list[str] = Field(min_length=1, max_length=8)
    source_command_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    source_path: list[str] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_paths(self) -> Self:
        for path in (self.target_path, self.source_path):
            if any(not segment or len(segment) > 128 for segment in path):
                raise ValueError("command binding paths require non-empty segments")
        return self


class WorkflowAuthorizationBinding(WorkflowContractModel):
    """Authorize a customer created by an earlier command result."""

    source_command_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    source_path: list[str] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_path(self) -> Self:
        if any(not segment or len(segment) > 128 for segment in self.source_path):
            raise ValueError("authorization binding paths require non-empty segments")
        return self


class WorkflowAuthorizationScope(WorkflowContractModel):
    """Customer resources authorized by the confirmed business action."""

    customer_ids: list[str] = Field(max_length=50)
    customer_bindings: list[WorkflowAuthorizationBinding] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def validate_customer_ids(self) -> Self:
        normalized = [value.strip() for value in self.customer_ids]
        if any(not value or len(value) > 128 for value in normalized):
            raise ValueError("authorization customer ids must be non-empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("authorization customer ids must be unique")
        self.customer_ids = normalized
        return self


class WorkflowCommand(WorkflowContractModel):
    """One idempotent CRM tool command in a confirmed Workflow plan."""

    command_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    tool_name: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    payload: dict[str, JsonValue]
    authorization_scope: WorkflowAuthorizationScope
    bindings: list[WorkflowCommandBinding] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def require_unique_binding_targets(self) -> Self:
        targets = [tuple(binding.target_path) for binding in self.bindings]
        if len(targets) != len(set(targets)):
            raise ValueError("command binding targets must be unique")
        return self


class WorkflowActionPlan(WorkflowContractModel):
    """Checkpoint-safe ordered command plan confirmed as one business action."""

    schema_version: Literal["crm.workflow.plan.v1"] = "crm.workflow.plan.v1"
    action_id: str = Field(min_length=1, max_length=128)
    execution_authorization: Literal["CONFIRMATION_REQUIRED", "AUTO_EXECUTE_AUTHORIZED", "RESUME_AUTHORIZED"]
    risk_level: Literal["LOW", "MEDIUM", "HIGH"] | None = None
    authorization_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    commands: list[WorkflowCommand] = Field(default_factory=list, max_length=20)
    terminal_outcome: Literal["CANCELLED", "SKIPPED"] | None = None
    interaction: WorkflowInteraction | None = None
    completed_text: str = Field(default="", max_length=10_000)
    cancelled_text: str = Field(default="", max_length=10_000)
    terminal_reason: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def validate_command_order(self) -> Self:
        if self.terminal_outcome in {"CANCELLED", "SKIPPED"}:
            if self.commands or self.interaction is not None:
                raise ValueError("terminal no-op plans cannot carry commands or interactions")
            if self.execution_authorization != "RESUME_AUTHORIZED":
                raise ValueError("terminal no-op plans require resume authorization")
            if self.terminal_outcome == "CANCELLED" and not self.cancelled_text.strip():
                raise ValueError("cancelled plans require cancelled text")
            if self.terminal_outcome == "SKIPPED" and not self.terminal_reason:
                raise ValueError("skipped plans require a terminal reason")
            return self
        if not self.commands:
            raise ValueError("non-terminal Workflow plans require at least one command")
        if not self.completed_text.strip() or not self.cancelled_text.strip():
            raise ValueError("non-terminal Workflow plans require terminal texts")
        if self.execution_authorization == "CONFIRMATION_REQUIRED":
            if self.interaction is None or self.interaction.interaction_type != "confirmation":
                raise ValueError("confirmation-authorized plans require a confirmation interaction")
        elif self.interaction is not None:
            raise ValueError("non-interactive plans cannot carry a second interaction")
        if self.execution_authorization == "AUTO_EXECUTE_AUTHORIZED":
            if self.risk_level != "LOW" or self.authorization_confidence is None:
                raise ValueError("auto-execute plans require low-risk confidence evidence")
            if self.authorization_confidence < 0.85:
                raise ValueError("auto-execute confidence must meet the low-risk threshold")
        command_ids = [command.command_id for command in self.commands]
        if len(command_ids) != len(set(command_ids)):
            raise ValueError("Workflow command ids must be unique")
        available: set[str] = set()
        for command in self.commands:
            referenced_commands = [binding.source_command_id for binding in command.bindings]
            referenced_commands.extend(
                binding.source_command_id for binding in command.authorization_scope.customer_bindings
            )
            for source_command_id in referenced_commands:
                if source_command_id not in available:
                    raise ValueError("command bindings may only reference earlier commands")
            available.add(command.command_id)
        return self


class WorkflowResumeInput(WorkflowContractModel):
    """Canonical channel-neutral payload authorized by the Agent UI action ledger."""

    kind: Literal["text", "confirm", "reject"]
    content: str = Field(max_length=20_000)
    source: str = Field(min_length=1, max_length=128)
    provider: str | None = Field(default=None, max_length=128)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class WorkflowEffectResult(WorkflowContractModel):
    """Result of one guarded CRM mutation owned by the Workflow module."""

    success: bool
    code: str | None = Field(default=None, min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2_000)
    retryable: bool = False
    durable_work: list[AgentDurableWorkReceipt] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.success and self.code is not None:
            raise ValueError("successful Workflow effects cannot include an error code")
        if not self.success and self.code is None:
            raise ValueError("failed Workflow effects require an error code")
        if not self.success and self.durable_work:
            raise ValueError("failed Workflow effects cannot publish durable-work receipts")
        return self


WorkflowResult: TypeAlias = Annotated[
    WorkflowWaitingResult
    | WorkflowCompletedResult
    | WorkflowCancelledResult
    | WorkflowSkippedResult
    | WorkflowFailedResult
    | WorkflowReplayResult,
    Field(discriminator="status"),
]

workflow_result_adapter: TypeAdapter[WorkflowResult] = TypeAdapter(WorkflowResult)

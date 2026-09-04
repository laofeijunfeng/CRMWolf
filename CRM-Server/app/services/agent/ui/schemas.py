"""Closed-world contracts for CRM Agent messages, actions, and typed input."""

from __future__ import annotations

from typing import Annotated, Literal, Self, TypeAlias
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from app.services.agent.query.schemas import CRMResource, EntityRef, JsonDict  # noqa: TC001
from app.services.agent.ui.markdown import RAW_HTML_PATTERN, contains_raw_html, validate_agent_markdown

AgentUIMessageDisplay: TypeAlias = Literal["MESSAGE", "STATE_UPDATE"]


AgentErrorCode: TypeAlias = Literal[
    "ROUTE_AMBIGUOUS",
    "ENTITY_AMBIGUOUS",
    "QUERY_INVALID",
    "QUERY_UNSUPPORTED",
    "QUERY_EMPTY",
    "PERMISSION_DENIED",
    "QUERY_LIMIT_EXCEEDED",
    "UPSTREAM_TIMEOUT",
    "UPSTREAM_UNAVAILABLE",
    "CHECKPOINT_UNAVAILABLE",
    "MODEL_OUTPUT_INVALID",
    "RESULT_SET_EXPIRED",
    "ACTION_ALREADY_CONSUMED",
    "ACTION_EXPIRED",
    "ACTION_INVALID",
    "TURN_IN_PROGRESS",
    "IDEMPOTENCY_KEY_REUSED",
    "INTERNAL_ERROR",
]


class AgentUIContractModel(BaseModel):
    """Forbid undeclared protocol fields at every nested boundary."""

    model_config = ConfigDict(extra="forbid", strict=True)


class AgentUIValue(AgentUIContractModel):
    kind: Literal["text", "number", "money", "date", "datetime", "boolean", "status", "link"]
    value: str | int | float | bool | None
    display: str | None = Field(default=None, max_length=10000)
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_value_kind(self) -> Self:
        value = self.value
        if self.kind in {"number", "money"} and value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{self.kind} value must be numeric")
        elif self.kind == "boolean" and value is not None and not isinstance(value, bool):
            raise ValueError("boolean value must be boolean")
        elif self.kind not in {"number", "money", "boolean"} and value is not None and not isinstance(value, str):
            raise ValueError(f"{self.kind} value must be a string")
        if self.currency is not None and self.kind != "money":
            raise ValueError("currency is only valid for money values")
        return self


class AgentUIActionBase(AgentUIContractModel):
    action_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=200)


class OpenEntityAction(AgentUIActionBase):
    type: Literal["open_entity"]


class QueryRefinementAction(AgentUIActionBase):
    type: Literal["query_refinement"]


class StartWorkflowAction(AgentUIActionBase):
    type: Literal["start_workflow"]


class SubmitInteractionAction(AgentUIActionBase):
    type: Literal["submit_interaction"]


class RetryAction(AgentUIActionBase):
    type: Literal["retry"]


AgentUIAction: TypeAlias = Annotated[
    OpenEntityAction | QueryRefinementAction | StartWorkflowAction | SubmitInteractionAction | RetryAction,
    Field(discriminator="type"),
]


class AgentUIBlockBase(AgentUIContractModel):
    id: str = Field(min_length=1, max_length=128)


class TextBlock(AgentUIBlockBase):
    type: Literal["text"]
    format: Literal["plain", "markdown"]
    text: str = Field(
        max_length=10000,
        json_schema_extra={"not": {"pattern": RAW_HTML_PATTERN}},
    )

    @model_validator(mode="after")
    def validate_text_format(self) -> Self:
        if self.format == "markdown":
            validate_agent_markdown(self.text)
        elif contains_raw_html(self.text):
            raise ValueError("text blocks must not contain raw HTML")
        return self


class EntityField(AgentUIContractModel):
    key: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=200)
    value: AgentUIValue


class EntityListItem(AgentUIContractModel):
    entity_ref: EntityRef


class EntityListBlock(AgentUIBlockBase):
    type: Literal["entity_list"]
    entity_type: CRMResource
    items: list[EntityListItem] = Field(default_factory=list, max_length=100)
    total: int = Field(ge=0)
    result_set_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_entity_references(self) -> Self:
        for item in self.items:
            entity_ref = item.entity_ref
            if entity_ref.resource != self.entity_type:
                raise ValueError("entity resource must match entity_type")
            if entity_ref.result_set_id != self.result_set_id:
                raise ValueError("entity result_set_id must match list result_set_id")
        return self


class EntityCardSection(AgentUIContractModel):
    key: str = Field(min_length=1, max_length=128)
    title: str | None = Field(default=None, max_length=200)
    fields: list[EntityField] = Field(default_factory=list, max_length=12)


class EntityCardBlock(AgentUIBlockBase):
    type: Literal["entity_card"]
    entity_type: CRMResource
    ref_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    sections: list[EntityCardSection] = Field(default_factory=list, max_length=8)
    actions: list[AgentUIAction] = Field(default_factory=list, max_length=5)


class TableColumn(AgentUIContractModel):
    key: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=200)
    align: Literal["left", "center", "right"] = "left"


class TableCell(AgentUIContractModel):
    column_key: str = Field(min_length=1, max_length=128)
    value: AgentUIValue


class TableRow(AgentUIContractModel):
    id: str = Field(min_length=1, max_length=128)
    cells: list[TableCell] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def require_unique_column_keys(self) -> Self:
        column_keys = [cell.column_key for cell in self.cells]
        if len(column_keys) != len(set(column_keys)):
            raise ValueError("table row column_key values must be unique")
        return self


class TableBlock(AgentUIBlockBase):
    type: Literal["table"]
    columns: list[TableColumn] = Field(min_length=1, max_length=20)
    rows: list[TableRow] = Field(default_factory=list, max_length=100)
    caption: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_table_shape(self) -> Self:
        column_keys = [column.key for column in self.columns]
        if len(column_keys) != len(set(column_keys)):
            raise ValueError("table column keys must be unique")
        allowed_keys = set(column_keys)
        for row in self.rows:
            if any(cell.column_key not in allowed_keys for cell in row.cells):
                raise ValueError("table row references an unknown column_key")
        return self


class TimelineItem(AgentUIContractModel):
    id: str = Field(min_length=1, max_length=128)
    occurred_at: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    actor: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, max_length=128)


class TimelineBlock(AgentUIBlockBase):
    type: Literal["timeline"]
    items: list[TimelineItem] = Field(default_factory=list, max_length=100)


ProcessItemStatus: TypeAlias = Literal[
    "PENDING",
    "RUNNING",
    "COMPLETED",
    "WAITING",
    "FAILED",
    "CANCELLED",
    "SKIPPED",
]


class ProcessItem(AgentUIContractModel):
    key: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    title: str = Field(min_length=1, max_length=200)
    status: ProcessItemStatus
    description: str | None = Field(default=None, max_length=2_000)


class ProcessBlock(AgentUIBlockBase):
    """Compact execution-process projection; distinct from business timelines."""

    type: Literal["process"]
    title: str = Field(min_length=1, max_length=200)
    items: list[ProcessItem] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def require_unique_item_keys(self) -> Self:
        keys = [item.key for item in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("process item keys must be unique")
        return self


class AgentUIMetric(AgentUIContractModel):
    key: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=200)
    value: AgentUIValue
    change: AgentUIValue | None = None


class MetricGroupBlock(AgentUIBlockBase):
    type: Literal["metric_group"]
    metrics: list[AgentUIMetric] = Field(min_length=1, max_length=12)


class NoticeBlock(AgentUIBlockBase):
    type: Literal["notice"]
    tone: Literal["info", "success", "warning"]
    title: str | None = Field(default=None, max_length=200)
    text: str = Field(min_length=1, max_length=10000)


class ErrorBlock(AgentUIBlockBase):
    type: Literal["error"]
    code: AgentErrorCode
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=10000)
    retryable: bool
    trace_id: str | None = Field(default=None, min_length=1, max_length=128)


class InteractionOption(AgentUIContractModel):
    value: str = Field(min_length=1, max_length=500)
    label: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    disabled: bool = False


class InteractionField(AgentUIContractModel):
    key: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=200)
    field_type: Literal["text", "textarea", "number", "date", "datetime", "select", "multi_select", "boolean"]
    required: bool = False
    placeholder: str | None = Field(default=None, max_length=200)
    default_value: JsonValue = None
    min_length: int | None = Field(default=None, ge=0, le=10000)
    max_length: int | None = Field(default=None, ge=1, le=10000)
    minimum: float | None = None
    maximum: float | None = None
    options: list[InteractionOption] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_field_constraints(self) -> Self:
        if self.min_length is not None and self.max_length is not None and self.min_length > self.max_length:
            raise ValueError("min_length cannot exceed max_length")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum cannot exceed maximum")
        if self.field_type in {"select", "multi_select"} and not self.options:
            raise ValueError("select fields require options")
        if self.field_type not in {"select", "multi_select"} and self.options:
            raise ValueError("options are only valid for select fields")
        if len({option.value for option in self.options}) != len(self.options):
            raise ValueError("interaction field option values must be unique")
        if self.field_type in {"text", "textarea"} and (self.min_length is None or self.max_length is None):
            raise ValueError("text fields require min_length and max_length")
        if self.field_type == "number" and (self.minimum is None or self.maximum is None):
            raise ValueError("number fields require minimum and maximum")
        return self


class InteractionBlock(AgentUIBlockBase):
    type: Literal["interaction"]
    interaction_id: str = Field(min_length=1, max_length=128)
    interaction_type: Literal["choice", "form", "confirmation", "text_input"]
    presentation: Literal["COMPACT_TASK_COMPLETION"] | None = None
    state: Literal["ACTIVE", "SUBMITTED", "EXPIRED", "CANCELLED", "READ_ONLY"]
    prompt: str = Field(min_length=1, max_length=10000)
    fields: list[InteractionField] = Field(default_factory=list, max_length=20)
    options: list[InteractionOption] = Field(default_factory=list, max_length=50)
    selection_mode: Literal["single", "multiple"] | None = None
    min_selections: int | None = Field(default=None, ge=0, le=50)
    max_selections: int | None = Field(default=None, ge=1, le=50)
    allow_blank: bool | None = None
    submit_on_select: bool = False
    submit_label: str = Field(default="提交", min_length=1, max_length=200)
    submit_action_id: str | None = Field(min_length=1, max_length=128)
    submitted_values: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def validate_interaction_shape(self) -> Self:
        if self.state == "ACTIVE" and self.submit_action_id is None:
            raise ValueError("active interaction requires submit_action_id")
        if self.state != "ACTIVE" and self.submit_action_id is not None:
            raise ValueError("non-active interaction cannot expose submit_action_id")
        if len({option.value for option in self.options}) != len(self.options):
            raise ValueError("interaction option values must be unique")
        if (
            self.min_selections is not None
            and self.max_selections is not None
            and self.min_selections > self.max_selections
        ):
            raise ValueError("min_selections cannot exceed max_selections")
        if self.presentation == "COMPACT_TASK_COMPLETION" and (
            self.interaction_type != "choice"
            or self.selection_mode != "single"
            or self.min_selections != 1
            or self.max_selections != 1
            or not self.submit_on_select
            or len(self.options) != 1
        ):
            raise ValueError("compact task completion requires one submit-on-select choice")

        if self.interaction_type == "choice":
            if (
                self.fields
                or not self.options
                or self.selection_mode is None
                or self.min_selections is None
                or self.max_selections is None
                or self.allow_blank is not None
            ):
                raise ValueError("choice interaction requires options, selection_mode, and selection bounds only")
            if self.max_selections > len(self.options):
                raise ValueError("max_selections cannot exceed option count")
            if self.selection_mode == "single" and self.max_selections != 1:
                raise ValueError("single choice requires max_selections=1")
        elif self.interaction_type == "form":
            if (
                not self.fields
                or self.options
                or self.selection_mode is not None
                or self.min_selections is not None
                or self.max_selections is not None
                or self.allow_blank is not None
            ):
                raise ValueError("form interaction requires fields and no top-level choice constraints")
        elif self.interaction_type == "confirmation":
            option_values = {option.value for option in self.options}
            if (
                self.fields
                or len(self.options) != 2
                or self.selection_mode != "single"
                or option_values != {"confirm", "cancel"}
                or self.min_selections is not None
                or self.max_selections is not None
                or self.allow_blank is not None
            ):
                raise ValueError("confirmation requires exactly one confirm and one cancel option")
        elif self.interaction_type == "text_input":
            valid_text_field = len(self.fields) == 1 and self.fields[0].field_type in {"text", "textarea"}
            field = self.fields[0] if valid_text_field else None
            if (
                not valid_text_field
                or field is None
                or field.min_length is None
                or field.max_length is None
                or self.options
                or self.selection_mode is not None
                or self.min_selections is not None
                or self.max_selections is not None
                or self.allow_blank is None
            ):
                raise ValueError("text_input requires one bounded text field and allow_blank")
            if not self.allow_blank and field.min_length == 0:
                raise ValueError("non-blank text_input requires min_length greater than zero")
        if self.submit_on_select:
            if self.interaction_type == "choice":
                valid_submit_shape = (
                    self.selection_mode == "single"
                    and self.min_selections == 1
                    and self.max_selections == 1
                )
            elif self.interaction_type == "confirmation":
                # A confirmation is intrinsically a single binary decision; it
                # does not need the generic choice selection bounds.
                valid_submit_shape = self.selection_mode == "single"
            else:
                valid_submit_shape = False
            if not valid_submit_shape:
                raise ValueError("submit_on_select requires an exact single-choice interaction")
        return self


class ActionResultBlock(AgentUIBlockBase):
    type: Literal["action_result"]
    action_id: str = Field(min_length=1, max_length=128)
    status: Literal["SUCCESS", "FAILED", "CANCELLED"]
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=10000)
    entity_ref: EntityRef | None = None


class PaginationBlock(AgentUIBlockBase):
    type: Literal["pagination"]
    result_set_id: str = Field(min_length=1, max_length=128)
    range_start: int = Field(ge=1)
    range_end: int = Field(ge=1)
    total: int | None = Field(default=None, ge=0)
    previous_action_id: str | None = Field(default=None, min_length=1, max_length=128)
    next_action_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.range_end < self.range_start:
            raise ValueError("range_end cannot be less than range_start")
        if self.total is not None and self.range_end > self.total:
            raise ValueError("range_end cannot exceed total")
        return self


AgentUIBlock: TypeAlias = Annotated[
    TextBlock
    | EntityListBlock
    | EntityCardBlock
    | TableBlock
    | TimelineBlock
    | ProcessBlock
    | MetricGroupBlock
    | NoticeBlock
    | ErrorBlock
    | InteractionBlock
    | ActionResultBlock
    | PaginationBlock,
    Field(discriminator="type"),
]


class AgentUIMetadata(AgentUIContractModel):
    display: AgentUIMessageDisplay = "MESSAGE"
    route: Literal["QUERY", "WORKFLOW", "CLARIFY", "CHITCHAT"] | None = None
    result_set_id: str | None = Field(default=None, min_length=1, max_length=128)
    accessibility_label: str | None = Field(default=None, max_length=10000)


class AgentUIEnvelope(AgentUIContractModel):
    schema_version: Literal["crm.agent.ui.v1"]
    message_id: int = Field(gt=0)
    turn_id: str = Field(min_length=1, max_length=128)
    role: Literal["user", "assistant", "system"]
    state: Literal["streaming", "final", "failed"]
    blocks: list[AgentUIBlock] = Field(max_length=30)
    suggested_actions: list[AgentUIAction] = Field(default_factory=list, max_length=10)
    metadata: AgentUIMetadata

    @model_validator(mode="after")
    def require_unique_ids(self) -> Self:
        block_ids = [block.id for block in self.blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("block ids must be unique within an envelope")
        action_ids = [action.action_id for action in self.suggested_actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("suggested action ids must be unique within an envelope")
        return self


class AppendTextOperation(AgentUIContractModel):
    op: Literal["append_text"]
    block_id: str = Field(min_length=1, max_length=128)
    delta: str = Field(min_length=1, max_length=10000)


class UpsertBlockOperation(AgentUIContractModel):
    """Replace one temporary block projection with its latest typed snapshot."""

    op: Literal["upsert_block"]
    block: AgentUIBlock


AgentUIStreamOperation: TypeAlias = Annotated[
    AppendTextOperation | UpsertBlockOperation,
    Field(discriminator="op"),
]


class AgentUIDeltaStreamEvent(AgentUIContractModel):
    event: Literal["agent_ui"]
    phase: Literal["delta"]
    message_id: int | None = Field(default=None, gt=0)
    turn_id: str = Field(min_length=1, max_length=128)
    sequence: int = Field(ge=1)
    operations: list[AgentUIStreamOperation] = Field(min_length=1, max_length=100)


class AgentUIFinalStreamEvent(AgentUIContractModel):
    event: Literal["agent_ui"]
    phase: Literal["final"]
    message_id: int = Field(gt=0)
    turn_id: str = Field(min_length=1, max_length=128)
    sequence: int = Field(ge=1)
    message: AgentUIEnvelope

    @model_validator(mode="after")
    def validate_authoritative_message(self) -> Self:
        if self.message.state != "final":
            raise ValueError("final stream message must have final state")
        if self.message.message_id != self.message_id or self.message.turn_id != self.turn_id:
            raise ValueError("final stream identity must match message envelope")
        return self


class AgentTransportErrorEvent(AgentUIContractModel):
    event: Literal["transport_error"]
    code: AgentErrorCode
    message: str = Field(min_length=1, max_length=10000)
    retryable: bool
    session_id: int | None = Field(default=None, gt=0)
    status_code: int | None = Field(default=None, ge=400, le=599)


AgentUIStreamEvent: TypeAlias = Annotated[
    AgentUIDeltaStreamEvent | AgentUIFinalStreamEvent,
    Field(discriminator="phase"),
]


class TextAgentInput(AgentUIContractModel):
    type: Literal["text"]
    text: str = Field(min_length=1, max_length=10000)

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text cannot be blank")
        return value


class InteractionSubmissionInput(AgentUIContractModel):
    type: Literal["interaction_submission"]
    action_id: str = Field(min_length=1, max_length=128)
    values: JsonDict


class EntityActionInput(AgentUIContractModel):
    type: Literal["entity_action"]
    action_id: str = Field(min_length=1, max_length=128)


AgentChatInput: TypeAlias = Annotated[
    TextAgentInput | InteractionSubmissionInput | EntityActionInput,
    Field(discriminator="type"),
]


class AgentChatRequest(AgentUIContractModel):
    session_id: int | None = Field(default=None, gt=0)
    session_key: str | None = Field(default=None, min_length=1, max_length=64)
    client_request_id: UUID = Field(strict=False)
    input: AgentChatInput

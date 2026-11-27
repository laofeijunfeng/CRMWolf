"""Typed HTTP contracts shared by assistant transport and presentation."""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

from datetime import datetime  # noqa: TC003 -- Pydantic resolves annotations at runtime.
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_serializer,
    model_validator,
)

from app.services.assistant.contracts import (  # noqa: TC001 -- Pydantic resolves models at runtime.
    CommittedReceipt,
    EntityCreateReceipt,
    ProfileKind,
    TaskDraft,
    TaskKind,
    TaskStatus,
    TaskWaiting,
    TurnStatus,
)


class PendingEntityDraftView(BaseModel):
    """One unfinished direct-create draft in 「待补充」 (D20)."""

    model_config = ConfigDict(extra="forbid")

    public_id: str
    task_kind: TaskKind
    label: str
    customer_name: str | None
    waiting_type: str | None
    prompt: str | None
    last_modified_time: datetime


class ProfileProposalRowView(BaseModel):
    """One row of the post-activity profile list, with its child task's own result (D29)."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    kind: ProfileKind
    label: str
    summary: str
    quote: str
    decision: Literal["pending", "go", "skip", "failed"]
    child_task_public_id: str | None = None
    child_status: TaskStatus | None = None
    child_waiting_type: str | None = None
    child_receipt: EntityCreateReceipt | None = None


class AssistantTaskView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_id: str
    status: TaskStatus
    goal: str
    activity_kind: str | None
    # Persisted snapshots predating CRM-165 are activity tasks.
    task_kind: TaskKind = "customer_activity"
    draft: TaskDraft
    waiting: TaskWaiting | None
    committed: list[CommittedReceipt]
    budget_steps: int
    budget_max_steps: int
    version: int
    last_modified_time: str | None = None
    processing_turn_id: str | None = None
    processing_turn_status: TurnStatus | None = None
    reprocess_turn_id: str | None = None
    follow_up_disposition: dict[str, object] | None = None
    proposal_outcome: Literal["proposal_failed", "proposal_rejected"] | None = None
    reconciliation_required: bool = False
    profile_proposals: list[ProfileProposalRowView] | None = None

    @model_validator(mode="after")
    def match_processing_pointer(self) -> AssistantTaskView:
        if (self.processing_turn_id is None) != (self.processing_turn_status is None):
            raise ValueError("processing turn ID and status must appear together")
        return self

    @field_serializer("waiting")
    def serialize_waiting(self, waiting: TaskWaiting | None) -> dict[str, object] | None:
        # Business evidence IDs are not submission authority or a public UI contract.
        return waiting.model_dump(mode="json", exclude={"temporal_target"}) if waiting is not None else None

    @field_serializer("committed")
    def serialize_receipts(self, receipts: list[CommittedReceipt]) -> list[dict[str, object]]:
        return [receipt.model_dump(mode="json", exclude_unset=True) for receipt in receipts]


class AssistantTurnEventView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=0)
    event: str
    data: dict[str, object]


class AssistantTurnView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str
    status: TurnStatus
    lease_version: int = Field(ge=0)
    reprocess_allowed: bool = False
    events: list[AssistantTurnEventView]
    task: AssistantTaskView


class RetryTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_lease_version: int = Field(ge=0)
    after_seq: int = Field(default=0, ge=0)


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=2000, description="任务目标，来自用户首句")
    client_request_id: str = Field(min_length=8, max_length=128)


AssistantRejectReason = Literal["wrong_customer", "wrong_content", "should_not_record", "other"]
DispositionChoice = Annotated[str, StringConstraints(min_length=1, max_length=64)]


class SubmitInputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "text",
        "submit_field",
        "confirm",
        "cancel",
        "revise_activity_kind",
        "submit_form",
        "request_edit",
    ]
    text: str | None = Field(default=None, max_length=100_000)
    choice: str | None = Field(default=None, max_length=64)
    client_request_id: str = Field(min_length=8, max_length=128)
    action_id: str | None = Field(default=None, max_length=128)
    expected_version: int | None = Field(default=None, ge=0)
    # submit_form: values keyed by InteractionField.key plus the form revision they were edited against;
    # choice="cancel" without values backs out of the form; choice="defer" parks an entity form.
    values: dict[str, JsonValue] | None = None
    form_revision: int | None = Field(default=None, ge=0)
    # FOLLOW_UP_DISPOSITION multi-select: checked task ids are completed, unchecked are kept.
    choices: list[DispositionChoice] | None = Field(default=None, max_length=100)
    suppress_week: bool = False
    # Optional closed reason sent with kind="confirm", choice="reject".
    reason: AssistantRejectReason | None = None

    @model_validator(mode="after")
    def validate_kind_fields(self) -> SubmitInputRequest:
        if (self.values is not None or self.form_revision is not None) and self.kind != "submit_form":
            raise ValueError("values/form_revision are only valid for submit_form")
        if self.kind == "submit_form":
            if self.text is not None or self.choice not in {None, "cancel", "defer"}:
                raise ValueError("submit_form accepts values or choice='cancel'|'defer' only")
            if self.form_revision is None or (self.choice is None and self.values is None):
                raise ValueError("submit_form requires values and form_revision")
            if self.choice is not None and self.values is not None:
                raise ValueError("cancelling or deferring a form carries no values")
        if self.kind == "request_edit" and (self.choice is not None or self.text is not None):
            raise ValueError("request_edit takes no choice or text")
        if (self.choices is not None or self.suppress_week) and self.kind != "submit_field":
            raise ValueError("choices/suppress_week are only valid for submit_field")
        if self.suppress_week and self.choices is None:
            raise ValueError("suppress_week requires choices")
        if self.choices is not None and len(self.choices) != len(set(self.choices)):
            raise ValueError("choices must be unique")
        if self.choices is not None and (self.choice is not None or self.text is not None):
            raise ValueError("choices excludes choice and text")
        if self.reason is not None and (self.kind != "confirm" or self.choice != "reject"):
            raise ValueError("reason is only valid when rejecting a confirmation")
        return self

    def turn_input(self) -> dict[str, object]:
        # Preserve the pre-form fingerprint for submissions without new fields.
        return {
            "kind": self.kind, "text": self.text, "choice": self.choice,
            **self.model_dump(mode="json", include={"values", "form_revision", "choices", "suppress_week", "reason"},
                              exclude_none=True, exclude_defaults=True),
        }


class SubmitInputResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: AssistantTaskView
    message: str = Field(min_length=1, max_length=2000)


class AssistantTaskReconcileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["WRITTEN", "NOT_WRITTEN", "STILL_UNKNOWN", "NOOP"]
    task: AssistantTaskView
    message: str = Field(min_length=1, max_length=2000)
    followup_turn_id: str | None = None

"""Typed state contracts for sales-assistant tasks."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.services.assistant.action_evidence import (
    SourceSegment,  # noqa: TC001 - Pydantic resolves the source-record schema at runtime.
)

WaitingType = Literal["FIELD", "CONFIRMATION", "ACTIVITY_KIND", "OBJECT_SELECTION"]
Actor = Literal["MODEL", "USER", "SYSTEM"]
TaskStatus = Literal["ACTIVE", "COMPLETED", "CANCELLED", "FAILED"]
TurnStatus = Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]
ProposalKind = Literal[
    "customer_fact", "follow_up_task_create", "follow_up_task", "opportunity_stage", "opportunity_create"
]


class ActivityPreview(BaseModel):
    """The public subset of the frozen command; never a mutable draft."""

    model_config = ConfigDict(extra="forbid", strict=True)

    customer_name: str
    activity_kind: Literal[
        "PHONE_FOLLOW_UP",
        "WECHAT_FOLLOW_UP",
        "EMAIL_FOLLOW_UP",
        "VISIT_FOLLOW_UP",
        "OTHER_FOLLOW_UP",
        "ONLINE_MEETING",
        "OFFLINE_MEETING",
    ]
    title: str | None = None
    summary: str | None = None
    content_json: dict[str, object]
    source_content: str
    score: int
    score_reason: str
    next_action: str | None = None
    next_follow_time: str | None = None
    next_follow_time_text: str | None = None
    next_follow_time_granularity: Literal["DATE", "DATETIME", "UNKNOWN"] = "UNKNOWN"


class ActivityWriteConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["activity_write"]
    preview: ActivityPreview


class ProposalCandidate(BaseModel):
    """Exact current bound proposal identity, including optimistic CRM state."""

    model_config = ConfigDict(extra="forbid", strict=True)

    kind: ProposalKind
    key: str = Field(min_length=1)
    payload: dict[str, object]
    evidence_quote: str = Field(min_length=1)
    activity_id: int
    action_id: str | None = None
    customer_id: int
    due_date_granularity: Literal["DATE", "DATETIME", "UNKNOWN"] | None = None
    source_revision: int
    target_public_id: str | None = None
    prior_status: str | None = None
    task_owner_id: str | None = None
    prior_stage_snapshot_id: int | None = None
    prior_version: int | None = None
    prior_fact_version: int | None = None
    task_hash: str | None = None

    @model_validator(mode="after")
    def require_existing_target(self) -> ProposalCandidate:
        if self.kind in {"follow_up_task", "opportunity_stage"} and not self.target_public_id:
            raise ValueError("existing-object proposal requires a target")
        return self


class ProposalConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["proposal"]
    proposal_kind: ProposalKind
    candidate: ProposalCandidate

    @model_validator(mode="after")
    def match_candidate_kind(self) -> ProposalConfirmation:
        if self.proposal_kind != self.candidate.kind:
            raise ValueError("proposal discriminator does not match candidate")
        return self


ConfirmationPayload = Annotated[ActivityWriteConfirmation | ProposalConfirmation, Field(discriminator="kind")]


class CustomerActivityReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["customer_activity"]
    public_id: str = Field(min_length=1)
    customer_id: int | None = None


class AcceptedProposalReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: ProposalKind
    public_id: str = Field(min_length=1)
    proposal_key: str = Field(min_length=1)


class RefusedProposalReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal[
        "refused:customer_fact",
        "refused:follow_up_task_create",
        "refused:follow_up_task",
        "refused:opportunity_stage",
        "refused:opportunity_create",
        "refused:opportunity",
    ]
    proposal_key: str | None = None


CommittedReceipt = CustomerActivityReceipt | AcceptedProposalReceipt | RefusedProposalReceipt


class DraftField(BaseModel):
    """One draft slot: server-accepted value or model candidate."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["MISSING", "CANDIDATE", "ACCEPTED", "EXPLICITLY_NONE"]
    value: str | None = Field(default=None, max_length=20000)


class TaskDraft(BaseModel):
    """Canonical activity draft, original user segments and gate result."""

    model_config = ConfigDict(extra="forbid")

    customer: DraftField = Field(default_factory=lambda: DraftField(status="MISSING"))
    content: DraftField = Field(default_factory=lambda: DraftField(status="MISSING"))
    next_action: DraftField = Field(default_factory=lambda: DraftField(status="MISSING"))
    next_follow_time: DraftField = Field(default_factory=lambda: DraftField(status="MISSING"))
    # Meeting-specific slots (ignored for follow-ups).
    meeting_subject: DraftField = Field(default_factory=lambda: DraftField(status="MISSING"))
    participants: DraftField = Field(default_factory=lambda: DraftField(status="MISSING"))
    # Server-computed quality score surfaced on the confirmation card.
    # Canonical structured content and only user-authored source segments.
    content_json: dict[str, object] = Field(default_factory=dict)
    source_segments: list[str] = Field(default_factory=list)
    source_records: list[SourceSegment] = Field(default_factory=list)
    score_reason: str | None = None
    score_detail: dict[str, object] = Field(default_factory=dict)
    quality_score: DraftField = Field(default_factory=lambda: DraftField(status="MISSING"))


class TaskWaiting(BaseModel):
    """Current pause point; types are a closed enum."""

    model_config = ConfigDict(extra="forbid")

    type: WaitingType
    field: str | None = Field(default=None, max_length=64)
    question_id: str = Field(min_length=1, max_length=128)
    prompt: str = Field(min_length=1, max_length=2000)
    action_id: str | None = Field(default=None, max_length=128)
    expected_version: int | None = None
    fingerprint: str | None = Field(default=None, max_length=64)
    candidates: list[dict[str, object]] = Field(default_factory=list)
    confirmation_payload: ConfirmationPayload | None = None

    @model_validator(mode="after")
    def match_confirmation_command(self) -> TaskWaiting:
        payload = self.confirmation_payload
        if self.type != "CONFIRMATION":
            if payload is not None:
                raise ValueError("only confirmation waits may contain a command")
            return self
        if payload is None:
            raise ValueError("confirmation wait requires a command")
        expected_field = "activity_write" if payload.kind == "activity_write" else f"proposal:{payload.proposal_kind}"
        if self.field != expected_field:
            raise ValueError("confirmation field does not match command")
        return self

    @field_serializer("confirmation_payload")
    def serialize_confirmation(
        self, payload: ActivityWriteConfirmation | ProposalConfirmation | None
    ) -> dict[str, object] | None:
        # Omitted candidate fields must stay omitted: they participate in its hash.
        return payload.model_dump(mode="json", exclude_unset=True) if payload is not None else None


class TaskAuthority(BaseModel):
    """Server-only zone: bound object ids and confirmation receipts."""

    model_config = ConfigDict(extra="forbid")

    customer_public_id: str | None = Field(default=None, max_length=64)
    activity_public_id: str | None = Field(default=None, max_length=64)
    confirmation_receipt: str | None = Field(default=None, max_length=128)
    frozen_activity_command: dict[str, object] | None = None


class AssistantTaskSnapshot(BaseModel):
    """Projection of one task row used by the coordinator and API."""

    model_config = ConfigDict(extra="forbid")

    public_id: str
    team_id: int
    user_id: int
    status: TaskStatus
    goal: str
    activity_kind: str | None
    draft: TaskDraft
    waiting: TaskWaiting | None
    authority: TaskAuthority
    committed: list[dict[str, object]] = Field(default_factory=list)
    budget_steps: int
    budget_max_steps: int
    version: int

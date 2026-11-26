"""Typed state contracts for sales-assistant tasks."""

from __future__ import annotations

from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_serializer, model_validator

from app.services.assistant.action_evidence import (
    SourceSegment,  # noqa: TC001 - Pydantic resolves the source-record schema at runtime.
)

WaitingType = Literal[
    "FIELD",
    "CONFIRMATION",
    "ACTIVITY_KIND",
    "OBJECT_SELECTION",
    "FOLLOW_UP_DISPOSITION",
    "PROPOSAL_FORM",
    "CONFIRMATION_EDIT",
    "ENTITY_FORM",
    "ENTITY_DEFERRED",
    "PROFILE_PROPOSALS",
]
TemporalWaitingReason = Literal["DATE", "MONTH", "ROLE", "STATUS", "PRIMARY"]
Actor = Literal["MODEL", "USER", "SYSTEM"]
TaskStatus = Literal["ACTIVE", "COMPLETED", "CANCELLED", "FAILED"]
TurnStatus = Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]
ProposalKind = Literal["follow_up_task_create", "opportunity_stage", "opportunity_create", "opportunity_lose"]
# Waits and receipts frozen before CRM-154 may still carry retired kinds (`customer_fact`, and
# `follow_up_task` waits). They stay readable; the disposition still writes `follow_up_task` receipts.
StoredProposalKind = ProposalKind | Literal["customer_fact", "follow_up_task"]
EntityKind = Literal[
    "contact_create", "invoice_title_create", "deployment_create", "customer_create", "opportunity_create",
]
ENTITY_KINDS: frozenset[str] = frozenset(get_args(EntityKind))
# One task per record: a follow-up activity, or one directly created entity (opportunities included).
TaskKind = Literal["customer_activity"] | EntityKind
# Server-assigned provenance of one entity form value; rendered as `InteractionField.source_label`.
FieldSource = Literal[
    "ORIGINAL",
    "DERIVED",
    "DEFAULT",
    "USER_CHOICE",
    "SUPPLEMENT",
    "NORMALIZED",
    "AUTO_NAME",
    "CUSTOMER_DEFAULT",
]
FORM_WAITING_TYPES = frozenset({"PROPOSAL_FORM", "CONFIRMATION_EDIT", "ENTITY_FORM"})


class ContextEvidence(BaseModel):
    """One authorized source line on the follow-up confirmation card."""

    model_config = ConfigDict(extra="forbid", strict=True)

    source_type: str = Field(min_length=1, max_length=40)
    occurred_at: str | None = None
    summary: str = Field(min_length=1, max_length=120)
    relation: str = Field(min_length=1, max_length=20)
    key: bool = False


class ComparisonCurrentSource(BaseModel):
    """Verified original quote, frozen with source-local coordinates."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    segment_id: str = Field(min_length=1, max_length=100)
    quote_start: int = Field(ge=0)
    quote_end: int = Field(ge=0)
    quote: str = Field(min_length=1, max_length=500)


class ComparisonHistoricalSource(BaseModel):
    """Quote from the authorized historical summary, not attributed customer speech."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    ref: str = Field(min_length=1, max_length=16)
    source_type: str = Field(min_length=1, max_length=40)
    occurred_at: str | None = None
    quote_start: int = Field(ge=0)
    quote_end: int = Field(ge=0)
    quote: str = Field(min_length=1, max_length=120)


class FollowUpComparison(BaseModel):
    """At most one server-verified historical difference; never a stage judgment."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    kind: Literal["CUSTOMER_COMMITMENT", "RESCHEDULE"]
    subject: str = Field(min_length=1, max_length=80)
    action_id: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=300)
    current: ComparisonCurrentSource
    previous: ComparisonHistoricalSource
    previous_date: str | None = None
    current_date: str | None = None


class ActivityPreview(BaseModel):
    """The public subset of the frozen command; never a mutable draft."""

    model_config = ConfigDict(extra="forbid", strict=True)

    customer_name: str
    activity_kind: (
        Literal[
            "PHONE_FOLLOW_UP",
            "WECHAT_FOLLOW_UP",
            "EMAIL_FOLLOW_UP",
            "VISIT_FOLLOW_UP",
            "OTHER_FOLLOW_UP",
            "ONLINE_MEETING",
            "OFFLINE_MEETING",
        ]
        | None
    ) = None
    channel_status: Literal["recognized", "required", "selected", "revised"] = "recognized"
    channel_status_label: str | None = Field(default=None, max_length=40)
    channel_source_text: str | None = Field(default=None, max_length=400)
    channel_options: list[str] = Field(default_factory=list, max_length=7)
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
    comparison: FollowUpComparison | None = None
    context_status: str | None = Field(default=None, max_length=120)
    # Persisted previews only: generation no longer emits the old signal contract.
    change_signal: Literal["推进", "持平", "放缓", "待确认"] | None = None
    change_summary: str | None = Field(default=None, max_length=80)
    opportunity_name: str | None = None
    opportunity_stage: str | None = None
    context_as_of: str | None = None
    context_notices: list[str] = Field(default_factory=list)
    context_evidence: list[ContextEvidence] = Field(default_factory=list)
    ignored_noise_summary: str | None = Field(default=None, max_length=40)


class ActivityWriteConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["activity_write"]
    preview: ActivityPreview


class ProposalCandidate(BaseModel):
    """Exact current bound proposal identity, including optimistic CRM state."""

    model_config = ConfigDict(extra="forbid", strict=True)

    kind: StoredProposalKind
    key: str = Field(min_length=1)
    payload: dict[str, object]
    evidence_quote: str = Field(min_length=1)
    activity_id: int
    action_id: str | None = None
    customer_id: int
    due_date_granularity: Literal["DATE", "DATETIME", "UNKNOWN"] | None = None
    source_revision: int
    segment_id: str | None = None
    target_public_id: str | None = None
    prior_status: str | None = None
    task_owner_id: str | None = None
    prior_stage_snapshot_id: int | None = None
    prior_version: int | None = None
    prior_fact_version: int | None = None
    task_hash: str | None = None

    @model_validator(mode="after")
    def require_existing_target(self) -> ProposalCandidate:
        if self.kind in {"opportunity_stage", "opportunity_lose"} and not self.target_public_id:
            raise ValueError("existing-object proposal requires a target")
        return self


class ProposalConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["proposal"]
    proposal_kind: StoredProposalKind
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
    customer_public_id: str | None = None


class AcceptedProposalReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: StoredProposalKind
    public_id: str = Field(min_length=1)
    proposal_key: str = Field(min_length=1)
    customer_id: int | None = None
    customer_public_id: str | None = None
    approval_id: int | None = None
    approval_phase: Literal["pending_review"] | None = None
    detail: str | None = None
    # Server-resolved target name (opportunity or task title); older receipts have none.
    name: str | None = Field(default=None, min_length=1, max_length=200)


class RefusedProposalReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal[
        "refused:customer_fact",
        "refused:follow_up_task_create",
        "refused:follow_up_task",
        "refused:opportunity_stage",
        "refused:opportunity_create",
        "refused:opportunity_lose",
        "refused:opportunity",
        "refused:contact_create",
        "refused:invoice_title_create",
        "refused:deployment_create",
        "refused:customer_create",
    ]
    proposal_key: str | None = None


class EntityCreateReceipt(BaseModel):
    """One directly created (or already existing) CRM record of an entity task."""

    model_config = ConfigDict(extra="forbid", strict=True)

    kind: EntityKind
    public_id: str = Field(min_length=1, max_length=64)
    outcome: Literal["created", "existing"] = "created"
    customer_public_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    # Only a created opportunity whose effect carries an approval id is pending review (D26).
    approval_phase: Literal["pending_review"] | None = None


CommittedReceipt = CustomerActivityReceipt | AcceptedProposalReceipt | RefusedProposalReceipt | EntityCreateReceipt


class DraftField(BaseModel):
    """One draft slot: server-accepted value or model candidate."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["MISSING", "CANDIDATE", "ACCEPTED", "EXPLICITLY_NONE"]
    value: str | None = Field(default=None, max_length=100_000)


class VerifiedNoiseSpan(BaseModel):
    """A model noise label the server located in one source segment; it only removes questions."""

    model_config = ConfigDict(extra="forbid")

    segment_id: str = Field(min_length=1, max_length=64)
    kind: Literal["SPEAKER_TIMESTAMP", "CHANNEL_MENTION"]
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    raw_text: str = Field(min_length=1, max_length=40)


class EntityFieldValue(BaseModel):
    """One entity form value with its server-assigned provenance."""

    model_config = ConfigDict(extra="forbid")

    # Text for most fields; opportunity forms also carry numbers and multi-select ids.
    value: Annotated[str, Field(max_length=2000)] | int | float | list[Annotated[str, Field(max_length=64)]] | None = (
        Field(default=None)
    )
    source: FieldSource
    # Verified user phrase the value came from (DERIVED shows it as 按“…”).
    phrase: str | None = Field(default=None, max_length=200)
    # Server-found alternatives the user must pick from (two numbers, an adjacent scale band, ...).
    choices: list[str] = Field(default_factory=list, max_length=8)
    # Draft-time problem shown on the field until the user submits (e.g. 原文少一位, 请核对).
    warning: str | None = Field(default=None, max_length=200)


class EntityQuote(BaseModel):
    """One model-nominated value whose quote the server located in the user's own text."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=2000)
    quote: str = Field(min_length=1, max_length=2000)


class EntityDraft(BaseModel):
    """Editable draft of one record a sales rep asked to create directly."""

    model_config = ConfigDict(extra="forbid")

    kind: EntityKind
    customer_public_id: str | None = Field(default=None, max_length=64)
    customer_name: str | None = Field(default=None, max_length=200)
    fields: dict[str, EntityFieldValue] = Field(default_factory=dict)
    # Inline 「新建客户」 form values while this task waits on its customer (child task created on write).
    customer_fields: dict[str, EntityFieldValue] = Field(default_factory=dict)
    # Verified extraction kept until the customer is bound; the form module prepares fields from it.
    extracted: list[EntityQuote] = Field(default_factory=list, max_length=40)
    # Last submitted values per form kind, so a refused submit re-renders exactly what the user typed.
    submitted: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)
    source_text: str = Field(default="", max_length=100_000)
    credentials_mentioned: bool = False


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
    channel_status: Literal["recognized", "required", "selected", "revised"] | None = None
    channel_kind: str | None = Field(default=None, max_length=32)
    channel_source: Literal["model", "keyword", "user"] | None = None
    channel_quote: str | None = Field(default=None, max_length=200)
    channel_reason: str | None = Field(default=None, max_length=200)
    channel_confidence: float | None = None
    channel_status_label: str | None = Field(default=None, max_length=40)
    channel_source_text: str | None = Field(default=None, max_length=400)
    channel_options: list[str] = Field(default_factory=list, max_length=7)
    channel_origin_label: str | None = Field(default=None, max_length=40)
    input_noise: list[VerifiedNoiseSpan] = Field(default_factory=list, max_length=200)
    # Entity tasks only (task_kind != customer_activity).
    entity: EntityDraft | None = None


class TemporalWaitingTarget(BaseModel):
    """Server-derived evidence target for one temporal clarification."""

    model_config = ConfigDict(extra="forbid", strict=True)

    mention_id: str | None = Field(default=None, max_length=128)
    business_action_id: str | None = Field(default=None, max_length=128)
    reason: TemporalWaitingReason


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
    hint: str | None = Field(default=None, max_length=400)
    temporal_target: TemporalWaitingTarget | None = None
    confirmation_payload: ConfirmationPayload | None = None
    # Form waits (PROPOSAL_FORM, CONFIRMATION_EDIT, ENTITY_FORM) only: bumped on every form edit;
    # submit_form must echo it.
    form_revision: int | None = Field(default=None, ge=0)
    form_fields: list[dict[str, object]] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def match_confirmation_command(self) -> TaskWaiting:
        if (self.form_revision is not None) != (self.type in FORM_WAITING_TYPES):
            raise ValueError("form_revision is required on form waits and forbidden elsewhere")
        if self.form_fields is not None and self.form_revision is None:
            raise ValueError("form fields require a form wait")
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


ProfileKind = Literal["contact_create", "invoice_title_create", "deployment_create"]


class ProfileProposalItem(BaseModel):
    """One profile record a committed activity mentioned (D29); an accepted item becomes its own child task."""

    model_config = ConfigDict(extra="forbid")

    kind: ProfileKind
    summary: str = Field(min_length=1, max_length=120)
    quote: str = Field(min_length=1, max_length=2000)
    extracted: list[EntityQuote] = Field(default_factory=list, max_length=40)
    decision: Literal["pending", "go", "skip", "failed"] = "pending"
    child_task_public_id: str | None = Field(default=None, max_length=64)


class TaskAuthority(BaseModel):
    """Server-only zone: bound object ids and confirmation receipts."""

    model_config = ConfigDict(extra="forbid")

    customer_public_id: str | None = Field(default=None, max_length=64)
    opportunity_public_id: str | None = Field(default=None, max_length=64)
    opportunity_stage_name: str | None = Field(default=None, max_length=100)
    activity_public_id: str | None = Field(default=None, max_length=64)
    confirmation_receipt: str | None = Field(default=None, max_length=128)
    frozen_activity_command: dict[str, object] | None = None
    open_follow_up_batch: dict[str, object] | None = None
    proposal_outcome: Literal["proposal_failed", "proposal_rejected"] | None = None
    proposal_queue: list[ProposalCandidate] | None = None
    proposal_form: dict[str, object] | None = None
    # Offered at most once after the activity write; [] means offered and nothing found.
    profile_proposals: list[ProfileProposalItem] | None = None


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

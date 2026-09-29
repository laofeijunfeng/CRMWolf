"""Typed state contracts for sales-assistant tasks."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WaitingType = Literal["FIELD", "CONFIRMATION", "ACTIVITY_KIND", "OBJECT_SELECTION"]
Actor = Literal["MODEL", "USER", "SYSTEM"]
TaskStatus = Literal["ACTIVE", "COMPLETED", "CANCELLED", "FAILED"]


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
    confirmation_payload: dict[str, object] | None = None


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

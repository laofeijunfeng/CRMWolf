"""Public contracts for the versioned customer profile projection."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003  # Pydantic resolves this annotation at runtime.
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")
CustomerProfileStatusValue = Literal["READY", "UPDATING", "STALE", "PARTIAL", "FAILED", "NOT_READY"]
CustomerProfilePublicationStatusValue = Literal[
    "DRAFT", "PUBLISHED", "PUBLISHED_WITH_WARNINGS", "SUPERSEDED", "FAILED", "REJECTED"
]


class CustomerProfileApiError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class CustomerProfileApiEnvelope(BaseModel, Generic[T]):
    request_id: str
    data: T | None = None
    error: CustomerProfileApiError | None = None


class CustomerProfileFreshness(BaseModel):
    profile_as_of: datetime | None = None
    latest_business_event_at: datetime | None = None
    is_stale: bool = False
    stale_reason: str | None = None


class CustomerProfileSections(BaseModel):
    current_situation: dict[str, Any] = Field(default_factory=dict)
    current_journeys: list[dict[str, Any]] = Field(default_factory=list)
    important_changes: list[dict[str, Any]] = Field(default_factory=list)
    long_term_context: dict[str, Any] = Field(default_factory=dict)
    follow_up_process: list[dict[str, Any]] = Field(default_factory=list)
    recorded_follow_ups: list[dict[str, Any]] = Field(default_factory=list)


class CustomerProfileLinks(BaseModel):
    changes: str
    evidence: str
    journeys: str
    follow_ups: str
    versions: str


class CustomerProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: str
    profile_status: CustomerProfileStatusValue
    current_profile_version: str | None = None
    profile_version_number: int | None = None
    schema_version: str = "v2"
    freshness: CustomerProfileFreshness
    sections: CustomerProfileSections
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    links: CustomerProfileLinks


class CustomerProfileSubresourceResponse(BaseModel):
    profile_status: CustomerProfileStatusValue
    current_profile_version: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False


class CustomerProfileRefreshRequest(BaseModel):
    scope: Literal["partial", "full"] = "full"
    reason: Literal["manual_refresh", "migration", "correction"] = "manual_refresh"
    expected_current_version: int | None = Field(default=None, ge=1)


class CustomerProfileRefreshResponse(BaseModel):
    request_id: str
    run_id: int
    profile_status: CustomerProfileStatusValue
    current_profile_version: str | None = None
    scheduled_at: datetime


class CustomerProfileVersionSummary(BaseModel):
    public_id: str
    profile_version: int
    schema_version: str
    publication_status: CustomerProfilePublicationStatusValue
    source_event_key: str | None = None
    run_id: int | None = None
    graph_version: str
    source_watermark: dict[str, Any] = Field(default_factory=dict)
    fact_watermark: int = 0
    journey_watermark: int = 0
    task_watermark: int = 0
    commitment_watermark: int = 0
    generated_at: datetime
    published_at: datetime | None = None
    created_time: datetime


class CustomerProfileVersionListResponse(BaseModel):
    items: list[CustomerProfileVersionSummary]
    next_cursor: str | None = None
    has_more: bool = False

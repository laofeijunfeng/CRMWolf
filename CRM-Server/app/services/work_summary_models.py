"""Typed contracts shared by work-summary data, orchestration, and presentation layers."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.agent.schemas import WorkSummaryNarrativeItem  # noqa: TC001

DEFAULT_WORK_SUMMARY_PAGE_SIZE = 50
DEFAULT_WORK_SUMMARY_CITATION_BUDGET = 30
DEFAULT_WORK_SUMMARY_SYNTHESIS_CHUNK_BUDGET = 20

WorkSummaryStopReason = Literal[
    "all_facts_collected",
    "fact_budget_exceeded",
    "page_budget_exceeded",
    "source_failed",
]


class WorkSummaryQuery(BaseModel):
    """Snapshot-bound fact query consumed by the authoritative data adapter."""

    model_config = ConfigDict(extra="forbid")

    team_id: int
    user_id: int
    window: str = "this_week"
    customer_public_id: str | None = None
    include_tasks: bool = True
    include_activities: bool = True
    include_business_events: bool = True
    start_at: str | None = None
    end_at: str | None = None
    page_size: int = Field(DEFAULT_WORK_SUMMARY_PAGE_SIZE, ge=1, le=100)


class WorkSummaryFactPage(BaseModel):
    """One authoritative page of structured work facts."""

    model_config = ConfigDict(extra="forbid")

    items: list[dict[str, Any]] = Field(default_factory=list)
    available_total: int = Field(0, ge=0)
    next_cursor: str | None = None
    source_counts: dict[str, int] = Field(default_factory=dict)
    source_total_counts: dict[str, int] = Field(default_factory=dict)
    source_status: dict[str, str] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)


class WorkSummaryCitation(BaseModel):
    """A citation resolved exclusively from the retrieved fact snapshot."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str
    fact_type: str | None = None
    source_group: str | None = None
    title: str | None = None
    occurred_at: str | None = None
    customer: dict[str, Any] = Field(default_factory=dict)


class WorkSummaryCoverage(BaseModel):
    """Explicit completeness contract for a generated summary."""

    model_config = ConfigDict(extra="forbid")

    available_total: int = Field(0, ge=0)
    retrieved_total: int = Field(0, ge=0)
    summarized_total: int = Field(0, ge=0)
    referenced_total: int = Field(0, ge=0)
    pages_fetched: int = Field(0, ge=0)
    complete: bool
    stop_reason: WorkSummaryStopReason


class WorkSummaryOutcome(BaseModel):
    """Validated domain outcome returned to Agent and renderer adapters."""

    model_config = ConfigDict(extra="forbid")

    answer: str
    highlights: list[WorkSummaryNarrativeItem] = Field(default_factory=list)
    customer_summaries: list[WorkSummaryNarrativeItem] = Field(default_factory=list)
    citations: list[WorkSummaryCitation] = Field(
        default_factory=list,
        max_length=DEFAULT_WORK_SUMMARY_CITATION_BUDGET,
    )
    coverage: WorkSummaryCoverage
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    summary_source: Literal["langchain_structured_output", "deterministic_fallback"]
    model: str | None = None
    fallback_reason: str | None = None
    fallback_error: str | None = None


class ResolvedWorkSummaryNarrative(BaseModel):
    """Grounded narrative items paired with their authoritative citations."""

    model_config = ConfigDict(extra="forbid")

    highlights: list[WorkSummaryNarrativeItem] = Field(default_factory=list)
    customer_summaries: list[WorkSummaryNarrativeItem] = Field(default_factory=list)
    citations: list[WorkSummaryCitation] = Field(default_factory=list)

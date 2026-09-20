from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CustomerEnrichmentPurpose(StrEnum):
    INITIAL_CREATION = "INITIAL_CREATION"
    HISTORICAL_BACKFILL = "HISTORICAL_BACKFILL"


class CustomerEnrichmentJobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRY_PENDING = "RETRY_PENDING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    EXHAUSTED = "EXHAUSTED"


class CustomerEnrichmentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    field: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=500)


class CustomerEnrichmentInferenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decisions: list[CustomerEnrichmentDecision] = Field(min_length=1, max_length=20)


class CustomerEnrichmentJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    team_id: int = Field(gt=0)
    job_public_id: str = Field(pattern=r"^cej_[A-Za-z0-9_-]+$")


class CustomerEnrichmentRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    job_public_id: str
    customer_id: int
    execution_status: str
    success: bool
    retryable: bool = False
    applied_fields: list[str] = Field(default_factory=list)
    skip_reason: str | None = None
    error: str | None = None
    profile_refresh_action: Literal["RELEASED", "ENQUEUED", "NONE"] = "NONE"

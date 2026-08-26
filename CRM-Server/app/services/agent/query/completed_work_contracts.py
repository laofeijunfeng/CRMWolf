"""Frozen HTTP contracts for the completed-work CRM query capability."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

CompletedWorkWindow = Literal["today", "this_week", "last_week", "this_month", "custom"]


def _validate_iso_datetime_string(value: str) -> str:
    if "T" not in value:
        raise ValueError("must be an ISO datetime")
    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("must be an ISO datetime") from exc
    return value


def _validate_iso_date_string(value: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("must be an ISO date") from exc
    return value


ISODateTimeString = Annotated[
    str,
    Field(min_length=1, max_length=64),
    AfterValidator(_validate_iso_datetime_string),
]
ISODateString = Annotated[
    str,
    Field(min_length=10, max_length=10),
    AfterValidator(_validate_iso_date_string),
]


class CompletedWorkContractModel(BaseModel):
    """Closed-world base for the internal CRM HTTP boundary."""

    model_config = ConfigDict(extra="forbid", strict=True)


class CompletedWorkQueryRequest(CompletedWorkContractModel):
    """Validated query parameters for ``GET /v1/agent-query/completed-work``."""

    window: CompletedWorkWindow = "this_week"
    customer_id: str | None = Field(None, min_length=1, max_length=64)
    start_at: str | None = Field(None, min_length=1, max_length=64)
    end_at: str | None = Field(None, min_length=1, max_length=64)
    cursor: str | None = Field(None, min_length=1, max_length=2048)
    limit: int = Field(50, ge=1, le=100)

    @model_validator(mode="after")
    def validate_time_window(self) -> Self:
        has_custom_bounds = self.start_at is not None or self.end_at is not None
        if self.window != "custom":
            if has_custom_bounds:
                raise ValueError("start_at and end_at are only valid for the custom window")
            return self
        if self.start_at is None or self.end_at is None:
            raise ValueError("custom window requires both start_at and end_at")
        start = _parse_http_datetime(self.start_at, field_name="start_at", is_end=False)
        end = _parse_http_datetime(self.end_at, field_name="end_at", is_end=True)
        if end <= start:
            raise ValueError("end_at must be later than start_at")
        return self


def _parse_http_datetime(value: str, *, field_name: str, is_end: bool) -> datetime:
    try:
        if "T" in value:
            parsed = datetime.fromisoformat(value)
        else:
            parsed = datetime.combine(date.fromisoformat(value), time.min)
            if is_end:
                parsed += timedelta(days=1)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date or datetime") from exc
    if parsed.utcoffset() is not None:
        parsed = parsed.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    return parsed


class CompletedWorkCustomer(CompletedWorkContractModel):
    id: str = Field(min_length=1, max_length=64)
    public_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=500)
    account_name: str = Field(min_length=1, max_length=500)


class CompletedWorkAttribution(CompletedWorkContractModel):
    user_id: str = Field(min_length=1, max_length=100)
    field: Literal["owner_id"]
    source: Literal[
        "crm_follow_up_tasks.owner_id",
        "crm_customer_activities.owner_id",
    ]


class CompletedFollowUpTaskPayload(CompletedWorkContractModel):
    id: str = Field(min_length=1, max_length=64)
    public_id: str = Field(min_length=1, max_length=64)
    customer: CompletedWorkCustomer
    owner_id: str = Field(min_length=1, max_length=100)
    creator_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    status: str = Field(min_length=1, max_length=50)
    due_at: ISODateTimeString
    due_at_text: str | None = Field(None, max_length=255)
    completed_at: ISODateTimeString


class CustomerActivityPayload(CompletedWorkContractModel):
    customer: CompletedWorkCustomer | None = None
    activity_kind: str = Field(min_length=1, max_length=50)
    title: str | None = Field(None, max_length=500)
    summary: str | None = None
    next_action: str | None = None
    next_follow_time: ISODateTimeString | None = None
    occurred_at: ISODateTimeString
    owner_id: str = Field(min_length=1, max_length=100)


class CompletedFollowUpTaskFact(CompletedWorkContractModel):
    fact_id: str = Field(min_length=1, max_length=512)
    fact_type: Literal["completed_follow_up_task"]
    source_group: Literal["task"]
    source_table: Literal["crm_follow_up_tasks"]
    source_public_id: str = Field(min_length=1, max_length=64)
    business_key: None = None
    occurred_at: ISODateTimeString
    customer: CompletedWorkCustomer
    attribution: CompletedWorkAttribution
    title: str = Field(min_length=1, max_length=500)
    payload: CompletedFollowUpTaskPayload


class CustomerActivityFact(CompletedWorkContractModel):
    fact_id: str = Field(min_length=1, max_length=512)
    fact_type: Literal["customer_activity"]
    source_group: Literal["activity"]
    source_table: Literal["crm_customer_activities"]
    source_public_id: None = None
    business_key: None = None
    occurred_at: ISODateTimeString
    customer: CompletedWorkCustomer | None = None
    attribution: CompletedWorkAttribution
    title: str = Field(min_length=1, max_length=500)
    payload: CustomerActivityPayload


CompletedWorkFact = CompletedFollowUpTaskFact | CustomerActivityFact


class CompletedWorkSourceCounts(CompletedWorkContractModel):
    completed_follow_up_task: int = Field(0, ge=0)
    customer_activity: int = Field(0, ge=0)

    @property
    def total(self) -> int:
        return self.completed_follow_up_task + self.customer_activity


class CompletedWorkSourceStatus(CompletedWorkContractModel):
    completed_tasks: Literal["queried"]
    customer_activities: Literal["queried"]
    business_events: Literal["skipped"]


class CompletedWorkAppliedFilters(CompletedWorkContractModel):
    window: CompletedWorkWindow
    starts_at: ISODateTimeString
    ends_at: ISODateTimeString
    starts_on: ISODateString
    ends_before: ISODateString
    timezone: Literal["Asia/Shanghai"]
    customer_id: str | None = Field(min_length=1, max_length=64)
    include_tasks: Literal[True]
    include_activities: Literal[True]
    include_business_events: Literal[False]


class CompletedWorkQueryResponse(CompletedWorkContractModel):
    """Typed response body for the completed-work HTTP endpoint."""

    items: list[CompletedWorkFact] = Field(max_length=100)
    available_total: int = Field(ge=0)
    returned_count: int = Field(ge=0, le=100)
    truncated: bool
    next_cursor: str | None = Field(None, min_length=1, max_length=2048)
    source_counts: CompletedWorkSourceCounts
    source_total_counts: CompletedWorkSourceCounts
    source_status: CompletedWorkSourceStatus
    filters: CompletedWorkAppliedFilters

    @model_validator(mode="after")
    def validate_page_totals(self) -> Self:
        if self.returned_count != len(self.items):
            raise ValueError("returned_count must equal the number of items")
        if self.source_counts.total != self.returned_count:
            raise ValueError("source_counts must equal returned_count")
        if self.source_total_counts.total != self.available_total:
            raise ValueError("source_total_counts must equal available_total")
        if self.source_counts.completed_follow_up_task > self.source_total_counts.completed_follow_up_task:
            raise ValueError("returned task count cannot exceed available task count")
        if self.source_counts.customer_activity > self.source_total_counts.customer_activity:
            raise ValueError("returned activity count cannot exceed available activity count")
        if self.truncated != (self.next_cursor is not None):
            raise ValueError("truncated and next_cursor must describe the same page state")
        return self


CompletedWorkHTTPErrorCode = Literal[
    "QUERY_INVALID",
    "PERMISSION_DENIED",
    "INTERNAL_ERROR",
]


class CompletedWorkHTTPError(CompletedWorkContractModel):
    code: CompletedWorkHTTPErrorCode
    status_code: Literal[400, 403, 422, 500]
    detail: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_matching_status(self) -> Self:
        if self.code == "QUERY_INVALID":
            if self.status_code not in {400, 422}:
                raise ValueError("error code and status_code do not match")
            return self
        expected = {
            "PERMISSION_DENIED": 403,
            "INTERNAL_ERROR": 500,
        }[self.code]
        if self.status_code != expected:
            raise ValueError("error code and status_code do not match")
        return self


def map_completed_work_http_error(error: Exception) -> CompletedWorkHTTPError:
    """Freeze endpoint error semantics before the endpoint is implemented in work package 4."""

    from pydantic import ValidationError

    if isinstance(error, PermissionError):
        return CompletedWorkHTTPError(
            code="PERMISSION_DENIED",
            status_code=403,
            detail=str(error) or "permission denied",
        )
    if isinstance(error, ValidationError):
        return CompletedWorkHTTPError(
            code="QUERY_INVALID",
            status_code=422,
            detail="invalid completed-work request",
        )
    if isinstance(error, ValueError):
        return CompletedWorkHTTPError(
            code="QUERY_INVALID",
            status_code=400,
            detail=str(error) or "invalid completed-work query",
        )
    return CompletedWorkHTTPError(
        code="INTERNAL_ERROR",
        status_code=500,
        detail="completed-work query failed",
    )

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

BUSINESS_TIMEZONE = "Asia/Shanghai"
DUE_AT_GRANULARITY_DATE = "DATE"
DUE_AT_GRANULARITY_DATETIME = "DATETIME"
DUE_AT_GRANULARITY_WEEK = "WEEK"
DUE_AT_GRANULARITY_MONTH = "MONTH"
DUE_AT_GRANULARITY_UNKNOWN = "UNKNOWN"
FOLLOW_UP_TASK_DUE_WINDOW_TODAY = "today"
FOLLOW_UP_TASK_DUE_WINDOW_THIS_WEEK = "this_week"
FOLLOW_UP_TASK_DUE_WINDOW_NEXT_WEEK = "next_week"
FOLLOW_UP_TASK_DUE_WINDOW_OVERDUE = "overdue"
FOLLOW_UP_TASK_DUE_WINDOWS = {
    FOLLOW_UP_TASK_DUE_WINDOW_TODAY,
    FOLLOW_UP_TASK_DUE_WINDOW_THIS_WEEK,
    FOLLOW_UP_TASK_DUE_WINDOW_NEXT_WEEK,
    FOLLOW_UP_TASK_DUE_WINDOW_OVERDUE,
}


@dataclass(frozen=True)
class NormalizedDueAt:
    due_at: datetime | None
    due_at_granularity: str
    due_at_timezone: str


@dataclass(frozen=True)
class FollowUpTaskDueWindow:
    name: str
    starts_at: datetime | None
    ends_at: datetime | None
    timezone: str
    anchor_now: datetime


def business_now() -> datetime:
    """Return current business-local time for naive DateTime columns."""
    return datetime.now(ZoneInfo(BUSINESS_TIMEZONE)).replace(tzinfo=None)


def business_today() -> date:
    return business_now().date()


def normalize_business_timezone(timezone_name: str | None = None) -> str:
    normalized = timezone_name or BUSINESS_TIMEZONE
    ZoneInfo(normalized)
    return normalized


def to_business_naive(value: datetime, timezone_name: str | None = None) -> datetime:
    timezone = normalize_business_timezone(timezone_name)
    if value.tzinfo is None:
        return value.replace(tzinfo=None)
    return value.astimezone(ZoneInfo(timezone)).replace(tzinfo=None)


def normalize_due_at(
    value: date | datetime | None,
    *,
    granularity: str | None = None,
    timezone_name: str | None = None,
) -> NormalizedDueAt:
    timezone = normalize_business_timezone(timezone_name)
    if value is None:
        return NormalizedDueAt(
            due_at=None,
            due_at_granularity=granularity or DUE_AT_GRANULARITY_UNKNOWN,
            due_at_timezone=timezone,
        )

    if isinstance(value, datetime):
        due_at = to_business_naive(value, timezone)
        resolved_granularity = granularity or DUE_AT_GRANULARITY_DATETIME
    else:
        due_at = datetime.combine(value, time.min)
        resolved_granularity = granularity or DUE_AT_GRANULARITY_DATE

    if resolved_granularity == DUE_AT_GRANULARITY_WEEK:
        due_at = _start_of_week(due_at)
    elif resolved_granularity == DUE_AT_GRANULARITY_MONTH:
        due_at = due_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif resolved_granularity in {DUE_AT_GRANULARITY_DATE, DUE_AT_GRANULARITY_UNKNOWN}:
        due_at = _start_of_day(due_at)

    return NormalizedDueAt(
        due_at=due_at,
        due_at_granularity=resolved_granularity,
        due_at_timezone=timezone,
    )


def calculate_follow_up_task_due_window(
    window: str,
    *,
    now: datetime | None = None,
    timezone_name: str | None = None,
) -> FollowUpTaskDueWindow:
    if window not in FOLLOW_UP_TASK_DUE_WINDOWS:
        raise ValueError(f"未知跟进任务时间窗口: {window}")

    timezone = normalize_business_timezone(timezone_name)
    anchor_now = to_business_naive(now, timezone) if now is not None else business_now()
    today_start = _start_of_day(anchor_now)
    this_week_start = _start_of_week(anchor_now)

    if window == FOLLOW_UP_TASK_DUE_WINDOW_TODAY:
        starts_at = today_start
        ends_at = today_start + timedelta(days=1)
    elif window == FOLLOW_UP_TASK_DUE_WINDOW_THIS_WEEK:
        starts_at = this_week_start
        ends_at = this_week_start + timedelta(days=7)
    elif window == FOLLOW_UP_TASK_DUE_WINDOW_NEXT_WEEK:
        starts_at = this_week_start + timedelta(days=7)
        ends_at = this_week_start + timedelta(days=14)
    else:
        starts_at = None
        ends_at = today_start

    return FollowUpTaskDueWindow(
        name=window,
        starts_at=starts_at,
        ends_at=ends_at,
        timezone=timezone,
        anchor_now=anchor_now,
    )


def _start_of_day(value: datetime) -> datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_week(value: datetime) -> datetime:
    return _start_of_day(value) - timedelta(days=value.weekday())

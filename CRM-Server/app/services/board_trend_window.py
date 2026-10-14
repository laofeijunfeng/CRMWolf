from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.list_query.engine import parse_date_value
from app.core.list_query.types import FilterCondition


@dataclass(frozen=True)
class BoardTrendWindow:
    event_start: date | None
    event_end: date | None
    months: tuple[str, ...]

    @property
    def empty(self) -> bool:
        return not self.months

    def __post_init__(self) -> None:
        if self.empty:
            if self.event_start is not None or self.event_end is not None:
                raise ValueError("empty trend window has no event interval")
        elif self.event_start is None or self.event_end is None:
            raise ValueError("nonempty trend window requires closed event bounds")
        elif self.event_start > self.event_end:
            raise ValueError("reversed trend event interval")


def month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _shift_month(value: date, offset: int) -> date:
    ordinal = value.year * 12 + value.month - 1 + offset
    year, zero_based_month = divmod(ordinal, 12)
    return date(year, zero_based_month + 1, 1)


def extract_board_date_bounds(
    filters: Sequence[FilterCondition] | None,
    field: str,
) -> tuple[date | None, date | None]:
    lower: date | None = None
    upper: date | None = None
    for condition in filters or ():
        if condition.field != field or condition.op not in {"eq", "after", "before"}:
            continue
        parsed = parse_date_value(condition.value)
        if parsed is None:
            continue
        day = parsed.date()
        if condition.op in {"eq", "after"}:
            lower = day if lower is None else max(lower, day)
        if condition.op in {"eq", "before"}:
            upper = day if upper is None else min(upper, day)
    return lower, upper


def resolve_board_trend_window(
    *,
    today: date,
    start_bound: date | None,
    end_bound: date | None,
) -> BoardTrendWindow:
    latest_complete_day = today.replace(day=1) - timedelta(days=1)
    if start_bound is not None and start_bound > latest_complete_day:
        return BoardTrendWindow(None, None, ())
    if start_bound is not None and end_bound is not None:
        start, end = start_bound, end_bound
    elif start_bound is not None:
        start, end = start_bound, latest_complete_day
    else:
        end = min(end_bound, latest_complete_day) if end_bound is not None else latest_complete_day
        start = _shift_month(end.replace(day=1), -5)
    if end < start:
        return BoardTrendWindow(None, None, ())
    cursor, last = start.replace(day=1), end.replace(day=1)
    months: list[str] = []
    while cursor <= last:
        months.append(month_key(cursor))
        cursor = _shift_month(cursor, 1)
    return BoardTrendWindow(start, end, tuple(months))

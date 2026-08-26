"""Reproducible business-time parsing for one-version migration commands."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

_BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")


def parse_business_as_of(value: str) -> datetime:
    """Parse an aware ISO timestamp and return Shanghai-naive database time."""

    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError("--as-of must be an ISO-8601 datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--as-of must include a timezone offset")
    return parsed.astimezone(_BUSINESS_TIMEZONE).replace(tzinfo=None)

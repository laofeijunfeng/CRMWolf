from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


BUSINESS_TIMEZONE = "Asia/Shanghai"


def business_now() -> datetime:
    """Return current business-local time for naive DateTime columns."""
    return datetime.now(ZoneInfo(BUSINESS_TIMEZONE)).replace(tzinfo=None)


def business_today() -> date:
    return business_now().date()

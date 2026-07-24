"""Temporal normalization for CRM AI Agent."""
from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from app.services.agent.schemas import AgentTemporalExpression


DEFAULT_AGENT_TIMEZONE = "Asia/Shanghai"
DEFAULT_FOLLOW_UP_HOUR = 9
DEFAULT_FOLLOW_UP_MINUTE = 0


class AgentTemporalResolver:
    """Resolve AI-extracted temporal slots into concrete datetimes."""

    def __init__(self, timezone: str = DEFAULT_AGENT_TIMEZONE) -> None:
        self.timezone = timezone

    def now(self) -> datetime:
        return datetime.now(ZoneInfo(self.timezone))

    def resolve_follow_up_time(
        self,
        expression: Optional[AgentTemporalExpression],
        *,
        base_datetime: Optional[datetime] = None,
    ) -> Optional[str]:
        if not expression or expression.kind in {"NONE", "UNKNOWN"}:
            return None
        if expression.confidence < 0.7:
            return None

        base = base_datetime or self.now()
        resolved_date = self._resolve_date(expression, base.date())
        if resolved_date is None:
            return None

        resolved_time = time(
            hour=expression.hour if expression.hour is not None else DEFAULT_FOLLOW_UP_HOUR,
            minute=expression.minute if expression.minute is not None else DEFAULT_FOLLOW_UP_MINUTE,
        )
        return datetime.combine(resolved_date, resolved_time).isoformat()

    def resolve_date(
        self,
        expression: Optional[AgentTemporalExpression],
        *,
        base_datetime: Optional[datetime] = None,
    ) -> Optional[str]:
        if not expression or expression.kind in {"NONE", "UNKNOWN"}:
            return None
        if expression.confidence < 0.7:
            return None

        base = base_datetime or self.now()
        resolved_date = self._resolve_date(expression, base.date())
        return resolved_date.isoformat() if resolved_date else None

    def _resolve_date(self, expression: AgentTemporalExpression, base_date: date) -> Optional[date]:
        if expression.kind == "EXPLICIT_DATE" and expression.date_text:
            try:
                return date.fromisoformat(expression.date_text)
            except ValueError:
                return None

        if expression.kind == "MONTH_DAY":
            year = expression.year or base_date.year
            if expression.month is None or expression.day is None:
                return None
            if expression.year is None and (expression.month, expression.day) < (base_date.month, base_date.day):
                year += 1
            try:
                return date(year, expression.month, expression.day)
            except ValueError:
                return None

        if expression.kind == "MONTH_END":
            month = expression.month or base_date.month
            year = expression.year or base_date.year
            if expression.year is None and expression.month is not None and expression.month < base_date.month:
                year += 1
            try:
                return date(year, month, calendar.monthrange(year, month)[1])
            except ValueError:
                return None

        if expression.kind == "RELATIVE_MONTH_END":
            amount = expression.amount
            if amount is None:
                amount = 0 if expression.direction == "current" else 1
            if expression.direction == "past":
                amount = -amount
            total_month = base_date.month - 1 + amount
            year = base_date.year + total_month // 12
            month = total_month % 12 + 1
            return date(year, month, calendar.monthrange(year, month)[1])

        if expression.kind == "RELATIVE_DAY":
            amount = expression.amount
            if amount is None:
                if expression.direction == "current":
                    amount = 0
                elif expression.direction in {"next", "future"}:
                    amount = 1
            if amount is None:
                return None
            if expression.direction == "past":
                return base_date - timedelta(days=amount)
            return base_date + timedelta(days=amount)

        if expression.kind == "RELATIVE_WEEKDAY" and expression.weekday:
            if expression.direction == "next":
                monday = base_date - timedelta(days=base_date.isoweekday() - 1)
                return monday + timedelta(days=7 + expression.weekday - 1)
            if expression.direction in {"current", "future", None}:
                delta = expression.weekday - base_date.isoweekday()
                if delta < 0 or expression.direction == "future" and delta == 0:
                    delta += 7
                return base_date + timedelta(days=delta)

        return None


agent_temporal_resolver = AgentTemporalResolver()

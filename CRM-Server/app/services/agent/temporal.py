"""Temporal normalization for CRM AI Agent."""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from app.services.agent.schemas import AgentTemporalExpression


DEFAULT_AGENT_TIMEZONE = "Asia/Shanghai"
DEFAULT_FOLLOW_UP_HOUR = 9
DEFAULT_FOLLOW_UP_MINUTE = 0

_WEEKDAY_BY_TEXT = {
    "一": 1,
    "1": 1,
    "二": 2,
    "2": 2,
    "三": 3,
    "3": 3,
    "四": 4,
    "4": 4,
    "五": 5,
    "5": 5,
    "六": 6,
    "6": 6,
    "日": 7,
    "天": 7,
    "7": 7,
}
_CHINESE_NUMBERS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


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
        if self._looks_suspicious_for_raw_text(expression, base.date(), resolved_date):
            return None

        resolved_time = time(
            hour=expression.hour if expression.hour is not None else DEFAULT_FOLLOW_UP_HOUR,
            minute=expression.minute if expression.minute is not None else DEFAULT_FOLLOW_UP_MINUTE,
        )
        return datetime.combine(resolved_date, resolved_time).isoformat()

    def resolve_follow_up_time_text(
        self,
        raw_text: Optional[str],
        *,
        base_datetime: Optional[datetime] = None,
    ) -> Optional[str]:
        expression = self.expression_from_text(raw_text)
        return self.resolve_follow_up_time(expression, base_datetime=base_datetime)

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
        if resolved_date and self._looks_suspicious_for_raw_text(expression, base.date(), resolved_date):
            return None
        return resolved_date.isoformat() if resolved_date else None

    def expression_from_text(self, raw_text: Optional[str]) -> Optional[AgentTemporalExpression]:
        text = _normalize_temporal_text(raw_text)
        if not text:
            return None

        if re.fullmatch(r"20[0-9]{2}-[0-9]{1,2}-[0-9]{1,2}", text):
            try:
                parsed_date = date.fromisoformat(text)
            except ValueError:
                return None
            return AgentTemporalExpression(
                raw_text=raw_text,
                kind="EXPLICIT_DATE",
                date_text=parsed_date.isoformat(),
                confidence=0.95,
            )

        if text in {"今天", "今日"}:
            return AgentTemporalExpression(
                raw_text=raw_text,
                kind="RELATIVE_DAY",
                direction="current",
                amount=0,
                unit="day",
                confidence=0.95,
            )
        if text == "明天":
            return AgentTemporalExpression(
                raw_text=raw_text,
                kind="RELATIVE_DAY",
                direction="future",
                amount=1,
                unit="day",
                confidence=0.95,
            )
        if text == "后天":
            return AgentTemporalExpression(
                raw_text=raw_text,
                kind="RELATIVE_DAY",
                direction="future",
                amount=2,
                unit="day",
                confidence=0.95,
            )
        if text == "大后天":
            return AgentTemporalExpression(
                raw_text=raw_text,
                kind="RELATIVE_DAY",
                direction="future",
                amount=3,
                unit="day",
                confidence=0.95,
            )
        if text == "半个月后":
            return AgentTemporalExpression(
                raw_text=raw_text,
                kind="RELATIVE_DAY",
                direction="future",
                amount=14,
                unit="day",
                confidence=0.9,
            )
        if text in {"下周", "下星期", "下礼拜"}:
            return AgentTemporalExpression(
                raw_text=raw_text,
                kind="RELATIVE_WEEK",
                direction="future",
                amount=1,
                unit="week",
                confidence=0.9,
            )
        if text in {"本周末", "这周末", "这个周末", "周末"}:
            return AgentTemporalExpression(
                raw_text=raw_text,
                kind="RELATIVE_WEEKDAY",
                direction="current",
                weekday=6,
                confidence=0.9,
            )
        if text in {"下周末", "下星期末", "下礼拜末"}:
            return AgentTemporalExpression(
                raw_text=raw_text,
                kind="RELATIVE_WEEKDAY",
                direction="next",
                amount=1,
                unit="week",
                weekday=6,
                confidence=0.9,
            )

        weekday_expression = self._weekday_expression_from_text(raw_text, text)
        if weekday_expression is not None:
            return weekday_expression

        relative_expression = self._relative_expression_from_text(raw_text, text)
        if relative_expression is not None:
            return relative_expression

        month_day_expression = self._month_day_expression_from_text(raw_text, text)
        if month_day_expression is not None:
            return month_day_expression

        if text in {"月底", "本月底", "这个月底", "本月末", "这个月末"}:
            return AgentTemporalExpression(
                raw_text=raw_text,
                kind="MONTH_END",
                direction="current",
                confidence=0.9,
            )
        if text in {"下月底", "下月末"}:
            return AgentTemporalExpression(
                raw_text=raw_text,
                kind="RELATIVE_MONTH_END",
                direction="future",
                amount=1,
                unit="month",
                confidence=0.9,
            )
        return None

    def _resolve_date(self, expression: AgentTemporalExpression, base_date: date) -> Optional[date]:
        if not self._is_kind_unit_consistent(expression):
            return None

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

        if expression.kind == "RELATIVE_WEEK":
            amount = expression.amount
            if amount is None:
                if expression.direction == "current":
                    amount = 0
                elif expression.direction in {"next", "future"}:
                    amount = 1
            if amount is None:
                return None
            days = amount * 7
            if expression.direction == "past":
                return base_date - timedelta(days=days)
            return base_date + timedelta(days=days)

        if expression.kind == "RELATIVE_MONTH":
            amount = expression.amount
            if amount is None:
                if expression.direction == "current":
                    amount = 0
                elif expression.direction in {"next", "future"}:
                    amount = 1
            if amount is None:
                return None
            if expression.direction == "past":
                amount = -amount
            return self._add_months(base_date, amount)

        if expression.kind == "RELATIVE_YEAR":
            amount = expression.amount
            if amount is None:
                if expression.direction == "current":
                    amount = 0
                elif expression.direction in {"next", "future"}:
                    amount = 1
            if amount is None:
                return None
            if expression.direction == "past":
                amount = -amount
            return self._add_months(base_date, amount * 12)

        if expression.kind == "RELATIVE_WEEKDAY" and expression.weekday:
            if expression.direction == "next":
                week_offset = expression.amount if expression.amount is not None else 1
                monday = base_date - timedelta(days=base_date.isoweekday() - 1)
                return monday + timedelta(days=week_offset * 7 + expression.weekday - 1)
            if expression.direction in {"current", "future", None}:
                delta = expression.weekday - base_date.isoweekday()
                if delta < 0 or expression.direction == "future" and delta == 0:
                    delta += 7
                return base_date + timedelta(days=delta)

        return None

    def _weekday_expression_from_text(
        self,
        raw_text: Optional[str],
        text: str,
    ) -> Optional[AgentTemporalExpression]:
        match = re.fullmatch(r"(?:(本|这|下|下下)?(?:周|星期|礼拜))([一二三四五六日天1-7])", text)
        if not match:
            return None
        prefix, weekday_text = match.groups()
        weekday = _WEEKDAY_BY_TEXT.get(weekday_text)
        if weekday is None:
            return None
        direction = "next" if prefix in {"下", "下下"} else "current"
        if prefix == "下下":
            return AgentTemporalExpression(
                raw_text=raw_text,
                kind="RELATIVE_WEEKDAY",
                direction="next",
                amount=2,
                unit="week",
                weekday=weekday,
                confidence=0.9,
            )
        return AgentTemporalExpression(
            raw_text=raw_text,
            kind="RELATIVE_WEEKDAY",
            direction=direction,
            weekday=weekday,
            confidence=0.95,
        )

    def _relative_expression_from_text(
        self,
        raw_text: Optional[str],
        text: str,
    ) -> Optional[AgentTemporalExpression]:
        match = re.fullmatch(r"([0-9一二两三四五六七八九十]+)(天|日|周|星期|礼拜|个月|月|年)(?:后|以后|之后)", text)
        if not match:
            return None
        amount = _parse_small_positive_int(match.group(1))
        if amount is None:
            return None
        unit_text = match.group(2)
        kind_by_unit = {
            "天": ("RELATIVE_DAY", "day"),
            "日": ("RELATIVE_DAY", "day"),
            "周": ("RELATIVE_WEEK", "week"),
            "星期": ("RELATIVE_WEEK", "week"),
            "礼拜": ("RELATIVE_WEEK", "week"),
            "个月": ("RELATIVE_MONTH", "month"),
            "月": ("RELATIVE_MONTH", "month"),
            "年": ("RELATIVE_YEAR", "year"),
        }
        kind, unit = kind_by_unit[unit_text]
        return AgentTemporalExpression(
            raw_text=raw_text,
            kind=kind,
            direction="future",
            amount=amount,
            unit=unit,
            confidence=0.95,
        )

    def _month_day_expression_from_text(
        self,
        raw_text: Optional[str],
        text: str,
    ) -> Optional[AgentTemporalExpression]:
        match = re.fullmatch(r"(?:(20[0-9]{2})年)?([0-9]{1,2})月([0-9]{1,2})(?:日|号)?", text)
        if not match:
            return None
        year_text, month_text, day_text = match.groups()
        return AgentTemporalExpression(
            raw_text=raw_text,
            kind="MONTH_DAY",
            year=int(year_text) if year_text else None,
            month=int(month_text),
            day=int(day_text),
            confidence=0.95,
        )

    def _is_kind_unit_consistent(self, expression: AgentTemporalExpression) -> bool:
        expected_units = {
            "RELATIVE_DAY": "day",
            "RELATIVE_WEEK": "week",
            "RELATIVE_MONTH": "month",
            "RELATIVE_YEAR": "year",
            "RELATIVE_MONTH_END": "month",
        }
        expected_unit = expected_units.get(expression.kind)
        return expected_unit is None or expression.unit in {None, expected_unit}

    def _add_months(self, value: date, months: int) -> date:
        total_month = value.month - 1 + months
        year = value.year + total_month // 12
        month = total_month % 12 + 1
        day = min(value.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)

    def _looks_suspicious_for_raw_text(
        self,
        expression: AgentTemporalExpression,
        base_date: date,
        resolved_date: date,
    ) -> bool:
        if not expression.kind.startswith("RELATIVE_"):
            return False
        if expression.kind == "RELATIVE_WEEKDAY":
            return False
        raw_text = expression.raw_text or ""
        if any(marker in raw_text for marker in ("季度", "年")):
            return 0 < abs((resolved_date - base_date).days) < 28
        if "半个月" in raw_text:
            return False
        if any(marker in raw_text for marker in ("个月", "月后", "月以后", "月之后")):
            return 0 < abs((resolved_date - base_date).days) < 21
        if "周" in raw_text and (expression.amount or 1) >= 1:
            return 0 < abs((resolved_date - base_date).days) < 5
        return False


def _normalize_temporal_text(raw_text: Optional[str]) -> str:
    if not isinstance(raw_text, str):
        return ""
    return re.sub(r"\s+", "", raw_text.strip())


def _parse_small_positive_int(value: str) -> Optional[int]:
    if value.isdigit():
        parsed = int(value)
        return parsed if parsed >= 0 else None
    if value in _CHINESE_NUMBERS:
        return _CHINESE_NUMBERS[value]
    if value.startswith("十") and len(value) == 2:
        suffix = _CHINESE_NUMBERS.get(value[1])
        return 10 + suffix if suffix is not None else None
    if value.endswith("十") and len(value) == 2:
        prefix = _CHINESE_NUMBERS.get(value[0])
        return prefix * 10 if prefix is not None else None
    if "十" in value and len(value) == 3:
        prefix = _CHINESE_NUMBERS.get(value[0])
        suffix = _CHINESE_NUMBERS.get(value[2])
        if prefix is not None and suffix is not None:
            return prefix * 10 + suffix
    return None


agent_temporal_resolver = AgentTemporalResolver()

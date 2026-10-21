from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

FieldType = Literal["text", "enum", "date", "number"]
DateSemantics = Literal["day_bounds", "exclusive"]
DateKind = Literal["date", "datetime"]
SortDirection = Literal["asc", "desc"]

VALUE_REQUIRED_OPS = frozenset(
    {
        "eq",
        "neq",
        "contains",
        "not_contains",
        "in",
        "not_in",
        "before",
        "after",
        "between",
        "gt",
        "gte",
        "lt",
        "lte",
    }
)
EMPTY_OPS = frozenset({"is_empty", "is_not_empty"})
DATE_PRESET_OPS = frozenset(
    {
        "past_1_day",
        "past_3_days",
        "past_1_week",
        "past_1_month",
        "past_3_months",
        "past_6_months",
        "past_1_year",
    }
)
DEFAULT_OPS: dict[str, frozenset[str]] = {
    "text": frozenset({"eq", "neq", "contains", "not_contains", "is_empty", "is_not_empty"}),
    "enum": frozenset({"eq", "neq", "contains", "not_contains", "in", "not_in", "is_empty", "is_not_empty"}),
    "date": frozenset({"eq", "before", "after", "between", "is_empty", "is_not_empty"}) | DATE_PRESET_OPS,
    "number": frozenset({"eq", "neq", "gt", "gte", "lt", "lte", "is_empty", "is_not_empty"}),
}


class FilterCondition(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: str
    op: str
    value: Any = None


class SortCondition(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: str
    direction: SortDirection = "asc"


@dataclass
class ListQueryContext:
    db: Session | None = None
    team_id: int | None = None
    current_user_id: str | None = None
    today: date | None = None
    now: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def business_today(self) -> date:
        if self.today is not None:
            return self.today
        from app.utils.time import business_now

        return business_now().date()

    def business_now(self) -> datetime:
        if self.now is not None:
            return self.now
        from app.utils.time import business_now

        return business_now()


@dataclass(frozen=True)
class JoinSpec:
    key: str
    target: Any
    onclause: Any
    isouter: bool = False

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    StringConstraints,
    model_validator,
)

Count = Annotated[StrictInt, Field(ge=0)]
EntityId = Annotated[StrictInt, Field(gt=0)]
AmountString = Annotated[StrictStr, StringConstraints(pattern=r"^-?\d+\.\d{2}$")]
Percentage = Annotated[StrictFloat, Field(ge=0, le=100, allow_inf_nan=False)]
BoardTone = Literal["neutral", "info", "success", "warning", "danger", "muted"]


def _valid_date(value: str) -> str:
    date.fromisoformat(value)
    return value


def _valid_month(value: str) -> str:
    date.fromisoformat(f"{value}-01")
    return value


DateString = Annotated[
    StrictStr,
    StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$"),
    AfterValidator(_valid_date),
]
MonthString = Annotated[
    StrictStr,
    StringConstraints(pattern=r"^\d{4}-\d{2}$"),
    AfterValidator(_valid_month),
]


class StrictBoardModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class BoardOwner(StrictBoardModel):
    id: StrictStr
    name: StrictStr
    avatar_url: StrictStr | None = None


class BoardMetricBase(StrictBoardModel):
    key: StrictStr
    label: StrictStr
    secondary_label: StrictStr | None = None

    @model_validator(mode="after")
    def validate_secondary_label(self) -> Self:
        secondary_value = getattr(self, "secondary_value", None)
        if (secondary_value is not None) != (self.secondary_label is not None):
            raise ValueError("secondary value and label must be present together")
        return self


class BoardCountMetric(BoardMetricBase):
    value_type: Literal["count"]
    value: Count | None
    secondary_value: Count | None = None


class BoardAmountMetric(BoardMetricBase):
    value_type: Literal["amount"]
    value: AmountString | None
    secondary_value: AmountString | None = None


class BoardPercentageMetric(BoardMetricBase):
    value_type: Literal["percentage"]
    value: Percentage | None
    secondary_value: Percentage | None = None


BoardMetric = Annotated[
    BoardCountMetric | BoardAmountMetric | BoardPercentageMetric,
    Field(discriminator="value_type"),
]


def validate_preview_counts(*, count: int, shown: int, has_more: bool, remaining: int) -> None:
    if count < 0 or shown != min(count, 5) or remaining != count - shown or has_more != (remaining > 0):
        raise ValueError("inconsistent board preview counts")


def validate_full_column_counts(*, count: int, shown: int, has_more: bool, remaining: int) -> None:
    if count < 0 or shown != count or remaining != 0 or has_more:
        raise ValueError("inconsistent board column counts")

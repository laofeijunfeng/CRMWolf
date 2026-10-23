from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.schemas.board_primitives import (
    AmountString,
    BoardMetricBase,
    BoardOwner,
    BoardTone,
    Count,
    DateString,
    MonthString,
    Percentage,
    StrictBoardModel,
    validate_full_column_counts,
)


class CustomerBoardMetadata(StrictBoardModel):
    stage_hint: str | None = None
    industry: str | None = None
    city: str | None = None
    company_scale: str | None = None
    license_type: Literal["TRIAL", "OFFICIAL"] | None = None
    license_expiry_date: DateString | None = None


class CustomerBoardActionState(StrictBoardModel):
    can_edit: bool
    can_delete: bool
    can_assign: bool
    can_create_opportunity: bool


class CustomerBoardItem(StrictBoardModel):
    id: str
    title: str
    subtitle: str | None
    amount: AmountString | None
    date: DateString | None
    owner: BoardOwner | None
    status: Literal["not_started", "following", "repurchasing", "won", "lost"]
    metadata: CustomerBoardMetadata
    action_state: CustomerBoardActionState


class CustomerBoardColumn(StrictBoardModel):
    key: Literal["not_started", "following", "repurchasing", "won", "lost"]
    label: str
    tone: BoardTone
    count: Count
    amount: AmountString | None
    items: list[CustomerBoardItem]
    has_more: bool
    remaining_count: Count

    @model_validator(mode="after")
    def validate_preview(self) -> Self:
        validate_full_column_counts(
            count=self.count,
            shown=len(self.items),
            has_more=self.has_more,
            remaining=self.remaining_count,
        )
        return self


class CustomerCountMetric(BoardMetricBase):
    key: Literal[
        "total_count",
        "following_count",
        "repurchasing_count",
        "won_count",
        "recent_new_count",
    ]
    value_type: Literal["count"]
    value: Count
    secondary_value: Count | None = None


class CustomerPercentageMetric(BoardMetricBase):
    key: Literal[
        "not_started_percentage",
        "following_percentage",
        "repurchasing_percentage",
        "won_percentage",
        "lost_percentage",
    ]
    value_type: Literal["percentage"]
    value: Percentage | None
    secondary_value: Percentage | None = None


CustomerBoardMetric = Annotated[
    CustomerCountMetric | CustomerPercentageMetric,
    Field(discriminator="value_type"),
]


class CustomerBoardTrendPoint(StrictBoardModel):
    date: MonthString
    count: Count


class CustomerBoardResponse(StrictBoardModel):
    summary: list[CustomerBoardMetric]
    columns: list[CustomerBoardColumn]
    trends: list[CustomerBoardTrendPoint]

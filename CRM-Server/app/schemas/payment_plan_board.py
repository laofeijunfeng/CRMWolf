from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.schemas.board_primitives import (
    AmountString,
    BoardMetricBase,
    BoardOwner,
    BoardTone,
    Count,
    DateString,
    EntityId,
    MonthString,
    StrictBoardModel,
    validate_full_column_counts,
)


class PaymentPlanBoardMetadata(StrictBoardModel):
    customer_name: str | None = None
    contract_name: str | None = None
    opportunity_name: str | None = None
    paid_amount: AmountString
    remaining_amount: AmountString


class PaymentPlanBoardActionState(StrictBoardModel):
    can_edit: bool
    can_delete: bool
    can_view_detail: bool


class PaymentPlanBoardItem(StrictBoardModel):
    id: EntityId
    title: str
    subtitle: str | None
    amount: AmountString
    planned_amount: AmountString
    paid_amount: AmountString
    remaining_amount: AmountString
    date: DateString | None
    owner: BoardOwner | None
    status: Literal["PENDING", "OVERDUE", "PARTIAL", "COMPLETED", "UNCLASSIFIED"]
    metadata: PaymentPlanBoardMetadata
    action_state: PaymentPlanBoardActionState


class PaymentPlanBoardColumn(StrictBoardModel):
    key: Literal["PENDING", "OVERDUE", "PARTIAL", "COMPLETED", "UNCLASSIFIED"]
    label: str
    tone: BoardTone
    count: Count
    amount: AmountString
    planned_amount: AmountString
    paid_amount: AmountString
    remaining_amount: AmountString
    overdue_remaining_amount: AmountString
    items: list[PaymentPlanBoardItem]
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


class PaymentPlanCountMetric(BoardMetricBase):
    key: Literal["overdue_count"]
    value_type: Literal["count"]
    value: Count
    secondary_value: Count | None = None


class PaymentPlanAmountMetric(BoardMetricBase):
    key: Literal[
        "planned_amount",
        "paid_amount",
        "remaining_amount",
        "overdue_remaining_amount",
    ]
    value_type: Literal["amount"]
    value: AmountString
    secondary_value: AmountString | None = None


PaymentPlanBoardMetric = Annotated[
    PaymentPlanCountMetric | PaymentPlanAmountMetric,
    Field(discriminator="value_type"),
]


class PaymentPlanBoardTrendPoint(StrictBoardModel):
    date: MonthString
    count: Count
    planned_amount: AmountString
    paid_amount: AmountString
    remaining_amount: AmountString


class PaymentPlanBoardResponse(StrictBoardModel):
    summary: list[PaymentPlanBoardMetric]
    columns: list[PaymentPlanBoardColumn]
    trends: list[PaymentPlanBoardTrendPoint]

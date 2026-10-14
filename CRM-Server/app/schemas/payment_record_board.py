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
    validate_preview_counts,
)


class PaymentRecordBoardMetadata(StrictBoardModel):
    customer_name: str | None = None
    contract_name: str | None = None
    actual_payer_name: str | None = None
    creator_name: str | None = None
    owner_name: str | None = None
    commission_member_name: str | None = None
    approval_phase: str | None = None
    approval_id: EntityId | None = None
    confirmation_status: Literal["PENDING", "CONFIRMED", "DISPUTED"] | None = None


class PaymentRecordBoardActionState(StrictBoardModel):
    can_edit: bool
    can_delete: bool
    can_resubmit: bool


class PaymentRecordBoardItem(StrictBoardModel):
    id: EntityId
    title: str
    subtitle: str | None
    amount: AmountString
    actual_amount: AmountString
    date: DateString | None
    owner: BoardOwner | None
    status: Literal[
        "pending_submit",
        "pending_approval",
        "rejected",
        "approved",
        "unclassified",
    ]
    metadata: PaymentRecordBoardMetadata
    action_state: PaymentRecordBoardActionState


class PaymentRecordBoardColumn(StrictBoardModel):
    key: Literal[
        "pending_submit",
        "pending_approval",
        "rejected",
        "approved",
        "unclassified",
    ]
    label: str
    tone: BoardTone
    count: Count
    amount: AmountString
    actual_amount: AmountString
    confirmed_amount: AmountString
    unconfirmed_amount: AmountString
    items: list[PaymentRecordBoardItem]
    has_more: bool
    remaining_count: Count

    @model_validator(mode="after")
    def validate_preview(self) -> Self:
        validate_preview_counts(
            count=self.count,
            shown=len(self.items),
            has_more=self.has_more,
            remaining=self.remaining_count,
        )
        return self


class PaymentRecordCountMetric(BoardMetricBase):
    key: Literal["total_count", "rejected_count"]
    value_type: Literal["count"]
    value: Count
    secondary_value: Count | None = None


class PaymentRecordAmountMetric(BoardMetricBase):
    key: Literal["actual_total", "confirmed_amount", "unconfirmed_amount"]
    value_type: Literal["amount"]
    value: AmountString
    secondary_value: AmountString | None = None


PaymentRecordBoardMetric = Annotated[
    PaymentRecordCountMetric | PaymentRecordAmountMetric,
    Field(discriminator="value_type"),
]


class PaymentRecordBoardTrendPoint(StrictBoardModel):
    date: MonthString
    count: Count
    actual_amount: AmountString
    confirmed_amount: AmountString
    unconfirmed_amount: AmountString


class PaymentRecordBoardResponse(StrictBoardModel):
    summary: list[PaymentRecordBoardMetric]
    columns: list[PaymentRecordBoardColumn]
    trends: list[PaymentRecordBoardTrendPoint]

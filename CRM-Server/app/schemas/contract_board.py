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


class ContractBoardMetadata(StrictBoardModel):
    customer_name: str | None = None
    opportunity_name: str | None = None
    license_type: str | None = None
    purchase_type: str | None = None
    signing_date: DateString | None = None
    effective_date: DateString | None = None
    expiry_date: DateString | None = None
    license_expiry_date: DateString | None = None
    authorized_users: Count | None = None


class ContractBoardActionState(StrictBoardModel):
    can_edit: bool
    can_delete: bool
    can_submit_approval: bool
    can_approve: bool
    can_reject: bool


class ContractBoardItem(StrictBoardModel):
    id: EntityId
    title: str
    subtitle: str | None
    amount: AmountString | None
    date: DateString | None
    owner: BoardOwner | None
    status: Literal[
        "DRAFT",
        "PENDING_REVIEW",
        "SIGNED",
        "EFFECTIVE",
        "EXPIRED",
        "TERMINATED",
        "UNCLASSIFIED",
    ]
    metadata: ContractBoardMetadata
    action_state: ContractBoardActionState


class ContractBoardColumn(StrictBoardModel):
    key: Literal[
        "DRAFT",
        "PENDING_REVIEW",
        "SIGNED",
        "EFFECTIVE",
        "EXPIRED",
        "TERMINATED",
        "UNCLASSIFIED",
    ]
    label: str
    tone: BoardTone
    count: Count
    amount: AmountString
    items: list[ContractBoardItem]
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


class ContractCountMetric(BoardMetricBase):
    key: Literal["total_count", "pending_review_count"]
    value_type: Literal["count"]
    value: Count
    secondary_value: Count | None = None


class ContractAmountMetric(BoardMetricBase):
    key: Literal["total_amount", "signed_effective_amount"]
    value_type: Literal["amount"]
    value: AmountString
    secondary_value: AmountString | None = None


ContractBoardMetric = Annotated[
    ContractCountMetric | ContractAmountMetric,
    Field(discriminator="value_type"),
]


class ContractBoardTrendPoint(StrictBoardModel):
    date: MonthString
    count: Count
    amount: AmountString


class ContractBoardResponse(StrictBoardModel):
    summary: list[ContractBoardMetric]
    columns: list[ContractBoardColumn]
    trends: list[ContractBoardTrendPoint]

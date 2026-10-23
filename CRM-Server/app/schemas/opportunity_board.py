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
    Percentage,
    StrictBoardModel,
    validate_full_column_counts,
)


class OpportunityBoardMetadata(StrictBoardModel):
    customer_name: str | None = None
    purchase_type: str | None = None
    license_type: str | None = None
    expected_closing_date: DateString | None = None
    win_probability: Percentage | None = None
    stage_name: str | None = None
    stage_sort_order: int | None = None
    procurement_method_name: str | None = None
    procurement_method_code: str | None = None
    procurement_stage_template_id: EntityId | None = None
    template_code: str | None = None


class OpportunityBoardActionState(StrictBoardModel):
    can_edit: bool
    can_delete: bool
    can_move_stage: bool
    can_mark_won: bool
    can_mark_lost: bool


class OpportunityBoardItem(StrictBoardModel):
    id: str
    title: str
    subtitle: str | None
    amount: AmountString | None
    date: DateString | None
    owner: BoardOwner | None
    status: Literal["active", "won", "lost", "unset_stage"]
    metadata: OpportunityBoardMetadata
    action_state: OpportunityBoardActionState


class OpportunityBoardColumn(StrictBoardModel):
    key: str
    label: str
    tone: BoardTone
    column_kind: Literal["active_stage", "won", "lost", "unset_stage"]
    stage_name: str | None = None
    template_code: str | None = None
    template_sort_order: int | None = None
    procurement_method_id: EntityId | None = None
    procurement_stage_template_id: EntityId | None = None
    count: Count
    amount: AmountString
    items: list[OpportunityBoardItem]
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


class OpportunityCountMetric(BoardMetricBase):
    key: Literal["total_count", "won_count"]
    value_type: Literal["count"]
    value: Count
    secondary_value: Count | None = None


class OpportunityAmountMetric(BoardMetricBase):
    key: Literal["pipeline_amount", "weighted_amount", "won_amount"]
    value_type: Literal["amount"]
    value: AmountString
    secondary_value: AmountString | None = None


OpportunityBoardMetric = Annotated[
    OpportunityCountMetric | OpportunityAmountMetric,
    Field(discriminator="value_type"),
]


class OpportunityBoardTrendPoint(StrictBoardModel):
    date: MonthString
    count: Count
    amount: AmountString


class OpportunityBoardResponse(StrictBoardModel):
    summary: list[OpportunityBoardMetric]
    columns: list[OpportunityBoardColumn]
    trends: list[OpportunityBoardTrendPoint]

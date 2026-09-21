from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.common import PaginatedResponse
from app.schemas.opportunity import OpportunityDetailResponse
from app.services.deal_journey_stage import (
    BoardStageKey,
    BusinessJourneyContractSummary,
    BusinessJourneyInvoiceSummary,
    BusinessJourneyPaymentSummary,
)


class CustomerDealJourneyOpportunitySummary(BaseModel):
    public_id: str
    opportunity_name: str
    status: int
    approval_phase: str
    win_probability: int | None
    expected_closing_date: date | None
    product_name: str | None


class CustomerDealJourneyResponse(BaseModel):
    id: str
    public_id: str
    name: str
    status: str
    current_board_stage: BoardStageKey
    current_board_stage_label: str
    amount: float
    purchase_type: str | None
    started_at: datetime | None
    closed_at: datetime | None
    last_event_at: datetime | None
    primary_opportunity: CustomerDealJourneyOpportunitySummary | None


class BusinessJourneyOwner(BaseModel):
    id: str
    name: str
    avatar_url: str | None = None


class BusinessJourneyListItem(CustomerDealJourneyResponse):
    customer_id: str
    customer_name: str
    owner: BusinessJourneyOwner | None
    primary_opportunity_name: str | None
    product_name: str | None
    created_time: datetime | None
    expected_closing_date: date | None


class BusinessJourneyListResponse(PaginatedResponse[BusinessJourneyListItem]):
    pass


class BusinessJourneyDetailResponse(BaseModel):
    journey: CustomerDealJourneyResponse
    primary_opportunity: OpportunityDetailResponse | None


class BusinessJourneyBoardOpportunitySummary(BaseModel):
    public_id: str
    opportunity_name: str
    amount: float
    actual_amount: float | None = None
    status: int
    current_stage_name: str | None = None
    win_probability: int | None = None
    expected_closing_date: date | None = None


class BusinessJourneyBoardCard(BaseModel):
    public_id: str
    journey_name: str
    customer_id: str
    customer_name: str
    owner: BusinessJourneyOwner | None = None
    status: str
    current_board_stage: BoardStageKey
    started_at: datetime | None = None
    closed_at: datetime | None = None
    last_event_at: datetime | None = None
    last_event_summary: str | None = None
    amount: float
    primary_opportunity: BusinessJourneyBoardOpportunitySummary | None = None
    contract_summary: BusinessJourneyContractSummary
    payment_summary: BusinessJourneyPaymentSummary
    invoice_summary: BusinessJourneyInvoiceSummary


class BusinessJourneyBoardColumn(BaseModel):
    key: BoardStageKey
    title: str
    description: str
    count: int
    amount: float
    cards: list[BusinessJourneyBoardCard]


class BusinessJourneyBoardSummary(BaseModel):
    total_count: int
    total_amount: float
    active_count: int
    completed_count: int
    lost_count: int


class BusinessJourneyBoardResponse(BaseModel):
    columns: list[BusinessJourneyBoardColumn]
    summary: BusinessJourneyBoardSummary
    truncated: bool

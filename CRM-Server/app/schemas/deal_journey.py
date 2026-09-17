from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.services.deal_journey_stage import BoardStageKey


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

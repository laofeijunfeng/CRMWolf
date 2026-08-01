from types import SimpleNamespace

from app.api.business_journey_board import (
    BOARD_COLUMNS,
    BusinessJourneyContractSummary,
    BusinessJourneyInvoiceSummary,
    BusinessJourneyPaymentSummary,
    _infer_active_opportunity_stage,
    _infer_stage,
)
from app.models.deal_journey import DealJourneyStatus


def test_closing_soon_column_is_titled_upcoming_contract():
    columns = {key: title for key, title, _ in BOARD_COLUMNS}

    assert columns["closing_soon"] == "即将签约"
    assert "won_pending_contract" not in columns


def test_won_pending_contract_merges_into_closing_soon_stage():
    stage = _infer_stage(
        SimpleNamespace(status=DealJourneyStatus.WON),
        SimpleNamespace(current_win_probability=100, win_probability=100),
        BusinessJourneyContractSummary(count=0, signed_count=0, amount=0),
        BusinessJourneyPaymentSummary(plan_count=0, record_count=0, planned_amount=0, paid_amount=0, remaining_amount=0),
        BusinessJourneyInvoiceSummary(application_count=0, issued_count=0, applied_amount=0, issued_amount=0),
    )

    assert stage == "closing_soon"


def test_100_percent_opportunity_merges_into_closing_soon_stage():
    stage = _infer_active_opportunity_stage(
        SimpleNamespace(current_win_probability=100, win_probability=100)
    )

    assert stage == "closing_soon"

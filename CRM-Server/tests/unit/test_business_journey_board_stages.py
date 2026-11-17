from types import SimpleNamespace

import pytest

from app.constants.approval_phase import ApprovalPhase

from app.models.deal_journey import DealJourneyStatus
from app.services.deal_journey_stage import (
    BOARD_COLUMNS,
    BusinessJourneyContractSummary,
    BusinessJourneyInvoiceSummary,
    BusinessJourneyPaymentSummary,
    infer_active_opportunity_stage,
    infer_board_stage,
)


def test_closing_soon_column_is_titled_upcoming_contract():
    columns = {key: title for key, title, _ in BOARD_COLUMNS}

    assert columns["closing_soon"] == "即将签约"
    assert "won_pending_contract" not in columns


def test_won_pending_contract_merges_into_closing_soon_stage():
    stage = infer_board_stage(
        SimpleNamespace(status=DealJourneyStatus.WON),
        SimpleNamespace(
            approval_phase=ApprovalPhase.APPROVED,
            current_win_probability=100,
            win_probability=100,
        ),
        BusinessJourneyContractSummary(count=0, signed_count=0, amount=0),
        BusinessJourneyPaymentSummary(plan_count=0, record_count=0, planned_amount=0, paid_amount=0, remaining_amount=0),
        BusinessJourneyInvoiceSummary(application_count=0, issued_count=0, applied_amount=0, issued_amount=0),
    )

    assert stage == "closing_soon"


def test_100_percent_opportunity_merges_into_closing_soon_stage():
    stage = infer_active_opportunity_stage(
        SimpleNamespace(current_win_probability=100, win_probability=100)
    )

    assert stage == "closing_soon"


@pytest.mark.parametrize(
    ("status", "expected_stage"),
    [
        (DealJourneyStatus.ACTIVE, "approval_rejected"),
        (DealJourneyStatus.LOST, "lost"),
        (DealJourneyStatus.COMPLETED, "completed"),
    ],
)
def test_rejected_opportunity_stage_respects_journey_lifecycle(status, expected_stage):
    stage = infer_board_stage(
        SimpleNamespace(status=status),
        SimpleNamespace(
            approval_phase=ApprovalPhase.REJECTED,
            current_win_probability=100,
            win_probability=100,
        ),
        BusinessJourneyContractSummary(count=1, signed_count=1, amount=100),
        BusinessJourneyPaymentSummary(
            plan_count=1, record_count=1, planned_amount=100, paid_amount=50, remaining_amount=50
        ),
        BusinessJourneyInvoiceSummary(
            application_count=1, issued_count=0, applied_amount=100, issued_amount=0
        ),
    )

    assert stage == expected_stage

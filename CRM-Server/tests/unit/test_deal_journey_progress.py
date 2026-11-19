from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from app.constants.approval_phase import ApprovalPhase
from app.models.contract import ContractStatus, PaymentStatus
from app.models.invoice import (
    InvoiceApplicationStatus,
    InvoiceRedOffsetSourceType,
    InvoiceReissueApplicationStatus,
)
from app.services.deal_journey_progress import (
    calculate_cumulative_progress_percent,
    invoice_application_is_currently_valid,
)

if TYPE_CHECKING:
    from datetime import datetime


def _application(*, status: str = InvoiceApplicationStatus.ISSUED) -> SimpleNamespace:
    return SimpleNamespace(status=status)


def _reissue(
    status: str,
    *,
    new_invoice_file_path: str | None = None,
    created_time: datetime | None = None,
    id: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        new_invoice_file_path=new_invoice_file_path,
        created_time=created_time,
        id=id,
    )


def _red_offset(
    source_type: str = InvoiceRedOffsetSourceType.MANUAL,
    *,
    created_time: datetime | None = None,
    id: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(source_type=source_type, created_time=created_time, id=id)


def _opportunity(
    *,
    status: int = 0,
    current_win_probability: int | None = None,
    win_probability: int = 0,
    approval_phase: str = ApprovalPhase.APPROVED.value,
) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        current_win_probability=current_win_probability,
        win_probability=win_probability,
        approval_phase=approval_phase,
    )


def _progress(opportunity: SimpleNamespace | None, *, journey_status: str = "ACTIVE", **facts) -> int:
    return calculate_cumulative_progress_percent(
        journey_status=journey_status,
        primary_opportunity=opportunity,
        contracts=facts.get("contracts", []),
        invoice_applications=facts.get("invoice_applications", []),
        invoice_validity=facts.get("invoice_validity"),
    )


_SIGNED = SimpleNamespace(status=ContractStatus.SIGNED, payment_status=PaymentStatus.UNPAID)
_PAID = SimpleNamespace(status=ContractStatus.EFFECTIVE, payment_status=PaymentStatus.COMPLETED)


@pytest.mark.parametrize(
    ("current_win_probability", "win_probability", "expected"),
    [
        (30, 30, 15),
        (80, 80, 40),
        (99, 99, 49),
        (100, 100, 49),
        (None, 0, 0),
        (None, 60, 30),
    ],
)
def test_deal_half_follows_current_win_rate_before_win_and_caps_at_49(
    current_win_probability: int | None,
    win_probability: int,
    expected: int,
) -> None:
    opportunity = _opportunity(
        current_win_probability=current_win_probability,
        win_probability=win_probability,
    )
    assert _progress(opportunity) == expected


def test_deal_half_drops_with_win_rate_instead_of_keeping_history() -> None:
    opportunity = _opportunity(current_win_probability=60, win_probability=60)
    assert _progress(opportunity) == 30
    opportunity.current_win_probability = 30
    opportunity.win_probability = 30
    assert _progress(opportunity) == 15


def test_without_primary_opportunity_deal_half_is_zero() -> None:
    assert _progress(None) == 0


def test_won_opportunity_fixes_deal_half_and_delivery_milestones_add_up() -> None:
    won = _opportunity(status=1, current_win_probability=30, win_probability=100)
    assert _progress(won) == 50
    assert _progress(won, contracts=[_SIGNED]) == 70
    assert _progress(
        won,
        contracts=[_SIGNED],
        invoice_applications=[_application()],
        invoice_validity=[True],
    ) == 80
    assert _progress(
        won,
        contracts=[_SIGNED],
        invoice_applications=[_application()],
        invoice_validity=[False],
    ) == 70
    assert _progress(
        won,
        contracts=[_PAID],
        invoice_applications=[_application()],
        invoice_validity=[True],
    ) == 100


@pytest.mark.parametrize(
    "opportunity",
    [
        _opportunity(status=2, current_win_probability=80, win_probability=0),
        _opportunity(current_win_probability=80, win_probability=80, approval_phase=ApprovalPhase.REJECTED.value),
        _opportunity(status=1, win_probability=100, approval_phase=ApprovalPhase.REJECTED.value),
    ],
    ids=["lost", "rejected", "rejected-but-won"],
)
def test_lost_or_rejected_opportunity_has_no_deal_half_but_keeps_delivery_facts(
    opportunity: SimpleNamespace,
) -> None:
    assert _progress(opportunity) == 0
    assert _progress(opportunity, contracts=[_SIGNED]) == 20


def test_cumulative_progress_completed_overrides_current_facts() -> None:
    assert _progress(None, journey_status="COMPLETED") == 100


def test_invoice_pending_reissue_invalidates_previous_completed_replacement() -> None:
    application = _application()
    reissues = [
        _reissue(InvoiceReissueApplicationStatus.COMPLETED, new_invoice_file_path="new.pdf", id=1),
        _reissue(InvoiceReissueApplicationStatus.PENDING_REVIEW, id=2),
    ]

    assert invoice_application_is_currently_valid(application, reissues, []) is False


def test_invoice_completed_reissue_is_valid_and_manual_red_offset_without_replacement_is_not() -> None:
    application = _application()
    assert invoice_application_is_currently_valid(
        application,
        [_reissue(InvoiceReissueApplicationStatus.COMPLETED, new_invoice_file_path="new.pdf")],
        [_red_offset(InvoiceRedOffsetSourceType.MANUAL)],
    ) is True
    assert invoice_application_is_currently_valid(
        application,
        [],
        [_red_offset(InvoiceRedOffsetSourceType.MANUAL)],
    ) is False

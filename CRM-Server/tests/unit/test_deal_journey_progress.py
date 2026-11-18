from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

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


def test_cumulative_progress_counts_four_current_milestones_equally() -> None:
    assert calculate_cumulative_progress_percent(
        journey_status="ACTIVE",
        primary_opportunity_won=True,
        contracts=[],
        invoice_applications=[],
    ) == 25

    signed_contract = SimpleNamespace(status=ContractStatus.SIGNED, payment_status=PaymentStatus.UNPAID)
    paid_contract = SimpleNamespace(status=ContractStatus.EFFECTIVE, payment_status=PaymentStatus.COMPLETED)
    assert calculate_cumulative_progress_percent(
        journey_status="ACTIVE",
        primary_opportunity_won=True,
        contracts=[signed_contract, paid_contract],
        invoice_applications=[_application()],
        invoice_validity=[True],
    ) == 75


def test_cumulative_progress_completed_overrides_current_facts() -> None:
    assert calculate_cumulative_progress_percent(
        journey_status="COMPLETED",
        primary_opportunity_won=False,
        contracts=[],
        invoice_applications=[],
    ) == 100


def test_empty_contracts_and_invoices_do_not_satisfy_milestones() -> None:
    assert calculate_cumulative_progress_percent(
        journey_status="ACTIVE",
        primary_opportunity_won=False,
        contracts=[],
        invoice_applications=[],
    ) == 0


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

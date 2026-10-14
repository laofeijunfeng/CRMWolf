"""Canonical payment approval read status, independent of confirmation."""

from __future__ import annotations

import pytest

from app.constants.business_types import BusinessType
from app.models.approval import ApprovalStatus
from app.services.payment_approval_status import (
    LinkedPaymentApproval,
    PaymentApprovalReadStatus,
    resolve_payment_approval_status,
)


RECORD_ID = 41
TEAM_ID = 7
APPROVAL_ID = 900


def _linked(
    *,
    status: str | None,
    approval_id: int | None = APPROVAL_ID,
    team_id: int = TEAM_ID,
    business_type: str = BusinessType.PAYMENT,
    business_id: int = RECORD_ID,
) -> LinkedPaymentApproval:
    return LinkedPaymentApproval(
        id=approval_id if approval_id is not None else APPROVAL_ID,
        team_id=team_id,
        business_type=business_type,
        business_id=business_id,
        status=status,
    )


@pytest.mark.parametrize(
    ("approval_id", "approval_phase", "linked", "expected"),
    [
        (
            APPROVAL_ID,
            "draft",
            _linked(status=ApprovalStatus.PENDING),
            PaymentApprovalReadStatus.PENDING_APPROVAL,
        ),
        (
            APPROVAL_ID,
            "draft",
            _linked(status=ApprovalStatus.REJECTED),
            PaymentApprovalReadStatus.REJECTED,
        ),
        (
            APPROVAL_ID,
            "draft",
            _linked(status=ApprovalStatus.APPROVED),
            PaymentApprovalReadStatus.APPROVED,
        ),
        (None, "pending_review", None, PaymentApprovalReadStatus.PENDING_APPROVAL),
        (None, "rejected", None, PaymentApprovalReadStatus.REJECTED),
        (None, "approved", None, PaymentApprovalReadStatus.APPROVED),
        (None, "draft", None, PaymentApprovalReadStatus.PENDING_SUBMIT),
        (
            APPROVAL_ID,
            "draft",
            _linked(status=ApprovalStatus.CANCELLED),
            PaymentApprovalReadStatus.PENDING_SUBMIT,
        ),
        (None, "withdrawn", None, PaymentApprovalReadStatus.UNCLASSIFIED),
        (None, None, None, PaymentApprovalReadStatus.UNCLASSIFIED),
        (None, "draft", _linked(status=ApprovalStatus.APPROVED), PaymentApprovalReadStatus.PENDING_SUBMIT),
        (
            APPROVAL_ID,
            "draft",
            _linked(status=ApprovalStatus.APPROVED, team_id=TEAM_ID + 1),
            PaymentApprovalReadStatus.PENDING_SUBMIT,
        ),
        (
            APPROVAL_ID,
            "draft",
            _linked(status=ApprovalStatus.APPROVED, business_type=BusinessType.CONTRACT),
            PaymentApprovalReadStatus.PENDING_SUBMIT,
        ),
        (
            APPROVAL_ID,
            "draft",
            _linked(status=ApprovalStatus.APPROVED, business_id=RECORD_ID + 1),
            PaymentApprovalReadStatus.PENDING_SUBMIT,
        ),
        (
            APPROVAL_ID,
            "approved",
            _linked(status=ApprovalStatus.APPROVED, approval_id=APPROVAL_ID + 1),
            PaymentApprovalReadStatus.APPROVED,
        ),
        (None, "draft", None, PaymentApprovalReadStatus.PENDING_SUBMIT),
    ],
    ids=[
        "linked-pending-overrides-native-draft",
        "linked-rejected",
        "linked-approved",
        "native-pending-review",
        "native-rejected",
        "native-approved",
        "native-draft-without-approval",
        "cancelled-approval-falls-back-to-native-draft",
        "unknown-native-phase",
        "missing-approval-evidence",
        "unlinked-approval-evidence",
        "wrong-team-approval",
        "non-payment-business-type",
        "wrong-business-id",
        "wrong-approval-id",
        "confirmed-only",
    ],
)
@pytest.mark.parametrize("confirmed", [False, True])
def test_resolve_payment_approval_status_ignores_confirmation(
    approval_id: int | None,
    approval_phase: str | None,
    linked: LinkedPaymentApproval | None,
    expected: PaymentApprovalReadStatus,
    confirmed: bool,
):
    del confirmed
    assert resolve_payment_approval_status(
        record_id=RECORD_ID,
        team_id=TEAM_ID,
        approval_id=approval_id,
        approval_phase=approval_phase,
        linked_approval=linked,
    ) is expected

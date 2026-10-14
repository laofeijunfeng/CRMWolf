from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import and_, case, exists
from sqlalchemy.sql.elements import ColumnElement

from app.constants.business_types import BusinessType
from app.core.list_query.types import ListQueryContext
from app.models.approval import Approval, ApprovalStatus
from app.models.payment import PaymentRecord


class PaymentApprovalReadStatus(StrEnum):
    PENDING_SUBMIT = "pending_submit"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"
    APPROVED = "approved"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class LinkedPaymentApproval:
    id: int
    team_id: int
    business_type: str
    business_id: int
    status: str | None


def resolve_payment_approval_status(
    *,
    record_id: int,
    team_id: int,
    approval_id: int | None,
    approval_phase: str | None,
    linked_approval: LinkedPaymentApproval | None,
) -> PaymentApprovalReadStatus:
    if (
        linked_approval is not None
        and linked_approval.id == approval_id
        and linked_approval.team_id == team_id
        and linked_approval.business_type == BusinessType.PAYMENT
        and linked_approval.business_id == record_id
    ):
        linked_status = linked_approval.status
        if linked_status == ApprovalStatus.PENDING:
            return PaymentApprovalReadStatus.PENDING_APPROVAL
        if linked_status == ApprovalStatus.REJECTED:
            return PaymentApprovalReadStatus.REJECTED
        if linked_status == ApprovalStatus.APPROVED:
            return PaymentApprovalReadStatus.APPROVED
    phase_by_value: dict[str, PaymentApprovalReadStatus] = {
        "pending_review": PaymentApprovalReadStatus.PENDING_APPROVAL,
        "rejected": PaymentApprovalReadStatus.REJECTED,
        "approved": PaymentApprovalReadStatus.APPROVED,
        "draft": PaymentApprovalReadStatus.PENDING_SUBMIT,
    }
    if approval_phase is None:
        return PaymentApprovalReadStatus.UNCLASSIFIED
    return phase_by_value.get(
        approval_phase,
        PaymentApprovalReadStatus.UNCLASSIFIED,
    )


def payment_approval_status_expression(context: ListQueryContext) -> ColumnElement[str | None]:
    del context

    def linked(status: str) -> ColumnElement[bool]:
        return exists().where(and_(
            Approval.id == PaymentRecord.approval_id,
            Approval.team_id == PaymentRecord.team_id,
            Approval.business_type == BusinessType.PAYMENT,
            Approval.business_id == PaymentRecord.id,
            Approval.status == status,
        )).correlate(PaymentRecord)

    return case(
        (linked(ApprovalStatus.PENDING), "pending_approval"),
        (linked(ApprovalStatus.REJECTED), "rejected"),
        (linked(ApprovalStatus.APPROVED), "approved"),
        (PaymentRecord.approval_phase == "pending_review", "pending_approval"),
        (PaymentRecord.approval_phase == "rejected", "rejected"),
        (PaymentRecord.approval_phase == "approved", "approved"),
        (PaymentRecord.approval_phase == "draft", "pending_submit"),
        else_=None,
    )

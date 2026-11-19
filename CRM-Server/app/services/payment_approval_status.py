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

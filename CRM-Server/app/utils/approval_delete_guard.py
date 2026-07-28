from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.constants.approval_phase import ApprovalPhase
from app.models.approval import ApprovalStatus


LOCKED_APPROVAL_PHASES = {
    ApprovalPhase.PENDING_REVIEW.value,
    ApprovalPhase.APPROVED.value,
}
LOCKED_APPROVAL_STATUSES = {
    ApprovalStatus.PENDING,
    ApprovalStatus.APPROVED,
}


def _normalize(value: object) -> Optional[str]:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def assert_deletable_approval_resource(
    db: Session,
    *,
    resource: object,
    business_type: str,
    business_id: int,
    team_id: Optional[int],
    resource_name: str,
    locked_business_statuses: Iterable[str] = (),
) -> None:
    """Block deletion once an approval is pending or approved."""
    approval_phase = _normalize(getattr(resource, "approval_phase", None))
    if approval_phase in LOCKED_APPROVAL_PHASES:
        raise ValueError(f"{resource_name}审批中或审批通过后不允许删除")

    business_status = _normalize(getattr(resource, "status", None))
    locked_statuses = {_normalize(status) for status in locked_business_statuses}
    if business_status in locked_statuses:
        raise ValueError(f"{resource_name}审批中或审批通过后不允许删除")

    from app.crud.approval import approval_crud

    approval = approval_crud.get_by_entity(db, business_type, business_id, team_id)
    if approval and _normalize(approval.status) in LOCKED_APPROVAL_STATUSES:
        raise ValueError(f"{resource_name}审批中或审批通过后不允许删除")

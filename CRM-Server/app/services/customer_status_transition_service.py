"""Controlled customer lifecycle status transition planning."""

from dataclasses import dataclass

from app.models.outbound_notification_job import OutboundNotificationEventType


class CustomerStatusTransitionError(ValueError):
    """Raised when a customer status is outside the controlled lifecycle contract."""


@dataclass(frozen=True)
class CustomerStatusTransitionDecision:
    previous_status: int
    new_status: int
    notification_event: str | None


class CustomerStatusTransitionService:
    """Plan only the reversible 0/1 customer lifecycle transitions."""

    _LIFECYCLE_STATUSES = frozenset({0, 1})

    def plan(self, *, current_status: int, target_status: int) -> CustomerStatusTransitionDecision:
        if current_status not in self._LIFECYCLE_STATUSES:
            raise CustomerStatusTransitionError("仅跟进中和已成交客户支持快捷状态切换")
        if target_status not in self._LIFECYCLE_STATUSES:
            raise CustomerStatusTransitionError("快捷状态只能设置为跟进中或已成交")
        if current_status == target_status:
            raise CustomerStatusTransitionError("客户已处于目标状态")
        return CustomerStatusTransitionDecision(
            previous_status=current_status,
            new_status=target_status,
            notification_event=(
                OutboundNotificationEventType.ACCOUNT_STATUS_WON if target_status == 1 else None
            ),
        )


customer_status_transition_service = CustomerStatusTransitionService()

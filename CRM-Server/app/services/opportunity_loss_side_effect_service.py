"""Shared post-commit effects for opportunity loss transitions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.crud.customer import customer_crud
from app.models.outbound_notification_job import OutboundNotificationEventType
from app.services.customer_business_object_intelligence_service import (
    customer_business_object_intelligence_service,
)
from app.services.outbound_notification_job_service import outbound_notification_job_service

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.opportunity import Opportunity


def enqueue_opportunity_loss_side_effects(
    db: Session,
    opportunity: Opportunity,
    *,
    actor_id: str,
    loss_reason: str,
) -> None:
    """Enqueue intelligence refresh and owner notification after loss commits."""
    change = customer_business_object_intelligence_service.build_change(
        None,
        source_type="opportunity",
        business_object=opportunity,
        change_type="updated",
        actor_id=actor_id,
    )
    if change is None:
        raise ValueError("商机缺少客户智能刷新所需字段")
    customer_business_object_intelligence_service.enqueue_change_refresh_after_commit(change)

    customer = customer_crud.get_by_id(db, opportunity.customer_id, opportunity.team_id)
    outbound_notification_job_service.queue_committed(
        db,
        team_id=opportunity.team_id,
        event_type=OutboundNotificationEventType.OPPORTUNITY_LOST,
        business_type="OPPORTUNITY",
        business_id=int(opportunity.id),
        recipient_user_ids=[opportunity.owner_id],
        actor_id=actor_id,
        payload_json={
            "opportunity_name": opportunity.opportunity_name,
            "customer_name": customer.account_name if customer else "",
            "loss_reason": loss_reason,
        },
    )

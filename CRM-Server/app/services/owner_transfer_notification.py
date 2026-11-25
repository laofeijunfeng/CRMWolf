"""Feishu notifications for owner changes: lead assignment and customer transfer (CRM-162).

Runs after the business transaction committed. Reads only; card content is snapshotted into
the outbox payload so delivery retries render what the operator saw at transfer time.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from app.crud.customer import contact_crud
from app.crud.customer_activity import customer_activity_crud
from app.crud.lead import lead_follow_up_crud
from app.crud.team import team_crud
from app.crud.user import user_crud
from app.models.outbound_notification_job import OutboundNotificationEventType
from app.services.customer_activity_kinds import get_activity_kind_meta
from app.services.outbound_notification_job_service import outbound_notification_job_service

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

    from app.models.customer import Customer
    from app.models.lead import Lead

logger = logging.getLogger(__name__)

FOLLOW_UP_CONTENT_LIMIT = 100
_CASCADE_SCOPES = frozenset({"following", "all"})


def queue_customer_transfer_notifications(
    db: Session,
    *,
    team_id: int,
    customer: Customer,
    previous_owner_id: str | None,
    new_owner_id: str,
    transfer_scope: str,
    transferred_opportunities: int,
    transferred_contracts: int,
    locked_contracts: int,
    remark: str | None,
    operator_id: int,
    operator_name: str | None,
    idempotency_key: str | None = None,
) -> None:
    try:
        new_owner, previous_owner = _recipients(
            db, team_id=team_id, new_owner_id=new_owner_id, previous_owner_id=previous_owner_id, operator_id=operator_id
        )
        if new_owner is None and previous_owner is None:
            return
        cascade = (
            {"opportunities": transferred_opportunities, "contracts": transferred_contracts, "locked": locked_contracts}
            if transfer_scope in _CASCADE_SCOPES
            else None
        )
        common = {"name": customer.account_name, "operator_name": operator_name, "cascade": cascade}
        business_id = int(customer.id)
        if new_owner is not None:
            contact = contact_crud.get_card_contact(db, customer_id=business_id, team_id=team_id)
            activity = customer_activity_crud.get_latest_by_customer_id(db, customer_id=business_id, team_id=team_id)
            follow_up = None
            if activity is not None:
                meta = get_activity_kind_meta(cast("str", activity.activity_kind))
                follow_up = _follow_up(
                    kind_label="会议纪要" if meta["category"] == "MEETING" else "跟进记录",
                    occurred_at=cast("datetime | None", activity.occurred_at),
                    method=meta["label"],
                    content=cast("str | None", activity.summary or activity.source_content),
                )
            outbound_notification_job_service.queue_committed(
                db,
                team_id=team_id,
                event_type=OutboundNotificationEventType.CUSTOMER_TRANSFERRED,
                business_type="CUSTOMER",
                business_id=business_id,
                recipient_user_ids=[new_owner],
                actor_id=str(operator_id),
                payload_json={
                    **common,
                    "previous_owner_name": _user_name(db, previous_owner_id),
                    "contact_name": contact.name if contact else None,
                    "contact_phone": contact.mobile if contact else None,
                    "follow_up": follow_up,
                    "remark": remark or None,
                    "detail_path": f"/customers?customerId={customer.public_id}",
                },
                idempotency_key=idempotency_key,
            )
        if previous_owner is not None:
            outbound_notification_job_service.queue_committed(
                db,
                team_id=team_id,
                event_type=OutboundNotificationEventType.CUSTOMER_TRANSFERRED_PREVIOUS,
                business_type="CUSTOMER",
                business_id=business_id,
                recipient_user_ids=[previous_owner],
                actor_id=str(operator_id),
                payload_json={**common, "new_owner_name": _user_name(db, new_owner_id)},
                idempotency_key=f"{idempotency_key}:previous" if idempotency_key else None,
            )
    except Exception:
        logger.exception("客户移交飞书通知入队失败: team=%s customer=%s", team_id, getattr(customer, "id", None))
        db.rollback()


def queue_lead_assignment_notifications(
    db: Session,
    *,
    team_id: int,
    lead: Lead,
    previous_owner_id: str | None,
    new_owner_id: str,
    operator_id: int,
    operator_name: str | None,
) -> None:
    try:
        new_owner, previous_owner = _recipients(
            db, team_id=team_id, new_owner_id=new_owner_id, previous_owner_id=previous_owner_id, operator_id=operator_id
        )
        business_id = int(lead.id)
        common = {"name": lead.lead_name, "operator_name": operator_name}
        if new_owner is not None:
            latest = lead_follow_up_crud.get_latest_for_team(db, lead_id=business_id, team_id=team_id)
            follow_up = None
            if latest is not None:
                method = latest.method
                follow_up = _follow_up(
                    kind_label="跟进记录",
                    occurred_at=cast("datetime | None", latest.created_time),
                    method=cast("str | None", getattr(method, "value", method)),
                    content=cast("str | None", latest.content),
                )
            outbound_notification_job_service.queue_committed(
                db,
                team_id=team_id,
                event_type=OutboundNotificationEventType.LEAD_ASSIGNED,
                business_type="LEAD",
                business_id=business_id,
                recipient_user_ids=[new_owner],
                actor_id=str(operator_id),
                payload_json={
                    **common,
                    "previous_owner_name": _user_name(db, previous_owner_id),
                    "contact_name": lead.contact_name,
                    "contact_phone": lead.contact_phone,
                    "follow_up": follow_up,
                    "detail_path": "/leads",
                },
            )
        if previous_owner is not None:
            outbound_notification_job_service.queue_committed(
                db,
                team_id=team_id,
                event_type=OutboundNotificationEventType.LEAD_ASSIGNED_PREVIOUS,
                business_type="LEAD",
                business_id=business_id,
                recipient_user_ids=[previous_owner],
                actor_id=str(operator_id),
                payload_json={**common, "new_owner_name": _user_name(db, new_owner_id)},
            )
    except Exception:
        logger.exception("线索分配飞书通知入队失败: team=%s lead=%s", team_id, getattr(lead, "id", None))
        db.rollback()


def _recipients(
    db: Session,
    *,
    team_id: int,
    new_owner_id: str | None,
    previous_owner_id: str | None,
    operator_id: int,
) -> tuple[int | None, int | None]:
    """(new owner, previous owner) user ids to notify: current team members, never the operator."""

    new_owner = _user_id(new_owner_id)
    previous_owner = _user_id(previous_owner_id)
    if previous_owner == new_owner:
        previous_owner = None

    def eligible(user_id: int | None) -> int | None:
        if user_id is None or user_id == operator_id or not team_crud.is_member(db, team_id, user_id):
            return None
        return user_id

    return eligible(new_owner), eligible(previous_owner)


def _user_id(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _user_name(db: Session, value: str | None) -> str | None:
    user_id = _user_id(value)
    user = user_crud.get_by_id(db, user_id) if user_id is not None else None
    return user.name if user else None


def _follow_up(
    *, kind_label: str, occurred_at: datetime | None, method: str | None, content: str | None
) -> dict[str, str | None]:
    text = (content or "").strip()
    if len(text) > FOLLOW_UP_CONTENT_LIMIT:
        text = f"{text[:FOLLOW_UP_CONTENT_LIMIT]}…"
    return {
        "kind_label": kind_label,
        "occurred_at": occurred_at.strftime("%Y-%m-%d %H:%M") if occurred_at else None,
        "method": method or None,
        "content": text or None,
    }

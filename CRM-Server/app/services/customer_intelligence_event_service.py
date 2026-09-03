"""Typed customer intelligence event boundary.

Business modules emit different objects: customer activities, profile projections, and deal journey events. The customer intelligence
graph should not depend on those ORM shapes directly, so this service normalizes
them into one event contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import TYPE_CHECKING, Literal, cast

if TYPE_CHECKING:
    from app.models.customer import Contact
    from app.models.customer_activity import CustomerActivity
    from app.models.deal_journey import CustomerDealJourneyEvent
    from app.models.sales_commitment import FollowUpTask, FollowUpTaskEvent

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]

CustomerIntelligenceBusinessObjectChangeType = Literal["created", "updated", "deleted"]
CustomerIntelligenceBusinessObjectTriggerType = Literal[
    "customer_business_object_created",
    "customer_business_object_updated",
    "customer_business_object_deleted",
    "customer_contact_created",
    "customer_contact_updated",
    "customer_contact_deleted",
]


def customer_business_object_trigger_for_change(
    change_type: CustomerIntelligenceBusinessObjectChangeType,
    *,
    source_type: str | None = None,
) -> CustomerIntelligenceBusinessObjectTriggerType:
    """Resolve a business-object mutation to its canonical intelligence trigger.

    Keeping this mapping beside the event contract prevents the event builder
    and refresh scheduler from silently drifting into different semantics.
    """

    if source_type == "customer_contact":
        contact_trigger_by_change: dict[
            CustomerIntelligenceBusinessObjectChangeType,
            CustomerIntelligenceBusinessObjectTriggerType,
        ] = {
            "created": "customer_contact_created",
            "updated": "customer_contact_updated",
            "deleted": "customer_contact_deleted",
        }
        return contact_trigger_by_change[change_type]

    trigger_by_change: dict[
        CustomerIntelligenceBusinessObjectChangeType,
        CustomerIntelligenceBusinessObjectTriggerType,
    ] = {
        "created": "customer_business_object_created",
        "updated": "customer_business_object_updated",
        "deleted": "customer_business_object_deleted",
    }
    return trigger_by_change[change_type]


CustomerIntelligenceTriggerType = Literal[
    "customer_created",
    "customer_converted_from_lead",
    "customer_activity_created",
    "customer_activity_updated",
    "customer_activity_deleted",
    "customer_contact_created",
    "customer_contact_updated",
    "customer_contact_deleted",
    "customer_business_object_created",
    "customer_business_object_updated",
    "customer_business_object_deleted",
    "deal_journey_event_recorded",
    "follow_up_task_created",
    "follow_up_task_updated",
    "follow_up_task_completed",
    "follow_up_task_cancelled",
    "follow_up_task_postponed",
    "follow_up_task_reopened",
    "deal_journey_association_changed",
    "sales_commitment_created",
    "sales_commitment_updated",
    "sales_commitment_fulfilled",
    "sales_commitment_cancelled",
    "sales_commitment_superseded",
    "manual_refresh_requested",
    "customer_intelligence_batch_rebuild_requested",
    "customer_intelligence_historical_backfill_requested",
    "customer_intelligence_reconciliation_requested",
    "agent_customer_question",
]

CUSTOMER_INTELLIGENCE_INLINE_TRIGGER_TYPES = frozenset({"agent_customer_question"})
CUSTOMER_INTELLIGENCE_COMMITTED_EVENT_TRIGGER_TYPES = frozenset({
    "customer_activity_created",
    "customer_activity_updated",
    "customer_activity_deleted",
    "customer_contact_created",
    "customer_contact_updated",
    "customer_contact_deleted",
    "customer_business_object_created",
    "customer_business_object_updated",
    "customer_business_object_deleted",
    "deal_journey_event_recorded",
    "follow_up_task_created",
    "follow_up_task_updated",
    "follow_up_task_completed",
    "follow_up_task_cancelled",
    "follow_up_task_postponed",
    "follow_up_task_reopened",
    "deal_journey_association_changed",
    "sales_commitment_created",
    "sales_commitment_updated",
    "sales_commitment_fulfilled",
    "sales_commitment_cancelled",
    "sales_commitment_superseded",
})


@dataclass(frozen=True)
class CustomerIntelligenceSource:
    source_type: str
    source_object_id: str
    source_version: int | str | None = None
    business_object_type: str | None = None
    business_object_id: str | None = None

    def to_dict(self) -> JsonObject:
        return {
            "source_type": self.source_type,
            "source_object_id": self.source_object_id,
            "source_version": self.source_version,
            "business_object_type": self.business_object_type,
            "business_object_id": self.business_object_id,
        }


@dataclass(frozen=True)
class CustomerIntelligenceEvent:
    event_key: str
    trigger_type: CustomerIntelligenceTriggerType
    tenant_id: int
    team_id: int
    customer_id: int
    deal_journey_id: int | None = None
    occurred_at: datetime | None = None
    source: CustomerIntelligenceSource = field(default_factory=lambda: CustomerIntelligenceSource("unknown", "unknown"))
    summary: str | None = None
    payload: JsonObject = field(default_factory=dict)
    actor_id: str | None = None

    def thread_id(self) -> str:
        return f"customer_intelligence:{self.team_id}:{self.event_key}"

    def to_dict(self) -> JsonObject:
        return {
            "event_key": self.event_key,
            "trigger_type": self.trigger_type,
            "tenant_id": self.tenant_id,
            "team_id": self.team_id,
            "customer_id": self.customer_id,
            "deal_journey_id": self.deal_journey_id,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
            "source": self.source.to_dict(),
            "summary": self.summary,
            "payload": self.payload,
            "actor_id": self.actor_id,
            "thread_id": self.thread_id(),
        }


class CustomerIntelligenceEventService:
    def from_dict(self, payload: JsonObject) -> CustomerIntelligenceEvent | None:
        """Restore the durable event contract from its persisted JSON snapshot."""

        source_payload = payload.get("source")
        if not isinstance(source_payload, dict):
            return None
        event_key = payload.get("event_key")
        trigger_type = payload.get("trigger_type")
        tenant_id = _positive_int(payload.get("tenant_id"))
        team_id = _positive_int(payload.get("team_id"))
        customer_id = _positive_int(payload.get("customer_id"))
        deal_journey_id = _positive_int(payload.get("deal_journey_id"))
        if not isinstance(event_key, str) or not event_key.strip():
            return None
        if not isinstance(trigger_type, str) or trigger_type not in _CUSTOMER_INTELLIGENCE_TRIGGER_TYPES:
            return None
        if tenant_id is None or team_id is None or customer_id is None or tenant_id != team_id:
            return None
        source_type = _required_string(source_payload.get("source_type"))
        source_object_id = _required_string(source_payload.get("source_object_id"))
        if source_type is None or source_object_id is None:
            return None
        occurred_at = _datetime_from_iso(payload.get("occurred_at"))
        event_payload = payload.get("payload")
        return CustomerIntelligenceEvent(
            event_key=event_key,
            trigger_type=cast("CustomerIntelligenceTriggerType", trigger_type),
            tenant_id=tenant_id,
            team_id=team_id,
            customer_id=customer_id,
            deal_journey_id=deal_journey_id,
            occurred_at=occurred_at,
            source=CustomerIntelligenceSource(
                source_type=source_type,
                source_object_id=source_object_id,
                source_version=_source_version(source_payload.get("source_version")),
                business_object_type=_optional_string(source_payload.get("business_object_type")),
                business_object_id=_optional_string(source_payload.get("business_object_id")),
            ),
            summary=_optional_string(payload.get("summary")),
            payload=event_payload if isinstance(event_payload, dict) else {},
            actor_id=_optional_string(payload.get("actor_id")),
        )

    def from_customer_activity(
        self,
        activity: CustomerActivity,
        *,
        trigger_type: Literal[
            "customer_activity_created",
            "customer_activity_updated",
            "customer_activity_deleted",
        ] = "customer_activity_created",
    ) -> CustomerIntelligenceEvent | None:
        if activity.customer_id is None:
            return None
        source_object_id = str(activity.id)
        activity_revision = int(getattr(activity, "activity_revision", None) or 1)
        event_identity = f"{source_object_id}:revision:{activity_revision}"
        return CustomerIntelligenceEvent(
            event_key=self._event_key(
                team_id=int(activity.team_id),
                trigger_type=trigger_type,
                source_type="customer_activity",
                source_object_id=event_identity,
            ),
            trigger_type=trigger_type,
            tenant_id=int(activity.team_id),
            team_id=int(activity.team_id),
            customer_id=int(activity.customer_id),
            deal_journey_id=getattr(activity, "deal_journey_id", None),
            occurred_at=activity.occurred_at,
            source=CustomerIntelligenceSource(
                source_type="customer_activity",
                source_object_id=source_object_id,
                source_version=activity_revision,
                business_object_type="customer_activity",
                business_object_id=source_object_id,
            ),
            summary=activity.summary or activity.source_content,
            payload=self._customer_activity_payload(
                activity,
                trigger_type=trigger_type,
                activity_revision=activity_revision,
            ),
            actor_id=activity.creator_id,
        )

    def _customer_activity_payload(
        self,
        activity: CustomerActivity,
        *,
        trigger_type: Literal[
            "customer_activity_created",
            "customer_activity_updated",
            "customer_activity_deleted",
        ],
        activity_revision: int,
    ) -> JsonObject:
        payload: JsonObject = {
            "activity_revision": activity_revision,
            "activity_kind": activity.activity_kind,
            "title": activity.title,
            "next_action": activity.next_action,
            "next_action_source": getattr(activity, "next_action_source", None),
            "next_follow_time": activity.next_follow_time.isoformat() if activity.next_follow_time else None,
            "next_follow_time_source": getattr(activity, "next_follow_time_source", None),
        }
        if trigger_type == "customer_activity_deleted":
            # The source row is removed immediately after this event is
            # registered. Keep the pre-delete facts available to the negative
            # projection even when the worker can no longer query the source.
            payload["deleted_snapshot"] = {
                "activity_kind": activity.activity_kind,
                "title": activity.title,
                "source_content": activity.source_content,
                "content_json": self._parse_json_object(activity.content_json),
                "summary": activity.summary,
                "next_action": activity.next_action,
                "next_action_source": getattr(activity, "next_action_source", None),
                "next_follow_time": activity.next_follow_time.isoformat() if activity.next_follow_time else None,
                "next_follow_time_source": getattr(activity, "next_follow_time_source", None),
                "occurred_at": activity.occurred_at.isoformat() if activity.occurred_at else None,
            }
        return payload

    def from_contact(
        self,
        contact: Contact,
        *,
        trigger_type: Literal[
            "customer_contact_created",
            "customer_contact_updated",
            "customer_contact_deleted",
        ] = "customer_contact_created",
        actor_id: str | None = None,
    ) -> CustomerIntelligenceEvent | None:
        if contact.customer_id is None:
            return None
        source_object_id = str(contact.id)
        contact_revision = int(getattr(contact, "post_commit_revision", None) or 1)
        event_source_object_id = f"{source_object_id}:revision:{contact_revision}"
        summary_by_trigger = {
            "customer_contact_created": "客户联系人已新增",
            "customer_contact_updated": "客户联系人已更新",
            "customer_contact_deleted": "客户联系人已删除",
        }
        return CustomerIntelligenceEvent(
            event_key=self._event_key(
                team_id=int(contact.team_id),
                trigger_type=trigger_type,
                source_type="customer_contact",
                source_object_id=event_source_object_id,
            ),
            trigger_type=trigger_type,
            tenant_id=int(contact.team_id),
            team_id=int(contact.team_id),
            customer_id=int(contact.customer_id),
            occurred_at=getattr(contact, "updated_time", None) or contact.created_time,
            source=CustomerIntelligenceSource(
                source_type="customer_contact",
                source_object_id=source_object_id,
                source_version=contact_revision,
                business_object_type="contact",
                business_object_id=source_object_id,
            ),
            summary=f"{summary_by_trigger[trigger_type]}: {contact.name}",
            payload={
                "name": contact.name,
                "gender": contact.gender,
                "position": contact.position,
                "is_decision_maker": bool(contact.is_decision_maker),
                "is_primary": bool(contact.is_primary),
                "reports_to": contact.reports_to,
                "remark": contact.remark,
            },
            actor_id=actor_id,
        )

    def from_deal_journey_event(self, event: CustomerDealJourneyEvent) -> CustomerIntelligenceEvent | None:
        if event.id is None:
            return None
        source_object_id = str(event.id)
        trigger_type = (
            "deal_journey_association_changed"
            if event.event_type == "association_changed"
            else "deal_journey_event_recorded"
        )
        return CustomerIntelligenceEvent(
            event_key=self._event_key(
                team_id=int(event.team_id),
                trigger_type=trigger_type,
                source_type="deal_journey_event",
                source_object_id=source_object_id,
            ),
            trigger_type=trigger_type,
            tenant_id=int(event.team_id),
            team_id=int(event.team_id),
            customer_id=int(event.customer_id),
            deal_journey_id=int(event.deal_journey_id),
            occurred_at=event.event_time,
            source=CustomerIntelligenceSource(
                source_type="deal_journey_event",
                source_object_id=source_object_id,
                source_version=int(event.id),
                business_object_type=event.source_type,
                business_object_id=str(event.source_id) if event.source_id is not None else None,
            ),
            summary=event.summary,
            payload={
                "event_type": event.event_type,
                "source_type": event.source_type,
                "source_id": event.source_id,
                "metadata": self._parse_json_object(event.metadata_json),
            },
            actor_id=event.actor_id,
        )

    def from_follow_up_task_event(
        self,
        task: FollowUpTask,
        event: FollowUpTaskEvent,
    ) -> CustomerIntelligenceEvent | None:
        """Turn a task status history row into a profile refresh event.

        A task transition is evidence of sales-side fulfilment only.  Keeping
        this event separate from customer activities prevents a completed task
        from being rendered as customer feedback or a new customer touch.
        """

        event_type = _follow_up_task_trigger_type(event.event_type)
        if event.id is None or event_type is None:
            return None
        source_object_id = str(event.id)
        return CustomerIntelligenceEvent(
            event_key=self._event_key(
                team_id=int(task.team_id),
                trigger_type=event_type,
                source_type="follow_up_task_event",
                source_object_id=source_object_id,
            ),
            trigger_type=event_type,
            tenant_id=int(task.team_id),
            team_id=int(task.team_id),
            customer_id=int(task.customer_id),
            deal_journey_id=getattr(task, "deal_journey_id", None),
            occurred_at=event.created_time,
            source=CustomerIntelligenceSource(
                source_type="follow_up_task_event",
                source_object_id=source_object_id,
                source_version=int(event.id),
                business_object_type="follow_up_task",
                business_object_id=str(task.id),
            ),
            summary=f"跟进任务状态变更: {event.new_status or event.event_type}",
            payload={
                "task_id": int(task.id),
                "task_public_id": task.public_id,
                "deal_journey_id": task.deal_journey_id,
                "event_type": event.event_type,
                "previous_status": event.previous_status,
                "new_status": event.new_status,
                "source_activity_id": event.source_activity_id,
                "payload": event.payload_json if isinstance(event.payload_json, dict) else {},
            },
            actor_id=event.actor_id,
        )

    def manual_refresh_requested(
        self,
        *,
        team_id: int,
        customer_id: int,
        actor_id: str | None,
        request_id: str,
        refresh_scope: str,
        occurred_at: datetime | None = None,
    ) -> CustomerIntelligenceEvent:
        return CustomerIntelligenceEvent(
            event_key=self._event_key(
                team_id=team_id,
                trigger_type="manual_refresh_requested",
                source_type="manual_refresh",
                source_object_id=request_id,
            ),
            trigger_type="manual_refresh_requested",
            tenant_id=team_id,
            team_id=team_id,
            customer_id=customer_id,
            occurred_at=occurred_at,
            source=CustomerIntelligenceSource(
                source_type="manual_refresh",
                source_object_id=request_id,
                business_object_type="customer",
                business_object_id=str(customer_id),
            ),
            summary="用户手动刷新客户智能档案",
            payload={"refresh_scope": refresh_scope},
            actor_id=actor_id,
        )

    def batch_rebuild_requested(
        self,
        *,
        team_id: int,
        customer_id: int,
        actor_id: str | None,
        request_id: str,
        refresh_scope: str,
        occurred_at: datetime | None = None,
    ) -> CustomerIntelligenceEvent:
        return CustomerIntelligenceEvent(
            event_key=self._event_key(
                team_id=team_id,
                trigger_type="customer_intelligence_batch_rebuild_requested",
                source_type="batch_rebuild",
                source_object_id=f"{customer_id}:{request_id}",
            ),
            trigger_type="customer_intelligence_batch_rebuild_requested",
            tenant_id=team_id,
            team_id=team_id,
            customer_id=customer_id,
            occurred_at=occurred_at,
            source=CustomerIntelligenceSource(
                source_type="batch_rebuild",
                source_object_id=request_id,
                business_object_type="customer",
                business_object_id=str(customer_id),
            ),
            summary="批量重建客户智能档案",
            payload={
                "refresh_scope": refresh_scope,
                "request_id": request_id,
            },
            actor_id=actor_id,
        )

    def historical_backfill_requested(
        self,
        *,
        team_id: int,
        customer_id: int,
        request_id: str,
        refresh_scope: str,
        occurred_at: datetime | None = None,
    ) -> CustomerIntelligenceEvent:
        return CustomerIntelligenceEvent(
            event_key=self._event_key(
                team_id=team_id,
                trigger_type="customer_intelligence_historical_backfill_requested",
                source_type="historical_backfill",
                source_object_id=f"{customer_id}:{request_id}",
            ),
            trigger_type="customer_intelligence_historical_backfill_requested",
            tenant_id=team_id,
            team_id=team_id,
            customer_id=customer_id,
            occurred_at=occurred_at,
            source=CustomerIntelligenceSource(
                source_type="historical_backfill",
                source_object_id=request_id,
                business_object_type="customer",
                business_object_id=str(customer_id),
            ),
            summary="系统自动补齐历史客户智能档案",
            payload={
                "refresh_scope": refresh_scope,
                "request_id": request_id,
                "maintenance_job": "missing_customer_intelligence_backfill",
            },
            actor_id=None,
        )

    def reconciliation_requested(
        self,
        *,
        team_id: int,
        customer_id: int,
        source_version: str,
        payload: JsonObject | None = None,
        occurred_at: datetime | None = None,
    ) -> CustomerIntelligenceEvent:
        """Create a stable event for a watermark reconciliation finding.

        The source version is a hash of the currently observed business
        watermark.  Re-running the scanner therefore produces the same event
        and durable run until the underlying business snapshot changes.
        """

        source_type = "customer_profile_reconciliation"
        source_object_id = str(customer_id)
        return CustomerIntelligenceEvent(
            event_key=self._event_key(
                team_id=team_id,
                trigger_type="customer_intelligence_reconciliation_requested",
                source_type=source_type,
                source_object_id=f"{source_object_id}:version:{source_version}",
            ),
            trigger_type="customer_intelligence_reconciliation_requested",
            tenant_id=team_id,
            team_id=team_id,
            customer_id=customer_id,
            occurred_at=occurred_at,
            source=CustomerIntelligenceSource(
                source_type=source_type,
                source_object_id=source_object_id,
                source_version=source_version,
                business_object_type="customer",
                business_object_id=source_object_id,
            ),
            summary="对账发现客户档案存在未纳入的业务变化",
            payload=payload or {},
            actor_id=None,
        )

    def customer_lifecycle_refresh_requested(
        self,
        *,
        team_id: int,
        customer_id: int,
        actor_id: str | None,
        request_id: str,
        trigger_type: Literal["customer_created", "customer_converted_from_lead"],
        source_lead_id: int | None = None,
        occurred_at: datetime | None = None,
    ) -> CustomerIntelligenceEvent:
        source_type = "lead_conversion" if trigger_type == "customer_converted_from_lead" else "customer"
        source_object_id = str(source_lead_id) if source_lead_id is not None else str(customer_id)
        return CustomerIntelligenceEvent(
            event_key=self._event_key(
                team_id=team_id,
                trigger_type=trigger_type,
                source_type=source_type,
                source_object_id=f"{source_object_id}:{request_id}",
            ),
            trigger_type=trigger_type,
            tenant_id=team_id,
            team_id=team_id,
            customer_id=customer_id,
            occurred_at=occurred_at,
            source=CustomerIntelligenceSource(
                source_type=source_type,
                source_object_id=source_object_id,
                business_object_type="customer",
                business_object_id=str(customer_id),
            ),
            summary="客户已创建，刷新客户智能档案",  # noqa: RUF001
            payload={
                "refresh_scope": "full",
                "source_lead_id": source_lead_id,
                "request_id": request_id,
            },
            actor_id=actor_id,
        )

    def agent_customer_question(
        self,
        *,
        team_id: int,
        customer_id: int,
        actor_id: str | None,
        session_id: int | str,
        message_id: int | str,
        question: str,
        occurred_at: datetime | None = None,
    ) -> CustomerIntelligenceEvent:
        source_object_id = f"{session_id}:{message_id}"
        return CustomerIntelligenceEvent(
            event_key=self._event_key(
                team_id=team_id,
                trigger_type="agent_customer_question",
                source_type="agent_message",
                source_object_id=source_object_id,
            ),
            trigger_type="agent_customer_question",
            tenant_id=team_id,
            team_id=team_id,
            customer_id=customer_id,
            occurred_at=occurred_at,
            source=CustomerIntelligenceSource(
                source_type="agent_message",
                source_object_id=source_object_id,
                business_object_type="customer",
                business_object_id=str(customer_id),
            ),
            summary=question[:500],
            payload={"question": question},
            actor_id=actor_id,
        )

    def business_object_changed(
        self,
        *,
        team_id: int,
        customer_id: int,
        actor_id: str | None,
        trigger_type: Literal[
            "customer_business_object_created",
            "customer_business_object_updated",
            "customer_business_object_deleted",
        ],
        source_type: str,
        source_id: int,
        change_id: str,
        summary: str,
        source_version: int | str | None = None,
        payload: JsonObject | None = None,
        occurred_at: datetime | None = None,
    ) -> CustomerIntelligenceEvent:
        source_object_id = str(source_id)
        # ``change_id`` identifies the transport attempt when the source does
        # not expose a business revision. A source version is the business
        # identity and therefore determines idempotency when available.
        source_identity = str(source_version) if source_version is not None else change_id
        return CustomerIntelligenceEvent(
            event_key=self._event_key(
                team_id=team_id,
                trigger_type=trigger_type,
                source_type=source_type,
                source_object_id=f"{source_object_id}:version:{source_identity}",
            ),
            trigger_type=trigger_type,
            tenant_id=team_id,
            team_id=team_id,
            customer_id=customer_id,
            occurred_at=occurred_at,
            source=CustomerIntelligenceSource(
                source_type=source_type,
                source_object_id=source_object_id,
                source_version=source_version if source_version is not None else change_id,
                business_object_type=source_type,
                business_object_id=source_object_id,
            ),
            summary=summary,
            payload=payload or {},
            actor_id=actor_id,
        )

    def sales_commitment_changed(
        self,
        *,
        team_id: int,
        customer_id: int,
        actor_id: str | None,
        trigger_type: Literal[
            "sales_commitment_created",
            "sales_commitment_updated",
            "sales_commitment_fulfilled",
            "sales_commitment_cancelled",
            "sales_commitment_superseded",
        ],
        commitment_id: int,
        change_id: str,
        deal_journey_id: int | None,
        summary: str,
        payload: JsonObject | None = None,
        occurred_at: datetime | None = None,
    ) -> CustomerIntelligenceEvent:
        """Build a durable event for a commitment lifecycle transition.

        Commitments are read-model inputs, not customer outcomes.  The payload
        therefore carries the previous/current sales-side state and never
        implies that the customer accepted or completed the promised work.
        ``change_id`` is supplied by the lifecycle owner and should be a
        monotonic source revision, so A → B → A remains three distinct
        transitions while a retry of one transition stays idempotent.
        """
        source_object_id = str(commitment_id)
        return CustomerIntelligenceEvent(
            event_key=self._event_key(
                team_id=team_id,
                trigger_type=trigger_type,
                source_type="sales_commitment",
                source_object_id=f"{source_object_id}:{change_id}",
            ),
            trigger_type=trigger_type,
            tenant_id=team_id,
            team_id=team_id,
            customer_id=customer_id,
            deal_journey_id=deal_journey_id,
            occurred_at=occurred_at,
            source=CustomerIntelligenceSource(
                source_type="sales_commitment",
                source_object_id=source_object_id,
                source_version=change_id,
                business_object_type="sales_commitment",
                business_object_id=source_object_id,
            ),
            summary=summary,
            payload=payload or {},
            actor_id=actor_id,
        )

    def _event_key(self, *, team_id: int, trigger_type: str, source_type: str, source_object_id: str) -> str:
        raw_key = f"crmwolf/customer-intelligence/{team_id}/{trigger_type}/{source_type}/{source_object_id}"
        return sha256(raw_key.encode("utf-8")).hexdigest()

    def _parse_json_object(self, raw: str | None) -> JsonObject:
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}



_CUSTOMER_INTELLIGENCE_TRIGGER_TYPES = frozenset({
    "customer_created",
    "customer_converted_from_lead",
    "customer_activity_created",
    "customer_activity_updated",
    "customer_activity_deleted",
    "customer_contact_created",
    "customer_contact_updated",
    "customer_contact_deleted",
    "customer_business_object_created",
    "customer_business_object_updated",
    "customer_business_object_deleted",
    "deal_journey_event_recorded",
    "follow_up_task_created",
    "follow_up_task_updated",
    "follow_up_task_completed",
    "follow_up_task_cancelled",
    "follow_up_task_postponed",
    "follow_up_task_reopened",
    "deal_journey_association_changed",
    "sales_commitment_created",
    "sales_commitment_updated",
    "sales_commitment_fulfilled",
    "sales_commitment_cancelled",
    "sales_commitment_superseded",
    "manual_refresh_requested",
    "customer_intelligence_batch_rebuild_requested",
    "customer_intelligence_historical_backfill_requested",
    "customer_intelligence_reconciliation_requested",
    "agent_customer_question",
})


def _follow_up_task_trigger_type(event_type: object) -> str | None:
    return {
        "CREATED": "follow_up_task_created",
        "UPDATED": "follow_up_task_updated",
        "COMPLETED": "follow_up_task_completed",
        "CANCELLED": "follow_up_task_cancelled",
        "REOPENED": "follow_up_task_reopened",
        "POSTPONED": "follow_up_task_postponed",
    }.get(str(event_type))


def _source_version(value: object) -> int | str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _required_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _datetime_from_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


customer_intelligence_event_service = CustomerIntelligenceEventService()

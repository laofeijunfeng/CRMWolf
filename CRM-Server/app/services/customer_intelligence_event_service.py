"""Typed customer intelligence event boundary.

Business modules emit different objects: customer activities, generated
profiles, generated briefs, and deal journey events. The customer intelligence
graph should not depend on those ORM shapes directly, so this service normalizes
them into one event contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Literal

from app.models.customer import Contact, Customer
from app.models.customer_activity import CustomerActivity
from app.models.deal_journey import CustomerDealJourneyEvent

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]

CustomerIntelligenceTriggerType = Literal[
    "customer_created",
    "customer_converted_from_lead",
    "customer_activity_created",
    "customer_activity_updated",
    "customer_activity_deleted",
    "customer_contact_created",
    "customer_contact_updated",
    "customer_contact_deleted",
    "customer_profile_generated",
    "customer_brief_generated",
    "customer_business_object_created",
    "customer_business_object_updated",
    "customer_business_object_deleted",
    "deal_journey_event_recorded",
    "manual_refresh_requested",
    "customer_intelligence_batch_rebuild_requested",
    "customer_intelligence_historical_backfill_requested",
    "agent_customer_question",
]


@dataclass(frozen=True)
class CustomerIntelligenceSource:
    source_type: str
    source_object_id: str
    business_object_type: str | None = None
    business_object_id: str | None = None

    def to_dict(self) -> JsonObject:
        return {
            "source_type": self.source_type,
            "source_object_id": self.source_object_id,
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
    occurred_at: datetime | None
    source: CustomerIntelligenceSource
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
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
            "source": self.source.to_dict(),
            "summary": self.summary,
            "payload": self.payload,
            "actor_id": self.actor_id,
            "thread_id": self.thread_id(),
        }


class CustomerIntelligenceEventService:
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
        return CustomerIntelligenceEvent(
            event_key=self._event_key(
                team_id=int(activity.team_id),
                trigger_type=trigger_type,
                source_type="customer_activity",
                source_object_id=source_object_id,
            ),
            trigger_type=trigger_type,
            tenant_id=int(activity.team_id),
            team_id=int(activity.team_id),
            customer_id=int(activity.customer_id),
            occurred_at=activity.occurred_at,
            source=CustomerIntelligenceSource(
                source_type="customer_activity",
                source_object_id=source_object_id,
                business_object_type="customer_activity",
                business_object_id=source_object_id,
            ),
            summary=activity.summary or activity.source_content,
            payload={
                "activity_kind": activity.activity_kind,
                "title": activity.title,
                "next_action": activity.next_action,
                "next_follow_time": activity.next_follow_time.isoformat() if activity.next_follow_time else None,
            },
            actor_id=activity.creator_id,
        )

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
                source_object_id=source_object_id,
            ),
            trigger_type=trigger_type,
            tenant_id=int(contact.team_id),
            team_id=int(contact.team_id),
            customer_id=int(contact.customer_id),
            occurred_at=contact.created_time,
            source=CustomerIntelligenceSource(
                source_type="customer_contact",
                source_object_id=source_object_id,
                business_object_type="contact",
                business_object_id=source_object_id,
            ),
            summary=f"{summary_by_trigger[trigger_type]}: {contact.name}",
            payload={
                "name": contact.name,
                "position": contact.position,
                "is_decision_maker": bool(contact.is_decision_maker),
                "is_primary": bool(contact.is_primary),
                "remark": contact.remark,
            },
            actor_id=actor_id,
        )

    def from_customer_profile(self, customer: Customer) -> CustomerIntelligenceEvent | None:
        if not self._has_profile_content(customer):
            return None
        source_object_id = str(customer.id)
        return CustomerIntelligenceEvent(
            event_key=self._event_key(
                team_id=int(customer.team_id),
                trigger_type="customer_profile_generated",
                source_type="customer_profile",
                source_object_id=source_object_id,
            ),
            trigger_type="customer_profile_generated",
            tenant_id=int(customer.team_id),
            team_id=int(customer.team_id),
            customer_id=int(customer.id),
            occurred_at=customer.profile_generated_time,
            source=CustomerIntelligenceSource(
                source_type="customer_profile",
                source_object_id=source_object_id,
                business_object_type="customer_profile",
                business_object_id=source_object_id,
            ),
            summary=f"客户档案已生成: {customer.account_name}",
            payload={
                "account_name": customer.account_name,
                "industry": customer.industry,
                "company_background": customer.company_background,
                "main_business": customer.main_business,
                "project_background": customer.project_background,
            },
            actor_id=customer.creator_id,
        )

    def from_customer_brief(self, customer: Customer) -> CustomerIntelligenceEvent | None:
        if not customer.customer_brief_markdown and not customer.customer_brief_json:
            return None
        source_object_id = str(customer.id)
        return CustomerIntelligenceEvent(
            event_key=self._event_key(
                team_id=int(customer.team_id),
                trigger_type="customer_brief_generated",
                source_type="customer_brief",
                source_object_id=source_object_id,
            ),
            trigger_type="customer_brief_generated",
            tenant_id=int(customer.team_id),
            team_id=int(customer.team_id),
            customer_id=int(customer.id),
            occurred_at=customer.customer_brief_generated_time,
            source=CustomerIntelligenceSource(
                source_type="customer_brief",
                source_object_id=source_object_id,
                business_object_type="customer_brief",
                business_object_id=source_object_id,
            ),
            summary=f"客户概况已生成: {customer.account_name}",
            payload={
                "account_name": customer.account_name,
                "customer_brief_json": self._parse_json_object(customer.customer_brief_json),
            },
            actor_id=customer.creator_id,
        )

    def from_deal_journey_event(self, event: CustomerDealJourneyEvent) -> CustomerIntelligenceEvent | None:
        if event.id is None:
            return None
        source_object_id = str(event.id)
        return CustomerIntelligenceEvent(
            event_key=self._event_key(
                team_id=int(event.team_id),
                trigger_type="deal_journey_event_recorded",
                source_type="deal_journey_event",
                source_object_id=source_object_id,
            ),
            trigger_type="deal_journey_event_recorded",
            tenant_id=int(event.team_id),
            team_id=int(event.team_id),
            customer_id=int(event.customer_id),
            occurred_at=event.event_time,
            source=CustomerIntelligenceSource(
                source_type="deal_journey_event",
                source_object_id=source_object_id,
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
            summary="客户已创建，刷新客户智能档案",
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
        payload: JsonObject | None = None,
        occurred_at: datetime | None = None,
    ) -> CustomerIntelligenceEvent:
        source_object_id = str(source_id)
        return CustomerIntelligenceEvent(
            event_key=self._event_key(
                team_id=team_id,
                trigger_type=trigger_type,
                source_type=source_type,
                source_object_id=f"{source_object_id}:{change_id}",
            ),
            trigger_type=trigger_type,
            tenant_id=team_id,
            team_id=team_id,
            customer_id=customer_id,
            occurred_at=occurred_at,
            source=CustomerIntelligenceSource(
                source_type=source_type,
                source_object_id=source_object_id,
                business_object_type=source_type,
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

    def _has_profile_content(self, customer: Customer) -> bool:
        return any(
            [
                customer.company_background,
                customer.main_business,
                customer.project_background,
                customer.similar_customers,
            ]
        )


customer_intelligence_event_service = CustomerIntelligenceEventService()

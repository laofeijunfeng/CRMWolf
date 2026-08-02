"""Build reusable customer evidence documents from CRM business events."""

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_vector_document import CustomerVectorDocumentSourceType
from app.models.deal_journey import CustomerDealJourneyEvent
from app.services.customer_activity_kinds import get_activity_kind_meta
from app.services.customer_alias_service import generated_aliases_for_customer_name

JSONPrimitive = str | int | float | bool | None
JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
JSONObject = dict[str, JSONValue]


@dataclass(frozen=True)
class BuiltCustomerEvidence:
    document_key: str
    tenant_id: int
    team_id: int
    customer_id: int
    source_type: str
    source_object_id: str
    business_object_type: str | None
    business_object_id: str | None
    title: str
    text: str
    text_hash: str
    qdrant_point_id: str
    occurred_at: datetime | None
    confidence: float
    visibility_scope: str
    metadata_version: int


class CustomerEvidenceBuilder:
    metadata_version = 2

    def from_customer_profile(
        self,
        customer: Customer,
        *,
        industry_display_name: str | None = None,
    ) -> BuiltCustomerEvidence | None:
        text = self._customer_profile_text(customer, industry_display_name=industry_display_name)
        if not text:
            return None
        source_object_id = str(customer.id)
        return self._build_customer_evidence(
            team_id=int(customer.team_id),
            customer_id=int(customer.id),
            source_type=CustomerVectorDocumentSourceType.CUSTOMER_PROFILE,
            source_object_id=source_object_id,
            business_object_type="customer_profile",
            business_object_id=source_object_id,
            title=f"客户档案: {customer.account_name}"[:255],
            text=text,
            occurred_at=customer.profile_generated_time,
            confidence=0.85,
        )

    def from_customer_brief(self, customer: Customer) -> BuiltCustomerEvidence | None:
        text = self._customer_brief_text(customer)
        if not text:
            return None
        source_object_id = str(customer.id)
        return self._build_customer_evidence(
            team_id=int(customer.team_id),
            customer_id=int(customer.id),
            source_type=CustomerVectorDocumentSourceType.CUSTOMER_BRIEF,
            source_object_id=source_object_id,
            business_object_type="customer_brief",
            business_object_id=source_object_id,
            title=f"客户概况: {customer.account_name}"[:255],
            text=text,
            occurred_at=customer.customer_brief_generated_time,
            confidence=0.8,
        )

    def from_deal_journey_event(self, event: CustomerDealJourneyEvent) -> BuiltCustomerEvidence | None:
        if event.id is None:
            return None
        text = self._deal_journey_event_text(event)
        if not text:
            return None
        source_object_id = str(event.id)
        return self._build_customer_evidence(
            team_id=int(event.team_id),
            customer_id=int(event.customer_id),
            source_type=CustomerVectorDocumentSourceType.BUSINESS_FLOW,
            source_object_id=source_object_id,
            business_object_type="deal_journey_event",
            business_object_id=source_object_id,
            title=f"业务流程事件: {event.event_type}"[:255],
            text=text,
            occurred_at=event.event_time,
            confidence=0.9,
        )

    def from_customer_activity(self, activity: CustomerActivity) -> BuiltCustomerEvidence | None:
        if activity.customer_id is None:
            return None

        text = self._activity_text(activity)
        source_object_id = str(activity.id)
        return self._build_customer_evidence(
            team_id=int(activity.team_id),
            customer_id=int(activity.customer_id),
            source_type=CustomerVectorDocumentSourceType.FOLLOW_UP,
            source_object_id=source_object_id,
            business_object_type="customer_activity",
            business_object_id=source_object_id,
            title=self._activity_title(activity),
            text=text,
            occurred_at=activity.occurred_at,
            confidence=0.95,
        )

    def _build_customer_evidence(
        self,
        *,
        team_id: int,
        customer_id: int,
        source_type: str,
        source_object_id: str,
        business_object_type: str,
        business_object_id: str,
        title: str,
        text: str,
        occurred_at: datetime | None,
        confidence: float,
    ) -> BuiltCustomerEvidence:
        text_hash = sha256(text.encode("utf-8")).hexdigest()
        document_key = self._document_key(
            team_id=team_id,
            source_type=source_type,
            source_object_id=source_object_id,
        )
        return BuiltCustomerEvidence(
            document_key=document_key,
            tenant_id=team_id,
            team_id=team_id,
            customer_id=customer_id,
            source_type=source_type,
            source_object_id=source_object_id,
            business_object_type=business_object_type,
            business_object_id=business_object_id,
            title=title,
            text=text,
            text_hash=text_hash,
            qdrant_point_id=document_key,
            occurred_at=occurred_at,
            confidence=confidence,
            visibility_scope="team",
            metadata_version=self.metadata_version,
        )

    def _activity_title(self, activity: CustomerActivity) -> str:
        if activity.title:
            return activity.title[:255]
        return get_activity_kind_meta(activity.activity_kind)["label"]

    def _activity_text(self, activity: CustomerActivity) -> str:
        sections: list[str] = []
        label = get_activity_kind_meta(activity.activity_kind)["label"]
        sections.append(f"活动类型: {label}")
        if activity.title:
            sections.append(f"标题: {activity.title}")
        if activity.summary:
            sections.append(f"摘要: {activity.summary}")
        sections.append(f"原始记录: {activity.source_content}")

        content = self._parse_object(activity.content_json)
        if content:
            structured_text = self._structured_content_text(content)
            if structured_text:
                sections.append(f"结构化内容: {structured_text}")

        if activity.next_action:
            sections.append(f"下一步: {activity.next_action}")
        if activity.next_follow_time:
            sections.append(f"下次跟进时间: {activity.next_follow_time.isoformat()}")

        return "\n".join(section for section in sections if section.strip())

    def _customer_profile_text(self, customer: Customer, *, industry_display_name: str | None = None) -> str:
        sections: list[str] = [f"客户名称: {customer.account_name}"]
        aliases = [
            alias for alias in generated_aliases_for_customer_name(str(customer.account_name or ""))
            if alias != customer.account_name
        ]
        if aliases:
            sections.append(f"常用简称候选: {'、'.join(aliases[:6])}")
        if industry_display_name:
            sections.append(f"行业: {industry_display_name}")
        if customer.city:
            sections.append(f"城市: {customer.city}")
        if customer.company_scale:
            sections.append(f"公司规模: {customer.company_scale}")
        if customer.company_background:
            sections.append(f"企业背景: {customer.company_background}")
        if customer.main_business:
            sections.append(f"主营业务: {customer.main_business}")
        if customer.project_background:
            sections.append(f"项目背景: {customer.project_background}")
        if customer.similar_customers:
            sections.append(f"相似客户: {customer.similar_customers}")
        return "\n".join(section for section in sections if section.strip())

    def _customer_brief_text(self, customer: Customer) -> str:
        sections: list[str] = [f"客户名称: {customer.account_name}"]
        if customer.customer_brief_markdown:
            sections.append(f"客户概况: {customer.customer_brief_markdown}")
        if customer.customer_brief_json:
            parsed = self._parse_object(customer.customer_brief_json)
            if parsed:
                sections.append(f"结构化概况: {self._structured_content_text(parsed)}")
        return "\n".join(section for section in sections if section.strip())

    def _deal_journey_event_text(self, event: CustomerDealJourneyEvent) -> str:
        sections = [
            f"事件类型: {event.event_type}",
            f"来源类型: {event.source_type}",
        ]
        if event.source_id is not None:
            sections.append(f"来源对象: {event.source_id}")
        if event.summary:
            sections.append(f"摘要: {event.summary}")
        metadata = self._parse_object(event.metadata_json)
        if metadata:
            sections.append(f"事件元数据: {self._structured_content_text(metadata)}")
        return "\n".join(section for section in sections if section.strip())

    def _parse_object(self, raw: str | None) -> JSONObject:
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _structured_content_text(self, value: JSONObject) -> str:
        normalized = self._compact_json_value(value)
        return json.dumps(normalized, ensure_ascii=False, separators=(",", ":")) if normalized else ""

    def _compact_json_value(self, value: JSONValue) -> JSONValue:
        if isinstance(value, dict):
            result: JSONObject = {}
            for key, item in value.items():
                compacted = self._compact_json_value(item)
                if self._has_content(compacted):
                    result[key] = compacted
            return result
        if isinstance(value, list):
            result_list = [self._compact_json_value(item) for item in value]
            return [item for item in result_list if self._has_content(item)]
        if isinstance(value, str):
            return value.strip()
        return value

    def _has_content(self, value: JSONValue) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, dict)):
            return bool(value)
        return True

    def _document_key(self, team_id: int, source_type: str, source_object_id: str) -> str:
        return uuid5(NAMESPACE_URL, f"crmwolf/customer-evidence/{team_id}/{source_type}/{source_object_id}").hex


customer_evidence_builder = CustomerEvidenceBuilder()

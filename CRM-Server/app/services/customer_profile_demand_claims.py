"""Deterministic demand-claim composition from recorded evidence.

This module owns topic grouping and claim wording. It must not import
customer_profile_projection_service (that module imports this one).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.crud.product_intent import match_catalog_product

_DEMAND_KEYWORDS = (
    "需求",
    "使用",
    "服务器",
    "部署",
    "采购",
    "功能",
    "预算",
    "系统",
    "平台",
    "接口",
    "场景",
    "私有化",
    "试用",
    "POC",
    "验收",
)
_TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("project_blocked", ("没进展", "暂无进展", "出差", "等领导", "等待领导")),
    ("approval", ("立项", "审批", "采购流程", "报价确认")),
    ("private_solution", ("私有化", "私有环境", "安装包", "部署方案", "本地部署")),
    ("usage_expansion", ("账号已用满", "增购", "授权", "续费", "扩大使用", "全公司")),
    ("reporting", ("报表", "导出", "按部门")),
    ("internal_validation", ("1-2个项目", "1—2个项目", "内部试用", "cto", "上级汇报")),
    ("procurement", ("预算", "采购", "招标", "放款", "财务审批", "付款", "内部过", "再给答复", "对一下时间")),
    ("acceptance", ("验收", "轻量交互页面")),
    ("poc", ("poc", "试用", "测试环境", "暂无问题", "正常进行")),
    ("generic_demand", _DEMAND_KEYWORDS),
)
_TOPIC_TITLES = {
    "project_blocked": "项目推进受阻",
    "approval": "立项与审批推进",
    "private_solution": "私有化方案评估",
    "acceptance": "产品事项验收",
    "poc": "POC 试用验证",
    "generic_demand": "客户沟通",
    "usage_expansion": "使用与授权范围",
    "reporting": "报表使用需求",
    "procurement": "采购与预算推进",
    "internal_validation": "内部试用与汇报",
}
_FACT_DEMAND_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("private_solution", ("私有化", "私有环境", "安装包", "本地部署", "部署方案")),
    ("reporting", ("报表", "导出", "按部门")),
    ("internal_validation", ("1-2个项目", "1—2个项目", "内部试用", "cto", "上级汇报")),
    ("usage_expansion", ("账号已用满", "增购", "授权", "续费", "扩大使用", "全公司")),
    ("procurement", ("预算", "采购", "招标", "放款", "财务审批", "付款")),
)
_DEMAND_TOPICS = {
    "private_solution",
    "poc",
    "acceptance",
    "generic_demand",
    "usage_expansion",
    "reporting",
    "internal_validation",
    "procurement",
}
_TOPIC_DETAIL_TERMS: dict[str, tuple[str, ...]] = {
    "private_solution": ("私有化", "私有环境", "安装包", "部署方案", "本地部署", "试用方案"),
    "poc": ("正式试用", "已部署", "已安装", "暂无问题", "正常进行", "测试环境", "POC", "poc", "试用"),
    "usage_expansion": ("账号已用满", "增购", "授权", "续费", "扩大使用", "全公司", "账号"),
    "reporting": ("报表", "导出", "按部门"),
    "internal_validation": ("1-2个项目", "1—2个项目", "内部试用", "CTO", "cto", "上级汇报"),
    "procurement": ("预算", "采购", "招标", "放款", "财务审批", "付款", "内部过", "再给答复", "对一下时间"),
    "acceptance": ("验收", "轻量交互页面"),
    "approval": ("立项", "审批", "采购流程", "报价确认", "立项材料"),
    "project_blocked": ("没进展", "暂无进展", "出差", "等领导", "等待领导"),
}
_TOPIC_FALLBACKS = {
    "private_solution": "跟进提到私有化或本地部署。",
    "poc": "跟进提到试用或 POC。",
    "acceptance": "跟进提到验收。",
    "usage_expansion": "跟进提到使用或授权范围。",
    "reporting": "跟进提到报表需求。",
    "internal_validation": "跟进提到内部试用。",
    "procurement": "跟进提到采购或预算。",
}
_TEXT_NORMALIZATION_PATTERN = r"[\s\uFF0C\u3002\uFF1B\uFF1A\u3001,.!?\uFF01\uFF1F\uFF08\uFF09()\-—_]+"


@dataclass(frozen=True)
class CatalogProductRef:
    public_id: str
    name: str
    is_active: bool = True


@dataclass(frozen=True)
class DemandClaim:
    topic: str
    statement: str
    claim_status: str
    product_public_ids: tuple[str, ...]
    product_names: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    source_quotes: tuple[str, ...]
    occurred_at: object
    latest_at: object
    journey_id: object
    journey_ids: tuple[object, ...]
    activity_count: int

    def as_item(self) -> dict[str, object]:
        source = " ".join(self.source_quotes)
        if (self.product_public_ids or self.topic == "private_solution") and "评估" in source:
            status = "方案仍在评估"
        else:
            status = "已记录"
        return {
            "topic": self.topic,
            "statement": self.statement,
            "occurred_at": self.occurred_at,
            "latest_at": self.latest_at,
            "journey_id": self.journey_id,
            "journey_ids": list(self.journey_ids),
            "activity_count": self.activity_count,
            "evidence_refs": list(self.evidence_refs),
            "status": status,
            "claim_status": self.claim_status,
            "product_public_ids": list(self.product_public_ids),
            "product_names": list(self.product_names),
            "source_quotes": list(self.source_quotes),
        }


def compose_demand_claims(
    activities: list[dict[str, object]],
    *,
    facts: list[dict[str, object]] | None = None,
    catalog: Sequence[CatalogProductRef] = (),
    customer_products: Sequence[CatalogProductRef] = (),
    opportunities: list[dict[str, object]] | None = None,
) -> list[DemandClaim]:
    catalog_rows = tuple(catalog or ())
    intent_products = tuple(customer_products or ())
    opportunity_rows = list(opportunities or [])
    claims_by_topic: dict[str, DemandClaim] = {}
    topic_order: list[str] = []

    for topic, grouped in _group_activities(activities):
        if topic not in _DEMAND_TOPICS:
            continue
        if topic == "generic_demand" and not any(_is_meaningful_activity(item) for item in grouped):
            continue
        claim = _claim_from_activities(
            topic,
            grouped,
            catalog=catalog_rows,
            customer_products=intent_products,
            opportunities=opportunity_rows,
        )
        if not claim.statement:
            continue
        claims_by_topic[topic] = claim
        if topic not in topic_order:
            topic_order.append(topic)

    for topic, grouped_facts in _group_demand_facts(facts or []):
        existing = claims_by_topic.get(topic)
        fact_refs = tuple(
            dict.fromkeys(
                key
                for fact in grouped_facts
                if (key := _evidence_key("fact", fact.get("id")))
            )
        )
        fact_quotes = tuple(
            quote
            for fact in grouped_facts
            if (quote := _text(fact.get("content"), limit=500))
        )
        if existing is not None:
            claims_by_topic[topic] = DemandClaim(
                topic=existing.topic,
                statement=existing.statement,
                claim_status=existing.claim_status,
                product_public_ids=existing.product_public_ids,
                product_names=existing.product_names,
                evidence_refs=tuple(dict.fromkeys([*existing.evidence_refs, *fact_refs])),
                source_quotes=tuple(dict.fromkeys([*existing.source_quotes, *fact_quotes])),
                occurred_at=existing.occurred_at,
                latest_at=existing.latest_at,
                journey_id=existing.journey_id,
                journey_ids=existing.journey_ids,
                activity_count=existing.activity_count,
            )
            continue
        statement = "；".join(fact_quotes)  # noqa: RUF001
        if not statement:
            continue
        latest = max(grouped_facts, key=_timeline_sort_key)
        occurred_at = min(
            (item.get("occurred_at") or item.get("extracted_at") or "" for item in grouped_facts),
            default=latest.get("occurred_at") or latest.get("extracted_at"),
        )
        claims_by_topic[topic] = DemandClaim(
            topic=topic,
            statement=statement,
            claim_status="AVAILABLE",
            product_public_ids=(),
            product_names=(),
            evidence_refs=fact_refs,
            source_quotes=fact_quotes,
            occurred_at=occurred_at,
            latest_at=latest.get("occurred_at") or latest.get("extracted_at"),
            journey_id=None,
            journey_ids=(),
            activity_count=0,
        )
        if topic not in topic_order:
            topic_order.append(topic)

    return [claims_by_topic[topic] for topic in topic_order if topic in claims_by_topic][:8]


def _text(value: object, *, limit: int = 500) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit].strip()


def _activity_text(activity: dict[str, object], *, limit: int = 800) -> str:
    """Prefer the concise recorded summary, falling back to the source wording."""

    return _text(activity.get("content") or activity.get("summary") or activity.get("source_content"), limit=limit)


def _timeline_sort_key(item: dict[str, object]) -> str:
    return str(
        item.get("occurred_at")
        or item.get("event_time")
        or item.get("created_time")
        or item.get("updated_time")
        or item.get("extracted_at")
        or ""
    )


def _similar_text(left: str, right: str) -> bool:
    """Cheap deterministic near-duplicate detection for short CRM notes."""

    normalized_left = re.sub(_TEXT_NORMALIZATION_PATTERN, "", left).lower()
    normalized_right = re.sub(_TEXT_NORMALIZATION_PATTERN, "", right).lower()
    if not normalized_left or not normalized_right:
        return False
    if normalized_left in normalized_right or normalized_right in normalized_left:
        return True
    left_chars, right_chars = set(normalized_left), set(normalized_right)
    overlap = len(left_chars & right_chars) / max(1, min(len(left_chars), len(right_chars)))
    return overlap >= 0.86


def _activity_topic(activity: dict[str, object]) -> str | None:
    text = _activity_text(activity, limit=1200).lower()
    if not text:
        return None
    for topic, keywords in _TOPIC_RULES:
        if any(keyword.lower() in text for keyword in keywords):
            return topic
    return None


def _activity_datetime(activity: dict[str, object]) -> datetime | None:
    value = activity.get("occurred_at") or activity.get("event_time") or activity.get("created_time")
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _unique_activity_texts(activities: list[dict[str, object]], *, limit: int = 3) -> list[str]:
    texts: list[str] = []
    for activity in sorted(activities, key=_timeline_sort_key):
        text = _activity_text(activity, limit=800)
        if text and not any(_similar_text(text, existing) for existing in texts):
            texts.append(text)
    return texts[-limit:]


def _group_activities(activities: list[dict[str, object]]) -> list[tuple[str, list[dict[str, object]]]]:
    """Group notes by recorded topic while keeping long-running phases readable.

    A topic starts a new node after a long gap, so an old need does not silently
    become the current phase. Within a phase, repeated notes are represented by
    one node with all evidence refs and a small set of distinct recorded facts.
    """

    groups: list[tuple[str, list[dict[str, object]]]] = []
    group_indexes: dict[str, int] = {}
    last_by_topic: dict[str, datetime] = {}
    for activity in sorted(activities, key=_timeline_sort_key):
        topic = _activity_topic(activity) or "other"
        occurred_at = _activity_datetime(activity)
        group_index = group_indexes.get(topic)
        previous_at = last_by_topic.get(topic)
        gap_days = 0.0
        if previous_at is not None and occurred_at is not None:
            try:
                gap_days = (occurred_at - previous_at).total_seconds() / 86400
            except TypeError:
                gap_days = 0.0
        if group_index is None or gap_days > 45:
            group_indexes[topic] = len(groups)
            groups.append((topic, [activity]))
        else:
            groups[group_index][1].append(activity)
        if occurred_at is not None:
            last_by_topic[topic] = occurred_at
    return groups


def _is_meaningful_activity(activity: dict[str, object]) -> bool:
    text = _activity_text(activity, limit=800)
    normalized = re.sub(_TEXT_NORMALIZATION_PATTERN, "", text).lower()
    return bool(
        normalized
        and normalized not in {"测试", "测试测试", "test", "testtest"}
        and not (normalized.startswith(("neg", "def")) and len(normalized) < 40)
    )


def _fact_topic(fact: dict[str, object]) -> str | None:
    text = " ".join(
        value
        for value in (
            _text(fact.get("subject"), limit=255),
            _text(fact.get("content"), limit=800),
        )
        if value
    ).lower()
    fact_type = str(fact.get("fact_type") or "")
    for topic, keywords in _FACT_DEMAND_RULES:
        if any(keyword.lower() in text for keyword in keywords):
            return topic
    if fact_type == "need":
        return "generic_demand"
    return None


def _group_demand_facts(facts: list[dict[str, object]]) -> list[tuple[str, list[dict[str, object]]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for fact in sorted(facts, key=_timeline_sort_key, reverse=True):
        topic = _fact_topic(fact)
        if topic is None:
            continue
        content = _text(fact.get("content"), limit=800)
        if not content or any(
            _similar_text(content, _text(item.get("content"), limit=800))
            for item in grouped.get(topic, [])
        ):
            continue
        grouped.setdefault(topic, []).append(fact)
    return list(grouped.items())


def _evidence_key(kind: str, object_id: object) -> str:
    if object_id is None or object_id == "":
        return ""
    return f"{kind}:{object_id}"


def _mentioned_products(text: str, catalog: Sequence[CatalogProductRef]) -> tuple[CatalogProductRef, ...]:
    matched = match_catalog_product(catalog, text)
    return (CatalogProductRef(matched.public_id, matched.name, True),) if matched is not None else ()


def _opportunity_products(
    opportunities: list[dict[str, object]],
    journey_ids: tuple[object, ...],
) -> tuple[CatalogProductRef, ...]:
    rows = opportunities
    if journey_ids:
        allowed = set(journey_ids)
        rows = [item for item in opportunities if item.get("deal_journey_id") in allowed]
    products: list[CatalogProductRef] = []
    seen: set[str] = set()
    for item in rows:
        public_id = item.get("product_public_id")
        name = item.get("product_name")
        if not public_id or not name:
            continue
        key = str(public_id)
        if key in seen:
            continue
        seen.add(key)
        products.append(CatalogProductRef(str(public_id), str(name)))
    return tuple(products)


def _resolve_products(
    *,
    mentioned: tuple[CatalogProductRef, ...],
    journey_ids: tuple[object, ...],
    customer_products: Sequence[CatalogProductRef],
    opportunities: list[dict[str, object]],
) -> tuple[tuple[CatalogProductRef, ...], str | None]:
    if mentioned:
        return mentioned, "mentioned"
    opportunity_products = _opportunity_products(opportunities, journey_ids)
    if len(opportunity_products) == 1:
        return opportunity_products, "opportunity"
    unique_intent = tuple(
        dict.fromkeys(item.public_id for item in customer_products if item.public_id and item.name)
    )
    if len(customer_products) == 1 and customer_products[0].public_id and customer_products[0].name:
        return (customer_products[0],), "customer"
    if len(unique_intent) == 1:
        match = next(item for item in customer_products if item.public_id == unique_intent[0])
        return (match,), "customer"
    return (), None


def _appearing_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    lower = text.lower()
    for term in terms:
        if term.lower() in lower and term not in found:
            found.append(term)
    return found


def _bound_product_prefix(products: tuple[CatalogProductRef, ...], source: str | None) -> str:
    if not products or source not in {"customer", "opportunity"}:
        return ""
    name = products[0].name
    if source == "customer":
        return f"客户意向产品为 {name}，"
    return f"商机产品为 {name}，"


def _append_private_extras(statement: str, source_text: str) -> str:
    extras = [term for term in ("安装包", "试用方案") if term in source_text]
    if not extras:
        return statement
    return statement.rstrip("。") + "，需要" + "和".join(extras) + "。"


def _compose_statement(
    topic: str,
    source_text: str,
    products: tuple[CatalogProductRef, ...],
    product_source: str | None,
) -> str:
    if topic == "generic_demand":
        return source_text
    if topic == "private_solution":
        if product_source == "mentioned" and products:
            statement = f"跟进记录显示客户对 {products[0].name} 感兴趣，公司层面使用需要私有化部署。"
        elif product_source in {"customer", "opportunity"} and products:
            statement = _bound_product_prefix(products, product_source) + "正在了解私有化部署。"
        else:
            statement = _TOPIC_FALLBACKS["private_solution"]
        return _append_private_extras(statement, source_text)

    details = _appearing_terms(source_text, _TOPIC_DETAIL_TERMS.get(topic, ()))
    if product_source == "mentioned" and products:
        name = products[0].name
        if details:
            return f"{name} 相关跟进提到{'、'.join(details)}。"
        fallback = _TOPIC_FALLBACKS.get(topic, "跟进已记录客户需求。")
        return f"{name} 相关{fallback}"
    body = f"跟进提到{'、'.join(details)}。" if details else _TOPIC_FALLBACKS.get(topic, "跟进已记录客户需求。")
    return _bound_product_prefix(products, product_source) + body


def _claim_from_activities(
    topic: str,
    grouped: list[dict[str, object]],
    *,
    catalog: Sequence[CatalogProductRef],
    customer_products: Sequence[CatalogProductRef],
    opportunities: list[dict[str, object]],
) -> DemandClaim:
    quotes = tuple(_unique_activity_texts(grouped, limit=3))
    mentioned: list[CatalogProductRef] = []
    seen: set[str] = set()
    for item in grouped:
        for product in _mentioned_products(_activity_text(item, limit=1200), catalog):
            if product.public_id in seen:
                continue
            seen.add(product.public_id)
            mentioned.append(product)
    journey_ids = tuple(
        dict.fromkeys(
            item.get("deal_journey_id") for item in grouped if item.get("deal_journey_id") is not None
        )
    )
    products, product_source = _resolve_products(
        mentioned=tuple(mentioned),
        journey_ids=journey_ids,
        customer_products=customer_products,
        opportunities=opportunities,
    )
    if topic == "generic_demand":
        statement = quotes[-1] if quotes else ""
    else:
        statement = _compose_statement(topic, "；".join(quotes), products, product_source)  # noqa: RUF001
    latest = grouped[-1]
    refs = tuple(
        dict.fromkeys(
            key
            for item in grouped
            if (key := _evidence_key("activity", item.get("id")))
        )
    )
    return DemandClaim(
        topic=topic,
        statement=statement,
        claim_status="AVAILABLE",
        product_public_ids=tuple(item.public_id for item in products),
        product_names=tuple(item.name for item in products),
        evidence_refs=refs,
        source_quotes=quotes,
        occurred_at=grouped[0].get("occurred_at"),
        latest_at=latest.get("occurred_at"),
        journey_id=latest.get("deal_journey_id"),
        journey_ids=journey_ids,
        activity_count=len(grouped),
    )

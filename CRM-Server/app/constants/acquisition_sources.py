"""获客来源系统默认项与历史映射。"""

from __future__ import annotations

from typing import Final, Iterable, NamedTuple

FORBIDDEN_SOURCE_NAME: Final = "线索转化"

SYSTEM_DEFAULT_SOURCES: Final[tuple[dict[str, object], ...]] = (
    {"sort_order": 10, "code": "ONLINE_REGISTER", "name": "线上注册"},
    {"sort_order": 20, "code": "MARKETING_ACTIVITY", "name": "市场活动"},
    {"sort_order": 30, "code": "REFERRAL", "name": "客户推荐"},
    {"sort_order": 40, "code": "COLD_CALL", "name": "电话营销"},
    {"sort_order": 50, "code": "WEBSITE_INQUIRY", "name": "网站咨询"},
    {"sort_order": 60, "code": "EXHIBITION", "name": "展会"},
    {"sort_order": 70, "code": "OTHER", "name": "其他"},
)

SYSTEM_SOURCE_CODES: Final[tuple[str, ...]] = tuple(
    str(item["code"]) for item in SYSTEM_DEFAULT_SOURCES
)

_LEGACY_SOURCE_ALIASES: Final[dict[str, str]] = {
    "online_register": "ONLINE_REGISTER",
    "线上注册": "ONLINE_REGISTER",
    "marketing_activity": "MARKETING_ACTIVITY",
    "市场活动": "MARKETING_ACTIVITY",
    "referral": "REFERRAL",
    "客户推荐": "REFERRAL",
    "cold_call": "COLD_CALL",
    "电话营销": "COLD_CALL",
    "website_inquiry": "WEBSITE_INQUIRY",
    "网站咨询": "WEBSITE_INQUIRY",
    "exhibition": "EXHIBITION",
    "展会": "EXHIBITION",
    "other": "OTHER",
    "其他": "OTHER",
    "lead_conversion": "OTHER",
    "线索转化": "OTHER",
}

# 仅系统项允许别名，避免自定义项被模糊匹配误伤。
AI_SOURCE_ALIASES: Final[dict[str, str]] = {
    **_LEGACY_SOURCE_ALIASES,
    "朋友介绍": "REFERRAL",
    "朋友推荐": "REFERRAL",
    "客户介绍": "REFERRAL",
    "老客户介绍": "REFERRAL",
    "转介绍": "REFERRAL",
    "官网注册": "ONLINE_REGISTER",
    "网上注册": "ONLINE_REGISTER",
    "网站注册": "ONLINE_REGISTER",
    "线上广告": "ONLINE_REGISTER",
    "线下活动": "MARKETING_ACTIVITY",
    "营销活动": "MARKETING_ACTIVITY",
    "电话咨询": "COLD_CALL",
    "电话推销": "COLD_CALL",
    "官网咨询": "WEBSITE_INQUIRY",
    "网上咨询": "WEBSITE_INQUIRY",
    "在线咨询": "WEBSITE_INQUIRY",
    "参展": "EXHIBITION",
    "博览会": "EXHIBITION",
    "渠道合作": "OTHER",
}


def normalize_source_name(name: str) -> str:
    return name.strip()


def is_forbidden_source_name(name: str) -> bool:
    return normalize_source_name(name).casefold() == FORBIDDEN_SOURCE_NAME.casefold()


class LegacySourceClassification(NamedTuple):
    code: str | None
    is_dirty: bool
    original: str | None


def classify_legacy_source(raw: object) -> LegacySourceClassification:
    if raw is None:
        return LegacySourceClassification(None, False, None)
    text = str(raw).strip()
    if not text:
        return LegacySourceClassification(None, False, None)
    mapped = _LEGACY_SOURCE_ALIASES.get(text.casefold())
    if mapped is not None:
        return LegacySourceClassification(mapped, False, text)
    return LegacySourceClassification("OTHER", True, text)


def map_legacy_source_code(raw: object) -> str | None:
    return classify_legacy_source(raw).code


def summarize_legacy_source_backfill(
    records: Iterable[tuple[int, object]],
) -> dict[str, object]:
    aligned = 0
    empty = 0
    dirty: list[dict[str, object]] = []
    for entity_id, raw in records:
        item = classify_legacy_source(raw)
        if item.code is None:
            empty += 1
            continue
        if item.is_dirty:
            dirty.append({"id": int(entity_id), "original": item.original})
        else:
            aligned += 1
    return {"aligned": aligned, "empty": empty, "dirty": dirty}

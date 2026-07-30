"""Canonical customer activity kind metadata."""
from __future__ import annotations

from typing import Any, Dict


class CustomerActivityKind:
    PHONE_FOLLOW_UP = "PHONE_FOLLOW_UP"
    WECHAT_FOLLOW_UP = "WECHAT_FOLLOW_UP"
    EMAIL_FOLLOW_UP = "EMAIL_FOLLOW_UP"
    VISIT_FOLLOW_UP = "VISIT_FOLLOW_UP"
    ONLINE_MEETING = "ONLINE_MEETING"
    OFFLINE_MEETING = "OFFLINE_MEETING"
    OTHER_FOLLOW_UP = "OTHER_FOLLOW_UP"


ACTIVITY_KIND_META: Dict[str, Dict[str, Any]] = {
    CustomerActivityKind.PHONE_FOLLOW_UP: {
        "category": "FOLLOW_UP",
        "label": "电话跟进",
        "agent_schema": "follow_up",
        "score_rule": "follow_up",
    },
    CustomerActivityKind.WECHAT_FOLLOW_UP: {
        "category": "FOLLOW_UP",
        "label": "微信跟进",
        "agent_schema": "follow_up",
        "score_rule": "follow_up",
    },
    CustomerActivityKind.EMAIL_FOLLOW_UP: {
        "category": "FOLLOW_UP",
        "label": "邮件跟进",
        "agent_schema": "follow_up",
        "score_rule": "follow_up",
    },
    CustomerActivityKind.VISIT_FOLLOW_UP: {
        "category": "FOLLOW_UP",
        "label": "拜访跟进",
        "agent_schema": "follow_up",
        "score_rule": "follow_up",
    },
    CustomerActivityKind.ONLINE_MEETING: {
        "category": "MEETING",
        "label": "线上会议",
        "agent_schema": "meeting",
        "score_rule": "meeting",
    },
    CustomerActivityKind.OFFLINE_MEETING: {
        "category": "MEETING",
        "label": "线下会议",
        "agent_schema": "meeting",
        "score_rule": "meeting",
    },
    CustomerActivityKind.OTHER_FOLLOW_UP: {
        "category": "FOLLOW_UP",
        "label": "其他跟进",
        "agent_schema": "follow_up",
        "score_rule": "follow_up",
    },
}


FOLLOW_UP_METHOD_TO_KIND = {
    "电话": CustomerActivityKind.PHONE_FOLLOW_UP,
    "电话跟进": CustomerActivityKind.PHONE_FOLLOW_UP,
    "微信": CustomerActivityKind.WECHAT_FOLLOW_UP,
    "微信跟进": CustomerActivityKind.WECHAT_FOLLOW_UP,
    "邮件": CustomerActivityKind.EMAIL_FOLLOW_UP,
    "邮件跟进": CustomerActivityKind.EMAIL_FOLLOW_UP,
    "拜访": CustomerActivityKind.VISIT_FOLLOW_UP,
    "拜访跟进": CustomerActivityKind.VISIT_FOLLOW_UP,
    "面谈": CustomerActivityKind.VISIT_FOLLOW_UP,
    "会议": CustomerActivityKind.ONLINE_MEETING,
    "线上会议": CustomerActivityKind.ONLINE_MEETING,
    "线上交流": CustomerActivityKind.ONLINE_MEETING,
    "线上沟通": CustomerActivityKind.ONLINE_MEETING,
    "远程交流": CustomerActivityKind.ONLINE_MEETING,
    "线下会议": CustomerActivityKind.OFFLINE_MEETING,
    "会议纪要": CustomerActivityKind.ONLINE_MEETING,
    "AI录入": CustomerActivityKind.OTHER_FOLLOW_UP,
    "其他": CustomerActivityKind.OTHER_FOLLOW_UP,
}

_OFFLINE_MEETING_KEYWORDS = ("线下会议", "现场会议", "线下交流会", "线下沟通会")
_ONLINE_MEETING_KEYWORDS = (
    "线上会议",
    "线上交流",
    "线上沟通",
    "在线交流",
    "在线沟通",
    "远程会议",
    "远程交流",
    "远程沟通",
    "视频会议",
    "腾讯会议",
    "飞书会议",
    "zoom会议",
)
_VISIT_KEYWORDS = ("线下拜访", "现场拜访", "客户拜访", "上门拜访", "拜访", "面谈")
_MEETING_STRUCTURE_KEYWORDS = (
    "会议内容",
    "会议纪要",
    "会议主题",
    "参会",
    "参会成员",
    "我方：",
    "我方:",
    "对接方：",
    "对接方:",
    "客户方：",
    "客户方:",
)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword.lower() in text.lower() for keyword in keywords)


def normalize_activity_kind(value: str | None) -> str:
    if not value:
        return CustomerActivityKind.OTHER_FOLLOW_UP
    normalized = value.strip()
    if normalized in ACTIVITY_KIND_META:
        return normalized
    if normalized in FOLLOW_UP_METHOD_TO_KIND:
        return FOLLOW_UP_METHOD_TO_KIND[normalized]
    if _contains_any(normalized, _ONLINE_MEETING_KEYWORDS):
        return CustomerActivityKind.ONLINE_MEETING
    if _contains_any(normalized, _OFFLINE_MEETING_KEYWORDS):
        return CustomerActivityKind.OFFLINE_MEETING
    if _contains_any(normalized, _VISIT_KEYWORDS):
        return CustomerActivityKind.VISIT_FOLLOW_UP
    return CustomerActivityKind.OTHER_FOLLOW_UP


def infer_activity_kind(method: str | None, content: str | None = None) -> str:
    method_text = (method or "").strip()
    content_text = (content or "").strip()
    combined = f"{method_text}\n{content_text}".strip()

    if _contains_any(combined, _ONLINE_MEETING_KEYWORDS):
        return CustomerActivityKind.ONLINE_MEETING
    if _contains_any(combined, _OFFLINE_MEETING_KEYWORDS):
        return CustomerActivityKind.OFFLINE_MEETING

    has_meeting_structure = _contains_any(combined, _MEETING_STRUCTURE_KEYWORDS)
    has_offline_visit_signal = _contains_any(method_text or content_text, _VISIT_KEYWORDS) or "线下" in combined
    if has_meeting_structure and has_offline_visit_signal:
        return CustomerActivityKind.OFFLINE_MEETING
    if has_meeting_structure:
        return CustomerActivityKind.ONLINE_MEETING

    return normalize_activity_kind(method_text)


def get_activity_kind_meta(activity_kind: str) -> Dict[str, Any]:
    kind = normalize_activity_kind(activity_kind)
    return {"value": kind, **ACTIVITY_KIND_META[kind]}


def get_activity_category(activity_kind: str) -> str:
    return get_activity_kind_meta(activity_kind)["category"]

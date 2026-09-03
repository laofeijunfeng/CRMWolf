"""Adapters for importing pre-canonical customer-activity data.

The customer-activity runtime uses ``activity_kind`` as its only canonical
classification.  This module is the explicit boundary for the one historical
shape that still needs conversion: ``LeadFollowUp.method``.
"""

from __future__ import annotations

from app.services.customer_activity_kinds import CustomerActivityKind

LEGACY_LEAD_METHOD_TO_ACTIVITY_KIND: dict[str, str] = {
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


def activity_kind_from_legacy_lead_method(method: object) -> str:
    """Convert a legacy lead follow-up method at the import boundary only."""

    if isinstance(method, str):
        value = method
    else:
        enum_value = getattr(method, "value", None)
        if not isinstance(enum_value, str):
            return CustomerActivityKind.OTHER_FOLLOW_UP
        value = enum_value
    return LEGACY_LEAD_METHOD_TO_ACTIVITY_KIND.get(
        value.strip(),
        CustomerActivityKind.OTHER_FOLLOW_UP,
    )

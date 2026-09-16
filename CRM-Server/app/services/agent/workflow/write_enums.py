"""Deterministic write-side enum canonicalization for Workflow planning."""

from __future__ import annotations

import re

from app.models.lead import CompanyScale, FollowUpMethod

_LEAD_FOLLOW_UP_METHOD_ALIASES: dict[str, FollowUpMethod] = {
    "电话": FollowUpMethod.PHONE,
    "phone": FollowUpMethod.PHONE,
    "电话联系": FollowUpMethod.PHONE,
    "电话沟通": FollowUpMethod.PHONE,
    "来电": FollowUpMethod.PHONE,
    "微信": FollowUpMethod.WECHAT,
    "wechat": FollowUpMethod.WECHAT,
    "拜访": FollowUpMethod.VISIT,
    "visit": FollowUpMethod.VISIT,
    "邮件": FollowUpMethod.EMAIL,
    "email": FollowUpMethod.EMAIL,
    "其他": FollowUpMethod.OTHER,
    "other": FollowUpMethod.OTHER,
    "会议": FollowUpMethod.OTHER,
    "线上会议": FollowUpMethod.OTHER,
    "线下会议": FollowUpMethod.OTHER,
    "视频会议": FollowUpMethod.OTHER,
}

_COMPANY_SCALE_BY_TEXT: dict[str, str] = {
    member.value: member.value for member in CompanyScale
}
_COMPANY_SCALE_BY_TEXT.update({member.name: member.value for member in CompanyScale})
_COMPANY_SCALE_BY_TEXT.update(
    {
        "10~29": CompanyScale.SCALE_1_50.value,
        "10-29": CompanyScale.SCALE_1_50.value,
        "15人左右": CompanyScale.SCALE_1_50.value,
        "15人": CompanyScale.SCALE_1_50.value,
    }
)


class UnmappedLeadFollowUpMethod(ValueError):
    def __init__(self, raw: str) -> None:
        self.raw = raw
        super().__init__(raw)


def canonicalize_lead_follow_up_method(value: object) -> FollowUpMethod:
    if value is None:
        return FollowUpMethod.OTHER
    if isinstance(value, FollowUpMethod):
        return value
    if not isinstance(value, str):
        raise UnmappedLeadFollowUpMethod(str(value))
    stripped = value.strip()
    if not stripped:
        return FollowUpMethod.OTHER
    if stripped in FollowUpMethod._value2member_map_:
        return FollowUpMethod(stripped)
    alias = _LEAD_FOLLOW_UP_METHOD_ALIASES.get(stripped) or _LEAD_FOLLOW_UP_METHOD_ALIASES.get(
        stripped.casefold()
    )
    if alias is not None:
        return alias
    raise UnmappedLeadFollowUpMethod(stripped)


def canonicalize_company_scale(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, CompanyScale):
        return value.value
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    direct = _COMPANY_SCALE_BY_TEXT.get(stripped) or _COMPANY_SCALE_BY_TEXT.get(stripped.casefold())
    if direct is not None:
        return direct
    match = re.fullmatch(r"(\d+)\s*人(?:左右)?", stripped)
    if match is not None:
        count = int(match.group(1))
        if 1 <= count <= 50:
            return CompanyScale.SCALE_1_50.value
        if 51 <= count <= 200:
            return CompanyScale.SCALE_51_200.value
        if 201 <= count <= 500:
            return CompanyScale.SCALE_201_500.value
        if 501 <= count <= 1000:
            return CompanyScale.SCALE_501_1000.value
        if count > 1000:
            return CompanyScale.SCALE_1000_PLUS.value
    return None

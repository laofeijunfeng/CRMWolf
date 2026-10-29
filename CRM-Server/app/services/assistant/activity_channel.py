"""Server acceptance of a model-nominated customer activity channel.

The model may nominate a canonical kind. This module decides whether that
nomination can be frozen, or whether the user must choose. Keyword matching
runs only when the model result cannot be used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from app.services.customer_activity_kinds import CustomerActivityKind, infer_activity_kind

if TYPE_CHECKING:
    from app.services.assistant.llm_contracts import KindDecision

# ruff: noqa: RUF001

HIGH_CONFIDENCE = 0.8

FOLLOW_UP_KINDS: tuple[str, ...] = (
    CustomerActivityKind.PHONE_FOLLOW_UP,
    CustomerActivityKind.WECHAT_FOLLOW_UP,
    CustomerActivityKind.EMAIL_FOLLOW_UP,
    CustomerActivityKind.VISIT_FOLLOW_UP,
    CustomerActivityKind.OTHER_FOLLOW_UP,
)
MEETING_KINDS: tuple[str, ...] = (
    CustomerActivityKind.ONLINE_MEETING,
    CustomerActivityKind.OFFLINE_MEETING,
)
CANONICAL_KINDS = frozenset(FOLLOW_UP_KINDS + MEETING_KINDS)

_PHONE_PHRASES = ("电话联系", "电话沟通", "电话跟进", "来电", "去电", "打电话", "通电话", "打了电话", "电话里")
_PHONE_NEGATIVE = ("电话号码", "手机号", "座机", "留个电话", "留电话")
_WECHAT_PHRASES = ("企业微信", "企微", "微信")
_EMAIL_PHRASES = ("发邮件", "邮件", "电邮", "e-mail", "email")
_VISIT_PHRASES = ("上门拜访", "现场拜访", "客户拜访", "拜访", "面谈")

ChannelStatus = Literal["recognized", "required", "family_unclear"]
ChannelSource = Literal["model", "keyword", "user"]
ActivityFamily = Literal["FOLLOW_UP", "ONLINE_MEETING", "OFFLINE_MEETING", "UNCLEAR"]


@dataclass(frozen=True)
class ChannelResolution:
    """What the server will freeze. A nomination is not itself a command."""

    status: ChannelStatus
    family: ActivityFamily
    kind: str | None
    source: ChannelSource | None
    confidence: float | None
    quote: str | None
    reason: str
    status_label: str
    source_text: str
    options: tuple[str, ...]


def structuring_kind(activity_kind: str | None) -> str:
    """Map a canonical follow-up onto the follow-up structuring schema."""

    if activity_kind in MEETING_KINDS:
        return activity_kind or "ONLINE_MEETING"
    return "FOLLOW_UP"


def resolve_channel(
    text: str,
    decision: KindDecision | None,
    *,
    model_failed: bool,
) -> ChannelResolution:
    """Accept one model nomination, or fall back to the closed keyword table."""

    source_text = text or ""
    if model_failed or decision is None:
        return _from_keywords(source_text, reason="模型结果不可用")
    quote = decision.evidence_quote.strip()
    if quote and quote not in source_text:
        return _from_keywords(source_text, reason="识别引用不在原文中")
    return _from_model(source_text, decision, quote)


def _from_model(text: str, decision: KindDecision, quote: str) -> ChannelResolution:
    if decision.kind == "UNCLEAR":
        return _family_unclear(decision.reason or "活动类型不清楚")
    nominated = _nominated_channels(decision)
    follow_channels = [kind for kind in nominated if kind in FOLLOW_UP_KINDS]
    meeting_channels = [kind for kind in nominated if kind in MEETING_KINDS]
    keyword_follow = detect_follow_up_channels(text)
    keyword_meeting = _keyword_meeting(text)
    if _cross_family(follow_channels, meeting_channels, keyword_follow, keyword_meeting):
        return _family_unclear("原文同时出现会议和跟进渠道")
    if len(dict.fromkeys([*follow_channels, *keyword_follow])) >= 2:
        return _required(text, "原文同时出现多个渠道", quote=quote)
    kind = decision.kind if decision.kind in CANONICAL_KINDS else None
    quote_ok = bool(quote)
    confident = decision.confidence >= HIGH_CONFIDENCE and quote_ok
    if kind is None or not confident:
        return _required(text, "渠道置信度不足或没有可用引用", quote=quote or None)
    if kind in FOLLOW_UP_KINDS and keyword_follow and keyword_follow != [kind]:
        return _required(text, "识别结果和原文渠道不一致", quote=quote)
    return _recognized(
        kind,
        source="model",
        confidence=decision.confidence,
        quote=quote,
        status_label="AI 已识别 · 高置信度",
    )


def _from_keywords(text: str, *, reason: str) -> ChannelResolution:
    follow_channels = detect_follow_up_channels(text)
    meeting = _keyword_meeting(text)
    if meeting is not None and follow_channels:
        return _family_unclear("原文同时出现会议和跟进渠道")
    if meeting is not None:
        quote = _meeting_quote(text, meeting)
        return _recognized(
            meeting,
            source="keyword",
            confidence=None,
            quote=quote,
            status_label="已识别 · 词表兜底",
        )
    if len(follow_channels) == 1:
        quote = _follow_quote(text, follow_channels[0])
        return _recognized(
            follow_channels[0],
            source="keyword",
            confidence=None,
            quote=quote,
            status_label="已识别 · 词表兜底",
        )
    if len(follow_channels) >= 2:
        return _required(text, "原文同时出现多个渠道")
    return _required(text, reason)


def detect_follow_up_channels(text: str) -> list[str]:
    """Return follow-up families explicitly named in user text, in card order."""

    found: list[str] = []
    scrubbed = text
    for phrase in _PHONE_NEGATIVE:
        scrubbed = scrubbed.replace(phrase, "")
    if any(phrase in text for phrase in _PHONE_PHRASES) or "电话" in scrubbed:
        found.append(CustomerActivityKind.PHONE_FOLLOW_UP)
    if any(phrase in text for phrase in _WECHAT_PHRASES):
        found.append(CustomerActivityKind.WECHAT_FOLLOW_UP)
    lowered = text.lower()
    if any(phrase.lower() in lowered for phrase in _EMAIL_PHRASES):
        found.append(CustomerActivityKind.EMAIL_FOLLOW_UP)
    if any(phrase in text for phrase in _VISIT_PHRASES):
        found.append(CustomerActivityKind.VISIT_FOLLOW_UP)
    return found


def _nominated_channels(decision: KindDecision) -> list[str]:
    values: list[str] = []
    if decision.kind in CANONICAL_KINDS:
        values.append(decision.kind)
    for kind in decision.channels:
        if kind in CANONICAL_KINDS and kind not in values:
            values.append(kind)
    return values


def _keyword_meeting(text: str) -> str | None:
    inferred = infer_activity_kind(None, text)
    if inferred in MEETING_KINDS:
        return inferred
    return None


def _cross_family(
    follow_channels: list[str],
    meeting_channels: list[str],
    keyword_follow: list[str],
    keyword_meeting: str | None,
) -> bool:
    has_follow = bool(follow_channels or keyword_follow)
    has_meeting = bool(meeting_channels or keyword_meeting)
    return has_follow and has_meeting


def _recognized(
    kind: str,
    *,
    source: ChannelSource,
    confidence: float | None,
    quote: str | None,
    status_label: str,
) -> ChannelResolution:
    family: ActivityFamily = kind if kind in MEETING_KINDS else "FOLLOW_UP"
    source_text = f"从“{quote}”中识别" if quote else "从原文中识别"
    return ChannelResolution(
        status="recognized",
        family=family,
        kind=kind,
        source=source,
        confidence=confidence,
        quote=quote,
        reason="",
        status_label=status_label,
        source_text=source_text,
        options=MEETING_KINDS if kind in MEETING_KINDS else FOLLOW_UP_KINDS,
    )


def _required(text: str, reason: str, *, quote: str | None = None) -> ChannelResolution:
    meeting = _keyword_meeting(text)
    options = MEETING_KINDS if meeting is not None and not detect_follow_up_channels(text) else FOLLOW_UP_KINDS
    family: ActivityFamily = "ONLINE_MEETING" if options is MEETING_KINDS else "FOLLOW_UP"
    if meeting == "OFFLINE_MEETING" and options is MEETING_KINDS:
        family = "OFFLINE_MEETING"
    detail = reason if not quote else f"{reason}：{quote}"
    return ChannelResolution(
        status="required",
        family=family,
        kind=None,
        source=None,
        confidence=None,
        quote=quote,
        reason=reason,
        status_label="未识别 · 需要确认",
        source_text=detail,
        options=options,
    )


def _family_unclear(reason: str) -> ChannelResolution:
    return ChannelResolution(
        status="family_unclear",
        family="UNCLEAR",
        kind=None,
        source=None,
        confidence=None,
        quote=None,
        reason=reason,
        status_label="未识别 · 需要确认",
        source_text=reason,
        options=(),
    )


def _follow_quote(text: str, kind: str) -> str | None:
    phrases = {
        CustomerActivityKind.PHONE_FOLLOW_UP: (*_PHONE_PHRASES, "电话"),
        CustomerActivityKind.WECHAT_FOLLOW_UP: _WECHAT_PHRASES,
        CustomerActivityKind.EMAIL_FOLLOW_UP: _EMAIL_PHRASES,
        CustomerActivityKind.VISIT_FOLLOW_UP: _VISIT_PHRASES,
    }[kind]
    lowered = text.lower()
    for phrase in phrases:
        if phrase.lower() in lowered:
            return phrase
    return None


def _meeting_quote(text: str, kind: str) -> str | None:
    phrases = ("线下会议", "现场会议", "线上会议", "视频会议", "腾讯会议", "飞书会议")
    if kind == CustomerActivityKind.ONLINE_MEETING:
        phrases = ("线上会议", "线上交流", "线上沟通", "视频会议", "腾讯会议", "飞书会议", "远程会议")
    for phrase in phrases:
        if phrase in text:
            return phrase
    return kind


def apply_channel_resolution(draft: object, resolution: ChannelResolution) -> object:
    """Copy a follow-up or meeting resolution onto the task draft."""

    from app.services.customer_activity_kinds import get_activity_kind_meta

    origin = None
    if resolution.kind is not None:
        origin = str(get_activity_kind_meta(resolution.kind)["label"])
    return draft.model_copy(
        update={
            "channel_status": None if resolution.status == "family_unclear" else resolution.status,
            "channel_kind": resolution.kind,
            "channel_source": resolution.source,
            "channel_quote": resolution.quote,
            "channel_reason": resolution.reason or None,
            "channel_confidence": resolution.confidence,
            "channel_status_label": resolution.status_label,
            "channel_source_text": resolution.source_text,
            "channel_options": list(resolution.options),
            "channel_origin_label": origin,
        }
    )


def selected_kind(kind: str) -> ChannelResolution:
    """A coarse family the user already picked. Meetings stay switchable."""

    from app.services.customer_activity_kinds import get_activity_kind_meta

    if kind not in MEETING_KINDS and kind not in FOLLOW_UP_KINDS:
        raise ValueError("unknown activity kind")
    label = str(get_activity_kind_meta(kind)["label"])
    family: ActivityFamily = kind if kind in MEETING_KINDS else "FOLLOW_UP"
    options = MEETING_KINDS if kind in MEETING_KINDS else FOLLOW_UP_KINDS
    return ChannelResolution(
        status="recognized",
        family=family,
        kind=kind,
        source="user",
        confidence=None,
        quote=None,
        reason="",
        status_label="已选择",
        source_text=f"你选择：{label}",
        options=options,
    )

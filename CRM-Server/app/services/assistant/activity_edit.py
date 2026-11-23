"""Typed amendments to a frozen activity, without mutating its source evidence."""

# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.
from __future__ import annotations

import re
from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

from pydantic import ValidationError

from app.services.assistant.action_evidence import parse_deadline
from app.services.assistant.activity_channel import FOLLOW_UP_KINDS, MEETING_KINDS, kind_label
from app.services.assistant.contracts import DraftField, TaskDraft
from app.services.assistant.temporal_evidence import StoredMention, resolved_sales_follow_up
from app.utils.time import to_business_naive

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pydantic import JsonValue

EDITABLE_ACTIVITY_FIELDS = frozenset({
    "communication_time", "channel_kind", "participants", "summary", "next_action", "next_follow_time",
})
_TIME_FIELDS = {"communication_time", "next_follow_time"}
_TIME_KEY = "activity_edit_times"
_GROUPS = ("internal", "customer")
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_ISO_DATETIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}(?::[0-9]{2})?(?:Z|[+-][0-9]{2}:[0-9]{2})?")
EditGranularity = Literal["DATE", "DATETIME", "UNKNOWN"]
EditTime = tuple[datetime | None, EditGranularity]


class ActivityEditValidationError(ValueError):
    """A typed edit was not valid for the requested editable field."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(f"{field}: {message}")


def _bundle(content_json: Mapping[str, object]) -> dict[str, object] | None:
    value = content_json.get("temporal_evidence")
    return value if isinstance(value, dict) and value.get("version") == "temporal-evidence-v1" else None


def _meeting(draft: TaskDraft) -> bool:
    return draft.channel_kind in MEETING_KINDS or "key_minutes" in draft.content_json


def editable_activity_channel_options(draft: TaskDraft) -> tuple[str, ...]:
    """Channel edits cannot cross the meeting/follow-up structure boundary."""
    family = MEETING_KINDS if _meeting(draft) else FOLLOW_UP_KINDS
    issued = tuple(kind for kind in draft.channel_options if kind in family)
    return issued or family


def edited_activity_summary(content_json: Mapping[str, object]) -> str | None:
    """The user-authored summary replaces the generated headline, not meeting minutes."""
    value = content_json.get("activity_edit_summary")
    return value if isinstance(value, str) and value else None


def activity_edit_time(content_json: Mapping[str, object], field: str) -> EditTime | None:
    """Return an explicit date/datetime, an explicit clear, or no user override."""
    times = content_json.get(_TIME_KEY)
    value = times.get(field) if isinstance(times, dict) else None
    if not isinstance(value, dict) or value.get("source") != "USER":
        return None
    raw = value.get("resolved_at")
    granularity = value.get("granularity")
    if raw is None and granularity == "UNKNOWN":
        return None, "UNKNOWN"
    if not isinstance(raw, str) or granularity not in ("DATE", "DATETIME"):
        return None
    try:
        return datetime.fromisoformat(raw), granularity
    except ValueError:
        return None


def _resolved_time(at: datetime | None, granularity: str) -> EditTime | None:
    if at is None:
        return None
    if granularity == "DATE":
        return datetime.combine(at.date(), datetime.min.time()), "DATE"
    if granularity == "DATETIME":
        return at, "DATETIME"
    return None


def communication_time_evidence(content_json: Mapping[str, object]) -> EditTime | None:
    """Return the active temporal evidence without applying a user override."""
    bundle = _bundle(content_json)
    if bundle is None:
        return None
    mentions = bundle.get("mentions")
    if isinstance(mentions, list):
        for raw in mentions:
            try:
                mention = StoredMention.model_validate(raw)
            except ValidationError:
                continue
            if (
                mention.communication_time
                and mention.state == "ACTIVE"
                and (resolved_mention := _resolved_time(mention.resolved_at, mention.granularity)) is not None
            ):
                return resolved_mention
    return None


def resolved_communication_time(content_json: Mapping[str, object]) -> EditTime | None:
    """Return the user override or the active communication-time evidence."""
    override = activity_edit_time(content_json, "communication_time")
    return override if override is not None else communication_time_evidence(content_json)


def persisted_communication_time(content_json: Mapping[str, object]) -> EditTime | None:
    """Return the occurrence time, restoring evidence after an explicit clear."""
    override = activity_edit_time(content_json, "communication_time")
    if override is not None and override[0] is not None:
        return override
    return communication_time_evidence(content_json)


def _evidence_time(draft: TaskDraft, field: str) -> EditTime | None:
    if field == "communication_time":
        return resolved_communication_time(draft.content_json)
    override = activity_edit_time(draft.content_json, field)
    if override is not None:
        return override
    bundle = _bundle(draft.content_json)
    if bundle is None:
        return None
    if field == "next_follow_time":
        resolved, granularity = resolved_sales_follow_up(draft)
        return _resolved_time(resolved, granularity)
    return None


def _time_value(draft: TaskDraft, field: str) -> str | None:
    temporal = _evidence_time(draft, field)
    if temporal is not None:
        at, granularity = temporal
        if at is None:
            return None
        return at.date().isoformat() if granularity == "DATE" else at.isoformat(timespec="auto")
    return draft.next_follow_time.value if field == "next_follow_time" else None


def editable_activity_fields(draft: TaskDraft) -> dict[str, JsonValue]:
    """Project only editable values; ``None`` means no current value to correct."""
    contacts = draft.content_json.get("participants")
    participants: dict[str, JsonValue] | None = None
    if isinstance(contacts, dict):
        participants = {}
        for group in _GROUPS:
            names = contacts.get(group)
            participants[group] = [name for name in names if isinstance(name, str)] if isinstance(names, list) else []
    summary = edited_activity_summary(draft.content_json)
    if summary is None:
        minutes = draft.content_json.get("key_minutes")
        head = minutes[0] if isinstance(minutes, list) and minutes else draft.content_json.get("content")
        summary = head[:300] if isinstance(head, str) and head else draft.content.value
    channel = draft.channel_kind
    return {
        "communication_time": _time_value(draft, "communication_time"),
        "channel_kind": channel if draft.channel_status != "required" else None,
        "participants": participants if participants and any(participants.values()) else None,
        "summary": summary,
        "next_action": draft.next_action.value if draft.next_action.status != "EXPLICITLY_NONE" else None,
        "next_follow_time": _time_value(draft, "next_follow_time"),
    }


def _text(field: str, value: object, limit: int, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ActivityEditValidationError(field, "请输入文字。")
    text = value.strip()
    if not text and not optional:
        raise ActivityEditValidationError(field, "此项不能为空。")
    if len(text) > limit:
        raise ActivityEditValidationError(field, f"此项不能超过 {limit} 个字符。")
    return text or None


def _contacts(value: object) -> dict[str, list[str]] | None:
    if value is None:
        return None
    field = "participants"
    if not isinstance(value, dict) or set(value) - set(_GROUPS):
        raise ActivityEditValidationError(field, "仅可提交我方和客户方联系人。")
    result: dict[str, list[str]] = {}
    for group in _GROUPS:
        names = value.get(group, [])
        if not isinstance(names, list) or len(names) > 50:
            raise ActivityEditValidationError(field, "联系人必须为姓名列表，每组最多 50 人。")
        clean_names: list[str] = []
        for name in names:
            text = _text(field, name, 100)
            if text is not None and text not in clean_names:
                clean_names.append(text)
        result[group] = clean_names
    return result if any(result.values()) else None


def _parse_time(field: str, text: str, anchor: datetime | None) -> EditTime:
    try:
        if _ISO_DATE.fullmatch(text):
            return datetime.combine(date.fromisoformat(text), datetime.min.time()), "DATE"
        if _ISO_DATETIME.fullmatch(text):
            return to_business_naive(datetime.fromisoformat(text.replace("Z", "+00:00"))), "DATETIME"
    except ValueError:
        raise ActivityEditValidationError(field, "请输入有效的日期或日期时间。") from None
    if anchor is not None and (resolved := _resolved_time(*parse_deadline(text, anchor=anchor))) is not None:
        return resolved
    raise ActivityEditValidationError(field, "请输入有效的日期或日期时间。")


def _set_time(draft: TaskDraft, field: str, raw: str | None, value: EditTime) -> None:
    old_times = draft.content_json.get(_TIME_KEY)
    times = dict(old_times) if isinstance(old_times, dict) else {}
    at, granularity = value
    times[field] = {
        "value": raw,
        "resolved_at": at.isoformat() if at is not None else None,
        "granularity": granularity,
        "source": "USER",
    }
    draft.content_json[_TIME_KEY] = times
    if field == "next_follow_time":
        draft.next_follow_time = _accepted(raw)
        draft.content_json["next_follow_time_text"] = raw or ""


def _accepted(value: str | None) -> DraftField:
    return DraftField(status="ACCEPTED" if value is not None else "EXPLICITLY_NONE", value=value)


def apply_activity_edits(
    draft: TaskDraft, values: Mapping[str, object], *, anchor: datetime | None = None
) -> tuple[TaskDraft, bool]:
    """Validate the whitelist atomically and copy only materially changed fields."""
    before = editable_activity_fields(draft)
    candidate: TaskDraft | None = None
    for field, raw in values.items():
        if field not in EDITABLE_ACTIVITY_FIELDS:
            raise ActivityEditValidationError(str(field), "此项不能在这里修改。")
        old = before[field]
        if field in _TIME_FIELDS:
            text = _text(field, raw, 200, optional=True)
            # Old cards may hold an already accepted phrase rather than an ISO date.
            if text == old:
                continue
            time_value = _parse_time(field, text, anchor) if text is not None else (None, "UNKNOWN")
            if time_value == _evidence_time(draft, field):
                continue
            candidate = candidate if candidate is not None else draft.model_copy(deep=True)
            _set_time(candidate, field, text, time_value)
        elif field == "participants":
            contacts = _contacts(raw)
            if contacts == old:
                continue
            candidate = candidate if candidate is not None else draft.model_copy(deep=True)
            candidate.content_json[field] = contacts or {group: [] for group in _GROUPS}
            candidate.participants = _accepted(
                "；".join(f"{label}：{'、'.join(contacts[group])}" for group, label in zip(
                    _GROUPS, ("我方", "客户方"), strict=True,
                ) if contacts[group]) if contacts is not None else None
            )
        else:
            limit = {"summary": 300, "next_action": 4000, "channel_kind": 32}[field]
            text = _text(field, raw, limit, optional=field in {"channel_kind", "next_action"})
            if text == old:
                continue
            if field == "channel_kind":
                if text is None or text not in editable_activity_channel_options(draft):
                    raise ActivityEditValidationError(field, "请选择同类活动的沟通方式。")
                candidate = candidate if candidate is not None else draft.model_copy(deep=True)
                candidate.channel_kind = text
                candidate.channel_status = "selected" if old is None else "revised"
                candidate.channel_source = "user"
                candidate.channel_status_label = "已手动修正"
                candidate.channel_source_text = f"你修改为：{kind_label(text)}"
                candidate.channel_options = list(editable_activity_channel_options(draft))
            elif field == "summary":
                candidate = candidate if candidate is not None else draft.model_copy(deep=True)
                candidate.content = _accepted(text)
                candidate.content_json["activity_edit_summary"] = text
                if not _meeting(draft):
                    candidate.content_json["content"] = text
            else:
                candidate = candidate if candidate is not None else draft.model_copy(deep=True)
                candidate.next_action = _accepted(text)
                key = "next_step_summary" if _meeting(draft) else "next_action"
                candidate.content_json[key] = text or ""
                if text and "next_action_absence_reason" in candidate.content_json:
                    candidate.content_json["next_action_absence_reason"] = ""
    return (candidate, True) if candidate is not None else (draft, False)

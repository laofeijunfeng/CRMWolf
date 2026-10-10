"""Server-owned source records and deterministic action-date evidence."""
# Chinese date grammar intentionally accepts full-width punctuation and ideographic zero.
# ruff: noqa: RUF001

from __future__ import annotations

import re
from datetime import datetime, time
from hashlib import sha256
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.utils import time as business_time

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.assistant import AssistantTask
    from app.services.assistant.contracts import TaskDraft

PARSER_VERSION = "assistant-date-v1"
_DAY = (
    r"(?:20\d{2}[-/年]\d{1,2}[-/月]\d{1,2}日?|大后天|后天|明天|今天|今日|"
    r"(?:下|本|这)?(?:周|星期|礼拜)[一二三四五六日天])"
)
_CLOCK = (
    r"(?:(?:上午|下午|晚上|中午|早上)?(?:\d{1,2}[:：]\d{2}(?::\d{2})?|"
    r"[零〇一二两三四五六七八九十\d]{1,3}[点时](?:半|[零〇一二两三四五六七八九十\d]{1,3}分?)?))"
)
_DATE = re.compile(rf"{_DAY}(?:(?:[ T]|的)?{_CLOCK})?(?:Z|[+-]\d{{2}}:\d{{2}})?")
_CORRECTION = re.compile(r"更正|纠正|不是|改为|改到|应为|而是")
_REPLACEMENT = re.compile(r"改为|改到|应为|而是")
_UNCERTAIN = re.compile(r"大概|大约|左右|前后|差不多|可能|也许|有空|暂定|争取|看情况|约")
_NEGATION = re.compile(r"不(?:会|再|安排|准备|打算|是)|取消|无需|不用|暂无")


class SourceSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    segment_id: str
    turn_id: str | None = None
    recorded_at: datetime
    timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"
    text: str


class ActionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    revision: int = Field(ge=1)
    state: Literal["ACTIVE", "SUPERSEDED", "EXPLICITLY_NONE"] = "ACTIVE"
    superseded_by: str | None = None
    action: str
    owner: str
    due_date: str | None = None
    segment_id: str | None = None
    evidence_quote: str = ""
    quote_start: int | None = None
    quote_end: int | None = None
    due_at_text: str | None = None
    anchor_at: datetime | None = None
    timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"
    parser_version: Literal["assistant-date-v1"] = PARSER_VERSION
    granularity: Literal["DATE", "DATETIME", "UNKNOWN"] = "UNKNOWN"
    resolution_status: Literal["RESOLVED", "AMBIGUOUS", "UNRESOLVED", "EXPLICITLY_NONE"] = "UNRESOLVED"
    due_at: datetime | None = None


def append_source(db: Session, task: AssistantTask, draft: TaskDraft, text: str) -> bool:
    """Accept each durable input once; identical text in another turn is a new event."""
    text = text.strip()
    if not text:
        return False
    turn_id = None
    anchor = business_time.business_now()
    if task.active_turn_id is not None:
        from app.models.assistant_turn import AssistantTurn

        turn = db.get(AssistantTurn, task.active_turn_id)
        if turn is None or (turn.task_id, turn.team_id, turn.user_id) != (task.id, task.team_id, task.user_id):
            raise ValueError("source turn does not belong to task")
        if (
            turn.input_json.get("kind") not in {"text", "submit_field"}
            or str(turn.input_json.get("text") or "").strip() != text
        ):
            raise ValueError("source text is not the accepted turn input")
        turn_id, anchor = turn.public_id, turn.created_time
    if any(record.turn_id == turn_id and record.text == text for record in draft.source_records):
        return False
    if turn_id is not None or text not in draft.source_segments:
        draft.source_segments.append(text)
    digest = sha256(f"{task.public_id}:{turn_id}:{len(draft.source_records)}:{text}".encode()).hexdigest()[:20]
    draft.source_records.append(
        SourceSegment(segment_id=f"seg_{digest}", turn_id=turn_id, recorded_at=anchor, text=text)
    )
    return True


def _number(value: str) -> int:
    if value.isdigit():
        return int(value)
    digits = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if "十" in value:
        left, right = value.split("十", 1)
        return digits.get(left, 1) * 10 + digits.get(right, 0)
    return digits[value]


def parse_deadline(text: str, *, anchor: datetime) -> tuple[datetime | None, str]:
    """No default hour for task dates; ambiguous or invalid expressions stay unresolved."""
    value = text.strip()
    if _DATE.fullmatch(value) is None:
        return None, "UNKNOWN"
    if re.match(r"20\d{2}-\d{2}-\d{2}[ T]\d{2}:\d{2}", value):
        try:
            return business_time.to_business_naive(datetime.fromisoformat(value.replace("Z", "+00:00"))), "DATETIME"
        except ValueError:
            return None, "UNKNOWN"
    day_match = re.match(_DAY, value)
    if day_match is None:
        return None, "UNKNOWN"
    day_text = day_match.group()
    day = business_time.resolve_follow_up_time(day_text, base=business_time.to_business_naive(anchor))
    if day is None:
        return None, "UNKNOWN"
    clock = value[day_match.end() :].lstrip(" T的")
    if not clock:
        return datetime.combine(day.date(), time.min), "DATE"
    match = re.fullmatch(
        r"(上午|下午|晚上|中午|早上)?(?:(\d{1,2})[:：](\d{2})(?::(\d{2}))?|([零〇一二两三四五六七八九十\d]{1,3})[点时](半|[零〇一二两三四五六七八九十\d]{1,3}分?)?)",
        clock,
    )
    if match is None:
        return None, "UNKNOWN"
    try:
        hour = int(match[2]) if match[2] else _number(match[5])
        minute = (
            int(match[3]) if match[3] else 30 if match[6] == "半" else _number(match[6].rstrip("分")) if match[6] else 0
        )
        if match[1] in {"上午", "早上", "下午", "晚上", "中午"} and not 1 <= hour <= 12:
            return None, "UNKNOWN"
        if match[1] in {"下午", "晚上"} and hour < 12:
            hour += 12
        elif match[1] in {"上午", "早上"} and hour == 12:
            hour = 0
        elif match[1] == "中午" and hour < 11:
            return None, "UNKNOWN"
        return day.replace(hour=hour, minute=minute, second=int(match[4] or 0)), "DATETIME"
    except (ValueError, KeyError):
        return None, "UNKNOWN"


def _clauses(text: str) -> list[tuple[int, int, str]]:
    clauses = []
    for sentence in re.finditer(r"[^。；;\n！？!?]+", text):
        for part in re.finditer(r"[^，,]+", sentence.group()):
            start, end = sentence.start() + part.start(), sentence.start() + part.end()
            quote = part.group()
            if (
                clauses
                and clauses[-1][0] >= sentence.start()
                and clauses[-1][1] == start - 1
                and (
                    _DATE.fullmatch(quote.strip())
                    or re.fullmatch(rf"(?:{_REPLACEMENT.pattern})\s*(?:{_DATE.pattern})", quote.strip())
                )
            ):
                prior_start = clauses[-1][0]
                clauses[-1] = (prior_start, end, text[prior_start:end])
            else:
                clauses.append((start, end, quote))
    return clauses


def _owned_action(quote: str, owner: str, action: str) -> bool:
    """Dates may separate the subject and verb; unrelated subjects may not."""
    if not owner or not action:
        return False
    without_dates = re.sub(r"\s+", "", _DATE.sub("", quote))
    pattern = (
        rf"(?:^|[，,：:]|由|决定|安排|承诺|确认){re.escape(owner)}"
        rf"(?:(?:将|会|负责|计划|要|在)|取消|不(?:会|再|安排|准备|打算|是)|无需|不用|暂无)*{re.escape(action)}"
    )
    return re.search(pattern, without_dates) is not None


def is_action_deadline_correction(text: str, owner: str, action: str) -> bool:
    """Only an explicit replacement in this action's own clause can revise it."""
    return any(
        _owned_action(quote, owner, action) and _CORRECTION.search(quote) and _REPLACEMENT.search(quote)
        for _, _, quote in _clauses(text)
    )


def _follow_up_action(content: dict[str, object], records: list[SourceSegment]) -> dict[str, object] | None:
    title = str(content.get("next_action") or "").strip()
    if not title:
        return None
    normalized = re.sub(r"\s+", "", _DATE.sub("", title))
    subject = re.match(r"^(本人|我)(?:将|会|负责|计划|要|在)?(.+)$", normalized)
    if subject:
        owner, action = subject.groups()
    else:
        action = normalized
        owner = next(
            (
                alias
                for record in reversed(records)
                for _, _, quote in _clauses(record.text)
                for alias in ("我", "本人")
                if _owned_action(quote, alias, action)
            ),
            "",
        )
    return {
        "item_id": "act_" + sha256(f"{owner}:{action}".encode()).hexdigest()[:16],
        "owner": owner,
        "action": action,
        "due_date": content.get("next_follow_time_text") or None,
    }


def _resolve_action(action: dict[str, object], records: list[SourceSegment], revision: int) -> ActionEvidence:
    title, owner = str(action.get("action") or "").strip(), str(action.get("owner") or "").strip()
    result = ActionEvidence(
        action_id=str(action["item_id"]),
        revision=revision,
        action=title,
        owner=owner,
        due_date=str(action["due_date"]) if action.get("due_date") else None,
    )
    if not title or not owner or not result.due_date:
        return result
    for record in reversed(records):
        matching = [
            (start, end, quote) for start, end, quote in _clauses(record.text) if _owned_action(quote, owner, title)
        ]
        if not matching:
            continue
        if len(matching) != 1:
            return result.model_copy(update={"resolution_status": "AMBIGUOUS"})
        start, end, quote = matching[0]
        result.segment_id, result.evidence_quote = record.segment_id, quote
        result.quote_start, result.quote_end, result.anchor_at = start, end, record.recorded_at
        correction = is_action_deadline_correction(quote, owner, title)
        effective = _REPLACEMENT.split(quote)[-1] if correction else quote
        dates = list(_DATE.finditer(effective))
        if len(dates) != 1 or _UNCERTAIN.search(effective):
            result.resolution_status = "AMBIGUOUS" if dates else "UNRESOLVED"
            return result
        date = dates[0]
        suffix = effective[date.end() :].lstrip()
        if re.match(
            r"上午|下午|晚上|中午|早上|[零〇一二两三四五六七八九十\d:：]|前|后|之|以|内|间|至|到|起", suffix
        ) or (not correction and _NEGATION.search(quote)):
            return result
        result.due_at_text = date.group()
        resolved, granularity = parse_deadline(result.due_at_text, anchor=record.recorded_at)
        canonical_due, canonical_granularity = parse_deadline(result.due_date, anchor=record.recorded_at)
        if resolved is None or canonical_due != resolved or canonical_granularity != granularity:
            return result
        result.due_at, result.granularity, result.resolution_status = resolved, granularity, "RESOLVED"
        return result
    return result


def _withdrawn_after(evidence: ActionEvidence, records: list[SourceSegment]) -> bool:
    """Later explicit withdrawals override a fixed anchor, not ordinary supplements."""
    index = next((index for index, record in enumerate(records) if record.segment_id == evidence.segment_id), None)
    if index is None:
        return False
    return any(
        _owned_action(quote, evidence.owner, evidence.action)
        and (_NEGATION.search(quote) or is_action_deadline_correction(quote, evidence.owner, evidence.action))
        for record in records[index + 1 :]
        for _, _, quote in _clauses(record.text)
    )


def reconcile_action_evidence(draft: TaskDraft, kind: str) -> None:
    """Eligibility belongs to current canonical actions, never historical quotes alone."""
    history = [ActionEvidence.model_validate(item) for item in draft.content_json.get("action_evidence", [])]
    if draft.next_action.status == "EXPLICITLY_NONE":
        for item in history:
            if item.state == "ACTIVE":
                item.state, item.resolution_status, item.due_at = "EXPLICITLY_NONE", "EXPLICITLY_NONE", None
        if kind != "FOLLOW_UP":
            draft.content_json["action_items"] = []
    else:
        if kind == "FOLLOW_UP":
            draft.content_json["next_action"] = draft.next_action.value or ""
            draft.content_json["next_follow_time_text"] = draft.next_follow_time.value or ""
            action = _follow_up_action(draft.content_json, draft.source_records)
            actions = [action] if action else []
        else:
            actions = draft.content_json.get("action_items", [])
        active_ids = {action.get("item_id") for action in actions if isinstance(action, dict)}
        for item in history:
            if item.state == "ACTIVE" and item.action_id not in active_ids:
                item.state = "SUPERSEDED"
        for action in actions:
            if not isinstance(action, dict) or not action.get("item_id"):
                continue
            prior = next(
                (item for item in reversed(history) if item.action_id == action["item_id"] and item.state == "ACTIVE"),
                None,
            )
            if (
                prior is not None
                and (prior.action, prior.owner, prior.due_date)
                == (action["action"], action.get("owner", ""), action.get("due_date"))
                and not _withdrawn_after(prior, draft.source_records)
            ):
                continue
            revision = 1 + max((item.revision for item in history if item.action_id == action["item_id"]), default=0)
            evidence = _resolve_action(action, draft.source_records, revision)
            if prior is not None:
                prior.state, prior.superseded_by = "SUPERSEDED", f"{evidence.action_id}:{revision}"
            history.append(evidence)
    draft.content_json["action_evidence"] = [item.model_dump(mode="json") for item in history]
    draft.content_json["source_records"] = [record.model_dump(mode="json") for record in draft.source_records]


def validate_action_evidence(
    content: dict[str, object], action_id: str, *, source_content: str
) -> ActionEvidence | None:
    """Jointly verify current canonical identity, immutable source and fixed parser result."""
    from pydantic import ValidationError

    try:
        if content.get("next_action_absence_reason"):
            return None
        records = [SourceSegment.model_validate(record) for record in content.get("source_records", [])]
        if "next_action" in content:
            current = _follow_up_action(content, records)
            actions = [current] if current is not None else []
        else:
            actions = content.get("action_items", [])
        matching = [item for item in actions if isinstance(item, dict) and item.get("item_id") == action_id]
        active = [
            ActionEvidence.model_validate(item)
            for item in content.get("action_evidence", [])
            if isinstance(item, dict) and item.get("action_id") == action_id and item.get("state") == "ACTIVE"
        ]
        if len(matching) != 1 or len(active) != 1 or active[0].resolution_status != "RESOLVED":
            return None
        evidence, action = active[0], matching[0]
        if (action.get("action"), action.get("owner"), action.get("due_date")) != (
            evidence.action,
            evidence.owner,
            evidence.due_date,
        ):
            return None
        sources = [record for record in records if record.segment_id == evidence.segment_id]
        if len(sources) != 1 or sources[0].text not in source_content:
            return None
        if _withdrawn_after(evidence, records):
            return None
        recomputed = _resolve_action(action, sources, evidence.revision)
        return evidence if recomputed == evidence else None
    except (ValidationError, ValueError, TypeError, KeyError):
        return None

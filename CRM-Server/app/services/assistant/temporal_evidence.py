"""Server-owned temporal evidence for Assistant 2.0.

The model may quote a time and name its role. Canonical dates, month
candidates and sales binding are decided here from the segment anchor.
"""

# Chinese date grammar intentionally accepts the approved user-facing sentences.
# ruff: noqa: RUF001

from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.assistant.contracts import DraftField, TaskDraft

PROTOCOL_VERSION = "temporal-evidence-v1"
PARSER_VERSION: Literal["assistant-date-v2"] = "assistant-date-v2"
POLICY_VERSION: Literal["bare-day-v1"] = "bare-day-v1"
TimeKind = Literal[
    "EXPLICIT_DATE",
    "MONTH_DAY",
    "DAY_OF_MONTH",
    "MONTH_END",
    "RELATIVE_DAY",
    "RELATIVE_WEEK",
    "RELATIVE_MONTH",
    "RELATIVE_WEEKDAY",
    "UNKNOWN",
]
TimeRole = Literal["CUSTOMER_COMMITMENT", "CUSTOMER_ACTION", "SALES_FOLLOW_UP", "INTERNAL_ACTION", "OTHER"]
Resolution = Literal["RESOLVED", "AMBIGUOUS", "UNRESOLVED", "EXPLICITLY_NONE"]
EvidenceState = Literal["ACTIVE", "SUPERSEDED", "EXPLICITLY_NONE"]
ActionStatus = Literal["PLANNED", "COMPLETED", "COMMITTED", "UNKNOWN"]
_UNCERTAIN = re.compile(r"大概|大约|左右|前后|差不多|可能|也许")
_REPLACEMENT = re.compile(r"改为|改到|应为|而是")
_CLOCK = re.compile(
    r"(?:[的\s]*)(?:(上午|下午|晚上|中午|早上)?(?:(\d{1,2})[:：](\d{2})(?::(\d{2}))?"
    r"|([零〇一二两三四五六七八九十\d]{1,3})[点时](半|[零〇一二两三四五六七八九十\d]{1,3}分?)?))"
)
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("RELATIVE_MONTH", re.compile(r"下个?月\s*([0-9]{1,2})\s*[号日]")),
    ("MONTH_END", re.compile(r"下个?月底|下月末|本月底|这个月底|这个月末|本月末|月底")),
    ("MONTH_DAY", re.compile(r"(?:(20\d{2})\s*年\s*)?([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*[号日]")),
    ("EXPLICIT_DATE", re.compile(r"20\d{2}[-/年]\d{1,2}[-/月]\d{1,2}日?")),
    ("RELATIVE_WEEKDAY", re.compile(r"(?:下|本|这)?(?:周|星期|礼拜)[一二三四五六日天]")),
    ("RELATIVE_DAY", re.compile(r"大后天|后天|明天|今天|今日")),
    ("DAY_OF_MONTH", re.compile(r"([0-9]{1,2})\s*[号日]")),
)
_WEEKDAYS = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


class TemporalContractError(ValueError):
    """Model evidence contradicted the source text or the closed vocabulary."""


class FoundSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: TimeKind
    start: int
    end: int
    raw_text: str
    groups: tuple[str | None, ...] = ()


class StoredMention(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mention_id: str
    raw_text: str
    source_segment_id: str
    quote_start: int
    quote_end: int
    kind: TimeKind
    role: TimeRole
    owner: str = ""
    action_id: str | None = None
    year: int | None = None
    month: int | None = None
    day: int | None = None
    hour: int | None = None
    minute: int | None = None
    granularity: Literal["DATE", "DATETIME", "UNKNOWN"] = "UNKNOWN"
    confidence: float = 0
    anchor_at: datetime
    timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"
    parser_version: Literal["assistant-date-v2"] = PARSER_VERSION
    policy_version: Literal["bare-day-v1"] = POLICY_VERSION
    resolution_status: Resolution = "UNRESOLVED"
    resolved_at: datetime | None = None
    ambiguity_reason: str | None = None
    correction_of: str | None = None
    state: EvidenceState = "ACTIVE"
    candidates: list[str] = Field(default_factory=list)


class StoredAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    revision: int = 1
    state: EvidenceState = "ACTIVE"
    owner_role: Literal["CUSTOMER", "SALES", "INTERNAL", "OTHER"]
    owner_text: str = ""
    action_text: str
    temporal_mention_id: str | None = None
    source_segment_id: str
    evidence_quote: str
    quote_start: int
    quote_end: int
    action_status: ActionStatus = "UNKNOWN"


def find_time_spans(text: str) -> list[FoundSpan]:
    """Return non-overlapping time spans. Longer matches win over inner ones."""

    found: list[FoundSpan] = []
    for kind, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            end = _extend_clock(text, match.end())
            found.append(
                FoundSpan(
                    kind=kind,  # type: ignore[arg-type]
                    start=match.start(),
                    end=end,
                    raw_text=text[match.start() : end],
                    groups=tuple(match.groups()),
                )
            )
    found.sort(key=lambda item: (item.start, -(item.end - item.start)))
    accepted: list[FoundSpan] = []
    cursor = -1
    for item in found:
        if item.start < cursor:
            continue
        if accepted and item.start < accepted[-1].end:
            continue
        accepted.append(item)
        cursor = item.end
    return accepted


def ensure_mentions_cover_source(text: str, mentions: list[object]) -> None:
    """Production structuring must quote every time the server can locate."""

    spans = find_time_spans(text)
    if not spans:
        return
    covered = {_mention_span(text, item) for item in mentions}
    missing = [span.raw_text for span in spans if (span.start, span.end) not in covered]
    if missing or len(mentions) != len(spans):
        raise TemporalContractError("temporal mentions do not cover the source")


def attach_model_evidence(
    draft: TaskDraft,
    *,
    segment_id: str,
    segment_text: str,
    anchor: datetime,
    mentions: list[object],
    actions: list[object],
) -> None:
    """Validate one segment and store protocol v1 beside the canonical draft."""

    if not mentions and not actions:
        return
    spans = find_time_spans(segment_text)
    built_mentions: list[StoredMention] = []
    built_actions: list[StoredAction] = []
    action_ids: dict[str, str] = {}
    for item in actions:
        action = _read_action(item)
        quote = _exact_slice(segment_text, action.quote_start, action.quote_end, action.evidence_quote)
        identity = f"{action.owner_role}:{action.action_text}:{action.quote_start}:{action.quote_end}"
        action_id = "act_" + sha256(identity.encode()).hexdigest()[:16]
        action_ids[action.action_ref] = action_id
        built_actions.append(
            StoredAction(
                action_id=action_id,
                owner_role=action.owner_role,
                owner_text=action.owner_text,
                action_text=action.action_text,
                source_segment_id=segment_id,
                evidence_quote=quote,
                quote_start=action.quote_start,
                quote_end=action.quote_end,
                action_status=action.action_status,
            )
        )
    used: set[tuple[int, int]] = set()
    for item in mentions:
        mention = _read_mention(item)
        start, end = _snap_span(segment_text, mention)
        if (start, end) in used:
            raise TemporalContractError("duplicate temporal span")
        used.add((start, end))
        found = next((span for span in spans if span.start == start and span.end == end), None)
        if found is None or found.kind != mention.kind:
            raise TemporalContractError("temporal mention does not match a source span")
        linked_id = action_ids.get(mention.action_ref) if mention.action_ref else None
        if mention.action_ref and linked_id is None:
            raise TemporalContractError("temporal mention points at an unknown action")
        stored = _resolve_span(
            found,
            segment_text=segment_text,
            segment_id=segment_id,
            anchor=anchor,
            action_id=linked_id,
            model_role=mention.role,
            model_owner=mention.owner,
            confidence=mention.confidence,
        )
        built_mentions.append(stored)
    if len(used) != len(spans):
        raise TemporalContractError("temporal mentions do not cover the source")
    _link_actions(built_mentions, built_actions)
    _supersede_replacements(segment_text, built_mentions, built_actions)
    previous = _bundle(draft)
    merged_mentions, merged_actions = _merge_history(previous, built_mentions, built_actions)
    draft.content_json["temporal_evidence"] = {
        "version": PROTOCOL_VERSION,
        "mentions": [item.model_dump(mode="json") for item in merged_mentions],
        "actions": [item.model_dump(mode="json") for item in merged_actions],
    }
    project_draft(draft)


def project_draft(draft: TaskDraft) -> None:
    """Refresh slots and card strings from ACTIVE evidence. Does not parse again."""

    bundle = _bundle(draft)
    if bundle is None:
        return
    raw_mentions, raw_actions = bundle
    mentions = [_stored_mention(item) for item in raw_mentions]
    actions = [_stored_action(item) for item in raw_actions]
    commitments = []
    for mention in mentions:
        if mention.state != "ACTIVE" or mention.role != "CUSTOMER_COMMITMENT":
            continue
        action = _action_for(mention, actions)
        owner = mention.owner or (action.owner_text if action else "")
        verb = action.action_text if action else ""
        text = _sentence(f"{owner}预计{mention.raw_text}{verb}")
        commitments.append(
            {
                "text": text,
                "mention_id": mention.mention_id,
                "resolved_on": mention.resolved_at.date().isoformat() if mention.resolved_at else None,
                "granularity": mention.granularity,
                "role": mention.role,
            }
        )
    draft.content_json["customer_commitments"] = commitments
    sales = _primary_sales(mentions, actions)
    notices: list[str] = []
    sales_text = ""
    if sales is not None and not isinstance(sales, list):
        sales_mention, sales_action = sales
        if draft.next_action.status not in {"ACCEPTED", "EXPLICITLY_NONE"}:
            draft.next_action = DraftField(status="CANDIDATE", value=sales_action.action_text)
            draft.content_json["next_action"] = sales_action.action_text
        if sales_mention is None:
            if draft.next_follow_time.status not in {"ACCEPTED", "EXPLICITLY_NONE"}:
                draft.next_follow_time = DraftField(status="MISSING")
            draft.content_json["next_follow_time_text"] = ""
            notices.append("已识别下一步动作，但未指定跟进日期；如需记录日期，请补充日期。")
            sales_text = _sentence(f"下一步：{sales_action.action_text}")
        elif sales_mention.resolution_status == "RESOLVED" and sales_mention.resolved_at is not None:
            if draft.next_follow_time.status not in {"ACCEPTED", "EXPLICITLY_NONE"}:
                draft.next_follow_time = DraftField(status="CANDIDATE", value=sales_mention.raw_text)
            draft.content_json["next_follow_time_text"] = sales_mention.raw_text
            label = f"{sales_mention.resolved_at.month}月{sales_mention.resolved_at.day}号"
            sales_text = _sentence(f"你将在{label}{sales_action.action_text}")
            if sales_mention.granularity == "DATE":
                day = sales_mention.resolved_at.date().isoformat()
                notices.append(f"已识别下次跟进日期为{day}，未指定具体时刻。")
        else:
            draft.content_json["next_follow_time_text"] = sales_mention.raw_text
            if draft.next_follow_time.status not in {"ACCEPTED", "EXPLICITLY_NONE"}:
                draft.next_follow_time = DraftField(status="CANDIDATE", value=sales_mention.raw_text)
    elif _commitment_only(mentions, actions):
        if draft.next_action.status not in {"ACCEPTED", "EXPLICITLY_NONE"}:
            draft.next_action = DraftField(status="MISSING")
            draft.content_json["next_action"] = ""
        if draft.next_follow_time.status not in {"ACCEPTED", "EXPLICITLY_NONE"}:
            draft.next_follow_time = DraftField(status="MISSING")
        draft.content_json["next_follow_time_text"] = ""
    draft.content_json["sales_follow_up_text"] = sales_text
    draft.content_json["temporal_notices"] = notices


def temporal_waiting(draft: TaskDraft) -> dict[str, object] | None:
    """Return the single blocking choice, or None when confirmation may proceed."""

    bundle = _bundle(draft)
    if bundle is None:
        return None
    raw_mentions, raw_actions = bundle
    mentions = [item for item in (_stored_mention(raw) for raw in raw_mentions) if item.state == "ACTIVE"]
    actions = [item for item in (_stored_action(raw) for raw in raw_actions) if item.state == "ACTIVE"]
    unresolved_roles = [item for item in mentions if item.ambiguity_reason == "ROLE"]
    if len(unresolved_roles) >= 2:
        left, right = unresolved_roles[0], unresolved_roles[1]
        return {
            "reason": "ROLE",
            "prompt": _role_prompt(left.raw_text, right.raw_text),
            "candidates": [
                {
                    "id": f"role:{left.mention_id}:customer",
                    "label": f"{left.raw_text}是客户完成，{right.raw_text}是我下次联系",
                },
                {
                    "id": f"role:{left.mention_id}:sales",
                    "label": f"{left.raw_text}是我下次联系，{right.raw_text}是客户完成",
                },
            ],
        }
    ambiguous = next((item for item in mentions if item.resolution_status == "AMBIGUOUS" and item.candidates), None)
    if ambiguous is not None:
        day = ambiguous.day or 0
        return {
            "reason": "MONTH",
            "prompt": _month_prompt(ambiguous.raw_text, day),
            "candidates": [
                {"id": f"{ambiguous.mention_id}:{index}", "label": _month_label(index, day)}
                for index, _value in enumerate(ambiguous.candidates)
            ],
        }
    vague = next(
        (
            item
            for item in mentions
            if item.resolution_status in {"AMBIGUOUS", "UNRESOLVED"} and not item.candidates
        ),
        None,
    )
    if vague is not None:
        return {
            "reason": "DATE",
            "prompt": f"“{vague.raw_text}”无法确定为唯一日期，请补充具体日期。",
            "candidates": [],
        }
    sales = _primary_sales(mentions, actions)
    if isinstance(sales, list):
        return {
            "reason": "PRIMARY",
            "prompt": "请确认哪一项是你的下一步。",
            "candidates": [
                {"id": f"primary:{action.action_id}", "label": action.action_text} for _mention, action in sales
            ],
        }
    return None


def apply_temporal_choice(draft: TaskDraft, choice_id: str) -> None:
    """Apply one server-issued choice id. Unknown ids fail closed."""

    bundle = _bundle(draft)
    if bundle is None:
        raise TemporalContractError("temporal choice without evidence")
    raw_mentions, raw_actions = bundle
    mentions = [_stored_mention(item) for item in raw_mentions]
    actions = [_stored_action(item) for item in raw_actions]
    if choice_id.startswith("primary:"):
        action_id = choice_id.removeprefix("primary:")
        if not any(item.action_id == action_id and item.state == "ACTIVE" for item in actions):
            raise TemporalContractError("unknown temporal choice")
        for item in actions:
            if item.owner_role == "SALES" and item.action_id != action_id and item.state == "ACTIVE":
                item.state = "SUPERSEDED"
        _write_bundle(draft, mentions, actions)
        project_draft(draft)
        return
    if choice_id.startswith("role:"):
        _apply_role_choice(choice_id, mentions)
        _write_bundle(draft, mentions, actions)
        project_draft(draft)
        return
    mention_id, _, index_text = choice_id.rpartition(":")
    if not index_text.isdigit():
        raise TemporalContractError("unknown temporal choice")
    mention = next((item for item in mentions if item.mention_id == mention_id and item.state == "ACTIVE"), None)
    if mention is None or int(index_text) >= len(mention.candidates):
        raise TemporalContractError("unknown temporal choice")
    chosen = datetime.fromisoformat(mention.candidates[int(index_text)])
    mention.year, mention.month, mention.day = chosen.year, chosen.month, chosen.day
    mention.resolved_at = chosen
    mention.granularity = "DATE"
    mention.resolution_status = "RESOLVED"
    mention.ambiguity_reason = None
    mention.candidates = []
    _write_bundle(draft, mentions, actions)
    project_draft(draft)


def commitment_only(draft: TaskDraft) -> bool:
    bundle = _bundle(draft)
    if bundle is None:
        return False
    raw_mentions, raw_actions = bundle
    mentions = [_stored_mention(item) for item in raw_mentions]
    actions = [_stored_action(item) for item in raw_actions]
    return _commitment_only(mentions, actions)


def resolved_sales_follow_up(draft: TaskDraft) -> tuple[datetime | None, str]:
    """Canonical sales instant for confirmation. DATE stays at midnight."""

    bundle = _bundle(draft)
    if bundle is None:
        raise TemporalContractError("missing temporal evidence")
    raw_mentions, raw_actions = bundle
    mentions = [_stored_mention(item) for item in raw_mentions]
    actions = [_stored_action(item) for item in raw_actions]
    sales = _primary_sales(mentions, actions)
    if sales is None or isinstance(sales, list):
        return None, "UNKNOWN"
    mention, _action = sales
    if mention is None or mention.resolved_at is None or mention.resolution_status != "RESOLVED":
        return None, "UNKNOWN"
    return mention.resolved_at, mention.granularity


def sales_evidence_overlay(draft: TaskDraft) -> dict[str, object] | None:
    """Legacy action evidence for the one resolved sales follow-up, if any."""

    bundle = _bundle(draft)
    if bundle is None:
        return None
    raw_mentions, raw_actions = bundle
    mentions = [_stored_mention(item) for item in raw_mentions]
    actions = [_stored_action(item) for item in raw_actions]
    sales = _primary_sales(mentions, actions)
    if sales is None or isinstance(sales, list):
        return None
    mention, action = sales
    if mention is None or mention.resolution_status != "RESOLVED" or mention.resolved_at is None:
        return None
    if action.owner_role != "SALES":
        return None
    return {
        "action_id": action.action_id,
        "revision": action.revision,
        "state": "ACTIVE",
        "action": action.action_text,
        "owner": "我",
        "due_date": mention.raw_text,
        "segment_id": mention.source_segment_id,
        "evidence_quote": action.evidence_quote,
        "quote_start": action.quote_start,
        "quote_end": action.quote_end,
        "due_at_text": mention.raw_text,
        "anchor_at": mention.anchor_at,
        "timezone": "Asia/Shanghai",
        "parser_version": PARSER_VERSION,
        "granularity": mention.granularity,
        "resolution_status": "RESOLVED",
        "due_at": mention.resolved_at,
    }


def _resolve_span(
    found: FoundSpan,
    *,
    segment_text: str,
    segment_id: str,
    anchor: datetime,
    action_id: str | None,
    model_role: TimeRole,
    model_owner: str,
    confidence: float,
) -> StoredMention:
    role, _action_status, reason = _bind_role(segment_text, found, model_role)
    owner = model_owner or _owner_from_clause(segment_text, found, role)
    base = StoredMention(
        mention_id="tm_" + sha256(f"{segment_id}:{found.start}:{found.end}:{found.raw_text}".encode()).hexdigest()[:16],
        raw_text=found.raw_text,
        source_segment_id=segment_id,
        quote_start=found.start,
        quote_end=found.end,
        kind=found.kind,
        role=role,
        owner=owner,
        action_id=action_id,
        confidence=confidence,
        anchor_at=anchor,
        ambiguity_reason=reason,
    )
    if reason == "UNCERTAIN":
        return base.model_copy(update={"resolution_status": "AMBIGUOUS", "granularity": "UNKNOWN"})
    resolved = _resolve_kind(found, anchor, segment_text)
    if reason == "ROLE":
        resolved["ambiguity_reason"] = "ROLE"
        if resolved.get("resolution_status") == "RESOLVED":
            resolved["resolution_status"] = "AMBIGUOUS"
    return base.model_copy(update=resolved)


def _resolve_kind(found: FoundSpan, anchor: datetime, segment_text: str) -> dict[str, object]:
    del segment_text
    hour_minute = _clock_in_text(found.raw_text)
    kind = found.kind
    if kind == "MONTH_END":
        month_shift = 1 if found.raw_text.startswith("下") else 0
        year, month = _shift_month(anchor.year, anchor.month, month_shift)
        day = calendar.monthrange(year, month)[1]
        return _dated(year, month, day, hour_minute, anchor)
    if kind == "DAY_OF_MONTH":
        day = int(found.groups[0] or "0")
        options = _bare_day_candidates(day, anchor)
        if len(options) == 1:
            chosen = options[0]
            return _dated(chosen.year, chosen.month, chosen.day, hour_minute, anchor)
        if len(options) > 1:
            return {
                "day": day,
                "resolution_status": "AMBIGUOUS",
                "ambiguity_reason": "MONTH",
                "granularity": "UNKNOWN",
                "candidates": [item.isoformat() for item in options],
            }
        return {"day": day, "resolution_status": "UNRESOLVED", "ambiguity_reason": "MONTH", "granularity": "UNKNOWN"}
    if kind == "RELATIVE_MONTH":
        day = int(found.groups[0] or "0")
        year, month = _shift_month(anchor.year, anchor.month, 1)
        if day < 1 or day > calendar.monthrange(year, month)[1]:
            return {"day": day, "resolution_status": "UNRESOLVED", "granularity": "UNKNOWN"}
        return _dated(year, month, day, hour_minute, anchor)
    if kind == "MONTH_DAY":
        year_text, month_text, day_text = (*found.groups, None, None, None)[:3]
        month, day = int(month_text or 0), int(day_text or 0)
        year = int(year_text) if year_text else anchor.year
        if year_text is None and (month, day) < (anchor.month, anchor.day):
            year += 1
        if month < 1 or month > 12 or day < 1 or day > calendar.monthrange(year, month)[1]:
            return {"month": month, "day": day, "resolution_status": "UNRESOLVED", "granularity": "UNKNOWN"}
        return _dated(year, month, day, hour_minute, anchor)
    if kind == "RELATIVE_DAY":
        offsets = {"今天": 0, "今日": 0, "明天": 1, "后天": 2, "大后天": 3}
        key = next(name for name in offsets if found.raw_text.startswith(name))
        target = anchor.date() + timedelta(days=offsets[key])
        return _dated(target.year, target.month, target.day, hour_minute, anchor)
    if kind == "RELATIVE_WEEKDAY":
        prefix = found.raw_text[0] if found.raw_text[0] in {"下", "本", "这"} else ""
        day_name = found.raw_text[-1]
        offset = _WEEKDAYS[day_name] - anchor.weekday()
        if prefix == "下" or (prefix == "" and offset < 0):
            offset += 7
        target = anchor.date() + timedelta(days=offset)
        return _dated(target.year, target.month, target.day, hour_minute, anchor)
    if kind == "EXPLICIT_DATE":
        match = re.match(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})", found.raw_text)
        if match is None:
            return {"resolution_status": "UNRESOLVED", "granularity": "UNKNOWN"}
        year, month, day = (int(part) for part in match.groups())
        try:
            datetime(year, month, day)
        except ValueError:
            return {"resolution_status": "UNRESOLVED", "granularity": "UNKNOWN"}
        return _dated(year, month, day, hour_minute, anchor)
    return {"resolution_status": "UNRESOLVED", "granularity": "UNKNOWN", "kind": "UNKNOWN"}


def _dated(
    year: int, month: int, day: int, clock: tuple[int, int] | None, anchor: datetime
) -> dict[str, object]:
    del anchor
    if clock is None:
        resolved = datetime(year, month, day)
        granularity: Literal["DATE", "DATETIME"] = "DATE"
        hour = minute = None
    else:
        hour, minute = clock
        resolved = datetime(year, month, day, hour, minute)
        granularity = "DATETIME"
    return {
        "year": year,
        "month": month,
        "day": day,
        "hour": hour,
        "minute": minute,
        "resolved_at": resolved,
        "granularity": granularity,
        "resolution_status": "RESOLVED",
        "ambiguity_reason": None,
        "candidates": [],
    }


def _bare_day_candidates(day: int, anchor: datetime) -> list[datetime]:
    found: list[datetime] = []
    for shift in (0, 1):
        year, month = _shift_month(anchor.year, anchor.month, shift)
        if day < 1 or day > calendar.monthrange(year, month)[1]:
            continue
        candidate = datetime(year, month, day)
        if candidate.date() < anchor.date():
            continue
        found.append(candidate)
    return found


def _shift_month(year: int, month: int, shift: int) -> tuple[int, int]:
    index = month - 1 + shift
    return year + index // 12, index % 12 + 1


def _bind_role(text: str, found: FoundSpan, model_role: TimeRole) -> tuple[TimeRole, ActionStatus, str | None]:
    clause = _clause(text, found.start)
    if _UNCERTAIN.search(clause):
        return model_role, "UNKNOWN", "UNCERTAIN"
    if found.raw_text.startswith(("今天", "今日")) and re.search(r"找|联系|确认", clause) and "再" not in clause:
        return "OTHER", "COMPLETED", None
    if re.search(r"反馈|预计|承诺|会完成", clause) and re.search(r"老师|总|经理|客户", clause):
        return "CUSTOMER_COMMITMENT", "COMMITTED", None
    before = clause[: max(0, found.start - _clause_start(text, found.start))]
    after = text[found.end : _clause_end(text, found.end)]
    if re.search(r"再找|再联系|等\s*$", before) or re.match(r"\s*(再)?(找|联系)", after):
        return "SALES_FOLLOW_UP", "PLANNED", None
    if re.search(r"(我|我们|本人)\s*$", before) or clause.startswith(("我", "我们", "本人")):
        return "SALES_FOLLOW_UP", "PLANNED", None
    marker = _REPLACEMENT.search(text)
    if marker is not None and found.start >= marker.start():
        return "SALES_FOLLOW_UP", "PLANNED", None
    if model_role == "OTHER":
        return "OTHER", "UNKNOWN", "ROLE"
    if model_role == "SALES_FOLLOW_UP":
        status: ActionStatus = "PLANNED"
    elif model_role == "CUSTOMER_COMMITMENT":
        status = "COMMITTED"
    else:
        status = "UNKNOWN"
    return model_role, status, None


def _owner_from_clause(text: str, found: FoundSpan, role: TimeRole) -> str:
    clause = _clause(text, found.start)
    if role == "SALES_FOLLOW_UP":
        return "我"
    match = re.search(r"([\u4e00-\u9fff]{1,8}(?:老师|总|经理))", clause)
    return match.group(1) if match else ""


def _link_actions(mentions: list[StoredMention], actions: list[StoredAction]) -> None:
    for mention in mentions:
        action = next((item for item in actions if item.action_id == mention.action_id), None)
        if action is None:
            continue
        action.temporal_mention_id = mention.mention_id
        if mention.role == "CUSTOMER_COMMITMENT":
            action.owner_role = "CUSTOMER"
            action.action_status = "COMMITTED"
        elif mention.role == "SALES_FOLLOW_UP":
            action.owner_role = "SALES"
            if action.action_status != "COMPLETED":
                action.action_status = "PLANNED"
        elif mention.role == "INTERNAL_ACTION":
            action.owner_role = "INTERNAL"
        elif mention.role == "OTHER":
            action.owner_role = "OTHER"
            action.action_status = "COMPLETED"


def _supersede_replacements(text: str, mentions: list[StoredMention], actions: list[StoredAction]) -> None:
    marker = _REPLACEMENT.search(text)
    if marker is None:
        return
    cut = marker.start()
    previous = [item for item in mentions if item.quote_end <= cut and item.role == "SALES_FOLLOW_UP"]
    current = [item for item in mentions if item.quote_start >= cut and item.role == "SALES_FOLLOW_UP"]
    if not previous or not current:
        return
    for item in previous:
        item.state = "SUPERSEDED"
    current[0].correction_of = previous[-1].mention_id
    for action in actions:
        if action.temporal_mention_id in {item.mention_id for item in previous}:
            action.state = "SUPERSEDED"


def _merge_history(
    previous: tuple[list[object], list[object]] | None,
    mentions: list[StoredMention],
    actions: list[StoredAction],
) -> tuple[list[StoredMention], list[StoredAction]]:
    if previous is None:
        return mentions, actions
    previous_mentions, previous_actions = previous
    old_mentions = [_stored_mention(item) for item in previous_mentions]
    old_actions = [_stored_action(item) for item in previous_actions]
    new_ids = {item.mention_id for item in mentions}
    kept = [item for item in old_mentions if item.mention_id not in new_ids]
    for item in kept:
        if item.state == "ACTIVE" and any(
            item.action_id and item.action_id == new.action_id and new.state == "ACTIVE" for new in mentions
        ):
            item.state = "SUPERSEDED"
    fresh_ids = {item.action_id for item in actions}
    kept_actions = [item for item in old_actions if item.action_id not in fresh_ids]
    return [*kept, *mentions], [*kept_actions, *actions]


def _primary_sales(
    mentions: list[StoredMention], actions: list[StoredAction]
) -> tuple[StoredMention | None, StoredAction] | list[tuple[StoredMention | None, StoredAction]] | None:
    sales = [
        item
        for item in actions
        if item.state == "ACTIVE" and item.owner_role == "SALES" and item.action_status == "PLANNED"
    ]
    if not sales:
        return None
    paired = []
    for action in sales:
        mention = next(
            (
                item
                for item in mentions
                if item.state == "ACTIVE" and item.mention_id == action.temporal_mention_id
            ),
            None,
        )
        paired.append((mention, action))
    if len(paired) == 1:
        return paired[0]
    return paired


def _commitment_only(mentions: list[StoredMention], actions: list[StoredAction]) -> bool:
    active_mentions = [item for item in mentions if item.state == "ACTIVE"]
    if not any(item.role == "CUSTOMER_COMMITMENT" for item in active_mentions):
        return False
    return _primary_sales(mentions, actions) is None


def _bundle(draft: TaskDraft) -> tuple[list[object], list[object]] | None:
    raw = draft.content_json.get("temporal_evidence")
    if not isinstance(raw, dict) or raw.get("version") != PROTOCOL_VERSION:
        return None
    mentions = raw.get("mentions")
    actions = raw.get("actions")
    if not isinstance(mentions, list) or not isinstance(actions, list):
        return None
    return mentions, actions


def _write_bundle(draft: TaskDraft, mentions: list[StoredMention], actions: list[StoredAction]) -> None:
    draft.content_json["temporal_evidence"] = {
        "version": PROTOCOL_VERSION,
        "mentions": [item.model_dump(mode="json") for item in mentions],
        "actions": [item.model_dump(mode="json") for item in actions],
    }


def _stored_mention(item: object) -> StoredMention:
    return item if isinstance(item, StoredMention) else StoredMention.model_validate(item)


def _stored_action(item: object) -> StoredAction:
    return item if isinstance(item, StoredAction) else StoredAction.model_validate(item)


class _ModelMention(BaseModel):
    model_config = ConfigDict(extra="ignore")

    raw_text: str
    quote_start: int
    quote_end: int
    kind: TimeKind
    role: TimeRole
    owner: str = ""
    action_ref: str = ""
    confidence: float = 0


class _ModelAction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action_ref: str
    owner_role: Literal["CUSTOMER", "SALES", "INTERNAL", "OTHER"]
    owner_text: str = ""
    action_text: str
    action_status: ActionStatus
    evidence_quote: str
    quote_start: int
    quote_end: int


def _read_mention(item: object) -> _ModelMention:
    try:
        return item if isinstance(item, _ModelMention) else _ModelMention.model_validate(item)
    except ValueError as exc:
        raise TemporalContractError("illegal temporal mention") from exc


def _read_action(item: object) -> _ModelAction:
    try:
        return item if isinstance(item, _ModelAction) else _ModelAction.model_validate(item)
    except ValueError as exc:
        raise TemporalContractError("illegal temporal action") from exc


def _mention_span(text: str, item: object) -> tuple[int, int]:
    mention = _read_mention(item)
    start, end = _snap_span(text, mention)
    return start, end


def _snap_span(text: str, mention: _ModelMention) -> tuple[int, int]:
    within = 0 <= mention.quote_start < mention.quote_end <= len(text)
    quoted = text[mention.quote_start : mention.quote_end] if within else ""
    if quoted == mention.raw_text:
        return mention.quote_start, mention.quote_end
    start = text.find(mention.raw_text)
    if start < 0 or text.find(mention.raw_text, start + 1) >= 0:
        raise TemporalContractError("temporal span is not in the source")
    return start, start + len(mention.raw_text)


def _exact_slice(text: str, start: int, end: int, raw: str) -> str:
    if 0 <= start < end <= len(text) and text[start:end] == raw:
        return raw
    found = text.find(raw)
    if found < 0 or text.find(raw, found + 1) >= 0:
        raise TemporalContractError("action quote is not in the source")
    return raw


def _extend_clock(text: str, end: int) -> int:
    match = _CLOCK.match(text[end:])
    if match is None or not match.group(0).strip(" 的"):
        return end
    return end + match.end()


def _clock_in_text(raw: str) -> tuple[int, int] | None:
    match = _CLOCK.search(raw)
    if match is None or match.start() == 0:
        return None
    return _clock_parts(match)


def _clock_parts(match: re.Match[str]) -> tuple[int, int] | None:
    try:
        hour = int(match.group(2)) if match.group(2) else _number(match.group(5) or "")
        minute = (
            int(match.group(3))
            if match.group(3)
            else 30
            if match.group(6) == "半"
            else _number(match.group(6).rstrip("分"))
            if match.group(6)
            else 0
        )
    except (ValueError, KeyError):
        return None
    period = match.group(1)
    if period in {"下午", "晚上"} and hour < 12:
        hour += 12
    elif period in {"上午", "早上"} and hour == 12:
        hour = 0
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    return hour, minute


def _number(value: str) -> int:
    if value.isdigit():
        return int(value)
    if "十" in value:
        left, right = value.split("十", 1)
        return _DIGITS.get(left, 1) * 10 + _DIGITS.get(right, 0)
    return _DIGITS[value]


def _clause(text: str, index: int) -> str:
    start = _clause_start(text, index)
    end = _clause_end(text, index)
    return text[start:end]


def _clause_start(text: str, index: int) -> int:
    return max(text.rfind(mark, 0, index) for mark in "，,。；;！？!?\n") + 1


def _clause_end(text: str, index: int) -> int:
    positions = [text.find(mark, index) for mark in "，,。；;！？!?\n"]
    positions = [item for item in positions if item >= 0]
    return min(positions) if positions else len(text)


def _action_for(mention: StoredMention, actions: list[StoredAction]) -> StoredAction | None:
    return next((item for item in actions if item.action_id == mention.action_id), None)


def _sentence(text: str) -> str:
    value = text.strip("。")
    return f"{value}。" if value else ""


def _month_prompt(raw: str, day: int) -> str:
    if raw.replace(" ", "") == "30号" or day == 30:
        return "“30号”是指本月30号还是下月30号？"
    return f"“{day}号”是指本月{day}号还是下月{day}号？"


def _month_label(index: int, day: int) -> str:
    prefix = "本月" if index == 0 else "下月"
    shown = day or ""
    if shown == 30:
        return f"{prefix}30号"
    return f"{prefix}{shown}号"


def _role_prompt(left: str, right: str) -> str:
    normalized = {left.replace(" ", ""), right.replace(" ", "")}
    if normalized == {"本月底", "30号"}:
        return "请确认“本月底”和“30号”分别对应客户完成时间，还是你下次联系时间。"
    return f"请确认“{left}”和“{right}”分别对应客户完成时间，还是你下次联系时间。"


def _apply_role_choice(choice_id: str, mentions: list[StoredMention]) -> None:
    parts = choice_id.split(":")
    if len(parts) != 3:
        raise TemporalContractError("unknown temporal choice")
    _, mention_id, side = parts
    ordered = [item for item in mentions if item.state == "ACTIVE" and item.ambiguity_reason == "ROLE"]
    if len(ordered) < 2 or ordered[0].mention_id != mention_id or side not in {"customer", "sales"}:
        raise TemporalContractError("unknown temporal choice")
    first, second = ordered[0], ordered[1]
    if side == "customer":
        first.role, second.role = "CUSTOMER_COMMITMENT", "SALES_FOLLOW_UP"
    else:
        first.role, second.role = "SALES_FOLLOW_UP", "CUSTOMER_COMMITMENT"
    for item in (first, second):
        if item.candidates:
            item.ambiguity_reason = "MONTH"
            item.resolution_status = "AMBIGUOUS"
        elif item.resolved_at is not None:
            item.ambiguity_reason = None
            item.resolution_status = "RESOLVED"
        else:
            item.ambiguity_reason = None



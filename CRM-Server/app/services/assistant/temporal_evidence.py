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
from app.services.assistant.llm_contracts import ModelDraftAction, ModelTemporalMention, TimeRole

StoredTimeKind = Literal[
    "EXPLICIT_DATE",
    "MONTH_DAY",
    "DAY_OF_MONTH",
    "MONTH_END",
    "MONTH_SEGMENT",
    "RELATIVE_DAY",
    "RELATIVE_WEEK",
    "RELATIVE_MONTH",
    "RELATIVE_WEEKDAY",
    "FULL_MONTH",
    "RELATIVE_YEAR_DATE",
    "UNKNOWN",
]
MonthSegmentName = Literal["EARLY", "MIDDLE", "LATE"]
MentionGranularity = Literal["DATE", "DATETIME", "UNKNOWN", "MONTH_SEGMENT", "FULL_MONTH"]

PROTOCOL_VERSION = "temporal-evidence-v1"
PARSER_VERSION: Literal["assistant-date-v2"] = "assistant-date-v2"
POLICY_VERSION: Literal["bare-day-v1"] = "bare-day-v1"
Resolution = Literal["RESOLVED", "AMBIGUOUS", "UNRESOLVED", "EXPLICITLY_NONE"]
EvidenceState = Literal["ACTIVE", "SUPERSEDED", "EXPLICITLY_NONE"]
ActionStatus = Literal["PLANNED", "COMPLETED", "COMMITTED", "UNKNOWN"]
_REPLACEMENT = re.compile(r"改成|改为|改到|应为|而是")
_LABEL_WHITESPACE = re.compile(r"\s+")
_CLOCK = re.compile(
    r"(?:[的\s]*)(?:(上午|下午|晚上|中午|早上)?(?:(\d{1,2})[:：](\d{2})(?::(\d{2}))?"
    r"|([零〇一二两三四五六七八九十\d]{1,3})[点时](半|[零〇一二两三四五六七八九十\d]{1,3}分?)?))"
)
_PERIOD = re.compile(r"[的\s]*(?:上午|下午|晚上|中午|早上)")
_YEAR_OFFSETS = {"今年": 0, "明年": 1, "后年": 2, "去年": -1}
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "RELATIVE_YEAR_DATE",
        re.compile(r"(今年|明年|后年|去年)[\s，,、]*(?:(20\d{2})\s*年\s*)?([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*[号日]"),
    ),
    ("UNKNOWN", re.compile(r"今年|明年|后年|去年|年初|年中|年底|年末")),
    ("RELATIVE_MONTH", re.compile(r"下个?月\s*([0-9]{1,2})\s*[号日]")),
    ("MONTH_SEGMENT", re.compile(r"(?<!\d)(1[0-2]|[1-9])\s*月\s*([初中末底])(?!旬)")),
    ("MONTH_SEGMENT", re.compile(r"(下个|这个|下|本)?月([初中末底])(?!旬)")),
    ("MONTH_DAY", re.compile(r"(?:(20\d{2})\s*年\s*)?([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*[号日]")),
    ("FULL_MONTH", re.compile(r"(?<!\d)(1[0-2]|[1-9])\s*月份")),
    ("FULL_MONTH", re.compile(r"(?<!\d)(1[0-2]|[1-9])\s*月(?!份|\d|初|中|末|底)")),
    ("EXPLICIT_DATE", re.compile(r"20\d{2}[-/年]\d{1,2}[-/月]\d{1,2}日?")),
    ("RELATIVE_WEEKDAY", re.compile(r"(?:下|本|这)?(?:周|星期|礼拜)[一二三四五六日天]")),
    ("RELATIVE_WEEK", re.compile(r"(?:下个?|本|这)(?:周|星期|礼拜)(?![一二三四五六日天期])")),
    ("RELATIVE_DAY", re.compile(r"大后天|后天|明天|今天|今日|刚刚|刚才|方才")),
    ("DAY_OF_MONTH", re.compile(r"([0-9]{1,2})\s*[号日]")),
)
_JUST_NOW = ("刚刚", "刚才", "方才")
_WEEKDAYS = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


class TemporalContractError(ValueError):
    """Model evidence contradicted the source text or the closed vocabulary."""

    def __init__(self, message: str, *, failure_origin: str = "model_output") -> None:
        super().__init__(message)
        if failure_origin not in {"model_output", "server_contract"}:
            failure_origin = "model_output"
        self.failure_origin = failure_origin


class ActionContractError(TemporalContractError):
    """Action model or action quote contradicted the source."""


class FoundSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: StoredTimeKind
    start: int
    end: int
    raw_text: str
    groups: tuple[str | None, ...] = ()


class QuotedAction(BaseModel):
    """Original model action quote with durable source-local coordinates."""

    model_config = ConfigDict(extra="forbid")

    source_segment_id: str
    action: ModelDraftAction


class StoredMention(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mention_id: str
    raw_text: str
    source_segment_id: str
    quote_start: int
    quote_end: int
    kind: StoredTimeKind
    role: TimeRole
    owner: str = ""
    action_id: str | None = None
    year: int | None = None
    month: int | None = None
    day: int | None = None
    hour: int | None = None
    minute: int | None = None
    segment: MonthSegmentName | None = None
    granularity: MentionGranularity = "UNKNOWN"
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
    source_quotes: list[ModelTemporalMention] = Field(default_factory=list)
    source_actions: list[QuotedAction] = Field(default_factory=list)
    communication_time: bool = False
    answer_gap: str | None = None


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


def validate_temporal_quotes(text: str, mentions: list[object]) -> None:
    """Validate source truth, independently of scanner coverage or model kind."""

    for item in mentions:
        _mention_span(text, item)


def _canonical_spans(text: str, mentions: list[ModelTemporalMention]) -> list[FoundSpan]:
    """Union source grammar and quotes; normalize a whole overlapping expression once."""

    spans = find_time_spans(text)
    for mention in mentions:
        spans.append(
            FoundSpan(kind="UNKNOWN", start=mention.quote_start, end=mention.quote_end, raw_text=mention.raw_text)
        )
    spans.sort(key=lambda item: (item.start, -(item.end - item.start)))
    merged: list[FoundSpan] = []
    for span in spans:
        if not merged or span.start >= merged[-1].end:
            merged.append(span)
            continue
        previous = merged[-1]
        if span.end <= previous.end:
            continue
        # A crossing quote is valid source evidence, not a scanner-format error.
        # The whole expression must normalize; an inner date cannot stand for it.
        merged[-1] = FoundSpan(
            kind="UNKNOWN", start=previous.start, end=span.end, raw_text=text[previous.start : span.end]
        )
    return merged


def attach_model_evidence(
    draft: TaskDraft,
    *,
    segment_id: str,
    segment_text: str,
    anchor: datetime,
    mentions: list[object],
    actions: list[object],
) -> None:
    """Quote truth and server normalization are separate; omissions cannot hide dates."""

    quoted: list[ModelTemporalMention] = []
    for item in mentions:
        mention = _read_mention(item)
        start, end = _snap_span(segment_text, mention)
        quoted.append(mention.model_copy(update={"quote_start": start, "quote_end": end}))
    spans = _canonical_spans(segment_text, quoted)
    if not spans and not actions:
        return
    built_mentions: list[StoredMention] = []
    built_actions: list[StoredAction] = []
    action_ids: dict[str, str] = {}
    quoted_actions: dict[str, QuotedAction] = {}
    for item in actions:
        action = _read_action(item)
        quote = action.evidence_quote
        start, end = _action_span(segment_text, action)
        identity = f"{segment_id}:{action.owner_role}:{action.action_text}:{start}:{end}"
        action_id = "act_" + sha256(identity.encode()).hexdigest()[:16]
        if action.action_ref in action_ids:
            raise ActionContractError("duplicate action reference")
        action_ids[action.action_ref] = action_id
        quoted_actions[action.action_ref] = QuotedAction(
            source_segment_id=segment_id,
            action=action.model_copy(update={"quote_start": start, "quote_end": end}),
        )
        built_actions.append(
            StoredAction(
                action_id=action_id,
                owner_role=action.owner_role,
                owner_text=action.owner_text,
                action_text=action.action_text,
                source_segment_id=segment_id,
                evidence_quote=quote,
                quote_start=start,
                quote_end=end,
                action_status=action.action_status,
            )
        )
    for mention in quoted:
        if mention.action_ref and mention.action_ref not in action_ids:
            raise TemporalContractError("temporal mention points at an unknown action")
    for found in spans:
        sources = [item for item in quoted if found.start <= item.quote_start and item.quote_end <= found.end]
        nominated = {action_ids[item.action_ref] for item in sources if item.action_ref}
        related = [item for item in built_actions if _same_action_clause(segment_text, found, item)]
        linked = next((item for item in related if item.action_id in nominated), None)
        if linked is None and len(related) == 1:
            linked = related[0]
        hint = next(
            (item for item in sources if item.quote_start == found.start and item.quote_end == found.end),
            sources[0] if sources else None,
        )
        stored = _resolve_span(
            found,
            segment_text=segment_text,
            segment_id=segment_id,
            anchor=anchor,
            action_id=linked.action_id if linked else None,
            model_role=hint.role if hint else "OTHER",
            model_owner=hint.owner if hint else "",
            confidence=hint.confidence if hint else 0,
        )
        stored.source_quotes = sources
        stored.source_actions = [
            quoted_actions[ref] for ref in dict.fromkeys(item.action_ref for item in sources if item.action_ref)
        ]
        if _meeting_context_time(segment_text, found):
            stored.role = "OTHER"
            stored.ambiguity_reason = None
            stored.action_id = None
            stored.communication_time = True
        elif _background_year(segment_text, found):
            stored.role = "CUSTOMER_ACTION" if linked and linked.owner_role == "CUSTOMER" else "OTHER"
            stored.ambiguity_reason = None
        if len(nominated) > 1:
            stored.ambiguity_reason = "ROLE"
            stored.resolution_status = "AMBIGUOUS"
        if (stored.role == "SALES_FOLLOW_UP" or stored.ambiguity_reason in {"ROLE", "STATUS"}) and linked is None:
            # Source-derived action, not model-invented text. Missing model evidence
            # must not make an explicit source action/date disappear from the gate.
            start, end = _clause_start(segment_text, found.start), _clause_end(segment_text, found.end)
            raw_quote = segment_text[start:end]
            quote = raw_quote.strip()
            if quote:
                start += len(raw_quote) - len(raw_quote.lstrip())
                end = start + len(quote)
                action_id = "act_" + sha256(f"{segment_id}:{start}:{end}:SALES".encode()).hexdigest()[:16]
                linked = StoredAction(
                    action_id=action_id,
                    owner_role="SALES",
                    owner_text="我",
                    action_text=_source_action_text(quote),
                    source_segment_id=segment_id,
                    evidence_quote=quote,
                    quote_start=start,
                    quote_end=end,
                    action_status="PLANNED",
                )
                built_actions.append(linked)
                stored.action_id = action_id
        built_mentions.append(stored)
    _link_actions(built_mentions, built_actions)
    _supersede_replacements(segment_text, built_mentions, built_actions)
    _guard_conflicting_dates(built_mentions, built_actions)
    previous = _bundle(draft)
    merged_mentions, merged_actions = _merge_history(previous, built_mentions, built_actions)
    _write_bundle(draft, merged_mentions, merged_actions)
    project_draft(draft)


def temporal_answer_target(draft: TaskDraft) -> str | None:
    """Return only the server's current action-scoped temporal question."""

    spec = temporal_waiting(draft)
    if spec is None or spec.get("reason") not in {"DATE", "MONTH", "ROLE", "STATUS"}:
        return None
    mention_id = spec.get("mention_id")
    if not isinstance(mention_id, str) or not isinstance(spec.get("business_action_id"), str):
        return None
    return mention_id


def temporal_supplement_target(draft: TaskDraft) -> str | None:
    """Authorize a confirmation supplement only for its unique primary date."""

    if temporal_waiting(draft) is not None:
        return None
    bundle = _bundle(draft)
    if bundle is None:
        return None
    sales = _primary_sales(
        [_stored_mention(item) for item in bundle[0]],
        [_stored_action(item) for item in bundle[1]],
        _primary_action_id(draft.content_json),
    )
    if sales is None or isinstance(sales, list):
        return None
    mention, _action = sales
    return mention.mention_id if mention and mention.resolution_status == "RESOLVED" and mention.resolved_at else None


def is_temporal_supplement(text: str) -> bool:
    """Accept dates/equivalents/corrections, never a newly described action."""

    value = re.sub(r"\s+", "", text)
    spans = find_time_spans(value)
    if not spans or any(_is_just_now(span) for span in spans):
        return False
    remainder = value
    for span in reversed(spans):
        remainder = remainder[: span.start] + remainder[span.end :]
    remainder = re.sub(r"也就是|也即|就是|改成|改为|改到|应为|而是|不是|日期|时间|补充|更正|调整为", "", remainder)
    return not remainder.strip("，,。；;：:、（）()‘’“”\"'！？!?的为是")


def is_temporal_choice_answer(draft: TaskDraft, text: str) -> bool:
    """Recognize an explicit answer only to the current role/status question."""

    target_id = temporal_answer_target(draft)
    bundle = _bundle(draft)
    if target_id is None or bundle is None:
        return False
    target = next((_stored_mention(item) for item in bundle[0] if item.get("mention_id") == target_id), None)
    return target is not None and _temporal_prose_choice(text, target, find_time_spans(text)) is not None


def _temporal_prose_choice(text: str, target: StoredMention, spans: list[FoundSpan]) -> str | None:
    residual = text
    for span in reversed(spans):
        residual = residual[: span.start] + residual[span.end :]
    value = re.sub(r"[\s，,。；;：:、！？!?]", "", residual)
    if target.ambiguity_reason == "ROLE":
        if re.fullmatch(r"(?:这|这个|那|那个)?(?:是|指的是|指)?客户(?:的)?(?:完成|付款|承诺)(?:时间|日期)?", value):
            return f"role:{target.mention_id}:customer"
        if re.fullmatch(
            r"(?:这|这个|那|那个)?(?:是|指的是|指)?(?:我|我们|销售)(?:的)?(?:下次)?(?:联系|跟进)(?:时间|日期)?", value
        ):
            return f"role:{target.mention_id}:sales"
    if target.ambiguity_reason == "STATUS":
        if re.fullmatch(
            r"(?:我|我们)?(?:已经|已)(?:联系|找|跟进|确认)?(?:过|完成)?(?:了)?(?:客户)?|(?:我|我们)?(?:联系|找|跟进|确认)(?:过|了)(?:客户)?",
            value,
        ):
            return f"status:{target.mention_id}:completed"
        if re.fullmatch(r"(?:我|我们)?(?:计划|准备|打算|将|要)(?:今天)?(?:再)?(?:联系|找|跟进|确认)(?:客户)?", value):
            return f"status:{target.mention_id}:planned"
    return None


def _apply_status_choice(choice_id: str, mentions: list[StoredMention], actions: list[StoredAction]) -> None:
    parts = choice_id.split(":")
    if len(parts) != 3 or parts[2] not in {"completed", "planned"}:
        raise TemporalContractError("unknown temporal choice")
    _, mention_id, status = parts
    mention = next(
        (
            item
            for item in mentions
            if item.mention_id == mention_id and item.state == "ACTIVE" and item.ambiguity_reason == "STATUS"
        ),
        None,
    )
    action = _action_for(mention, actions) if mention is not None else None
    if mention is None or action is None:
        raise TemporalContractError("unknown temporal choice")
    for item in mentions:
        if item.state != "ACTIVE" or item.action_id != action.action_id or item.ambiguity_reason != "STATUS":
            continue
        item.role = "SALES_FOLLOW_UP" if status == "planned" else "OTHER"
        item.ambiguity_reason = "DATE" if item.answer_gap == "DATE_CONFLICT" else None
        item.resolution_status = (
            "AMBIGUOUS"
            if item.answer_gap == "DATE_CONFLICT"
            else "RESOLVED"
            if item.resolved_at is not None
            else "UNRESOLVED"
        )
    action.owner_role = "SALES"
    action.action_status = "PLANNED" if status == "planned" else "COMPLETED"


def apply_temporal_answer(
    draft: TaskDraft,
    *,
    target_id: str,
    source_text: str,
    answer_segment_id: str,
    mentions: list[object],
    actions: list[object],
) -> None:
    """Restructure all source semantics, but consume only the current date wait.

    Old evidence keeps its anchor and prior role/choice decisions. Global model
    offsets must map to one durable source; a reply never replans other actions.
    """

    previous = _bundle(draft)
    if (
        previous is None
        or not target_id
        or target_id not in {temporal_answer_target(draft), temporal_supplement_target(draft)}
    ):
        raise TemporalContractError("temporal answer does not match the current wait")
    records = draft.source_records
    if source_text != "\n".join(record.text for record in records):
        raise TemporalContractError("temporal answer source does not match source records")
    ranges: list[tuple[int, int]] = []
    offset = 0
    for record in records:
        ranges.append((offset, offset + len(record.text)))
        offset += len(record.text) + 1

    def source_index(start: int, end: int) -> int | None:
        for index, (left, right) in enumerate(ranges):
            if left <= start < end <= right:
                return index
        return None

    quoted_actions: dict[str, QuotedAction] = {}
    dropped_quotes = False
    for item in actions:
        try:
            action = _read_action(item)
            start, end = _action_span(source_text, action, ranges)
            index = source_index(start, end)
        except (TemporalContractError, ActionContractError):
            dropped_quotes = True
            continue
        if index is None or action.action_ref in quoted_actions:
            dropped_quotes = True
            continue
        quoted_actions[action.action_ref] = QuotedAction(
            source_segment_id=records[index].segment_id,
            action=action.model_copy(
                update={
                    "quote_start": start - ranges[index][0],
                    "quote_end": end - ranges[index][0],
                }
            ),
        )

    def mention_text_in_answer(item: object, answer_text: str) -> bool:
        raw = getattr(item, "raw_text", None)
        if not isinstance(raw, str) and isinstance(item, dict):
            raw = item.get("raw_text")
        return isinstance(raw, str) and raw in answer_text

    quotes: dict[str, list[ModelTemporalMention]] = {record.segment_id: [] for record in records}

    answer_record = next((record for record in records if record.segment_id == answer_segment_id), None)
    answer_index = next((index for index, record in enumerate(records) if record.segment_id == answer_segment_id), None)
    for item in mentions:
        try:
            mention = _read_mention(item)
            start, end = _snap_span(source_text, mention, ranges)
            index = source_index(start, end)
        except (TemporalContractError, ActionContractError, ValueError) as exc:
            if answer_record is not None and mention_text_in_answer(item, answer_record.text):
                raise TemporalContractError("temporal answer evidence is invalid") from exc
            dropped_quotes = True
            continue
        in_answer = answer_index is not None and index == answer_index
        if index is None or (mention.action_ref and mention.action_ref not in quoted_actions):
            answered_here = answer_record is not None and mention.raw_text in answer_record.text
            if in_answer or answered_here:
                raise TemporalContractError("temporal answer evidence is invalid")
            dropped_quotes = True
            continue
        quotes[records[index].segment_id].append(
            mention.model_copy(
                update={
                    "quote_start": start - ranges[index][0],
                    "quote_end": end - ranges[index][0],
                }
            )
        )
    old_mentions, old_actions = previous
    stored = [_stored_mention(item) for item in old_mentions]
    bound = [_stored_action(item) for item in old_actions]
    target = next((item for item in stored if item.mention_id == target_id and item.state == "ACTIVE"), None)
    if target is None:
        raise TemporalContractError("temporal answer target is no longer active")
    target_action = _action_for(target, bound)
    if target_action is None or target_action.state != "ACTIVE":
        raise TemporalContractError("temporal answer has no current action")
    answer = next((record for record in records if record.segment_id == answer_segment_id), None)
    if answer is None:
        raise TemporalContractError("temporal answer has no source segment")

    # Preserve every legal quote, including newly mentioned unknown old phrases,
    # without letting fresh model roles overwrite earlier server decisions.
    for record in records:
        if record.segment_id == answer_segment_id:
            continue
        for quote in quotes[record.segment_id]:
            matched = next(
                (
                    item
                    for item in stored
                    if item.source_segment_id == record.segment_id
                    and item.quote_start < quote.quote_end
                    and quote.quote_start < item.quote_end
                ),
                None,
            )
            if matched is None:
                found = FoundSpan(kind="UNKNOWN", start=quote.quote_start, end=quote.quote_end, raw_text=quote.raw_text)
                matched = _resolve_span(
                    found,
                    segment_text=record.text,
                    segment_id=record.segment_id,
                    anchor=record.recorded_at,
                    action_id=None,
                    model_role="OTHER",
                    model_owner="",
                    confidence=quote.confidence,
                )
                stored.append(matched)
            if quote not in matched.source_quotes:
                matched.source_quotes.append(quote)
            if quote.action_ref:
                source_action = quoted_actions[quote.action_ref]
                if source_action not in matched.source_actions:
                    matched.source_actions.append(source_action)

    spans = _canonical_spans(answer.text, quotes[answer_segment_id])
    pending_reason = target.ambiguity_reason if target.ambiguity_reason in {"ROLE", "STATUS"} else None
    prose_choice = _temporal_prose_choice(answer.text, target, spans)
    if prose_choice is not None:
        if pending_reason == "ROLE":
            _apply_role_choice(prose_choice, stored)
            _link_actions(stored, bound)
        elif pending_reason == "STATUS":
            _apply_status_choice(prose_choice, stored, bound)
        pending_reason = None
        if not spans:
            _write_bundle(draft, stored, bound)
            project_draft(draft)
            return
    marker = _REPLACEMENT.search(answer.text)
    before_correction = [span for span in spans if marker and span.end <= marker.start()]
    correction_spans = [span for span in spans if marker and span.start >= marker.end()]
    explicit_correction = marker is not None and len(correction_spans) == 1
    candidates = correction_spans if explicit_correction else spans
    replacements: list[StoredMention] = []
    for span in candidates:
        item = _resolve_span(
            span,
            segment_text=answer.text,
            segment_id=answer.segment_id,
            anchor=answer.recorded_at,
            action_id=target_action.action_id,
            model_role=target.role,
            model_owner=target.owner,
            confidence=0,
        )
        if not _is_just_now(item):
            item.role = target.role
            # A bound answer is the action's date, never the communication moment.
            item.communication_time = False
            # A date answer does not let model ownership override the current question.
            if item.ambiguity_reason in {"ROLE", "STATUS"}:
                item.ambiguity_reason = None
                if item.resolved_at is not None:
                    item.resolution_status = "RESOLVED"
        item.source_quotes = [
            q for q in quotes[answer_segment_id] if span.start <= q.quote_start and q.quote_end <= span.end
        ]
        if not item.source_quotes:
            item.source_quotes = [
                ModelTemporalMention(
                    raw_text=span.raw_text,
                    quote_start=span.start,
                    quote_end=span.end,
                    kind=span.kind,
                    role=target.role,
                    confidence=0,
                )
            ]
        item.source_actions = [
            quoted_actions[ref] for ref in dict.fromkeys(q.action_ref for q in item.source_quotes if q.action_ref)
        ]
        if explicit_correction and span.kind == "DAY_OF_MONTH" and target.resolved_at is not None:
            referenced = len(before_correction) == 1 and before_correction[0].kind == "DAY_OF_MONTH"
            old_day = int(before_correction[0].groups[0] or 0) if referenced else None
            # An omitted month inherits only when the rejected day identifies this date.
            primary = _primary_sales(stored, bound, _primary_action_id(draft.content_json))
            safe = (
                old_day == target.resolved_at.day
                and primary is not None
                and not isinstance(primary, list)
                and primary[1].action_id == target_action.action_id
            )
            if safe:
                new_day = int(span.groups[0] or 0)
                try:
                    item = item.model_copy(
                        update=_dated(
                            target.resolved_at.year,
                            target.resolved_at.month,
                            new_day,
                            _clock_in_text(span.raw_text),
                            answer.recorded_at,
                        )
                    )
                except ValueError:
                    item.answer_gap = "INVALID_DATE"
                    item.resolved_at = None
                    item.resolution_status = "UNRESOLVED"
            else:
                item.resolved_at = None
                item.candidates = []
                item.resolution_status = "UNRESOLVED"
                item.answer_gap = "MONTH"
        replacements.append(item)
    dated = [item for item in replacements if not _is_just_now(item)]
    unique: dict[tuple[datetime, str], StoredMention] = {}
    for item in dated:
        if item.resolved_at is not None and item.resolution_status == "RESOLVED":
            key = (item.resolved_at, item.granularity)
            equivalent = unique.get(key)
            if equivalent is not None:
                equivalent.source_quotes.extend(q for q in item.source_quotes if q not in equivalent.source_quotes)
                equivalent.source_actions.extend(q for q in item.source_actions if q not in equivalent.source_actions)
                replacements.remove(item)
            else:
                unique[key] = item
    dated = [item for item in replacements if not _is_just_now(item)]
    pinned = len(dated) == 1 and dated[0].resolution_status == "RESOLVED" and dated[0].resolved_at is not None
    if dropped_quotes and not pinned:
        raise TemporalContractError("temporal answer evidence is invalid")
    if pinned:
        replacement = dated[0]
        if target.ambiguity_reason == "DATE":
            selected = next(
                (
                    item
                    for item in stored
                    if item.state == "ACTIVE"
                    and item.action_id == target_action.action_id
                    and item.resolved_at == replacement.resolved_at
                    and item.granularity == replacement.granularity
                ),
                None,
            )
            if selected is not None:
                target = selected
                target_id = selected.mention_id
                target_action.temporal_mention_id = selected.mention_id
        equivalent = target.resolved_at == replacement.resolved_at and target.granularity == replacement.granularity
        if equivalent:
            stored.extend(replacements)
            replacement.state = "SUPERSEDED"
            replacement.correction_of = None
            if target.ambiguity_reason == "DATE":
                target.resolution_status = "RESOLVED"
                target.ambiguity_reason = None
                target.answer_gap = None
                target.candidates = []
                for item in stored:
                    if (
                        item.mention_id != target_id
                        and item.state == "ACTIVE"
                        and item.action_id == target_action.action_id
                        and item.ambiguity_reason == "DATE"
                    ):
                        item.state = "SUPERSEDED"
                draft.next_follow_time = DraftField(status="ACCEPTED", value=target.raw_text)
        elif target.resolved_at is not None and not explicit_correction:
            # Two distinct dates are facts, not an implicit correction.
            target.resolution_status = "AMBIGUOUS"
            target.ambiguity_reason = pending_reason or "DATE"
            target.answer_gap = "DATE_CONFLICT"
            replacement.resolution_status = "AMBIGUOUS"
            replacement.ambiguity_reason = pending_reason or "DATE"
            replacement.answer_gap = "DATE_CONFLICT"
            stored.extend(replacements)
        else:
            for item in stored:
                if item.state == "ACTIVE" and item.action_id == target_action.action_id:
                    item.state = "SUPERSEDED"
            replacement.correction_of = target_id
            replacement.role = target.role
            if pending_reason:
                replacement.ambiguity_reason = pending_reason
                replacement.resolution_status = "AMBIGUOUS"
            target_action.temporal_mention_id = replacement.mention_id
            target_action.revision += 1
            stored.extend(replacements)
            if not pending_reason:
                draft.next_follow_time = DraftField(status="ACCEPTED", value=replacement.raw_text)
    else:
        gap = "UNRECOGNIZED"
        if dated:
            last = dated[-1]
            gap = last.answer_gap or (
                "INVALID_DATE"
                if last.day is not None and last.kind != "DAY_OF_MONTH"
                else "MONTH"
                if last.kind == "DAY_OF_MONTH"
                else "DATE"
            )
        target.answer_gap = gap
        for item in dated:
            item.role = target.role
            item.ambiguity_reason = pending_reason or "DATE"
            item.resolution_status = "AMBIGUOUS" if len(dated) > 1 else "UNRESOLVED"
        stored.extend(replacements)
    _write_bundle(draft, stored, bound)
    project_draft(draft)


def _source_action_text(quote: str) -> str:
    # Keep the action itself source-derived, without putting its date in the
    # downstream task title. The original quote remains untouched for auditing.
    text = quote
    for span in reversed(find_time_spans(quote)):
        text = text[: span.start] + text[span.end :]
    return re.sub(r"^(本人|我们|我)(?:将|会|负责|计划|要|在)?", "", text.strip()).strip(" ，,、")


def _same_action_clause(text: str, found: FoundSpan, action: StoredAction) -> bool:
    if action.quote_start < found.end and found.start < action.quote_end:
        return True
    start, end = _clause_start(text, found.start), _clause_end(text, found.end)
    if start <= action.quote_start < end:
        return True
    between = text[found.end : action.quote_start]
    return found.end <= action.quote_start and re.fullmatch(r"[\s，,、]*", between) is not None


def _meeting_context_time(text: str, found: FoundSpan) -> bool:
    """Source-derived communication context is not an actionable due date."""

    clause = _clause(text, found.start)
    if found.raw_text.startswith(("今天", "今日")) and re.search(r"线上会议|线下会议|会议|培训|纪要|讨论", clause):
        return not re.search(
            r"(?:计划|准备|将|打算|要)(?:今天|今日|下午|上午|晚上)?(?:召开|开|参加|进行|安排|线上|线下|会议|培训|讨论)|再联系|跟进",
            clause,
        )
    if text[: found.start].strip():
        return False
    line_end = text.find("\n", found.end)
    line = text[found.start : line_end if line_end >= 0 else len(text)].strip()
    return line == found.raw_text


def _background_year(text: str, found: FoundSpan) -> bool:
    if found.kind != "UNKNOWN":
        return False
    clause = _clause(text, found.start)
    if re.fullmatch(r"\s*(今年|明年|后年|去年)?快?年[底末]了?\s*", clause):
        return True
    after = text[found.end : _clause_end(text, found.end)].strip()
    if re.match(r"(?:目前|暂时|现在|仍然|还是)?(?:没有|暂无|没|无|不再).{0,8}(?:采购|购买|预算|计划|需求)", after):
        return True
    if re.fullmatch(r"再看看?", after):
        prefix = text[: found.start]
        # A previously contacted person's name alone is not customer speech.
        reports = list(re.finditer(r"(?:客户|老师|总|经理)(?:反馈|表示|说)", prefix))
        return bool(reports and not re.search(r"我|我们|本人", prefix[reports[-1].end() :]))
    return False


def _project_answered_actions(draft: TaskDraft, mentions: list[StoredMention], actions: list[StoredAction]) -> None:
    """Project accepted dates into uniquely matched canonical actions, never source evidence."""
    primary = _primary_sales(mentions, actions, _primary_action_id(draft.content_json))
    primary_id = primary[1].action_id if isinstance(primary, tuple) else None
    for action in actions:
        current = next((item for item in mentions if item.mention_id == action.temporal_mention_id), None)
        if (
            action.state != "ACTIVE"
            or current is None
            or current.state != "ACTIVE"
            or current.correction_of is None
            or current.resolution_status != "RESOLVED"
            or current.resolved_at is None
        ):
            continue
        at = current.resolved_at
        label = f"{at.year}年{at.month}月{at.day}日"
        if current.granularity == "DATETIME":
            label += f" {at:%H:%M}"
        history = [item for item in mentions if item.action_id == action.action_id]
        dates = {item.raw_text for item in history}
        for item in history:
            if item.resolved_at is not None:
                old = item.resolved_at
                dates.add(
                    f"{old.year}年{old.month}月{old.day}日"
                    + (f" {old:%H:%M}" if item.granularity == "DATETIME" else "")
                )

        def replace_date(text: str, dates: set[str] = dates, label: str = label) -> str:
            for span in reversed(find_time_spans(text)):
                if span.raw_text in dates:
                    text = text[: span.start] + label + text[span.end :]
            return re.sub(r"(?:大概|大约|可能|也许|暂定)\s*(?=" + re.escape(label) + r")", "", text)

        def identity(text: str) -> str:
            text = re.sub(r"^(?:我方|我们|本人|销售|我)(?:将|会|负责|计划|要|在)?", "", text.strip())
            return re.sub(r"大概|大约|可能|也许|暂定|\s", "", _source_action_text(text))

        owners = {action.owner_text} - {""}
        if action.owner_role == "SALES":
            owners.update({"我", "我们", "本人", "我方", "销售"})
        items = [item for item in draft.content_json.get("action_items", []) if isinstance(item, dict)]
        matching = [item for item in items if item.get("item_id") == action.action_id]
        if not matching:
            matching = [
                item
                for item in items
                if item.get("owner") in owners
                and identity(str(item.get("action") or "")) == identity(action.action_text)
            ]
        if len(matching) == 1:
            item = matching[0]
            item["action"] = replace_date(str(item["action"]))
            item["due_date"] = label
        elif matching:
            continue
        # The scalar next action describes the primary sales action even when paraphrased.
        if action.action_id == primary_id or identity(draft.next_action.value or "") == identity(action.action_text):
            draft.next_action = draft.next_action.model_copy(
                update={"value": replace_date(draft.next_action.value or "")}
            )
        # A summary can mention several owners; never replace an unqualified shared action.
        shared = any(
            item.get("owner") not in owners and identity(str(item.get("action") or "")) == identity(action.action_text)
            for item in items
        )
        base = _source_action_text(action.action_text)
        variants = {action.action_text, *(date + base for date in dates)}
        for date in dates:
            variant = action.action_text
            for span in reversed(find_time_spans(variant)):
                if span.raw_text in dates:
                    variant = variant[: span.start] + date + variant[span.end :]
            variants.add(variant)
            variants.add(re.sub(r"(?:大概|大约|可能|也许|暂定)\s*(?=" + re.escape(date) + r")", "", variant))
        for key in ("next_action", "next_step_summary"):
            text = draft.content_json.get(key)
            if not isinstance(text, str):
                continue
            for variant in sorted(variants, key=len, reverse=True):
                if shared:
                    for owner in owners:
                        text = text.replace(owner + variant, owner + replace_date(variant))
                else:
                    text = text.replace(variant, replace_date(variant))
            if action.action_id == primary_id:
                # Paraphrased summaries: replace only owner-qualified stale dates of this action.
                for owner in owners:
                    for date in dates:
                        text = re.sub(
                            re.escape(owner) + r"(?:大概|大约|可能|也许|暂定)?\s*" + re.escape(date),
                            lambda _m, owner=owner, label=label: owner + label,
                            text,
                        )
            draft.content_json[key] = text


def project_draft(draft: TaskDraft) -> None:
    """Refresh slots and card strings from ACTIVE evidence. Does not parse again."""

    bundle = _bundle(draft)
    if bundle is None:
        return
    raw_mentions, raw_actions = bundle
    mentions = [_stored_mention(item) for item in raw_mentions]
    actions = [_stored_action(item) for item in raw_actions]
    _project_answered_actions(draft, mentions, actions)
    commitments = []
    for mention in mentions:
        if mention.state != "ACTIVE" or mention.role != "CUSTOMER_COMMITMENT":
            continue
        action = _action_for(mention, actions)
        owner = mention.owner or (action.owner_text if action else "")
        verb = action.action_text if action else ""
        if mention.raw_text and mention.raw_text in verb:
            text = _sentence(f"{owner}{verb}")
        else:
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
    sales = _primary_sales(mentions, actions, _primary_action_id(draft.content_json))
    notices: list[str] = []
    sales_text = ""
    corrections = [item for item in mentions if item.state == "ACTIVE" and item.correction_of]
    for item in corrections:
        previous = next((old for old in mentions if old.mention_id == item.correction_of), None)
        if previous is not None and previous.resolved_at is not None and item.resolved_at is not None:
            notices.append(
                f"已将当前动作日期从 {previous.resolved_at.year}年{previous.resolved_at.month}月"
                f"{previous.resolved_at.day}日"
                f"改为 {item.resolved_at.year}年{item.resolved_at.month}月{item.resolved_at.day}日。"
            )
    for mention in mentions:
        if mention.state != "ACTIVE" or not mention.communication_time:
            continue
        if mention.resolved_at is not None:
            notices.append(f'沟通时间：{mention.resolved_at.date().isoformat()}（原话："{mention.raw_text}"）。')
    if sales is not None and not isinstance(sales, list):
        sales_mention, sales_action = sales
        if draft.next_action.status not in {"ACCEPTED", "EXPLICITLY_NONE"} and (
            not sales_mention or not sales_mention.correction_of
        ):
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
            sales_text = _sentence(f"下一步：{draft.next_action.value or sales_action.action_text}（{label}）")
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
    """Return the single blocking, action-scoped temporal interaction."""

    bundle = _bundle(draft)
    if bundle is None:
        return None
    raw_mentions, raw_actions = bundle
    mentions = [item for item in (_stored_mention(raw) for raw in raw_mentions) if item.state == "ACTIVE"]
    actions = [item for item in (_stored_action(raw) for raw in raw_actions) if item.state == "ACTIVE"]
    action_by_id = {item.action_id: item for item in actions}
    action_times = [
        item
        for item in mentions
        if item.role == "SALES_FOLLOW_UP"
        or item.ambiguity_reason in {"ROLE", "STATUS"}
        or item.answer_gap == "DATE_CONFLICT"
    ]
    unresolved_roles = [item for item in action_times if item.ambiguity_reason == "ROLE"]
    if unresolved_roles:
        mention = unresolved_roles[0]
        action = action_by_id.get(mention.action_id or "")
        if len(unresolved_roles) >= 2 and unresolved_roles[0].action_id != unresolved_roles[1].action_id:
            left, right = unresolved_roles[:2]
            same_phrase = left.raw_text.replace(" ", "") == right.raw_text.replace(" ", "")
            if same_phrase:
                phrase = left.raw_text
                prompt = f"“{phrase}”是客户完成时间，还是你下次联系时间？"
                labels = ("客户完成时间", "我下次联系时间")
            else:
                prompt = _role_prompt(left.raw_text, right.raw_text)
                labels = (
                    f"{left.raw_text}是客户完成，{right.raw_text}是我下次联系",
                    f"{left.raw_text}是我下次联系，{right.raw_text}是客户完成",
                )
            candidates = [
                {"id": f"role:{left.mention_id}:customer", "label": labels[0]},
                {"id": f"role:{left.mention_id}:sales", "label": labels[1]},
            ]
        else:
            prompt = f"“{mention.raw_text}”是客户完成时间，还是你下次联系时间？"
            candidates = [
                {"id": f"role:{mention.mention_id}:customer", "label": "客户完成时间"},
                {"id": f"role:{mention.mention_id}:sales", "label": "我下次联系时间"},
            ]
        return {
            "reason": "ROLE",
            "mention_id": mention.mention_id,
            "business_action_id": action.action_id if action else None,
            "prompt": prompt,
            "candidates": candidates,
        }
    unresolved_status = next((item for item in action_times if item.ambiguity_reason == "STATUS"), None)
    if unresolved_status is not None:
        action = action_by_id.get(unresolved_status.action_id or "")
        return {
            "reason": "STATUS",
            "mention_id": unresolved_status.mention_id,
            "business_action_id": action.action_id if action else None,
            "prompt": f"“{unresolved_status.raw_text}联系客户”是已经完成，还是计划今天联系？",
            "candidates": [
                {"id": f"status:{unresolved_status.mention_id}:completed", "label": "已经完成"},
                {"id": f"status:{unresolved_status.mention_id}:planned", "label": "计划今天联系"},
            ],
        }
    ambiguous = next((item for item in action_times if item.resolution_status == "AMBIGUOUS" and item.candidates), None)
    if ambiguous is not None:
        day = ambiguous.day or 0
        action = action_by_id.get(ambiguous.action_id or "")
        return {
            "reason": "MONTH",
            "mention_id": ambiguous.mention_id,
            "business_action_id": action.action_id if action else None,
            "prompt": _month_prompt(ambiguous.raw_text, day),
            "candidates": [
                {"id": f"{ambiguous.mention_id}:{index}", "label": _month_label(index, day)}
                for index, _value in enumerate(ambiguous.candidates)
            ],
        }
    vague = next(
        (
            item
            for item in action_times
            if item.resolution_status in {"AMBIGUOUS", "UNRESOLVED"}
            and not item.candidates
            and (_date_answer_action(item, actions) is not None or item.answer_gap == "DATE_CONFLICT")
        ),
        None,
    )
    if vague is not None:
        action = action_by_id.get(vague.action_id or "")
        scoped = [item for item in mentions if item.action_id == vague.action_id]
        latest = scoped[-1] if scoped else vague
        gap = vague.answer_gap or "DATE"
        if gap == "INVALID_DATE":
            prompt = f"已保留原有信息，但“{latest.raw_text}”不是有效日期，请补充这个动作的有效日期。"
        elif gap == "MONTH":
            prompt = f"已保留“{latest.raw_text}”，还缺少月份，请补充这个动作的完整年月日。"
        elif gap == "UNRECOGNIZED":
            prompt = f"已保留“{vague.raw_text}”及原有动作信息，但未识别到具体日期，请补充这个动作的日期。"
        elif gap == "DATE_CONFLICT":
            dates = list(
                dict.fromkeys(item.resolved_at.date().isoformat() for item in scoped if item.resolved_at is not None)
            )
            labels = "、".join(dates)
            prompt = f"已保留这个动作的日期{labels}，请确认采用哪一个日期；如需更正，请明确说明。"
        else:
            prompt = f"“{vague.raw_text}”无法确定为唯一日期，请补充具体日期。"
        return {
            "reason": "DATE",
            "mention_id": vague.mention_id,
            "business_action_id": action.action_id if action else None,
            "prompt": prompt,
            "candidates": [],
            "gap": gap,
        }
    sales = _primary_sales(mentions, actions, _primary_action_id(draft.content_json))
    if isinstance(sales, list):
        return {
            "reason": "PRIMARY",
            "prompt": "请确认哪一项是你的下一步。",
            "candidates": [
                {"id": f"primary:{action.action_id}", "label": action.action_text} for _mention, action in sales
            ],
        }
    return None


_FUZZY_TIME_LABEL = "（模糊时间，未确定具体日期）"
_FULL_MONTH_LABEL = "（整月，未确定具体日期）"


def confirmation_time_labels(content_json: dict[str, object]) -> tuple[str | None, str | None]:
    """Return confirmation-card lines. None means that row stays absent or unchanged."""

    raw = content_json.get("temporal_evidence")
    if not isinstance(raw, dict) or raw.get("version") != PROTOCOL_VERSION:
        return None, None
    raw_mentions = raw.get("mentions")
    raw_actions = raw.get("actions")
    if not isinstance(raw_mentions, list) or not isinstance(raw_actions, list):
        return None, None
    mentions = [_stored_mention(item) for item in raw_mentions]
    actions = [_stored_action(item) for item in raw_actions]
    stored_commitments = content_json.get("customer_commitments")
    stored_texts: dict[str, str] = {}
    if isinstance(stored_commitments, list):
        for item in stored_commitments:
            if isinstance(item, dict) and isinstance(item.get("mention_id"), str) and isinstance(item.get("text"), str):
                stored_texts[item["mention_id"]] = item["text"]
    lines: list[str] = []
    for mention in mentions:
        if mention.state != "ACTIVE" or mention.role != "CUSTOMER_COMMITMENT":
            continue
        action = _action_for(mention, actions)
        phrase = _card_phrase(mention.raw_text, action.action_text if action is not None else "")
        if _full_month_mention(mention):
            lines.append(f"{phrase}{_FULL_MONTH_LABEL}")
            continue
        if mention.granularity == "MONTH_SEGMENT":
            lines.append(f"{phrase}{_FUZZY_TIME_LABEL}")
            continue
        fallback = stored_texts.get(mention.mention_id)
        lines.append(fallback or phrase)
    customer_line = "；".join(line for line in lines if line) or None
    sales = _primary_sales(mentions, actions, _primary_action_id(content_json))
    if sales is None or isinstance(sales, list):
        return customer_line, None
    sales_mention, _sales_action = sales
    if not isinstance(sales_mention, StoredMention) or sales_mention.resolution_status != "RESOLVED":
        return customer_line, None
    if sales_mention.granularity == "DATE":
        return customer_line, sales_mention.raw_text
    if _full_month_mention(sales_mention):
        return customer_line, f"{sales_mention.raw_text}{_FULL_MONTH_LABEL}"
    if sales_mention.granularity == "MONTH_SEGMENT":
        return customer_line, f"{sales_mention.raw_text}{_FUZZY_TIME_LABEL}"
    if sales_mention.granularity == "DATETIME":
        return customer_line, sales_mention.raw_text
    return customer_line, None


def _card_phrase(raw: str, verb: str) -> str:
    if raw and verb and raw in verb:
        return verb
    if raw and verb:
        return f"{raw}{verb}"
    return verb or raw


def match_temporal_choice_id(candidates: list[dict[str, object]], text: str) -> str | None:
    """Return the one current candidate id whose label equals text, ignoring whitespace."""

    needle = _LABEL_WHITESPACE.sub("", text)
    if not needle:
        return None
    matched: list[str] = []
    for candidate in candidates:
        label = candidate.get("label")
        choice_id = candidate.get("id")
        if not isinstance(label, str) or not isinstance(choice_id, str) or not choice_id:
            continue
        if _LABEL_WHITESPACE.sub("", label) == needle:
            matched.append(choice_id)
    if len(matched) != 1:
        return None
    return matched[0]


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
        _write_bundle(draft, mentions, actions)
        draft.content_json["temporal_evidence"]["primary_action_id"] = action_id
        project_draft(draft)
        return
    if choice_id.startswith("status:"):
        _apply_status_choice(choice_id, mentions, actions)
        _write_bundle(draft, mentions, actions)
        project_draft(draft)
        return
    if choice_id.startswith("role:"):
        _apply_role_choice(choice_id, mentions)
        _link_actions(mentions, actions)
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
    sales = _primary_sales(mentions, actions, _primary_action_id(draft.content_json))
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
    sales = _primary_sales(mentions, actions, _primary_action_id(draft.content_json))
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
        "segment_id": action.source_segment_id,
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
        # The event moment is audit evidence; it never owns or reclassifies an action.
        action_id=None if _is_just_now(found) else action_id,
        confidence=confidence,
        anchor_at=anchor,
        ambiguity_reason=reason,
        communication_time=_is_just_now(found) or _meeting_context_time(segment_text, found),
    )
    before, after = segment_text[: found.start], segment_text[found.end :]
    uncertain = re.search(r"(?:大概|大约|差不多|可能|也许)\s*$", before) or re.match(
        r"\s*(?:左右|前后|大概|大约|可能|也许)", after
    )
    if uncertain:
        return base.model_copy(
            update={
                "resolution_status": "AMBIGUOUS",
                "granularity": "UNKNOWN",
                "ambiguity_reason": reason or "UNCERTAIN",
            }
        )
    resolved = _resolve_kind(found, anchor, segment_text)
    if reason in {"ROLE", "STATUS"}:
        resolved["ambiguity_reason"] = reason
        if resolved.get("resolution_status") == "RESOLVED":
            resolved["resolution_status"] = "AMBIGUOUS"
    return base.model_copy(update=resolved)


def _full_month_mention(mention: StoredMention) -> bool:
    """Resolved whole-month evidence, including drafts stored before FULL_MONTH existed."""

    if mention.kind == "FULL_MONTH" or mention.granularity == "FULL_MONTH":
        return mention.resolution_status == "RESOLVED" and mention.resolved_at is None and mention.day is None
    return (
        mention.kind == "UNKNOWN"
        and mention.granularity == "UNKNOWN"
        and mention.resolution_status == "RESOLVED"
        and mention.day is None
        and mention.resolved_at is None
        and mention.month is not None
        and re.fullmatch(r"(?:1[0-2]|[1-9])\s*月份?", re.sub(r"\s+", "", mention.raw_text)) is not None
    )


def _explicit_year(text: str, start: int) -> int | None:
    match = re.search(r"(20\d{2})\s*年\s*$", text[:start])
    return int(match.group(1)) if match else None


def _year_for_month(text: str, start: int, month: int, anchor: datetime) -> int:
    explicit = _explicit_year(text, start)
    if explicit is not None:
        return explicit
    return anchor.year if month >= anchor.month else anchor.year + 1


def _resolve_kind(found: FoundSpan, anchor: datetime, segment_text: str) -> dict[str, object]:
    hour_minute = _clock_in_text(found.raw_text)
    kind = found.kind
    if kind == "RELATIVE_YEAR_DATE":
        relative, explicit, month_text, day_text = found.groups[:4]
        year = int(explicit) if explicit else anchor.year + _YEAR_OFFSETS[relative or "今年"]
        month, day = int(month_text or 0), int(day_text or 0)
        try:
            datetime(year, month, day)
        except ValueError:
            return {
                "year": year,
                "month": month,
                "day": day,
                "resolution_status": "UNRESOLVED",
                "granularity": "UNKNOWN",
            }
        return _dated(year, month, day, hour_minute, anchor)
    if kind == "MONTH_SEGMENT":
        if hour_minute is not None:
            return {
                "resolution_status": "UNRESOLVED",
                "ambiguity_reason": "DATE",
                "granularity": "UNKNOWN",
                "resolved_at": None,
                "candidates": [],
            }
        first = found.groups[0] if found.groups else None
        segment_char = found.groups[1] if len(found.groups) > 1 else None
        segment = {"初": "EARLY", "中": "MIDDLE", "末": "LATE", "底": "LATE"}.get(segment_char or "")
        if segment is None:
            return {"resolution_status": "UNRESOLVED", "granularity": "UNKNOWN"}
        if first and first.isdigit():
            month = int(first)
            if not 1 <= month <= 12:
                return {"month": month, "resolution_status": "UNRESOLVED", "granularity": "UNKNOWN"}
            year = _year_for_month(segment_text, found.start, month, anchor)
        else:
            year, month = _shift_month(anchor.year, anchor.month, 1 if first in {"下", "下个"} else 0)
        return {
            "year": year,
            "month": month,
            "day": None,
            "hour": None,
            "minute": None,
            "segment": segment,
            "resolved_at": None,
            "granularity": "MONTH_SEGMENT",
            "resolution_status": "RESOLVED",
            "ambiguity_reason": None,
            "candidates": [],
        }
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
    if kind == "FULL_MONTH":
        if hour_minute is not None:
            return {
                "resolution_status": "UNRESOLVED",
                "ambiguity_reason": "DATE",
                "granularity": "UNKNOWN",
                "resolved_at": None,
                "candidates": [],
            }
        month_text = found.groups[0] if found.groups else None
        month = int(month_text) if month_text and month_text.isdigit() else 0
        if not 1 <= month <= 12:
            return {"resolution_status": "UNRESOLVED", "granularity": "UNKNOWN"}
        year = _year_for_month(segment_text, found.start, month, anchor)
        return {
            "year": year,
            "month": month,
            "day": None,
            "hour": None,
            "minute": None,
            "resolved_at": None,
            "granularity": "FULL_MONTH",
            "resolution_status": "RESOLVED",
            "ambiguity_reason": None,
            "candidates": [],
        }
    if kind == "RELATIVE_WEEK":
        return {
            "resolution_status": "RESOLVED",
            "granularity": "UNKNOWN",
            "resolved_at": None,
            "ambiguity_reason": None,
            "candidates": [],
        }
    if kind == "RELATIVE_DAY":
        offsets = {"今天": 0, "今日": 0, "刚刚": 0, "刚才": 0, "方才": 0, "明天": 1, "后天": 2, "大后天": 3}
        key = next(name for name in offsets if found.raw_text.startswith(name))
        target = anchor.date() + timedelta(days=offsets[key])
        return _dated(target.year, target.month, target.day, hour_minute, anchor)
    if kind == "RELATIVE_WEEKDAY":
        prefix = found.raw_text[0] if found.raw_text[0] in {"下", "本", "这"} else ""
        weekday = re.match(r"(?:下|本|这)?(?:周|星期|礼拜)([一二三四五六日天])", found.raw_text)
        if weekday is None:
            return {"resolution_status": "UNRESOLVED", "granularity": "UNKNOWN"}
        day_name = weekday.group(1)
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


def _dated(year: int, month: int, day: int, clock: tuple[int, int] | None, anchor: datetime) -> dict[str, object]:
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


def _is_just_now(span: FoundSpan | StoredMention) -> bool:
    # Scanner-owned only: a model quote merged across 刚刚 and a date stays a date.
    return span.kind == "RELATIVE_DAY" and span.raw_text.startswith(_JUST_NOW)


def _bind_role(text: str, found: FoundSpan, model_role: TimeRole) -> tuple[TimeRole, ActionStatus, str | None]:
    clause = _clause(text, found.start)
    if _is_just_now(found):
        # The moment the reported event happened, never a time to follow up.
        return "OTHER", "COMPLETED", None
    if _meeting_context_time(text, found):
        return "OTHER", "COMPLETED", None
    if (
        found.raw_text.startswith(("今天", "今日"))
        and re.search(r"找|联系|确认|电话跟进", clause)
        and "再" not in clause
    ):
        if re.search(r"已|已经|完成了|联系了|确认了|找了", clause):
            return "OTHER", "COMPLETED", None
        if re.search(
            r"(?:计划|准备|将|打算|要|会)(?:今天|今日|稍后|下午|上午|晚上)?(?:再)?(?:找|联系|确认|电话跟进)", clause
        ):
            return "SALES_FOLLOW_UP", "PLANNED", None
        return "SALES_FOLLOW_UP", "UNKNOWN", "STATUS"
    before = clause[: max(0, found.start - _clause_start(text, found.start))]
    # Customer speech names its subject or verb before the time; "周四找陈老师对齐内部反馈"
    # is a sales step whose object merely contains 反馈.
    commitment = r"反馈|预计|承诺|会完成"
    if re.search(commitment, clause) and (re.search(r"老师|总|经理|客户", before) or re.search(commitment, before)):
        return "CUSTOMER_COMMITMENT", "COMMITTED", None
    action_after = text[found.end :]
    customer = r"(?:客户|[\u4e00-\u9fff]{1,8}(?:老师|总|经理|工))"
    verb = r"(?:会|将|再)?(?:找|联系|回复|反馈|发送|给|完成|发|交|确认|采购|支付)"
    after_actor = action_after.lstrip(" ，,、\t\n")
    if (re.search(customer + r"\s*$", before) and re.match(r"[\s，,、]*" + verb, action_after)) or (
        not re.match(verb, after_actor) and re.match(customer + verb, after_actor)
    ):
        return "CUSTOMER_COMMITMENT", "COMMITTED", None
    if re.search(r"再找|再联系|等\s*$", before) or re.match(r"[\s，,、]*(再)?(找|联系)", action_after):
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
        if (
            mention.role == "OTHER"
            and mention.ambiguity_reason != "ROLE"
            and any(item.action_id == mention.action_id and item.role != "OTHER" for item in mentions)
        ):
            # A broad model action quote may also cover communication background.
            # Keep its audit link, but never let it replace the actionable date.
            continue
        action = next((item for item in actions if item.action_id == mention.action_id), None)
        if action is None:
            continue
        action.temporal_mention_id = mention.mention_id
        if mention.role == "CUSTOMER_COMMITMENT":
            action.owner_role = "CUSTOMER"
            action.action_status = "COMMITTED"
        elif mention.role == "SALES_FOLLOW_UP":
            action.owner_role = "SALES"
            if mention.ambiguity_reason == "STATUS":
                action.action_status = "UNKNOWN"
            elif action.action_status != "COMPLETED":
                action.action_status = "PLANNED"
        elif mention.role == "INTERNAL_ACTION":
            action.owner_role = "INTERNAL"
        elif mention.role == "OTHER":
            action.owner_role = "OTHER"
            if mention.ambiguity_reason != "ROLE":
                action.action_status = "COMPLETED"


def _guard_conflicting_dates(mentions: list[StoredMention], actions: list[StoredAction]) -> None:
    """Distinct dates conflict only within one action; equivalents retain provenance."""

    for action in actions:
        active = [
            item
            for item in mentions
            if item.state == "ACTIVE" and item.action_id == action.action_id and item.role == "SALES_FOLLOW_UP"
        ]
        if len(active) < 2:
            continue
        resolved = [item for item in active if item.resolution_status == "RESOLVED"]
        conditions = [
            item
            for item in active
            if item.kind == "UNKNOWN" and item.resolution_status == "UNRESOLVED" and not item.candidates
        ]
        dates = {(item.resolved_at, item.granularity) for item in resolved}
        if len(dates) == 1 and len(resolved) + len(conditions) == len(active):
            for item in conditions:
                item.role = "OTHER"
            action.temporal_mention_id = resolved[0].mention_id
            continue
        for item in active:
            item.resolution_status = "AMBIGUOUS"
            item.ambiguity_reason = item.ambiguity_reason if item.ambiguity_reason in {"ROLE", "STATUS"} else "DATE"
            item.candidates = []


def _supersede_replacements(text: str, mentions: list[StoredMention], actions: list[StoredAction]) -> None:
    marker = _REPLACEMENT.search(text)
    if marker is None:
        return
    previous = [item for item in mentions if item.quote_end <= marker.start() and item.role == "SALES_FOLLOW_UP"]
    current = [item for item in mentions if item.quote_start >= marker.end() and item.role == "SALES_FOLLOW_UP"]
    if not previous or len(current) != 1:
        return
    replacement = current[0]
    target = previous[-1]
    replacement.correction_of = target.mention_id
    for item in previous:
        if item.action_id == target.action_id:
            item.state = "SUPERSEDED"
    old_action = _action_for(target, actions)
    new_action = _action_for(replacement, actions)
    if old_action is not None and new_action is not None and old_action.action_id != new_action.action_id:
        old_action.state = "SUPERSEDED"
    elif old_action is not None:
        old_action.temporal_mention_id = replacement.mention_id


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


def _primary_action_id(content_json: dict[str, object]) -> str | None:
    raw = content_json.get("temporal_evidence")
    return (
        raw.get("primary_action_id")
        if isinstance(raw, dict) and isinstance(raw.get("primary_action_id"), str)
        else None
    )


def _primary_sales(
    mentions: list[StoredMention], actions: list[StoredAction], primary_action_id: str | None = None
) -> tuple[StoredMention | None, StoredAction] | list[tuple[StoredMention | None, StoredAction]] | None:
    sales = [
        item
        for item in actions
        if item.state == "ACTIVE" and item.owner_role == "SALES" and item.action_status == "PLANNED"
    ]
    if not sales:
        return None
    paired = [
        (
            next(
                (item for item in mentions if item.state == "ACTIVE" and item.mention_id == action.temporal_mention_id),
                None,
            ),
            action,
        )
        for action in sales
    ]
    if primary_action_id:
        selected = next((item for item in paired if item[1].action_id == primary_action_id), None)
        if selected is not None:
            return selected
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
    primary_action_id = _primary_action_id(draft.content_json)
    draft.content_json["temporal_evidence"] = {
        "version": PROTOCOL_VERSION,
        "mentions": [item.model_dump(mode="json") for item in mentions],
        "actions": [item.model_dump(mode="json") for item in actions],
        "primary_action_id": primary_action_id,
    }


def _stored_mention(item: object) -> StoredMention:
    return item if isinstance(item, StoredMention) else StoredMention.model_validate(item)


def _stored_action(item: object) -> StoredAction:
    return item if isinstance(item, StoredAction) else StoredAction.model_validate(item)


def _read_mention(item: object) -> ModelTemporalMention:
    try:
        return item if isinstance(item, ModelTemporalMention) else ModelTemporalMention.model_validate(item)
    except ValueError as exc:
        raise TemporalContractError("illegal temporal mention") from exc


def _read_action(item: object) -> ModelDraftAction:
    try:
        return item if isinstance(item, ModelDraftAction) else ModelDraftAction.model_validate(item)
    except ValueError as exc:
        raise ActionContractError("illegal temporal action") from exc


def _mention_span(text: str, item: object) -> tuple[int, int]:
    mention = _read_mention(item)
    start, end = _snap_span(text, mention)
    return start, end


def _snap_span(
    text: str, mention: ModelTemporalMention, segments: list[tuple[int, int]] | None = None
) -> tuple[int, int]:
    return _locate_quote(
        text,
        mention.quote_start,
        mention.quote_end,
        mention.raw_text,
        segments,
        TemporalContractError,
        "temporal span is not in the source",
    )


def _action_span(text: str, action: ModelDraftAction, segments: list[tuple[int, int]] | None = None) -> tuple[int, int]:
    return _locate_quote(
        text,
        action.quote_start,
        action.quote_end,
        action.evidence_quote,
        segments,
        ActionContractError,
        "action quote is not in the source",
    )


def _locate_quote(
    text: str,
    start: int,
    end: int,
    raw: str,
    segments: list[tuple[int, int]] | None,
    error: type[TemporalContractError],
    message: str,
) -> tuple[int, int]:
    """Bind a verbatim quote to source offsets; the model's offset is only a locality hint.

    An exact slice wins. Otherwise the quote binds to the nearest occurrence that
    lies inside one source segment; absence or an equidistant tie is fabricated.
    """

    if not raw:
        raise error(message)
    if 0 <= start < end <= len(text) and text[start:end] == raw:
        return start, end
    bounds = segments if segments is not None else [(0, len(text))]
    distances: list[tuple[int, int]] = []
    found = text.find(raw)
    while found >= 0:
        if any(left <= found and found + len(raw) <= right for left, right in bounds):
            distances.append((abs(found - start), found))
        found = text.find(raw, found + 1)
    distances.sort()
    if not distances or (len(distances) > 1 and distances[0][0] == distances[1][0]):
        raise error(message)
    nearest = distances[0][1]
    return nearest, nearest + len(raw)


def _extend_clock(text: str, end: int) -> int:
    match = _CLOCK.match(text[end:])
    if match is not None and match.group(0).strip(" 的"):
        return end + match.end()
    period = _PERIOD.match(text[end:])
    if period is not None and period.group(0).strip(" 的"):
        return end + period.end()
    return end


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


def _date_answer_action(mention: StoredMention, actions: list[StoredAction]) -> StoredAction | None:
    """The planned sales step a date answer would replace; asking and accepting share it."""

    action = _action_for(mention, actions)
    if action is None or action.owner_role != "SALES" or action.action_status != "PLANNED":
        return None
    return action


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
    if not ordered or ordered[0].mention_id != mention_id or side not in {"customer", "sales"}:
        raise TemporalContractError("unknown temporal choice")
    first = ordered[0]
    first.role = "CUSTOMER_COMMITMENT" if side == "customer" else "SALES_FOLLOW_UP"
    chosen = [first]
    same_action = [item for item in ordered[1:] if item.action_id == first.action_id]
    if same_action:
        for item in same_action:
            item.role = first.role
        chosen.extend(same_action)
    elif len(ordered) >= 2:
        second = ordered[1]
        second.role = "SALES_FOLLOW_UP" if side == "customer" else "CUSTOMER_COMMITMENT"
        chosen.append(second)
    for item in chosen:
        if item.answer_gap == "DATE_CONFLICT":
            item.ambiguity_reason = "DATE"
            item.resolution_status = "AMBIGUOUS"
        elif item.candidates:
            item.ambiguity_reason = "MONTH"
            item.resolution_status = "AMBIGUOUS"
        elif item.resolved_at is not None:
            item.ambiguity_reason = None
            item.resolution_status = "RESOLVED"
        else:
            item.ambiguity_reason = None
            if item.granularity in {"MONTH_SEGMENT", "FULL_MONTH"}:
                item.resolution_status = "RESOLVED"

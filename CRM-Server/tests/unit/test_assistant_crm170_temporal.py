# ruff: noqa: RUF001
"""CRM-170: structured model temporal fields, server computation/cross-check, and shared-time action merge."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.services.assistant.action_evidence import SourceSegment, parse_deadline
from app.services.assistant.contracts import DraftField, TaskDraft
from app.services.assistant.llm_contracts import (
    ModelTemporalMention,
    StructuredFollowUp,
    StructuredMeeting,
)
from app.services.assistant.model_transport import _strict_json_schema
from app.services.assistant.temporal_evidence import (
    TemporalContractError,
    TemporalFields,
    apply_temporal_answer,
    apply_temporal_choice,
    attach_model_evidence,
    compute_temporal,
    confirmation_time_labels,
    find_time_spans,
    is_temporal_supplement_candidate,
    project_draft,
    resolved_sales_follow_up,
    temporal_answer_target,
    temporal_supplement_target,
    temporal_waiting,
    validate_temporal_quotes,
)

ANCHOR = datetime(2026, 11, 26, 10, 0)


def _quote(
    text: str, raw: str, *, role: str = "SALES_FOLLOW_UP", action_ref: str = "", **extra: object
) -> dict[str, object]:
    start = text.index(raw)
    return {
        "raw_text": raw,
        "quote_start": start,
        "quote_end": start + len(raw),
        "kind": "UNKNOWN",
        "role": role,
        "owner": "我",
        "action_ref": action_ref,
        "confidence": 1.0,
        **extra,
    }


def _action(
    text: str,
    quote: str,
    *,
    ref: str,
    action_text: str | None = None,
    owner_role: str = "SALES",
    owner_text: str = "我",
    action_status: str = "PLANNED",
) -> dict[str, object]:
    start = text.index(quote)
    return {
        "action_ref": ref,
        "owner_role": owner_role,
        "owner_text": owner_text,
        "action_text": action_text or quote,
        "evidence_quote": quote,
        "quote_start": start,
        "quote_end": start + len(quote),
        "action_status": action_status,
    }


def _attach(
    text: str,
    *,
    mentions: list[object] | None = None,
    actions: list[object] | None = None,
    anchor: datetime = ANCHOR,
) -> TaskDraft:
    draft = TaskDraft(
        content=DraftField(status="CANDIDATE", value=text),
        content_json={"content": text},
        source_segments=[text],
        source_records=[SourceSegment(segment_id="s1", text=text, recorded_at=anchor)],
        quality_score=DraftField(status="CANDIDATE", value="85"),
    )
    attach_model_evidence(
        draft,
        segment_id="s1",
        segment_text=text,
        anchor=anchor,
        mentions=mentions or [],
        actions=actions or [],
    )
    return draft


# --- AC 1: Original sample & shared-time action merging ---


@pytest.mark.parametrize("link_both", [False, True])
def test_ac1_original_sample_merges_shared_time_sales_actions_without_primary_wait(link_both: bool) -> None:
    text = "北京川三今天已经完成回款。明年 2 月 26 号再找尚老师跟进使用情况，同时提供新版本进行更新。"
    actions = [
        _action(text, "找尚老师跟进使用情况", ref="a1"),
        _action(text, "提供新版本进行更新", ref="a2"),
    ]
    mentions = [
        _quote(text, "明年 2 月 26 号", action_ref="a1", year_offset=1, month=2, day=26),
    ]
    if link_both:
        mentions.append(_quote(text, "明年 2 月 26 号", action_ref="a2", year_offset=1, month=2, day=26))

    draft = _attach(text, mentions=mentions, actions=actions)

    assert temporal_waiting(draft) is None
    assert draft.next_action.value == "找尚老师跟进使用情况，并提供新版本进行更新"
    assert draft.next_follow_time.value == "明年 2 月 26 号"
    assert resolved_sales_follow_up(draft) == (datetime(2027, 2, 26), "DATE")
    assert confirmation_time_labels(draft.content_json) == (None, "明年 2 月 26 号")


@pytest.mark.parametrize(
    ("joiner", "second_quote", "second_text"),
    [
        ("，同时", "提供新版本进行更新", "提供新版本进行更新"),
        ("，", "同时提供新版本进行更新", "同时提供新版本进行更新"),
        ("并", "提供新版本进行更新", "提供新版本进行更新"),
        ("，顺便", "提供新版本进行更新", "提供新版本进行更新"),
        ("，另外", "提供新版本进行更新", "提供新版本进行更新"),
        ("，", "提供新版本进行更新", "提供新版本进行更新"),
    ],
)
def test_shared_time_actions_merge_across_approved_joiners(joiner: str, second_quote: str, second_text: str) -> None:
    text = f"明年 2 月 26 号找尚老师跟进使用情况{joiner}{second_quote}。"
    draft = _attach(
        text,
        mentions=[_quote(text, "明年 2 月 26 号", action_ref="a1", year_offset=1, month=2, day=26)],
        actions=[
            _action(text, "找尚老师跟进使用情况", ref="a1"),
            _action(text, second_quote, ref="a2", action_text=second_text),
        ],
    )
    assert temporal_waiting(draft) is None
    assert draft.next_action.value == "找尚老师跟进使用情况，并提供新版本进行更新"
    assert resolved_sales_follow_up(draft) == (datetime(2027, 2, 26), "DATE")


def test_actions_in_different_sentences_do_not_merge() -> None:
    text = "明年 2 月 26 号找尚老师跟进使用情况。另外提供新版本进行更新。"
    draft = _attach(
        text,
        mentions=[_quote(text, "明年 2 月 26 号", action_ref="a1", year_offset=1, month=2, day=26)],
        actions=[
            _action(text, "找尚老师跟进使用情况", ref="a1"),
            _action(text, "提供新版本进行更新", ref="a2"),
        ],
    )
    waiting = temporal_waiting(draft)
    assert waiting is not None and waiting["reason"] == "PRIMARY"


# --- AC 2-6: Model structured temporal fields resolved by compute_temporal ---


@pytest.mark.parametrize(
    ("text", "raw", "fields", "expected"),
    [
        (
            "明年二月二十六号再找尚老师",
            "明年二月二十六号",
            {"year_offset": 1, "month": 2, "day": 26},
            datetime(2027, 2, 26),
        ),
        ("明年2月26再找尚老师", "明年2月26", {"year_offset": 1, "month": 2, "day": 26}, datetime(2027, 2, 26)),
        ("下下周三再找尚老师", "下下周三", {"week_offset": 2, "weekday": 3}, datetime(2026, 12, 9)),
        ("三天后再找尚老师", "三天后", {"day_offset": 3}, datetime(2026, 11, 29)),
        ("2/26 再找尚老师", "2/26", {"month": 2, "day": 26}, datetime(2027, 2, 26)),
    ],
)
def test_ac2_to_ac6_structured_temporal_expressions_resolve_accurately(
    text: str, raw: str, fields: dict[str, object], expected: datetime
) -> None:
    draft = _attach(
        text,
        mentions=[_quote(text, raw, action_ref="a1", **fields)],
        actions=[_action(text, "找尚老师", ref="a1")],
    )
    assert temporal_waiting(draft) is None
    assert resolved_sales_follow_up(draft) == (expected, "DATE")
    assert confirmation_time_labels(draft.content_json) == (None, raw)


def test_ac4_scanner_never_misreads_xia_xia_zhousan_as_next_week() -> None:
    assert find_time_spans("下下周三再找尚老师") == []


# --- AC 7 & AC 8: Vague & Invalid dates ---


def test_ac7_vague_expression_asks_for_specific_date() -> None:
    text = "春节后再找尚老师"
    draft = _attach(
        text,
        mentions=[_quote(text, "春节后", action_ref="a1", vague=True)],
        actions=[_action(text, "找尚老师", ref="a1")],
    )
    waiting = temporal_waiting(draft)
    assert waiting is not None
    assert waiting["reason"] == "DATE"
    assert "春节后" in str(waiting["prompt"])
    assert resolved_sales_follow_up(draft) == (None, "UNKNOWN")


def test_ac8_invalid_calendar_date_enters_invalid_date_wait() -> None:
    text = "2 月 30 号再找尚老师"
    draft = _attach(
        text,
        mentions=[_quote(text, "2 月 30 号", action_ref="a1", month=2, day=30)],
        actions=[_action(text, "找尚老师", ref="a1")],
    )
    waiting = temporal_waiting(draft)
    assert waiting is not None
    assert waiting["reason"] == "DATE"
    assert waiting["gap"] == "INVALID_DATE"
    assert waiting["prompt"] == "“2 月 30 号”不是有效日期，请补充具体日期。"
    assert resolved_sales_follow_up(draft) == (None, "UNKNOWN")


# --- AC 9: Distinct-date actions do not merge and show dated PRIMARY labels ---


def test_ac9_distinct_date_actions_stay_separate_with_dated_primary_labels() -> None:
    text = "下周三找陈老师，下个月 5 号给客户发报价"
    draft = _attach(
        text,
        mentions=[
            _quote(text, "下周三", action_ref="a1", week_offset=1, weekday=3),
            _quote(text, "下个月 5 号", action_ref="a2", month_offset=1, day=5),
        ],
        actions=[
            _action(text, "找陈老师", ref="a1"),
            _action(text, "给客户发报价", ref="a2"),
        ],
    )
    waiting = temporal_waiting(draft)
    assert waiting is not None
    assert waiting["reason"] == "PRIMARY"
    labels = [item["label"] for item in waiting["candidates"]]
    assert labels == ["找陈老师（2026-12-02）", "给客户发报价（2026-12-05）"]


# --- AC 10: Model vs regex disagreement asks AMBIGUOUS DATE and discards both ---


def test_ac10_model_and_regex_date_disagreement_asks_and_writes_neither() -> None:
    text = "下周三再找尚老师"
    draft = _attach(
        text,
        mentions=[_quote(text, "下周三", action_ref="a1", week_offset=2, weekday=3)],
        actions=[_action(text, "找尚老师", ref="a1")],
    )
    waiting = temporal_waiting(draft)
    assert waiting is not None
    assert waiting["reason"] == "DATE"
    assert resolved_sales_follow_up(draft) == (None, "UNKNOWN")
    mention = draft.content_json["temporal_evidence"]["mentions"][0]
    assert mention["resolution_status"] == "AMBIGUOUS"
    assert mention["ambiguity_reason"] == "DATE"
    assert mention["resolved_at"] is None


def test_ac10_model_and_regex_clock_disagreement_asks_and_writes_neither() -> None:
    text = "明天下午3点再找尚老师"
    draft = _attach(
        text,
        mentions=[_quote(text, "明天下午3点", action_ref="a1", day_offset=1, clock="10:00")],
        actions=[_action(text, "找尚老师", ref="a1")],
    )
    waiting = temporal_waiting(draft)
    assert waiting is not None
    assert waiting["reason"] == "DATE"
    assert resolved_sales_follow_up(draft) == (None, "UNKNOWN")


# --- Schema fail-closed, compute_temporal segments/clocks, and strict JSON schema ---


@pytest.mark.parametrize(
    "bad_fields",
    [
        {"month": 13, "day": 1},
        {"month": 2, "day": 32},
        {"week_offset": 1, "weekday": 8},
        {"year": 1999, "month": 1, "day": 1},
        {"day_offset": 500},
        {"segment": "QUARTER"},
        {"iso_date": "2027-02-26"},
    ],
)
def test_model_temporal_mention_fails_closed_on_out_of_range_or_iso_fields(bad_fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ModelTemporalMention.model_validate(
            {
                "raw_text": "明年2月26号",
                "quote_start": 0,
                "quote_end": 7,
                "kind": "UNKNOWN",
                "role": "SALES_FOLLOW_UP",
                "owner": "我",
                "confidence": 1.0,
                **bad_fields,
            }
        )


def test_strict_json_schema_accepts_structured_follow_up_and_meeting() -> None:
    follow_up_schema = _strict_json_schema(StructuredFollowUp.model_json_schema())
    meeting_schema = _strict_json_schema(StructuredMeeting.model_json_schema())
    assert follow_up_schema["additionalProperties"] is False
    assert meeting_schema["additionalProperties"] is False


def test_compute_temporal_handles_segments_and_clocks() -> None:
    early = compute_temporal(TemporalFields(month=3, segment="EARLY"), ANCHOR)
    assert early is not None and early.status == "RESOLVED" and early.granularity == "MONTH_SEGMENT"
    assert (early.year, early.month, early.segment) == (2027, 3, "EARLY")

    whole = compute_temporal(TemporalFields(month=12, segment="WHOLE_MONTH"), ANCHOR)
    assert whole is not None and whole.status == "RESOLVED" and whole.granularity == "FULL_MONTH"
    assert (whole.year, whole.month, whole.segment) == (2026, 12, None)

    with_clock = compute_temporal(TemporalFields(day_offset=3, clock="14:30"), ANCHOR)
    assert with_clock is not None and with_clock.status == "RESOLVED" and with_clock.granularity == "DATETIME"
    assert with_clock.resolved_date == date(2026, 11, 29) and with_clock.clock == (14, 30)

    bad_clock = compute_temporal(TemporalFields(day_offset=1, clock="25:00"), ANCHOR)
    assert bad_clock is not None and bad_clock.status == "INVALID_DATE"

    seg_clock = compute_temporal(TemporalFields(month=12, segment="MID", clock="10:00"), ANCHOR)
    assert seg_clock is not None and seg_clock.status == "UNRESOLVED" and seg_clock.ambiguity_reason == "DATE"


# --- Edge cases from idea.md ---


def test_edge_merged_action_then_date_correction_keeps_merged_text() -> None:
    text = "北京川三今天已经完成回款。明年 2 月 26 号再找尚老师跟进使用情况，同时提供新版本进行更新。"
    draft = _attach(
        text,
        mentions=[_quote(text, "明年 2 月 26 号", action_ref="a1", year_offset=1, month=2, day=26)],
        actions=[
            _action(text, "找尚老师跟进使用情况", ref="a1"),
            _action(text, "提供新版本进行更新", ref="a2"),
        ],
    )
    target = temporal_supplement_target(draft)
    assert target is not None
    reply = SourceSegment(segment_id="s2", text="改为明年 3 月 5 号", recorded_at=ANCHOR)
    draft.source_records.append(reply)
    draft.source_segments.append(reply.text)
    source_text = "\n".join(record.text for record in draft.source_records)
    apply_temporal_answer(
        draft,
        target_id=target,
        source_text=source_text,
        answer_segment_id="s2",
        mentions=[_quote(source_text, "明年 3 月 5 号", year_offset=1, month=3, day=5)],
        actions=[],
    )
    assert temporal_waiting(draft) is None
    assert draft.next_action.value == "找尚老师跟进使用情况，并提供新版本进行更新"
    assert resolved_sales_follow_up(draft) == (datetime(2027, 3, 5), "DATE")
    active = [
        item for item in draft.content_json["temporal_evidence"]["mentions"] if item["state"] == "ACTIVE"
    ]
    assert any(item["correction_of"] is not None for item in active)


def test_edge_year_rollover_december_saying_february() -> None:
    dec_anchor = datetime(2026, 12, 15, 10, 0)
    text = "2月10号再找尚老师"
    draft = _attach(
        text,
        anchor=dec_anchor,
        mentions=[_quote(text, "2月10号", action_ref="a1", month=2, day=10)],
        actions=[_action(text, "找尚老师", ref="a1")],
    )
    assert resolved_sales_follow_up(draft) == (datetime(2027, 2, 10), "DATE")


def test_edge_structured_fields_cannot_bypass_quote_validation() -> None:
    bad_mention = ModelTemporalMention(
        raw_text="明年2月26号",
        quote_start=0,
        quote_end=7,
        kind="UNKNOWN",
        role="SALES_FOLLOW_UP",
        owner="我",
        confidence=1.0,
        year_offset=1,
        month=2,
        day=26,
    )
    with pytest.raises(TemporalContractError):
        validate_temporal_quotes("明天再找尚老师", [bad_mention])


def test_edge_customer_commitment_and_sales_action_same_sentence_never_merge() -> None:
    text = "明年 2 月 26 号客户王经理反馈评估结果，同时我方跟进使用情况。"
    draft = _attach(
        text,
        mentions=[
            _quote(
                text,
                "明年 2 月 26 号",
                role="CUSTOMER_COMMITMENT",
                action_ref="a1",
                year_offset=1,
                month=2,
                day=26,
            ),
        ],
        actions=[
            _action(
                text,
                "客户王经理反馈评估结果",
                ref="a1",
                action_text="反馈评估结果",
                owner_role="CUSTOMER",
                owner_text="客户王经理",
                action_status="COMMITTED",
            ),
            _action(text, "我方跟进使用情况", ref="a2", action_text="跟进使用情况"),
        ],
    )
    commitments = draft.content_json["customer_commitments"]
    assert len(commitments) == 1
    assert "反馈评估结果" in commitments[0]["text"]
    assert "跟进使用情况" not in commitments[0]["text"]
    assert draft.next_action.value == "跟进使用情况"


# --- Non-empty next_follow_time safeguard ---


def test_safeguard_blocks_silent_empty_follow_time_and_accepts_unbound_answer() -> None:
    text = "明年 2 月 26 号找尚老师跟进使用情况。另外给王总发演示包。"
    draft = _attach(
        text,
        mentions=[_quote(text, "明年 2 月 26 号", action_ref="a1", year_offset=1, month=2, day=26)],
        actions=[
            _action(text, "找尚老师跟进使用情况", ref="a1"),
            _action(text, "给王总发演示包", ref="a2"),
        ],
    )
    primary_wait = temporal_waiting(draft)
    assert primary_wait is not None and primary_wait["reason"] == "PRIMARY"
    second_choice = next(item["id"] for item in primary_wait["candidates"] if "演示包" in item["label"])
    apply_temporal_choice(draft, second_choice)

    safeguard_wait = temporal_waiting(draft)
    assert safeguard_wait is not None
    assert safeguard_wait["reason"] == "DATE"
    assert safeguard_wait["business_action_id"] is not None
    assert "2027-02-26" in str(safeguard_wait["prompt"])
    assert not any("未指定跟进日期" in notice for notice in draft.content_json["temporal_notices"])

    target = temporal_answer_target(draft)
    assert target is not None
    reply = SourceSegment(segment_id="s2", text="下下周三", recorded_at=ANCHOR)
    draft.source_records.append(reply)
    draft.source_segments.append(reply.text)
    source_text = "\n".join(record.text for record in draft.source_records)
    apply_temporal_answer(
        draft,
        target_id=target,
        source_text=source_text,
        answer_segment_id="s2",
        mentions=[_quote(source_text, "下下周三", week_offset=2, weekday=3)],
        actions=[],
    )
    assert temporal_waiting(draft) is None
    assert draft.next_follow_time.status == "ACCEPTED"
    assert resolved_sales_follow_up(draft) == (datetime(2026, 12, 9), "DATE")


def test_safeguard_respects_explicitly_none_next_follow_time() -> None:
    text = "明年 2 月 26 号找尚老师跟进使用情况。另外给王总发演示包。"
    draft = _attach(
        text,
        mentions=[_quote(text, "明年 2 月 26 号", action_ref="a1", year_offset=1, month=2, day=26)],
        actions=[
            _action(text, "找尚老师跟进使用情况", ref="a1"),
            _action(text, "给王总发演示包", ref="a2"),
        ],
    )
    primary_wait = temporal_waiting(draft)
    assert primary_wait is not None
    second_choice = next(item["id"] for item in primary_wait["candidates"] if "演示包" in item["label"])
    apply_temporal_choice(draft, second_choice)
    draft.next_follow_time = DraftField(status="EXPLICITLY_NONE", value="暂不安排")
    project_draft(draft)
    assert temporal_waiting(draft) is None


# --- Unified action_evidence.parse_deadline ---


def test_unified_parse_deadline_delegates_to_single_temporal_engine() -> None:
    assert parse_deadline("明年 2 月 26 号", anchor=ANCHOR) == (datetime(2027, 2, 26), "DATE")
    assert parse_deadline("下周三下午3点", anchor=ANCHOR) == (datetime(2026, 12, 2, 15, 0), "DATETIME")
    assert parse_deadline("2027-02-26 14:30:15", anchor=ANCHOR) == (datetime(2027, 2, 26, 14, 30, 15), "DATETIME")
    assert parse_deadline("2 月 30 号", anchor=ANCHOR) == (None, "UNKNOWN")
    assert parse_deadline("明天下午", anchor=ANCHOR) == (None, "UNKNOWN")
    assert parse_deadline("下下周三", anchor=ANCHOR) == (None, "UNKNOWN")


def test_legacy_model_temporal_mention_without_structured_fields_keeps_regex_behavior() -> None:
    legacy = ModelTemporalMention.model_validate(
        {
            "raw_text": "明年 2 月 26 号",
            "quote_start": 0,
            "quote_end": 11,
            "kind": "EXPLICIT_DATE",
            "role": "SALES_FOLLOW_UP",
            "owner": "我",
            "action_ref": "a1",
            "confidence": 1.0,
        }
    )
    assert legacy.year_offset is None and legacy.vague is False and legacy.segment is None and legacy.clock is None
    text = "明年 2 月 26 号找尚老师跟进"
    draft = _attach(text, mentions=[legacy], actions=[_action(text, "找尚老师跟进", ref="a1")])
    assert temporal_waiting(draft) is None
    assert resolved_sales_follow_up(draft) == (datetime(2027, 2, 26), "DATE")


# --- Review fix regressions (CRM-170) ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("下下周三", True),
        ("三天后", True),
        ("2/26", True),
        ("明年2月26", True),
        ("明年二月二十六号", True),
        ("改为下下周三", True),
        ("改为2/26", True),
        ("下下周三下午3点", True),
        ("不是明天，改为下下周三", True),
        ("本月 30 号", True),
        ("改为2026年12月6日", True),
        ("补充一个背景：客户完成安全测评", False),
        ("另外客户12月6号付款", False),
        ("下下周三发报价给客户", False),
        ("刚才", False),
        ("", False),
    ],
)
def test_is_temporal_supplement_candidate_admits_compact_model_dates_only(text: str, expected: bool) -> None:
    assert is_temporal_supplement_candidate(text) is expected


def test_apply_temporal_answer_normalizes_stored_only_kinds_in_fallback_quotes() -> None:
    for reply_text, expected_kind in (("明年2月26号", "EXPLICIT_DATE"), ("本月底", "MONTH_SEGMENT")):
        source = "春节后联系客户"
        draft = _attach(
            source,
            mentions=[_quote(source, "春节后", action_ref="a1", vague=True)],
            actions=[_action(source, "联系客户", ref="a1")],
        )
        target = temporal_answer_target(draft)
        assert target is not None
        reply = SourceSegment(segment_id="s2", text=reply_text, recorded_at=ANCHOR)
        draft.source_records.append(reply)
        draft.source_segments.append(reply.text)
        apply_temporal_answer(
            draft,
            target_id=target,
            source_text="\n".join(record.text for record in draft.source_records),
            answer_segment_id="s2",
            mentions=[],
            actions=[],
        )
        bundle = draft.content_json["temporal_evidence"]
        added = next(item for item in bundle["mentions"] if item["source_segment_id"] == "s2")
        assert added["source_quotes"][0]["kind"] == expected_kind


@pytest.mark.parametrize(
    ("raw", "kwargs", "expected_date"),
    [
        ("前天", {"day_offset": -2}, date(2026, 11, 24)),
        ("上周三", {"week_offset": -1, "weekday": 3}, date(2026, 11, 18)),
        ("上个月15号", {"month_offset": -1, "day": 15}, date(2026, 10, 15)),
    ],
)
def test_model_temporal_mention_accepts_negative_relative_offsets(
    raw: str, kwargs: dict[str, object], expected_date: date
) -> None:
    mention = ModelTemporalMention(
        raw_text=raw,
        quote_start=0,
        quote_end=len(raw),
        kind="UNKNOWN",
        role="COMPLETED_EVENT",
        confidence=0.95,
        **kwargs,
    )
    computed = compute_temporal(mention, ANCHOR)
    assert computed is not None
    assert computed.status == "RESOLVED"
    assert computed.resolved_date == expected_date


@pytest.mark.parametrize(
    "bad_kwargs",
    [
        {"day_offset": -367},
        {"week_offset": -5, "weekday": 1},
        {"month_offset": -13, "day": 1},
    ],
)
def test_model_temporal_mention_rejects_out_of_range_negative_offsets(bad_kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ModelTemporalMention(
            raw_text="过去某天",
            quote_start=0,
            quote_end=4,
            kind="UNKNOWN",
            role="COMPLETED_EVENT",
            **bad_kwargs,
        )


def test_second_clause_shared_time_binds_to_first_action_and_merges() -> None:
    text = "给尚老师发报价，同时明年 2 月 26 号跟进使用情况。"
    draft = _attach(
        text,
        mentions=[
            _quote(text, "明年 2 月 26 号", action_ref="a1", year_offset=1, month=2, day=26),
            _quote(text, "明年 2 月 26 号", action_ref="a2", year_offset=1, month=2, day=26),
        ],
        actions=[
            _action(text, "给尚老师发报价", ref="a1"),
            _action(text, "明年 2 月 26 号跟进使用情况", ref="a2", action_text="跟进使用情况"),
        ],
    )
    assert temporal_waiting(draft) is None
    assert resolved_sales_follow_up(draft) == (datetime(2027, 2, 26), "DATE")
    assert draft.next_action.value == "给尚老师发报价，并跟进使用情况"
    active_actions = [item for item in draft.content_json["temporal_evidence"]["actions"] if item["state"] == "ACTIVE"]
    assert len(active_actions) == 1


def test_shared_time_merge_still_blocks_when_another_active_mention_intervenes() -> None:
    text = "明天给尚老师发报价，同时下周五跟进使用情况。"
    draft = _attach(
        text,
        mentions=[
            _quote(text, "明天", action_ref="a1", day_offset=1),
            _quote(text, "下周五", action_ref="a2", week_offset=1, weekday=5),
        ],
        actions=[
            _action(text, "明天给尚老师发报价", ref="a1", action_text="给尚老师发报价"),
            _action(text, "下周五跟进使用情况", ref="a2", action_text="跟进使用情况"),
        ],
    )
    wait = temporal_waiting(draft)
    assert wait is not None and wait["reason"] == "PRIMARY"


def test_cross_check_marks_clock_and_granularity_conflicts_ambiguous() -> None:
    # Scanner resolves DATE (no clock), model supplies clock -> granularity conflict asks.
    text_date = "明天找尚老师跟进"
    draft_extra_clock = _attach(
        text_date,
        mentions=[_quote(text_date, "明天", action_ref="a1", day_offset=1, clock="15:00")],
        actions=[_action(text_date, "找尚老师跟进", ref="a1")],
    )
    wait_extra = temporal_waiting(draft_extra_clock)
    assert wait_extra is not None and wait_extra["reason"] == "DATE"
    assert resolved_sales_follow_up(draft_extra_clock) == (None, "UNKNOWN")

    # Scanner resolves DATETIME 15:00, model omits clock -> granularity conflict asks.
    text_dt = "明天下午3点找尚老师跟进"
    draft_missing_clock = _attach(
        text_dt,
        mentions=[_quote(text_dt, "明天下午3点", action_ref="a1", day_offset=1)],
        actions=[_action(text_dt, "找尚老师跟进", ref="a1")],
    )
    wait_missing = temporal_waiting(draft_missing_clock)
    assert wait_missing is not None and wait_missing["reason"] == "DATE"
    assert resolved_sales_follow_up(draft_missing_clock) == (None, "UNKNOWN")

    # Scanner resolves DATETIME 15:00, model supplies 16:00 -> clock conflict asks.
    draft_wrong_clock = _attach(
        text_dt,
        mentions=[_quote(text_dt, "明天下午3点", action_ref="a1", day_offset=1, clock="16:00")],
        actions=[_action(text_dt, "找尚老师跟进", ref="a1")],
    )
    wait_wrong = temporal_waiting(draft_wrong_clock)
    assert wait_wrong is not None and wait_wrong["reason"] == "DATE"

    # Scanner and model agree on DATETIME 15:00 -> RESOLVED.
    draft_agree = _attach(
        text_dt,
        mentions=[_quote(text_dt, "明天下午3点", action_ref="a1", day_offset=1, clock="15:00")],
        actions=[_action(text_dt, "找尚老师跟进", ref="a1")],
    )
    assert temporal_waiting(draft_agree) is None
    assert resolved_sales_follow_up(draft_agree) == (datetime(2026, 11, 27, 15, 0), "DATETIME")


def test_safeguard_wait_invalid_and_unrecognized_replies_do_not_mutate_foreign_mention_or_leak() -> None:
    text = "明年 2 月 26 号找尚老师跟进使用情况。另外给王总发演示包。"
    draft = _attach(
        text,
        mentions=[_quote(text, "明年 2 月 26 号", action_ref="a1", year_offset=1, month=2, day=26)],
        actions=[
            _action(text, "找尚老师跟进使用情况", ref="a1"),
            _action(text, "给王总发演示包", ref="a2"),
        ],
    )
    primary_wait = temporal_waiting(draft)
    assert primary_wait is not None and primary_wait["reason"] == "PRIMARY"
    second_choice = next(item["id"] for item in primary_wait["candidates"] if "演示包" in item["label"])
    apply_temporal_choice(draft, second_choice)

    safeguard_wait = temporal_waiting(draft)
    assert safeguard_wait is not None and safeguard_wait["reason"] == "DATE"
    foreign_mention_id = str(safeguard_wait["mention_id"])
    unbound_action_id = str(safeguard_wait["business_action_id"])

    # 1) Unrecognized reply keeps safeguard wait without mutating a1's mention.
    unrecognized = SourceSegment(segment_id="s2", text="好吧", recorded_at=ANCHOR)
    draft.source_records.append(unrecognized)
    draft.source_segments.append(unrecognized.text)
    apply_temporal_answer(
        draft,
        target_id=foreign_mention_id,
        source_text="\n".join(record.text for record in draft.source_records),
        answer_segment_id="s2",
        mentions=[],
        actions=[],
    )
    mentions_after_unrec = draft.content_json["temporal_evidence"]["mentions"]
    foreign = next(item for item in mentions_after_unrec if item["mention_id"] == foreign_mention_id)
    assert foreign["answer_gap"] is None
    wait_after_unrec = temporal_waiting(draft)
    assert wait_after_unrec is not None and wait_after_unrec["mention_id"] == foreign_mention_id

    # 2) Invalid date reply records INVALID_DATE on a2 without touching a1's mention.
    invalid = SourceSegment(segment_id="s3", text="2月30号", recorded_at=ANCHOR)
    draft.source_records.append(invalid)
    draft.source_segments.append(invalid.text)
    apply_temporal_answer(
        draft,
        target_id=foreign_mention_id,
        source_text="\n".join(record.text for record in draft.source_records),
        answer_segment_id="s3",
        mentions=[],
        actions=[],
    )
    mentions_after_invalid = draft.content_json["temporal_evidence"]["mentions"]
    foreign = next(item for item in mentions_after_invalid if item["mention_id"] == foreign_mention_id)
    assert foreign["answer_gap"] is None
    bad_mention = next(item for item in mentions_after_invalid if item["source_segment_id"] == "s3")
    assert bad_mention["action_id"] == unbound_action_id
    assert bad_mention["ambiguity_reason"] == "INVALID_DATE"
    assert bad_mention["answer_gap"] == "INVALID_DATE"
    wait_after_invalid = temporal_waiting(draft)
    assert wait_after_invalid is not None
    assert wait_after_invalid["reason"] == "DATE"
    assert wait_after_invalid["gap"] == "INVALID_DATE"
    assert wait_after_invalid["mention_id"] == bad_mention["mention_id"]

    # 3) Valid date reply supersedes the stale invalid mention on a2 and leaves a1 intact.
    valid = SourceSegment(segment_id="s4", text="2026年12月20日", recorded_at=ANCHOR)
    draft.source_records.append(valid)
    draft.source_segments.append(valid.text)
    apply_temporal_answer(
        draft,
        target_id=str(wait_after_invalid["mention_id"]),
        source_text="\n".join(record.text for record in draft.source_records),
        answer_segment_id="s4",
        mentions=[],
        actions=[],
    )
    assert temporal_waiting(draft) is None
    assert resolved_sales_follow_up(draft) == (datetime(2026, 12, 20), "DATE")
    final_mentions = draft.content_json["temporal_evidence"]["mentions"]
    bad_final = next(item for item in final_mentions if item["mention_id"] == bad_mention["mention_id"])
    assert bad_final["state"] == "SUPERSEDED"
    assert next(item for item in final_mentions if item["mention_id"] == foreign_mention_id)["state"] == "ACTIVE"
    assert next(item for item in final_mentions if item["mention_id"] == foreign_mention_id)["answer_gap"] is None


@pytest.mark.asyncio
async def test_non_regex_temporal_wait_and_confirmation_supplement_route_through_intake_step(monkeypatch) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from sqlalchemy.types import BigInteger

    from app.core.database import Base
    from app.models.assistant import (
        AssistantAction,
        AssistantTask,
        AssistantTaskStatus,
        AssistantWaitingType,
    )
    from app.models.assistant_conversation import AssistantConversation, AssistantConversationEntry
    from app.models.assistant_turn import AssistantRequest, AssistantTurn, AssistantTurnEvent
    from app.schemas.assistant_conversation import ConversationDecision, ConversationTextRequest
    from app.services.assistant import conversation as conv_module
    from app.services.assistant import turns as turns_module
    from app.services.assistant.contracts import (
        ActivityPreview,
        ActivityWriteConfirmation,
        TaskAuthority,
        TaskWaiting,
    )
    from app.services.assistant.conversation import ConversationService
    from app.services.assistant.coordinator import AssistantCoordinator, AssistantInput, NextActionDecision
    from app.services.assistant.llm_contracts import KindDecision, ModelDraftAction, StructureDraftResult
    from app.services.assistant.task_state import load_draft, load_waiting
    from app.utils import time as business_time

    @compiles(BigInteger, "sqlite")
    def _bigint_sqlite(element, compiler, **kw):
        return "INTEGER"

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(
        engine,
        tables=[
            model.__table__
            for model in (
                AssistantTask,
                AssistantAction,
                AssistantRequest,
                AssistantTurn,
                AssistantTurnEvent,
                AssistantConversation,
                AssistantConversationEntry,
            )
        ],
    )
    monkeypatch.setattr(conv_module, "schedule_turn", lambda turn_id: None)
    monkeypatch.setattr(business_time, "business_now", lambda: ANCHOR)

    class _Classifier:
        def __init__(self, decision: ConversationDecision):
            self.decision = decision

        async def classify(self, db, **kwargs):
            return self.decision

    class _Structurer:
        def __init__(self):
            self.seen_texts: list[str] = []

        async def classify(self, db, *, team_id, user_text):
            return KindDecision(kind="FOLLOW_UP")

        async def structure(self, db, *, team_id, kind, user_text):
            self.seen_texts.append(user_text)
            mentions: list[ModelTemporalMention] = []
            if "下下周三" in user_text:
                start = user_text.rindex("下下周三")
                mentions.append(
                    ModelTemporalMention(
                        raw_text="下下周三",
                        quote_start=start,
                        quote_end=start + len("下下周三"),
                        kind="RELATIVE_WEEKDAY",
                        role="SALES_FOLLOW_UP",
                        owner="我",
                        confidence=0.95,
                        week_offset=2,
                        weekday=3,
                    )
                )
            if "2/26" in user_text:
                start = user_text.rindex("2/26")
                mentions.append(
                    ModelTemporalMention(
                        raw_text="2/26",
                        quote_start=start,
                        quote_end=start + len("2/26"),
                        kind="MONTH_DAY",
                        role="SALES_FOLLOW_UP",
                        owner="我",
                        confidence=0.95,
                        month=2,
                        day=26,
                    )
                )
            return StructureDraftResult(
                kind_confirmed="FOLLOW_UP",
                content="跟进尚老师",
                customer_name="尚老师",
                next_action="跟进使用情况",
                next_follow_time_text="下下周三" if "下下周三" in user_text else "2/26",
                temporal_mentions=mentions,
                actions=[
                    ModelDraftAction(
                        action_ref="a1",
                        owner_role="SALES",
                        owner_text="我",
                        action_text="跟进使用情况",
                        action_status="PLANNED",
                        evidence_quote="联系尚老师跟进使用情况",
                        quote_start=user_text.index("联系尚老师跟进使用情况"),
                        quote_end=user_text.index("联系尚老师跟进使用情况") + len("联系尚老师跟进使用情况"),
                    )
                ],
            )

    try:
        with sessionmaker(bind=engine)() as session:
            # Part A: non-regex reply ("下下周三") to a FIELD temporal wait.
            source = "春节后联系尚老师跟进使用情况"
            draft = _attach(
                source,
                mentions=[_quote(source, "春节后", action_ref="a1", vague=True)],
                actions=[_action(source, "联系尚老师跟进使用情况", ref="a1", action_text="跟进使用情况")],
            )
            draft.customer = DraftField(status="ACCEPTED", value="尚老师")
            spec = temporal_waiting(draft)
            assert spec is not None and spec["reason"] == "DATE"
            waiting = TaskWaiting(
                type=AssistantWaitingType.FIELD,
                field="next_follow_time",
                question_id="q_time_1",
                action_id="awa_wait_1",
                prompt=str(spec["prompt"]),
                candidates=[],
                temporal_target={
                    "mention_id": spec["mention_id"],
                    "business_action_id": spec["business_action_id"],
                    "reason": spec["reason"],
                },
            )
            task = AssistantTask(
                public_id="task_crm170_wait",
                team_id=1,
                user_id=2,
                goal="记录客户跟进",
                task_kind="customer_activity",
                status=AssistantTaskStatus.ACTIVE,
                activity_kind="FOLLOW_UP",
                waiting_type=waiting.type,
                waiting_field=waiting.field,
                waiting_json={
                    "payload": waiting.model_dump(mode="json", exclude={"type", "field", "expected_version"}),
                    "action_id": waiting.action_id,
                },
                draft_json=draft.model_dump(mode="json"),
                authority_json=TaskAuthority(customer_public_id="cust_1").model_dump(mode="json"),
                version=1,
            )
            session.add(task)
            session.commit()

            # ConversationService routes "下下周三" as submit_field even when decision.field_answer is False.
            conv_decision = ConversationDecision(
                semantic_plan={
                    "speech_act": "PROVIDE_SUPPLEMENT",
                    "business_object": "CUSTOMER_ACTIVITY",
                    "operation": "CREATE",
                    "confidence": 0.95,
                },
                task_relation="CONTINUE_TASK",
                route="WORKFLOW",
                boundary="CONTINUE",
                target_task_public_id=task.public_id,
                confidence=0.95,
                field_answer=False,
            )
            service = ConversationService(classifier=_Classifier(conv_decision))
            opened = service.open(session, team_id=1, user_id=2)
            submitted = await service.submit_text(
                session,
                team_id=1,
                user_id=2,
                request=ConversationTextRequest(
                    client_request_id="req-non-regex-wait",
                    expected_version=opened.version,
                    text="下下周三",
                ),
            )
            assert submitted.submission is not None
            assert submitted.submission.input.kind == "submit_field"
            assert submitted.submission.input.text == "下下周三"

            # Coordinator routes "下下周三" through intake_step(..., temporal_answer_id=target_id).
            structurer = _Structurer()
            class _Chooser:
                async def choose(self, _task):
                    return NextActionDecision(action="prepare_confirmation", parameters={})

            coordinator = AssistantCoordinator(next_action_chooser=_Chooser(), structurer=structurer)
            session.refresh(task)
            task.active_turn_id = None
            session.commit()
            outcome = await coordinator.handle_task(
                session, task, AssistantInput(kind="submit_field", text="下下周三")
            )
            assert structurer.seen_texts == [f"{source}\n下下周三"]
            updated_draft = load_draft(outcome.task)
            assert temporal_waiting(updated_draft) is None
            assert resolved_sales_follow_up(updated_draft) == (datetime(2026, 12, 9), "DATE")
            assert updated_draft.customer.value == "尚老师"
            assert updated_draft.next_action.value == "跟进使用情况"

            # Part B: non-regex supplement ("改为2/26") on a signed CONFIRMATION card.
            conf_waiting = TaskWaiting(
                type=AssistantWaitingType.CONFIRMATION,
                field="activity_write",
                question_id="q_confirm_1",
                action_id="act_confirm_1",
                expected_version=outcome.task.version,
                prompt="请确认记录",
                confirmation_payload=ActivityWriteConfirmation(
                    kind="activity_write",
                    preview=ActivityPreview(
                        customer_name="尚老师",
                        content_json=updated_draft.content_json,
                        source_content=source,
                        score=80,
                        score_reason="ok",
                    ),
                ),
            )
            outcome.task.status = AssistantTaskStatus.ACTIVE
            outcome.task.waiting_type = conf_waiting.type
            outcome.task.waiting_field = conf_waiting.field
            outcome.task.waiting_json = {
                "payload": conf_waiting.model_dump(mode="json", exclude={"type", "field", "expected_version"}),
                "action_id": conf_waiting.action_id,
            }
            session.commit()

            # turns.accept_submit admits "改为2/26" against CONFIRMATION card.
            turn, accepted = turns_module.accept_submit(
                session,
                task=outcome.task,
                key="confirm-non-regex-supplement",
                input_data={"kind": "text", "text": "改为2/26", "choice": None},
                action_id=conf_waiting.action_id,
                expected_version=conf_waiting.expected_version,
            )
            assert accepted and turn is not None
            # Release active_turn_id to test ConversationService + Coordinator execution cleanly.
            outcome.task.active_turn_id = None
            session.commit()

            state_before_corr = service.open(session, team_id=1, user_id=2)
            corr_resp = await service.submit_text(
                session,
                team_id=1,
                user_id=2,
                request=ConversationTextRequest(
                    client_request_id="req-confirm-corr-226",
                    expected_version=state_before_corr.version,
                    text="改为2/26",
                ),
            )
            assert corr_resp.submission is not None
            assert corr_resp.submission.input.kind == "text"
            assert corr_resp.submission.input.action_id == conf_waiting.action_id
            session.refresh(outcome.task)
            assert load_waiting(outcome.task) is not None
            assert load_waiting(outcome.task).type == AssistantWaitingType.CONFIRMATION
            outcome.task.active_turn_id = None
            session.commit()
            outcome2 = await coordinator.handle_task(
                session, outcome.task, AssistantInput(kind="text", text="改为2/26")
            )
            assert len(structurer.seen_texts) == 2
            assert structurer.seen_texts[-1].endswith("\n改为2/26")
            final_draft = load_draft(outcome2.task)
            assert temporal_waiting(final_draft) is None
            assert resolved_sales_follow_up(final_draft) == (datetime(2027, 2, 26), "DATE")
    finally:
        engine.dispose()


def test_bind_quote_spans_resolves_omitted_offsets_and_disambiguates_repeated_quotes() -> None:
    from app.services.assistant.llm_contracts import ModelDraftAction, ModelTemporalMention
    from app.services.assistant.temporal_evidence import TemporalContractError, bind_quote_spans

    text = "客户说下周三给反馈，我方也计划下周三电话确认进展。"
    actions = [
        ModelDraftAction(
            action_ref="a1",
            owner_role="CUSTOMER",
            action_text="客户给反馈",
            action_status="COMMITTED",
            evidence_quote="客户说下周三给反馈",
        ),
        ModelDraftAction(
            action_ref="a2",
            owner_role="SALES",
            action_text="电话确认进展",
            action_status="PLANNED",
            evidence_quote="我方也计划下周三电话确认进展",
        ),
    ]
    mentions = [
        ModelTemporalMention(
            raw_text="下周三",
            kind="RELATIVE_WEEKDAY",
            role="SALES_FOLLOW_UP",
            action_ref="a2",
            week_offset=1,
            weekday=3,
        ),
        ModelTemporalMention(
            raw_text="下周三",
            kind="RELATIVE_WEEKDAY",
            role="CUSTOMER_COMMITMENT",
            action_ref="a1",
            week_offset=1,
            weekday=3,
        ),
    ]

    bound_mentions, bound_actions = bind_quote_spans(text, mentions, actions)

    assert [text[a.quote_start : a.quote_end] for a in bound_actions] == [
        "客户说下周三给反馈",
        "我方也计划下周三电话确认进展",
    ]
    # action_ref locality binds a2's mention to the second "下周三" and a1's to the first.
    assert bound_mentions[0].quote_start == text.rindex("下周三")
    assert bound_mentions[1].quote_start == text.index("下周三")
    assert all(text[m.quote_start : m.quote_end] == m.raw_text for m in bound_mentions)

    with pytest.raises(TemporalContractError, match="temporal span is not in the source"):
        bind_quote_spans(
            text,
            [ModelTemporalMention(raw_text="大后天", kind="RELATIVE_DAY", role="SALES_FOLLOW_UP")],
            [],
        )

"""CRM-72: quotes are evidence, not a mirror of the server date scanner."""
# ruff: noqa: RUF001

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.services.assistant.contracts import DraftField, TaskDraft
from app.services.assistant.llm_contracts import StructuredFollowUp
from app.services.assistant.temporal_evidence import (
    TemporalContractError,
    attach_model_evidence,
    find_time_spans,
    resolved_sales_follow_up,
    temporal_waiting,
    validate_temporal_quotes,
)

ANCHOR = datetime(2026, 11, 2, 13, 20)
REAL = json.loads((Path(__file__).parents[1] / "fixtures/assistant_relative_year_real_response.json").read_text())


def quoted(text, raw, *, kind="UNKNOWN", role="SALES_FOLLOW_UP", ref="sales"):
    start = text.index(raw)
    return {
        "raw_text": raw,
        "quote_start": start,
        "quote_end": start + len(raw),
        "kind": kind,
        "role": role,
        "action_ref": ref,
        "confidence": 0.95,
    }


def action(text, *, ref="sales", role="SALES", quote=None):
    quote = quote or text
    start = text.index(quote)
    return {
        "action_ref": ref,
        "owner_role": role,
        "owner_text": "我" if role == "SALES" else "杨老师",
        "action_text": quote,
        "action_status": "PLANNED",
        "evidence_quote": quote,
        "quote_start": start,
        "quote_end": start + len(quote),
    }


def attach(text, mentions=None, actions=None, anchor=ANCHOR):
    draft = TaskDraft(
        content=DraftField(status="CANDIDATE", value=text), content_json={"content": text}, source_segments=[text]
    )
    attach_model_evidence(
        draft,
        segment_id="seg_original",
        segment_text=text,
        anchor=anchor,
        mentions=mentions or [],
        actions=actions if actions is not None else [action(text)],
    )
    return draft


def test_exact_real_model_response_keeps_all_quotes_and_background_without_false_failure():
    text = REAL["source"]
    response = StructuredFollowUp.model_validate_json(REAL["response"])
    assert len(response.temporal_mentions) == 5
    assert all(text[m.quote_start : m.quote_end] == m.raw_text for m in response.temporal_mentions)
    validate_temporal_quotes(text, response.temporal_mentions)
    draft = attach(text, response.temporal_mentions, response.actions)
    assert temporal_waiting(draft) is None
    assert resolved_sales_follow_up(draft) == (datetime(2027, 1, 15), "DATE")
    evidence = draft.content_json["temporal_evidence"]
    active = {m["raw_text"]: m for m in evidence["mentions"] if m["state"] == "ACTIVE"}
    assert "1 月 15 号" not in active
    for raw in ("今年", "年底", "明年"):
        assert active[raw]["resolved_at"] is None
    assert active["明年 1 月 15 号"]["anchor_at"] == ANCHOR.isoformat()
    assert active["明年 1 月 15 号"]["role"] == "SALES_FOLLOW_UP"
    assert draft.content.value == text
    assert "采购的可能" in draft.next_action.value
    assert sum(len(m["source_quotes"]) for m in evidence["mentions"]) == 5


@pytest.mark.parametrize("raw", ["明年1月15号", "明年1月15日", "明年 1 月 15 日", "明年 1 月 15 号", "明年，1月15号"])
@pytest.mark.parametrize("model_kind", ["UNKNOWN", "MONTH_DAY", "FULL_MONTH"])
def test_compound_variants_use_server_semantics_not_model_classification(raw, model_kind):
    text = f"{raw}，联系杨老师确认采购可能"
    draft = attach(text, [quoted(text, raw, kind=model_kind)])
    assert [(s.raw_text, s.kind) for s in find_time_spans(text)] == [(raw, "RELATIVE_YEAR_DATE")]
    assert resolved_sales_follow_up(draft) == (datetime(2027, 1, 15), "DATE")
    assert temporal_waiting(draft) is None


@pytest.mark.parametrize(
    ("raw", "anchor", "expected"),
    [
        ("明年1月15号", datetime(2026, 1, 1), datetime(2027, 1, 15)),
        ("今年1月15号", ANCHOR, datetime(2026, 1, 15)),
        ("后年1月15号", ANCHOR, datetime(2028, 1, 15)),
        ("去年1月15号", ANCHOR, datetime(2025, 1, 15)),
        ("2028年1月15号", ANCHOR, datetime(2028, 1, 15)),
        ("明年2028年1月15号", ANCHOR, datetime(2028, 1, 15)),
        ("后年2月29号", ANCHOR, datetime(2028, 2, 29)),
    ],
)
def test_year_precedence_and_original_anchor(raw, anchor, expected):
    text = raw + "联系杨老师"
    # Replaying the source always uses its immutable anchor, never the worker's current clock.
    for _ in range(2):
        draft = attach(text, [quoted(text, raw)], anchor=anchor)
        assert resolved_sales_follow_up(draft) == (expected, "DATE")


def test_complete_expression_supersedes_inner_model_spans_without_losing_quote_audit():
    text = "明年 1 月 15 号联系杨老师"
    mentions = [quoted(text, raw) for raw in ("明年", "1 月 15 号", "明年 1 月 15 号")]
    validate_temporal_quotes(text, mentions)
    draft = attach(text, mentions)
    evidence = draft.content_json["temporal_evidence"]["mentions"]
    assert len(evidence) == 1
    assert evidence[0]["raw_text"] == "明年 1 月 15 号"
    assert {q["raw_text"] for q in evidence[0]["source_quotes"]} == {m["raw_text"] for m in mentions}
    assert resolved_sales_follow_up(draft) == (datetime(2027, 1, 15), "DATE")


def test_model_omission_cannot_hide_a_source_action_time():
    text = "我明年1月15号联系杨老师"
    validate_temporal_quotes(text, [])
    draft = attach(text, [])
    assert resolved_sales_follow_up(draft) == (datetime(2027, 1, 15), "DATE")
    assert temporal_waiting(draft) is None


@pytest.mark.parametrize(
    "text,raw", [("大概明年联系杨老师", "明年"), ("秋后联系杨老师", "秋后"), ("明年2月30号联系杨老师", "明年2月30号")]
)
def test_unresolved_action_time_has_one_existing_date_wait_and_no_fake_instant(text, raw):
    draft = attach(text, [quoted(text, raw)])
    assert resolved_sales_follow_up(draft) == (None, "UNKNOWN")
    waiting = temporal_waiting(draft)
    assert waiting is not None and waiting["reason"] == "DATE"
    assert waiting["candidates"] == []
    assert "请补充具体日期" in waiting["prompt"]


def test_missing_all_model_evidence_does_not_bypass_source_time_gate():
    draft = attach("我大概明年联系杨老师", [], [])
    assert temporal_waiting(draft)["reason"] == "DATE"
    assert resolved_sales_follow_up(draft) == (None, "UNKNOWN")


def test_undated_action_remains_undated_without_new_date_requirement():
    draft = attach("联系杨老师确认采购可能", [], [action("联系杨老师确认采购可能")])
    assert temporal_waiting(draft) is None
    assert resolved_sales_follow_up(draft) == (None, "UNKNOWN")


@pytest.mark.parametrize("text", ["明年联系杨老师", "联系杨老师"])
def test_fabricated_time_rejected_even_when_scanner_finds_nothing(text):
    fake = {
        "raw_text": "2027年1月15号",
        "quote_start": 0,
        "quote_end": 11,
        "kind": "MONTH_DAY",
        "role": "SALES_FOLLOW_UP",
        "action_ref": "",
        "confidence": 1,
    }
    with pytest.raises(TemporalContractError):
        validate_temporal_quotes(text, [fake])
    with pytest.raises(TemporalContractError):
        attach(text, [fake])


def test_scanner_owned_weekday_with_clock_stays_resolvable_when_model_omits_it():
    text = "我下周三下午三点联系杨老师"
    draft = attach(text, [])
    assert temporal_waiting(draft) is None
    assert resolved_sales_follow_up(draft) == (datetime(2026, 11, 11, 15), "DATETIME")


def test_background_after_dated_action_cannot_overwrite_the_sales_binding():
    text = "明年1月15号联系杨老师，今年快年底了"
    mentions = [
        quoted(text, raw, role="OTHER" if raw != "明年1月15号" else "SALES_FOLLOW_UP")
        for raw in ("明年1月15号", "今年", "年底")
    ]
    draft = attach(text, mentions)
    assert temporal_waiting(draft) is None
    assert resolved_sales_follow_up(draft) == (datetime(2027, 1, 15), "DATE")


def test_two_distinct_dates_on_one_action_require_one_date_answer_not_last_wins():
    text = "我明年1月15号或1月16号联系杨老师"
    draft = attach(text, [quoted(text, raw) for raw in ("明年1月15号", "1月16号")])
    assert temporal_waiting(draft)["reason"] == "DATE"
    assert temporal_waiting(draft)["candidates"] == []
    assert resolved_sales_follow_up(draft) == (None, "UNKNOWN")


def temporal_answer_draft(answer):
    from app.services.assistant.action_evidence import SourceSegment
    from app.services.assistant.temporal_evidence import temporal_answer_target

    text = "我大概明年联系杨老师"
    draft = attach(text, [quoted(text, "明年")])
    draft.source_records = [
        SourceSegment(segment_id="seg_original", text=text, recorded_at=ANCHOR),
        SourceSegment(segment_id="seg_answer", text=answer, recorded_at=datetime(2027, 1, 2, 10)),
    ]
    draft.source_segments.append(answer)
    return draft, temporal_answer_target(draft), text + "\n" + answer


def test_date_answer_preserves_source_anchors_and_current_action_even_if_model_replans():
    from app.services.assistant.temporal_evidence import apply_temporal_answer

    answer = "2027年1月15号"
    draft, target, source = temporal_answer_draft(answer)
    original_action = draft.next_action.value
    # Full-context structuring may nominate a different role; this reply only answers the date.
    mentions = [quoted(source, "明年", role="CUSTOMER_COMMITMENT"), quoted(source, answer)]
    nominated_action = action(source, quote=draft.source_segments[0], role="CUSTOMER")
    apply_temporal_answer(
        draft,
        target_id=target,
        source_text=source,
        answer_segment_id="seg_answer",
        mentions=mentions,
        actions=[nominated_action],
    )
    assert temporal_waiting(draft) is None
    assert resolved_sales_follow_up(draft) == (datetime(2027, 1, 15), "DATE")
    assert draft.next_action.value == original_action
    stored = draft.content_json["temporal_evidence"]["mentions"]
    old = next(item for item in stored if item["mention_id"] == target)
    new = next(item for item in stored if item["correction_of"] == target)
    assert old["state"] == "SUPERSEDED" and old["role"] == "SALES_FOLLOW_UP"
    assert old["anchor_at"] == ANCHOR.isoformat()
    assert new["source_segment_id"] == "seg_answer"
    assert new["anchor_at"] == datetime(2027, 1, 2, 10).isoformat()
    quoted_action = new["source_actions"][0]
    assert quoted_action["source_segment_id"] == "seg_original"
    assert quoted_action["action"]["action_ref"] == new["source_quotes"][0]["action_ref"]
    assert quoted_action["action"]["evidence_quote"] == draft.source_segments[0]


@pytest.mark.parametrize(
    "answer", ["2027年2月30号", "大概明年", "2027年1月15号或2027年1月16号", "以后再说", "1月份", "1月初"]
)
def test_invalid_or_non_unique_date_reply_stays_in_single_wait(answer):
    from app.services.assistant.temporal_evidence import apply_temporal_answer

    draft, target, source = temporal_answer_draft(answer)
    apply_temporal_answer(
        draft, target_id=target, source_text=source, answer_segment_id="seg_answer", mentions=[], actions=[]
    )
    assert temporal_waiting(draft)["reason"] == "DATE"
    assert temporal_waiting(draft)["candidates"] == []
    assert resolved_sales_follow_up(draft) == (None, "UNKNOWN")


@pytest.mark.parametrize("bad_evidence", ["fabricated_time", "fabricated_action", "cross_segment", "dangling_action"])
def test_date_answer_rejects_invalid_evidence_without_mutating_original_draft(bad_evidence):
    from app.services.assistant.temporal_evidence import apply_temporal_answer

    draft, target, source = temporal_answer_draft("2027年1月15号")
    before = draft.model_dump(mode="json")
    mentions, actions = [], []
    if bad_evidence == "fabricated_time":
        mentions = [quoted("2028年1月15号", "2028年1月15号", ref="")]
    elif bad_evidence == "fabricated_action":
        actions = [action("我明天采购了十台设备")]
    elif bad_evidence == "cross_segment":
        mentions = [quoted(source, source, ref="")]
    else:
        mentions = [quoted(source, "2027年1月15号")]
    with pytest.raises(TemporalContractError):
        apply_temporal_answer(
            draft,
            target_id=target,
            source_text=source,
            answer_segment_id="seg_answer",
            mentions=mentions,
            actions=actions,
        )
    assert draft.model_dump(mode="json") == before


def test_date_answer_keeps_action_and_date_provenance_valid_for_existing_proposals():
    from app.services.assistant.action_evidence import reconcile_action_evidence, validate_action_evidence
    from app.services.assistant.temporal_evidence import apply_temporal_answer

    draft, target, source = temporal_answer_draft("2027年1月15号")
    apply_temporal_answer(
        draft,
        target_id=target,
        source_text=source,
        answer_segment_id="seg_answer",
        mentions=[],
        actions=[],
    )
    reconcile_action_evidence(draft, "FOLLOW_UP")
    evidence = [
        item
        for item in draft.content_json["action_evidence"]
        if item["state"] == "ACTIVE" and item["parser_version"] == "assistant-date-v2"
    ]
    assert len(evidence) == 1
    assert evidence[0]["segment_id"] == "seg_original"
    assert validate_action_evidence(draft.content_json, evidence[0]["action_id"], source_content=source) is not None


def test_a_contact_name_elsewhere_does_not_turn_a_vague_sales_action_into_background():
    text = "今天联系了杨老师。大概明年再看看"
    draft = attach(text, [quoted(text, "明年")], [action(text, quote="大概明年再看看")])
    assert temporal_waiting(draft)["reason"] == "DATE"
    assert resolved_sales_follow_up(draft) == (None, "UNKNOWN")


def test_a_year_qualifying_absent_procurement_plans_is_background_not_a_date_question():
    text = "今年没有采购计划。明年1月15号联系杨老师"
    draft = attach(
        text,
        [quoted(text, "今年", ref="", role="OTHER"), quoted(text, "明年1月15号")],
        [action(text, quote="明年1月15号联系杨老师")],
    )
    assert temporal_waiting(draft) is None
    assert resolved_sales_follow_up(draft) == (datetime(2027, 1, 15), "DATE")


def test_source_derived_action_keeps_exact_offsets_after_whitespace():
    text = "客户暂无采购计划。 明年1月15号联系杨老师"
    draft = attach(text, [], [])
    evidence = draft.content_json["temporal_evidence"]
    assert len(evidence["actions"]) == 1
    stored = evidence["actions"][0]
    assert text[stored["quote_start"] : stored["quote_end"]] == stored["evidence_quote"]
    assert stored["action_text"] == "联系杨老师"
    assert resolved_sales_follow_up(draft) == (datetime(2027, 1, 15), "DATE")


@pytest.mark.parametrize("text", ["杨老师明年1月15号联系我", "明年1月15号杨老师联系我"])
def test_explicit_customer_actor_overrides_a_model_sales_role(text):
    draft = attach(text, [quoted(text, "明年1月15号")])
    assert resolved_sales_follow_up(draft) == (None, "UNKNOWN")
    assert temporal_waiting(draft) is None
    stored = draft.content_json["temporal_evidence"]["mentions"][0]
    assert stored["role"] == "CUSTOMER_COMMITMENT"
    assert draft.next_follow_time.status == "MISSING"


def test_expanded_old_quote_is_audit_not_another_date_wait_after_answer():
    from app.services.assistant.temporal_evidence import apply_temporal_answer

    draft, target, source = temporal_answer_draft("2027年1月15号")
    apply_temporal_answer(
        draft,
        target_id=target,
        source_text=source,
        answer_segment_id="seg_answer",
        mentions=[quoted(source, "大概明年"), quoted(source, "2027年1月15号")],
        actions=[action(source, quote=draft.source_segments[0])],
    )
    assert temporal_waiting(draft) is None
    assert resolved_sales_follow_up(draft) == (datetime(2027, 1, 15), "DATE")
    stored = draft.content_json["temporal_evidence"]["mentions"]
    assert len(stored) == 2
    old = next(item for item in stored if item["mention_id"] == target)
    assert "大概明年" in {item["raw_text"] for item in old["source_quotes"]}
    assert old["anchor_at"] == ANCHOR.isoformat()


def test_background_negation_earlier_in_clause_cannot_swallow_the_sales_time():
    text = "今年没有采购计划所以我明年联系杨老师"
    draft = attach(
        text,
        [quoted(text, "今年", role="OTHER", ref=""), quoted(text, "明年")],
        [action(text, quote="我明年联系杨老师")],
    )
    assert temporal_waiting(draft)["reason"] == "DATE"
    assert temporal_waiting(draft)["prompt"].startswith("“明年”")
    assert resolved_sales_follow_up(draft) == (None, "UNKNOWN")


def shifted(item, start):
    """Model quote with a wrong offset; raw text still names the source words."""
    width = item["quote_end"] - item["quote_start"]
    return {**item, "quote_start": start, "quote_end": start + width}


def repeated_word_answer_draft(answer):
    from app.services.assistant.action_evidence import SourceSegment
    from app.services.assistant.temporal_evidence import temporal_answer_target

    text = "陈老师反馈周四会完成测试，我大概明年联系陈老师"
    draft = attach(
        text,
        [quoted(text, "周四", role="CUSTOMER_COMMITMENT", ref=""), quoted(text, "明年")],
        [action(text, quote="我大概明年联系陈老师")],
    )
    draft.source_records = [
        SourceSegment(segment_id="seg_original", text=text, recorded_at=ANCHOR),
        SourceSegment(segment_id="seg_answer", text=answer, recorded_at=datetime(2026, 11, 2, 13, 25)),
    ]
    draft.source_segments.append(answer)
    return draft, temporal_answer_target(draft), text + "\n" + answer


@pytest.mark.parametrize("offsets", ["answer_off_by_one", "answer_segment_local", "original_off_by_two"])
def test_answer_repeating_an_original_word_resolves_from_the_nearest_occurrence(offsets):
    from app.services.assistant.temporal_evidence import apply_temporal_answer

    draft, target, source = repeated_word_answer_draft("周四")
    answer_start = source.rindex("周四")
    original = quoted(source, "周四", role="CUSTOMER_COMMITMENT", ref="")
    answer = shifted(original, answer_start)
    mentions = {
        "answer_off_by_one": [shifted(answer, answer_start - 1)],
        "answer_segment_local": [shifted(answer, 0)],
        "original_off_by_two": [shifted(original, original["quote_start"] + 2), answer],
    }[offsets]
    apply_temporal_answer(
        draft, target_id=target, source_text=source, answer_segment_id="seg_answer", mentions=mentions, actions=[]
    )
    assert temporal_waiting(draft) is None
    assert resolved_sales_follow_up(draft) == (datetime(2026, 11, 5), "DATE")
    stored = draft.content_json["temporal_evidence"]["mentions"]
    customer = next(item for item in stored if item["role"] == "CUSTOMER_COMMITMENT")
    assert (customer["source_segment_id"], customer["quote_start"], customer["state"]) == ("seg_original", 5, "ACTIVE")


def test_quote_equally_near_two_occurrences_is_still_rejected():
    text = "周四开会周四再联系"
    tie = shifted(quoted(text, "周四"), 2)  # occurrences at 0 and 4: distance 2 to both
    with pytest.raises(TemporalContractError, match="temporal span is not in the source"):
        validate_temporal_quotes(text, [tie])


def test_repeated_action_quote_binds_to_the_nearest_occurrence_not_the_first():
    text = "我找陈老师确认需求，周四再找陈老师对齐"
    second = text.rindex("找陈老师")
    nominated = shifted(action(text, quote="找陈老师"), second + 1)
    draft = attach(text, [quoted(text, "周四")], [nominated])
    stored = draft.content_json["temporal_evidence"]["actions"][0]
    assert stored["quote_start"] == second
    assert resolved_sales_follow_up(draft) == (datetime(2026, 11, 5), "DATE")


@pytest.mark.parametrize("moment", ["刚刚", "刚才", "方才"])
def test_just_now_is_the_event_moment_not_a_date_question_or_next_follow_up(moment):
    text = f"{moment}微信联系了陈老师，周四再找陈老师对齐"
    draft = attach(
        text,
        [quoted(text, moment), quoted(text, "周四")],
        [action(text, quote="周四再找陈老师对齐")],
    )
    assert temporal_waiting(draft) is None
    assert resolved_sales_follow_up(draft) == (datetime(2026, 11, 5), "DATE")
    stored = draft.content_json["temporal_evidence"]["mentions"]
    just_now = next(item for item in stored if item["raw_text"] == moment)
    assert just_now["role"] == "OTHER" and just_now["resolution_status"] == "RESOLVED"


def test_just_now_alone_does_not_ask_for_a_follow_up_date():
    text = "刚刚微信联系了陈老师"
    draft = attach(text, [quoted(text, "刚刚")])
    assert temporal_waiting(draft) is None
    assert resolved_sales_follow_up(draft) == (None, "UNKNOWN")


@pytest.mark.parametrize("text", ["刚刚说再联系陈老师", "刚才客户说让我再联系他"])
def test_just_now_never_takes_over_the_sales_next_action(text):
    quote = text[text.index("再") :]
    draft = attach(text, [], [action(text, quote=quote)])
    assert draft.next_action.value
    assert resolved_sales_follow_up(draft) == (None, "UNKNOWN")


def test_quote_crossing_just_now_into_a_date_is_still_a_date_question():
    text = "刚刚周四再找陈老师"
    draft = attach(text, [quoted(text, "刚刚周四")], [action(text, quote="周四再找陈老师")])
    assert temporal_waiting(draft) is not None


@pytest.mark.parametrize("answer", ["刚才问过了，周四", "周四，刚才忘说了"])
def test_date_answer_with_a_just_now_aside_still_resolves_the_wait(answer):
    from app.services.assistant.temporal_evidence import apply_temporal_answer

    draft, target, source = repeated_word_answer_draft(answer)
    apply_temporal_answer(
        draft,
        target_id=target,
        source_text=source,
        answer_segment_id="seg_answer",
        mentions=[quoted(source, "周四", role="CUSTOMER_COMMITMENT", ref="")],
        actions=[],
    )
    assert temporal_waiting(draft) is None
    assert resolved_sales_follow_up(draft) == (datetime(2026, 11, 5), "DATE")

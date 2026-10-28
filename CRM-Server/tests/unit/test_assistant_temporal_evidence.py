"""Temporal evidence separates customer commitments from sales follow-up dates."""

# ruff: noqa: RUF001

from __future__ import annotations

from datetime import datetime

import pytest

from app.services.assistant.contracts import DraftField, TaskDraft
from app.services.assistant.llm_contracts import ModelDraftAction, ModelTemporalMention
from app.services.assistant.temporal_evidence import (
    ActionContractError,
    TemporalContractError,
    apply_temporal_choice,
    attach_model_evidence,
    ensure_mentions_cover_source,
    find_time_spans,
    resolved_sales_follow_up,
    temporal_waiting,
)

ANCHOR = datetime(2026, 10, 27, 15, 0)
EXAMPLE = (
    "今天找通力电梯的研发经理叶老师确认部署服务器的准备情况，"
    "叶老师反馈本月底会完成；等 30 号再找叶老师确认下服务器的准备情况"
)


def _draft(text: str) -> TaskDraft:
    return TaskDraft(
        content=DraftField(status="CANDIDATE", value=text),
        content_json={"content": text},
        source_segments=[text],
    )


def _attach(text: str, anchor: datetime = ANCHOR, *, action_text: str = "联系叶老师") -> TaskDraft:
    spans = find_time_spans(text)
    mentions = []
    actions = []
    for index, span in enumerate(spans):
        mentions.append(
            {
                "raw_text": span.raw_text,
                "quote_start": span.start,
                "quote_end": span.end,
                "kind": span.kind,
                "role": "OTHER",
                "owner": "",
                "action_ref": f"a{index}",
                "confidence": 0.9,
            }
        )
        actions.append(
            {
                "action_ref": f"a{index}",
                "owner_role": "SALES",
                "owner_text": "我",
                "action_text": action_text if span.kind != "MONTH_END" else "完成部署服务器准备",
                "action_status": "PLANNED",
                "evidence_quote": span.raw_text,
                "quote_start": span.start,
                "quote_end": span.end,
            }
        )
    draft = _draft(text)
    attach_model_evidence(
        draft, segment_id="seg_test", segment_text=text, anchor=anchor, mentions=mentions, actions=actions
    )
    return draft


def test_example_keeps_month_end_out_of_sales_follow_up_and_asks_which_month() -> None:
    draft = _attach(EXAMPLE, action_text="联系叶老师，确认部署服务器的准备情况")
    mentions = {item["raw_text"]: item for item in draft.content_json["temporal_evidence"]["mentions"]}
    assert mentions["本月底"]["role"] == "CUSTOMER_COMMITMENT"
    assert mentions["本月底"]["resolved_at"] == "2026-10-31T00:00:00"
    assert mentions["30 号"]["role"] == "SALES_FOLLOW_UP"
    assert mentions["30 号"]["resolution_status"] == "AMBIGUOUS"
    assert draft.content_json["customer_commitments"][0]["text"] == "叶老师预计本月底完成部署服务器准备。"
    assert "2026-10-31" not in (draft.next_follow_time.value or "")
    waiting = temporal_waiting(draft)
    assert waiting is not None
    assert waiting["prompt"] == "“30号”是指本月30号还是下月30号？"
    assert [item["label"] for item in waiting["candidates"]] == ["本月30号", "下月30号"]
    apply_temporal_choice(draft, waiting["candidates"][0]["id"])
    resolved, granularity = resolved_sales_follow_up(draft)
    assert (resolved, granularity) == (datetime(2026, 10, 30), "DATE")
    assert resolved.hour == 0
    assert draft.content_json["sales_follow_up_text"] == "你将在10月30号联系叶老师，确认部署服务器的准备情况。"
    assert draft.content_json["temporal_notices"] == ["已识别下次跟进日期为2026-10-30，未指定具体时刻。"]


def test_month_end_alone_keeps_an_empty_sales_time() -> None:
    draft = _attach("叶老师反馈本月底会完成")
    assert temporal_waiting(draft) is None
    assert resolved_sales_follow_up(draft) == (None, "UNKNOWN")
    assert draft.next_follow_time.status == "MISSING"
    assert draft.content_json["customer_commitments"][0]["resolved_on"] == "2026-10-31"


def test_bare_day_with_one_future_month_confirms_as_date() -> None:
    draft = _attach("30号联系叶老师", datetime(2026, 10, 31, 9))
    assert temporal_waiting(draft) is None
    resolved, granularity = resolved_sales_follow_up(draft)
    assert (resolved, granularity) == (datetime(2026, 11, 30), "DATE")
    assert "未指定具体时刻" in draft.content_json["temporal_notices"][0]


def test_explicit_month_and_relative_month_do_not_ask_again() -> None:
    next_month = _attach("下个月30号联系叶老师")
    named = _attach("10月30号联系叶老师")
    assert temporal_waiting(next_month) is None
    assert temporal_waiting(named) is None
    assert resolved_sales_follow_up(next_month)[0] == datetime(2026, 11, 30)
    assert resolved_sales_follow_up(named)[0] == datetime(2026, 10, 30)


def test_vague_month_end_stays_ambiguous() -> None:
    draft = _attach("月底左右联系叶老师")
    waiting = temporal_waiting(draft)
    assert waiting is not None and waiting["candidates"] == []
    assert waiting["prompt"] == "“月底”无法确定为唯一日期，请补充具体日期。"
    assert resolved_sales_follow_up(draft) == (None, "UNKNOWN")


def test_correction_keeps_only_the_replacement_active() -> None:
    draft = _attach("我下周三联系，改为下周五", datetime(2026, 10, 8, 23, 59))
    mentions = draft.content_json["temporal_evidence"]["mentions"]
    assert [(item["raw_text"], item["state"]) for item in mentions] == [("下周三", "SUPERSEDED"), ("下周五", "ACTIVE")]
    assert resolved_sales_follow_up(draft)[0] == datetime(2026, 10, 16)


def test_two_actions_keep_two_spans() -> None:
    text = "我下周三发方案，李工下周五给报价"
    draft = _attach(text, datetime(2026, 10, 8, 23, 59))
    mentions = draft.content_json["temporal_evidence"]["mentions"]
    assert len(mentions) == 2
    assert {item["raw_text"] for item in mentions} == {"下周三", "下周五"}
    assert all(item["state"] == "ACTIVE" for item in mentions)


def test_customer_date_does_not_authorize_an_undated_sales_action() -> None:
    text = "叶老师本月底会完成准备，我再联系叶老师"
    draft = _attach(text)
    sales = resolved_sales_follow_up(draft)
    assert sales == (None, "UNKNOWN")
    assert draft.content_json["customer_commitments"][0]["resolved_on"] == "2026-10-31"


def test_illegal_span_is_a_contract_failure() -> None:
    draft = _draft("本月底完成")
    with pytest.raises(TemporalContractError):
        attach_model_evidence(
            draft,
            segment_id="seg_test",
            segment_text="本月底完成",
            anchor=ANCHOR,
            mentions=[
                {
                    "raw_text": "下周五",
                    "quote_start": 0,
                    "quote_end": 3,
                    "kind": "RELATIVE_WEEKDAY",
                    "role": "SALES_FOLLOW_UP",
                    "action_ref": "",
                    "confidence": 1,
                }
            ],
            actions=[],
        )


def test_model_must_cover_every_source_time() -> None:
    with pytest.raises(TemporalContractError):
        ensure_mentions_cover_source(EXAMPLE, [])


def test_choice_id_from_outside_the_waiting_set_is_rejected() -> None:
    draft = _attach(EXAMPLE)
    with pytest.raises(TemporalContractError):
        apply_temporal_choice(draft, "tm_missing:0")


def test_public_model_instances_are_accepted() -> None:
    text = "叶老师反馈本月底会完成"
    span = find_time_spans(text)[0]
    mention = ModelTemporalMention(
        raw_text=span.raw_text,
        quote_start=span.start,
        quote_end=span.end,
        kind=span.kind,
        role="CUSTOMER_COMMITMENT",
        owner="叶老师",
        action_ref="c1",
        confidence=0.9,
    )
    action = ModelDraftAction(
        action_ref="c1",
        owner_role="CUSTOMER",
        owner_text="叶老师",
        action_text="完成",
        action_status="COMMITTED",
        evidence_quote="会完成",
        quote_start=text.find("会完成"),
        quote_end=text.find("会完成") + len("会完成"),
    )
    ensure_mentions_cover_source(text, [mention])
    draft = _draft(text)
    attach_model_evidence(
        draft,
        segment_id="seg_test",
        segment_text=text,
        anchor=ANCHOR,
        mentions=[mention],
        actions=[action],
    )
    stored = draft.content_json["temporal_evidence"]["mentions"]
    assert stored[0]["raw_text"] == "本月底"
    assert stored[0]["role"] == "CUSTOMER_COMMITMENT"


def test_extra_mention_field_is_rejected() -> None:
    text = "叶老师反馈本月底会完成"
    span = find_time_spans(text)[0]
    mention = {
        "raw_text": span.raw_text,
        "quote_start": span.start,
        "quote_end": span.end,
        "kind": span.kind,
        "role": "CUSTOMER_COMMITMENT",
        "iso_date": "2026-10-31",
    }
    with pytest.raises(TemporalContractError, match="illegal temporal mention"):
        ensure_mentions_cover_source(text, [mention])


def test_action_quote_miss_is_an_action_contract_error() -> None:
    text = "叶老师会完成准备"
    draft = _draft(text)
    with pytest.raises(ActionContractError, match="action quote is not in the source"):
        attach_model_evidence(
            draft,
            segment_id="seg_test",
            segment_text=text,
            anchor=ANCHOR,
            mentions=[],
            actions=[
                ModelDraftAction(
                    action_ref="a1",
                    owner_role="CUSTOMER",
                    owner_text="叶老师",
                    action_text="完成准备",
                    action_status="COMMITTED",
                    evidence_quote="不在原文",
                    quote_start=0,
                    quote_end=4,
                )
            ],
        )

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



FUTURES = (
    "今天微信联系了上海期货信息技术有限公司的代理商商务左总对齐合同和发票方面的情况，"
    "目前合同已经走完盖章流程，左总反馈发票今天可以开具，预计11月份可以完成付款；"
    "11月15号跟进付款方面的情况"
)


def _span(raw, start, end, kind, role, ref, owner=""):
    return {
        "raw_text": raw,
        "quote_start": start,
        "quote_end": end,
        "kind": kind,
        "role": role,
        "owner": owner,
        "action_ref": ref,
        "confidence": 0.9,
    }


def _futures_mentions(*, month_kind: str = "UNKNOWN") -> list[dict[str, object]]:
    return [
        _span("今天", 0, 2, "RELATIVE_DAY", "SALES_FOLLOW_UP", "a1"),
        _span("今天", 59, 61, "RELATIVE_DAY", "CUSTOMER_COMMITMENT", "a3", "左总"),
        _span("11月份", 68, 72, month_kind, "CUSTOMER_COMMITMENT", "a4", "左总"),
        _span("11月15号", 79, 85, "MONTH_DAY", "SALES_FOLLOW_UP", "a5"),
    ]


def _act(ref, role, text, status, start, end, owner=""):
    return {
        "action_ref": ref,
        "owner_role": role,
        "owner_text": owner,
        "action_text": text,
        "action_status": status,
        "evidence_quote": FUTURES[start:end],
        "quote_start": start,
        "quote_end": end,
    }


def _futures_actions() -> list[dict[str, object]]:
    return [
        _act("a1", "SALES", "微信联系对齐合同和发票", "COMPLETED", 0, 39),
        _act("a3", "CUSTOMER", "发票今天可以开具", "COMMITTED", 53, 65, "左总"),
        _act("a4", "CUSTOMER", "预计11月份可以完成付款", "PLANNED", 66, 78, "左总"),
        _act("a5", "SALES", "11月15号跟进付款方面的情况", "PLANNED", 79, 94),
    ]


def test_digit_month_is_a_span_and_does_not_swallow_the_follow_up_day() -> None:
    spans = [(item.kind, item.raw_text) for item in find_time_spans(FUTURES)]
    assert spans == [
        ("RELATIVE_DAY", "今天"),
        ("RELATIVE_DAY", "今天"),
        ("UNKNOWN", "11月份"),
        ("MONTH_DAY", "11月15号"),
    ]
    ensure_mentions_cover_source(FUTURES, _futures_mentions())


def test_digit_month_commitment_stays_month_level_and_sales_keeps_november_15() -> None:
    draft = _draft(FUTURES)
    attach_model_evidence(
        draft,
        segment_id="seg_futures",
        segment_text=FUTURES,
        anchor=datetime(2026, 10, 29, 19, 0),
        mentions=_futures_mentions(),
        actions=_futures_actions(),
    )
    listed = draft.content_json["temporal_evidence"]["mentions"]
    mentions = {item["raw_text"]: item for item in listed}
    todays = [item for item in listed if item["raw_text"] == "今天"]
    assert [item["role"] for item in todays] == ["OTHER", "CUSTOMER_COMMITMENT"]
    assert mentions["11月份"]["year"] == 2026
    assert mentions["11月份"]["month"] == 11
    assert mentions["11月份"]["day"] is None
    assert mentions["11月份"]["resolved_at"] is None
    assert mentions["11月份"]["resolution_status"] == "RESOLVED"
    assert mentions["11月份"]["role"] == "CUSTOMER_COMMITMENT"
    assert mentions["11月15号"]["role"] == "SALES_FOLLOW_UP"
    assert mentions["11月15号"]["resolved_at"] == "2026-11-15T00:00:00"
    texts = [item["text"] for item in draft.content_json["customer_commitments"]]
    assert "左总发票今天可以开具。" in texts
    assert "左总预计11月份可以完成付款。" in texts
    assert temporal_waiting(draft) is None
    resolved, granularity = resolved_sales_follow_up(draft)
    assert (resolved, granularity) == (datetime(2026, 11, 15), "DATE")


def test_past_digit_month_uses_next_year() -> None:
    text = "预计11月份可以完成付款"
    draft = _draft(text)
    attach_model_evidence(
        draft,
        segment_id="seg_past",
        segment_text=text,
        anchor=datetime(2026, 12, 2, 9, 0),
        mentions=[{
            "raw_text": "11月份",
            "quote_start": 2,
            "quote_end": 6,
            "kind": "UNKNOWN",
            "role": "CUSTOMER_COMMITMENT",
            "owner": "左总",
            "action_ref": "a1",
            "confidence": 0.9,
        }],
        actions=[{
            "action_ref": "a1",
            "owner_role": "CUSTOMER",
            "owner_text": "左总",
            "action_text": "预计11月份可以完成付款",
            "action_status": "COMMITTED",
            "evidence_quote": text,
            "quote_start": 0,
            "quote_end": len(text),
        }],
    )
    mention = draft.content_json["temporal_evidence"]["mentions"][0]
    assert (mention["year"], mention["month"], mention["day"]) == (2027, 11, None)
    assert temporal_waiting(draft) is None


def test_wrong_kind_for_digit_month_is_still_rejected() -> None:
    draft = _draft(FUTURES)
    with pytest.raises(TemporalContractError, match="temporal mention does not match a source span"):
        attach_model_evidence(
            draft,
            segment_id="seg_futures",
            segment_text=FUTURES,
            anchor=datetime(2026, 10, 29, 19, 0),
            mentions=_futures_mentions(month_kind="MONTH_DAY"),
            actions=_futures_actions(),
        )


FOLLOW_UP_WITH_AFTERNOON_AND_WEEK = (
    "今天下午电话跟进广东智通人才连锁股份有限公司，已和下周三确认预算并发送正式报价，客户预计下周反馈。"
)


def test_afternoon_without_clock_and_bare_week_are_source_spans() -> None:
    spans = [(item.kind, item.raw_text) for item in find_time_spans(FOLLOW_UP_WITH_AFTERNOON_AND_WEEK)]
    assert spans == [
        ("RELATIVE_DAY", "今天下午"),
        ("RELATIVE_WEEKDAY", "下周三"),
        ("RELATIVE_WEEK", "下周"),
    ]
    assert [(item.kind, item.raw_text) for item in find_time_spans("下周三")] == [
        ("RELATIVE_WEEKDAY", "下周三")
    ]
    assert find_time_spans("我下周三下午三点发方案")[0].raw_text == "下周三下午三点"


def test_model_quotes_of_afternoon_and_bare_week_cover_the_source() -> None:
    text = FOLLOW_UP_WITH_AFTERNOON_AND_WEEK
    mentions = [
        ModelTemporalMention(
            raw_text="今天下午",
            quote_start=0,
            quote_end=4,
            kind="RELATIVE_DAY",
            role="SALES_FOLLOW_UP",
            confidence=1,
        ),
        ModelTemporalMention(
            raw_text="下周三",
            quote_start=text.find("下周三"),
            quote_end=text.find("下周三") + 3,
            kind="RELATIVE_WEEKDAY",
            role="SALES_FOLLOW_UP",
            action_ref="a1",
            confidence=1,
        ),
        ModelTemporalMention(
            raw_text="下周",
            quote_start=text.rfind("下周"),
            quote_end=text.rfind("下周") + 2,
            kind="RELATIVE_WEEK",
            role="CUSTOMER_COMMITMENT",
            confidence=1,
        ),
    ]
    ensure_mentions_cover_source(text, mentions)
    draft = _draft(text)
    attach_model_evidence(
        draft,
        segment_id="seg_follow_up",
        segment_text=text,
        anchor=datetime(2026, 10, 29, 21, 36),
        mentions=mentions,
        actions=[
            {
                "action_ref": "a1",
                "owner_role": "SALES",
                "owner_text": "我",
                "action_text": "确认预算并发送正式报价",
                "action_status": "PLANNED",
                "evidence_quote": "下周三确认预算并发送正式报价",
                "quote_start": text.find("下周三确认预算并发送正式报价"),
                "quote_end": text.find("下周三确认预算并发送正式报价") + len("下周三确认预算并发送正式报价"),
            }
        ],
    )
    stored = {item["raw_text"]: item for item in draft.content_json["temporal_evidence"]["mentions"]}
    assert stored["今天下午"]["resolved_at"] == "2026-10-29T00:00:00"
    assert stored["下周三"]["resolved_at"] == "2026-11-04T00:00:00"
    assert stored["下周"]["resolution_status"] == "RESOLVED"
    assert stored["下周"]["granularity"] == "UNKNOWN"
    assert stored["下周"]["resolved_at"] is None
    assert temporal_waiting(draft) is None
    resolved, granularity = resolved_sales_follow_up(draft)
    assert (resolved, granularity) == (datetime(2026, 11, 4), "DATE")

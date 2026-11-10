"""Model-labelled input noise may remove questions, never business facts or source text."""

# ruff: noqa: RUF001

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.services.assistant.activity_channel import resolve_channel
from app.services.assistant.contracts import DraftField, SourceSegment, TaskDraft
from app.services.assistant.coordinator import AssistantCoordinator, AssistantInput
from app.services.assistant.llm_contracts import (
    KindDecision,
    ModelDraftAction,
    ModelTemporalMention,
    StructureDraftResult,
)
from app.services.assistant.noise import ignored_noise_summary, record_noise
from app.services.assistant.temporal_evidence import attach_model_evidence, temporal_waiting
from tests.unit.test_assistant_follow_up_context import Chooser, Context, Gate, _task, db_session  # noqa: F401

ANCHOR = datetime(2026, 11, 10, 15, 0)
SAMPLE = (
    "13:45 张总：我们这边预算已经批了。\n"
    "13:47 我：好的，我下周三再联系您确认合同细节。\n"
    "13:52 李工：部署环境我们月底前准备好。"
)


def _span(text: str, raw: str, nth: int = 0) -> tuple[int, int]:
    start = -1
    for _ in range(nth + 1):
        start = text.index(raw, start + 1)
    return start, start + len(raw)


def _label(text: str, kind: str, raw: str, nth: int = 0) -> dict[str, object]:
    start, end = _span(text, raw, nth)
    return {"kind": kind, "raw_text": raw, "quote_start": start, "quote_end": end}


def _decision(text: str, *labels: tuple[str, str], **fields: object) -> KindDecision:
    return KindDecision(noise_spans=[_label(text, kind, raw) for kind, raw in labels], **fields)


def _sourced(text: str) -> TaskDraft:
    draft = TaskDraft(
        content=DraftField(status="CANDIDATE", value=text), content_json={"content": text}, source_segments=[text]
    )
    draft.source_records.append(SourceSegment(segment_id="seg", turn_id=None, recorded_at=ANCHOR, text=text))
    return draft


def _mention(text: str, raw: str, role: str, ref: str = "", kind: str = "UNKNOWN") -> dict[str, object]:
    start, end = _span(text, raw)
    return {
        "raw_text": raw,
        "quote_start": start,
        "quote_end": end,
        "kind": kind,
        "role": role,
        "owner": "",
        "action_ref": ref,
        "confidence": 0.9,
    }


def _action(text: str, ref: str, owner: str, quote: str, action_text: str) -> dict[str, object]:
    start, end = _span(text, quote)
    return {
        "action_ref": ref,
        "owner_role": owner,
        "owner_text": "",
        "action_text": action_text,
        "action_status": "PLANNED",
        "evidence_quote": quote,
        "quote_start": start,
        "quote_end": end,
    }


def _attach(text: str, draft: TaskDraft, mentions: list[dict], actions: list[dict]) -> TaskDraft:
    attach_model_evidence(draft, segment_id="seg", segment_text=text, anchor=ANCHOR, mentions=mentions, actions=actions)
    return draft


def test_speaker_timestamps_never_become_questions_and_business_times_keep_their_roles() -> None:
    labels = [("SPEAKER_TIMESTAMP", raw) for raw in ("13:45", "13:47", "13:52")]
    draft = _sourced(SAMPLE)
    record_noise(draft, SAMPLE, _decision(SAMPLE, *labels))
    _attach(
        SAMPLE,
        draft,
        [
            *(_mention(SAMPLE, raw, "OTHER") for raw in ("13:45", "13:47", "13:52")),
            _mention(SAMPLE, "下周三", "SALES_FOLLOW_UP", "s", "RELATIVE_WEEKDAY"),
            _mention(SAMPLE, "月底", "CUSTOMER_COMMITMENT", "c", "MONTH_SEGMENT"),
        ],
        [
            _action(SAMPLE, "s", "SALES", "我下周三再联系您确认合同细节", "联系张总确认合同细节"),
            _action(SAMPLE, "c", "CUSTOMER", "部署环境我们月底前准备好", "准备部署环境"),
        ],
    )
    roles = {item["raw_text"]: item["role"] for item in draft.content_json["temporal_evidence"]["mentions"]}
    assert roles == {"下周三": "SALES_FOLLOW_UP", "月底": "CUSTOMER_COMMITMENT"}
    assert temporal_waiting(draft) is None
    assert ignored_noise_summary(draft) == "已忽略 3 处发言时间"
    assert draft.source_records[0].text == SAMPLE


def test_label_touching_a_business_time_is_dropped() -> None:
    text = "13:47 我：明天下午 2 点再电话确认"
    verified = _sourced(text)
    record_noise(verified, text, _decision(text, ("SPEAKER_TIMESTAMP", "13:47"), ("SPEAKER_TIMESTAMP", "2 点")))
    assert [item.raw_text for item in verified.input_noise] == ["13:47"]
    meeting = "今天下午 13:45 和张总开会"
    draft = _sourced(meeting)
    record_noise(draft, meeting, _decision(meeting, ("SPEAKER_TIMESTAMP", "13:45")))
    assert draft.input_noise == []


@pytest.mark.parametrize(
    ("text", "raw"),
    [
        ("[00:12:33] 张总：预算批了", "[00:12:33]"),
        ("说话人1 00:03 预算批了", "00:03"),
        ("张总 下午1:45\n预算批了", "下午1:45"),
    ],
)
def test_transcript_timestamp_forms_are_not_asked(text: str, raw: str) -> None:
    draft = _sourced(text)
    record_noise(draft, text, _decision(text, ("SPEAKER_TIMESTAMP", raw)))
    mentions = [_mention(text, raw, "SALES_FOLLOW_UP", "s")]
    _attach(text, draft, mentions, [_action(text, "s", "SALES", raw, "跟进")])
    from app.services.assistant.temporal_evidence import resolved_sales_follow_up

    assert resolved_sales_follow_up(draft) == (None, "UNKNOWN")
    assert temporal_waiting(draft) is None


def test_timestamp_quoted_as_an_action_clears_the_mention_reference_instead_of_failing() -> None:
    draft = _sourced(SAMPLE)
    record_noise(draft, SAMPLE, _decision(SAMPLE, ("SPEAKER_TIMESTAMP", "13:52")))
    _attach(
        SAMPLE,
        draft,
        [
            _mention(SAMPLE, "下周三", "SALES_FOLLOW_UP", "s", "RELATIVE_WEEKDAY"),
            _mention(SAMPLE, "13:52", "OTHER", "t"),
        ],
        [
            _action(SAMPLE, "s", "SALES", "我下周三再联系您确认合同细节", "联系张总"),
            _action(SAMPLE, "t", "OTHER", "13:52", "发言"),
        ],
    )
    evidence = draft.content_json["temporal_evidence"]
    assert "13:52" not in [item["raw_text"] for item in evidence["mentions"]]
    assert all(item["evidence_quote"] != "13:52" for item in evidence["actions"])


def test_mentioned_only_channels_do_not_block_the_meeting_kind() -> None:
    text = "今天和张总开了线上会议，会后邮件发纪要，有问题电话沟通"
    decision = _decision(
        text,
        ("CHANNEL_MENTION", "邮件"),
        ("CHANNEL_MENTION", "电话"),
        kind="ONLINE_MEETING",
        confidence=0.92,
        evidence_quote="线上会议",
        channels=["ONLINE_MEETING"],
    )
    assert resolve_channel(text, decision, model_failed=False).status == "family_unclear"
    draft = _sourced(text)
    masked = record_noise(draft, text, decision)
    resolved = resolve_channel(masked, decision, model_failed=False)
    assert (resolved.status, resolved.kind) == ("recognized", "ONLINE_MEETING")
    assert ignored_noise_summary(draft) == "已忽略 2 处渠道提及"
    assert draft.source_records[0].text == text


def test_channel_label_cannot_hide_the_quoted_evidence() -> None:
    text = "今天电话跟张总沟通了报价"
    decision = _decision(
        text, ("CHANNEL_MENTION", "电话"), kind="PHONE_FOLLOW_UP", confidence=0.95, evidence_quote="电话"
    )
    draft = _sourced(text)
    resolved = resolve_channel(record_noise(draft, text, decision), decision, model_failed=False)
    assert resolved.kind == "PHONE_FOLLOW_UP"
    assert draft.input_noise == []


def test_unlocatable_or_unmatched_labels_have_no_effect() -> None:
    text = "张总 13:45 电话沟通了报价"
    decision = KindDecision(
        noise_spans=[
            {"kind": "SPEAKER_TIMESTAMP", "raw_text": "14:00", "quote_start": 0, "quote_end": 5},
            {"kind": "CHANNEL_MENTION", "raw_text": "微信", "quote_start": 0, "quote_end": 2},
        ]
    )
    draft = _sourced(text)
    assert record_noise(draft, text, decision) == text
    assert draft.input_noise == []
    elsewhere = _sourced("另一段原文")
    assert record_noise(elsewhere, text, _decision(text, ("SPEAKER_TIMESTAMP", "13:45"))) == text
    assert elsewhere.input_noise == []


def test_malformed_noise_label_fails_the_whole_classification() -> None:
    with pytest.raises(ValidationError):
        KindDecision(
            noise_spans=[
                {"kind": "SPEAKER_TIMESTAMP", "raw_text": "13:45", "quote_start": 0, "quote_end": 5, "role": "OTHER"}
            ]
        )
    with pytest.raises(ValidationError):
        KindDecision(noise_spans=[{"kind": "SPEAKER_NAME", "raw_text": "张总", "quote_start": 0, "quote_end": 2}])


async def test_sample_note_reaches_confirmation_with_ignored_timestamps(db_session, monkeypatch):  # noqa: F811
    monkeypatch.setattr("app.utils.time.business_now", lambda: ANCHOR)
    text = "广州睿狐科技有限公司\n" + SAMPLE
    labels = [("SPEAKER_TIMESTAMP", raw) for raw in ("13:45", "13:47", "13:52")]

    class Structurer:
        async def classify(self, db, *, team_id, user_text):
            assert user_text == text
            return _decision(text, *labels, kind="OTHER_FOLLOW_UP", confidence=0.95, evidence_quote="联系")

        async def structure(self, db, *, team_id, kind, user_text):
            return StructureDraftResult(
                kind_confirmed="FOLLOW_UP",
                content="张总预算已批；李工月底前准备部署环境。",
                customer_name="广州睿狐科技有限公司",
                next_action="联系张总确认合同细节",
                next_follow_time_text="下周三",
                content_json={
                    "content": "张总预算已批；李工月底前准备部署环境。",
                    "next_action": "联系张总确认合同细节",
                },
                temporal_mentions=[
                    ModelTemporalMention.model_validate(_mention(text, raw, "OTHER")) for raw in ("13:45", "13:47")
                ]
                + [
                    ModelTemporalMention.model_validate(
                        _mention(text, "下周三", "SALES_FOLLOW_UP", "s", "RELATIVE_WEEKDAY")
                    ),
                    ModelTemporalMention.model_validate(
                        _mention(text, "月底", "CUSTOMER_COMMITMENT", "c", "MONTH_SEGMENT")
                    ),
                ],
                actions=[
                    ModelDraftAction.model_validate(
                        _action(text, "s", "SALES", "我下周三再联系您确认合同细节", "联系张总确认合同细节")
                    ),
                    ModelDraftAction.model_validate(
                        _action(text, "c", "CUSTOMER", "部署环境我们月底前准备好", "准备部署环境")
                    ),
                ],
            )

    outcome = await AssistantCoordinator(
        Chooser(), structurer=Structurer(), quality_gate=Gate(), follow_up=Context("广州睿狐科技有限公司")
    ).handle_task(db_session, _task(db_session), AssistantInput(kind="text", text=text))
    waiting = outcome.reply.waiting
    assert waiting is not None and waiting.type == "CONFIRMATION"
    preview = waiting.confirmation_payload.preview
    assert preview.ignored_noise_summary == "已忽略 3 处发言时间"
    assert preview.source_content == text
    command = outcome.task.authority_json["frozen_activity_command"]
    assert command["next_follow_time"].startswith("2026-11-18")
    assert command["ignored_noise_summary"] == "已忽略 3 处发言时间"

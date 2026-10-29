# ruff: noqa: RUF001
"""Server acceptance of model-nominated activity channels."""

from app.services.assistant.activity_channel import HIGH_CONFIDENCE, resolve_channel
from app.services.assistant.llm_contracts import KindDecision

PHONE = "今天电话联系了客户，报价还在内部评估。"


def test_high_confidence_phone_quote_is_accepted() -> None:
    decision = KindDecision(
        kind="PHONE_FOLLOW_UP",
        confidence=HIGH_CONFIDENCE,
        evidence_quote="电话联系",
    )
    resolved = resolve_channel(PHONE, decision, model_failed=False)
    assert resolved.status == "recognized"
    assert resolved.kind == "PHONE_FOLLOW_UP"
    assert resolved.source == "model"
    assert resolved.status_label == "AI 已识别 · 高置信度"
    assert resolved.source_text == "从“电话联系”中识别"
    assert resolved.family == "FOLLOW_UP"
    assert "ONLINE_MEETING" not in resolved.options


def test_confidence_below_threshold_must_be_chosen() -> None:
    decision = KindDecision(kind="PHONE_FOLLOW_UP", confidence=0.79, evidence_quote="电话联系")
    resolved = resolve_channel(PHONE, decision, model_failed=False)
    assert resolved.status == "required"
    assert resolved.kind is None
    assert resolved.status_label == "未识别 · 需要确认"
    assert resolved.options[0] == "PHONE_FOLLOW_UP"


def test_quote_missing_from_source_uses_keyword_fallback() -> None:
    decision = KindDecision(kind="WECHAT_FOLLOW_UP", confidence=0.95, evidence_quote="没说过的话")
    resolved = resolve_channel(PHONE, decision, model_failed=False)
    assert resolved.status == "recognized"
    assert resolved.kind == "PHONE_FOLLOW_UP"
    assert resolved.source == "keyword"
    assert resolved.status_label == "已识别 · 词表兜底"


def test_model_failure_uses_one_keyword_and_refuses_many() -> None:
    phone = resolve_channel(PHONE, None, model_failed=True)
    assert phone.kind == "PHONE_FOLLOW_UP" and phone.source == "keyword"
    mixed = resolve_channel("电话和微信都沟通了", None, model_failed=True)
    assert mixed.status == "required" and mixed.kind is None
    vague = resolve_channel("跟进了客户", None, model_failed=True)
    assert vague.status == "required"
    visit = resolve_channel("上门拜访了客户", None, model_failed=True)
    assert visit.kind == "VISIT_FOLLOW_UP"
    meeting = resolve_channel("今天下午开了线上会议", None, model_failed=True)
    assert meeting.kind == "ONLINE_MEETING" and meeting.family == "ONLINE_MEETING"


def test_phone_number_alone_is_not_a_phone_follow_up() -> None:
    resolved = resolve_channel("请把电话号码发我", None, model_failed=True)
    assert resolved.kind is None
    assert resolved.status == "required"


def test_high_confidence_cannot_hide_a_second_channel() -> None:
    decision = KindDecision(kind="PHONE_FOLLOW_UP", confidence=0.99, evidence_quote="电话")
    resolved = resolve_channel("电话和微信都沟通了", decision, model_failed=False)
    assert resolved.status == "required"
    assert resolved.kind is None


def test_meeting_nomination_stays_on_the_meeting_schema() -> None:
    text = "今天下午开了线上会议，确认了范围。"
    decision = KindDecision(kind="ONLINE_MEETING", confidence=0.91, evidence_quote="线上会议")
    resolved = resolve_channel(text, decision, model_failed=False)
    assert resolved.kind == "ONLINE_MEETING"
    assert resolved.options == ("ONLINE_MEETING", "OFFLINE_MEETING")


def test_meeting_plus_phone_does_not_pick_a_schema() -> None:
    text = "今天电话联系了客户，然后开了线上会议。"
    decision = KindDecision(
        kind="ONLINE_MEETING",
        confidence=0.93,
        evidence_quote="线上会议",
        channels=["ONLINE_MEETING", "PHONE_FOLLOW_UP"],
    )
    resolved = resolve_channel(text, decision, model_failed=False)
    assert resolved.status == "family_unclear"
    assert resolved.kind is None

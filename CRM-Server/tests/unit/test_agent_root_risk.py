"""Deterministic Root intent guardrail tests."""

from app.services.agent.orchestrator.risk import (
    has_explicit_follow_up_record_intent,
    has_explicit_write_intent,
)


def test_completed_customer_contact_with_business_update_is_follow_up_write() -> None:
    text = "微信联系了凡亚信息，技术经理张总反馈项目正在走立项流程"  # noqa: RUF001

    assert has_explicit_follow_up_record_intent(text) is True
    assert has_explicit_write_intent(text) is True


def test_completed_customer_contact_with_next_plan_is_follow_up_write() -> None:
    text = "电话沟通过凡亚信息，下周三继续跟进立项流程"  # noqa: RUF001

    assert has_explicit_follow_up_record_intent(text) is True


def test_contact_history_question_is_not_follow_up_write() -> None:
    text = "看看上周微信联系了哪些客户"

    assert has_explicit_follow_up_record_intent(text) is False
    assert has_explicit_write_intent(text) is False


def test_future_follow_up_query_without_completed_contact_is_not_write() -> None:
    text = "下周有哪些客户需要继续跟进"

    assert has_explicit_follow_up_record_intent(text) is False
    assert has_explicit_write_intent(text) is False


def test_contact_method_question_is_not_follow_up_write() -> None:
    text = "微信怎么联系客户"

    assert has_explicit_follow_up_record_intent(text) is False


def test_customer_status_question_after_historical_contact_is_not_follow_up_write() -> None:
    text = "我联系过凡亚信息，项目现在是什么状态"  # noqa: RUF001

    assert has_explicit_follow_up_record_intent(text) is False
    assert has_explicit_write_intent(text) is False


def test_confirm_word_does_not_turn_explicit_customer_query_into_write() -> None:
    text = "确认一下上海有哪些客户"

    assert has_explicit_follow_up_record_intent(text) is False
    assert has_explicit_write_intent(text) is False

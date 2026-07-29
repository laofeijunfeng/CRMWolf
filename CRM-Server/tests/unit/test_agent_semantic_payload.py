"""Semantic result to CRM payload conversion tests."""
from __future__ import annotations

from datetime import datetime

from app.services.agent.schemas import AgentSemanticParseResult
from app.services.agent.semantic_payload import parsed_from_semantic


class FakeTemporalResolver:
    def resolve_follow_up_time(self, expression, *, base_datetime=None):
        if expression is None:
            return None
        assert isinstance(base_datetime, datetime)
        return "2026-08-05T09:00:00"

    def resolve_date(self, expression, *, base_datetime=None):
        if expression is None:
            return None
        if expression.raw_text == "今天":
            return "2026-07-29"
        if expression.raw_text == "月底":
            return "2026-07-31"
        return None


def test_parsed_from_semantic_builds_payment_and_follow_up_payloads():
    semantic_result = AgentSemanticParseResult.model_validate({
        "intent": "PAYMENT_RECORD",
        "intent_confidence": 0.95,
        "customer": {"name_text": "越秀金融", "confidence": 0.95},
        "follow_up": {
            "content": "客户今天已付款",
            "method": "微信",
            "next_action": "下周核对发票",
            "next_follow_time_text": "下周三",
            "next_follow_time": {
                "raw_text": "下周三",
                "kind": "RELATIVE_WEEKDAY",
                "direction": "next",
                "weekday": 3,
                "confidence": 0.9,
            },
        },
        "payment": {
            "actual_amount": 5000,
            "actual_payer_name": "越秀金融",
            "payment_date_text": "今天",
            "payment_date": {
                "raw_text": "今天",
                "kind": "RELATIVE_DAY",
                "direction": "current",
                "amount": 0,
                "unit": "day",
                "confidence": 0.9,
            },
            "notes": "首款",
        },
    })

    parsed = parsed_from_semantic(
        semantic_result,
        "原始内容",
        temporal_resolver=FakeTemporalResolver(),
        base_datetime=datetime(2026, 7, 29, 10, 0, 0),
    )

    assert parsed["customer_name"] == "越秀金融"
    assert parsed["follow_up_content"] == "客户今天已付款"
    assert parsed["next_follow_time_iso"] == "2026-08-05T09:00:00"
    assert parsed["payment"] == {
        "actual_amount": 5000.0,
        "actual_payer_name": "越秀金融",
        "payment_date_text": "今天",
        "payment_date_iso": "2026-07-29",
        "notes": "首款",
    }
    assert parsed["missing_payment_fields"] == []


def test_parsed_from_semantic_computes_opportunity_missing_fields_with_resolved_date():
    semantic_result = AgentSemanticParseResult.model_validate({
        "intent": "CREATE_OPPORTUNITY",
        "intent_confidence": 0.95,
        "customer": {"name_text": "越秀金融", "confidence": 0.95},
        "opportunity": {
            "total_amount": 120000,
            "user_count": 30,
            "license_type": "SUBSCRIPTION",
            "purchase_type": "NEW",
            "expected_closing_date_text": "月底",
            "expected_closing_date": {
                "raw_text": "月底",
                "kind": "MONTH_END",
                "direction": "current",
                "confidence": 0.9,
            },
        },
    })

    parsed = parsed_from_semantic(
        semantic_result,
        "创建商机",
        temporal_resolver=FakeTemporalResolver(),
        base_datetime=datetime(2026, 7, 29, 10, 0, 0),
    )

    assert parsed["opportunity"]["expected_closing_date"] == "2026-07-31"
    assert parsed["missing_opportunity_fields"] == ["subscription_years"]

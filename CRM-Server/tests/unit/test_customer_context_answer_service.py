import pytest

from app.crud.ai_config import ai_config_crud
from app.services.customer_context_answer_service import CustomerContextAnswerService
from app.services.agent.schemas import CustomerContextAnswerResult


@pytest.mark.asyncio
async def test_customer_context_answer_fallback_uses_business_context_without_technical_tokens(monkeypatch):
    monkeypatch.setattr(ai_config_crud, "get_config", lambda db, team_id: None)
    service = CustomerContextAnswerService()

    envelope = await service.answer_with_metadata(
        object(),
        team_id=2,
        question="总结一下这个客户现在什么情况",
        customer_context={
            "strong_context": {
                "customer": {
                    "id": 101,
                    "account_name": "越秀金融",
                    "industry_name": "金融",
                    "city": "广州",
                },
                "customer_facts": [{
                    "id": 501,
                    "fact_type": "stage",
                    "content": "客户已经进入 POC。",
                    "confidence": 0.91,
                }],
                "opportunities": [{
                    "id": 301,
                    "name": "CRM 项目",
                    "stage": "POC",
                    "amount": "120000",
                    "procurement_method_id": 2,
                }],
                "contracts": [],
                "payment_plans": [],
                "recent_activities": [{
                    "id": 801,
                    "content": "张总说本周开始 POC。",
                    "source_type": "customer_activity",
                }],
            },
            "semantic_evidence": [{
                "evidence_id": "ev-1",
                "source_type": "follow_up",
                "text": "张总说本周开始 POC。",
            }],
        },
        customer_memory={
            "namespace_prefix": ["2", "customer", "101"],
            "summaries": [{"key": "latest", "value": {"summary": "客户正在 POC"}}],
        },
    )

    answer = envelope.result.answer
    assert envelope.answer_source == "deterministic_context_fallback"
    assert answer.startswith("### 越秀金融客户现状")
    assert "- **推进中的商机**" in answer
    assert "越秀金融" in answer
    assert "POC" in answer
    assert "source_type" not in answer
    assert "procurement_method_id" not in answer
    assert "evidence_id" not in answer


def test_customer_context_answer_cleaning_preserves_markdown_section_breaks():
    result = CustomerContextAnswerResult(
        answer=(
            "中科院信工所当前情况\n\n"
            "### 1. 客户现状\n"
            "客户是政府/公共机构客户。\n\n"
            "### 2. 商机与合同进展\n"
            "合同已签。"
        ),
        confidence=0.93,
        used_sections=["customer", "opportunities"],
        missing_context=[],
    )

    cleaned = CustomerContextAnswerService._clean_result(result)

    assert "当前情况\n\n### 1. 客户现状" in cleaned.answer
    assert "客户。\n\n### 2. 商机与合同进展" in cleaned.answer
    assert "当前情况 ### 1." not in cleaned.answer


def test_customer_context_answer_cleaning_repairs_inline_numbered_headings():
    result = CustomerContextAnswerResult(
        answer="中科院信工所当前情况 ### 1. 客户现状\n客户资料完整。 ### 2. 商机与合同进展\n合同已签。",
        confidence=0.93,
        used_sections=["customer", "contracts"],
        missing_context=[],
    )

    cleaned = CustomerContextAnswerService._clean_result(result)

    assert "当前情况\n\n### 1. 客户现状" in cleaned.answer
    assert "资料完整。\n\n### 2. 商机与合同进展" in cleaned.answer

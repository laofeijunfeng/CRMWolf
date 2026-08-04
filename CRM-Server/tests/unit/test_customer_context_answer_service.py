import pytest

from app.crud.ai_config import ai_config_crud
from app.services.agent.schemas import CustomerContextAnswerResult
from app.services.customer_context_answer_service import CustomerContextAnswerService
from app.services.customer_context_answer_telemetry_service import CustomerContextAnswerTelemetryService


class RecordingTelemetry(CustomerContextAnswerTelemetryService):
    def __init__(self) -> None:
        self.calls = []

    def record_answer(self, db, **kwargs):
        self.calls.append({"db": db, **kwargs})
        return None


@pytest.mark.asyncio
async def test_customer_context_answer_fallback_uses_business_context_without_technical_tokens(monkeypatch):
    monkeypatch.setattr(ai_config_crud, "get_config", lambda db, team_id: None)
    telemetry = RecordingTelemetry()
    service = CustomerContextAnswerService(telemetry_service=telemetry)

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
                "score": 0.91,
                "source_type": "follow_up",
                "source_object_id": "801",
                "title": "电话跟进",
                "text": "张总说本周开始 POC。",
            }],
            "retrieval": {"status": "ok", "enabled": True, "top_score": 0.91},
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
    assert envelope.result.answer_mode == "grounded"
    assert envelope.result.citations[0]["evidence_id"] == "ev-1"
    assert envelope.result.citations[0]["score"] == 0.91
    assert telemetry.calls[0]["team_id"] == 2
    assert telemetry.calls[0]["question"] == "总结一下这个客户现在什么情况"
    assert telemetry.calls[0]["answer_source"] == "deterministic_context_fallback"
    assert telemetry.calls[0]["fallback_reason"] == "ai_config_missing"
    assert telemetry.calls[0]["result"].answer_mode == "grounded"


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


def test_customer_context_answer_fallback_uses_completed_customer_profile():
    result = CustomerContextAnswerService.fallback_answer(
        question="汇川技术现在是什么情况",
        customer_context={
            "strong_context": {
                "customer": {
                    "account_name": "汇川技术",
                    "profile_status": "COMPLETED",
                    "company_background": "工业自动化控制与新能源领域的上市公司。",
                    "main_business": "主营工业自动化、新能源汽车电驱与轨道交通牵引系统。",
                    "project_background": "正在评估 CRM 用于规范大客户销售过程。",
                    "customer_brief_markdown": "## 客户概况\n客户重点关注销售过程管理和项目预测。",
                },
                "customer_facts": [],
                "opportunities": [],
                "contracts": [],
                "payment_plans": [],
                "recent_activities": [],
            },
            "semantic_evidence": [],
            "retrieval": {"status": "embedding_unavailable", "enabled": True},
        },
        customer_memory={},
    )

    assert "工业自动化控制与新能源领域的上市公司" in result.answer
    assert "主营工业自动化、新能源汽车电驱与轨道交通牵引系统" in result.answer
    assert "正在评估 CRM 用于规范大客户销售过程" in result.answer
    assert "客户重点关注销售过程管理和项目预测" in result.answer
    assert result.confidence > 0.45
    assert "profile" in result.used_sections
    assert result.missing_context == []
    assert result.answer_mode == "degraded"
    assert result.citations == []


def test_customer_context_answer_low_confidence_uses_fallback_policy():
    result = CustomerContextAnswerService.fallback_answer(
        question="客户 POC 进展怎么样",
        customer_context={
            "strong_context": {
                "customer": {
                    "account_name": "越秀金融",
                    "customer_brief_markdown": "## 客户概况\n客户正在推进 POC。",
                },
                "customer_facts": [],
                "opportunities": [{"name": "CRM 项目", "stage": "POC"}],
                "contracts": [],
                "payment_plans": [],
                "recent_activities": [],
            },
            "semantic_evidence": [],
            "retrieval": {
                "status": "low_confidence",
                "enabled": True,
                "top_score": 0.21,
                "min_score": 0.45,
            },
        },
        customer_memory={},
    )

    assert result.answer_mode == "fallback"
    assert result.citations == []
    assert result.confidence == 0.74
    assert "可引用的高置信度语义证据" in result.missing_context


def test_customer_context_answer_metadata_rejects_hallucinated_citations_without_auto_replacement():
    result = CustomerContextAnswerResult(
        answer="客户正在 POC。",
        confidence=0.9,
        used_sections=["customer", "evidence"],
        missing_context=[],
        answer_mode="grounded",
        citations=[{"evidence_id": "fake-ev", "score": 0.99}],
    )

    cleaned = CustomerContextAnswerService._with_answer_metadata(
        result,
        {
            "citations": [{"evidence_id": "real-ev", "score": 0.88, "text": "真实证据"}],
            "retrieval": {"status": "ok"},
        },
    )

    assert cleaned.answer_mode == "fallback"
    assert cleaned.citations == []
    assert "可验证的语义证据引用" in cleaned.missing_context


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

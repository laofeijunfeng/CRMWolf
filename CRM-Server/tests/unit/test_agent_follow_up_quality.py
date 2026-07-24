"""CRM AI Agent follow-up quality evaluator tests."""
import pytest

from app.services.agent.prompts import CRM_AGENT_FOLLOW_UP_QUALITY_SYSTEM_PROMPT, build_follow_up_quality_messages
from app.services.agent.quality import AgentFollowUpQualityEvaluator
from app.services.agent.schemas import AgentFollowUpQualityResult, AgentSemanticParseResult


def semantic_result():
    return AgentSemanticParseResult.model_validate({
        "intent": "CUSTOMER_FOLLOW_UP",
        "intent_confidence": 0.95,
        "customer": {"name_text": "睿狐科技", "confidence": 0.95},
        "follow_up": {
            "content": "客户已立项，预算 30 万，计划采购 100 人，下周三前提供招标参数版本",
            "method": "微信",
            "next_action": "提供招标参数版本",
            "next_follow_time_text": "下周三",
        },
        "contact": {},
        "invoice_title": {},
        "deployment_info": {},
        "business_signals": [{"type": "opportunity_progress", "summary": "客户已立项", "confidence": 0.95}],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": ["客户已立项", "预算 30 万"],
    })


def test_follow_up_quality_prompt_contains_six_principles_and_threshold():
    messages = build_follow_up_quality_messages(
        "今天睿狐科技说项目已立项，下周三前提供招标参数版本",
        semantic_result().model_dump_json(exclude_none=True),
        "{}",
    )

    assert "客户跟进记录质检 Agent" in messages[0]["content"]
    assert "事实优先原则" in CRM_AGENT_FOLLOW_UP_QUALITY_SYSTEM_PROMPT
    assert "动作闭环原则" in CRM_AGENT_FOLLOW_UP_QUALITY_SYSTEM_PROMPT
    assert "阶段推进原则" in CRM_AGENT_FOLLOW_UP_QUALITY_SYSTEM_PROMPT
    assert "决策穿透原则" in CRM_AGENT_FOLLOW_UP_QUALITY_SYSTEM_PROMPT
    assert "异议具象原则" in CRM_AGENT_FOLLOW_UP_QUALITY_SYSTEM_PROMPT
    assert "信息可接力原则" in CRM_AGENT_FOLLOW_UP_QUALITY_SYSTEM_PROMPT
    assert "如果总分达到 60 分" in CRM_AGENT_FOLLOW_UP_QUALITY_SYSTEM_PROMPT
    assert "【语义解析结果】" in messages[1]["content"]


def test_follow_up_quality_normalizes_threshold_behavior():
    evaluator = AgentFollowUpQualityEvaluator()

    passed = evaluator.normalize_result(AgentFollowUpQualityResult.model_validate({
        "score": 60,
        "passed": False,
        "reason": "基本可接力",
        "missing_aspects": ["决策链"],
        "supplement_question": "请补充决策链。",
        "principle_scores": {},
    }))
    blocked = evaluator.normalize_result(AgentFollowUpQualityResult.model_validate({
        "score": 59,
        "passed": True,
        "reason": "下一步不清楚",
        "missing_aspects": ["下一步动作", "时间", "责任人", "异议"],
        "supplement_question": None,
        "principle_scores": {},
    }))

    assert passed.passed is True
    assert passed.supplement_question is None
    assert blocked.passed is False
    assert blocked.missing_aspects == ["下一步动作", "时间", "责任人"]
    assert blocked.supplement_question == "这条跟进还差一点关键信息，请补充下一步由谁在什么时间做什么。"


@pytest.mark.asyncio
async def test_follow_up_quality_uses_langchain_structured_output_path():
    class FakeChatModel:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeAgent:
        async def ainvoke(self, payload):
            assert "messages" in payload
            return {
                "structured_response": AgentFollowUpQualityResult.model_validate({
                    "score": 72,
                    "passed": True,
                    "reason": "有事实、预算、下一步动作和时间。",
                    "missing_aspects": [],
                    "supplement_question": None,
                    "principle_scores": {},
                }),
            }

    calls = {}

    def fake_agent_factory(**kwargs):
        calls["response_format"] = kwargs["response_format"]
        calls["system_prompt"] = kwargs["system_prompt"]
        return FakeAgent()

    result = await AgentFollowUpQualityEvaluator(
        agent_factory=fake_agent_factory,
        chat_model_factory=FakeChatModel,
    )._evaluate_with_langchain(
        api_host="https://ai.example.com/v1",
        api_key="test-key",
        model="test-model",
        user_message="今天睿狐科技说项目已立项，下周三前提供招标参数版本",
        semantic_json=semantic_result().model_dump_json(exclude_none=True),
        memory_json="{}",
        principles_text="1. 事实优先原则（20分）：测试原则。",
        temperature=0.1,
    )

    assert calls["response_format"] is AgentFollowUpQualityResult
    assert "客户跟进记录质检 Agent" in calls["system_prompt"]
    assert "测试原则" in calls["system_prompt"]
    assert result.score == 72

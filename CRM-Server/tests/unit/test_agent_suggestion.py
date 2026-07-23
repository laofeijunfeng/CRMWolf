"""CRM AI Agent suggestion generator tests."""
import pytest

from app.services.agent.prompts import CRM_AGENT_SUGGESTION_SYSTEM_PROMPT, build_suggestion_messages
from app.services.agent.schemas import AgentSemanticParseResult, AgentSuggestionResult
from app.services.agent.suggestion import AgentSuggestionGenerator, AgentSuggestionGeneratorError


def semantic_result():
    return AgentSemanticParseResult.model_validate({
        "intent": "CUSTOMER_FOLLOW_UP",
        "intent_confidence": 0.95,
        "customer": {"name_text": "睿狐科技", "confidence": 0.95},
        "follow_up": {"content": "客户已立项，预算 30 万，计划采购 100 人"},
        "contact": {},
        "invoice_title": {},
        "deployment_info": {},
        "business_signals": [{"type": "opportunity_progress", "summary": "客户已立项", "confidence": 0.95}],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": ["预算 30 万"],
    })


def test_suggestion_prompt_contains_business_boundaries():
    messages = build_suggestion_messages(
        "今天睿狐科技提到项目已经立项成功",
        semantic_result().model_dump_json(exclude_none=True),
        '{"customer":{"id":1,"account_name":"睿狐科技"}}',
    )

    assert "业务建议生成器" in messages[0]["content"]
    assert "只生成建议，不执行任何业务动作" in messages[0]["content"]
    assert "创建合同第一版不支持" in CRM_AGENT_SUGGESTION_SYSTEM_PROMPT
    assert "【客户上下文】" in messages[1]["content"]


def test_suggestion_parser_accepts_json_object_wrapped_in_code_fence():
    result = AgentSuggestionGenerator().parse_raw_response("""
```json
{
  "summary": "客户项目已进入采购准备阶段。",
  "suggestions": [
    {
      "action": "CREATE_OPPORTUNITY",
      "title": "创建商机",
      "reason": "用户输入提到预算和采购人数。",
      "priority": "high",
      "requires_confirmation": true,
      "missing_fields": ["商机名称"],
      "related_object_type": null,
      "related_object_id": null,
      "risk_notes": [],
      "confidence": 0.92
    }
  ],
  "need_user_choice": true,
  "clarification_question": null
}
```
""")

    assert result.summary == "客户项目已进入采购准备阶段。"
    assert result.suggestions[0].action == "CREATE_OPPORTUNITY"
    assert result.suggestions[0].missing_fields == ["商机名称"]


def test_suggestion_parser_rejects_invalid_ai_output():
    with pytest.raises(AgentSuggestionGeneratorError):
        AgentSuggestionGenerator().parse_raw_response('{"summary":"x","suggestions":[{"action":"CREATE_CONTRACT"}]}')


@pytest.mark.asyncio
async def test_suggestion_generator_uses_langchain_structured_output_path():
    class FakeChatModel:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeAgent:
        async def ainvoke(self, payload):
            assert "messages" in payload
            return {
                "structured_response": AgentSuggestionResult.model_validate({
                    "summary": "客户项目已立项。",
                    "suggestions": [{
                        "action": "CREATE_OPPORTUNITY",
                        "title": "创建商机",
                        "reason": "客户已有预算和采购人数。",
                        "priority": "high",
                        "requires_confirmation": True,
                        "missing_fields": ["商机名称"],
                        "risk_notes": [],
                        "confidence": 0.91,
                    }],
                    "need_user_choice": True,
                    "clarification_question": None,
                }),
            }

    calls = {}

    def fake_agent_factory(**kwargs):
        calls["response_format"] = kwargs["response_format"]
        calls["system_prompt"] = kwargs["system_prompt"]
        return FakeAgent()

    result = await AgentSuggestionGenerator(
        agent_factory=fake_agent_factory,
        chat_model_factory=FakeChatModel,
    )._generate_with_langchain(
        api_host="https://ai.example.com/v1",
        api_key="test-key",
        model="test-model",
        user_message="今天睿狐科技提到项目已经立项成功",
        semantic_json=semantic_result().model_dump_json(exclude_none=True),
        customer_context_json='{"customer":{"id":1,"account_name":"睿狐科技"}}',
        temperature=0.1,
    )

    assert calls["response_format"] is AgentSuggestionResult
    assert "CRM AI Agent 业务建议生成器" in calls["system_prompt"]
    assert result.suggestions[0].action == "CREATE_OPPORTUNITY"

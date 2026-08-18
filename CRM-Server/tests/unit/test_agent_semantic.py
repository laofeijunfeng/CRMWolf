"""CRM AI Agent semantic parser tests."""
import pytest

from app.services.agent.prompts import CRM_AGENT_SEMANTIC_SYSTEM_PROMPT, build_semantic_messages, render_semantic_system_prompt
from app.services.agent.semantic import AgentSemanticParser, AgentSemanticParserError
from app.services.agent.schemas import AgentSemanticParseResult


def test_semantic_prompt_contains_business_and_boundary_rules():
    messages = build_semantic_messages(
        "今天和越秀金融沟通了项目进展",
        '{"recent_messages":[]}',
    )

    assert "围绕客户活动" in messages[0]["content"]
    assert "业务动作只能由后续 tool 调用现有 CRM API 完成" in messages[0]["content"]
    assert "禁止输出 Markdown" in messages[0]["content"]
    assert "intent_confidence 低于 0.75" in CRM_AGENT_SEMANTIC_SYSTEM_PROMPT
    assert "next_follow_time_iso" in CRM_AGENT_SEMANTIC_SYSTEM_PROMPT
    assert "【用户输入】" in messages[1]["content"]


def test_semantic_parser_accepts_json_object_wrapped_in_code_fence():
    result = AgentSemanticParser().parse_raw_response("""
```json
{
  "intent": "CUSTOMER_ACTIVITY",
  "intent_confidence": 0.95,
  "customer": {"name_text": "越秀金融", "confidence": 0.95},
  "follow_up": {
    "content": "客户反馈项目还在立项评估阶段",
    "method": "未指定",
    "next_action": "下周三确认进展",
    "next_follow_time_text": "下周三",
    "next_follow_time": {
      "raw_text": "下周三",
      "kind": "RELATIVE_WEEKDAY",
      "direction": "next",
      "weekday": 3,
      "confidence": 0.95
    },
    "next_follow_time_iso": null
  },
  "contact": {},
  "invoice_title": {},
  "deployment_info": {},
  "business_signals": [],
  "requested_actions": [],
  "missing_fields": [],
  "need_clarification": false,
  "clarification_question": null,
  "evidence": ["今天和越秀金融沟通了项目进展"]
}
```
""")

    assert result.intent == "CUSTOMER_ACTIVITY"
    assert result.customer.name_text == "越秀金融"
    assert result.follow_up.next_follow_time_text == "下周三"
    assert result.follow_up.next_follow_time.weekday == 3
    assert result.follow_up.next_follow_time_iso is None


def test_semantic_parser_rejects_invalid_ai_output():
    with pytest.raises(AgentSemanticParserError):
        AgentSemanticParser().parse_raw_response('{"intent":"NOT_ALLOWED"}')


@pytest.mark.asyncio
async def test_semantic_parser_uses_langchain_structured_output_path():
    class FakeChatModel:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeAgent:
        async def ainvoke(self, payload):
            assert "messages" in payload
            return {
                "structured_response": AgentSemanticParseResult.model_validate({
                    "intent": "CUSTOMER_ACTIVITY",
                    "intent_confidence": 0.95,
                    "customer": {"name_text": "越秀金融", "confidence": 0.95},
                    "follow_up": {"content": "客户还在立项评估阶段"},
                    "contact": {},
                    "invoice_title": {},
                    "deployment_info": {},
                    "business_signals": [],
                    "requested_actions": [],
                    "missing_fields": [],
                    "need_clarification": False,
                    "clarification_question": None,
                    "evidence": ["客户还在立项评估阶段"],
                }),
            }

    calls = {}

    def fake_agent_factory(**kwargs):
        calls["response_format"] = kwargs["response_format"]
        calls["system_prompt"] = kwargs["system_prompt"]
        return FakeAgent()

    result = await AgentSemanticParser(
        agent_factory=fake_agent_factory,
        chat_model_factory=FakeChatModel,
    )._parse_with_langchain(
        api_host="https://ai.example.com/v1",
        api_key="test-key",
        model="test-model",
        user_message="今天和越秀金融沟通了项目进展",
        memory_json='{"recent_messages":[]}',
        temperature=0.1,
    )

    assert calls["response_format"] is AgentSemanticParseResult
    assert "CRM AI Agent 语义解析器" in calls["system_prompt"]
    assert result.intent == "CUSTOMER_ACTIVITY"

def test_semantic_prompt_injects_team_source_names_instead_of_hardcoded_enum():
    prompt = render_semantic_system_prompt(
        source_names=["线上注册", "未分类"],
        default_source_name="未分类",
    )
    messages = build_semantic_messages(
        "帮我建一条线索",
        '{"recent_messages":[]}',
        source_names=["线上注册", "未分类"],
        default_source_name="未分类",
    )

    assert "获客来源只能输出当前团队启用项：线上注册、未分类" in prompt
    assert "禁止输出“线索转化”" in prompt
    assert '"source": "线上注册|未分类|null"' in prompt
    assert "用户未明确来源时默认可输出“未分类”" in prompt
    assert "线上注册|市场活动|客户推荐|电话营销|网站咨询|展会|其他" not in prompt
    assert "获客来源只能输出当前团队启用项：线上注册、未分类" in messages[0]["content"]


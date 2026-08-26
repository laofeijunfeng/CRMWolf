"""CRM AI Agent semantic parser tests."""

import pytest

from app.services.agent.prompts import (
    CRM_AGENT_SEMANTIC_SYSTEM_PROMPT,
    build_semantic_messages,
    render_semantic_system_prompt,
)
from app.services.agent.schemas import AgentSemanticParseResult
from app.services.agent.semantic import AgentSemanticParser, AgentSemanticParserError


def test_semantic_prompt_declares_stage_transition_as_semantic_only():
    assert "MOVE_OPPORTUNITY_STAGE" in CRM_AGENT_SEMANTIC_SYSTEM_PROMPT
    assert '"opportunity_stage_transition"' in CRM_AGENT_SEMANTIC_SYSTEM_PROMPT
    assert '"target_stage_name"' in CRM_AGENT_SEMANTIC_SYSTEM_PROMPT
    assert "禁止输出可信 stage_template_id" in CRM_AGENT_SEMANTIC_SYSTEM_PROMPT


def test_semantic_prompt_contains_business_and_boundary_rules():
    messages = build_semantic_messages(
        "今天和越秀金融沟通了项目进展",
        '{"recent_messages":[]}',
    )

    assert "围绕客户活动" in messages[0]["content"]
    assert "业务动作只能由后续 tool 调用现有 CRM API 完成" in messages[0]["content"]
    assert "禁止输出 Markdown" in messages[0]["content"]
    assert "intent_confidence 只表示意图识别把握" in CRM_AGENT_SEMANTIC_SYSTEM_PROMPT
    assert "next_follow_time_iso" in CRM_AGENT_SEMANTIC_SYSTEM_PROMPT
    assert "【用户输入】" in messages[1]["content"]


def test_semantic_contract_only_extracts_facts_and_does_not_decide_clarification():
    properties = AgentSemanticParseResult.model_json_schema()["properties"]

    assert "missing_fields" not in properties
    assert "need_clarification" not in properties
    assert "clarification_question" not in properties
    assert "缺失字段、实体绑定和冲突由后续确定性规划器判断" in CRM_AGENT_SEMANTIC_SYSTEM_PROMPT


def test_semantic_contract_uses_typed_action_frames_and_no_model_memory_source():
    schema = AgentSemanticParseResult.model_json_schema()

    assert schema["properties"]["invoice_title"] == {
        "$ref": "#/$defs/AgentInvoiceTitleEntity"
    }
    customer_source = schema["$defs"]["AgentCustomerEntity"]["properties"][
        "resolution_source"
    ]
    assert customer_source["enum"] == ["EXPLICIT", "NONE"]
    assert "MEMORY" not in CRM_AGENT_SEMANTIC_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_semantic_parser_uses_langchain_structured_output_path():
    class FakeChatModel:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeAgent:
        async def ainvoke(self, payload):
            assert "messages" in payload
            return {
                "structured_response": AgentSemanticParseResult.model_validate(
                    {
                        "intent": "CUSTOMER_ACTIVITY",
                        "intent_confidence": 0.95,
                        "customer": {"name_text": "越秀金融", "confidence": 0.95},
                        "follow_up": {"content": "客户还在立项评估阶段"},
                        "contact": {},
                        "invoice_title": {},
                        "deployment_info": {},
                        "business_signals": [],
                        "requested_actions": [],
                        "evidence": ["客户还在立项评估阶段"],
                    }
                ),
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


@pytest.mark.asyncio
async def test_semantic_parser_uses_single_structured_path_and_disables_qwen_thinking(monkeypatch):
    from types import SimpleNamespace

    from app.services.agent import semantic

    class FakeChatModel:
        calls = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.__class__.calls.append(kwargs)

    class FakeAgent:
        async def ainvoke(self, payload):
            return {
                "structured_response": AgentSemanticParseResult.model_validate(
                    {
                        "intent": "CUSTOMER_ACTIVITY",
                        "intent_confidence": 0.95,
                        "customer": {"name_text": "越秀金融", "confidence": 0.95},
                        "follow_up": {"content": "客户还在立项评估阶段"},
                        "contact": {},
                        "invoice_title": {},
                        "deployment_info": {},
                        "business_signals": [],
                        "requested_actions": [],
                        "evidence": ["客户还在立项评估阶段"],
                    }
                ),
            }

    monkeypatch.setattr(
        semantic.ai_config_crud,
        "get_config",
        lambda db, team_id: SimpleNamespace(
            api_host="https://ai.example.com/v1",
            model_name="qwen3.5-plus",
            temperature=0.1,
            max_tokens=1024,
        ),
    )
    monkeypatch.setattr(
        semantic.ai_config_crud,
        "get_decrypted_api_key",
        lambda db, team_id: "test-key",
    )
    monkeypatch.setattr(semantic, "format_active_source_names", lambda db, team_id: [])
    monkeypatch.setattr(semantic, "default_source_name", lambda db, team_id: None)

    envelope = await AgentSemanticParser(
        agent_factory=lambda **kwargs: FakeAgent(),
        chat_model_factory=FakeChatModel,
    ).parse_with_metadata(
        object(),
        team_id=1,
        user_message="今天和越秀金融沟通了项目进展",
    )

    assert envelope.parse_source == "langchain_structured_output"
    assert FakeChatModel.calls[0]["extra_body"] == {"enable_thinking": False}
    assert FakeChatModel.calls[0]["max_retries"] == 0


@pytest.mark.asyncio
async def test_semantic_parser_does_not_fallback_to_legacy_stream_after_structured_failure(monkeypatch):
    from types import SimpleNamespace

    from app.services.agent import semantic

    class FakeChatModel:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FailingAgent:
        async def ainvoke(self, payload):
            raise TimeoutError("structured call timed out")

    monkeypatch.setattr(
        semantic.ai_config_crud,
        "get_config",
        lambda db, team_id: SimpleNamespace(
            api_host="https://ai.example.com/v1",
            model_name="qwen3.5-plus",
            temperature=0.1,
            max_tokens=1024,
        ),
    )
    monkeypatch.setattr(
        semantic.ai_config_crud,
        "get_decrypted_api_key",
        lambda db, team_id: "test-key",
    )
    monkeypatch.setattr(semantic, "format_active_source_names", lambda db, team_id: [])
    monkeypatch.setattr(semantic, "default_source_name", lambda db, team_id: None)

    parser = AgentSemanticParser(
        agent_factory=lambda **kwargs: FailingAgent(),
        chat_model_factory=FakeChatModel,
    )

    with pytest.raises(AgentSemanticParserError, match="LangChain structured output 调用失败"):
        await parser.parse_with_metadata(
            object(),
            team_id=1,
            user_message="今天和越秀金融沟通了项目进展",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "kwargs"),
    [
        ("assess_pending_interruption", {"pending_task": {"id": 1}}),
        (
            "rank_resource_candidates",
            {
                "resource_kind": "contract",
                "action_name": "CREATE_PAYMENT_PLAN",
                "target": {"customer_id": 1},
                "candidates": [{"id": 11, "name": "合同 A"}],
            },
        ),
        (
            "assess_turn_relation",
            {"active_task": {"id": 1}, "suspended_tasks": []},
        ),
        (
            "assess_turn_intent",
            {
                "current_interrupt": {"type": "write_confirmation"},
                "active_task": {"id": 1},
                "suspended_tasks": [],
            },
        ),
    ],
)
async def test_semantic_decision_entrypoints_never_use_legacy_stream(
    monkeypatch,
    method_name,
    kwargs,
):
    from types import SimpleNamespace

    from app.services.agent import semantic

    class FakeChatModel:
        calls = []

        def __init__(self, **call_kwargs):
            self.__class__.calls.append(call_kwargs)

    class FailingAgent:
        async def ainvoke(self, payload):
            raise TimeoutError("structured call timed out")

    monkeypatch.setattr(
        semantic.ai_config_crud,
        "get_config",
        lambda db, team_id: SimpleNamespace(
            api_host="https://ai.example.com/v1",
            model_name="qwen3.5-plus",
            temperature=0.1,
            max_tokens=1024,
        ),
    )
    monkeypatch.setattr(
        semantic.ai_config_crud,
        "get_decrypted_api_key",
        lambda db, team_id: "test-key",
    )

    parser = AgentSemanticParser(
        agent_factory=lambda **agent_kwargs: FailingAgent(),
        chat_model_factory=FakeChatModel,
    )

    with pytest.raises(AgentSemanticParserError, match="LangChain .* 调用失败"):
        await getattr(parser, method_name)(
            object(),
            team_id=1,
            user_message="确认",
            **kwargs,
        )

    assert FakeChatModel.calls[0]["extra_body"] == {"enable_thinking": False}
    assert FakeChatModel.calls[0]["max_retries"] == 0

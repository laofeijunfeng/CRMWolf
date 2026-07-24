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
    assert "客户 -> 商机 -> 合同 -> 回款计划 -> 登记回款 -> 发票 -> License 申请" in CRM_AGENT_SUGGESTION_SYSTEM_PROMPT
    assert "创建回款计划必须依赖一条明确的合同" in CRM_AGENT_SUGGESTION_SYSTEM_PROMPT
    assert "试用 License 必须依赖一条审批通过的商机" in CRM_AGENT_SUGGESTION_SYSTEM_PROMPT
    assert "正式 License 必须依赖一条审批通过且可用的合同" in CRM_AGENT_SUGGESTION_SYSTEM_PROMPT
    assert "禁止硬编码阶段名" in CRM_AGENT_SUGGESTION_SYSTEM_PROMPT
    assert "MOVE_OPPORTUNITY_STAGE" in CRM_AGENT_SUGGESTION_SYSTEM_PROMPT
    assert "系统当前没有跟进提醒 tool" in CRM_AGENT_SUGGESTION_SYSTEM_PROMPT
    assert "FOLLOW_UP_REMINDER" not in CRM_AGENT_SUGGESTION_SYSTEM_PROMPT
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
      "missing_fields": ["预计成交日期"],
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
    assert result.suggestions[0].missing_fields == ["预计成交日期"]


def test_suggestion_parser_rejects_invalid_ai_output():
    with pytest.raises(AgentSuggestionGeneratorError):
        AgentSuggestionGenerator().parse_raw_response('{"summary":"x","suggestions":[{"action":"CREATE_CONTRACT"}]}')


def test_suggestion_parser_rejects_follow_up_reminder_action():
    with pytest.raises(AgentSuggestionGeneratorError):
        AgentSuggestionGenerator().parse_raw_response("""
{
  "summary": "客户有下次跟进时间。",
  "suggestions": [{
    "action": "FOLLOW_UP_REMINDER",
    "title": "设置下周三跟进提醒",
    "reason": "用户提到下周三再问问。",
    "priority": "medium",
    "requires_confirmation": true,
    "missing_fields": [],
    "risk_notes": [],
    "confidence": 0.9
  }],
  "need_user_choice": true,
  "clarification_question": null
}
""")


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
                        "missing_fields": ["预计成交日期"],
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


def test_suggestion_guardrail_blocks_payment_plan_without_contract():
    ai_result = AgentSuggestionResult.model_validate({
        "summary": "客户已回款但没有回款计划。",
        "suggestions": [{
            "action": "CREATE_PAYMENT_PLAN",
            "title": "补建回款计划",
            "reason": "用户输入体现已回款。",
            "priority": "high",
            "requires_confirmation": True,
            "missing_fields": [],
            "related_object_type": None,
            "related_object_id": None,
            "risk_notes": [],
            "confidence": 0.91,
        }],
        "need_user_choice": True,
        "clarification_question": None,
    })
    payment_semantic = AgentSemanticParseResult.model_validate({
        "intent": "PAYMENT_RECORD",
        "intent_confidence": 0.96,
        "customer": {"name_text": "睿狐科技", "confidence": 0.95},
        "payment": {
            "actual_amount": 50000,
            "payment_date_text": "今天",
            "payment_date_iso": "2026-07-24",
        },
        "contact": {},
        "invoice_title": {},
        "deployment_info": {},
        "business_signals": [{"type": "payment_received", "summary": "客户已回款", "confidence": 0.95}],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": ["今天回了 5 万"],
    })

    guarded = AgentSuggestionGenerator.apply_business_guardrails(
        ai_result,
        payment_semantic,
        {
            "customer": {"id": 101, "account_name": "广州睿狐科技有限公司"},
            "opportunities": {"items": []},
            "contracts": {"items": []},
            "payment_plans": {"items": []},
        },
    )

    assert [suggestion.action for suggestion in guarded.suggestions] == ["CREATE_OPPORTUNITY"]
    assert guarded.suggestions[0].title == "先补充商机"
    assert guarded.need_user_choice is True


def test_suggestion_guardrail_keeps_payment_plan_with_single_contract():
    ai_result = AgentSuggestionResult.model_validate({
        "summary": "客户已回款，有合同但没有回款计划。",
        "suggestions": [{
            "action": "CREATE_PAYMENT_PLAN",
            "title": "创建回款计划",
            "reason": "客户已有合同。",
            "priority": "high",
            "requires_confirmation": True,
            "missing_fields": [],
            "related_object_type": None,
            "related_object_id": None,
            "risk_notes": [],
            "confidence": 0.88,
        }],
        "need_user_choice": True,
        "clarification_question": None,
    })

    guarded = AgentSuggestionGenerator.apply_business_guardrails(
        ai_result,
        semantic_result(),
        {
            "contracts": [{"id": 201, "contract_name": "CRM 合同"}],
            "payment_plans": [],
        },
    )

    assert guarded.suggestions[0].action == "CREATE_PAYMENT_PLAN"
    assert guarded.suggestions[0].related_object_type == "contract"
    assert guarded.suggestions[0].related_object_id == 201


def test_suggestion_guardrail_keeps_valid_opportunity_stage_move():
    ai_result = AgentSuggestionResult.model_validate({
        "summary": "客户已进入招标准备。",
        "suggestions": [{
            "action": "MOVE_OPPORTUNITY_STAGE",
            "title": "推进商机阶段到招标准备",
            "reason": "用户输入提到需要准备招标技术和商务材料。",
            "priority": "high",
            "requires_confirmation": True,
            "missing_fields": [],
            "related_object_type": "opportunity",
            "related_object_id": 301,
            "execution_payload": {"stage_template_id": 12},
            "risk_notes": [],
            "confidence": 0.88,
        }],
        "need_user_choice": True,
        "clarification_question": None,
    })

    guarded = AgentSuggestionGenerator.apply_business_guardrails(
        ai_result,
        semantic_result(),
        {
            "active_opportunity_stage_context": [{
                "opportunity": {"id": 301, "status": 0, "approval_phase": "approved"},
                "procurement_stages": [
                    {"id": 11, "stage_name": "立项", "sort_order": 1, "is_current": True},
                    {"id": 12, "stage_name": "招标准备", "sort_order": 2, "is_current": False},
                ],
            }],
        },
    )

    assert guarded.suggestions[0].action == "MOVE_OPPORTUNITY_STAGE"
    assert guarded.suggestions[0].related_object_id == 301
    assert guarded.suggestions[0].execution_payload["target_stage_name"] == "招标准备"


def test_suggestion_guardrail_blocks_stage_move_for_unapproved_opportunity():
    ai_result = AgentSuggestionResult.model_validate({
        "summary": "客户似乎进入下一阶段。",
        "suggestions": [{
            "action": "MOVE_OPPORTUNITY_STAGE",
            "title": "推进商机阶段",
            "reason": "用户提到采购推进。",
            "priority": "high",
            "requires_confirmation": True,
            "missing_fields": [],
            "related_object_type": "opportunity",
            "related_object_id": 301,
            "execution_payload": {"stage_template_id": 12},
            "risk_notes": [],
            "confidence": 0.88,
        }],
        "need_user_choice": True,
        "clarification_question": None,
    })

    guarded = AgentSuggestionGenerator.apply_business_guardrails(
        ai_result,
        semantic_result(),
        {
            "active_opportunity_stage_context": [{
                "opportunity": {"id": 301, "status": 0, "approval_phase": "pending_review"},
                "procurement_stages": [
                    {"id": 11, "stage_name": "立项", "sort_order": 1, "is_current": True},
                    {"id": 12, "stage_name": "招标准备", "sort_order": 2, "is_current": False},
                ],
            }],
        },
    )

    assert guarded.suggestions == []
    assert guarded.need_user_choice is False


def test_suggestion_guardrail_keeps_trial_license_with_approved_opportunity_and_deployment():
    ai_result = AgentSuggestionResult.model_validate({
        "summary": "客户需要试用 License。",
        "suggestions": [{
            "action": "CREATE_LICENSE_APPLICATION",
            "title": "申请试用 License",
            "reason": "用户输入体现需要试用 License，客户已有审批通过商机和部署信息。",
            "priority": "high",
            "requires_confirmation": True,
            "missing_fields": [],
            "related_object_type": "opportunity",
            "related_object_id": None,
            "risk_notes": [],
            "confidence": 0.9,
        }],
        "need_user_choice": True,
        "clarification_question": None,
    })

    guarded = AgentSuggestionGenerator.apply_business_guardrails(
        ai_result,
        semantic_result(),
        {
            "opportunities": {"items": [{"id": 301, "approval_phase": "approved"}]},
            "contracts": {"items": []},
            "deployment_infos": {"items": [{"id": 401, "deployment_name": "生产环境"}]},
        },
    )

    assert guarded.suggestions[0].action == "CREATE_LICENSE_APPLICATION"
    assert guarded.suggestions[0].related_object_type == "opportunity"
    assert guarded.suggestions[0].related_object_id == 301


def test_suggestion_guardrail_blocks_official_license_without_approved_contract():
    ai_result = AgentSuggestionResult.model_validate({
        "summary": "客户需要正式 License。",
        "suggestions": [{
            "action": "CREATE_LICENSE_APPLICATION",
            "title": "申请正式 License",
            "reason": "用户输入体现需要正式 License。",
            "priority": "high",
            "requires_confirmation": True,
            "missing_fields": [],
            "related_object_type": "contract",
            "related_object_id": None,
            "risk_notes": [],
            "confidence": 0.9,
        }],
        "need_user_choice": True,
        "clarification_question": None,
    })

    guarded = AgentSuggestionGenerator.apply_business_guardrails(
        ai_result,
        semantic_result(),
        {
            "opportunities": {"items": [{"id": 301, "approval_phase": "approved"}]},
            "contracts": {"items": [{"id": 201, "status": "PENDING_REVIEW"}]},
            "deployment_infos": {"items": [{"id": 401, "deployment_name": "生产环境"}]},
        },
    )

    assert guarded.suggestions == []
    assert guarded.need_user_choice is False

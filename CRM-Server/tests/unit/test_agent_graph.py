"""CRM AI Agent LangGraph tests."""
from datetime import datetime

import pytest

from app.services.agent.graph import CRMAgentGraphService
from app.services.agent.schemas import (
    AgentFollowUpQualityResult,
    AgentMemorySnapshot,
    AgentSemanticParseResult,
    AgentSuggestionResult,
)
from app.services.agent.semantic import AgentSemanticParseEnvelope
from app.services.agent.tools.base import AgentToolResult


class FakeSemanticParser:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def parse(self, db, *, team_id, user_message, memory=None, current_date=None):
        self.calls.append({
            "db": db,
            "team_id": team_id,
            "user_message": user_message,
            "memory": memory,
            "current_date": current_date,
        })
        return self.result


class FakeMemoryService:
    def __init__(self, session_context=None):
        self.session_context = session_context or {}

    def load_snapshot(self, db, *, team_id, user_id, session_id, session_context=None, message_limit=12):
        return AgentMemorySnapshot(
            recent_messages=[{"role": "USER", "content": "上一轮消息"}],
            session_context=session_context or self.session_context,
        )


class FakeToolService:
    def __init__(self, items=None, customer_context=None):
        self.searches = []
        self.context_queries = []
        self.items = items or [{"id": 101, "account_name": "越秀金融"}]
        self.customer_context = customer_context

    async def search_customers(self, context, keyword, limit=10):
        self.searches.append({"context": context, "keyword": keyword, "limit": limit})
        return AgentToolResult(
            tool_name="search_customers",
            success=True,
            data={"items": self.items, "total": len(self.items)},
            tool_call_id=501,
        )

    async def get_customer_context(self, context, customer_id):
        self.context_queries.append({"context": context, "customer_id": customer_id})
        if self.customer_context is not None:
            return AgentToolResult(
                tool_name="get_customer_context",
                success=True,
                data=self.customer_context,
                tool_call_id=502,
            )
        return AgentToolResult(
            tool_name="get_customer_context",
            success=True,
            data={
                "customer": {"id": customer_id, "account_name": "越秀金融"},
                "contracts": {"items": []},
                "payment_plans": {"items": []},
                "follow_ups": {"items": []},
            },
            tool_call_id=502,
        )


class FakeSuggestionGenerator:
    def __init__(self):
        self.calls = []

    async def generate_with_metadata(self, db, *, team_id, user_message, semantic_result, customer_context, current_date=None):
        self.calls.append({
            "db": db,
            "team_id": team_id,
            "user_message": user_message,
            "semantic_result": semantic_result,
            "customer_context": customer_context,
            "current_date": current_date,
        })

        class Envelope:
            result = AgentSuggestionResult.model_validate({
                "summary": "客户项目已有推进信号，建议继续推进商机。",
                "suggestions": [{
                    "action": "CREATE_OPPORTUNITY",
                    "title": "创建商机",
                    "reason": "用户输入提到预算和采购计划。",
                    "priority": "high",
                    "requires_confirmation": True,
                    "missing_fields": ["预计成交日期"],
                    "risk_notes": [],
                    "confidence": 0.92,
                }],
                "need_user_choice": True,
                "clarification_question": None,
            })
            suggestion_source = "test_suggestion_generator"
            model = "test-model"

        return Envelope()


class FakeFollowUpQualityEvaluator:
    def __init__(self, score=80, passed=True):
        self.calls = []
        self.score = score
        self.passed = passed

    async def evaluate_with_metadata(self, db, *, team_id, user_message, semantic_result, memory=None, current_date=None):
        self.calls.append({
            "db": db,
            "team_id": team_id,
            "user_message": user_message,
            "semantic_result": semantic_result,
            "memory": memory,
            "current_date": current_date,
        })
        score = self.score
        passed = self.passed

        class Envelope:
            result = AgentFollowUpQualityResult.model_validate({
                "score": score,
                "passed": passed,
                "reason": "质量达标" if passed else "缺少明确下一步动作",
                "missing_aspects": [] if passed else ["下一步动作"],
                "supplement_question": None if passed else "请补充下一步由谁在什么时间做什么。",
                "principle_scores": {},
            })
            quality_source = "test_quality_evaluator"
            model = "test-model"
            fallback_reason = None
            fallback_error = None

        return Envelope()


class FakeStageMoveSuggestionGenerator:
    async def generate_with_metadata(self, db, *, team_id, user_message, semantic_result, customer_context, current_date=None):
        class Envelope:
            result = AgentSuggestionResult.model_validate({
                "summary": "客户反馈已经进入下一采购阶段。",
                "suggestions": [{
                    "action": "MOVE_OPPORTUNITY_STAGE",
                    "title": "推进商机阶段到招标准备",
                    "reason": "跟进内容提到客户需要招标技术和商务参考材料。",
                    "priority": "high",
                    "requires_confirmation": True,
                    "related_object_type": "opportunity",
                    "related_object_id": 301,
                    "execution_payload": {
                        "stage_template_id": 902,
                        "target_stage_name": "招标准备",
                    },
                    "risk_notes": [],
                    "confidence": 0.91,
                }],
                "need_user_choice": True,
                "clarification_question": None,
            })
            suggestion_source = "test_stage_move_suggestion_generator"
            model = "test-model"

        return Envelope()


class FakeTemporalResolver:
    def now(self):
        return datetime(2026, 7, 24, 15, 0, 0)

    def resolve_follow_up_time(self, expression, *, base_datetime=None):
        if expression is None:
            return None
        assert expression.raw_text == "下周三"
        assert expression.kind == "RELATIVE_WEEKDAY"
        assert expression.direction == "next"
        assert expression.weekday == 3
        return "2026-07-29T09:00:00"

    def resolve_date(self, expression, *, base_datetime=None):
        if expression is None:
            return None
        if expression.raw_text == "今天":
            return "2026-07-24"
        return None


def semantic_result(**overrides):
    payload = {
        "intent": "CUSTOMER_FOLLOW_UP",
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
                "confidence": 0.95,
            },
            "next_follow_time_iso": None,
        },
        "contact": {},
        "invoice_title": {},
        "deployment_info": {},
        "business_signals": [],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": ["今天和越秀金融沟通了项目进展"],
    }
    payload.update(overrides)
    return AgentSemanticParseResult.model_validate(payload)


def payment_semantic_result(**overrides):
    payload = {
        "intent": "PAYMENT_RECORD",
        "intent_confidence": 0.95,
        "customer": {"name_text": "越秀金融", "confidence": 0.95},
        "follow_up": {"content": "客户今天已回款", "method": "未指定"},
        "payment": {
            "actual_amount": 300000,
            "actual_payer_name": None,
            "payment_date_text": "今天",
            "payment_date": {
                "raw_text": "今天",
                "kind": "RELATIVE_DAY",
                "direction": "current",
                "confidence": 0.95,
            },
            "payment_date_iso": None,
            "notes": None,
        },
        "contact": {},
        "invoice_title": {},
        "deployment_info": {},
        "business_signals": [{"type": "payment_received", "summary": "客户今天已回款", "confidence": 0.95}],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": ["今天已回款"],
    }
    payload.update(overrides)
    return AgentSemanticParseResult.model_validate(payload)


def opportunity_semantic_result(**overrides):
    payload = {
        "intent": "CREATE_OPPORTUNITY",
        "intent_confidence": 0.95,
        "customer": {"name_text": None, "confidence": 0.0, "resolution_source": "MEMORY"},
        "follow_up": {"content": "用户要求创建商机", "method": "未指定"},
        "opportunity": {
            "opportunity_name": "100人订阅1年商机",
            "total_amount": 50000,
            "user_count": 100,
            "license_type": "SUBSCRIPTION",
            "subscription_years": 1,
            "purchase_type": None,
            "expected_closing_date": None,
        },
        "contact": {},
        "invoice_title": {},
        "deployment_info": {},
        "business_signals": [{"type": "opportunity_progress", "summary": "用户要求创建商机", "confidence": 0.95}],
        "requested_actions": [{"action": "CREATE_OPPORTUNITY", "requires_confirmation": True}],
        "missing_fields": ["purchase_type", "expected_closing_date"],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": ["帮我创建一个商机，5 万 100 人使用，订阅 1 年"],
    }
    payload.update(overrides)
    return AgentSemanticParseResult.model_validate(payload)


def build_service(result, tool_service=None):
    return CRMAgentGraphService(
        tool_service=tool_service or FakeToolService(),
        semantic_parser=FakeSemanticParser(result),
        memory_service=FakeMemoryService(),
        temporal_resolver=FakeTemporalResolver(),
        suggestion_generator=FakeSuggestionGenerator(),
        follow_up_quality_evaluator=FakeFollowUpQualityEvaluator(),
    )


def build_service_with_memory(result, tool_service=None, session_context=None):
    return CRMAgentGraphService(
        tool_service=tool_service or FakeToolService(),
        semantic_parser=FakeSemanticParser(result),
        memory_service=FakeMemoryService(session_context=session_context),
        temporal_resolver=FakeTemporalResolver(),
        suggestion_generator=FakeSuggestionGenerator(),
        follow_up_quality_evaluator=FakeFollowUpQualityEvaluator(),
    )


def input_state(content="这句话没有任何用于规则识别的关键词"):
    return {
        "db": object(),
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "authorization": "Bearer test-token",
        "content": content,
    }


class FakeSemanticParserWithMetadata:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def parse_with_metadata(self, db, *, team_id, user_message, memory=None, current_date=None):
        self.calls.append({
            "db": db,
            "team_id": team_id,
            "user_message": user_message,
            "memory": memory,
            "current_date": current_date,
        })
        return AgentSemanticParseEnvelope(
            result=self.result,
            parse_source="system_ai_json_object",
            model="test-model",
            fallback_reason="langchain_structured_output_failed",
            fallback_error="RuntimeError",
        )


@pytest.mark.asyncio
async def test_agent_graph_uses_ai_semantic_result_for_intent_and_entities():
    parser = FakeSemanticParser(semantic_result(
        intent="PAYMENT_RECORD",
        customer={"name_text": "光大证券", "confidence": 0.96},
        follow_up={"content": "客户已回款", "method": "未指定"},
        business_signals=[{"type": "payment_received", "summary": "客户已回款", "confidence": 0.95}],
    ))
    tool_service = FakeToolService()
    service = CRMAgentGraphService(
        tool_service=tool_service,
        semantic_parser=parser,
        memory_service=FakeMemoryService(),
        suggestion_generator=FakeSuggestionGenerator(),
        follow_up_quality_evaluator=FakeFollowUpQualityEvaluator(),
    )

    result = await service.run(input_state("没有关键词也应该只相信 AI parser 的结构化结果"))

    assert result["intent"] == "PAYMENT_RECORD"
    assert result["parsed"]["customer_name"] == "光大证券"
    semantic_events = [event for event in result["events"] if event["event"] == "semantic_parsed"]
    assert semantic_events[0]["parse_source"] == "test_parser"
    assert tool_service.searches[0]["keyword"] == "光大证券"
    assert parser.calls[0]["memory"].recent_messages[0]["content"] == "上一轮消息"


@pytest.mark.asyncio
async def test_agent_graph_exposes_structured_output_fallback_metadata():
    parser = FakeSemanticParserWithMetadata(semantic_result())
    service = CRMAgentGraphService(
        tool_service=FakeToolService(),
        semantic_parser=parser,
        memory_service=FakeMemoryService(),
        temporal_resolver=FakeTemporalResolver(),
        suggestion_generator=FakeSuggestionGenerator(),
        follow_up_quality_evaluator=FakeFollowUpQualityEvaluator(),
    )

    result = await service.run({
        **input_state("今天和越秀金融沟通了项目进展"),
        "current_datetime": datetime(2026, 7, 24, 15, 0, 0),
    })

    semantic_events = [event for event in result["events"] if event["event"] == "semantic_parsed"]
    assert semantic_events[0]["parse_source"] == "system_ai_json_object"
    assert semantic_events[0]["fallback_reason"] == "langchain_structured_output_failed"
    assert semantic_events[0]["fallback_error"] == "RuntimeError"
    assert parser.calls[0]["current_date"].isoformat() == "2026-07-24"


@pytest.mark.asyncio
async def test_agent_graph_loads_customer_context_and_generates_ai_suggestions():
    tool_service = FakeToolService()
    suggestion_generator = FakeSuggestionGenerator()
    service = CRMAgentGraphService(
        tool_service=tool_service,
        semantic_parser=FakeSemanticParser(semantic_result(
            follow_up={
                "content": "客户已经立项，计划采购 100 人，总预算 30 万",
                "method": "未指定",
                "next_action": "下周三前提供招标参数",
                "next_follow_time_text": "下周三",
                "next_follow_time": {
                    "raw_text": "下周三",
                    "kind": "RELATIVE_WEEKDAY",
                    "direction": "next",
                    "weekday": 3,
                    "confidence": 0.95,
                },
                "next_follow_time_iso": None,
            },
        )),
        memory_service=FakeMemoryService(),
        temporal_resolver=FakeTemporalResolver(),
        suggestion_generator=suggestion_generator,
        follow_up_quality_evaluator=FakeFollowUpQualityEvaluator(),
    )

    result = await service.run(input_state())

    assert tool_service.context_queries[0]["customer_id"] == 101
    assert suggestion_generator.calls[0]["customer_context"]["customer"]["id"] == 101
    suggestion_events = [event for event in result["events"] if event["event"] == "business_suggestions"]
    assert suggestion_events[0]["suggestion_source"] == "test_suggestion_generator"
    assert suggestion_events[0]["suggestions"][0]["action"] == "CREATE_OPPORTUNITY"
    assert "请确认是否创建这条跟进记录？" in result["response"]
    assert "基于客户上下文，我建议下一步可以" not in result["response"]


@pytest.mark.asyncio
async def test_agent_graph_blocks_low_quality_follow_up_before_customer_search():
    tool_service = FakeToolService()
    suggestion_generator = FakeSuggestionGenerator()
    quality_evaluator = FakeFollowUpQualityEvaluator(score=45, passed=False)
    service = CRMAgentGraphService(
        tool_service=tool_service,
        semantic_parser=FakeSemanticParser(semantic_result(
            follow_up={
                "content": "客户说再看看",
                "method": "微信",
                "next_action": None,
                "next_follow_time_text": None,
                "next_follow_time": None,
            },
        )),
        memory_service=FakeMemoryService(),
        temporal_resolver=FakeTemporalResolver(),
        suggestion_generator=suggestion_generator,
        follow_up_quality_evaluator=quality_evaluator,
    )

    result = await service.run(input_state("今天和越秀金融聊了下，客户说再看看"))

    assert result["response"] == "请补充下一步由谁在什么时间做什么。"
    assert tool_service.searches == []
    assert suggestion_generator.calls == []
    quality_events = [event for event in result["events"] if event["event"] == "follow_up_quality_evaluated"]
    assert quality_events[0]["score"] == 45
    assert quality_events[0]["passed"] is False
    assert [event["event"] for event in result["events"] if event["event"] == "confirmation_required"] == []


@pytest.mark.asyncio
async def test_agent_graph_streams_step_events_before_final_response():
    service = build_service(semantic_result())
    events = []

    async for event in service.stream_events(input_state("今天和越秀金融沟通了项目进展")):
        events.append(event)

    event_names = [event["event"] for event in events]
    assert event_names[0] == "agent_step"
    assert events[0]["step"] == "load_memory"
    assert events[0]["status"] == "started"
    assert event_names.index("semantic_parsed") < event_names.index("final")
    assert event_names.index("tool_result") < event_names.index("final")
    assert event_names.index("business_suggestions") < event_names.index("final")


@pytest.mark.asyncio
async def test_agent_graph_requires_clarification_when_ai_confidence_is_low():
    result = await build_service(semantic_result(
        intent="CUSTOMER_FOLLOW_UP",
        intent_confidence=0.62,
        customer={"name_text": "越秀", "confidence": 0.5},
        need_clarification=True,
        clarification_question="请确认客户全称是哪一个？",
    )).run(input_state())

    assert result["response"] == "请确认客户全称是哪一个？"
    assert not result.get("customer_candidates")
    assert any(event["event"] == "clarification_required" for event in result["events"])


@pytest.mark.asyncio
async def test_agent_graph_searches_customer_and_requires_follow_up_confirmation():
    tool_service = FakeToolService()
    result = await build_service(semantic_result(), tool_service).run(input_state())

    assert tool_service.searches[0]["keyword"] == "越秀金融"
    assert result["customer_candidates"] == [{"id": 101, "account_name": "越秀金融", "owner_info": None, "collaborator_infos": []}]
    confirmation_events = [event for event in result["events"] if event["event"] == "confirmation_required"]
    assert confirmation_events[0]["action"] == "create_customer_follow_up"
    assert confirmation_events[0]["payload"]["customer_id"] == 101
    assert confirmation_events[0]["payload"]["content"] == "客户反馈项目还在立项评估阶段"


@pytest.mark.asyncio
async def test_agent_graph_attaches_opportunity_stage_move_as_next_task_after_follow_up():
    tool_service = FakeToolService(
        items=[{"id": 101, "account_name": "睿狐科技", "owner_info": {"id": 2}}],
        customer_context={
            "customer": {"id": 101, "account_name": "睿狐科技"},
            "opportunities": {"items": [{"id": 301, "opportunity_name": "睿狐科技采购项目"}]},
            "active_opportunity_stage_context": [{
                "opportunity": {"id": 301, "opportunity_name": "睿狐科技采购项目"},
                "procurement_stages": [
                    {"id": 901, "stage_name": "立项评估", "is_current": True},
                    {"id": 902, "stage_name": "招标准备", "is_current": False},
                ],
            }],
            "contracts": {"items": []},
            "payment_plans": {"items": []},
        },
    )
    service = CRMAgentGraphService(
        tool_service=tool_service,
        semantic_parser=FakeSemanticParser(semantic_result(
            customer={"name_text": "睿狐科技", "confidence": 0.95},
            follow_up={
                "content": "客户需要我们提供招标技术和商务参考材料",
                "method": "未指定",
                "next_action": "提供招标参数版本",
                "next_follow_time_text": None,
                "next_follow_time": None,
            },
        )),
        memory_service=FakeMemoryService(),
        temporal_resolver=FakeTemporalResolver(),
        suggestion_generator=FakeStageMoveSuggestionGenerator(),
        follow_up_quality_evaluator=FakeFollowUpQualityEvaluator(),
    )

    result = await service.run(input_state("睿狐科技需要我们提供招标技术和商务参考材料"))

    confirmation_events = [event for event in result["events"] if event["event"] == "confirmation_required"]
    assert confirmation_events[0]["action"] == "create_customer_follow_up"
    next_task = confirmation_events[0]["payload"]["_next_task"]
    assert next_task["action"] == "move_opportunity_stage"
    assert next_task["payload"]["opportunity_id"] == 301
    assert next_task["payload"]["stage_template_id"] == 902
    assert next_task["payload"]["target_stage_name"] == "招标准备"


@pytest.mark.asyncio
async def test_agent_graph_attaches_opportunity_collection_as_next_task_after_follow_up():
    tool_service = FakeToolService(
        items=[{"id": 101, "account_name": "汇川技术", "owner_info": {"id": 2}}],
        customer_context={
            "customer": {"id": 101, "account_name": "汇川技术"},
            "opportunities": {"items": []},
            "contracts": {"items": []},
            "payment_plans": {"items": []},
        },
    )
    service = CRMAgentGraphService(
        tool_service=tool_service,
        semantic_parser=FakeSemanticParser(semantic_result(
            customer={"name_text": "汇川技术", "confidence": 0.95},
            follow_up={
                "content": "客户反馈续费事项本月底会对接到采购侧",
                "method": "微信",
                "next_action": "下周三确认采购联系时间",
                "next_follow_time_text": "下周三",
                "next_follow_time": {
                    "raw_text": "下周三",
                    "kind": "RELATIVE_WEEKDAY",
                    "direction": "next",
                    "weekday": 3,
                    "confidence": 0.95,
                },
            },
            opportunity={"purchase_type": "RENEWAL"},
        )),
        memory_service=FakeMemoryService(),
        temporal_resolver=FakeTemporalResolver(),
        suggestion_generator=FakeSuggestionGenerator(),
        follow_up_quality_evaluator=FakeFollowUpQualityEvaluator(),
    )

    result = await service.run(input_state("今天微信找了汇川技术沟通续费"))

    assert "基于客户上下文，我建议下一步可以" not in result["response"]
    confirmation_events = [event for event in result["events"] if event["event"] == "confirmation_required"]
    next_task = confirmation_events[0]["payload"]["_next_task"]
    assert next_task["action"] == "collect_opportunity_fields"
    assert next_task["payload"]["opportunity"]["purchase_type"] == "RENEWAL"
    assert "total_amount" in next_task["payload"]["missing_fields"]
    assert "继续帮你补齐商机信息" in next_task["content"]


@pytest.mark.asyncio
async def test_agent_graph_inherits_current_customer_from_structured_memory():
    memory_customer = {
        "id": 101,
        "account_name": "广州睿狐科技有限公司",
        "owner_info": {"id": 2},
        "collaborator_infos": [],
    }
    tool_service = FakeToolService(
        items=[{"id": 999, "account_name": "深圳市云视创科技有限公司"}],
        customer_context={
            "customer": {"id": 101, "account_name": "广州睿狐科技有限公司"},
            "opportunities": {"items": []},
            "contracts": {"items": []},
            "payment_plans": {"items": []},
        },
    )
    result = await build_service_with_memory(
        opportunity_semantic_result(),
        tool_service,
        session_context={"current_customer": memory_customer},
    ).run(input_state("那帮我创建一个商机，5 万 100 人使用，订阅 1 年"))

    assert tool_service.searches == []
    assert tool_service.context_queries[0]["customer_id"] == 101
    assert result["selected_customer"]["account_name"] == "广州睿狐科技有限公司"
    assert result["parsed"]["customer_name"] == "广州睿狐科技有限公司"
    field_events = [event for event in result["events"] if event["event"] == "opportunity_fields_required"]
    assert field_events[0]["action"] == "collect_opportunity_fields"
    assert field_events[0]["payload"]["customer_id"] == 101
    assert field_events[0]["payload"]["opportunity"]["total_amount"] == 50000
    assert field_events[0]["payload"]["missing_fields"] == ["purchase_type", "expected_closing_date"]


@pytest.mark.asyncio
async def test_agent_graph_explicit_customer_overrides_current_customer_memory():
    memory_customer = {
        "id": 101,
        "account_name": "广州睿狐科技有限公司",
        "owner_info": {"id": 2},
        "collaborator_infos": [],
    }
    tool_service = FakeToolService(
        items=[{"id": 202, "account_name": "汇川技术"}],
        customer_context={
            "customer": {"id": 202, "account_name": "汇川技术"},
            "opportunities": {"items": []},
            "contracts": {"items": []},
            "payment_plans": {"items": []},
        },
    )
    service = build_service_with_memory(
        semantic_result(
            customer={"name_text": "汇川技术", "confidence": 0.95, "resolution_source": "EXPLICIT"},
            follow_up={
                "content": "客户反馈已经找了研发侧，本月底会对接到采购侧",
                "method": "微信",
                "next_action": "下周三确认采购联系时间",
                "next_follow_time_text": "下周三",
                "next_follow_time": {
                    "raw_text": "下周三",
                    "kind": "RELATIVE_WEEKDAY",
                    "direction": "next",
                    "weekday": 3,
                    "confidence": 0.95,
                },
            },
        ),
        tool_service,
        session_context={"current_customer": memory_customer},
    )

    result = await service.run(input_state("今天微信找了汇川技术沟通续费方面的事宜"))

    assert tool_service.searches[0]["keyword"] == "汇川技术"
    assert result["selected_customer"]["account_name"] == "汇川技术"
    assert result["parsed"]["customer_name"] == "汇川技术"


@pytest.mark.asyncio
async def test_agent_graph_payment_record_uses_customer_context_plan():
    tool_service = FakeToolService(
        items=[{
            "id": 101,
            "account_name": "越秀金融",
            "owner_info": {"id": 2, "name": "销售A"},
            "collaborator_infos": [{"id": 9, "name": "协作A"}],
        }],
        customer_context={
            "customer": {"id": 101, "account_name": "越秀金融"},
            "contracts": [{"id": 201, "contract_name": "越秀金融 CRM 合同", "total_amount": 300000, "status": "SIGNED"}],
            "payment_plans": [{
                "id": 301,
                "contract_id": 201,
                "contract_name": "越秀金融 CRM 合同",
                "stage_name": "首款",
                "remaining_amount": 300000,
                "status": "PENDING",
            }],
        },
    )
    result = await build_service(payment_semantic_result(), tool_service).run(input_state("越秀金融今天回款 30 万"))

    confirmation_events = [event for event in result["events"] if event["event"] == "confirmation_required"]
    assert confirmation_events[0]["action"] == "create_payment_record"
    assert confirmation_events[0]["payload"]["payment_plan_id"] == 301
    assert confirmation_events[0]["payload"]["actual_amount"] == 300000
    assert confirmation_events[0]["payload"]["payment_date"] == "2026-07-24"
    assert confirmation_events[0]["payload"]["commission_member_id"] == "9"


@pytest.mark.asyncio
async def test_agent_graph_payment_record_without_plan_requires_plan_creation():
    tool_service = FakeToolService(
        items=[{"id": 101, "account_name": "越秀金融", "owner_info": {"id": 2}}],
        customer_context={
            "customer": {"id": 101, "account_name": "越秀金融"},
            "contracts": [{"id": 201, "contract_name": "越秀金融 CRM 合同", "total_amount": 300000, "status": "SIGNED"}],
            "payment_plans": [],
        },
    )
    result = await build_service(payment_semantic_result(), tool_service).run(input_state("越秀金融今天回款 30 万"))

    confirmation_events = [event for event in result["events"] if event["event"] == "confirmation_required"]
    assert confirmation_events[0]["action"] == "create_payment_plan"
    assert confirmation_events[0]["payload"]["contract_id"] == 201
    assert confirmation_events[0]["payload"]["planned_amount"] == 300000
    assert confirmation_events[0]["payload"]["pending_payment_record"]["commission_member_id"] == "2"


@pytest.mark.asyncio
async def test_agent_graph_payment_record_without_opportunity_or_contract_explains_chain_gap():
    tool_service = FakeToolService(
        items=[{"id": 101, "account_name": "睿狐科技", "owner_info": {"id": 2}}],
        customer_context={
            "customer": {"id": 101, "account_name": "睿狐科技"},
            "opportunities": {"items": []},
            "contracts": {"items": []},
            "payment_plans": {"items": []},
        },
    )
    result = await build_service(payment_semantic_result(), tool_service).run(input_state("睿狐科技今天回了 5 万"))

    confirmation_events = [event for event in result["events"] if event["event"] == "confirmation_required"]
    assert confirmation_events == []
    assert "没有找到商机和可用于登记回款的合同" in result["response"]
    assert "需要先补齐商机" in result["response"]
    assert "创建回款计划" not in result["response"]


@pytest.mark.asyncio
async def test_agent_graph_payment_record_missing_amount_requires_ai_field_collection():
    tool_service = FakeToolService(
        items=[{"id": 101, "account_name": "越秀金融", "owner_info": {"id": 2}}],
        customer_context={
            "customer": {"id": 101, "account_name": "越秀金融"},
            "contracts": [{"id": 201, "contract_name": "越秀金融 CRM 合同", "total_amount": 300000, "status": "SIGNED"}],
            "payment_plans": [{
                "id": 301,
                "contract_id": 201,
                "contract_name": "越秀金融 CRM 合同",
                "stage_name": "首款",
                "remaining_amount": 300000,
                "status": "PENDING",
            }],
        },
    )
    result = await build_service(payment_semantic_result(
        payment={
            "actual_amount": None,
            "payment_date_text": "今天",
            "payment_date": {
                "raw_text": "今天",
                "kind": "RELATIVE_DAY",
                "direction": "current",
                "confidence": 0.95,
            },
            "payment_date_iso": None,
        },
        missing_fields=["actual_amount"],
    ), tool_service).run(input_state("越秀金融今天回款了"))

    field_events = [event for event in result["events"] if event["event"] == "payment_fields_required"]
    assert field_events[0]["action"] == "collect_payment_fields"
    assert field_events[0]["payload"]["missing_fields"] == ["actual_amount"]


@pytest.mark.asyncio
async def test_agent_graph_requires_customer_selection_when_multiple_candidates():
    tool_service = FakeToolService(items=[
        {"id": 101, "account_name": "越秀金融"},
        {"id": 102, "account_name": "越秀金融科技"},
    ])
    result = await build_service(semantic_result(), tool_service).run(input_state())

    selection_events = [event for event in result["events"] if event["event"] == "customer_selection_required"]
    assert selection_events[0]["action"] == "select_customer_for_follow_up"
    assert selection_events[0]["customers"][1]["id"] == 102
    assert "请回复序号或客户名称" in result["response"]


@pytest.mark.asyncio
async def test_agent_graph_requires_contact_confirmation_when_ai_fields_complete():
    result = await build_service(semantic_result(
        intent="CREATE_CONTACT",
        customer={"name_text": "越秀金融", "confidence": 0.95},
        contact={
            "is_decision_maker": False,
            "name": "王总",
            "mobile": "13800138000",
            "position": "总经理",
            "gender": "1",
        },
    )).run(input_state())

    confirmation_events = [event for event in result["events"] if event["event"] == "confirmation_required"]
    assert confirmation_events[0]["action"] == "create_contact"
    assert confirmation_events[0]["payload"]["contact"]["mobile"] == "13800138000"


@pytest.mark.asyncio
async def test_agent_graph_requires_contact_fields_when_ai_fields_missing():
    result = await build_service(semantic_result(
        intent="CREATE_CONTACT",
        customer={"name_text": "越秀金融", "confidence": 0.95},
        contact={"name": "王总", "is_decision_maker": False},
        missing_fields=["mobile", "position", "gender"],
    )).run(input_state())

    field_events = [event for event in result["events"] if event["event"] == "contact_fields_required"]
    assert field_events[0]["payload"]["missing_fields"] == ["mobile", "position", "gender"]


@pytest.mark.asyncio
async def test_agent_graph_requires_invoice_title_confirmation_when_ai_fields_complete():
    result = await build_service(semantic_result(
        intent="CREATE_INVOICE_TITLE",
        customer={"name_text": "越秀金融", "confidence": 0.95},
        invoice_title={
            "title_type": "COMPANY",
            "title": "越秀金融控股有限公司",
            "taxpayer_id": "91440000123456789X",
            "set_default": True,
        },
    )).run(input_state())

    confirmation_events = [event for event in result["events"] if event["event"] == "confirmation_required"]
    assert confirmation_events[0]["action"] == "create_invoice_title"
    assert confirmation_events[0]["payload"] == {
        "customer_id": 101,
        "invoice_title": {
            "title_type": "COMPANY",
            "title": "越秀金融控股有限公司",
            "taxpayer_id": "91440000123456789X",
        },
        "set_default": True,
    }


@pytest.mark.asyncio
async def test_agent_graph_requires_invoice_title_fields_when_ai_fields_missing():
    result = await build_service(semantic_result(
        intent="CREATE_INVOICE_TITLE",
        customer={"name_text": "越秀金融", "confidence": 0.95},
        invoice_title={"title_type": "COMPANY"},
        missing_fields=["title", "taxpayer_id"],
    )).run(input_state())

    field_events = [event for event in result["events"] if event["event"] == "invoice_title_fields_required"]
    assert field_events[0]["payload"]["missing_fields"] == ["title", "taxpayer_id"]


@pytest.mark.asyncio
async def test_agent_graph_requires_deployment_info_confirmation_when_ai_fields_complete():
    result = await build_service(semantic_result(
        intent="CREATE_DEPLOYMENT_INFO",
        customer={"name_text": "越秀金融", "confidence": 0.95},
        deployment_info={
            "is_default": True,
            "deployment_name": "生产环境",
            "server_address": "https://crm.example.com",
            "authorized_users": 100,
        },
    )).run(input_state())

    confirmation_events = [event for event in result["events"] if event["event"] == "confirmation_required"]
    assert confirmation_events[0]["action"] == "create_deployment_info"
    assert confirmation_events[0]["payload"] == {
        "customer_id": 101,
        "deployment_info": {
            "is_default": True,
            "deployment_name": "生产环境",
            "server_address": "https://crm.example.com",
            "authorized_users": 100,
            "customer_id": 101,
        },
    }


@pytest.mark.asyncio
async def test_agent_graph_requires_deployment_info_fields_when_ai_fields_missing():
    result = await build_service(semantic_result(
        intent="CREATE_DEPLOYMENT_INFO",
        customer={"name_text": "越秀金融", "confidence": 0.95},
        deployment_info={"is_default": False},
        missing_fields=["deployment_name", "server_address", "authorized_users"],
    )).run(input_state())

    field_events = [event for event in result["events"] if event["event"] == "deployment_info_fields_required"]
    assert field_events[0]["payload"]["missing_fields"] == [
        "deployment_name",
        "server_address",
        "authorized_users",
    ]


@pytest.mark.asyncio
async def test_agent_graph_requires_customer_member_confirmation_when_candidate_matches():
    tool_service = FakeToolService(customer_context={
        "customer": {"id": 101, "account_name": "越秀金融"},
        "contracts": {"items": []},
        "payment_plans": {"items": []},
        "follow_ups": {"items": []},
        "member_candidates": [
            {"id": "9", "name": "张三", "already_member": False},
        ],
    })
    result = await build_service(semantic_result(
        intent="CREATE_CUSTOMER_MEMBER",
        customer={"name_text": "越秀金融", "confidence": 0.95},
        customer_member={
            "user_name": "张三",
            "member_role": "PRESALES",
            "access_level": "FOLLOW_UP",
        },
    ), tool_service).run(input_state())

    confirmation_events = [event for event in result["events"] if event["event"] == "confirmation_required"]
    assert confirmation_events[0]["action"] == "create_customer_member"
    assert confirmation_events[0]["payload"]["member"] == {
        "user_id": "9",
        "user_name": "张三",
        "member_role": "PRESALES",
        "access_level": "FOLLOW_UP",
    }


@pytest.mark.asyncio
async def test_agent_graph_requires_customer_member_name_when_missing():
    result = await build_service(semantic_result(
        intent="CREATE_CUSTOMER_MEMBER",
        customer={"name_text": "越秀金融", "confidence": 0.95},
        customer_member={"member_role": "PRESALES"},
        missing_fields=["user_name"],
    )).run(input_state())

    field_events = [event for event in result["events"] if event["event"] == "customer_member_fields_required"]
    assert field_events[0]["payload"]["missing_fields"] == ["user_name"]

"""CRM AI Agent LangGraph tests."""
import pytest

from app.services.agent.graph import CRMAgentGraphService
from app.services.agent.schemas import AgentMemorySnapshot, AgentSemanticParseResult, AgentSuggestionResult
from app.services.agent.tools.base import AgentToolResult


class FakeSemanticParser:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def parse(self, db, *, team_id, user_message, memory=None):
        self.calls.append({
            "db": db,
            "team_id": team_id,
            "user_message": user_message,
            "memory": memory,
        })
        return self.result


class FakeMemoryService:
    def load_snapshot(self, db, *, team_id, user_id, session_id, session_context=None, message_limit=12):
        return AgentMemorySnapshot(
            recent_messages=[{"role": "USER", "content": "上一轮消息"}],
            session_context=session_context or {},
        )


class FakeToolService:
    def __init__(self, items=None):
        self.searches = []
        self.context_queries = []
        self.items = items or [{"id": 101, "account_name": "越秀金融"}]

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

    async def generate_with_metadata(self, db, *, team_id, user_message, semantic_result, customer_context):
        self.calls.append({
            "db": db,
            "team_id": team_id,
            "user_message": user_message,
            "semantic_result": semantic_result,
            "customer_context": customer_context,
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
                    "missing_fields": ["商机名称", "预计成交日期"],
                    "risk_notes": [],
                    "confidence": 0.92,
                }],
                "need_user_choice": True,
                "clarification_question": None,
            })
            suggestion_source = "test_suggestion_generator"
            model = "test-model"

        return Envelope()


class FakeTemporalResolver:
    def resolve_follow_up_time(self, expression, *, base_datetime=None):
        assert expression.raw_text == "下周三"
        assert expression.kind == "RELATIVE_WEEKDAY"
        assert expression.direction == "next"
        assert expression.weekday == 3
        return "2026-07-29T09:00:00"


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


def build_service(result, tool_service=None):
    return CRMAgentGraphService(
        tool_service=tool_service or FakeToolService(),
        semantic_parser=FakeSemanticParser(result),
        memory_service=FakeMemoryService(),
        temporal_resolver=FakeTemporalResolver(),
        suggestion_generator=FakeSuggestionGenerator(),
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
    )

    result = await service.run(input_state("没有关键词也应该只相信 AI parser 的结构化结果"))

    assert result["intent"] == "PAYMENT_RECORD"
    assert result["parsed"]["customer_name"] == "光大证券"
    semantic_events = [event for event in result["events"] if event["event"] == "semantic_parsed"]
    assert semantic_events[0]["parse_source"] == "test_parser"
    assert tool_service.searches[0]["keyword"] == "光大证券"
    assert parser.calls[0]["memory"].recent_messages[0]["content"] == "上一轮消息"


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
    )

    result = await service.run(input_state())

    assert tool_service.context_queries[0]["customer_id"] == 101
    assert suggestion_generator.calls[0]["customer_context"]["customer"]["id"] == 101
    suggestion_events = [event for event in result["events"] if event["event"] == "business_suggestions"]
    assert suggestion_events[0]["suggestion_source"] == "test_suggestion_generator"
    assert suggestion_events[0]["suggestions"][0]["action"] == "CREATE_OPPORTUNITY"
    assert "基于客户上下文，我建议下一步可以：1. 创建商机。" in result["response"]


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

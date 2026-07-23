"""CRM AI Agent LangGraph tests."""
import pytest

from app.services.agent.graph import CRMAgentGraphService
from app.services.agent.tools.base import AgentToolResult


class FakeToolService:
    def __init__(self, items=None):
        self.searches = []
        self.items = items or [{"id": 101, "account_name": "越秀金融"}]

    async def search_customers(self, context, keyword, limit=10):
        self.searches.append({"context": context, "keyword": keyword, "limit": limit})
        return AgentToolResult(
            tool_name="search_customers",
            success=True,
            data={"items": self.items, "total": len(self.items)},
            tool_call_id=501,
        )


@pytest.mark.asyncio
async def test_agent_graph_classifies_follow_up_intent():
    service = CRMAgentGraphService()

    result = await service.run({
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "content": "今天和越秀金融沟通了项目进展，下周三继续跟进",
    })

    assert result["intent"] == "CUSTOMER_FOLLOW_UP"
    assert result["events"][0] == {"event": "intent", "intent": "CUSTOMER_FOLLOW_UP"}
    assert result["events"][-1]["event"] == "final"


@pytest.mark.asyncio
async def test_agent_graph_classifies_payment_intent():
    service = CRMAgentGraphService()

    result = await service.run({
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "content": "光大证券今天回款了",
    })

    assert result["intent"] == "PAYMENT_RECORD"


@pytest.mark.asyncio
async def test_agent_graph_classifies_contact_intent():
    service = CRMAgentGraphService()

    result = await service.run({
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "content": "帮我给越秀金融创建联系人王总",
    })

    assert result["intent"] == "CREATE_CONTACT"


@pytest.mark.asyncio
async def test_agent_graph_classifies_invoice_title_intent():
    service = CRMAgentGraphService()

    result = await service.run({
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "content": "帮我给越秀金融创建发票抬头",
    })

    assert result["intent"] == "CREATE_INVOICE_TITLE"


@pytest.mark.asyncio
async def test_agent_graph_searches_customer_and_requires_follow_up_confirmation():
    tool_service = FakeToolService()
    service = CRMAgentGraphService(tool_service=tool_service)

    result = await service.run({
        "db": object(),
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "authorization": "Bearer test-token",
        "content": "今天和越秀金融的王总沟通了项目进展，下周三继续跟进",
    })

    assert tool_service.searches[0]["keyword"] == "越秀金融"
    assert result["customer_candidates"] == [{"id": 101, "account_name": "越秀金融", "owner_info": None, "collaborator_infos": []}]
    assert any(event["event"] == "customer_candidates" for event in result["events"])
    confirmation_events = [event for event in result["events"] if event["event"] == "confirmation_required"]
    assert confirmation_events[0]["action"] == "create_customer_follow_up"
    assert confirmation_events[0]["payload"]["customer_id"] == 101


@pytest.mark.asyncio
async def test_agent_graph_requires_customer_selection_when_multiple_candidates():
    tool_service = FakeToolService(items=[
        {"id": 101, "account_name": "越秀金融"},
        {"id": 102, "account_name": "越秀金融科技"},
    ])
    service = CRMAgentGraphService(tool_service=tool_service)

    result = await service.run({
        "db": object(),
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "authorization": "Bearer test-token",
        "content": "今天和越秀金融的王总沟通了项目进展，下周三继续跟进",
    })

    selection_events = [event for event in result["events"] if event["event"] == "customer_selection_required"]
    assert selection_events[0]["action"] == "select_customer_for_follow_up"
    assert selection_events[0]["customers"][1]["id"] == 102
    assert "请回复序号或客户名称" in result["response"]


@pytest.mark.asyncio
async def test_agent_graph_requires_contact_confirmation_when_fields_complete():
    tool_service = FakeToolService()
    service = CRMAgentGraphService(tool_service=tool_service)

    result = await service.run({
        "db": object(),
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "authorization": "Bearer test-token",
        "content": "帮我给越秀金融创建联系人王总，手机号13800138000，职务总经理，男",
    })

    confirmation_events = [event for event in result["events"] if event["event"] == "confirmation_required"]
    assert confirmation_events[0]["action"] == "create_contact"
    assert confirmation_events[0]["payload"]["contact"] == {
        "is_decision_maker": False,
        "name": "王总",
        "mobile": "13800138000",
        "position": "总经理",
        "gender": "1",
    }


@pytest.mark.asyncio
async def test_agent_graph_requires_contact_fields_when_missing():
    tool_service = FakeToolService()
    service = CRMAgentGraphService(tool_service=tool_service)

    result = await service.run({
        "db": object(),
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "authorization": "Bearer test-token",
        "content": "帮我给越秀金融创建联系人王总",
    })

    field_events = [event for event in result["events"] if event["event"] == "contact_fields_required"]
    assert field_events[0]["action"] == "collect_contact_fields"
    assert field_events[0]["payload"]["missing_fields"] == ["mobile", "position", "gender"]


@pytest.mark.asyncio
async def test_agent_graph_requires_invoice_title_confirmation_when_fields_complete():
    tool_service = FakeToolService()
    service = CRMAgentGraphService(tool_service=tool_service)

    result = await service.run({
        "db": object(),
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "authorization": "Bearer test-token",
        "content": "帮我给越秀金融创建发票抬头，抬头是越秀金融控股有限公司，税号91440000123456789X，设为默认",
    })

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
async def test_agent_graph_requires_invoice_title_fields_when_missing():
    tool_service = FakeToolService()
    service = CRMAgentGraphService(tool_service=tool_service)

    result = await service.run({
        "db": object(),
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "authorization": "Bearer test-token",
        "content": "帮我给越秀金融创建发票抬头",
    })

    field_events = [event for event in result["events"] if event["event"] == "invoice_title_fields_required"]
    assert field_events[0]["action"] == "collect_invoice_title_fields"
    assert field_events[0]["payload"]["missing_fields"] == ["title", "taxpayer_id"]

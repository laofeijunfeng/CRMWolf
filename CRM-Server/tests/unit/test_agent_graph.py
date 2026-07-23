"""CRM AI Agent LangGraph tests."""
import pytest

from app.services.agent.graph import CRMAgentGraphService


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

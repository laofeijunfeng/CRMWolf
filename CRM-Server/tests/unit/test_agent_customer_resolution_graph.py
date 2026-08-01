"""Customer resolution domain LangGraph tests."""

from langgraph.checkpoint.memory import InMemorySaver

import pytest

from app.services.agent.customer_resolution_graph import (
    CustomerResolutionGraphService,
    build_customer_resolution_graph_config,
    build_customer_resolution_thread_id,
)
from app.services.agent.schemas import AgentMemorySnapshot
from app.services.agent.tools.base import AgentToolResult
from tests.unit.test_agent_graph import semantic_result


class FakeToolRegistry:
    def __init__(self):
        self.calls = []

    async def execute(self, tool_name, context, payload):
        self.calls.append({
            "tool_name": tool_name,
            "context": context,
            "payload": payload,
        })
        return AgentToolResult(
            tool_name=tool_name,
            success=True,
            data={"items": [{"id": 101, "account_name": "越秀金融"}], "total": 1},
            tool_call_id=701,
        )


@pytest.mark.asyncio
async def test_customer_resolution_graph_searches_and_checkpoints_customer_target():
    registry = FakeToolRegistry()
    service = CustomerResolutionGraphService(
        tool_registry=registry,
        checkpointer=InMemorySaver(),
    )

    result = await service.run({
        "db": object(),
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "content": "今天和越秀金融沟通了项目进展",
        "authorization": "Bearer test",
        "intent": "CUSTOMER_ACTIVITY",
        "semantic_result": semantic_result(),
        "parsed": {"customer_name": "越秀金融"},
        "events": [],
    })
    snapshot = await service._graph.aget_state(build_customer_resolution_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
    ))

    assert build_customer_resolution_thread_id(team_id=1, user_id=2, session_id=3) == (
        "crm_agent_customer_resolution:1:2:3"
    )
    assert registry.calls[0]["tool_name"] == "search_customers"
    assert result["selected_customer"]["id"] == 101
    assert result["selected_customer"]["account_name"] == "越秀金融"
    assert snapshot.values["selected_customer"]["id"] == 101


@pytest.mark.asyncio
async def test_customer_resolution_graph_uses_memory_customer_without_search():
    registry = FakeToolRegistry()
    service = CustomerResolutionGraphService(
        tool_registry=registry,
        checkpointer=InMemorySaver(),
    )
    memory = AgentMemorySnapshot(
        recent_messages=[],
        session_context={"current_customer": {"id": 202, "account_name": "广州睿狐"}},
    )

    result = await service.run({
        "db": object(),
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "content": "补一条跟进",
        "authorization": "Bearer test",
        "intent": "CUSTOMER_ACTIVITY",
        "memory": memory,
        "semantic_result": semantic_result(customer={
            "name_text": None,
            "resolution_source": "MEMORY",
            "confidence": 0.9,
        }),
        "parsed": {},
        "events": [],
    })

    assert registry.calls == []
    assert result["parsed"]["customer_name"] == "广州睿狐"
    assert result["selected_customer"] == {"id": 202, "account_name": "广州睿狐"}

"""Creation duplicate-check domain LangGraph tests."""

from langgraph.checkpoint.memory import InMemorySaver

import pytest

from app.services.agent.creation_duplicates_graph import (
    CreationDuplicateGraphService,
    build_creation_duplicates_graph_config,
    build_creation_duplicates_thread_id,
)
from app.services.agent.tools.base import AgentToolResult
from tests.unit.test_agent_graph import customer_create_semantic_result, lead_semantic_result


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
            data={
                "customers": [{"id": 101, "account_name": "广州睿狐科技"}],
                "leads": [{"id": 201, "lead_name": "广州睿狐"}],
                "hidden_customer_count": 1,
                "hidden_lead_count": 0,
            },
            tool_call_id=901,
        )


@pytest.mark.asyncio
async def test_creation_duplicates_graph_searches_and_checkpoints_json_state():
    registry = FakeToolRegistry()
    service = CreationDuplicateGraphService(
        tool_registry=registry,
        checkpointer=InMemorySaver(),
    )

    result = await service.run({
        "db": object(),
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "content": "帮我创建客户广州睿狐科技",
        "authorization": "Bearer test",
        "semantic_result": customer_create_semantic_result(),
        "parsed": {
            "customer_create": {
                "account_name": "广州睿狐科技",
                "contact_phone": "13800138000",
            },
        },
        "events": [],
    })
    snapshot = await service._graph.aget_state(build_creation_duplicates_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
    ))

    assert build_creation_duplicates_thread_id(team_id=1, user_id=2, session_id=3) == (
        "crm_agent_creation_duplicates:1:2:3"
    )
    assert registry.calls[0]["tool_name"] == "search_creation_duplicates"
    assert registry.calls[0]["payload"]["customer_keywords"] == ["广州睿狐科技"]
    assert registry.calls[0]["payload"]["lead_keywords"] == ["广州睿狐科技"]
    assert registry.calls[0]["payload"]["phone"] == "13800138000"
    assert registry.calls[0]["payload"]["limit"] == 5
    assert result["creation_duplicate_candidates"]["customers"][0]["id"] == 101
    assert result["creation_duplicate_candidates"]["hidden_customer_count"] == 1
    assert snapshot.values["duplicate_search_payload"]["phone"] == "13800138000"
    assert snapshot.values["creation_duplicate_candidates"]["leads"][0]["id"] == 201
    assert "db" not in snapshot.values
    assert "authorization" not in snapshot.values
    assert "semantic_result" not in snapshot.values


@pytest.mark.asyncio
async def test_creation_duplicates_graph_skips_without_search_terms():
    registry = FakeToolRegistry()
    service = CreationDuplicateGraphService(
        tool_registry=registry,
        checkpointer=InMemorySaver(),
    )

    result = await service.run({
        "db": object(),
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "content": "帮我创建线索",
        "authorization": "Bearer test",
        "semantic_result": lead_semantic_result(),
        "parsed": {"lead": {}},
        "events": [],
    })

    assert registry.calls == []
    assert result["duplicate_search_requested"] is False
    assert result["duplicate_skip_reason"] == "missing_search_terms"
    assert result["creation_duplicate_candidates"] == {}

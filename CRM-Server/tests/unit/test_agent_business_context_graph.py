"""Business-context domain LangGraph tests."""

from langgraph.checkpoint.memory import InMemorySaver

import pytest

from app.services.agent.business_context_graph import (
    BusinessContextGraphService,
    build_business_context_graph_config,
    build_business_context_thread_id,
)
from app.services.agent.schemas import AgentSuggestionResult
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
            data={
                "customer": {"id": 101, "account_name": "越秀金融"},
                "opportunities": {"items": [{"id": 301, "opportunity_name": "CRM 项目"}]},
                "contracts": {"items": []},
                "payment_plans": {"items": []},
            },
            tool_call_id=801,
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
                "summary": "建议推进商机。",
                "suggestions": [{
                    "action": "MOVE_OPPORTUNITY_STAGE",
                    "title": "推进商机阶段",
                    "reason": "客户表达了签约意向。",
                    "priority": "high",
                    "requires_confirmation": True,
                    "confidence": 0.91,
                }],
                "need_user_choice": False,
                "clarification_question": None,
            })
            suggestion_source = "test_business_context_graph"
            model = "test-model"
            structured_output_strategy = "tool"
            fallback_reason = None
            fallback_error = None
            fallback_error_message = None

        return Envelope()


@pytest.mark.asyncio
async def test_business_context_graph_loads_context_generates_suggestions_and_checkpoints_json_state():
    registry = FakeToolRegistry()
    suggestion_generator = FakeSuggestionGenerator()
    service = BusinessContextGraphService(
        tool_registry=registry,
        suggestion_generator=suggestion_generator,
        checkpointer=InMemorySaver(),
    )

    result = await service.run({
        "db": object(),
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "content": "张总说今天可以开始签合同了",
        "authorization": "Bearer test",
        "current_date": "2026-07-31",
        "selected_customer": {"id": 101, "account_name": "越秀金融"},
        "semantic_result": semantic_result(),
        "events": [],
    })
    snapshot = await service._graph.aget_state(build_business_context_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
    ))

    assert build_business_context_thread_id(team_id=1, user_id=2, session_id=3) == (
        "crm_agent_business_context:1:2:3"
    )
    assert registry.calls[0]["tool_name"] == "get_customer_context"
    assert registry.calls[0]["payload"] == {"customer_id": 101}
    assert suggestion_generator.calls[0]["customer_context"]["customer"]["id"] == 101
    assert result["suggestion_result"].suggestions[0].action == "MOVE_OPPORTUNITY_STAGE"
    assert result["suggestion_metadata"]["structured_output_strategy"] == "tool"
    assert result["suggestion_metadata"]["fallback_error_message"] is None
    assert snapshot.values["business_context"]["customer"]["id"] == 101
    assert "suggestion_result" not in snapshot.values


@pytest.mark.asyncio
async def test_business_context_graph_accepts_numeric_string_customer_id():
    registry = FakeToolRegistry()
    service = BusinessContextGraphService(
        tool_registry=registry,
        suggestion_generator=FakeSuggestionGenerator(),
        checkpointer=InMemorySaver(),
    )

    await service.run({
        "db": object(),
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "content": "张总说今天可以开始签合同了",
        "authorization": "Bearer test",
        "current_date": "2026-07-31",
        "selected_customer": {"id": "101", "account_name": "越秀金融"},
        "semantic_result": semantic_result(),
        "events": [],
    })

    assert registry.calls[0]["payload"] == {"customer_id": 101}

"""Customer-activity domain LangGraph tests."""

from langgraph.checkpoint.memory import InMemorySaver

import pytest

from app.services.agent.customer_activity_graph import (
    CustomerActivityPlanningGraphService,
    build_customer_activity_graph_config,
    build_customer_activity_thread_id,
)


def customer_activity_input(**overrides):
    payload = {
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "parsed": {
            "customer_name": "越秀金融",
            "follow_up_content": "客户反馈项目还在立项评估阶段",
            "original_content": "客户反馈项目还在立项评估阶段",
            "method": "未指定",
            "next_action": "下周三确认进展",
            "next_follow_time_text": "下周三",
            "next_follow_time_iso": "2026-07-29T09:00:00",
        },
        "customer_candidates": [{"id": 101, "account_name": "越秀金融"}],
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_customer_activity_graph_routes_single_customer_to_confirmation():
    service = CustomerActivityPlanningGraphService(checkpointer=InMemorySaver())

    result = await service.run(customer_activity_input())

    assert build_customer_activity_thread_id(team_id=1, user_id=2, session_id=3) == (
        "crm_agent_customer_activity:1:2:3"
    )
    assert result["customer_route"] == "single_customer"
    assert result["selected_customer"]["id"] == 101
    assert result["action"]["action"] == "create_customer_activity"
    assert result["action"]["payload"]["customer_id"] == 101
    assert result["action"]["payload"]["content"] == "客户反馈项目还在立项评估阶段"


@pytest.mark.asyncio
async def test_customer_activity_graph_routes_missing_customer_name_to_text_request():
    service = CustomerActivityPlanningGraphService()

    result = await service.run(customer_activity_input(parsed={
        "follow_up_content": "客户反馈项目还在立项评估阶段",
    }))

    assert result["customer_route"] == "missing_customer_name"
    assert result["action"] == {}
    assert "缺少明确客户名称" in result["response"]


@pytest.mark.asyncio
async def test_customer_activity_graph_routes_multiple_customers_to_choice_action():
    service = CustomerActivityPlanningGraphService()

    result = await service.run(customer_activity_input(customer_candidates=[
        {"id": 101, "account_name": "越秀金融"},
        {"id": 102, "account_name": "越秀金融科技"},
    ]))

    assert result["customer_route"] == "multiple_customers"
    assert result["action"]["action"] == "select_customer_for_activity"
    assert result["action"]["customers"][1]["id"] == 102


@pytest.mark.asyncio
async def test_customer_activity_graph_resets_action_between_turns_on_same_thread():
    service = CustomerActivityPlanningGraphService(checkpointer=InMemorySaver())

    first = await service.run(customer_activity_input())
    second = await service.run(customer_activity_input(
        parsed={"customer_name": "不存在客户", "follow_up_content": "继续跟进"},
        customer_candidates=[],
    ))

    snapshot = await service._graph.aget_state(build_customer_activity_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
    ))
    assert first["action"]["action"] == "create_customer_activity"
    assert second["customer_route"] == "customer_not_found"
    assert second["action"] == {}
    assert snapshot.values["customer_route"] == "customer_not_found"
    assert snapshot.values["action"] == {}
    assert snapshot.values["selected_customer"] == {}


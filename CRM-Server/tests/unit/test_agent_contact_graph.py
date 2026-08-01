"""Contact domain LangGraph tests."""

from langgraph.checkpoint.memory import InMemorySaver

import pytest

from app.services.agent.contact_graph import (
    ContactPlanningGraphService,
    build_contact_graph_config,
    build_contact_thread_id,
)


def contact_input(**overrides):
    payload = {
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "parsed": {
            "customer_name": "越秀金融",
            "contact": {
                "name": "王总",
                "mobile": "13800138000",
                "position": "总经理",
                "gender": "1",
                "is_decision_maker": True,
            },
        },
        "customer_candidates": [{"id": 101, "account_name": "越秀金融"}],
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_contact_graph_routes_complete_contact_to_confirmation():
    service = ContactPlanningGraphService(checkpointer=InMemorySaver())

    result = await service.run(contact_input())

    assert build_contact_thread_id(team_id=1, user_id=2, session_id=3) == "crm_agent_contact:1:2:3"
    assert result["customer_route"] == "single_customer"
    assert result["contact_route"] == "confirm_create"
    assert result["action"]["action"] == "create_contact"
    assert result["action"]["payload"]["customer_id"] == 101
    assert result["action"]["payload"]["contact"]["mobile"] == "13800138000"


@pytest.mark.asyncio
async def test_contact_graph_routes_missing_fields_to_form_action():
    service = ContactPlanningGraphService()

    result = await service.run(contact_input(parsed={
        "customer_name": "越秀金融",
        "contact": {"name": "王总"},
    }))

    assert result["contact_route"] == "collect_fields"
    assert result["action"]["action"] == "collect_contact_fields"
    assert result["action"]["payload"]["missing_fields"] == ["mobile", "position", "gender"]


@pytest.mark.asyncio
async def test_contact_graph_routes_multiple_customers_to_choice_action():
    service = ContactPlanningGraphService()

    result = await service.run(contact_input(customer_candidates=[
        {"id": 101, "account_name": "越秀金融"},
        {"id": 102, "account_name": "越秀金融科技"},
    ]))

    assert result["customer_route"] == "multiple_customers"
    assert result["action"]["action"] == "select_customer_for_contact"
    assert result["action"]["customers"][1]["id"] == 102
    assert "请告诉我要把联系人创建到哪一个客户" in result["response"]


@pytest.mark.asyncio
async def test_contact_graph_resets_action_between_turns_on_same_thread():
    service = ContactPlanningGraphService(checkpointer=InMemorySaver())

    first = await service.run(contact_input())
    second = await service.run(contact_input(
        parsed={"customer_name": "不存在客户", "contact": {}},
        customer_candidates=[],
    ))

    snapshot = await service._graph.aget_state(build_contact_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
    ))
    assert first["action"]["action"] == "create_contact"
    assert second["customer_route"] == "customer_not_found"
    assert second["action"] == {}
    assert snapshot.values["customer_route"] == "customer_not_found"

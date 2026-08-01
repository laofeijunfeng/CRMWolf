"""Customer-member domain LangGraph tests."""

from langgraph.checkpoint.memory import InMemorySaver

import pytest

from app.services.agent.customer_member_graph import (
    CustomerMemberPlanningGraphService,
    build_customer_member_graph_config,
    build_customer_member_thread_id,
)


def customer_member_input(**overrides):
    payload = {
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "parsed": {
            "customer_name": "越秀金融",
            "customer_member": {
                "user_name": "陈工",
                "member_role": "PRESALES",
                "access_level": "EDIT",
            },
        },
        "customer_candidates": [{"id": 101, "account_name": "越秀金融"}],
        "business_context": {
            "member_candidates": {
                "items": [{"id": 201, "name": "陈工", "already_member": False}],
            },
        },
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_customer_member_graph_routes_resolved_member_to_confirmation():
    service = CustomerMemberPlanningGraphService(checkpointer=InMemorySaver())

    result = await service.run(customer_member_input())

    assert build_customer_member_thread_id(team_id=1, user_id=2, session_id=3) == (
        "crm_agent_customer_member:1:2:3"
    )
    assert result["customer_route"] == "single_customer"
    assert result["customer_member_route"] == "confirm_create"
    assert result["action"]["action"] == "create_customer_member"
    assert result["action"]["payload"]["customer_id"] == 101
    assert result["action"]["payload"]["member"]["user_id"] == 201


@pytest.mark.asyncio
async def test_customer_member_graph_routes_missing_fields_to_form_action():
    service = CustomerMemberPlanningGraphService()

    result = await service.run(customer_member_input(parsed={
        "customer_name": "越秀金融",
        "customer_member": {},
    }))

    assert result["customer_member_route"] == "collect_fields"
    assert result["action"]["action"] == "collect_customer_member_fields"
    assert result["action"]["payload"]["missing_fields"] == ["user_name"]


@pytest.mark.asyncio
async def test_customer_member_graph_routes_resolution_error_to_form_action():
    service = CustomerMemberPlanningGraphService()

    result = await service.run(customer_member_input(business_context={
        "member_candidates": {"items": []},
    }))

    assert result["customer_member_route"] == "member_resolution_error"
    assert result["action"]["action"] == "collect_customer_member_fields"
    assert result["action"]["payload"]["missing_fields"] == ["user_name"]
    assert "没在客户成员候选人里找到" in result["response"]


@pytest.mark.asyncio
async def test_customer_member_graph_routes_multiple_customers_to_choice_action():
    service = CustomerMemberPlanningGraphService()

    result = await service.run(customer_member_input(customer_candidates=[
        {"id": 101, "account_name": "越秀金融"},
        {"id": 102, "account_name": "越秀金融科技"},
    ]))

    assert result["customer_route"] == "multiple_customers"
    assert result["action"]["action"] == "select_customer_for_customer_member"
    assert result["action"]["customers"][1]["id"] == 102


@pytest.mark.asyncio
async def test_customer_member_graph_resets_action_between_turns_on_same_thread():
    service = CustomerMemberPlanningGraphService(checkpointer=InMemorySaver())

    first = await service.run(customer_member_input())
    second = await service.run(customer_member_input(
        parsed={"customer_name": "不存在客户", "customer_member": {}},
        customer_candidates=[],
    ))

    snapshot = await service._graph.aget_state(build_customer_member_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
    ))
    assert first["action"]["action"] == "create_customer_member"
    assert second["customer_route"] == "customer_not_found"
    assert second["action"] == {}
    assert snapshot.values["customer_route"] == "customer_not_found"
    assert snapshot.values["action"] == {}
    assert snapshot.values["selected_customer"] == {}
    assert snapshot.values["resolved_member"] == {}
    assert snapshot.values["member_error"] is None
    assert snapshot.values["missing_fields"] == ["user_name"]

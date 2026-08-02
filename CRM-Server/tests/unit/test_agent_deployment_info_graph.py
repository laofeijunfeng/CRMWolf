"""Deployment-info domain LangGraph tests."""

from langgraph.checkpoint.memory import InMemorySaver

import pytest

from app.services.agent.deployment_info_graph import (
    DeploymentInfoPlanningGraphService,
    build_deployment_info_graph_config,
    build_deployment_info_thread_id,
)


def deployment_info_input(**overrides):
    payload = {
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "parsed": {
            "customer_name": "越秀金融",
            "deployment_info": {
                "deployment_name": "生产环境",
                "server_address": "https://crm.example.com",
                "authorized_users": 100,
            },
        },
        "customer_candidates": [{"id": 101, "account_name": "越秀金融"}],
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_deployment_info_graph_routes_complete_info_to_confirmation():
    service = DeploymentInfoPlanningGraphService(checkpointer=InMemorySaver())

    result = await service.run(deployment_info_input())

    assert build_deployment_info_thread_id(team_id=1, user_id=2, session_id=3) == (
        "crm_agent_deployment_info:1:2:3"
    )
    assert result["customer_route"] == "single_customer"
    assert result["deployment_info_route"] == "confirm_create"
    assert result["action"]["action"] == "create_deployment_info"
    assert result["action"]["payload"]["customer_id"] == 101
    assert result["action"]["payload"]["deployment_info"]["customer_id"] == 101


@pytest.mark.asyncio
async def test_deployment_info_graph_routes_missing_fields_to_form_action():
    service = DeploymentInfoPlanningGraphService()

    result = await service.run(deployment_info_input(parsed={
        "customer_name": "越秀金融",
        "deployment_info": {"deployment_name": "生产环境"},
    }))

    assert result["deployment_info_route"] == "collect_fields"
    assert result["action"]["action"] == "collect_deployment_info_fields"
    assert result["action"]["payload"]["missing_fields"] == ["server_address"]


@pytest.mark.asyncio
async def test_deployment_info_graph_routes_multiple_customers_to_choice_action():
    service = DeploymentInfoPlanningGraphService()

    result = await service.run(deployment_info_input(customer_candidates=[
        {"id": 101, "account_name": "越秀金融"},
        {"id": 102, "account_name": "越秀金融科技"},
    ]))

    assert result["customer_route"] == "multiple_customers"
    assert result["action"]["action"] == "select_customer_for_deployment_info"
    assert result["action"]["customers"][1]["id"] == 102


@pytest.mark.asyncio
async def test_deployment_info_graph_resets_action_between_turns_on_same_thread():
    service = DeploymentInfoPlanningGraphService(checkpointer=InMemorySaver())

    first = await service.run(deployment_info_input())
    second = await service.run(deployment_info_input(
        parsed={"customer_name": "不存在客户", "deployment_info": {}},
        customer_candidates=[],
    ))

    snapshot = await service._graph.aget_state(build_deployment_info_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
    ))
    assert first["action"]["action"] == "create_deployment_info"
    assert second["customer_route"] == "customer_not_found"
    assert second["action"] == {}
    assert snapshot.values["customer_route"] == "customer_not_found"
    assert snapshot.values["action"] == {}
    assert snapshot.values["selected_customer"] == {}
    assert snapshot.values["missing_fields"] == ["deployment_name", "server_address"]

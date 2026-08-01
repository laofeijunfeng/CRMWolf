"""Opportunity domain LangGraph tests."""

from langgraph.checkpoint.memory import InMemorySaver

import pytest

from app.services.agent.opportunity_graph import (
    OpportunityPlanningGraphService,
    build_opportunity_graph_config,
    build_opportunity_thread_id,
)


def opportunity_input(**overrides):
    payload = {
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "parsed": {
            "customer_name": "越秀金融",
            "opportunity": {
                "opportunity_name": "越秀金融 CRM 商机",
                "total_amount": 50000,
                "user_count": 100,
                "license_type": "SUBSCRIPTION",
                "subscription_years": 1,
                "purchase_type": "NEW",
                "expected_closing_date": "2026-08-31",
                "procurement_method_id": 9,
            },
            "missing_opportunity_fields": [],
        },
        "customer_candidates": [{
            "id": 101,
            "account_name": "越秀金融",
            "default_procurement_method_id": 9,
        }],
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_opportunity_graph_routes_complete_opportunity_to_confirmation():
    service = OpportunityPlanningGraphService(checkpointer=InMemorySaver())

    result = await service.run(opportunity_input())

    assert build_opportunity_thread_id(team_id=1, user_id=2, session_id=3) == "crm_agent_opportunity:1:2:3"
    assert result["customer_route"] == "single_customer"
    assert result["opportunity_route"] == "confirm_create"
    assert result["action"]["action"] == "create_opportunity"
    assert result["action"]["payload"]["customer_id"] == 101
    assert "opportunity_name" not in result["action"]["payload"]["opportunity"]


@pytest.mark.asyncio
async def test_opportunity_graph_routes_missing_fields_to_form_action():
    service = OpportunityPlanningGraphService()

    result = await service.run(opportunity_input(parsed={
        "customer_name": "越秀金融",
        "opportunity": {
            "total_amount": 50000,
            "user_count": 100,
            "license_type": "SUBSCRIPTION",
            "subscription_years": 1,
        },
        "missing_opportunity_fields": ["purchase_type", "expected_closing_date"],
    }))

    assert result["opportunity_route"] == "collect_fields"
    assert result["action"]["action"] == "collect_opportunity_fields"
    assert result["action"]["payload"]["missing_fields"] == ["purchase_type", "expected_closing_date"]
    assert "procurement_method_id" in result["action"]["payload"]["interaction_fields"]


@pytest.mark.asyncio
async def test_opportunity_graph_routes_multiple_customers_to_choice_action():
    service = OpportunityPlanningGraphService()

    result = await service.run(opportunity_input(customer_candidates=[
        {"id": 101, "account_name": "越秀金融"},
        {"id": 102, "account_name": "越秀金融科技"},
    ]))

    assert result["customer_route"] == "multiple_customers"
    assert result["action"]["action"] == "select_customer_for_opportunity"
    assert result["action"]["customers"][1]["id"] == 102
    assert "请告诉我要把商机创建到哪一个客户" in result["response"]


@pytest.mark.asyncio
async def test_opportunity_graph_resets_action_between_turns_on_same_thread():
    service = OpportunityPlanningGraphService(checkpointer=InMemorySaver())

    first = await service.run(opportunity_input())
    second = await service.run(opportunity_input(
        parsed={"customer_name": "不存在客户", "opportunity": {}},
        customer_candidates=[],
    ))

    snapshot = await service._graph.aget_state(build_opportunity_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
    ))
    assert first["action"]["action"] == "create_opportunity"
    assert second["customer_route"] == "customer_not_found"
    assert second["action"] == {}
    assert snapshot.values["customer_route"] == "customer_not_found"

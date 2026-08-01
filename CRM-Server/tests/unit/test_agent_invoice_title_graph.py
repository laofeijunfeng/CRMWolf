"""Invoice-title domain LangGraph tests."""

from langgraph.checkpoint.memory import InMemorySaver

import pytest

from app.services.agent.invoice_title_graph import (
    InvoiceTitlePlanningGraphService,
    build_invoice_title_graph_config,
    build_invoice_title_thread_id,
)


def invoice_title_input(**overrides):
    payload = {
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "parsed": {
            "customer_name": "越秀金融",
            "invoice_title": {
                "title_type": "ENTERPRISE",
                "title": "越秀金融科技有限公司",
                "taxpayer_id": "91440101MA00000000",
                "set_default": True,
            },
        },
        "customer_candidates": [{"id": 101, "account_name": "越秀金融"}],
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_invoice_title_graph_routes_complete_title_to_confirmation():
    service = InvoiceTitlePlanningGraphService(checkpointer=InMemorySaver())

    result = await service.run(invoice_title_input())

    assert build_invoice_title_thread_id(team_id=1, user_id=2, session_id=3) == (
        "crm_agent_invoice_title:1:2:3"
    )
    assert result["customer_route"] == "single_customer"
    assert result["invoice_title_route"] == "confirm_create"
    assert result["action"]["action"] == "create_invoice_title"
    assert result["action"]["payload"]["customer_id"] == 101
    assert result["action"]["payload"]["set_default"] is True
    assert "set_default" not in result["action"]["payload"]["invoice_title"]


@pytest.mark.asyncio
async def test_invoice_title_graph_routes_missing_fields_to_form_action():
    service = InvoiceTitlePlanningGraphService()

    result = await service.run(invoice_title_input(parsed={
        "customer_name": "越秀金融",
        "invoice_title": {"title": "越秀金融科技有限公司"},
    }))

    assert result["invoice_title_route"] == "collect_fields"
    assert result["action"]["action"] == "collect_invoice_title_fields"
    assert result["action"]["payload"]["missing_fields"] == ["title_type", "taxpayer_id"]


@pytest.mark.asyncio
async def test_invoice_title_graph_routes_multiple_customers_to_choice_action():
    service = InvoiceTitlePlanningGraphService()

    result = await service.run(invoice_title_input(customer_candidates=[
        {"id": 101, "account_name": "越秀金融"},
        {"id": 102, "account_name": "越秀金融科技"},
    ]))

    assert result["customer_route"] == "multiple_customers"
    assert result["action"]["action"] == "select_customer_for_invoice_title"
    assert result["action"]["customers"][1]["id"] == 102


@pytest.mark.asyncio
async def test_invoice_title_graph_resets_action_between_turns_on_same_thread():
    service = InvoiceTitlePlanningGraphService(checkpointer=InMemorySaver())

    first = await service.run(invoice_title_input())
    second = await service.run(invoice_title_input(
        parsed={"customer_name": "不存在客户", "invoice_title": {}},
        customer_candidates=[],
    ))

    snapshot = await service._graph.aget_state(build_invoice_title_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
    ))
    assert first["action"]["action"] == "create_invoice_title"
    assert second["customer_route"] == "customer_not_found"
    assert second["action"] == {}
    assert snapshot.values["customer_route"] == "customer_not_found"
    assert snapshot.values["action"] == {}
    assert snapshot.values["selected_customer"] == {}
    assert snapshot.values["missing_fields"] == ["title_type", "title", "taxpayer_id"]

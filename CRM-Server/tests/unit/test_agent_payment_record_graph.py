"""Payment-record domain LangGraph tests."""

from langgraph.checkpoint.memory import InMemorySaver

import pytest

from app.services.agent.payment_record_graph import (
    PaymentRecordPlanningGraphService,
    build_payment_record_graph_config,
    build_payment_record_thread_id,
)


def payment_input(**overrides):
    payload = {
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "parsed": {
            "customer_name": "越秀金融",
            "payment": {
                "actual_amount": 300000,
                "payment_date_iso": "2026-07-31",
                "actual_payer_name": "越秀金融",
            },
        },
        "customer_candidates": [{
            "id": 101,
            "account_name": "越秀金融",
            "owner_info": {"id": 2},
        }],
        "business_context": {
            "contracts": {"items": [{
                "id": 201,
                "contract_name": "越秀金融 CRM 合同",
                "total_amount": 300000,
                "status": "SIGNED",
            }]},
            "payment_plans": {"items": [{
                "id": 301,
                "contract_id": 201,
                "contract_name": "越秀金融 CRM 合同",
                "stage_name": "首款",
                "remaining_amount": 300000,
                "status": "PENDING",
            }]},
            "opportunities": {"items": []},
        },
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_payment_record_graph_routes_single_open_plan_to_confirmation():
    service = PaymentRecordPlanningGraphService(checkpointer=InMemorySaver())

    result = await service.run(payment_input())

    assert build_payment_record_thread_id(team_id=1, user_id=2, session_id=3) == "crm_agent_payment_record:1:2:3"
    assert result["customer_route"] == "single_customer"
    assert result["payment_route"] == "single_open_payment_plan"
    assert result["action"]["action"] == "create_payment_record"
    assert result["action"]["payload"]["payment_plan_id"] == 301
    assert "请确认是否登记这笔回款" in result["response"]


@pytest.mark.asyncio
async def test_payment_record_graph_routes_missing_fields_to_form_action():
    service = PaymentRecordPlanningGraphService()

    result = await service.run(payment_input(parsed={
        "customer_name": "越秀金融",
        "payment": {
            "actual_amount": None,
            "payment_date_iso": "2026-07-31",
        },
    }))

    assert result["payment_route"] == "missing_payment_fields"
    assert result["action"]["action"] == "collect_payment_fields"
    assert result["action"]["payload"]["missing_fields"] == ["actual_amount"]


@pytest.mark.asyncio
async def test_payment_record_graph_resets_action_between_turns_on_same_thread():
    service = PaymentRecordPlanningGraphService(checkpointer=InMemorySaver())

    first = await service.run(payment_input())
    second = await service.run(payment_input(business_context={
        "contracts": {"items": []},
        "payment_plans": {"items": []},
        "opportunities": {"items": []},
    }))

    snapshot = await service._graph.aget_state(build_payment_record_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
    ))
    assert first["action"]["action"] == "create_payment_record"
    assert second["payment_route"] == "no_contracts_no_opportunities"
    assert second["action"] == {}
    assert snapshot.values["payment_route"] == "no_contracts_no_opportunities"


@pytest.mark.asyncio
async def test_payment_record_graph_routes_multiple_customers_to_choice_action():
    service = PaymentRecordPlanningGraphService()

    result = await service.run(payment_input(customer_candidates=[
        {"id": 101, "account_name": "越秀金融"},
        {"id": 102, "account_name": "越秀金融科技"},
    ]))

    assert result["customer_route"] == "multiple_customers"
    assert result["action"]["action"] == "select_customer_for_payment_record"
    assert result["action"]["customers"][1]["id"] == 102
    assert "请告诉我要为哪一个客户处理回款" in result["response"]

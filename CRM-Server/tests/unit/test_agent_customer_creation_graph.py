"""Customer-creation domain LangGraph tests."""

from langgraph.checkpoint.memory import InMemorySaver

import pytest

from app.services.agent.customer_creation_graph import (
    CustomerCreationPlanningGraphService,
    build_customer_creation_graph_config,
    build_customer_creation_thread_id,
)


def customer_creation_input(**overrides):
    payload = {
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "parsed": {
            "customer_create": {
                "account_name": "广州睿狐科技",
                "city": "广州",
                "contact_name": "王总",
                "contact_phone": "13800138000",
                "contact_position": "CTO",
                "contact_gender": "1",
            },
            "customer_activity": {"content": "客户已经确认采购 CRM"},
        },
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_customer_creation_graph_routes_complete_customer_to_confirmation():
    service = CustomerCreationPlanningGraphService(checkpointer=InMemorySaver())

    result = await service.run(customer_creation_input())

    assert build_customer_creation_thread_id(team_id=1, user_id=2, session_id=3) == (
        "crm_agent_customer_creation:1:2:3"
    )
    assert result["customer_create_route"] == "confirm_create"
    assert result["missing_fields"] == []
    assert result["action"]["action"] == "create_customer"
    assert result["action"]["payload"]["customer"]["account_name"] == "广州睿狐科技"


@pytest.mark.asyncio
async def test_customer_creation_graph_routes_missing_fields_to_form_action():
    service = CustomerCreationPlanningGraphService()

    result = await service.run(customer_creation_input(parsed={
        "customer_create": {"account_name": "广州睿狐科技"},
        "customer_follow_up": {"content": "客户已经确认采购 CRM"},
    }))

    assert result["customer_create_route"] == "collect_fields"
    assert result["action"]["action"] == "collect_customer_fields"
    assert result["action"]["payload"]["missing_fields"] == ["city"]
    assert result["action"]["payload"]["customer_activity"]["content"] == "客户已经确认采购 CRM"


@pytest.mark.asyncio
async def test_customer_creation_graph_resets_action_between_turns_on_same_thread():
    service = CustomerCreationPlanningGraphService(checkpointer=InMemorySaver())

    first = await service.run(customer_creation_input())
    second = await service.run(customer_creation_input(parsed={"customer_create": {}}))

    snapshot = await service._graph.aget_state(build_customer_creation_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
    ))
    assert first["action"]["action"] == "create_customer"
    assert second["customer_create_route"] == "collect_fields"
    assert second["action"]["action"] == "collect_customer_fields"
    assert snapshot.values["action"]["action"] == "collect_customer_fields"
    assert snapshot.values["missing_fields"] == ["account_name", "city"]


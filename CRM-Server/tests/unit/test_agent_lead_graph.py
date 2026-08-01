"""Lead domain LangGraph tests."""

from langgraph.checkpoint.memory import InMemorySaver

import pytest

from app.services.agent.lead_graph import (
    LeadPlanningGraphService,
    build_lead_graph_config,
    build_lead_thread_id,
)


def lead_input(**overrides):
    payload = {
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "parsed": {
            "lead": {
                "lead_name": "广州睿狐科技",
                "city": "广州",
                "contact_name": "王总",
                "contact_phone": "13800138000",
            },
            "lead_follow_up": {"content": "客户对 CRM 感兴趣"},
        },
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_lead_graph_routes_complete_lead_to_confirmation():
    service = LeadPlanningGraphService(checkpointer=InMemorySaver())

    result = await service.run(lead_input())

    assert build_lead_thread_id(team_id=1, user_id=2, session_id=3) == "crm_agent_lead:1:2:3"
    assert result["lead_route"] == "confirm_create"
    assert result["missing_fields"] == []
    assert result["action"]["action"] == "create_lead"
    assert result["action"]["payload"]["lead"]["lead_name"] == "广州睿狐科技"


@pytest.mark.asyncio
async def test_lead_graph_routes_missing_fields_to_form_action():
    service = LeadPlanningGraphService()

    result = await service.run(lead_input(parsed={
        "lead": {"lead_name": "广州睿狐科技"},
        "lead_follow_up": {"content": "客户对 CRM 感兴趣"},
    }))

    assert result["lead_route"] == "collect_fields"
    assert result["action"]["action"] == "collect_lead_fields"
    assert result["action"]["payload"]["missing_fields"] == ["city", "contact_name", "contact_phone"]


@pytest.mark.asyncio
async def test_lead_graph_resets_action_between_turns_on_same_thread():
    service = LeadPlanningGraphService(checkpointer=InMemorySaver())

    first = await service.run(lead_input())
    second = await service.run(lead_input(parsed={"lead": {}}))

    snapshot = await service._graph.aget_state(build_lead_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
    ))
    assert first["action"]["action"] == "create_lead"
    assert second["lead_route"] == "collect_fields"
    assert second["action"]["action"] == "collect_lead_fields"
    assert snapshot.values["action"]["action"] == "collect_lead_fields"
    assert snapshot.values["missing_fields"] == ["lead_name", "city", "contact_name", "contact_phone"]


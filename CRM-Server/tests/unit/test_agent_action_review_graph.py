import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.services.agent.action_review_graph import ActionReviewGraphService


@pytest.mark.asyncio
async def test_action_review_auto_executes_low_risk_clear_follow_up():
    service = ActionReviewGraphService(checkpointer=InMemorySaver())

    result = await service.run({
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "event": {
            "event": "confirmation_required",
            "action": "create_customer_activity",
            "hitl_auto_execute_candidate": True,
            "payload": {
                "customer_id": 101,
                "content": "张总确认今天可以开始签合同了",
                "hitl_auto_execute_candidate": True,
            },
        },
    })

    assert result["decision"] == "auto_execute"
    assert result["risk_level"] == "low"
    assert result["execution_confidence"] >= 0.92


@pytest.mark.asyncio
async def test_action_review_keeps_high_risk_payment_confirmation():
    service = ActionReviewGraphService(checkpointer=InMemorySaver())

    result = await service.run({
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "event": {
            "event": "confirmation_required",
            "action": "create_payment_record",
            "hitl_auto_execute_candidate": True,
            "payload": {
                "customer_id": 101,
                "amount": 10000,
                "hitl_auto_execute_candidate": True,
            },
        },
    })

    assert result["decision"] == "require_confirmation"
    assert result["risk_level"] == "high"


@pytest.mark.asyncio
async def test_action_review_keeps_selection_as_choice():
    service = ActionReviewGraphService(checkpointer=InMemorySaver())

    result = await service.run({
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "event": {
            "event": "business_selection_required",
            "action": "select_opportunity_for_stage_move",
            "payload": {"customer_id": 101},
        },
    })

    assert result["decision"] == "require_choice"


@pytest.mark.asyncio
async def test_action_review_keeps_field_collection_as_form():
    service = ActionReviewGraphService(checkpointer=InMemorySaver())

    result = await service.run({
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "event": {
            "event": "opportunity_fields_required",
            "action": "collect_opportunity_fields",
            "payload": {"customer_id": 101},
        },
    })

    assert result["decision"] == "require_fields"

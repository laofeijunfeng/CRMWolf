"""Tests for deterministic Root Graph interaction arbitration."""

from app.services.agent.business_interaction_planner import BusinessInteractionPlanner


def test_existing_interrupt_has_priority_over_follow_up_confirmation():
    planner = BusinessInteractionPlanner()

    plan = planner.plan(
        semantic={},
        business_context={},
        suggestions={},
        current_interrupt={
            "schema_version": "agent.interrupt.v1",
            "type": "confirm",
            "reason": "user_input_required",
            "business_action": "CREATE_FOLLOW_UP",
        },
        pending_task_projection={},
        tool_capability={"follow_up_confirmation": True},
        follow_up_confirmation_candidate={"case_public_id": "fuc_1"},
    )

    assert plan.action == "keep_current_interrupt"
    assert plan.candidate == {}
    assert plan.reason == "higher_priority_interaction_already_selected"


def test_follow_up_confirmation_is_selected_when_no_higher_priority_interaction_exists():
    planner = BusinessInteractionPlanner()
    candidate = {"case_public_id": "fuc_1"}

    plan = planner.plan(
        semantic={},
        business_context={},
        suggestions={},
        current_interrupt=None,
        pending_task_projection={},
        tool_capability={"follow_up_confirmation": True},
        follow_up_confirmation_candidate=candidate,
    )

    assert plan.action == "follow_up_confirmation"
    assert plan.candidate == candidate
    assert plan.reason == "durable_owner_confirmation_pending"

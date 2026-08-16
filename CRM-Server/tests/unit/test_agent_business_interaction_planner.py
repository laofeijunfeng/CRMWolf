"""Tests for deterministic Root Graph interaction arbitration."""

from app.services.agent.business_interaction_planner import BusinessInteractionPlanner


def _scope(*, customer_id=101, operation_status="succeeded"):
    return {
        "turn_id": "turn-1",
        "session_id": 4,
        "customer_id": customer_id,
        "operation_status": operation_status,
    }


def _candidate(*, customer_id=101, origin="current_turn", presentation="blocking_interrupt"):
    return {
        "interaction_id": "int-1",
        "kind": "follow_up_confirmation",
        "origin": origin,
        "presentation": presentation,
        "customer_id": customer_id,
        "case_public_id": "fuc_1",
        "business_action": "resolve_follow_up_task_confirmation_case",
        "priority": 100,
        "payload": {"case_public_id": "fuc_1"},
    }


def test_existing_interrupt_has_priority_over_current_turn_confirmation():
    planner = BusinessInteractionPlanner()

    plan = planner.plan(
        turn_scope=_scope(),
        current_interrupt={
            "schema_version": "agent.interrupt.v1",
            "type": "confirm",
            "reason": "user_input_required",
            "business_action": "CREATE_FOLLOW_UP",
        },
        candidates=[_candidate()],
    )

    assert plan.action == "keep_current_interrupt"
    assert plan.candidate == {}
    assert plan.reason == "higher_priority_interaction_already_selected"


def test_matching_current_turn_confirmation_may_block():
    planner = BusinessInteractionPlanner()
    candidate = _candidate()

    plan = planner.plan(turn_scope=_scope(), current_interrupt=None, candidates=[candidate])

    assert plan.action == "follow_up_confirmation"
    assert plan.candidate == candidate
    assert plan.reason == "current_turn_confirmation_requires_user_input"


def test_historical_durable_confirmation_never_blocks_current_turn():
    planner = BusinessInteractionPlanner()

    plan = planner.plan(
        turn_scope=_scope(),
        current_interrupt=None,
        candidates=[_candidate(origin="durable_inbox", presentation="notification_only")],
    )

    assert plan.action == "none"
    assert plan.reason == "no_current_turn_blocking_interaction"


def test_cross_customer_confirmation_never_blocks_current_turn():
    planner = BusinessInteractionPlanner()

    plan = planner.plan(
        turn_scope=_scope(customer_id=101),
        current_interrupt=None,
        candidates=[_candidate(customer_id=202)],
    )

    assert plan.action == "none"
    assert plan.reason == "no_current_turn_blocking_interaction"


def test_failed_current_operation_is_not_overridden_by_confirmation():
    planner = BusinessInteractionPlanner()

    plan = planner.plan(
        turn_scope=_scope(operation_status="failed"),
        current_interrupt=None,
        candidates=[_candidate()],
    )

    assert plan.action == "none"
    assert plan.reason == "current_operation_not_interruptible"

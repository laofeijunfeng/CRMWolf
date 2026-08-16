import pytest

from app.services.agent import task_factory


def test_waiting_task_event_protocol_includes_all_agent_interaction_events():
    event_names = {
        "confirmation_required",
        "customer_selection_required",
        "contact_fields_required",
        "invoice_title_fields_required",
        "deployment_info_fields_required",
        "customer_member_fields_required",
        "payment_fields_required",
        "lead_fields_required",
        "customer_fields_required",
        "opportunity_fields_required",
        "follow_up_quality_required",
        "business_selection_required",
    }

    assert task_factory.WAITING_TASK_EVENT_TYPES == event_names
    assert all(task_factory._is_waiting_task_event({"event": event}) for event in event_names)
    assert task_factory._is_waiting_task_event({"event": "final"}) is False


def test_confirmation_summary_for_action_hides_internal_action_key():
    assert task_factory._confirmation_summary_for_action(
        "create_customer_activity",
        content="确认后，我会继续执行「create_customer_activity」。",
    ) == "确认记录跟进"
    assert task_factory._confirmation_summary_for_action(
        "create_customer_activity",
        content=None,
    ) == "确认记录跟进"


def test_waiting_task_semantics_fail_closed_on_unregistered_action():
    from app.services.agent.waiting_task_semantics import require_waiting_event_name_for_task_action

    try:
        require_waiting_event_name_for_task_action("select_unknown_resource")
    except ValueError as exc:
        assert "no registered interaction semantics" in str(exc)
    else:
        raise AssertionError("expected unregistered waiting action to fail closed")


def test_waiting_task_semantics_reject_conflicting_persisted_source_event():
    from app.services.agent.waiting_task_semantics import waiting_event_name_from_task_state

    try:
        waiting_event_name_from_task_state({
            "action": "select_customer_for_activity",
            "source_event": "confirmation_required",
        })
    except ValueError as exc:
        assert "semantics conflict" in str(exc)
    else:
        raise AssertionError("expected conflicting waiting semantics to fail closed")


def test_waiting_task_semantics_reject_unregistered_action_even_with_persisted_source_event():
    from app.services.agent.waiting_task_semantics import waiting_event_name_from_task_state

    with pytest.raises(ValueError, match="no registered interaction semantics"):
        waiting_event_name_from_task_state({
            "action": "select_unknown_resource",
            "source_event": "customer_selection_required",
        })

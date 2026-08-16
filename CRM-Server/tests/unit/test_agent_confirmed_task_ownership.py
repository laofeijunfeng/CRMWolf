"""Confirmed-task active ownership contract tests."""
from types import SimpleNamespace

from app.services.agent.confirmed_task_ownership import ConfirmedTaskOwnershipProjector


def _executed_task():
    return SimpleNamespace(
        id=101,
        task_key="task-101",
        team_id=2,
        user_id=3,
        session_id=4,
        status="COMPLETED",
        state_json={"action": "create_customer_activity"},
    )


def _executed_snapshot():
    return {
        "id": 101,
        "task_key": "task-101",
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "status": "COMPLETED",
        "state_json": {"action": "create_customer_activity"},
    }


def _active_snapshot():
    return {
        "id": 102,
        "task_key": "task-102",
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "status": "WAITING_USER",
        "intent": "CREATE_OPPORTUNITY",
        "target_type": "customer",
        "target_id": 17,
        "state_json": {
            "action": "collect_opportunity_fields",
            "customer": {"id": 17, "account_name": "广州睿狐科技有限公司"},
            "payload": {"customer_id": 17, "missing_fields": ["total_amount"]},
        },
    }


def _result(*, active_snapshot=None, next_task_id=102):
    interaction = {
        "schema_version": "agent.interaction.v1",
        "interaction_id": "int-next-task-102",
        "type": "form",
        "status": "waiting_user_input",
        "business_action": "create_opportunity",
        "prompt": "还差商机金额。请补充。",
        "fields": [],
        "choices": [],
        "presentation": {},
        "metadata": {},
    }
    task_event = {
        "event": "task_completed",
        "task_id": 101,
        "content": "跟进记录已创建。",
        "interaction": interaction,
    }
    if next_task_id is not None:
        task_event["next_task_id"] = next_task_id
    return {
        "task_event": task_event,
        "executed_task_snapshot": _executed_snapshot(),
        "active_task_snapshot": _active_snapshot() if active_snapshot is None else active_snapshot,
    }


def test_projector_accepts_owned_waiting_next_task_snapshot():
    projection = ConfirmedTaskOwnershipProjector().project(
        _result(),
        expected_task=_executed_task(),
        team_id=2,
        user_id=3,
        session_id=4,
    )

    assert projection.rejected is False
    assert projection.active_task_snapshot["id"] == 102
    assert projection.task_projection == {
        "id": 102,
        "task_key": "task-102",
        "status": "WAITING_USER",
        "intent": "CREATE_OPPORTUNITY",
        "target_type": "customer",
        "target_id": 17,
    }
    assert projection.current_interrupt["task_projection_id"] == 102


def test_projector_clears_owner_when_confirmed_result_has_no_next_task():
    projection = ConfirmedTaskOwnershipProjector().project(
        _result(active_snapshot={}, next_task_id=None),
        expected_task=_executed_task(),
        team_id=2,
        user_id=3,
        session_id=4,
    )

    assert projection.rejected is False
    assert projection.active_task_snapshot == {}
    assert projection.task_projection == {}
    assert projection.current_interrupt is None


def test_projector_fails_closed_when_next_task_owner_does_not_match_session():
    active_snapshot = _active_snapshot()
    active_snapshot["session_id"] = 999

    projection = ConfirmedTaskOwnershipProjector().project(
        _result(active_snapshot=active_snapshot),
        expected_task=_executed_task(),
        team_id=2,
        user_id=3,
        session_id=4,
    )

    assert projection.rejected is True
    assert projection.rejection_event["reason"] == "active_task_owner_mismatch"
    assert projection.active_task_snapshot == {}
    assert projection.current_interrupt is None


def test_projector_refuses_to_rediscover_declared_next_task_without_snapshot():
    projection = ConfirmedTaskOwnershipProjector().project(
        _result(active_snapshot={}),
        expected_task=_executed_task(),
        team_id=2,
        user_id=3,
        session_id=4,
    )

    assert projection.rejected is True
    assert projection.rejection_event["reason"] == "next_task_missing_active_snapshot"
    assert projection.active_task_snapshot == {}
    assert projection.current_interrupt is None

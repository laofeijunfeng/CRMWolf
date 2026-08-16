from types import SimpleNamespace

from app.services.agent.active_task_ownership import (
    ActiveTaskOwnershipCandidate,
    ActiveTaskOwnershipProjector,
)


def _waiting_snapshot(task_id: int) -> dict[str, object]:
    return {
        "id": task_id,
        "task_key": f"task-{task_id}",
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "status": "WAITING_USER",
        "intent": "CREATE_OPPORTUNITY",
        "target_type": "customer",
        "target_id": 17,
        "summary": "等待补充商机信息",
        "state_json": {
            "action": "collect_opportunity_fields",
            "payload": {"customer_id": 17, "missing_fields": ["total_amount"]},
        },
    }


def test_active_task_ownership_projects_persisted_waiting_task_without_db_lookup():
    projector = ActiveTaskOwnershipProjector()
    task = SimpleNamespace(**_waiting_snapshot(102))

    projection = projector.project_task(
        task,
        team_id=2,
        user_id=3,
        session_id=4,
        source="new_flow_waiting_task",
    )

    assert projection.rejection_event is None
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
    assert projection.current_interrupt["task_projection_key"] == "task-102"


def test_active_task_ownership_arbitration_fails_closed_for_two_distinct_active_tasks():
    projector = ActiveTaskOwnershipProjector()
    first = projector.project_snapshot(
        _waiting_snapshot(102),
        team_id=2,
        user_id=3,
        session_id=4,
        source="parallel_branch:act-1",
    )
    second = projector.project_snapshot(
        _waiting_snapshot(103),
        team_id=2,
        user_id=3,
        session_id=4,
        source="parallel_branch:act-2",
    )

    projection = projector.arbitrate(
        [
            ActiveTaskOwnershipCandidate.from_projection(first, source="parallel_branch:act-1"),
            ActiveTaskOwnershipCandidate.from_projection(second, source="parallel_branch:act-2"),
        ],
        team_id=2,
        user_id=3,
        session_id=4,
        source="new_flow_auto_execute",
    )

    assert projection.current_interrupt is None
    assert projection.active_task_snapshot == {}
    assert projection.task_projection == {}
    assert projection.rejection_event == {
        "event": "agent_root_active_task_ownership_rejected",
        "reason": "multiple_active_tasks",
        "source": "new_flow_auto_execute",
        "active_task_ids": [102, 103],
        "candidate_sources": ["parallel_branch:act-1", "parallel_branch:act-2"],
    }

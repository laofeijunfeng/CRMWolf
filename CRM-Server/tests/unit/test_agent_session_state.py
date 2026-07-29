"""Agent session-state snapshot tests."""

from types import SimpleNamespace

from app.models.agent import AgentTaskStatus
from app.services.agent import session_state


def test_pending_task_snapshot_exposes_semantic_selection_fields():
    task = SimpleNamespace(
        id=202,
        status=AgentTaskStatus.SUSPENDED,
        intent="CREATE_OPPORTUNITY",
        target_type="customer",
        target_id=101,
        summary="广州睿狐商机草稿",
        created_time=None,
        updated_time=None,
        state_json={
            "action": "collect_opportunity_fields",
            "missing_fields": ["expected_closing_date", "purchase_type"],
        },
        input_json={
            "payload": {
                "customer": {"id": 101, "account_name": "广州睿狐科技有限公司"},
                "opportunity": {"user_count": 20},
            },
        },
    )

    snapshot = session_state._pending_task_snapshot(task)

    assert snapshot["id"] == 202
    assert snapshot["action"] == "collect_opportunity_fields"
    assert snapshot["customer_name"] == "广州睿狐科技有限公司"
    assert snapshot["missing_fields"] == ["expected_closing_date", "purchase_type"]
    assert snapshot["status"] == AgentTaskStatus.SUSPENDED

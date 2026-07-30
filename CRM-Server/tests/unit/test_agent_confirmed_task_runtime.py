from types import SimpleNamespace

import pytest

from app.services.agent import interactions
from app.services.agent.confirmed_task_runtime import AgentConfirmedTaskRuntime
from app.services.agent.tools.base import AgentToolResult


@pytest.mark.asyncio
async def test_confirmed_task_runtime_clears_completed_task_and_offers_next_task(monkeypatch):
    runtime = AgentConfirmedTaskRuntime()
    db = object()
    session = SimpleNamespace(id=3)
    task = SimpleNamespace(
        id=11,
        state_json={"action": "create_customer_activity"},
    )
    next_task = SimpleNamespace(id=12, state_json={"action": "collect_opportunity_fields"})
    cleared_task_ids = []

    async def fake_execute_waiting_task(db_arg, task_arg, *, session, team_id, user_id, authorization):
        assert db_arg is db
        assert task_arg is task
        assert session.id == 3
        assert team_id == 1
        assert user_id == 2
        assert authorization == "Bearer test"
        return (
            AgentToolResult(
                tool_name="create_customer_activity",
                success=True,
                data={"id": 101},
                tool_call_id=501,
            ),
            "跟进记录已创建。请确认是否执行下一步动作？",
        )

    monkeypatch.setattr(
        "app.services.agent.confirmed_task_runtime.task_execution._execute_waiting_task",
        fake_execute_waiting_task,
    )
    monkeypatch.setattr(
        "app.services.agent.confirmed_task_runtime.session_state._clear_pending_task",
        lambda db_arg, session_arg, task_id: cleared_task_ids.append(task_id),
    )
    monkeypatch.setattr(
        "app.services.agent.confirmed_task_runtime.session_state._get_current_waiting_task",
        lambda db_arg, session_arg, team_id, user_id: next_task,
    )
    monkeypatch.setattr(
        "app.services.agent.confirmed_task_runtime.interactions._should_offer_next_pending_task",
        lambda action: action == "create_customer_activity",
    )
    monkeypatch.setattr(
        "app.services.agent.confirmed_task_runtime.interactions._pending_task_interaction",
        lambda task_arg, content, **kwargs: {"type": "form", "prompt": content, "task_id": task_arg.id},
    )

    result = await runtime.execute(
        db,
        task,
        session=session,
        team_id=1,
        user_id=2,
        authorization="Bearer test",
    )

    assert cleared_task_ids == [11]
    assert result.tool_event
    assert result.tool_event["event"] == "tool_result"
    assert result.tool_event["tool_name"] == "create_customer_activity"
    assert result.tool_event["success"] is True
    assert result.tool_event["data"] == {"id": 101}
    assert result.tool_event["tool_call_id"] == 501
    assert result.task_event == {
        "event": "task_completed",
        "task_id": 11,
        "content": "跟进记录已创建。请确认是否执行下一步动作？",
        "next_task_id": 12,
        "interaction": {
            "type": "form",
            "prompt": "跟进记录已创建。请确认是否执行下一步动作？",
            "task_id": 12,
        },
    }


@pytest.mark.asyncio
async def test_confirmed_task_runtime_returns_failed_task_event(monkeypatch):
    runtime = AgentConfirmedTaskRuntime()
    db = object()
    session = SimpleNamespace(id=3)
    task = SimpleNamespace(id=11, state_json={"action": "unsupported"})
    cleared_task_ids = []

    async def fake_execute_waiting_task(*args, **kwargs):
        return None, "执行失败：暂不支持的执行动作：unsupported"

    monkeypatch.setattr(
        "app.services.agent.confirmed_task_runtime.task_execution._execute_waiting_task",
        fake_execute_waiting_task,
    )
    monkeypatch.setattr(
        "app.services.agent.confirmed_task_runtime.session_state._clear_pending_task",
        lambda db_arg, session_arg, task_id: cleared_task_ids.append(task_id),
    )

    result = await runtime.execute(
        db,
        task,
        session=session,
        team_id=1,
        user_id=2,
        authorization="Bearer test",
    )

    assert cleared_task_ids == []
    assert result.tool_event is None
    assert result.task_event == {
        "event": "task_failed",
        "task_id": 11,
        "content": "执行失败：暂不支持的执行动作：unsupported",
    }


def test_next_opportunity_field_task_uses_form_interaction():
    task = SimpleNamespace(
        id=12,
        task_key="task_12",
        state_json={
            "action": "collect_opportunity_fields",
            "customer": {"id": 101, "account_name": "广州睿狐科技有限公司"},
            "payload": {
                "customer_id": 101,
                "missing_fields": ["total_amount", "license_type", "subscription_years", "procurement_method_id"],
                "interaction_fields": ["total_amount", "license_type", "subscription_years", "procurement_method_id"],
                "field_defaults": {},
            },
        },
    )

    interaction = interactions._pending_task_interaction(
        task,
        "好嘞，跟进已记录。这条还像「新增授权」商机，还差：预计成交金额、授权模式、订阅年限、采购方式。",
    )

    assert interaction["type"] == "form"
    assert interaction["status"] == "waiting_user_input"
    assert interaction["business_action"] == "create_opportunity"
    assert interaction["task_id"] == 12
    assert interaction["task_key"] == "task_12"

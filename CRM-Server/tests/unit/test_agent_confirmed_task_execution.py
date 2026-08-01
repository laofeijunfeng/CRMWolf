from types import SimpleNamespace

import pytest

from app.services.agent import interactions
from app.services.agent.confirmed_task_graph import execute_confirmed_task
from app.services.agent.task_execution import WaitingTaskExecutionResult, _execute_opportunity_stage_move_plan
from app.services.agent.tools.base import AgentToolContext
from app.services.agent.tools.base import AgentToolResult


@pytest.mark.asyncio
async def test_confirmed_task_graph_execute_node_returns_completed_task_result(monkeypatch):
    db = object()
    session = SimpleNamespace(id=3)
    task = SimpleNamespace(
        id=11,
        state_json={"action": "create_customer_activity"},
    )
    next_task = SimpleNamespace(id=12, state_json={"action": "collect_opportunity_fields"})

    async def fake_execute_waiting_task(db_arg, task_arg, *, session, team_id, user_id, authorization, event_sink):
        assert db_arg is db
        assert task_arg is task
        assert session.id == 3
        assert team_id == 1
        assert user_id == 2
        assert authorization == "Bearer test"
        assert event_sink is None
        return WaitingTaskExecutionResult(
            AgentToolResult(
                tool_name="create_customer_activity",
                success=True,
                data={"id": 101},
                tool_call_id=501,
            ),
            "跟进记录已创建。请确认是否执行下一步动作？",
            next_task,
        )

    monkeypatch.setattr(
        "app.services.agent.confirmed_task_graph.task_execution._execute_waiting_task",
        fake_execute_waiting_task,
    )
    result = await execute_confirmed_task(
        db,
        task,
        session=session,
        team_id=1,
        user_id=2,
        authorization="Bearer test",
    )

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
    }
    assert result.next_task is next_task


@pytest.mark.asyncio
async def test_confirmed_task_graph_execute_node_returns_failed_task_event(monkeypatch):
    db = object()
    session = SimpleNamespace(id=3)
    task = SimpleNamespace(id=11, state_json={"action": "unsupported"})

    async def fake_execute_waiting_task(*args, **kwargs):
        return WaitingTaskExecutionResult(None, "执行失败：暂不支持的执行动作：unsupported")

    monkeypatch.setattr(
        "app.services.agent.confirmed_task_graph.task_execution._execute_waiting_task",
        fake_execute_waiting_task,
    )
    result = await execute_confirmed_task(
        db,
        task,
        session=session,
        team_id=1,
        user_id=2,
        authorization="Bearer test",
    )

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


@pytest.mark.asyncio
async def test_stage_move_plan_executes_steps_in_order():
    class FakeRuntime:
        def __init__(self):
            self.calls = []

        async def execute(self, tool_name, context, payload, policy):
            self.calls.append((tool_name, payload, policy.allowed_tool_names))
            return AgentToolResult(
                tool_name=tool_name,
                success=True,
                data={
                    "id": payload["opportunity_id"],
                    "current_stage_snapshot": {
                        "procurement_stage_template_id": payload["stage_template_id"],
                        "stage_name": "签约" if payload["stage_template_id"] == 10 else "方案确认",
                    },
                },
                tool_call_id=500 + len(self.calls),
            )

    runtime = FakeRuntime()
    progress_events = []
    context = AgentToolContext(
        db=object(),
        team_id=1,
        user_id=2,
        session_id=3,
        authorization="Bearer test",
        confirmed_by_user=True,
    )

    result = await _execute_opportunity_stage_move_plan(
        runtime,
        context,
        {
            "customer_id": 101,
            "opportunity_id": 301,
            "stage_template_id": 10,
            "target_stage_name": "签约",
            "stage_move_steps": [
                {"stage_template_id": 9, "stage_name": "方案确认"},
                {"stage_template_id": 10, "stage_name": "签约"},
            ],
        },
        "task_11",
        progress_events=progress_events,
        event_sink=None,
    )

    assert result.success is True
    assert [call[1]["stage_template_id"] for call in runtime.calls] == [9, 10]
    assert [call[1]["idempotency_suffix"] for call in runtime.calls] == ["task_11:stage:1", "task_11:stage:2"]
    assert result.data["current_stage_snapshot"]["stage_name"] == "签约"
    assert result.data["stage_move_steps"] == [
        {"stage_template_id": 9, "stage_name": "方案确认", "tool_call_id": 501},
        {"stage_template_id": 10, "stage_name": "签约", "tool_call_id": 502},
    ]
    assert progress_events == [
        {"event": "agent_step", "step": "opportunity_stage_move_1", "status": "started", "content": "推进到「方案确认」"},
        {"event": "agent_step", "step": "opportunity_stage_move_1", "status": "completed", "content": "推进到「方案确认」"},
        {"event": "agent_step", "step": "opportunity_stage_move_2", "status": "started", "content": "推进到「签约」"},
        {"event": "agent_step", "step": "opportunity_stage_move_2", "status": "completed", "content": "推进到「签约」"},
    ]


@pytest.mark.asyncio
async def test_stage_move_plan_streams_each_stage_step():
    class FakeRuntime:
        async def execute(self, tool_name, context, payload, policy):
            return AgentToolResult(
                tool_name=tool_name,
                success=True,
                data={"current_stage_snapshot": {"stage_name": "产品试用"}},
            )

    streamed_events = []

    async def event_sink(event):
        streamed_events.append(event)

    progress_events = []
    context = AgentToolContext(
        db=object(),
        team_id=1,
        user_id=2,
        session_id=3,
        authorization="Bearer test",
        confirmed_by_user=True,
    )

    await _execute_opportunity_stage_move_plan(
        FakeRuntime(),
        context,
        {
            "customer_id": 101,
            "opportunity_id": 301,
            "stage_move_steps": [
                {"stage_template_id": 9, "stage_name": "方案交流"},
                {"stage_template_id": 10, "stage_name": "产品试用"},
            ],
        },
        "task_11",
        progress_events=progress_events,
        event_sink=event_sink,
    )

    assert streamed_events == progress_events
    assert [event["content"] for event in streamed_events] == [
        "推进到「方案交流」",
        "推进到「方案交流」",
        "推进到「产品试用」",
        "推进到「产品试用」",
    ]

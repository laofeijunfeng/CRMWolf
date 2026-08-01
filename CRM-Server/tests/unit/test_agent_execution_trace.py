"""Execution trace projection tests."""
from __future__ import annotations

from types import SimpleNamespace

from app.services.agent.execution_trace import (
    confirmed_task_execution_events,
    pending_task_step_completed,
    pending_task_step_started,
)


def test_confirmed_task_execution_events_use_business_labels():
    task = SimpleNamespace(state_json={"action": "create_customer_activity"})

    events = confirmed_task_execution_events(
        task=task,
        graph_events=[
            {"event": "confirmed_task_graph_started"},
            {"event": "confirmed_task_execution_completed", "task_event": "task_completed"},
            {"event": "confirmed_task_effects_applied"},
            {"event": "confirmed_task_graph_finished"},
        ],
        output_events=[
            {"event": "tool_result", "tool_name": "create_customer_activity", "success": True},
            {"event": "task_completed", "content": "客户活动已记录。"},
            {"event": "final", "content": "客户活动已记录。"},
        ],
    )

    assert events[:8] == [
        {"event": "agent_step", "step": "confirmed_task_prepare", "status": "started", "content": "读取待确认任务"},
        {"event": "agent_step", "step": "confirmed_task_prepare", "status": "completed", "content": "读取待确认任务"},
        {"event": "agent_step", "step": "confirmed_task_execute", "status": "started", "content": "执行记录跟进"},
        {"event": "agent_step", "step": "confirmed_task_execute", "status": "completed", "content": "执行记录跟进"},
        {"event": "agent_step", "step": "confirmed_task_effects", "status": "started", "content": "同步业务状态"},
        {"event": "agent_step", "step": "confirmed_task_effects", "status": "completed", "content": "同步业务状态"},
        {"event": "agent_step", "step": "confirmed_task_finish", "status": "started", "content": "整理执行结果"},
        {"event": "agent_step", "step": "confirmed_task_finish", "status": "completed", "content": "整理执行结果"},
    ]
    assert events[8] == {
        "event": "tool_result",
        "tool_name": "create_customer_activity",
        "success": True,
        "content": "记录跟进已执行",
    }
    assert "create_customer_activity" not in str([event.get("content") for event in events])


def test_confirmed_task_execution_events_expand_multi_stage_move_steps():
    task = SimpleNamespace(state_json={"action": "move_opportunity_stage"})

    events = confirmed_task_execution_events(
        task=task,
        graph_events=[
            {"event": "confirmed_task_graph_started"},
            {"event": "confirmed_task_execution_completed", "task_event": "task_completed"},
        ],
        output_events=[
            {
                "event": "tool_result",
                "tool_name": "move_opportunity_stage",
                "success": True,
                "data": {
                    "stage_move_steps": [
                        {"stage_template_id": 8, "stage_name": "方案交流"},
                        {"stage_template_id": 9, "stage_name": "产品试用"},
                    ],
                },
            },
            {"event": "task_completed", "content": "商机阶段已推进到「产品试用」。"},
        ],
    )

    stage_events = [
        event
        for event in events
        if isinstance(event.get("step"), str) and event["step"].startswith("opportunity_stage_move_")
    ]
    assert stage_events == [
        {"event": "agent_step", "step": "opportunity_stage_move_1", "status": "started", "content": "推进到「方案交流」"},
        {"event": "agent_step", "step": "opportunity_stage_move_1", "status": "completed", "content": "推进到「方案交流」"},
        {"event": "agent_step", "step": "opportunity_stage_move_2", "status": "started", "content": "推进到「产品试用」"},
        {"event": "agent_step", "step": "opportunity_stage_move_2", "status": "completed", "content": "推进到「产品试用」"},
    ]
    assert events[-2]["content"] == "推进商机阶段已执行"


def test_confirmed_task_execution_events_do_not_duplicate_streamed_stage_move_steps():
    task = SimpleNamespace(state_json={"action": "move_opportunity_stage"})

    events = confirmed_task_execution_events(
        task=task,
        graph_events=[
            {"event": "confirmed_task_graph_started"},
            {"event": "agent_step", "step": "opportunity_stage_move_1", "status": "started", "content": "推进到「方案交流」"},
            {"event": "agent_step", "step": "opportunity_stage_move_1", "status": "completed", "content": "推进到「方案交流」"},
            {"event": "agent_step", "step": "opportunity_stage_move_2", "status": "started", "content": "推进到「产品试用」"},
            {"event": "agent_step", "step": "opportunity_stage_move_2", "status": "completed", "content": "推进到「产品试用」"},
            {"event": "confirmed_task_execution_completed", "task_event": "task_completed"},
        ],
        output_events=[
            {
                "event": "tool_result",
                "tool_name": "move_opportunity_stage",
                "success": True,
                "data": {
                    "stage_move_steps": [
                        {"stage_template_id": 8, "stage_name": "方案交流"},
                        {"stage_template_id": 9, "stage_name": "产品试用"},
                    ],
                },
            },
            {"event": "task_completed", "content": "商机阶段已推进到「产品试用」。"},
        ],
        include_graph_progress_events=False,
    )

    stage_events = [
        event
        for event in events
        if isinstance(event.get("step"), str) and event["step"].startswith("opportunity_stage_move_")
    ]
    assert stage_events == []
    assert events[-2]["content"] == "推进商机阶段已执行"


def test_pending_task_step_events_use_business_labels():
    assert pending_task_step_started("preflight") == {
        "event": "agent_step",
        "step": "preflight",
        "status": "started",
        "content": "识别确认或取消意图",
    }
    assert pending_task_step_completed("plan_interaction") == {
        "event": "agent_step",
        "step": "plan_interaction",
        "status": "completed",
        "content": "整理需要确认或补充的信息",
    }
    assert pending_task_step_started("internal_unknown_node") is None

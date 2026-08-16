from types import SimpleNamespace

from app.services.agent.confirmed_task_effects import (
    ConfirmedTaskSideEffectContext,
    confirmed_task_side_effect_handler,
)
from app.services.agent.state import ConfirmedTaskExecutionResult


def test_confirmed_task_effects_clear_completed_task_and_offer_next(monkeypatch):
    db = object()
    session = SimpleNamespace(id=3)
    task = SimpleNamespace(
        id=11,
        task_key="task-11",
        team_id=1,
        user_id=2,
        session_id=3,
        status="COMPLETED",
        state_json={"action": "create_customer_activity"},
    )
    next_task = SimpleNamespace(
        id=12,
        task_key="task-12",
        team_id=1,
        user_id=2,
        session_id=3,
        status="WAITING_USER",
        state_json={"action": "collect_opportunity_fields"},
    )
    monkeypatch.setattr(
        "app.services.agent.confirmed_task_effects.interactions._should_offer_next_pending_task",
        lambda action: action == "create_customer_activity",
    )
    monkeypatch.setattr(
        "app.services.agent.confirmed_task_effects.interactions._pending_task_interaction",
        lambda task_arg, content, **kwargs: {"type": "form", "prompt": content, "task_id": task_arg.id},
    )

    result = confirmed_task_side_effect_handler.apply(
        ConfirmedTaskSideEffectContext(
            db=db,
            session=session,
            task=task,
            team_id=1,
            user_id=2,
            execution=ConfirmedTaskExecutionResult(
                tool_event={"event": "tool_result", "tool_name": "create_customer_activity", "success": True},
                task_event={"event": "task_completed", "task_id": 11, "content": "跟进记录已创建。"},
                assistant_content="跟进记录已创建。",
                next_task=next_task,
            ),
        )
    )

    assert result.task_event == {
        "event": "task_completed",
        "task_id": 11,
        "content": "跟进记录已创建。",
        "next_task_id": 12,
        "interaction": {
            "type": "form",
            "prompt": "跟进记录已创建。",
            "task_id": 12,
        },
    }
    assert result.output_events == [
        {"event": "tool_result", "tool_name": "create_customer_activity", "success": True},
        result.task_event,
        {"event": "final", "content": "跟进记录已创建。"},
    ]
    assert result.executed_task_snapshot["id"] == 11
    assert result.executed_task_snapshot["status"] == "COMPLETED"
    assert result.active_task_snapshot["id"] == 12
    assert result.active_task_snapshot["status"] == "WAITING_USER"


def test_confirmed_task_effects_do_not_clear_failed_task(monkeypatch):
    db = object()
    session = SimpleNamespace(id=3)
    task = SimpleNamespace(
        id=11,
        task_key="task-11",
        team_id=1,
        user_id=2,
        session_id=3,
        status="FAILED",
        state_json={"action": "unsupported"},
    )

    result = confirmed_task_side_effect_handler.apply(
        ConfirmedTaskSideEffectContext(
            db=db,
            session=session,
            task=task,
            team_id=1,
            user_id=2,
            execution=ConfirmedTaskExecutionResult(
                tool_event=None,
                task_event={"event": "task_failed", "task_id": 11, "content": "执行失败"},
                assistant_content="执行失败",
            ),
        )
    )

    assert result.output_events == [
        {"event": "task_failed", "task_id": 11, "content": "执行失败"},
        {"event": "final", "content": "执行失败"},
    ]
    assert result.executed_task_snapshot["id"] == 11
    assert result.active_task_snapshot == {}



def test_confirmed_task_effects_leave_post_commit_confirmation_for_root_runtime():
    db = object()
    session = SimpleNamespace(id=3)
    task = SimpleNamespace(
        id=11,
        task_key="task-11",
        team_id=1,
        user_id=2,
        session_id=3,
        status="COMPLETED",
        state_json={"action": "create_customer_activity"},
    )
    tool_event = {
        "event": "tool_result",
        "tool_name": "create_customer_activity",
        "success": True,
        "data": {
            "id": 190,
            "post_commit": {
                "needs_user_confirmation": True,
                "confirmation_case_public_ids": ["fuc_11111111111111111111111111111111"],
            },
        },
    }

    result = confirmed_task_side_effect_handler.apply(
        ConfirmedTaskSideEffectContext(
            db=db,
            session=session,
            task=task,
            team_id=1,
            user_id=2,
            execution=ConfirmedTaskExecutionResult(
                tool_event=tool_event,
                task_event={"event": "task_completed", "task_id": 11, "content": "跟进记录已创建。"},
                assistant_content="跟进记录已创建。",
            ),
        )
    )

    assert result.output_events == [
        tool_event,
        {"event": "task_completed", "task_id": 11, "content": "跟进记录已创建。"},
        {"event": "final", "content": "跟进记录已创建。"},
    ]
    assert result.assistant_content == "跟进记录已创建。"
    assert result.executed_task_snapshot["id"] == 11
    assert result.active_task_snapshot == {}

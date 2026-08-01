from types import SimpleNamespace

from app.services.agent.confirmed_task_effects import (
    ConfirmedTaskSideEffectContext,
    confirmed_task_side_effect_handler,
)
from app.services.agent.state import ConfirmedTaskExecutionResult


def test_confirmed_task_effects_clear_completed_task_and_offer_next(monkeypatch):
    db = object()
    session = SimpleNamespace(id=3)
    task = SimpleNamespace(id=11, state_json={"action": "create_customer_activity"})
    next_task = SimpleNamespace(id=12, state_json={"action": "collect_opportunity_fields"})
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


def test_confirmed_task_effects_do_not_clear_failed_task(monkeypatch):
    db = object()
    session = SimpleNamespace(id=3)
    task = SimpleNamespace(id=11, state_json={"action": "unsupported"})

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

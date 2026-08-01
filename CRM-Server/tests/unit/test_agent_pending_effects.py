from types import SimpleNamespace

from app.services.agent.pending_effects import PendingTaskSideEffectContext, PendingTaskSideEffectHandler
from app.services.agent.state import PendingTaskGraphSideEffects


def test_pending_task_side_effect_handler_applies_session_effects(monkeypatch):
    handler = PendingTaskSideEffectHandler()
    db = object()
    session = SimpleNamespace(id=3)
    task = SimpleNamespace(id=11)
    suspended_task = SimpleNamespace(id=12)
    suspended = []
    remembered_customers = []

    monkeypatch.setattr(
        "app.services.agent.pending_effects.session_state._suspend_pending_task",
        lambda db_arg, session_arg, task_arg, reason: suspended.append((task_arg, reason)),
    )
    monkeypatch.setattr(
        "app.services.agent.pending_effects.session_state._remember_current_customer",
        lambda db_arg, session_arg, customer: remembered_customers.append(customer),
    )
    result = handler.apply(
        {
            "has_active_task": True,
            "task_projection": {"id": 11},
            "handled": True,
            "suspended_task_id": 12,
            "suspend_reason": "新客户流程",
            "selected_customer": {"id": 101, "account_name": "越秀金融"},
            "remember_pending_task": True,
            "assistant_content": "请确认是否创建商机？",
            "switch_notice": "切换处理新流程。",
            "events": [{"event": "confirmation_required"}, {"event": "final"}],
        },
        PendingTaskSideEffectContext(
            db=db,
            session=session,
            graph_side_effects=PendingTaskGraphSideEffects(task=task, suspended_task=suspended_task),
        ),
    )

    assert suspended == [(suspended_task, "新客户流程")]
    assert remembered_customers == [{"id": 101, "account_name": "越秀金融"}]
    assert result.task is task
    assert result.events[0]["event"] == "confirmation_required"
    assert isinstance(result.events[0]["interaction"], dict)
    assert result.events[1] == {"event": "final"}
    assert result.assistant_content == "请确认是否创建商机？"
    assert result.switch_notice == "切换处理新流程。"
    assert result.current_interrupt is not None
    assert result.current_interrupt["type"] == "confirm"
    assert result.current_interrupt["reason"] == "write_confirmation"
    assert result.current_interrupt["allowed_resume_actions"] == ["approve", "edit", "reject", "cancel"]
    assert result.current_interrupt["source_event"] == "confirmation_required"


def test_pending_task_side_effect_handler_does_not_restore_cleared_task(monkeypatch):
    handler = PendingTaskSideEffectHandler()
    task = SimpleNamespace(id=11)
    suspended = []

    monkeypatch.setattr(
        "app.services.agent.pending_effects.session_state._suspend_pending_task",
        lambda db_arg, session_arg, task_arg, reason: suspended.append((task_arg, reason)),
    )

    result = handler.apply(
        {
            "has_active_task": False,
            "handled": True,
            "suspended_task_id": 11,
            "suspend_reason": "用户选择先不处理。",
            "clear_pending_task_id": 11,
            "assistant_content": "好嘞，这一步先放着。",
            "events": [{"event": "task_cancelled"}, {"event": "final"}],
        },
        PendingTaskSideEffectContext(
            db=object(),
            session=SimpleNamespace(id=3),
            graph_side_effects=PendingTaskGraphSideEffects(task=task, suspended_task=task),
        ),
    )

    assert suspended == [(task, "用户选择先不处理。")]
    assert result.task is None
    assert result.current_interrupt is None

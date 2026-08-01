from types import SimpleNamespace

from app.services.agent.new_flow_effects import NewFlowSideEffectContext, NewFlowSideEffectHandler


def test_new_flow_side_effect_handler_applies_waiting_memory_and_final_notice(monkeypatch):
    handler = NewFlowSideEffectHandler()
    db = object()
    session = SimpleNamespace(id=3)
    remembered_customers = []
    waiting_events = []

    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.session_state._remember_current_customer",
        lambda db_arg, session_arg, customer: remembered_customers.append(customer),
    )
    def create_waiting_task(db_arg, event, team_id, user_id, session_arg):
        event["task_id"] = 501
        event["task_key"] = "task-501"
        waiting_events.append(event)
        return SimpleNamespace(id=501, task_key="task-501")

    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.task_factory._create_waiting_task_from_event",
        create_waiting_task,
    )
    context = NewFlowSideEffectContext(
        db=db,
        session=session,
        team_id=1,
        user_id=2,
        switch_notice="我先切到新流程处理。",
    )

    handler.apply(
        {
            "event": "business_context_loaded",
            "customer": {"id": 101, "account_name": "越秀金融"},
        },
        context,
    )
    handler.apply(
        {
            "event": "confirmation_required",
            "action": "create_customer_activity",
            "payload": {"customer_id": 101, "content": "已沟通项目进展"},
            "content": "请确认是否创建这条跟进记录？",
        },
        context,
    )
    final_event = handler.apply({"event": "final", "content": "已处理"}, context)

    assert remembered_customers == [{"id": 101, "account_name": "越秀金融"}]
    assert waiting_events[0]["event"] == "confirmation_required"
    assert context.current_interrupt is not None
    assert context.current_interrupt["type"] == "confirm"
    assert context.current_interrupt["reason"] == "write_confirmation"
    assert context.current_interrupt["allowed_resume_actions"] == ["approve", "edit", "reject", "cancel"]
    assert context.current_interrupt["task_projection_id"] == 501
    assert context.current_interrupt["task_projection_key"] == "task-501"
    assert final_event == {"event": "final", "content": "我先切到新流程处理。\n\n已处理"}
    assert context.assistant_content == "我先切到新流程处理。\n\n已处理"

from types import SimpleNamespace

import pytest

from app.services.agent import action_workflow
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
        return SimpleNamespace(
            id=501,
            task_key="task-501",
            team_id=team_id,
            user_id=user_id,
            session_id=session_arg.id,
            status="WAITING_USER",
            intent="CUSTOMER_ACTIVITY",
            target_type="customer",
            target_id=101,
            summary="请确认是否创建这条跟进记录？",
            state_json={
                "action": event["action"],
                "payload": event["payload"],
            },
        )

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
    assert context.active_task_snapshot["id"] == 501
    assert context.active_task_snapshot["team_id"] == 1
    assert context.active_task_snapshot["user_id"] == 2
    assert context.active_task_snapshot["session_id"] == 3
    assert context.ownership_rejection_event is None
    assert final_event == {"event": "final", "content": "我先切到新流程处理。\n\n已处理"}
    assert context.assistant_content == "我先切到新流程处理。\n\n已处理"


@pytest.mark.asyncio
async def test_new_flow_side_effect_handler_queues_direct_action_level_auto_execute_item(monkeypatch):
    class FakeActionReviewGraphService:
        async def run(self, input_state):
            return {
                "decision": "auto_execute",
                "risk_level": "low",
                "execution_confidence": 0.96,
                "reason": "明确低风险跟进记录。",
                "events": [],
            }

    created_tasks = []

    def create_waiting_task(db_arg, event, team_id, user_id, session_arg):
        created_tasks.append(event)
        return SimpleNamespace(id=501, task_key="task-501", target_type="customer", target_id=101)

    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.task_factory._create_waiting_task_from_event",
        create_waiting_task,
    )
    handler = NewFlowSideEffectHandler(action_review_graph_service=FakeActionReviewGraphService())
    workflow = action_workflow.required_write_contract(action="create_customer_activity")
    context = NewFlowSideEffectContext(
        db=object(),
        session=SimpleNamespace(id=3),
        team_id=1,
        user_id=2,
    )

    event = await handler.apply_async(
        {
            "event": "confirmation_required",
            "action": "create_customer_activity",
            "workflow": workflow,
            "payload": {"customer_id": 101, "content": "今天拜访客户"},
            "content": "请确认是否创建这条跟进记录？",
        },
        context,
    )

    assert event["event"] == "action_auto_execution_queued"
    assert created_tasks == []
    assert context.auto_execute_tasks is None
    assert context.auto_execute_actions is not None
    assert len(context.auto_execute_actions) == 1
    [action_item] = context.auto_execute_actions
    assert action_item.action_id == workflow["action_id"]
    assert action_item.action_type == "create_customer_activity"
    assert action_item.payload["customer_id"] == 101
    assert action_item.payload["content"] == "今天拜访客户"
    assert action_item.workflow["status"] == action_workflow.STATUS_PLANNED
    assert action_item.workflow["policy"]["execution_policy"] == action_workflow.EXECUTION_AUTO_EXECUTE
    assert action_item.payload["workflow"]["policy"]["execution_policy"] == action_workflow.EXECUTION_AUTO_EXECUTE
    assert action_item.task_id is None
    assert action_item.target_type == "customer"
    assert action_item.target_id == 101


@pytest.mark.asyncio
async def test_new_flow_side_effect_handler_keeps_task_projection_when_auto_execute_action_needs_follow_up_projection(monkeypatch):
    class FakeActionReviewGraphService:
        async def run(self, input_state):
            return {
                "decision": "auto_execute",
                "risk_level": "low",
                "execution_confidence": 0.96,
                "reason": "明确低风险跟进记录，但后续动作需要任务投影承接。",
                "events": [],
            }

    created_tasks = []

    def create_waiting_task(db_arg, event, team_id, user_id, session_arg):
        created_tasks.append(event)
        return SimpleNamespace(
            id=501,
            task_key="task-501",
            target_type="customer",
            target_id=101,
        )

    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.task_factory._create_waiting_task_from_event",
        create_waiting_task,
    )
    handler = NewFlowSideEffectHandler(action_review_graph_service=FakeActionReviewGraphService())
    workflow = action_workflow.required_write_contract(action="create_customer_activity")
    context = NewFlowSideEffectContext(
        db=object(),
        session=SimpleNamespace(id=3),
        team_id=1,
        user_id=2,
    )

    event = await handler.apply_async(
        {
            "event": "confirmation_required",
            "action": "create_customer_activity",
            "workflow": workflow,
            "payload": {
                "customer_id": 101,
                "content": "今天拜访客户",
                "_next_task": {
                    "action": "transition_follow_up_task",
                    "payload": {"task_id": "fut_1", "transition_action": "complete"},
                },
            },
            "content": "请确认是否创建这条跟进记录？",
        },
        context,
    )

    assert event["event"] == "action_auto_execution_queued"
    assert len(created_tasks) == 1
    assert context.auto_execute_tasks is not None
    assert len(context.auto_execute_tasks) == 1
    assert context.auto_execute_actions is not None
    [action_item] = context.auto_execute_actions
    assert action_item.task_id == 501
    assert action_item.target_type == "customer"
    assert action_item.target_id == 101

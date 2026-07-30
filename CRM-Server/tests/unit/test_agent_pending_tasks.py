"""CRM AI Agent pending task interaction planner tests."""

from types import SimpleNamespace

import pytest

from app.models.agent import AgentTaskStatus
from app.services.agent import pending_tasks
from app.services.agent.pending_tasks import PendingTaskInteractionPlanner, PendingTaskPreflightPlanner
from app.services.agent.input import AgentTurnInput
from app.services.agent.schemas import AgentConfirmationIntentDecision, AgentPendingInterruptionDecision


def _task(*, action: str, status: str = AgentTaskStatus.WAITING_USER):
    return SimpleNamespace(
        id=101,
        status=status,
        intent="CUSTOMER_ACTIVITY",
        target_type="customer",
        target_id=201,
        summary="创建客户跟进",
        input_json={"payload": "current"},
        state_json={"action": action},
    )


@pytest.mark.asyncio
async def test_pending_task_planner_turns_completed_field_collection_into_confirmation(monkeypatch):
    task = _task(action="collect_opportunity_fields")

    async def fake_apply(db, task_arg, content):
        assert task_arg is task
        assert content == "补充 100 人"
        return True, "商机信息已补齐。请确认是否创建商机？"

    monkeypatch.setattr(pending_tasks.opportunity_fields, "_apply_opportunity_fields", fake_apply)

    result = await PendingTaskInteractionPlanner().plan(
        db=None,
        task=task,
        content="补充 100 人",
        team_id=1,
        user_id=2,
        session_id=3,
        authorization="Bearer test",
    )

    assert result.handled is True
    assert result.remember_pending_task is True
    assert result.assistant_content == "商机信息已补齐。请确认是否创建商机？"
    assert result.events == [
        {
            "event": "confirmation_required",
            "task_id": 101,
            "content": "商机信息已补齐。请确认是否创建商机？",
            "payload": {"payload": "current"},
        },
        {"event": "final", "content": "商机信息已补齐。请确认是否创建商机？"},
    ]


@pytest.mark.asyncio
async def test_pending_task_planner_reports_business_selection(monkeypatch):
    task = _task(action="select_contract_for_payment_plan")

    monkeypatch.setattr(
        pending_tasks.selection,
        "_apply_business_selection",
        lambda db, task_arg, content: (False, "没有匹配到合同，请输入序号。"),
    )

    result = await PendingTaskInteractionPlanner().plan(
        db=None,
        task=task,
        content="合同 A",
        team_id=1,
        user_id=2,
        session_id=3,
        authorization="Bearer test",
    )

    assert result.handled is True
    assert result.remember_pending_task is True
    assert result.events[0] == {
        "event": "business_selection_failed",
        "task_id": 101,
        "content": "没有匹配到合同，请输入序号。",
        "selected": False,
    }


@pytest.mark.asyncio
async def test_pending_task_planner_returns_customer_memory_instruction(monkeypatch):
    task = _task(action="select_customer_for_activity", status=AgentTaskStatus.COMPLETED)
    selected_customer = {"id": 201, "account_name": "越秀金融"}

    async def fake_apply(db, task_arg, content, *, team_id, user_id, session_id, authorization):
        assert (team_id, user_id, session_id, authorization) == (1, 2, 3, "Bearer test")
        return selected_customer, "已选择越秀金融。请确认是否创建跟进？"

    monkeypatch.setattr(pending_tasks.selection, "_apply_customer_selection", fake_apply)

    result = await PendingTaskInteractionPlanner().plan(
        db=None,
        task=task,
        content="1",
        team_id=1,
        user_id=2,
        session_id=3,
        authorization="Bearer test",
    )

    assert result.handled is True
    assert result.selected_customer == selected_customer
    assert result.remember_pending_task is False
    assert result.clear_pending_task_id == 101
    assert result.events[0] == {
        "event": "customer_selected",
        "task_id": 101,
        "customer": selected_customer,
        "content": "已选择越秀金融。请确认是否创建跟进？",
    }


@pytest.mark.asyncio
async def test_pending_task_preflight_routes_high_confidence_new_flow(monkeypatch):
    task = _task(action="collect_opportunity_fields")
    session = SimpleNamespace(context_json={})

    monkeypatch.setattr(
        pending_tasks.agent_confirmation_intent_service,
        "is_executable_confirmation_task",
        lambda task_arg: False,
    )

    async def fake_assess(db, *, team_id, session, task, user_message):
        return AgentPendingInterruptionDecision(
            decision="START_NEW_FLOW",
            confidence=0.92,
            detected_customer_name="汇川技术",
            detected_intent="CUSTOMER_ACTIVITY",
            is_field_supplement=False,
            reason="明确提到另一个客户的新跟进。",
        )

    monkeypatch.setattr(pending_tasks.session_state, "_assess_pending_interruption", fake_assess)

    result = await PendingTaskPreflightPlanner().plan(
        db=None,
        session=session,
        task=task,
        turn_input=AgentTurnInput.text("今天跟进了汇川技术"),
        team_id=1,
    )

    assert result.handled is False
    assert result.task is None
    assert result.suspended_task is task
    assert result.suspend_reason == "明确提到另一个客户的新跟进。"
    assert result.switch_notice == "这条是在说「汇川技术」。我先把刚才那一步放着，切过来处理。"
    assert result.events[0]["event"] == "pending_interruption_assessed"
    assert result.events[1] == {
        "event": "pending_task_interrupted",
        "content": result.switch_notice,
        "suspended_task_id": 101,
    }


@pytest.mark.asyncio
async def test_pending_task_preflight_keeps_unknown_executable_reply_in_confirmation(monkeypatch):
    task = _task(action="create_customer_activity")
    session = SimpleNamespace(context_json={})

    monkeypatch.setattr(
        pending_tasks.agent_confirmation_intent_service,
        "is_executable_confirmation_task",
        lambda task_arg: True,
    )

    async def fake_confirm(db, *, team_id, turn_input, task, memory=None):
        return AgentConfirmationIntentDecision(intent="unknown", confidence=0.2, reason="不是明确确认")

    async def fake_assess(db, *, team_id, session, task, user_message):
        return AgentPendingInterruptionDecision(
            decision="CONTINUE_PENDING",
            confidence=0.8,
            reason="仍在当前确认上下文。",
            is_field_supplement=True,
        )

    monkeypatch.setattr(pending_tasks.agent_confirmation_intent_service, "assess", fake_confirm)
    monkeypatch.setattr(pending_tasks.session_state, "_assess_pending_interruption", fake_assess)

    result = await PendingTaskPreflightPlanner().plan(
        db=None,
        session=session,
        task=task,
        turn_input=AgentTurnInput.text("这个客户挺重要"),
        team_id=1,
    )

    assert result.handled is True
    assert result.task is task
    assert result.assistant_content == "你是要确认执行，还是先取消？也可以直接说新的需求。"
    assert [event["event"] for event in result.events] == [
        "confirmation_intent_assessed",
        "pending_interruption_assessed",
        "confirmation_intent_unknown",
        "final",
    ]


@pytest.mark.asyncio
async def test_pending_task_preflight_allows_confirmed_executable_task(monkeypatch):
    task = _task(action="create_customer_activity")
    session = SimpleNamespace(context_json={})

    monkeypatch.setattr(
        pending_tasks.agent_confirmation_intent_service,
        "is_executable_confirmation_task",
        lambda task_arg: True,
    )

    async def fake_confirm(db, *, team_id, turn_input, task, memory=None):
        return AgentConfirmationIntentDecision(intent="confirm", confidence=1.0, reason="明确确认")

    monkeypatch.setattr(pending_tasks.agent_confirmation_intent_service, "assess", fake_confirm)

    result = await PendingTaskPreflightPlanner().plan(
        db=None,
        session=session,
        task=task,
        turn_input=AgentTurnInput.text("确认"),
        team_id=1,
    )

    assert result.handled is False
    assert result.task is task
    assert result.confirmation_decision.intent == "confirm"
    assert result.events == [
        {
            "event": "confirmation_intent_assessed",
            "task_id": 101,
            "intent": "confirm",
            "confidence": 1.0,
            "reason": "明确确认",
        }
    ]

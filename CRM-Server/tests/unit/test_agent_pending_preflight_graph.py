from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.services.agent import pending_preflight_graph as preflight_module
from app.services.agent.input import AgentTurnInput
from app.services.agent.pending_preflight_graph import (
    PendingPreflightGraphService,
    build_pending_preflight_graph_config,
)
from app.services.agent.schemas import AgentConfirmationIntentDecision, AgentPendingInterruptionDecision


def _task(action: str = "create_customer_activity"):
    return SimpleNamespace(
        id=21,
        task_key="task-21",
        status="WAITING_USER",
        intent="CREATE_FOLLOW_UP",
        target_type="customer",
        target_id=7,
        state_json={"action": action},
    )


@pytest.mark.asyncio
async def test_pending_preflight_graph_checkpoints_confirmed_executable_task(monkeypatch):
    task = _task()
    service = PendingPreflightGraphService(checkpointer=InMemorySaver())

    monkeypatch.setattr(
        preflight_module.agent_confirmation_intent_service,
        "is_executable_confirmation_task",
        lambda task_arg: True,
    )

    async def fake_assess(*args, **kwargs):
        return AgentConfirmationIntentDecision(intent="confirm", confidence=0.96, reason="用户明确确认")

    monkeypatch.setattr(preflight_module.agent_confirmation_intent_service, "assess", fake_assess)
    monkeypatch.setattr(
        preflight_module.session_state,
        "_memory_snapshot_for_session",
        lambda session, task_arg: SimpleNamespace(),
    )

    result = await service.run({
        "db": object(),
        "session": SimpleNamespace(id=3),
        "task": task,
        "turn_input": AgentTurnInput.confirm(),
        "team_id": 1,
        "session_id": 3,
        "events": [],
    })
    snapshot = await service._graph.aget_state(build_pending_preflight_graph_config(
        team_id=1,
        session_id=3,
        task_id=21,
    ))

    assert result.task is task
    assert result.handled is False
    assert result.confirmation_decision.intent == "confirm"
    assert snapshot.values["confirmation_decision"]["intent"] == "confirm"
    assert snapshot.values["task_projection"]["id"] == 21


@pytest.mark.asyncio
async def test_pending_preflight_graph_suspends_for_high_confidence_new_flow(monkeypatch):
    task = _task(action="collect_customer_activity_fields")
    service = PendingPreflightGraphService()

    monkeypatch.setattr(
        preflight_module.agent_confirmation_intent_service,
        "is_executable_confirmation_task",
        lambda task_arg: False,
    )
    monkeypatch.setattr(preflight_module.session_state, "_is_rejection", lambda content: False)

    async def fake_assess_interruption(*args, **kwargs):
        return AgentPendingInterruptionDecision(
            decision="START_NEW_FLOW",
            confidence=0.93,
            detected_customer_name="xxx 公司",
            detected_intent="CREATE_CUSTOMER",
            reason="用户明确开启新客户流程",
        )

    monkeypatch.setattr(preflight_module.session_state, "_assess_pending_interruption", fake_assess_interruption)
    monkeypatch.setattr(preflight_module.session_state, "_is_high_confidence_new_flow", lambda decision: True)
    monkeypatch.setattr(preflight_module.session_state, "_is_ambiguous_pending_interruption", lambda decision: False)
    monkeypatch.setattr(
        preflight_module.agent_copy,
        "pending_switch_notice",
        lambda customer_name: f"先处理 {customer_name} 的新流程。",
    )

    result = await service.run({
        "db": object(),
        "session": SimpleNamespace(id=3),
        "task": task,
        "turn_input": AgentTurnInput.text("xxx 公司要新建客户"),
        "team_id": 1,
        "session_id": 3,
        "events": [],
    })

    assert result.task is None
    assert result.suspended_task is task
    assert result.switch_notice == "先处理 xxx 公司 的新流程。"
    assert result.events[-1]["event"] == "pending_task_interrupted"


@pytest.mark.asyncio
async def test_pending_preflight_graph_keeps_unknown_executable_reply_in_confirmation(monkeypatch):
    task = _task()
    service = PendingPreflightGraphService()

    monkeypatch.setattr(
        preflight_module.agent_confirmation_intent_service,
        "is_executable_confirmation_task",
        lambda task_arg: True,
    )

    async def fake_confirm(*args, **kwargs):
        return AgentConfirmationIntentDecision(intent="unknown", confidence=0.2, reason="不是明确确认")

    async def fake_assess_interruption(*args, **kwargs):
        return AgentPendingInterruptionDecision(
            decision="CONTINUE_PENDING",
            confidence=0.8,
            reason="仍在当前确认上下文。",
            is_field_supplement=True,
        )

    monkeypatch.setattr(preflight_module.agent_confirmation_intent_service, "assess", fake_confirm)
    monkeypatch.setattr(
        preflight_module.session_state,
        "_memory_snapshot_for_session",
        lambda session, task_arg: SimpleNamespace(),
    )
    monkeypatch.setattr(preflight_module.session_state, "_assess_pending_interruption", fake_assess_interruption)

    result = await service.run({
        "db": object(),
        "session": SimpleNamespace(id=3),
        "task": task,
        "turn_input": AgentTurnInput.text("这个客户挺重要"),
        "team_id": 1,
        "session_id": 3,
        "events": [],
    })

    assert result.handled is True
    assert result.task is task
    assert result.assistant_content == "你是要确认执行，还是先取消？也可以直接说新的需求。"
    assert [event["event"] for event in result.events] == [
        "confirmation_intent_assessed",
        "pending_interruption_assessed",
        "confirmation_intent_unknown",
        "final",
    ]

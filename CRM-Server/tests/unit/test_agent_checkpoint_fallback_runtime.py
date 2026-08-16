"""Tests for the root checkpoint-unavailable LangGraph fallback runtime."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.agent.checkpoint_fallback_runtime import AgentCheckpointFallbackRuntime
from app.services.agent.input import AgentTurnInput
from app.services.agent.schemas import AgentConfirmationIntentDecision


class FakePendingHandledGraphService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def run(self, state: dict[str, object], *, side_effects: object | None = None) -> dict[str, object]:
        self.calls.append(state)
        task = state.get("task")
        if side_effects:
            side_effects.task = task
        return {
            "has_active_task": True,
            "task_projection": {"id": 501},
            "handled": True,
            "assistant_content": "等待任务已处理。",
            "events": [{"event": "final", "content": "等待任务已处理。"}],
        }


class FakeTracedPendingHandledGraphService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.trace_calls: list[dict[str, object]] = []

    async def run(self, state: dict[str, object], *, side_effects: object | None = None) -> dict[str, object]:
        self.calls.append(state)
        return {
            "handled": False,
            "events": [{"event": "final", "content": "untraced"}],
        }

    async def run_with_trace(
        self,
        state: dict[str, object],
        *,
        side_effects: object | None = None,
    ) -> dict[str, object]:
        self.trace_calls.append(state)
        task = state.get("task")
        if side_effects:
            side_effects.task = task
        return {
            "has_active_task": True,
            "task_projection": {"id": 501},
            "handled": True,
            "assistant_content": "等待任务已处理。",
            "events": [
                {"event": "agent_step", "step": "preflight", "status": "started", "content": "判断确认意图"},
                {"event": "final", "content": "等待任务已处理。"},
            ],
        }


class FakePendingConfirmedGraphService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def run(self, state: dict[str, object], *, side_effects: object | None = None) -> dict[str, object]:
        self.calls.append(state)
        task = state.get("task")
        if side_effects:
            side_effects.task = task
        return {
            "has_active_task": True,
            "task_projection": {"id": 501},
            "handled": False,
            "confirmation_decision": AgentConfirmationIntentDecision(
                intent="confirm",
                confidence=0.98,
                reason="用户确认执行。",
            ),
            "events": [{"event": "confirmation_intent_assessed"}],
        }


@pytest.mark.asyncio
async def test_checkpoint_fallback_runtime_routes_pending_handled_result() -> None:
    pending_graph = FakePendingHandledGraphService()
    runtime = AgentCheckpointFallbackRuntime(pending_graph_service=pending_graph)
    task = SimpleNamespace(id=501, task_key="task-501", status="WAITING_USER")

    result = await runtime.run(
        db=object(),
        session=SimpleNamespace(id=4, session_key="abc", context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充字段"),
        content="补充字段",
        team_id=2,
        user_id=3,
        authorization="Bearer test",
    )

    assert result.checkpoint_unavailable is True
    assert result.state["application_action"] == "pending_handled"
    assert result.turn_output.assistant_content == "等待任务已处理。"
    assert pending_graph.calls[0]["task"] is task
    assert result.turn_output.events[0]["event"] == "agent_root_checkpoint_unavailable_fallback_started"


@pytest.mark.asyncio
async def test_checkpoint_fallback_runtime_prefers_traced_pending_events() -> None:
    pending_graph = FakeTracedPendingHandledGraphService()
    runtime = AgentCheckpointFallbackRuntime(pending_graph_service=pending_graph)
    task = SimpleNamespace(id=501, task_key="task-501", status="WAITING_USER")

    result = await runtime.run(
        db=object(),
        session=SimpleNamespace(id=4, session_key="abc", context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充字段"),
        content="补充字段",
        team_id=2,
        user_id=3,
        authorization="Bearer test",
    )

    assert pending_graph.calls == []
    assert pending_graph.trace_calls[0]["task"] is task
    assert result.turn_output.events[1] == {
        "event": "agent_step",
        "step": "preflight",
        "status": "started",
        "content": "判断确认意图",
    }


@pytest.mark.asyncio
async def test_checkpoint_fallback_runtime_blocks_confirmed_pending_task_write() -> None:
    pending_graph = FakePendingConfirmedGraphService()
    runtime = AgentCheckpointFallbackRuntime(pending_graph_service=pending_graph)
    task = SimpleNamespace(id=501, task_key="task-501", status="WAITING_USER")

    result = await runtime.run(
        db=object(),
        session=SimpleNamespace(id=4, session_key="abc", context_json={}),
        task=task,
        turn_input=AgentTurnInput.confirm(),
        content="确认",
        team_id=2,
        user_id=3,
        authorization="Bearer test",
    )

    assert result.state["application_action"] == "execute_confirmed_task"
    assert result.state["runtime_status"] == "checkpoint_unavailable_write_blocked"
    assert "业务写入已暂停" in result.turn_output.assistant_content
    assert pending_graph.calls[0]["task"] is task
    assert any(event["event"] == "agent_root_checkpoint_write_blocked" for event in result.turn_output.events)


@pytest.mark.asyncio
async def test_checkpoint_fallback_runtime_routes_no_pending_confirmation() -> None:
    pending_graph = FakePendingHandledGraphService()
    runtime = AgentCheckpointFallbackRuntime(pending_graph_service=pending_graph)

    result = await runtime.run(
        db=object(),
        session=SimpleNamespace(id=4, session_key="abc", context_json={}),
        task=None,
        turn_input=AgentTurnInput.confirm(),
        content="确认",
        team_id=2,
        user_id=3,
        authorization="Bearer test",
    )

    assert result.state["application_action"] == "no_pending_confirmation"
    assert result.turn_output.assistant_content
    assert pending_graph.calls == []


@pytest.mark.asyncio
async def test_checkpoint_fallback_runtime_blocks_new_flow_write_side_effects() -> None:
    pending_graph = FakePendingHandledGraphService()
    runtime = AgentCheckpointFallbackRuntime(pending_graph_service=pending_graph)

    result = await runtime.run(
        db=object(),
        session=SimpleNamespace(id=4, session_key="abc", context_json={}),
        task=None,
        turn_input=AgentTurnInput.text("今天和客户沟通了续费"),
        content="今天和客户沟通了续费",
        team_id=2,
        user_id=3,
        authorization="Bearer test",
    )

    assert result.state["application_action"] == "run_new_flow"
    assert result.state["runtime_status"] == "checkpoint_unavailable_write_blocked"
    assert "业务写入已暂停" in result.turn_output.assistant_content
    assert pending_graph.calls == []

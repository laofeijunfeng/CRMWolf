"""Confirmed task LangGraph orchestration tests."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.exc import SQLAlchemyError

from app.services.agent import confirmed_task_graph as confirmed_task_graph_module
from app.services.agent.confirmed_task_graph import (
    ConfirmedTaskGraphService,
    build_confirmed_task_graph_config,
    build_confirmed_task_thread_id,
)
from app.services.agent.state import (
    ConfirmedTaskExecutionResult,
    ConfirmedTaskGraphSideEffects,
    ConfirmedTaskRuntimeContext,
)


class FakeCheckpointFailingGraph:
    async def ainvoke(self, state, config, *, context):
        raise SQLAlchemyError("checkpoint write failed")


class FakeFallbackGraph:
    def __init__(self):
        self.calls = []

    async def ainvoke(self, state, config, *, context):
        self.calls.append({"state": state, "config": config, "context": context})
        return {
            **state,
            "task_event": {"event": "task_completed", "task_id": 101},
            "assistant_content": "fallback ok",
            "execution_status": "completed",
            "events": [{"event": "confirmed_task_graph_finished"}],
        }


class FakeConfirmedTaskSideEffectHandler:
    def __init__(self):
        self.calls = []

    def apply(self, context):
        self.calls.append(context)
        output_events = []
        if context.execution.tool_event:
            output_events.append(context.execution.tool_event)
        output_events.append(context.execution.task_event)
        output_events.append({"event": "final", "content": context.execution.assistant_content})
        return SimpleNamespace(
            task_event=context.execution.task_event,
            output_events=output_events,
            assistant_content=context.execution.assistant_content,
        )


def _task():
    return SimpleNamespace(
        id=101,
        task_key="task-101",
        status="WAITING_USER",
        intent="CREATE_FOLLOW_UP",
        target_type="customer",
        target_id=17,
        state_json={"action": "create_customer_activity", "payload": {"customer_id": 17}},
    )


def _input_state(task):
    return {
        "db": object(),
        "session": SimpleNamespace(id=3),
        "task": task,
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "authorization": "Bearer test",
        "events": [],
    }


@pytest.mark.asyncio
async def test_confirmed_task_graph_checkpoints_by_session_and_task_thread(monkeypatch):
    task = _task()
    calls = []

    async def fake_execute_confirmed_task(db, task, *, session, team_id, user_id, authorization, event_sink):
        calls.append({
            "db": db,
            "task": task,
            "session": session,
            "team_id": team_id,
            "user_id": user_id,
            "authorization": authorization,
            "event_sink": event_sink,
        })
        return ConfirmedTaskExecutionResult(
            tool_event={"event": "tool_result", "tool_name": "create_customer_activity", "success": True},
            task_event={"event": "task_completed", "task_id": task.id, "content": "跟进记录已创建。"},
            assistant_content="跟进记录已创建。",
            next_task=None,
        )

    monkeypatch.setattr(confirmed_task_graph_module, "execute_confirmed_task", fake_execute_confirmed_task)
    side_effect_handler = FakeConfirmedTaskSideEffectHandler()
    service = ConfirmedTaskGraphService(
        side_effect_handler=side_effect_handler,
        checkpointer=InMemorySaver(),
    )

    result = await service.run(_input_state(task))
    snapshot = await service._graph.aget_state(build_confirmed_task_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
        task_id=101,
    ))

    assert build_confirmed_task_thread_id(team_id=1, user_id=2, session_id=3, task_id=101) == (
        "crm_agent_confirmed:1:2:3:101"
    )
    assert calls[0]["task"] is task
    assert calls[0]["authorization"] == "Bearer test"
    assert calls[0]["event_sink"] is None
    assert side_effect_handler.calls[0].task is task
    assert snapshot.values["task_projection"] == {
        "id": 101,
        "task_key": "task-101",
        "status": "WAITING_USER",
        "intent": "CREATE_FOLLOW_UP",
        "target_type": "customer",
        "target_id": 17,
    }
    assert snapshot.values["tool_request"] == {
        "task": snapshot.values["task_projection"],
        "action": "create_customer_activity",
    }
    assert snapshot.values["execution_status"] == "completed"
    assert result["output_events"] == [
        {"event": "tool_result", "tool_name": "create_customer_activity", "success": True},
        {"event": "task_completed", "task_id": 101, "content": "跟进记录已创建。"},
        {"event": "final", "content": "跟进记录已创建。"},
    ]


@pytest.mark.asyncio
async def test_confirmed_task_graph_internal_state_keeps_runtime_objects_in_context(monkeypatch):
    task = _task()
    async def fake_execute_confirmed_task(db, task, *, session, team_id, user_id, authorization, event_sink):
        return ConfirmedTaskExecutionResult(
            tool_event={"event": "tool_result", "tool_name": "create_customer_activity", "success": True},
            task_event={"event": "task_completed", "task_id": task.id, "content": "跟进记录已创建。"},
            assistant_content="跟进记录已创建。",
            next_task=None,
        )

    monkeypatch.setattr(confirmed_task_graph_module, "execute_confirmed_task", fake_execute_confirmed_task)
    side_effect_handler = FakeConfirmedTaskSideEffectHandler()
    service = ConfirmedTaskGraphService(
        side_effect_handler=side_effect_handler,
    )
    side_effects = ConfirmedTaskGraphSideEffects()

    state = await service._graph.ainvoke(
        {
            "team_id": 1,
            "user_id": 2,
            "session_id": 3,
            "task_projection": {"id": 101},
            "events": [],
        },
        context=ConfirmedTaskRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=3),
            task=task,
            team_id=1,
            user_id=2,
            session_id=3,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
    )

    assert "db" not in state
    assert "session" not in state
    assert "task" not in state
    assert "authorization" not in state
    assert side_effects.task_event == {"event": "task_completed", "task_id": 101, "content": "跟进记录已创建。"}
    assert side_effects.output_events[-1] == {"event": "final", "content": "跟进记录已创建。"}
    assert side_effect_handler.calls[0].execution.assistant_content == "跟进记录已创建。"


@pytest.mark.asyncio
async def test_confirmed_task_graph_does_not_fallback_for_business_sql_errors(monkeypatch):
    async def fake_execute_confirmed_task(db, task, *, session, team_id, user_id, authorization, event_sink):
        raise SQLAlchemyError("business db failed")

    monkeypatch.setattr(confirmed_task_graph_module, "execute_confirmed_task", fake_execute_confirmed_task)
    service = ConfirmedTaskGraphService(checkpointer=InMemorySaver())

    with pytest.raises(SQLAlchemyError, match="business db failed"):
        await service.run(_input_state(_task()))


@pytest.mark.asyncio
async def test_confirmed_task_graph_falls_back_only_for_checkpoint_storage_errors(monkeypatch):
    service = ConfirmedTaskGraphService(
        side_effect_handler=FakeConfirmedTaskSideEffectHandler(),
        checkpointer=InMemorySaver(),
    )
    fallback_graph = FakeFallbackGraph()
    service._graph = FakeCheckpointFailingGraph()
    service._fallback_graph = fallback_graph
    monkeypatch.setattr(confirmed_task_graph_module, "is_checkpoint_storage_error", lambda exc: True)

    result = await service.run(_input_state(_task()))

    assert fallback_graph.calls
    assert fallback_graph.calls[0]["state"]["task_projection"]["id"] == 101
    assert result["events"][0]["event"] == "agent_checkpoint_unavailable_fallback_started"
    assert result["events"][0]["runtime"] == "crm_agent_confirmed_task"
    assert result["events"][0]["graph"] == "crm_agent_confirmed_task"
    assert result["events"][0]["fallback_reason"] == "checkpoint_storage_error"
    assert result["output_events"][0] == result["events"][0]
    assert result["execution_status"] == "completed"

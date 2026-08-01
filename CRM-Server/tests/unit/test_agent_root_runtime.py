"""Tests for the LangGraph-native CRM Agent root runtime."""
from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from types import SimpleNamespace

from app.services.agent import agent_copy
from app.services.agent import root_runtime as root_runtime_module
from app.services.agent.input import AgentTurnInput
from app.services.agent.root_runtime import (
    AgentRootRuntime,
    build_agent_thread_id,
    project_turn_output,
)
from app.services.agent.schemas import AgentConfirmationIntentDecision
from app.services.agent.state import AgentRootRuntimeSideEffects, AgentRuntimeContext


class FakePendingGraphService:
    def __init__(self):
        self.calls = []

    async def run(self, state, *, side_effects=None):
        self.calls.append(state)
        if side_effects:
            side_effects.task = state["task"]
        return {
            "has_active_task": True,
            "task_projection": {
                "id": state["task"].id,
                "task_key": state["task"].task_key,
                "status": state["task"].status,
                "intent": state["task"].intent,
                "target_id": state["task"].target_id,
            },
            "handled": True,
            "assistant_content": "请确认是否创建商机？",
            "remember_pending_task": True,
            "events": [{"event": "confirmation_required"}, {"event": "final"}],
        }


class FakeTracedPendingGraphService:
    def __init__(self):
        self.calls = []
        self.trace_calls = []

    async def run(self, state, *, side_effects=None):
        self.calls.append(state)
        return {
            "handled": False,
            "events": [{"event": "final", "content": "untraced"}],
        }

    async def run_with_trace(self, state, *, side_effects=None):
        self.trace_calls.append(state)
        if side_effects:
            side_effects.task = state["task"]
        return {
            "has_active_task": True,
            "task_projection": {
                "id": state["task"].id,
                "task_key": state["task"].task_key,
                "status": state["task"].status,
                "intent": state["task"].intent,
                "target_id": state["task"].target_id,
            },
            "handled": True,
            "assistant_content": "请确认是否创建商机？",
            "remember_pending_task": True,
            "events": [
                {"event": "agent_step", "step": "preflight", "status": "started", "content": "判断确认意图"},
                {"event": "agent_step", "step": "preflight", "status": "completed", "content": "判断确认意图"},
                {"event": "confirmation_required"},
                {"event": "final"},
            ],
        }


class FakeConfirmingPendingGraphService:
    def __init__(self):
        self.calls = []

    async def run(self, state, *, side_effects=None):
        self.calls.append(state)
        if side_effects:
            side_effects.task = state["task"]
        return {
            "has_active_task": True,
            "task_projection": {"id": state["task"].id, "task_key": state["task"].task_key, "status": state["task"].status},
            "handled": False,
            "confirmation_decision": AgentConfirmationIntentDecision(
                intent="confirm",
                confidence=0.98,
                reason="用户确认执行。",
            ),
            "events": [{"event": "confirmation_intent_assessed"}],
        }


class FakeConfirmedTaskGraphService:
    def __init__(self):
        self.calls = []

    async def run(self, state):
        self.calls.append(state)
        task = state["task"]
        return {
            "task_projection": {"id": task.id, "task_key": task.task_key, "status": task.status},
            "tool_result": {"event": "tool_result", "tool_name": "create_customer_activity", "success": True},
            "task_event": {"event": "task_completed", "task_id": task.id, "content": "跟进记录已创建。"},
            "assistant_content": "跟进记录已创建。",
            "execution_status": "completed",
            "output_events": [
                {"event": "tool_result", "tool_name": "create_customer_activity", "success": True},
                {"event": "task_completed", "task_id": task.id, "content": "跟进记录已创建。"},
                {"event": "final", "content": "跟进记录已创建。"},
            ],
            "events": [
                {"event": "confirmed_task_graph_started"},
                {"event": "confirmed_task_execution_completed"},
                {"event": "confirmed_task_graph_finished"},
            ],
        }


@pytest.mark.asyncio
async def test_root_runtime_run_turn_aligns_context_task_to_checkpoint_interrupt(monkeypatch):
    checkpoint_task = SimpleNamespace(
        id=900,
        task_key="task-checkpoint",
        status="WAITING_USER",
        intent="CREATE_FOLLOW_UP",
        target_type="customer",
        target_id=101,
    )
    stale_task = SimpleNamespace(
        id=100,
        task_key="task-stale",
        status="WAITING_USER",
        intent="CREATE_OPPORTUNITY",
        target_type="customer",
        target_id=202,
    )
    lookup_calls = []

    def fake_get_by_id(db, task_id, *, team_id, user_id):
        lookup_calls.append({
            "db": db,
            "task_id": task_id,
            "team_id": team_id,
            "user_id": user_id,
        })
        return checkpoint_task if task_id == checkpoint_task.id else None

    class RuntimeUnderTest(AgentRootRuntime):
        def __init__(self):
            self.resume_calls = []

        async def current_interrupt(self, **kwargs):
            return {
                "type": "confirm",
                "reason": "write_confirmation",
                "business_action": "checkpoint_action",
                "allowed_resume_actions": ["approve", "edit", "reject", "cancel"],
                "task_projection_id": checkpoint_task.id,
                "task_projection_key": checkpoint_task.task_key,
            }

        async def has_pending_interrupt(self, **kwargs):
            return True

        async def checkpoint_turn_start(self, state, *, context=None):
            raise AssertionError("active checkpoint interrupt should resume directly")

        async def resume_interrupt(self, **kwargs):
            self.resume_calls.append(kwargs)
            return {
                "application_action": "no_pending_confirmation",
                "current_interrupt": None,
                "resume_payload": kwargs["resume_payload"],
                "task_projection": {"id": kwargs["context"].task.id},
            }

    monkeypatch.setattr(root_runtime_module.agent_task_crud, "get_by_id", fake_get_by_id)

    runtime = RuntimeUnderTest()
    context = AgentRuntimeContext(
        db=object(),
        task=stale_task,
        turn_input=AgentTurnInput.confirm(source="web"),
        content="确认",
        team_id=1,
        user_id=2,
        session_id=3,
        authorization="Bearer test-token",
    )

    state = await runtime.run_turn(
        turn_input=AgentTurnInput.confirm(source="web"),
        content="确认",
        team_id=1,
        user_id=2,
        session_id=3,
        session_key="session-key",
        current_customer={},
        context=context,
    )

    assert context.task == checkpoint_task
    assert lookup_calls == [{
        "db": context.db,
        "task_id": checkpoint_task.id,
        "team_id": 1,
        "user_id": 2,
    }]
    assert runtime.resume_calls[0]["current_interrupt"]["task_projection_id"] == checkpoint_task.id
    assert runtime.resume_calls[0]["resume_payload"]["task_projection_id"] == checkpoint_task.id
    assert state["task_projection"]["id"] == checkpoint_task.id


class FakePendingTaskSideEffectHandler:
    def __init__(self):
        self.calls = []

    def apply(self, graph_state, context):
        self.calls.append({"graph_state": graph_state, "context": context})
        graph_side_effects = getattr(context, "graph_side_effects", None)
        task = getattr(graph_side_effects, "task", None) if graph_side_effects else context.task
        return SimpleNamespace(
            task=task,
            events=graph_state.get("events", []),
            assistant_content=graph_state.get("assistant_content"),
            switch_notice=graph_state.get("switch_notice"),
            current_interrupt=graph_state.get("current_interrupt"),
        )


class FakeNewFlowGraphService:
    def __init__(self):
        self.calls = []

    async def stream_events(self, input_state):
        self.calls.append(input_state)
        yield {"event": "agent_step", "step": "semantic_parse", "status": "started"}
        yield {"event": "final", "content": "已处理新流程"}


class FakeNativeNewFlowGraphService:
    def __init__(self):
        self.calls = []
        self.stream_calls = []

    async def run(self, input_state):
        self.calls.append(input_state)
        return {
            "events": [
                {"event": "business_context_loaded", "customer": {"id": 101, "account_name": "越秀金融"}},
                {
                    "event": "confirmation_required",
                    "action": "create_customer_activity",
                    "payload": {"customer_id": 101, "content": "已沟通项目进展"},
                    "content": "请确认是否创建这条跟进记录？",
                },
                {"event": "final", "content": "已处理：今天和越秀金融沟通"},
            ],
            "response": "已处理：今天和越秀金融沟通",
        }

    async def stream_events(self, input_state):
        self.stream_calls.append(input_state)
        yield {"event": "agent_step", "step": "load_memory", "status": "started", "content": "加载会话记忆"}
        yield {"event": "agent_step", "step": "load_memory", "status": "completed", "content": "加载会话记忆"}
        yield {"event": "business_context_loaded", "customer": {"id": 101, "account_name": "越秀金融"}}
        yield {
            "event": "confirmation_required",
            "action": "create_customer_activity",
            "payload": {"customer_id": 101, "content": "已沟通项目进展"},
            "content": "请确认是否创建这条跟进记录？",
        }
        yield {"event": "final", "content": "已处理：今天和越秀金融沟通"}


class FakeSideEffectNewFlowGraphService:
    async def stream_events(self, input_state):
        yield {
            "event": "business_context_loaded",
            "customer": {"id": 101, "account_name": "越秀金融"},
        }
        yield {
            "event": "confirmation_required",
            "action": "create_customer_activity",
            "payload": {"customer_id": 101, "content": "已沟通项目进展"},
            "content": "请确认是否创建这条跟进记录？",
        }
        yield {"event": "final", "content": "已处理：今天和越秀金融沟通"}


class FakeAutoExecutableNewFlowGraphService:
    async def stream_events(self, input_state):
        yield {
            "event": "business_context_loaded",
            "customer": {"id": 101, "account_name": "越秀金融"},
        }
        yield {
            "event": "confirmation_required",
            "action": "create_customer_activity",
            "hitl_auto_execute_candidate": True,
            "payload": {
                "customer_id": 101,
                "content": "已沟通项目进展",
                "hitl_auto_execute_candidate": True,
            },
            "content": "请确认是否创建这条跟进记录？",
        }
        yield {"event": "final", "content": "请确认是否创建这条跟进记录？"}


def waiting_task_stub():
    return SimpleNamespace(
        id=101,
        task_key="task-101",
        status="WAITING_USER",
        intent="CUSTOMER_ACTIVITY",
        target_id=101,
        summary="等待确认创建跟进",
        state_json={"action": "create_customer_activity", "payload": {"customer_id": 101}},
    )


def test_build_agent_thread_id_is_session_scoped_and_stable():
    assert build_agent_thread_id(team_id=2, user_id=3, session_id=4, session_key="abc") == "crm_agent:2:3:4:abc"
    assert build_agent_thread_id(team_id=2, user_id=3, session_id=4) == "crm_agent:2:3:4:4"


@pytest.mark.asyncio
async def test_root_runtime_checkpoints_serializable_agent_state():
    new_flow_graph_service = FakeNewFlowGraphService()
    runtime = AgentRootRuntime(checkpointer=InMemorySaver(), new_flow_graph_service=new_flow_graph_service)
    side_effects = AgentRootRuntimeSideEffects()

    state = await runtime.checkpoint_turn_start({
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "session_key": "abc",
        "channel": "web",
        "content": "记录一下客户跟进",
        "turn_kind": "text",
        "current_customer": {"id": 10, "account_name": "睿狐科技"},
    }, context=AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4),
        content="记录一下客户跟进",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=side_effects,
    ))

    assert state["runtime_status"] == "checkpointed"
    assert state["route"] == "new_flow_graph"
    assert [event["event"] for event in state["events"]] == [
        "agent_root_graph_started",
        "agent_root_route_selected",
        "agent_root_application_action_decided",
        "agent_root_new_flow_graph_completed",
        "agent_root_graph_checkpointed",
    ]
    assert state["application_action"] == "run_new_flow"
    assert state["new_flow_result"] == {
        "handled": True,
        "event_count": 2,
        "has_assistant_content": True,
        "has_interrupt": False,
        "assistant_content": "已处理新流程",
    }
    assert new_flow_graph_service.calls[0]["content"] == "记录一下客户跟进"
    assert new_flow_graph_service.calls[0]["session_context"] == {}
    assert side_effects.new_flow_events[-1] == {"event": "final", "content": "已处理新流程"}
    assert side_effects.new_flow_assistant_content == "已处理新流程"


@pytest.mark.asyncio
async def test_root_runtime_resets_turn_scoped_result_projections_between_invokes():
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeNewFlowGraphService(),
    )

    first_state = await runtime.checkpoint_turn_start({
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "session_key": "abc",
        "channel": "web",
        "content": "记录一下客户跟进",
        "turn_kind": "text",
    }, context=AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        content="记录一下客户跟进",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    ))

    second_state = await runtime.checkpoint_turn_start({
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "session_key": "abc",
        "channel": "web",
        "content": "确认",
        "turn_kind": "confirm",
        "current_interrupt": {"type": "confirm", "business_action": "CREATE_FOLLOW_UP"},
    })

    assert first_state["new_flow_result"]["assistant_content"] == "已处理新流程"
    assert second_state["new_flow_result"] == {}
    assert second_state["pending_task_result"] == {}


@pytest.mark.asyncio
async def test_root_runtime_applies_new_flow_side_effects_inside_graph_node(monkeypatch):
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

    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.task_factory._create_waiting_task_from_event",
        create_waiting_task,
    )
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeSideEffectNewFlowGraphService(),
    )
    side_effects = AgentRootRuntimeSideEffects()

    state = await runtime.checkpoint_turn_start({
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "session_key": "abc",
        "channel": "web",
        "content": "今天和越秀金融沟通",
        "turn_kind": "text",
    }, context=AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        content="今天和越秀金融沟通",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        switch_notice="我先切到新流程处理。",
        side_effects=side_effects,
    ))

    assert remembered_customers == [{"id": 101, "account_name": "越秀金融"}]
    assert waiting_events[0]["event"] == "confirmation_required"
    assert state["current_interrupt"]["type"] == "confirm"
    assert state["current_interrupt"]["reason"] == "write_confirmation"
    assert state["current_interrupt"]["allowed_resume_actions"] == ["approve", "edit", "reject", "cancel"]
    assert state["current_interrupt"]["task_projection_id"] == 501
    assert state["current_interrupt"]["task_projection_key"] == "task-501"
    assert state["new_flow_result"]["has_interrupt"] is True
    assert state["new_flow_result"]["task_projection_id"] == 501
    assert state["new_flow_result"]["task_projection_key"] == "task-501"
    assert side_effects.current_interrupt == state["current_interrupt"]
    assert "__interrupt__" in state
    assert await runtime.has_pending_interrupt(team_id=2, user_id=3, session_id=4, session_key="abc") is True
    assert side_effects.new_flow_events[-1] == {
        "event": "final",
        "content": "我先切到新流程处理。\n\n已处理：今天和越秀金融沟通",
    }
    assert side_effects.new_flow_assistant_content == "我先切到新流程处理。\n\n已处理：今天和越秀金融沟通"


@pytest.mark.asyncio
async def test_root_runtime_auto_executes_low_risk_reviewed_new_flow_action(monkeypatch):
    created_tasks = []

    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.session_state._remember_current_customer",
        lambda db_arg, session_arg, customer: None,
    )

    def create_waiting_task(db_arg, event, team_id, user_id, session_arg):
        task = SimpleNamespace(
            id=501,
            task_key="task-501",
            status="WAITING_USER",
            state_json={
                "action": event["action"],
                "payload": event["payload"],
                "customer": event.get("customer") or {"id": 101, "account_name": "越秀金融"},
            },
        )
        event["task_id"] = task.id
        event["task_key"] = task.task_key
        created_tasks.append(task)
        return task

    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.task_factory._create_waiting_task_from_event",
        create_waiting_task,
    )
    confirmed_task_graph_service = FakeConfirmedTaskGraphService()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=confirmed_task_graph_service,
    )
    side_effects = AgentRootRuntimeSideEffects()

    state = await runtime.checkpoint_turn_start({
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "session_key": "abc",
        "channel": "web",
        "content": "今天和越秀金融沟通",
        "turn_kind": "text",
    }, context=AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        content="今天和越秀金融沟通",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=side_effects,
    ))

    assert created_tasks[0].id == 501
    assert confirmed_task_graph_service.calls[0]["task"].id == 501
    assert state["current_interrupt"] is None
    assert state["new_flow_result"]["has_interrupt"] is False
    assert state["assistant_content"] == "跟进记录已创建。"
    assert "请确认是否创建这条跟进记录？" not in [
        event.get("content")
        for event in side_effects.new_flow_events
        if event.get("event") == "final"
    ]
    assert [event["event"] for event in side_effects.new_flow_events].count("action_review_decided") == 1
    assert [event["event"] for event in side_effects.new_flow_events].count("action_auto_execution_queued") == 1
    assert {
        "event": "agent_step",
        "step": "auto_execute_task",
        "status": "started",
        "content": "记录跟进",
    } in side_effects.new_flow_events
    assert "确认记录跟进" not in str([
        event.get("content")
        for event in side_effects.new_flow_events
    ])


@pytest.mark.asyncio
async def test_root_runtime_checkpoints_new_flow_result_and_interrupt_snapshot(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.session_state._remember_current_customer",
        lambda db_arg, session_arg, customer: None,
    )

    def create_waiting_task(db_arg, event, team_id, user_id, session_arg):
        event["task_id"] = 501
        event["task_key"] = "task-501"

    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.task_factory._create_waiting_task_from_event",
        create_waiting_task,
    )
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeSideEffectNewFlowGraphService(),
    )

    state = await runtime.checkpoint_turn_start({
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "session_key": "abc",
        "channel": "web",
        "content": "今天和越秀金融沟通",
        "turn_kind": "text",
    }, context=AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        content="今天和越秀金融沟通",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    ))

    checkpoint_state = await runtime.current_checkpoint_state(
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
    )

    assert checkpoint_state["new_flow_result"] == state["new_flow_result"]
    assert checkpoint_state["current_interrupt"] == state["current_interrupt"]
    assert checkpoint_state["new_flow_result"]["has_interrupt"] is True
    assert checkpoint_state["new_flow_result"]["task_projection_id"] == 501


@pytest.mark.asyncio
async def test_root_runtime_exposes_checkpoint_history_for_replayable_audit():
    runtime = AgentRootRuntime(checkpointer=InMemorySaver())

    first_state = await runtime.checkpoint_turn_start({
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "session_key": "abc",
        "channel": "web",
        "content": "确认",
        "turn_kind": "confirm",
        "current_interrupt": {"type": "confirm", "business_action": "CREATE_FOLLOW_UP"},
    })
    assert first_state["current_interrupt"]["business_action"] == "CREATE_FOLLOW_UP"

    await runtime.resume_interrupt(
        resume_payload={"action": "approve", "content": "确认", "source": "web", "metadata": {}},
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
    )

    history = await runtime.state_history(
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        limit=12,
    )

    assert len(history) >= 2
    assert all("checkpoint_id" in item for item in history)
    assert all("values" in item for item in history)
    assert all("db" not in item["values"] for item in history)
    assert all("authorization" not in item["values"] for item in history)
    assert history[0]["values"]["current_interrupt"] is None
    assert any(item["has_interrupt"] is True for item in history)
    assert any(
        item["values"].get("current_interrupt", {}).get("business_action") == "CREATE_FOLLOW_UP"
        for item in history
        if isinstance(item["values"].get("current_interrupt"), dict)
    )
    assert any(
        event.get("event") == "agent_root_interrupt_resumed"
        for item in history
        for event in item["values"].get("events", [])
        if isinstance(event, dict)
    )


@pytest.mark.asyncio
async def test_root_runtime_can_read_state_at_history_checkpoint():
    runtime = AgentRootRuntime(checkpointer=InMemorySaver())

    await runtime.checkpoint_turn_start({
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "session_key": "abc",
        "channel": "web",
        "content": "确认",
        "turn_kind": "confirm",
        "current_interrupt": {"type": "confirm", "business_action": "CREATE_FOLLOW_UP"},
    })
    await runtime.resume_interrupt(
        resume_payload={"action": "approve", "content": "确认", "source": "web", "metadata": {}},
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
    )
    history = await runtime.state_history(
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        limit=12,
    )
    interrupted_checkpoint = next(
        item for item in history
        if isinstance(item["values"].get("current_interrupt"), dict)
    )

    checkpoint_state = await runtime.checkpoint_state_at(
        checkpoint_id=interrupted_checkpoint["checkpoint_id"],
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
    )

    assert checkpoint_state["current_interrupt"]["business_action"] == "CREATE_FOLLOW_UP"
    assert checkpoint_state["current_interrupt"]["type"] == "confirm"


@pytest.mark.asyncio
async def test_root_runtime_prefers_native_new_flow_graph_stream_updates(monkeypatch):
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

    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.task_factory._create_waiting_task_from_event",
        create_waiting_task,
    )
    new_flow_graph_service = FakeNativeNewFlowGraphService()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=new_flow_graph_service,
    )
    side_effects = AgentRootRuntimeSideEffects()

    state = await runtime.checkpoint_turn_start({
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "session_key": "abc",
        "channel": "web",
        "content": "今天和越秀金融沟通",
        "turn_kind": "text",
    }, context=AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        content="今天和越秀金融沟通",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=side_effects,
    ))

    assert new_flow_graph_service.calls == []
    assert len(new_flow_graph_service.stream_calls) == 1
    assert side_effects.new_flow_events[:3] == [
        {"event": "agent_step", "step": "new_flow_branch", "status": "started", "content": "处理新的业务输入"},
        {"event": "agent_step", "step": "load_memory", "status": "started", "content": "加载会话记忆"},
        {"event": "agent_step", "step": "load_memory", "status": "completed", "content": "加载会话记忆"},
    ]
    assert remembered_customers == [{"id": 101, "account_name": "越秀金融"}]
    assert waiting_events[0]["event"] == "confirmation_required"
    assert state["current_interrupt"]["task_projection_id"] == 501
    assert state["__interrupt__"][0].value == state["current_interrupt"]
    assert side_effects.new_flow_assistant_content == "已处理：今天和越秀金融沟通"


@pytest.mark.asyncio
async def test_root_runtime_resumes_generated_interrupt_by_loading_task_projection(monkeypatch):
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

    task = SimpleNamespace(id=501, task_key="task-501", status="WAITING_USER")
    loaded_task_ids = []
    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.task_factory._create_waiting_task_from_event",
        create_waiting_task,
    )
    monkeypatch.setattr(
        "app.services.agent.root_runtime.agent_task_crud.get_by_id",
        lambda db_arg, task_id, team_id, user_id: loaded_task_ids.append(task_id) or task,
    )
    pending_graph_service = FakeConfirmingPendingGraphService()
    confirmed_task_graph_service = FakeConfirmedTaskGraphService()
    pending_effects = FakePendingTaskSideEffectHandler()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeNativeNewFlowGraphService(),
        pending_graph_service=pending_graph_service,
        confirmed_task_graph_service=confirmed_task_graph_service,
        pending_task_side_effect_handler=pending_effects,
    )

    first_side_effects = AgentRootRuntimeSideEffects()
    first_state = await runtime.checkpoint_turn_start({
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "session_key": "abc",
        "channel": "web",
        "content": "今天和越秀金融沟通",
        "turn_kind": "text",
    }, context=AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        content="今天和越秀金融沟通",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=first_side_effects,
    ))

    resumed_side_effects = AgentRootRuntimeSideEffects()
    resumed_state = await runtime.resume_interrupt(
        resume_payload={
            "action": "approve",
            "content": "确认",
            "source": "web",
            "metadata": {},
            "task_projection_id": 501,
            "task_projection_key": "task-501",
            "business_action": first_state["current_interrupt"]["business_action"],
            "interrupt_reason": first_state["current_interrupt"]["reason"],
        },
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        current_interrupt=first_state["current_interrupt"],
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            turn_input=AgentTurnInput.confirm(source="web"),
            content="确认",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=resumed_side_effects,
        ),
    )

    assert waiting_events[0]["task_id"] == 501
    assert loaded_task_ids == [501]
    assert pending_graph_service.calls[0]["task"] is task
    assert confirmed_task_graph_service.calls[0]["task"] is task
    assert resumed_state["application_action"] == "execute_confirmed_task"
    assert resumed_state["current_interrupt"] is None


@pytest.mark.asyncio
async def test_root_runtime_resumes_generated_interrupt_after_runtime_restart(monkeypatch):
    checkpointer = InMemorySaver()
    waiting_events = []

    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.session_state._remember_current_customer",
        lambda db_arg, session_arg, customer: None,
    )

    def create_waiting_task(db_arg, event, team_id, user_id, session_arg):
        event["task_id"] = 501
        event["task_key"] = "task-501"
        waiting_events.append(event)

    task = SimpleNamespace(id=501, task_key="task-501", status="WAITING_USER")
    loaded_task_ids = []
    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.task_factory._create_waiting_task_from_event",
        create_waiting_task,
    )
    monkeypatch.setattr(
        "app.services.agent.root_runtime.agent_task_crud.get_by_id",
        lambda db_arg, task_id, team_id, user_id: loaded_task_ids.append(task_id) or task,
    )
    first_runtime = AgentRootRuntime(
        checkpointer=checkpointer,
        new_flow_graph_service=FakeNativeNewFlowGraphService(),
    )
    first_state = await first_runtime.checkpoint_turn_start({
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "session_key": "abc",
        "channel": "web",
        "content": "今天和越秀金融沟通",
        "turn_kind": "text",
    }, context=AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        content="今天和越秀金融沟通",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    ))

    resumed_runtime = AgentRootRuntime(
        checkpointer=checkpointer,
        pending_graph_service=FakeConfirmingPendingGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
        pending_task_side_effect_handler=FakePendingTaskSideEffectHandler(),
    )
    resumed_state = await resumed_runtime.resume_interrupt(
        resume_payload={
            "action": "approve",
            "content": "确认",
            "source": "web",
            "metadata": {},
            "task_projection_id": 501,
            "task_projection_key": "task-501",
            "business_action": first_state["current_interrupt"]["business_action"],
            "interrupt_reason": first_state["current_interrupt"]["reason"],
        },
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            turn_input=AgentTurnInput.confirm(source="web"),
            content="确认",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=AgentRootRuntimeSideEffects(),
        ),
    )

    assert waiting_events[0]["task_id"] == 501
    assert loaded_task_ids == [501]
    assert resumed_state["resume_payload"]["action"] == "approve"
    assert resumed_state["application_action"] == "execute_confirmed_task"
    assert resumed_state["current_interrupt"] is None
    assert await resumed_runtime.has_pending_interrupt(team_id=2, user_id=3, session_id=4, session_key="abc") is False


@pytest.mark.asyncio
async def test_root_runtime_uses_langgraph_interrupt_for_waiting_state():
    runtime = AgentRootRuntime(checkpointer=InMemorySaver())

    state = await runtime.checkpoint_turn_start({
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "session_key": "abc",
        "channel": "web",
        "content": "确认",
        "turn_kind": "confirm",
        "current_interrupt": {"type": "confirm", "business_action": "CREATE_FOLLOW_UP"},
    })

    assert state["route"] == "interrupt"
    assert "__interrupt__" in state
    assert state["__interrupt__"][0].value == {"type": "confirm", "business_action": "CREATE_FOLLOW_UP"}
    assert await runtime.has_pending_interrupt(team_id=2, user_id=3, session_id=4, session_key="abc") is True


@pytest.mark.asyncio
async def test_root_runtime_resumes_langgraph_interrupt_with_command():
    runtime = AgentRootRuntime(checkpointer=InMemorySaver())
    await runtime.checkpoint_turn_start({
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "session_key": "abc",
        "channel": "web",
        "content": "确认",
        "turn_kind": "confirm",
        "current_interrupt": {"type": "confirm", "business_action": "CREATE_FOLLOW_UP"},
    })

    state = await runtime.resume_interrupt(
        resume_payload={"action": "approve", "content": "确认", "source": "web", "metadata": {}},
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
    )

    assert state["runtime_status"] == "checkpointed"
    assert state["current_interrupt"] is None
    assert state["resume_payload"]["action"] == "approve"
    assert [event["event"] for event in state["events"]] == [
        "agent_root_graph_started",
        "agent_root_route_selected",
        "agent_root_interrupt_resumed",
        "agent_root_route_selected",
        "agent_root_application_action_decided",
        "agent_root_no_pending_confirmation_completed",
        "agent_root_graph_checkpointed",
    ]
    assert state["application_action"] == "no_pending_confirmation"
    assert await runtime.has_pending_interrupt(team_id=2, user_id=3, session_id=4, session_key="abc") is False


@pytest.mark.asyncio
async def test_root_runtime_rejects_resume_action_not_allowed_by_current_interrupt():
    runtime = AgentRootRuntime(checkpointer=InMemorySaver())
    await runtime.checkpoint_turn_start({
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "session_key": "abc",
        "channel": "web",
        "content": "确认",
        "turn_kind": "confirm",
        "current_interrupt": {
            "type": "confirm",
            "business_action": "CREATE_FOLLOW_UP",
            "allowed_resume_actions": ["approve", "edit", "reject", "cancel"],
        },
    })

    with pytest.raises(ValueError, match="not allowed"):
        await runtime.resume_interrupt(
            resume_payload={"action": "submit", "content": "确认", "source": "web", "metadata": {}},
            team_id=2,
            user_id=3,
            session_id=4,
            session_key="abc",
        )


@pytest.mark.asyncio
async def test_root_runtime_rejects_resume_without_active_interrupt():
    runtime = AgentRootRuntime(checkpointer=InMemorySaver())

    with pytest.raises(ValueError, match="without an active interrupt"):
        await runtime.resume_interrupt(
            resume_payload={"action": "approve", "content": "确认", "source": "web", "metadata": {}},
            team_id=2,
            user_id=3,
            session_id=4,
            session_key="abc",
        )


@pytest.mark.asyncio
async def test_root_runtime_emits_no_pending_confirmation_side_effects():
    runtime = AgentRootRuntime(checkpointer=InMemorySaver())
    side_effects = AgentRootRuntimeSideEffects()

    state = await runtime.checkpoint_turn_start({
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "session_key": "abc",
        "channel": "web",
        "content": "确认",
        "turn_kind": "confirm",
    }, context=AgentRuntimeContext(side_effects=side_effects))

    assert state["application_action"] == "no_pending_confirmation"
    expected_content = agent_copy.no_pending_confirmation()
    assert side_effects.no_pending_confirmation_events == [
        {"event": "final", "content": expected_content}
    ]
    assert side_effects.no_pending_confirmation_assistant_content == expected_content


@pytest.mark.asyncio
async def test_root_runtime_routes_pending_task_through_subgraph_context():
    pending_graph_service = FakePendingGraphService()
    pending_effects = FakePendingTaskSideEffectHandler()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        pending_graph_service=pending_graph_service,
        pending_task_side_effect_handler=pending_effects,
    )
    task = waiting_task_stub()
    side_effects = AgentRootRuntimeSideEffects()

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "补充金额 10 万",
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            task=task,
            turn_input=AgentTurnInput.text("补充金额 10 万"),
            content="补充金额 10 万",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
    )

    assert pending_graph_service.calls[0]["task"] is task
    assert pending_effects.calls[0]["graph_state"]["task_projection"]["id"] == 101
    assert pending_effects.calls[0]["context"].graph_side_effects.task is task
    assert side_effects.pending_task_result is not None
    assert side_effects.pending_task_result["task_projection"]["id"] == 101
    assert side_effects.pending_task_events == [
        {
            "event": "agent_step",
            "step": "pending_task_branch",
            "status": "started",
            "content": "进入待确认或待补充流程",
        },
        {"event": "confirmation_required"},
        {"event": "final"},
    ]
    assert side_effects.pending_task_assistant_content == "请确认是否创建商机？"
    assert state["route"] == "pending_task_subgraph"
    assert state["pending_task_result"] == {
        "handled": True,
        "has_task": True,
        "has_suspended_task": False,
        "remember_pending_task": True,
        "event_count": 2,
        "assistant_content": "请确认是否创建商机？",
        "task": {
            "id": 101,
            "task_key": "task-101",
            "status": "WAITING_USER",
            "intent": "CUSTOMER_ACTIVITY",
            "target_id": 101,
        },
    }
    assert [event["event"] for event in state["events"]] == [
        "agent_root_graph_started",
        "agent_root_pending_task_subgraph_completed",
        "agent_root_pending_task_effects_applied",
        "agent_root_application_action_decided",
        "agent_root_graph_checkpointed",
    ]
    assert state["application_action"] == "pending_handled"


@pytest.mark.asyncio
async def test_root_runtime_prefers_traced_pending_task_graph_events():
    pending_graph_service = FakeTracedPendingGraphService()
    pending_effects = FakePendingTaskSideEffectHandler()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        pending_graph_service=pending_graph_service,
        pending_task_side_effect_handler=pending_effects,
    )
    task = waiting_task_stub()
    side_effects = AgentRootRuntimeSideEffects()

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "补充金额 10 万",
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            task=task,
            turn_input=AgentTurnInput.text("补充金额 10 万"),
            content="补充金额 10 万",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
    )

    assert pending_graph_service.calls == []
    assert pending_graph_service.trace_calls[0]["task"] is task
    assert side_effects.pending_task_events[:3] == [
        {
            "event": "agent_step",
            "step": "pending_task_branch",
            "status": "started",
            "content": "进入待确认或待补充流程",
        },
        {"event": "agent_step", "step": "preflight", "status": "started", "content": "判断确认意图"},
        {"event": "agent_step", "step": "preflight", "status": "completed", "content": "判断确认意图"},
    ]
    assert state["application_action"] == "pending_handled"


@pytest.mark.asyncio
async def test_root_runtime_projects_pending_waiting_event_to_current_interrupt(monkeypatch):
    pending_graph_service = FakePendingGraphService()
    runtime = AgentRootRuntime(checkpointer=InMemorySaver(), pending_graph_service=pending_graph_service)
    task = waiting_task_stub()
    side_effects = AgentRootRuntimeSideEffects()
    monkeypatch.setattr(
        "app.services.agent.session_state.agent_session_crud.update",
        lambda db_arg, session_arg, update: setattr(session_arg, "context_json", update.context_json),
    )

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "补充金额 10 万",
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            task=task,
            turn_input=AgentTurnInput.text("补充金额 10 万"),
            content="补充金额 10 万",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
    )

    assert state["current_interrupt"]["reason"] == "write_confirmation"
    assert state["current_interrupt"]["source_event"] == "confirmation_required"
    assert state["current_interrupt"]["type"] == "confirm"
    assert "__interrupt__" in state
    assert await runtime.has_pending_interrupt(team_id=2, user_id=3, session_id=4, session_key="abc") is True
    assert side_effects.current_interrupt == state["current_interrupt"]


@pytest.mark.asyncio
async def test_root_runtime_decides_confirmed_task_execution_after_pending_subgraph():
    pending_graph_service = FakeConfirmingPendingGraphService()
    confirmed_task_graph_service = FakeConfirmedTaskGraphService()
    pending_effects = FakePendingTaskSideEffectHandler()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        pending_graph_service=pending_graph_service,
        confirmed_task_graph_service=confirmed_task_graph_service,
        pending_task_side_effect_handler=pending_effects,
    )
    task = SimpleNamespace(
        id=101,
        task_key="task-101",
        status="WAITING_USER",
        state_json={"action": "create_customer_activity"},
    )
    side_effects = AgentRootRuntimeSideEffects()

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "确认",
            "turn_kind": "confirm",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4),
            task=task,
            turn_input=AgentTurnInput.confirm(source="web"),
            content="确认",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
    )

    assert state["application_action"] == "execute_confirmed_task"
    assert pending_effects.calls[0]["graph_state"]["task_projection"]["id"] == 101
    assert pending_effects.calls[0]["context"].graph_side_effects.task is task
    assert state["pending_task_result"]["confirmation_decision"] == {
        "intent": "confirm",
        "confidence": 0.98,
        "reason": "用户确认执行。",
    }
    assert confirmed_task_graph_service.calls[0]["task"] is task
    assert confirmed_task_graph_service.calls[0]["session_id"] == 4
    assert side_effects.confirmed_task_result is not None
    assert side_effects.confirmed_task_result["execution_status"] == "completed"
    assert side_effects.confirmed_task_events[:8] == [
        {
            "event": "agent_step",
            "step": "confirmed_task_branch",
            "status": "started",
            "content": "继续上一步待确认操作",
        },
        {"event": "agent_step", "step": "confirmed_task_prepare", "status": "started", "content": "读取待确认任务"},
        {"event": "agent_step", "step": "confirmed_task_prepare", "status": "completed", "content": "读取待确认任务"},
        {"event": "agent_step", "step": "confirmed_task_execute", "status": "started", "content": "执行记录跟进"},
        {"event": "agent_step", "step": "confirmed_task_execute", "status": "completed", "content": "执行记录跟进"},
        {"event": "agent_step", "step": "confirmed_task_finish", "status": "started", "content": "整理执行结果"},
        {"event": "agent_step", "step": "confirmed_task_finish", "status": "completed", "content": "整理执行结果"},
        {
            "event": "tool_result",
            "tool_name": "create_customer_activity",
            "success": True,
            "content": "记录跟进已执行",
        },
    ]
    assert side_effects.confirmed_task_events[8:] == [
        {"event": "task_completed", "task_id": 101, "content": "跟进记录已创建。"},
        {"event": "final", "content": "跟进记录已创建。"},
    ]
    assert side_effects.confirmed_task_assistant_content == "跟进记录已创建。"
    assert state["events"][-2] == {
        "event": "agent_root_confirmed_task_subgraph_completed",
        "emitted_event_count": 9,
        "task_event": "task_completed",
        "execution_status": "completed",
        "has_next_interrupt": False,
    }


def test_project_turn_output_preserves_pending_events_before_confirmed_task_events():
    side_effects = AgentRootRuntimeSideEffects()
    side_effects.pending_task_events.extend([
        {"event": "confirmation_intent_assessed"},
    ])
    side_effects.confirmed_task_events.extend([
        {"event": "agent_step", "step": "confirmed_task_execute", "status": "started", "content": "执行记录跟进"},
        {"event": "agent_step", "step": "confirmed_task_execute", "status": "completed", "content": "执行记录跟进"},
        {"event": "tool_result", "success": True, "content": "记录跟进已执行"},
        {"event": "task_completed", "content": "跟进记录已创建。"},
        {"event": "final", "content": "跟进记录已创建。"},
    ])
    side_effects.confirmed_task_assistant_content = "跟进记录已创建。"

    output = project_turn_output({"application_action": "execute_confirmed_task"}, side_effects)

    assert output.events == [
        {"event": "confirmation_intent_assessed"},
        {"event": "agent_step", "step": "confirmed_task_execute", "status": "started", "content": "执行记录跟进"},
        {"event": "agent_step", "step": "confirmed_task_execute", "status": "completed", "content": "执行记录跟进"},
        {"event": "tool_result", "success": True, "content": "记录跟进已执行"},
        {"event": "task_completed", "content": "跟进记录已创建。"},
        {"event": "final", "content": "跟进记录已创建。"},
    ]
    assert output.assistant_content == "跟进记录已创建。"


def test_project_turn_output_keeps_switch_notice_single_for_new_flow():
    side_effects = AgentRootRuntimeSideEffects()
    side_effects.pending_task_events.extend([
        {"event": "pending_task_interrupted"},
    ])
    side_effects.pending_task_switch_notice = "这条是在说「汇川技术」。我先把刚才那一步放着，切过来处理。"
    side_effects.new_flow_events.extend([
        {
            "event": "final",
            "content": "这条是在说「汇川技术」。我先把刚才那一步放着，切过来处理。\n\n已切换处理汇川技术的跟进。",
        },
    ])
    side_effects.new_flow_assistant_content = (
        "这条是在说「汇川技术」。我先把刚才那一步放着，切过来处理。\n\n已切换处理汇川技术的跟进。"
    )

    output = project_turn_output({"application_action": "run_new_flow"}, side_effects)

    assert output.events == [
        {"event": "pending_task_interrupted"},
        {
            "event": "final",
            "content": "这条是在说「汇川技术」。我先把刚才那一步放着，切过来处理。\n\n已切换处理汇川技术的跟进。",
        },
    ]
    assert output.assistant_content == (
        "这条是在说「汇川技术」。我先把刚才那一步放着，切过来处理。\n\n已切换处理汇川技术的跟进。"
    )

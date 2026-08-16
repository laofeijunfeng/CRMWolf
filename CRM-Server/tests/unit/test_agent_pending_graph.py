"""Pending task LangGraph orchestration tests."""

import json
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.exc import SQLAlchemyError

from app.models.agent import AgentTaskStatus
from app.services.agent import action_workflow, follow_up_fields, opportunity_fields, selection, session_state
from app.services.agent import pending_graph as pending_graph_module
from app.services.agent.input import AgentTurnInput
from app.services.agent.pending_continuation import pending_task_checkpoint_config
from app.services.agent.pending_graph import PendingTaskGraphService, build_pending_task_thread_id
from app.services.agent.pending_interaction_graph import PendingInteractionGraphService
from app.services.agent.schemas import AgentConfirmationIntentDecision, AgentTurnRelationDecision
from app.services.agent.state import PendingTaskGraphSideEffects, PendingTaskRuntimeContext
from app.services.agent.task_projection import RuntimeAgentTaskView, agent_task_snapshot


def test_pending_graph_defaults_to_application_step_protocol_without_legacy_adapters():
    service = PendingTaskGraphService()

    assert service.application_step_protocol is True
    assert service.preflight_graph_service is None
    assert service.interaction_graph_service is None

    with pytest.raises(ValueError, match="legacy pending graph mode requires explicit application adapters"):
        PendingTaskGraphService(
            preflight_graph_service=object(),
            application_step_protocol=False,
        )


@dataclass
class FakePreflightResult:
    task: object = None
    handled: bool = False
    events: list[dict] = field(default_factory=list)
    assistant_content: str | None = None
    switch_notice: str | None = None
    suspended_task: object = None
    suspend_reason: str | None = None
    clear_pending_task_id: int | None = None
    confirmation_decision: object = None


@dataclass
class FakeInteractionResult:
    handled: bool = False
    events: list[dict] = field(default_factory=list)
    assistant_content: str | None = None
    selected_customer: dict | None = None
    remember_pending_task: bool = False
    clear_pending_task_id: int | None = None


class FakePreflightGraphService:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def run(self, input_state):
        input_task = input_state.get("task")
        self.calls.append({
            "db": input_state.get("db"),
            "session": input_state.get("session"),
            "task": input_task,
            "turn_input": input_state.get("turn_input"),
            "team_id": input_state.get("team_id"),
            "session_id": input_state.get("session_id"),
        })
        input_task_id = getattr(input_task, "id", None)
        if input_task_id is not None:
            for field_name in ("task", "suspended_task"):
                result_task = getattr(self.result, field_name, None)
                if getattr(result_task, "id", None) == input_task_id:
                    setattr(self.result, field_name, input_task)
        return self.result


class FakeInteractionGraphService:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def run(self, input_state):
        self.calls.append({
            "db": input_state.get("db"),
            "task": input_state.get("task"),
            "content": input_state.get("content"),
            "team_id": input_state.get("team_id"),
            "user_id": input_state.get("user_id"),
            "session_id": input_state.get("session_id"),
            "authorization": input_state.get("authorization"),
        })
        return self.result


class FakeFailingPreflightGraphService:
    async def run(self, input_state):
        raise SQLAlchemyError("business db failed")


def _task_projection_effect(result: dict, task_id: int) -> dict:
    matches = [
        intent
        for intent in result.get("effect_intents", [])
        if intent.get("intent_type") == "project_pending_task_state"
        and intent.get("task_id") == task_id
    ]
    assert len(matches) == 1
    assert matches[0]["intent_id"].startswith(f"project_pending_task_state:{task_id}:")
    return matches[0]


class FakeCheckpointFailingGraph:
    async def ainvoke(self, state, config, *, context):
        raise SQLAlchemyError("checkpoint write failed")


class FakePendingFallbackGraph:
    def __init__(self):
        self.calls = []

    async def ainvoke(self, state, config, *, context):
        self.calls.append({"state": state, "config": config, "context": context})
        return {
            **state,
            "handled": True,
            "has_active_task": bool(context.task),
            "task_projection": {"id": context.task.id} if context.task else {},
            "events": [{"event": "final", "content": "fallback ok"}],
            "assistant_content": "fallback ok",
        }


def _state(task):
    return {
        "db": object(),
        "session": SimpleNamespace(id=3),
        "task_snapshot": agent_task_snapshot(task),
        "turn_input": AgentTurnInput.text("补充采购类型"),
        "content": "补充采购类型",
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "authorization": "Bearer test",
        "events": [],
    }


def _state_without_task():
    return {
        "db": object(),
        "session": SimpleNamespace(id=3, context_json={}),
        "task_snapshot": {},
        "turn_input": AgentTurnInput.text("张总说改成增购 20 个了"),
        "content": "张总说改成增购 20 个了",
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "authorization": "Bearer test",
        "events": [],
    }


def _serialized_task_candidate(task: object) -> dict:
    return agent_task_snapshot(task)


def _state_with_suspended_candidates(candidates: list[dict]):
    return {
        **_state_without_task(),
        "suspended_candidates": candidates,
    }


async def _start_continuation(service, state, *, side_effects=None):
    graph_side_effects = side_effects or PendingTaskGraphSideEffects(task=state.get("task_snapshot"))
    result = await service.run(state, side_effects=graph_side_effects)
    assert graph_side_effects.checkpoint_ref is not None
    return result, graph_side_effects.checkpoint_ref


def _resume_state(state, continuation, resume_payload):
    return {
        **state,
        "continuation_ref": continuation,
        "resume_payload": resume_payload,
    }


def test_pending_task_snapshot_builds_readable_opportunity_draft_summary():
    task = SimpleNamespace(
        id=201,
        intent="CREATE_OPPORTUNITY",
        target_type="customer",
        target_id=17,
        summary="等待确认执行：collect_opportunity_fields",
        status=AgentTaskStatus.SUSPENDED,
        created_time=None,
        updated_time=None,
        input_json={
            "customer_id": 17,
            "opportunity": {
                "total_amount": 300000,
                "user_count": 50,
                "license_type": "SUBSCRIPTION",
            },
            "missing_fields": ["expected_closing_date"],
        },
        state_json={
            "action": "collect_opportunity_fields",
            "customer": {"id": 17, "account_name": "广州睿狐科技有限公司"},
        },
    )

    snapshot = session_state._pending_task_snapshot(task)

    assert snapshot["display_summary"] == "补商机信息｜广州睿狐科技有限公司｜缺：预计成交日期、采购方式"


def test_pending_task_snapshot_hides_internal_customer_activity_action_name():
    task = SimpleNamespace(
        id=301,
        intent="CREATE_CUSTOMER_ACTIVITY",
        target_type="customer",
        target_id=17,
        summary="等待确认执行：create_customer_activity",
        status=AgentTaskStatus.SUSPENDED,
        created_time=None,
        updated_time=None,
        input_json={
            "payload": {
                "customer": {"id": 17, "account_name": "广州睿狐科技有限公司"},
                "content": "张总说今天可以开始签合同了",
            },
        },
        state_json={"action": "create_customer_activity"},
    )

    snapshot = session_state._pending_task_snapshot(task)

    assert snapshot["display_summary"] == "确认记录跟进｜广州睿狐科技有限公司｜张总说今天可以开始签合同了"
    assert "create_customer_activity" not in snapshot["display_summary"]


@pytest.mark.asyncio
async def test_pending_task_graph_ends_after_preflight_new_flow():
    task = SimpleNamespace(id=101)
    preflight = FakePreflightGraphService(FakePreflightResult(
        task=None,
        switch_notice="切换处理新流程。",
        suspended_task=task,
        suspend_reason="新客户流程",
        events=[{"event": "pending_task_interrupted"}],
    ))
    interaction = FakeInteractionGraphService(FakeInteractionResult())

    side_effects = PendingTaskGraphSideEffects(task=task)
    result = await PendingTaskGraphService(
        preflight_graph_service=preflight,
        interaction_graph_service=interaction,
    ).run(_state(task), side_effects=side_effects)

    assert result["has_active_task"] is False
    assert result["suspended_task_id"] == 101
    assert side_effects.task is None
    assert side_effects.suspended_task == agent_task_snapshot(task)
    assert result["switch_notice"] == "切换处理新流程。"
    assert result["events"] == [{"event": "pending_task_interrupted"}]
    assert interaction.calls == []


@pytest.mark.asyncio
async def test_pending_task_graph_result_exposes_json_projection_not_runtime_objects():
    task = SimpleNamespace(id=101)
    preflight = FakePreflightGraphService(FakePreflightResult(
        task=task,
        events=[{"event": "pending_interruption_assessed"}],
    ))
    interaction = FakeInteractionGraphService(FakeInteractionResult(
        handled=True,
        assistant_content="请确认是否创建商机？",
        remember_pending_task=True,
        events=[{"event": "confirmation_required"}, {"event": "final"}],
    ))
    emitted_events = []

    async def emit_event(event):
        emitted_events.append(event)

    side_effects = PendingTaskGraphSideEffects(task=task, event_sink=emit_event)

    result = await PendingTaskGraphService(
        preflight_graph_service=preflight,
        interaction_graph_service=interaction,
    ).run(_state(task), side_effects=side_effects)

    assert "task" not in result
    assert "resumed_task" not in result
    assert "suspended_task" not in result
    assert "preflight_result_object" not in result
    assert "interaction_result_object" not in result
    assert result["task_projection"] == {"id": 101}
    assert side_effects.task == agent_task_snapshot(task)
    assert side_effects.preflight_result is preflight.result
    assert side_effects.interaction_result is interaction.result


@pytest.mark.asyncio
async def test_pending_task_graph_runs_interaction_after_continue_pending():
    task = SimpleNamespace(id=101)
    preflight = FakePreflightGraphService(FakePreflightResult(
        task=task,
        events=[{"event": "pending_interruption_assessed"}],
    ))
    interaction = FakeInteractionGraphService(FakeInteractionResult(
        handled=True,
        assistant_content="请确认是否创建商机？",
        remember_pending_task=True,
        events=[{"event": "confirmation_required"}, {"event": "final"}],
    ))

    side_effects = PendingTaskGraphSideEffects(task=task)
    result = await PendingTaskGraphService(
        preflight_graph_service=preflight,
        interaction_graph_service=interaction,
    ).run(_state(task), side_effects=side_effects)

    assert result["handled"] is True
    assert result["has_active_task"] is True
    assert result["task_projection"] == {"id": 101}
    assert side_effects.task == agent_task_snapshot(task)
    assert result["assistant_content"] == "请确认是否创建商机？"
    assert result["remember_pending_task"] is True
    assert result["events"] == [
        {"event": "pending_interruption_assessed"},
        {"event": "confirmation_required"},
        {"event": "final"},
    ]
    interaction_task = interaction.calls[0]["task"]
    assert isinstance(interaction_task, RuntimeAgentTaskView)
    assert interaction_task.source_task == agent_task_snapshot(task)


@pytest.mark.asyncio
async def test_pending_task_graph_run_with_trace_exposes_langgraph_steps():
    task = SimpleNamespace(id=101)
    preflight = FakePreflightGraphService(FakePreflightResult(
        task=task,
        events=[{"event": "pending_interruption_assessed"}],
    ))
    interaction = FakeInteractionGraphService(FakeInteractionResult(
        handled=True,
        assistant_content="请确认是否创建商机？",
        remember_pending_task=True,
        events=[{"event": "confirmation_required"}, {"event": "final"}],
    ))

    emitted_events = []

    async def emit_event(event):
        emitted_events.append(event)

    side_effects = PendingTaskGraphSideEffects(task=task, event_sink=emit_event)
    result = await PendingTaskGraphService(
        preflight_graph_service=preflight,
        interaction_graph_service=interaction,
    ).run_with_trace(_state(task), side_effects=side_effects)

    assert result["events"] == [
        {"event": "agent_step", "step": "preflight", "status": "started", "content": "识别确认或取消意图"},
        {"event": "pending_interruption_assessed"},
        {"event": "agent_step", "step": "preflight", "status": "completed", "content": "识别确认或取消意图"},
        {"event": "agent_step", "step": "plan_interaction", "status": "started", "content": "整理需要确认或补充的信息"},
        {"event": "confirmation_required"},
        {"event": "final"},
        {"event": "agent_step", "step": "plan_interaction", "status": "completed", "content": "整理需要确认或补充的信息"},
    ]
    assert emitted_events == []
    assert side_effects.task == agent_task_snapshot(task)
    interaction_task = interaction.calls[0]["task"]
    assert isinstance(interaction_task, RuntimeAgentTaskView)
    assert interaction_task.source_task == agent_task_snapshot(task)


@pytest.mark.asyncio
async def test_pending_task_graph_run_with_trace_reconciles_checkpointed_authoritative_state():
    task = SimpleNamespace(id=101)
    preflight = FakePreflightGraphService(FakePreflightResult(
        task=task,
        events=[{"event": "pending_interruption_assessed"}],
    ))
    interaction = FakeInteractionGraphService(FakeInteractionResult(
        handled=True,
        assistant_content="请确认是否创建商机？",
        remember_pending_task=True,
        events=[{"event": "confirmation_required"}, {"event": "final"}],
    ))

    result = await PendingTaskGraphService(
        preflight_graph_service=preflight,
        interaction_graph_service=interaction,
        checkpointer=InMemorySaver(),
    ).run_with_trace(_state(task))

    assert result["handled"] is True
    assert result["assistant_content"] == "请确认是否创建商机？"
    assert result["remember_pending_task"] is True
    assert result["task_projection"] == {"id": 101}
    event_names = [event["event"] for event in result["events"]]
    assert "pending_interruption_assessed" in event_names
    assert "confirmation_required" in event_names
    assert "final" in event_names
    assert event_names.index("pending_interruption_assessed") < event_names.index("confirmation_required")
    assert event_names.index("confirmation_required") < event_names.index("final")
    interaction_task = interaction.calls[0]["task"]
    assert isinstance(interaction_task, RuntimeAgentTaskView)
    assert interaction_task.source_task == agent_task_snapshot(task)


@pytest.mark.asyncio
async def test_pending_task_graph_run_with_trace_reconciles_new_turn_after_existing_checkpoint(monkeypatch):
    task = SimpleNamespace(
        id=202,
        status=AgentTaskStatus.SUSPENDED,
        intent="CREATE_OPPORTUNITY",
        target_type="customer",
        target_id=101,
        summary="等待确认执行：create_opportunity",
        input_json={},
        state_json={"action": "create_opportunity", "payload": {"opportunity": {"user_count": 10}}},
    )

    async def fake_assess(db, *, team_id, user_id, session, task, user_message):
        return AgentTurnRelationDecision(
            relation="RESUME_SUSPENDED_DRAFT",
            confidence=0.93,
            target_task_id=202,
            detected_intent="CREATE_OPPORTUNITY",
            reason="用户在修改最近暂停的商机草稿。",
        )

    monkeypatch.setattr(pending_graph_module.session_state, "_assess_turn_relation", fake_assess)

    monkeypatch.setattr(
        pending_graph_module.session_state,
        "_resume_suspended_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("graph must not persist task resume")),
    )
    interaction = FakeInteractionGraphService(FakeInteractionResult(
        handled=True,
        assistant_content="商机信息齐了，请确认。",
        remember_pending_task=True,
        events=[{"event": "confirmation_required"}, {"event": "final"}],
    ))
    service = PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult()),
        interaction_graph_service=interaction,
        checkpointer=InMemorySaver(),
    )

    await service.run(_state_without_task())
    side_effects = PendingTaskGraphSideEffects()
    result = await service.run_with_trace(
        _state_with_suspended_candidates([{
            "id": 202,
            "task_key": "task_202",
            "status": AgentTaskStatus.SUSPENDED,
            "intent": "CREATE_OPPORTUNITY",
            "target_type": "customer",
            "target_id": 101,
            "summary": "等待确认执行：create_opportunity",
            "input_json": {},
            "state_json": {"action": "create_opportunity", "payload": {"opportunity": {"user_count": 10}}},
        }]),
        side_effects=side_effects,
    )

    assert result["handled"] is True
    assert result["assistant_content"] == "商机信息齐了，请确认。"
    assert result["task_projection"]["id"] == 202
    assert isinstance(side_effects.task, dict)
    assert side_effects.task["id"] == task.id
    assert side_effects.resumed_task is None
    projection = _task_projection_effect(result, 202)
    assert projection["expected_task"]["status"] == AgentTaskStatus.SUSPENDED
    assert projection["task_update"]["status"] == AgentTaskStatus.WAITING_USER
    assert task.status == AgentTaskStatus.SUSPENDED
    json.dumps(result["effect_intents"])
    event_names = [event["event"] for event in result["events"]]
    assert "turn_relation_classified" in event_names
    assert "suspended_task_resumed" in event_names
    assert "confirmation_required" in event_names
    assert "final" in event_names


@pytest.mark.asyncio
async def test_pending_task_graph_returns_progress_events_without_calling_transport_sink():
    task = SimpleNamespace(id=101)
    preflight = FakePreflightGraphService(FakePreflightResult(
        task=task,
        handled=True,
        assistant_content="请确认。",
        events=[{"event": "confirmation_required"}, {"event": "final", "content": "请确认。"}],
    ))
    service = PendingTaskGraphService(
        preflight_graph_service=preflight,
        interaction_graph_service=FakeInteractionGraphService(FakeInteractionResult()),
        checkpointer=InMemorySaver(),
    )

    async def forbidden_transport(_event):
        raise AssertionError("LangGraph execution must return events instead of publishing transport side effects")

    result = await service.run_with_trace(
        _state(task),
        side_effects=PendingTaskGraphSideEffects(task=task, event_sink=forbidden_transport),
    )

    event_names = [event["event"] for event in result["events"]]
    assert "confirmation_required" in event_names
    assert "final" in event_names


@pytest.mark.asyncio
async def test_pending_task_graph_internal_state_keeps_runtime_objects_in_context():
    task = SimpleNamespace(id=101)
    confirmation_decision = AgentConfirmationIntentDecision(
        intent="unknown",
        confidence=0.82,
        reason="用户在补充字段，不是确认执行。",
    )
    preflight = FakePreflightGraphService(FakePreflightResult(
        task=task,
        confirmation_decision=confirmation_decision,
        events=[{"event": "pending_interruption_assessed"}],
    ))
    interaction = FakeInteractionGraphService(FakeInteractionResult(
        handled=True,
        assistant_content="请确认是否创建商机？",
        remember_pending_task=True,
        events=[{"event": "confirmation_required"}, {"event": "final"}],
    ))
    task_snapshot = agent_task_snapshot(task)
    side_effects = PendingTaskGraphSideEffects(task=task_snapshot)
    service = PendingTaskGraphService(
        preflight_graph_service=preflight,
        interaction_graph_service=interaction,
    )

    state = await service._graph.ainvoke(
        {
            "has_active_task": True,
            "task_snapshot": task_snapshot,
            "turn_input": AgentTurnInput.text("补充采购类型").model_dump(mode="json"),
            "task_projection": {"id": 101},
            "content": "补充采购类型",
            "team_id": 1,
            "user_id": 2,
            "session_id": 3,
            "authorization": "Bearer test",
            "events": [],
        },
        context=PendingTaskRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=3),
            task=RuntimeAgentTaskView(task_snapshot),
            turn_input=AgentTurnInput.text("补充采购类型"),
            content="补充采购类型",
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
    assert state["turn_input"] == {
        "kind": "text",
        "content": "补充采购类型",
        "source": "web",
        "provider": None,
        "metadata": {},
    }
    assert state["task_snapshot"] == task_snapshot
    assert not isinstance(state["turn_input"], AgentTurnInput)
    assert state["confirmation_decision"] == {
        "intent": "unknown",
        "confidence": 0.82,
        "reason": "用户在补充字段，不是确认执行。",
    }
    assert side_effects.task == agent_task_snapshot(task)
    assert side_effects.confirmation_decision is confirmation_decision
    assert side_effects.interaction_result is interaction.result


@pytest.mark.asyncio
async def test_pending_task_graph_checkpoints_by_session_and_task_thread():
    task = SimpleNamespace(id=101)
    service = PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult(
            task=task,
            events=[{"event": "pending_interruption_assessed"}],
        )),
        interaction_graph_service=FakeInteractionGraphService(FakeInteractionResult(
            handled=True,
            assistant_content="请确认是否创建商机？",
            remember_pending_task=True,
            events=[{"event": "confirmation_required"}, {"event": "final"}],
        )),
        checkpointer=InMemorySaver(),
    )

    initial_result, continuation = await _start_continuation(service, _state(task))
    snapshot = await service._graph.aget_state(pending_task_checkpoint_config(continuation))

    assert build_pending_task_thread_id(team_id=1, user_id=2, session_id=3, task_id=101) == (
        "crm_agent_pending:1:2:3:101"
    )
    assert continuation["continuation_id"]
    assert continuation["thread_id"].startswith("crm_agent_pending:1:2:3:101:")
    assert snapshot.values["handled"] is True
    assert snapshot.values["task_projection"] == {"id": 101}
    assert snapshot.values["interaction_result"] == {
        "handled": True,
        "remember_pending_task": True,
        "has_selected_customer": False,
        "event_count": 2,
    }
    assert snapshot.values["current_interrupt"]["type"] == "confirm"
    assert snapshot.values["current_interrupt"]["source_event"] == "confirmation_required"
    assert snapshot.next == ("wait_interaction_interrupt",)


@pytest.mark.asyncio
async def test_pending_task_graph_resumes_native_interaction_interrupt():
    task = SimpleNamespace(id=101)
    service = PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult(
            task=task,
            events=[{"event": "pending_interruption_assessed"}],
        )),
        interaction_graph_service=FakeInteractionGraphService(FakeInteractionResult(
            handled=True,
            assistant_content="请确认是否创建商机？",
            remember_pending_task=True,
            events=[{
                "event": "confirmation_required",
                "task_id": 101,
                "action": "create_opportunity",
                "payload": {"customer_id": 7},
            }, {"event": "final"}],
        )),
        checkpointer=InMemorySaver(),
    )
    initial_result, continuation = await _start_continuation(service, _state(task))

    state = _resume_state(_state(task), continuation, {"action": "approve", "content": "确认"})
    result = await service.run(state)

    assert result["resume_payload"] == {"action": "approve", "content": "确认"}
    assert result["events"][-1] == {
        "event": "pending_task_interaction_interrupt_resumed",
        "resume_action": "approve",
    }
    assert result["confirmation_decision"] == {
        "intent": "confirm",
        "confidence": 1.0,
        "reason": "用户通过 LangGraph interrupt resume 批准执行。",
    }


@pytest.mark.asyncio
async def test_pending_task_graph_resumes_native_interaction_interrupt_after_service_restart():
    task = SimpleNamespace(id=101)
    checkpointer = InMemorySaver()
    first_interaction = FakeInteractionGraphService(FakeInteractionResult(
        handled=True,
        assistant_content="请确认是否创建商机？",
        remember_pending_task=True,
        events=[{
            "event": "confirmation_required",
            "task_id": 101,
            "action": "create_opportunity",
            "payload": {"customer_id": 7},
        }, {"event": "final"}],
    ))
    first_service = PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult(
            task=task,
            events=[{"event": "pending_interruption_assessed"}],
        )),
        interaction_graph_service=first_interaction,
        checkpointer=checkpointer,
    )
    _, continuation = await _start_continuation(first_service, _state(task))

    resumed_preflight = FakePreflightGraphService(FakePreflightResult(task=task))
    resumed_interaction = FakeInteractionGraphService(FakeInteractionResult())
    resumed_service = PendingTaskGraphService(
        preflight_graph_service=resumed_preflight,
        interaction_graph_service=resumed_interaction,
        checkpointer=checkpointer,
    )
    state = _resume_state(_state(task), continuation, {"action": "approve", "content": "确认"})
    result = await resumed_service.run(state)

    assert resumed_preflight.calls == []
    assert resumed_interaction.calls == []
    assert result["resume_payload"] == {"action": "approve", "content": "确认"}
    assert result["confirmation_decision"] == {
        "intent": "confirm",
        "confidence": 1.0,
        "reason": "用户通过 LangGraph interrupt resume 批准执行。",
    }
    assert result["current_interrupt"] is None


@pytest.mark.asyncio
async def test_pending_task_graph_rejects_native_confirmation_interrupt_without_text_reclassification(monkeypatch):
    workflow = action_workflow.required_write_contract(action="create_opportunity")
    task = SimpleNamespace(
        id=101,
        status=AgentTaskStatus.WAITING_USER,
        state_json={
            "workflow": workflow,
            "payload": {"workflow": workflow},
        },
    )
    monkeypatch.setattr(
        pending_graph_module.workflow_action_ledger,
        "mark_action_cancelled",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("graph must not write workflow ledger")
        ),
    )
    preflight = FakePreflightGraphService(FakePreflightResult(
        task=task,
        events=[{"event": "pending_interruption_assessed"}],
    ))
    interaction = FakeInteractionGraphService(FakeInteractionResult(
        handled=True,
        assistant_content="请确认是否创建商机？",
        remember_pending_task=True,
        events=[{
            "event": "confirmation_required",
            "task_id": 101,
            "action": "create_opportunity",
            "workflow": workflow,
            "payload": {"customer_id": 7},
        }, {"event": "final"}],
    ))
    service = PendingTaskGraphService(
        preflight_graph_service=preflight,
        interaction_graph_service=interaction,
        checkpointer=InMemorySaver(),
    )
    initial_result, continuation = await _start_continuation(service, _state(task))

    state = _resume_state(_state(task), continuation, {"action": "reject", "content": "先不处理"})
    result = await service.run(state)

    assert len(preflight.calls) == 1
    assert len(interaction.calls) == 1
    assert result["handled"] is True
    assert result["clear_pending_task_id"] == 101
    assert result["confirmation_decision"] == {
        "intent": "reject",
        "confidence": 1.0,
        "reason": "用户通过 LangGraph interrupt resume 拒绝执行。",
    }
    assert result["events"][-2:] == [
        {"event": "task_cancelled", "task_id": 101, "content": "好嘞，这一步先放着。"},
        {"event": "final", "content": "好嘞，这一步先放着。"},
    ]
    assert result["effect_intents"] == [{
        "intent_id": f"cancel_workflow_action:{workflow['action_id']}:101",
        "intent_type": "cancel_workflow_action",
        "task_id": 101,
        "workflow": workflow,
        "expected_task": {
            "status": AgentTaskStatus.WAITING_USER,
            "workflow": workflow,
            "payload_workflow": workflow,
        },
        "expected_ledger": {
            "workflow_id": workflow["workflow_id"],
            "action_id": workflow["action_id"],
            "task_id": 101,
            "status": "WAITING_USER",
        },
        "reason": "用户通过 LangGraph interrupt resume 拒绝执行。",
        "source_type": "pending_resume",
        "decision": {
            "decision": "reject",
            "resume_reason": "write_confirmation",
            "content": "先不处理",
        },
    }]
    assert task.state_json["workflow"]["status"] == action_workflow.STATUS_WAITING_USER
    assert task.state_json["payload"]["workflow"]["status"] == action_workflow.STATUS_WAITING_USER
    json.dumps(result["effect_intents"], ensure_ascii=False)


@pytest.mark.asyncio
async def test_pending_task_graph_skips_optional_suggestion_without_cancelling_required_workflow():
    workflow = action_workflow.optional_suggestion_contract(action="collect_opportunity_fields")
    task = SimpleNamespace(id=101)
    interaction = FakeInteractionGraphService(FakeInteractionResult(
        handled=True,
        assistant_content="请补充商机信息。",
        remember_pending_task=True,
        events=[{
            "event": "confirmation_required",
            "task_id": 101,
            "action": "collect_opportunity_fields",
            "content": "请补充商机信息。",
            "workflow": workflow,
            "payload": {"customer_id": 7, "workflow": workflow},
        }, {"event": "final"}],
    ))
    service = PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult(
            task=task,
            events=[{"event": "pending_interruption_assessed"}],
        )),
        interaction_graph_service=interaction,
        checkpointer=InMemorySaver(),
    )
    _, continuation = await _start_continuation(service, _state(task))

    state = _resume_state(_state(task), continuation, {"action": "skip_current_action", "content": "先不管"})
    side_effects = PendingTaskGraphSideEffects(task=task)
    result = await service.run(state, side_effects=side_effects)

    assert result["handled"] is True
    assert result["has_active_task"] is False
    assert result["clear_pending_task_id"] == 101
    assert result["suspension_kind"] == "dismissed"
    assert result["suspend_reason"] == "先不管"
    assert result["assistant_content"] == "已跳过补商机信息建议。"
    assert result["events"][-2:] == [
        {
            "event": "workflow_action_skipped",
            "content": "已跳过补商机信息建议。",
            "reason": "先不管",
            "action_id": workflow["action_id"],
            "action_type": "collect_opportunity_fields",
            "task_id": 101,
        },
        {"event": "final", "content": "已跳过补商机信息建议。"},
    ]
    assert side_effects.task is None
    assert side_effects.suspended_task == agent_task_snapshot(task)


@pytest.mark.asyncio
async def test_pending_task_graph_routes_native_confirmation_edit_back_to_interaction_graph():
    task = SimpleNamespace(id=101)
    interaction = FakeInteractionGraphService(FakeInteractionResult(
        handled=True,
        assistant_content="请确认是否创建商机？",
        remember_pending_task=True,
        events=[{
            "event": "confirmation_required",
            "task_id": 101,
            "action": "create_opportunity",
            "payload": {"customer_id": 7},
        }, {"event": "final"}],
    ))
    service = PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult(
            task=task,
            events=[{"event": "pending_interruption_assessed"}],
        )),
        interaction_graph_service=interaction,
        checkpointer=InMemorySaver(),
    )
    _, continuation = await _start_continuation(service, _state(task))

    state = _state(task)
    state["continuation_ref"] = continuation
    state["content"] = "金额改成 30 万"
    state["turn_input"] = AgentTurnInput.text("金额改成 30 万")
    state["resume_payload"] = {"action": "edit", "content": "金额改成 30 万"}
    result = await service.run(state)

    assert len(interaction.calls) == 2
    assert interaction.calls[1]["content"] == "金额改成 30 万"
    assert result["resume_route"] == "interaction"


@pytest.mark.asyncio
async def test_pending_task_graph_applies_projected_pending_switch_approval_without_subgraph_interrupt():
    task = SimpleNamespace(id=101)
    preflight = FakePreflightGraphService(FakePreflightResult(
        task=task,
        events=[{"event": "pending_interruption_assessed"}],
    ))
    interaction = FakeInteractionGraphService(FakeInteractionResult())
    side_effects = PendingTaskGraphSideEffects(task=task)

    state = _state(task)
    state["projected_resume_payload"] = {
        "action": "approve",
        "content": "切换新流程",
        "interrupt_reason": "pending_flow_switch_confirmation",
    }
    result = await PendingTaskGraphService(
        preflight_graph_service=preflight,
        interaction_graph_service=interaction,
        checkpointer=InMemorySaver(),
    ).run(state, side_effects=side_effects)

    assert preflight.calls == []
    assert interaction.calls == []
    assert result["handled"] is True
    assert result["has_active_task"] is False
    assert result["task_projection"] == {}
    assert result["suspended_task_id"] == 101
    assert result["assistant_content"] == "这条像是新的流程。我先把刚才那一步放着，切过来处理。"
    assert result["switch_notice"] == "这条像是新的流程。我先把刚才那一步放着，切过来处理。"
    assert result["events"] == [
        {
            "event": "pending_task_interrupted",
            "content": result["switch_notice"],
            "suspended_task_id": 101,
        },
        {"event": "final", "content": result["switch_notice"]},
    ]
    assert side_effects.task is None
    assert side_effects.suspended_task == agent_task_snapshot(task)


@pytest.mark.asyncio
async def test_pending_task_graph_routes_projected_pending_switch_rejection_to_interaction():
    task = SimpleNamespace(id=101)
    preflight = FakePreflightGraphService(FakePreflightResult(
        task=task,
        events=[{"event": "pending_interruption_assessed"}],
    ))
    interaction = FakeInteractionGraphService(FakeInteractionResult(
        handled=True,
        assistant_content="继续补充当前任务。",
        events=[{"event": "interaction_planned"}],
    ))
    side_effects = PendingTaskGraphSideEffects(task=task)

    state = _state(task)
    state["content"] = "继续刚才"
    state["turn_input"] = AgentTurnInput.text("继续刚才")
    state["projected_resume_payload"] = {
        "action": "reject",
        "content": "继续刚才",
        "interrupt_reason": "pending_flow_switch_confirmation",
    }
    result = await PendingTaskGraphService(
        preflight_graph_service=preflight,
        interaction_graph_service=interaction,
        checkpointer=InMemorySaver(),
    ).run(state, side_effects=side_effects)

    assert preflight.calls == []
    assert len(interaction.calls) == 1
    assert interaction.calls[0]["content"] == "继续刚才"
    assert result["resume_route"] == "interaction"
    assert result["handled"] is True
    assert result["events"] == [{"event": "interaction_planned"}]


@pytest.mark.asyncio
async def test_pending_task_graph_preflights_projected_missing_fields_resume_before_native_field_node(monkeypatch):
    task = SimpleNamespace(
        id=101,
        input_json={"opportunity": {"amount": 300000}},
        state_json={"action": "collect_opportunity_fields"},
    )
    interaction = PendingInteractionGraphService()

    async def fake_apply(db, task_arg, content):
        task_arg.input_json = {"opportunity": {"amount": 300000, "expected_closing_date": "2026-08-30"}}
        return True, "商机信息齐了，请确认是否创建？"

    monkeypatch.setattr(
        opportunity_fields,
        "_apply_opportunity_fields",
        fake_apply,
    )

    state = _state(task)
    state["content"] = "预计 8 月底成交"
    state["turn_input"] = AgentTurnInput.text("预计 8 月底成交")
    state["projected_resume_payload"] = {
        "action": "submit_fields",
        "content": "预计 8 月底成交",
        "interrupt_reason": "missing_required_fields",
    }

    result = await PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult(task=task)),
        interaction_graph_service=interaction,
        checkpointer=InMemorySaver(),
    ).run(state)

    assert result["resume_route"] == "preflight"
    assert result["handled"] is True
    assert result["remember_pending_task"] is True
    assert result["events"] == [
        {
            "event": "confirmation_required",
            "task_id": 101,
            "content": "商机信息齐了，请确认是否创建？",
            "payload": {"opportunity": {"amount": 300000, "expected_closing_date": "2026-08-30"}},
        },
        {"event": "final", "content": "商机信息齐了，请确认是否创建？"},
    ]
    projection = _task_projection_effect(result, 101)
    assert projection["expected_task"]["input_json"] == {
        "opportunity": {"amount": 300000},
    }
    assert projection["task_update"]["input_json"] == {
        "opportunity": {"amount": 300000, "expected_closing_date": "2026-08-30"},
    }
    assert task.input_json == {"opportunity": {"amount": 300000}}


@pytest.mark.asyncio
async def test_pending_task_graph_resumes_native_missing_fields_interrupt_after_service_restart(monkeypatch):
    task = SimpleNamespace(
        id=101,
        input_json={"opportunity": {"amount": 300000}},
        state_json={"action": "collect_opportunity_fields"},
    )
    checkpointer = InMemorySaver()
    first_interaction = FakeInteractionGraphService(FakeInteractionResult(
        handled=True,
        assistant_content="还需要预计成交日期。",
        remember_pending_task=True,
        events=[{
            "event": "opportunity_fields_required",
            "task_id": 101,
            "content": "还需要预计成交日期。",
            "payload": {"opportunity": {"amount": 300000}},
        }, {"event": "final", "content": "还需要预计成交日期。"}],
    ))
    first_service = PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult(
            task=task,
            events=[{"event": "pending_interruption_assessed"}],
        )),
        interaction_graph_service=first_interaction,
        checkpointer=checkpointer,
    )

    _, continuation = await _start_continuation(first_service, _state(task))
    snapshot = await first_service._graph.aget_state(pending_task_checkpoint_config(continuation))

    assert snapshot.interrupts
    assert snapshot.values["current_interrupt"]["reason"] == "missing_required_fields"
    assert snapshot.next == ("wait_interaction_interrupt",)

    async def fake_apply(db, task_arg, content):
        task_arg.input_json = {"opportunity": {"amount": 300000, "expected_closing_date": "2026-08-30"}}
        return True, "商机信息齐了，请确认是否创建？"

    monkeypatch.setattr(
        opportunity_fields,
        "_apply_opportunity_fields",
        fake_apply,
    )

    resumed_preflight = FakePreflightGraphService(FakePreflightResult(task=task))
    resumed_interaction = PendingInteractionGraphService()
    resumed_service = PendingTaskGraphService(
        preflight_graph_service=resumed_preflight,
        interaction_graph_service=resumed_interaction,
        checkpointer=checkpointer,
    )
    state = _state(task)
    state["continuation_ref"] = continuation
    state["content"] = "预计 8 月底成交"
    state["turn_input"] = AgentTurnInput.text("预计 8 月底成交")
    state["resume_payload"] = {"action": "submit_fields", "content": "预计 8 月底成交"}

    result = await resumed_service.run(state)

    assert resumed_preflight.calls == []
    assert result["resume_route"] == "field_resume"
    assert result["handled"] is True
    assert result["remember_pending_task"] is True
    assert result["current_interrupt"]["reason"] == "write_confirmation"
    assert "__interrupt__" in result
    assert result["__interrupt__"][0].value == result["current_interrupt"]
    assert result["events"][-3:] == [
        {"event": "pending_task_interaction_interrupt_resumed", "resume_action": "submit_fields"},
        {
            "event": "confirmation_required",
            "task_id": 101,
            "content": "商机信息齐了，请确认是否创建？",
            "payload": {"opportunity": {"amount": 300000, "expected_closing_date": "2026-08-30"}},
        },
        {"event": "final", "content": "商机信息齐了，请确认是否创建？"},
    ]
    resumed_snapshot = await resumed_service._graph.aget_state(pending_task_checkpoint_config(continuation))
    assert resumed_snapshot.interrupts
    assert resumed_snapshot.values["current_interrupt"]["reason"] == "write_confirmation"
    assert resumed_snapshot.next == ("wait_interaction_interrupt",)


@pytest.mark.asyncio
async def test_pending_task_graph_routes_choice_resume_to_native_choice_node(monkeypatch):
    task = SimpleNamespace(
        id=101,
        status=AgentTaskStatus.WAITING_USER,
        input_json={},
        state_json={"action": "select_customer_for_opportunity"},
    )
    selected_customer = {"id": 7, "account_name": "广州睿狐科技有限公司"}
    interaction = PendingInteractionGraphService()

    monkeypatch.setattr(
        selection,
        "_is_business_selection_task",
        lambda task_arg: False,
    )
    monkeypatch.setattr(
        selection,
        "_is_customer_selection_task",
        lambda task_arg: getattr(task_arg, "id", None) == task.id,
    )

    async def fake_apply_customer_selection(db, task_arg, content, *, team_id, user_id, session_id, authorization, metadata):
        assert metadata == {"selected_customer_id": 7}
        task_arg.target_id = 7
        task_arg.summary = "等待确认创建广州睿狐商机"
        task_arg.state_json = {
            "action": "create_opportunity",
            "customer": selected_customer,
        }
        return selected_customer, "已选择客户「广州睿狐科技有限公司」。请确认是否创建商机？"

    monkeypatch.setattr(
        selection,
        "_apply_customer_selection",
        fake_apply_customer_selection,
    )

    state = _state(task)
    state["content"] = "选择广州睿狐"
    state["turn_input"] = AgentTurnInput.text("选择广州睿狐", metadata={"selected_customer_id": 7})
    state["projected_resume_payload"] = {
        "action": "select",
        "content": "选择广州睿狐",
        "interrupt_reason": "business_object_disambiguation",
        "metadata": {"selected_customer_id": 7},
    }

    result = await PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult(task=task)),
        interaction_graph_service=interaction,
        checkpointer=InMemorySaver(),
    ).run(state)

    assert result["resume_route"] == "choice_resume"
    assert result["selected_customer"] == selected_customer
    assert result["remember_pending_task"] is True
    assert result["events"][0]["event"] == "customer_selected"
    projection = _task_projection_effect(result, 101)
    assert projection["task_update"] == {
        "target_id": 7,
        "summary": "等待确认创建广州睿狐商机",
        "state_json": {
            "action": "create_opportunity",
            "customer": selected_customer,
            "source_event": "confirmation_required",
        },
    }
    assert getattr(task, "target_id", None) is None


@pytest.mark.asyncio
async def test_pending_task_graph_resumes_native_choice_interrupt_after_service_restart(monkeypatch):
    task = SimpleNamespace(
        id=101,
        status=AgentTaskStatus.WAITING_USER,
        input_json={},
        state_json={"action": "select_customer_for_opportunity"},
    )
    selected_customer = {"id": 7, "account_name": "广州睿狐科技有限公司"}
    checkpointer = InMemorySaver()
    first_interaction = FakeInteractionGraphService(FakeInteractionResult(
        handled=True,
        assistant_content="请选择客户。",
        remember_pending_task=True,
        events=[{
            "event": "customer_selection_required",
            "task_id": 101,
            "content": "请选择客户。",
            "customers": [selected_customer],
        }, {"event": "final", "content": "请选择客户。"}],
    ))
    first_service = PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult(
            task=task,
            events=[{"event": "pending_interruption_assessed"}],
        )),
        interaction_graph_service=first_interaction,
        checkpointer=checkpointer,
    )

    _, continuation = await _start_continuation(first_service, _state(task))
    snapshot = await first_service._graph.aget_state(pending_task_checkpoint_config(continuation))

    assert snapshot.interrupts
    assert snapshot.values["current_interrupt"]["reason"] == "business_object_disambiguation"
    assert snapshot.next == ("wait_interaction_interrupt",)

    monkeypatch.setattr(
        selection,
        "_is_business_selection_task",
        lambda task_arg: False,
    )
    monkeypatch.setattr(
        selection,
        "_is_customer_selection_task",
        lambda task_arg: getattr(task_arg, "id", None) == task.id,
    )

    async def fake_apply_customer_selection(db, task_arg, content, *, team_id, user_id, session_id, authorization, metadata):
        assert metadata == {"selected_customer_id": 7}
        return selected_customer, "已选择客户「广州睿狐科技有限公司」。请确认是否创建商机？"

    monkeypatch.setattr(
        selection,
        "_apply_customer_selection",
        fake_apply_customer_selection,
    )

    resumed_preflight = FakePreflightGraphService(FakePreflightResult(task=task))
    resumed_interaction = PendingInteractionGraphService()
    resumed_service = PendingTaskGraphService(
        preflight_graph_service=resumed_preflight,
        interaction_graph_service=resumed_interaction,
        checkpointer=checkpointer,
    )
    state = _state(task)
    state["continuation_ref"] = continuation
    state["content"] = "选择广州睿狐"
    state["turn_input"] = AgentTurnInput.text("选择广州睿狐", metadata={"selected_customer_id": 7})
    state["resume_payload"] = {
        "action": "select",
        "content": "选择广州睿狐",
        "metadata": {"selected_customer_id": 7},
    }

    result = await resumed_service.run(state)

    assert resumed_preflight.calls == []
    assert result["resume_route"] == "choice_resume"
    assert result["selected_customer"] == selected_customer
    assert result["remember_pending_task"] is True
    assert result["events"][-3:] == [
        {"event": "pending_task_interaction_interrupt_resumed", "resume_action": "select"},
        {
            "event": "customer_selected",
            "task_id": 101,
            "customer": selected_customer,
            "content": "已选择客户「广州睿狐科技有限公司」。请确认是否创建商机？",
        },
        {"event": "final", "content": "已选择客户「广州睿狐科技有限公司」。请确认是否创建商机？"},
    ]


@pytest.mark.asyncio
async def test_pending_task_graph_preflights_projected_quality_text_resume_before_native_text_node(monkeypatch):
    task = SimpleNamespace(
        id=101,
        input_json={"content": "拜访了客户"},
        state_json={"action": "collect_follow_up_quality_fields"},
    )
    interaction = PendingInteractionGraphService()

    async def fake_apply(db, task_arg, content):
        task_arg.input_json = {"content": "张总确认预算 30 万，8 月底签合同"}
        return True, "跟进内容已补充完整，请确认是否保存？"

    monkeypatch.setattr(
        follow_up_fields,
        "_apply_follow_up_quality_fields",
        fake_apply,
    )

    state = _state(task)
    state["content"] = "张总确认预算 30 万，8 月底签合同"
    state["turn_input"] = AgentTurnInput.text("张总确认预算 30 万，8 月底签合同")
    state["projected_resume_payload"] = {
        "action": "submit_text",
        "content": "张总确认预算 30 万，8 月底签合同",
        "interrupt_reason": "insufficient_follow_up_quality",
    }

    result = await PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult(task=task)),
        interaction_graph_service=interaction,
        checkpointer=InMemorySaver(),
    ).run(state)

    assert result["resume_route"] == "preflight"
    assert result["handled"] is True
    assert result["events"] == [
        {
            "event": "confirmation_required",
            "task_id": 101,
            "content": "跟进内容已补充完整，请确认是否保存？",
            "payload": {"content": "张总确认预算 30 万，8 月底签合同"},
        },
        {"event": "final", "content": "跟进内容已补充完整，请确认是否保存？"},
    ]


@pytest.mark.asyncio
async def test_pending_task_graph_resumes_native_text_interrupt_after_service_restart(monkeypatch):
    task = SimpleNamespace(
        id=101,
        input_json={"content": "拜访了客户"},
        state_json={"action": "collect_follow_up_quality_fields"},
    )
    checkpointer = InMemorySaver()
    first_interaction = FakeInteractionGraphService(FakeInteractionResult(
        handled=True,
        assistant_content="请补充有效跟进信息。",
        remember_pending_task=True,
        events=[{
            "event": "follow_up_quality_required",
            "task_id": 101,
            "content": "请补充有效跟进信息。",
            "payload": {"content": "拜访了客户"},
        }, {"event": "final", "content": "请补充有效跟进信息。"}],
    ))
    first_service = PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult(
            task=task,
            events=[{"event": "pending_interruption_assessed"}],
        )),
        interaction_graph_service=first_interaction,
        checkpointer=checkpointer,
    )

    _, continuation = await _start_continuation(first_service, _state(task))
    snapshot = await first_service._graph.aget_state(pending_task_checkpoint_config(continuation))

    assert snapshot.interrupts
    assert snapshot.values["current_interrupt"]["reason"] == "insufficient_follow_up_quality"
    assert snapshot.next == ("wait_interaction_interrupt",)

    async def fake_apply(db, task_arg, content):
        task_arg.input_json = {"content": "张总确认预算 30 万，8 月底签合同"}
        return True, "跟进内容已补充完整，请确认是否保存？"

    monkeypatch.setattr(
        follow_up_fields,
        "_apply_follow_up_quality_fields",
        fake_apply,
    )

    resumed_preflight = FakePreflightGraphService(FakePreflightResult(task=task))
    resumed_interaction = PendingInteractionGraphService()
    resumed_service = PendingTaskGraphService(
        preflight_graph_service=resumed_preflight,
        interaction_graph_service=resumed_interaction,
        checkpointer=checkpointer,
    )
    state = _state(task)
    state["continuation_ref"] = continuation
    state["content"] = "张总确认预算 30 万，8 月底签合同"
    state["turn_input"] = AgentTurnInput.text("张总确认预算 30 万，8 月底签合同")
    state["resume_payload"] = {
        "action": "submit_text",
        "content": "张总确认预算 30 万，8 月底签合同",
    }

    result = await resumed_service.run(state)

    assert resumed_preflight.calls == []
    assert result["resume_route"] == "text_resume"
    assert result["handled"] is True
    assert result["remember_pending_task"] is True
    assert result["current_interrupt"]["reason"] == "write_confirmation"
    assert "__interrupt__" in result
    assert result["__interrupt__"][0].value == result["current_interrupt"]
    assert result["events"][-3:] == [
        {"event": "pending_task_interaction_interrupt_resumed", "resume_action": "submit_text"},
        {
            "event": "confirmation_required",
            "task_id": 101,
            "content": "跟进内容已补充完整，请确认是否保存？",
            "payload": {"content": "张总确认预算 30 万，8 月底签合同"},
        },
        {"event": "final", "content": "跟进内容已补充完整，请确认是否保存？"},
    ]
    resumed_snapshot = await resumed_service._graph.aget_state(pending_task_checkpoint_config(continuation))
    assert resumed_snapshot.interrupts
    assert resumed_snapshot.values["current_interrupt"]["reason"] == "write_confirmation"
    assert resumed_snapshot.next == ("wait_interaction_interrupt",)


@pytest.mark.asyncio
async def test_pending_task_graph_does_not_fallback_for_business_sql_errors():
    task = SimpleNamespace(id=101)
    service = PendingTaskGraphService(
        preflight_graph_service=FakeFailingPreflightGraphService(),
        interaction_graph_service=FakeInteractionGraphService(FakeInteractionResult()),
        checkpointer=InMemorySaver(),
    )

    with pytest.raises(SQLAlchemyError, match="business db failed"):
        await service.run(_state(task))


@pytest.mark.asyncio
async def test_pending_task_graph_records_checkpoint_storage_fallback(monkeypatch):
    task = SimpleNamespace(id=101)
    service = PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult()),
        interaction_graph_service=FakeInteractionGraphService(FakeInteractionResult()),
        checkpointer=InMemorySaver(),
    )
    fallback_graph = FakePendingFallbackGraph()
    service._graph = FakeCheckpointFailingGraph()
    service._fallback_graph = fallback_graph
    monkeypatch.setattr(pending_graph_module, "is_checkpoint_storage_error", lambda exc: True)

    result = await service.run(_state(task))

    assert fallback_graph.calls
    assert fallback_graph.calls[0]["state"]["task_projection"]["id"] == 101
    assert result["events"][0]["event"] == "agent_checkpoint_unavailable_fallback_started"
    assert result["events"][0]["runtime"] == "crm_agent_pending_task"
    assert result["events"][0]["graph"] == "crm_agent_pending_task"
    assert result["events"][0]["fallback_reason"] == "checkpoint_storage_error"
    assert result["assistant_content"] == "fallback ok"


def test_task_projection_intent_supersedes_legacy_resume_for_same_task():
    task = SimpleNamespace(
        id=202,
        status=AgentTaskStatus.SUSPENDED,
        state_json={"action": "create_opportunity", "suspended_reason": "新流程切换"},
    )
    runtime_task = RuntimeAgentTaskView(task)
    runtime_task.status = AgentTaskStatus.WAITING_USER
    runtime_task.state_json = {"action": "create_opportunity"}

    intents = pending_graph_module._with_task_projection_intent(
        [{
            "intent_id": "resume_suspended_task:202",
            "intent_type": "resume_suspended_task",
            "task_id": 202,
        }],
        runtime_task,
    )

    assert [intent["intent_type"] for intent in intents] == ["project_pending_task_state"]
    assert intents[0]["expected_task"]["status"] == AgentTaskStatus.SUSPENDED
    assert intents[0]["task_update"]["status"] == AgentTaskStatus.WAITING_USER


@pytest.mark.asyncio
async def test_pending_task_graph_resumes_suspended_draft_before_interaction(monkeypatch):
    task = SimpleNamespace(
        id=202,
        status=AgentTaskStatus.SUSPENDED,
        intent="CREATE_OPPORTUNITY",
        target_type="customer",
        target_id=101,
        summary="等待确认执行：create_opportunity",
        input_json={},
        state_json={"action": "create_opportunity", "payload": {"opportunity": {"user_count": 10}}},
    )

    async def fake_assess(db, *, team_id, user_id, session, task, user_message):
        return AgentTurnRelationDecision(
            relation="RESUME_SUSPENDED_DRAFT",
            confidence=0.93,
            target_task_id=202,
            detected_intent="CREATE_OPPORTUNITY",
            reason="用户在修改最近暂停的商机草稿。",
        )

    monkeypatch.setattr(pending_graph_module.session_state, "_assess_turn_relation", fake_assess)

    monkeypatch.setattr(
        pending_graph_module.session_state,
        "_resume_suspended_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("graph must not persist task resume")),
    )

    interaction = FakeInteractionGraphService(FakeInteractionResult(
        handled=True,
        assistant_content="商机信息齐了，请确认。",
        remember_pending_task=True,
        events=[{"event": "confirmation_required"}, {"event": "final"}],
    ))

    side_effects = PendingTaskGraphSideEffects()
    result = await PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult()),
        interaction_graph_service=interaction,
    ).run(
        _state_with_suspended_candidates([_serialized_task_candidate(task)]),
        side_effects=side_effects,
    )

    assert result["task_projection"]["id"] == 202
    assert isinstance(side_effects.task, dict)
    assert side_effects.task["id"] == task.id
    assert side_effects.resumed_task is None
    projection = _task_projection_effect(result, 202)
    assert projection["expected_task"]["status"] == AgentTaskStatus.SUSPENDED
    assert projection["task_update"]["status"] == AgentTaskStatus.WAITING_USER
    assert task.status == AgentTaskStatus.SUSPENDED
    json.dumps(result["effect_intents"])
    assert result["handled"] is True
    assert interaction.calls[0]["task"].id == task.id
    assert interaction.calls[0]["task"].status == AgentTaskStatus.WAITING_USER
    assert [event["event"] for event in result["events"]] == [
        "turn_relation_classified",
        "suspended_task_resumed",
        "confirmation_required",
        "final",
    ]


@pytest.mark.asyncio
async def test_pending_task_graph_resumes_suspended_draft_from_interaction_metadata(monkeypatch):
    task = SimpleNamespace(
        id=202,
        status=AgentTaskStatus.SUSPENDED,
        intent="CREATE_OPPORTUNITY",
        target_type="customer",
        target_id=101,
        summary="等待确认执行：create_opportunity",
        input_json={},
        state_json={"action": "create_opportunity", "payload": {"opportunity": {"user_count": 10}}},
    )

    monkeypatch.setattr(
        pending_graph_module.session_state,
        "_assess_turn_relation",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("structured choice should not call semantic routing")),
    )

    monkeypatch.setattr(
        pending_graph_module.session_state,
        "_resume_suspended_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("graph must not persist task resume")),
    )

    interaction = FakeInteractionGraphService(FakeInteractionResult(
        handled=True,
        assistant_content="商机信息齐了，请确认。",
        remember_pending_task=True,
        events=[{"event": "confirmation_required"}, {"event": "final"}],
    ))
    state = _state_with_suspended_candidates([_serialized_task_candidate(task)])
    state["turn_input"] = AgentTurnInput.text("继续：广州睿狐创建商机确认", metadata={"selected_task_id": 202})
    state["content"] = "继续：广州睿狐创建商机确认"

    side_effects = PendingTaskGraphSideEffects()
    result = await PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult()),
        interaction_graph_service=interaction,
    ).run(state, side_effects=side_effects)

    assert result["task_projection"]["id"] == 202
    assert isinstance(side_effects.task, dict)
    assert side_effects.task["id"] == task.id
    assert side_effects.resumed_task is None
    projection = _task_projection_effect(result, 202)
    assert projection["expected_task"]["status"] == AgentTaskStatus.SUSPENDED
    assert projection["task_update"]["status"] == AgentTaskStatus.WAITING_USER
    assert task.status == AgentTaskStatus.SUSPENDED
    json.dumps(result["effect_intents"])
    assert interaction.calls[0]["task"].id == task.id
    assert interaction.calls[0]["task"].status == AgentTaskStatus.WAITING_USER
    assert interaction.calls[0]["task"] is not task
    classified_events = [
        event
        for event in result["events"]
        if event.get("event") == "turn_relation_classified"
    ]
    assert classified_events[0]["source"] == "interaction_metadata"


@pytest.mark.asyncio
async def test_pending_task_graph_resumes_suspended_draft_from_visible_choice_text(monkeypatch):
    task = SimpleNamespace(
        id=301,
        task_key="task-301",
        status=AgentTaskStatus.SUSPENDED,
        intent="CREATE_CUSTOMER_ACTIVITY",
        target_type="customer",
        target_id=17,
    )
    monkeypatch.setattr(
        pending_graph_module.session_state,
        "_assess_turn_relation",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("visible choice text should not call semantic routing")),
    )
    monkeypatch.setattr(
        pending_graph_module.session_state,
        "_resume_suspended_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("graph must not persist task resume")),
    )
    interaction = FakeInteractionGraphService(FakeInteractionResult(
        handled=True,
        assistant_content="继续处理跟进草稿。",
        events=[{"event": "interaction_planned"}, {"event": "final", "content": "继续处理跟进草稿。"}],
    ))
    state = _state_with_suspended_candidates([{
        **_serialized_task_candidate(task),
        "summary": "等待确认执行：create_customer_activity",
        "action": "create_customer_activity",
        "customer_name": "广州睿狐科技有限公司",
    }])
    state["turn_input"] = AgentTurnInput.text("继续：确认记录跟进「广州睿狐科技有限公司」")
    state["content"] = "继续：确认记录跟进「广州睿狐科技有限公司」"

    side_effects = PendingTaskGraphSideEffects()
    result = await PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult()),
        interaction_graph_service=interaction,
    ).run(state, side_effects=side_effects)

    assert result["resumed_task_id"] == 301
    assert side_effects.resumed_task is None
    projection = _task_projection_effect(result, 301)
    assert projection["expected_task"]["status"] == AgentTaskStatus.SUSPENDED
    assert projection["task_update"]["status"] == AgentTaskStatus.WAITING_USER
    assert task.status == AgentTaskStatus.SUSPENDED
    assert interaction.calls[0]["task"].id == task.id
    assert interaction.calls[0]["task"].status == AgentTaskStatus.WAITING_USER
    classified_events = [
        event
        for event in result["events"]
        if event.get("event") == "turn_relation_classified"
    ]
    assert classified_events[0]["source"] == "local_text_match"
    assert classified_events[0]["target_task_id"] == 301


@pytest.mark.asyncio
async def test_pending_task_graph_cancels_turn_relation_choice_without_reasking(monkeypatch):
    async def fail_assess(*args, **kwargs):
        raise AssertionError("cancelled turn relation choice must not be reclassified")

    monkeypatch.setattr(pending_graph_module.session_state, "_assess_turn_relation", fail_assess)

    state = _state_with_suspended_candidates([{
        "id": 202,
        "action": "create_customer_activity",
        "customer_name": "广州睿狐科技有限公司",
    }])
    state["projected_resume_payload"] = {
        "action": "cancel",
        "content": "先不处理",
        "interrupt_reason": "business_object_disambiguation",
    }
    state["turn_input"] = AgentTurnInput.text("先不处理")
    state["content"] = "先不处理"

    result = await PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult()),
        interaction_graph_service=FakeInteractionGraphService(FakeInteractionResult()),
        checkpointer=InMemorySaver(),
    ).run(state)

    assert result["handled"] is True
    assert result["assistant_content"] == "好嘞，这一步先放着。"
    assert result["has_active_task"] is False
    assert result["task_projection"] == {}
    assert result.get("current_interrupt") is None


@pytest.mark.asyncio
async def test_pending_task_graph_starts_new_flow_from_interaction_metadata(monkeypatch):
    monkeypatch.setattr(
        pending_graph_module.session_state,
        "_assess_turn_relation",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("structured new-flow choice should not call semantic routing")),
    )

    state = _state_with_suspended_candidates([{
        "id": 202,
        "intent": "CREATE_OPPORTUNITY",
        "display_summary": "确认创建商机｜广州睿狐科技有限公司",
    }])
    state["turn_input"] = AgentTurnInput.text("作为新流程处理", metadata={"turn_relation": "START_NEW_FLOW"})
    state["content"] = "作为新流程处理"

    side_effects = PendingTaskGraphSideEffects()
    result = await PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult()),
        interaction_graph_service=FakeInteractionGraphService(FakeInteractionResult()),
    ).run(state, side_effects=side_effects)

    assert result.get("handled") is not True
    assert side_effects.task is None
    assert side_effects.resumed_task is None
    assert side_effects.turn_relation_decision is not None
    assert side_effects.turn_relation_decision.relation == "START_NEW_FLOW"
    classified_events = [
        event
        for event in result["events"]
        if event.get("event") == "turn_relation_classified"
    ]
    assert classified_events[0]["source"] == "interaction_metadata"
    assert classified_events[0]["relation"] == "START_NEW_FLOW"


@pytest.mark.asyncio
async def test_pending_task_graph_asks_when_suspended_relation_is_ambiguous(monkeypatch):
    async def fake_assess(db, *, team_id, user_id, session, task, user_message):
        return AgentTurnRelationDecision(
            relation="ASK_USER",
            confidence=0.66,
            target_task_id=202,
            reason="可能是修改旧商机，也可能是新跟进。",
            question="这句是继续刚才放下的商机，还是新记录一条跟进？",
        )

    monkeypatch.setattr(pending_graph_module.session_state, "_assess_turn_relation", fake_assess)
    interaction = FakeInteractionGraphService(FakeInteractionResult())

    result = await PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult()),
        interaction_graph_service=interaction,
    ).run(_state_with_suspended_candidates([{"id": 202, "intent": "CREATE_OPPORTUNITY"}]))

    assert result["handled"] is True
    assert result["assistant_content"] == "这句是继续刚才放下的商机，还是新记录一条跟进？"
    assert interaction.calls == []
    assert result["events"][-1] == {"event": "final", "content": result["assistant_content"]}


@pytest.mark.asyncio
async def test_pending_task_graph_asks_when_resume_confidence_is_low(monkeypatch):
    async def fake_assess(db, *, team_id, user_id, session, task, user_message):
        return AgentTurnRelationDecision(
            relation="RESUME_SUSPENDED_DRAFT",
            confidence=0.62,
            target_task_id=202,
            detected_intent="CREATE_OPPORTUNITY",
            reason="可能是在修改暂停商机，但置信度不足。",
        )

    monkeypatch.setattr(pending_graph_module.session_state, "_assess_turn_relation", fake_assess)

    result = await PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult()),
        interaction_graph_service=FakeInteractionGraphService(FakeInteractionResult()),
    ).run(_state_with_suspended_candidates([{
        "id": 202,
        "intent": "CREATE_OPPORTUNITY",
        "summary": "广州睿狐商机草稿",
    }]))

    assert result["handled"] is True
    assert "广州睿狐商机草稿" in result["assistant_content"]
    assert result["events"][-2]["event"] == "turn_relation_clarification_required"


@pytest.mark.asyncio
async def test_pending_task_graph_turn_relation_question_hides_legacy_action_summary(monkeypatch):
    async def fake_assess(db, *, team_id, user_id, session, task, user_message):
        return AgentTurnRelationDecision(
            relation="RESUME_SUSPENDED_DRAFT",
            confidence=0.62,
            target_task_id=202,
            reason="可能是在继续暂停草稿，但置信度不足。",
            question="这句是继续「等待确认执行：create_customer_activity」，还是新开一个流程？",
        )

    monkeypatch.setattr(pending_graph_module.session_state, "_assess_turn_relation", fake_assess)

    result = await PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult()),
        interaction_graph_service=FakeInteractionGraphService(FakeInteractionResult()),
    ).run(_state_with_suspended_candidates([{
        "id": 202,
        "summary": "等待确认执行：create_customer_activity",
        "action": "create_customer_activity",
        "customer_name": "广州睿狐科技有限公司",
    }]))

    interaction = result["events"][-2]["interaction"]
    assert "确认记录跟进｜广州睿狐科技有限公司" in result["assistant_content"]
    assert "create_customer_activity" not in result["assistant_content"]
    assert interaction["choices"][0]["label"] == "继续处理：确认记录跟进｜广州睿狐科技有限公司"
    assert interaction["choices"][1]["label"] == "作为新流程处理"
    assert "create_customer_activity" not in str(interaction)


@pytest.mark.asyncio
async def test_pending_task_graph_interrupts_inside_subgraph_for_turn_relation_choice(monkeypatch):
    async def fake_assess(db, *, team_id, user_id, session, task, user_message):
        return AgentTurnRelationDecision(
            relation="ASK_USER",
            confidence=0.41,
            reason="需要用户选择是否恢复挂起草稿。",
            question="这句是继续广州睿狐商机草稿，还是新记录一条跟进？",
        )

    monkeypatch.setattr(pending_graph_module.session_state, "_assess_turn_relation", fake_assess)
    service = PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult()),
        interaction_graph_service=FakeInteractionGraphService(FakeInteractionResult()),
        checkpointer=InMemorySaver(),
    )

    result = await service.run(_state_with_suspended_candidates([{
        "id": 202,
        "intent": "CREATE_OPPORTUNITY",
        "summary": "广州睿狐商机草稿",
    }]))

    assert result["current_interrupt"]["type"] == "choice"
    assert result["current_interrupt"]["reason"] == "business_object_disambiguation"
    assert result["current_interrupt"]["source_event"] == "turn_relation_clarification_required"
    assert result["current_interrupt"]["interaction"]["business_action"] == "select_suspended_task"
    assert "__interrupt__" in result
    assert result["__interrupt__"][0].value == result["current_interrupt"]


@pytest.mark.asyncio
async def test_pending_task_graph_resumes_subgraph_interrupt_with_selected_task(monkeypatch):
    suspended_task = SimpleNamespace(
        id=202,
        task_key="task-202",
        status=AgentTaskStatus.SUSPENDED,
        intent="CREATE_OPPORTUNITY",
        target_type="customer",
        target_id=17,
    )
    async def fake_assess(db, *, team_id, user_id, session, task, user_message):
        return AgentTurnRelationDecision(
            relation="ASK_USER",
            confidence=0.41,
            reason="需要用户选择是否恢复挂起草稿。",
            question="这句是继续广州睿狐商机草稿，还是新记录一条跟进？",
        )

    monkeypatch.setattr(pending_graph_module.session_state, "_assess_turn_relation", fake_assess)
    monkeypatch.setattr(
        pending_graph_module.session_state,
        "_resume_suspended_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("graph must not persist task resume")),
    )
    interaction = FakeInteractionGraphService(FakeInteractionResult(events=[{"event": "interaction_planned"}]))
    service = PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult()),
        interaction_graph_service=interaction,
        checkpointer=InMemorySaver(),
    )

    _, continuation = await _start_continuation(service, _state_with_suspended_candidates([{
        **_serialized_task_candidate(suspended_task),
        "summary": "广州睿狐商机草稿",
    }]))
    side_effects = PendingTaskGraphSideEffects()
    result = await service.run({
        **_state_without_task(),
        "content": "继续这个草稿",
        "turn_input": AgentTurnInput.text("继续这个草稿"),
        "continuation_ref": continuation,
        "resume_payload": {
            "action": "select",
            "content": "继续这个草稿",
            "source": "web",
            "metadata": {"selected_task_id": 202},
        },
    }, side_effects=side_effects)

    assert result["resumed_task_id"] == 202
    assert result["task_projection"]["id"] == 202
    assert isinstance(side_effects.task, dict)
    assert side_effects.task["id"] == suspended_task.id
    assert side_effects.resumed_task is None
    projection = _task_projection_effect(result, 202)
    assert projection["expected_task"]["status"] == AgentTaskStatus.SUSPENDED
    assert projection["task_update"]["status"] == AgentTaskStatus.WAITING_USER
    assert suspended_task.status == AgentTaskStatus.SUSPENDED
    assert interaction.calls[0]["task"].id == suspended_task.id
    assert interaction.calls[0]["task"].status == AgentTaskStatus.WAITING_USER
    event_names = [event["event"] for event in result["events"]]
    assert "turn_relation_classified" in event_names
    assert "suspended_task_resumed" in event_names
    assert event_names[-1] == "interaction_planned"


@pytest.mark.asyncio
async def test_pending_task_graph_asks_when_resume_target_is_not_a_candidate(monkeypatch):
    async def fake_assess(db, *, team_id, user_id, session, task, user_message):
        return AgentTurnRelationDecision(
            relation="RESUME_SUSPENDED_DRAFT",
            confidence=0.93,
            target_task_id=999,
            detected_intent="CREATE_OPPORTUNITY",
            reason="模型返回了不存在的目标任务。",
        )

    monkeypatch.setattr(pending_graph_module.session_state, "_assess_turn_relation", fake_assess)

    result = await PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult()),
        interaction_graph_service=FakeInteractionGraphService(FakeInteractionResult()),
    ).run(_state_with_suspended_candidates([{
        "id": 202,
        "intent": "CREATE_OPPORTUNITY",
        "summary": "广州睿狐商机草稿",
    }]))

    assert result["handled"] is True
    assert "广州睿狐商机草稿" in result["assistant_content"]
    assert result["events"][-2]["decision"]["target_task_id"] == 999


@pytest.mark.asyncio
async def test_pending_task_graph_abort_projection_releases_native_interrupt_without_business_effects(monkeypatch):
    workflow = action_workflow.required_write_contract(action="create_opportunity")
    task = SimpleNamespace(
        id=101,
        task_key="task-101",
        status=AgentTaskStatus.WAITING_USER,
        state_json={"workflow": workflow, "payload": {"workflow": workflow}},
    )
    service = PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult(
            task=task,
            events=[{"event": "pending_interruption_assessed"}],
        )),
        interaction_graph_service=FakeInteractionGraphService(FakeInteractionResult(
            handled=True,
            assistant_content="请确认是否创建商机？",
            remember_pending_task=True,
            events=[{
                "event": "confirmation_required",
                "task_id": 101,
                "action": "create_opportunity",
                "workflow": workflow,
            }, {"event": "final"}],
        )),
        checkpointer=InMemorySaver(),
    )
    initial_result, continuation = await _start_continuation(service, _state(task))
    monkeypatch.setattr(
        pending_graph_module.session_state,
        "_resume_suspended_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("abort must not resume task")),
    )
    monkeypatch.setattr(
        pending_graph_module.workflow_action_ledger,
        "mark_action_cancelled",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("abort must not mutate ledger")),
    )

    result = await service.run(_resume_state(
        _state(task),
        continuation,
        {"action": "abort_projection", "content": "internal recovery"},
    ))
    snapshot = await service._graph.aget_state(pending_task_checkpoint_config(continuation))

    assert result["handled"] is False
    assert result["projection_aborted"] is True
    assert result["pending_interrupt_requested"] is False
    assert result["current_interrupt"] is None
    assert result["resume_route"] == "end"
    assert result["effect_intents"] == []
    assert result["projection_abort_interrupt"] == snapshot.values["projection_abort_interrupt"]
    assert result["projection_abort_interrupt"] == initial_result["current_interrupt"]
    assert not any(event.get("event") == "task_cancelled" for event in result["events"])
    assert task.state_json["workflow"]["status"] == action_workflow.STATUS_WAITING_USER
    assert snapshot.next == ()
    assert snapshot.interrupts == ()

@pytest.mark.asyncio
async def test_pending_graph_uses_hidden_application_step_interrupt_for_preflight():
    task = SimpleNamespace(
        id=101,
        task_key="task-101",
        team_id=1,
        user_id=2,
        session_id=3,
        status=AgentTaskStatus.WAITING_USER,
        intent="CREATE_OPPORTUNITY",
        target_type="customer",
        target_id=7,
        input_json={},
        state_json={},
    )
    preflight = FakePreflightGraphService(FakePreflightResult(task=task))
    interaction = FakeInteractionGraphService(FakeInteractionResult(
        handled=True,
        assistant_content="请确认是否创建商机？",
        remember_pending_task=True,
        events=[{"event": "confirmation_required"}, {"event": "final"}],
    ))
    service = PendingTaskGraphService(
        preflight_graph_service=preflight,
        interaction_graph_service=interaction,
        checkpointer=InMemorySaver(),
        application_step_protocol=True,
    )
    first, continuation = await _start_continuation(service, _state(task))

    application_step = first["current_interrupt"]
    assert application_step["reason"] == "pending_task_application_step"
    assert application_step["internal"] is True
    assert application_step["step_type"] == "preflight"
    assert application_step["checkpoint_ref"] == continuation
    assert preflight.calls == []
    assert interaction.calls == []

    acknowledgement = {
        "schema_version": "agent.pending_application_step.v1",
        "status": "COMPLETED",
        "step_id": application_step["step_id"],
        "result": {
            "step_type": "preflight",
            "task_snapshot": agent_task_snapshot(task),
            "suspended_task_snapshot": {},
            "result": {
                "handled": False,
                "events": [{"event": "pending_interruption_assessed"}],
                "confirmation_decision": {},
            },
        },
        "replayed": False,
        "retryable": False,
    }
    interaction_step_result = await service.run(
        _resume_state(_state(task), continuation, acknowledgement)
    )

    assert preflight.calls == []
    assert interaction.calls == []
    interaction_step = interaction_step_result["current_interrupt"]
    assert interaction_step["reason"] == "pending_task_application_step"
    assert interaction_step["internal"] is True
    assert interaction_step["step_type"] == "interaction"
    assert interaction_step["checkpoint_ref"] == continuation

    checkpointed_interaction_task_snapshot = interaction_step["task_snapshot"]
    task.input_json = {"opportunity": {"purchase_type": "NEW_PURCHASE"}}
    task.state_json = {"workflow": {"status": "WAITING_CONFIRMATION"}}

    business_interrupt = {
        "type": "confirm",
        "reason": "write_confirmation",
        "source_event": "confirmation_required",
        "business_action": "create_opportunity",
        "interaction": {
            "type": "confirm",
            "prompt": "请确认是否创建商机？",
            "choices": [],
            "payload": {"task_id": 101},
        },
    }
    interaction_acknowledgement = {
        "schema_version": "agent.pending_application_step.v1",
        "status": "COMPLETED",
        "step_id": interaction_step["step_id"],
        "result": {
            "step_type": "interaction",
            "task_snapshot": agent_task_snapshot(task),
            "result": {
                "handled": True,
                "events": [
                    {"event": "confirmation_required"},
                    {"event": "final"},
                ],
                "assistant_content": "请确认是否创建商机？",
                "selected_customer": {},
                "remember_pending_task": True,
                "clear_pending_task_id": None,
                "current_interrupt": business_interrupt,
            },
        },
        "replayed": False,
        "retryable": False,
    }
    resumed = await service.run(
        _resume_state(_state(task), continuation, interaction_acknowledgement)
    )

    assert interaction.calls == []
    assert interaction_step["task_snapshot"] == checkpointed_interaction_task_snapshot
    assert resumed["current_interrupt"]["reason"] == "write_confirmation"
    assert resumed["events"] == [
        {"event": "pending_interruption_assessed"},
        {"event": "confirmation_required"},
        {"event": "final"},
    ]


@pytest.mark.asyncio
async def test_pending_graph_uses_hidden_application_step_for_semantic_turn_relation(monkeypatch):
    monkeypatch.setattr(
        pending_graph_module.session_state,
        "_assess_turn_relation",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("LangGraph node must not execute semantic turn-relation assessment")
        ),
    )
    service = PendingTaskGraphService(
        preflight_graph_service=FakePreflightGraphService(FakePreflightResult()),
        interaction_graph_service=FakeInteractionGraphService(FakeInteractionResult()),
        checkpointer=InMemorySaver(),
        application_step_protocol=True,
    )
    state = _state_with_suspended_candidates([{
        "id": 202,
        "task_key": "task-202",
        "status": AgentTaskStatus.SUSPENDED,
        "intent": "CREATE_OPPORTUNITY",
        "display_summary": "确认创建商机｜广州睿狐科技有限公司",
    }])
    state["turn_input"] = AgentTurnInput.text("张总说金额改成 30 万")
    state["content"] = "张总说金额改成 30 万"

    first, continuation = await _start_continuation(service, state)

    application_step = first["current_interrupt"]
    assert application_step["reason"] == "pending_task_application_step"
    assert application_step["internal"] is True
    assert application_step["step_type"] == "turn_relation_assessment"
    assert application_step["checkpoint_ref"] == continuation

    acknowledgement = {
        "schema_version": "agent.pending_application_step.v1",
        "status": "COMPLETED",
        "step_id": application_step["step_id"],
        "result": {
            "step_type": "turn_relation_assessment",
            "task_snapshot": {},
            "result": {
                "decision": {
                    "relation": "ASK_USER",
                    "confidence": 0.62,
                    "target_task_id": 202,
                    "reason": "可能是继续挂起商机，也可能是新流程。",
                    "question": "这句是继续广州睿狐商机，还是作为新流程处理？",
                },
            },
        },
        "replayed": False,
        "retryable": False,
    }
    resumed = await service.run(_resume_state(state, continuation, acknowledgement))

    assert resumed["turn_relation_decision"]["relation"] == "ASK_USER"
    assert resumed["current_interrupt"]["reason"] == "business_object_disambiguation"
    classified = [
        event for event in resumed["events"]
        if event.get("event") == "turn_relation_classified"
    ]
    assert classified[-1]["source"] == "application_step"

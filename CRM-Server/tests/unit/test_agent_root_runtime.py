"""Tests for the LangGraph-native CRM Agent root runtime."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.services.agent import action_plan, action_workflow, agent_copy
from app.services.agent import pending_graph as pending_graph_module
from app.services.agent import root_runtime as root_runtime_module
from app.services.agent.input import AgentTurnInput
from app.services.agent.interrupts import interrupt_payload_from_json
from app.services.agent.pending_application_step_contracts import (
    build_pending_application_step_request,
    pending_application_step_id,
)
from app.services.agent.pending_application_step_projection import PendingApplicationStepProjectionResult
from app.services.agent.pending_checkpoint import PendingTaskCheckpointLoadResult
from app.services.agent.pending_continuation import new_pending_task_continuation
from app.services.agent.pending_graph import PendingTaskGraphService
from app.services.agent.pending_interrupt_projection import PendingInterruptProjectionResult
from app.services.agent.pending_outcome import PendingTaskOutcomeRecovery
from app.services.agent.root_runtime import (
    AgentRootRuntime,
    build_agent_thread_id,
    project_turn_output,
)
from app.services.agent.schemas import AgentConfirmationIntentDecision
from app.services.agent.state import AgentRootRuntimeSideEffects, AgentRuntimeContext
from app.services.agent.task_execution import ActionToolExecutionResult
from app.services.agent.task_projection import agent_task_snapshot
from app.services.agent.tools.base import AgentToolResult
from app.services.follow_up_task_confirmation_channel_service import (
    FOLLOW_UP_CONFIRMATION_PROMPT_EVENT,
    FollowUpTaskConfirmationChannelService,
)


def without_projection_metadata(events):
    return [
        {key: value for key, value in event.items() if key not in {"projection_key", "projection_event_id"}}
        for event in events
    ]


def bind_fake_pending_continuation(state, side_effects, *, continuation_id: str) -> None:
    if side_effects is None:
        return
    runtime_config = root_runtime_module.get_config()
    configurable = runtime_config.get("configurable", {})
    root_thread_id = configurable.get("thread_id")
    checkpoint_ns = configurable.get("checkpoint_ns")
    assert isinstance(root_thread_id, str)
    assert isinstance(checkpoint_ns, str)
    assert checkpoint_ns.startswith("pending_task_subgraph:")
    task_snapshot = state["task_snapshot"]
    side_effects.task = task_snapshot
    side_effects.checkpoint_ref = new_pending_task_continuation(
        team_id=state["team_id"],
        user_id=state["user_id"],
        session_id=state["session_id"],
        task_id=task_snapshot["id"],
        root_thread_id=root_thread_id,
        checkpoint_ns=checkpoint_ns,
    )


def _waiting_task_snapshot(
    task_id: int,
    *,
    action: str = "collect_opportunity_fields",
    target_id: int = 17,
) -> dict[str, object]:
    return {
        "id": task_id,
        "task_key": f"task-{task_id}",
        "team_id": 2,
        "user_id": 3,
        "session_id": 4,
        "status": "WAITING_USER",
        "intent": "CREATE_OPPORTUNITY",
        "target_type": "customer",
        "target_id": target_id,
        "summary": "等待补充业务信息",
        "state_json": {
            "action": action,
            "payload": {"customer_id": target_id, "missing_fields": ["total_amount"]},
        },
    }


def _persisted_waiting_task_from_event(
    event: dict[str, object],
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    task_id: int = 501,
) -> SimpleNamespace:
    """Build the persisted task returned by the application write seam.

    New-flow ownership must be projected from the created task itself. Tests
    therefore model the complete persisted contract instead of relying on the
    legacy event mutation side effect.
    """

    event["task_id"] = task_id
    event["task_key"] = f"task-{task_id}"
    payload = dict(event.get("payload") or {})
    customer_id = payload.get("customer_id")
    return SimpleNamespace(
        id=task_id,
        task_key=f"task-{task_id}",
        team_id=team_id,
        user_id=user_id,
        session_id=session_id,
        status="WAITING_USER",
        intent="CUSTOMER_ACTIVITY",
        target_type="customer",
        target_id=customer_id if isinstance(customer_id, int) else None,
        summary=event.get("content") or "等待确认业务操作",
        input_json=payload,
        state_json={
            "action": event.get("action"),
            "payload": payload,
            "customer": event.get("customer"),
        },
    )


class FakePendingGraphService:
    def __init__(self):
        self.calls = []

    async def run_with_trace(self, state, *, side_effects=None):
        self.calls.append(state)
        bind_fake_pending_continuation(
            state,
            side_effects,
            continuation_id="fake-pending-outcome",
        )
        return {
            "has_active_task": True,
            "task_projection": {
                "id": state["task_snapshot"]["id"],
                "task_key": state["task_snapshot"]["task_key"],
                "status": state["task_snapshot"]["status"],
                "intent": state["task_snapshot"]["intent"],
                "target_id": state["task_snapshot"]["target_id"],
            },
            "handled": True,
            "assistant_content": "请确认是否创建商机？",
            "remember_pending_task": True,
            "events": [{"event": "confirmation_required"}, {"event": "final"}],
        }


class FakeTerminalRecoveryPendingGraphService:
    def __init__(self):
        self.calls = []

    async def run_with_trace(self, state, *, side_effects=None):
        self.calls.append(state)
        return {
            "handled": False,
            "recovery_failed": True,
            "terminal": True,
            "runtime_status": "checkpoint_recovery_failed",
            "runtime_retryable": False,
            "failure_reason": "checkpoint_locator_not_found",
            "current_interrupt": None,
            "assistant_content": "当前待确认流程恢复失败，本次流程已终止；你可以重新发起。",  # noqa: RUF001
            "events": [{
                "event": "pending_task_checkpoint_recovery_failed",
                "reason": "checkpoint_locator_not_found",
                "retryable": False,
            }],
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
        bind_fake_pending_continuation(
            state,
            side_effects,
            continuation_id="fake-traced-pending-outcome",
        )
        return {
            "has_active_task": True,
            "task_projection": {
                "id": state["task_snapshot"]["id"],
                "task_key": state["task_snapshot"]["task_key"],
                "status": state["task_snapshot"]["status"],
                "intent": state["task_snapshot"]["intent"],
                "target_id": state["task_snapshot"]["target_id"],
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


class FakeNativeInterruptPreflightGraphService:
    async def run(self, input_state):
        return SimpleNamespace(
            task=input_state["task"],
            handled=False,
            events=[{"event": "pending_interruption_assessed"}],
            assistant_content=None,
            switch_notice=None,
            suspended_task=None,
            suspend_reason=None,
            suspension_kind=None,
            clear_pending_task_id=None,
            confirmation_decision=None,
        )


class FakeNativeInterruptInteractionGraphService:
    async def run(self, input_state):
        return SimpleNamespace(
            handled=True,
            events=[
                {"event": "confirmation_required", "content": "商机信息齐了。要创建商机吗？"},
                {"event": "final", "content": "商机信息齐了。要创建商机吗？"},
            ],
            assistant_content="商机信息齐了。要创建商机吗？",
            selected_customer=None,
            remember_pending_task=True,
            clear_pending_task_id=None,
        )


class FakeConfirmingPendingGraphService:
    def __init__(self):
        self.calls = []

    async def run_with_trace(self, state, *, side_effects=None):
        self.calls.append(state)
        bind_fake_pending_continuation(
            state,
            side_effects,
            continuation_id="fake-confirming-pending-outcome",
        )
        return {
            "has_active_task": True,
            "task_projection": {
                "id": state["task_snapshot"]["id"],
                "task_key": state["task_snapshot"]["task_key"],
                "status": state["task_snapshot"]["status"],
            },
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
        executed_task_snapshot = agent_task_snapshot(task)
        executed_task_snapshot.update({
            "team_id": state["team_id"],
            "user_id": state["user_id"],
            "session_id": state["session_id"],
            "status": "COMPLETED",
        })
        return {
            "task_projection": {"id": task.id, "task_key": task.task_key, "status": task.status},
            "tool_result": {"event": "tool_result", "tool_name": "create_customer_activity", "success": True},
            "task_event": {"event": "task_completed", "task_id": task.id, "content": "跟进记录已创建。"},
            "assistant_content": "跟进记录已创建。",
            "execution_status": "completed",
            "executed_task_snapshot": executed_task_snapshot,
            "active_task_snapshot": {},
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


class FakeConfirmedTaskWithNextGraphService(FakeConfirmedTaskGraphService):
    async def run(self, state):
        self.calls.append(state)
        task = state["task"]
        executed_task_snapshot = agent_task_snapshot(task)
        executed_task_snapshot.update({
            "team_id": state["team_id"],
            "user_id": state["user_id"],
            "session_id": state["session_id"],
            "status": "COMPLETED",
        })
        active_task_snapshot = {
            "id": 102,
            "task_key": "task-102",
            "team_id": state["team_id"],
            "user_id": state["user_id"],
            "session_id": state["session_id"],
            "status": "WAITING_USER",
            "intent": "CREATE_OPPORTUNITY",
            "target_type": "customer",
            "target_id": 17,
            "summary": "等待补充商机信息",
            "state_json": {
                "action": "collect_opportunity_fields",
                "customer": {"id": 17, "account_name": "广州睿狐科技有限公司"},
                "payload": {"customer_id": 17, "missing_fields": ["total_amount"]},
            },
        }
        interaction = {
            "schema_version": "agent.interaction.v1",
            "interaction_id": "int-next-task-102",
            "type": "form",
            "status": "waiting_user_input",
            "business_action": "create_opportunity",
            "prompt": "还差商机金额。请补充。",
            "fields": [],
            "choices": [],
            "presentation": {},
            "metadata": {},
        }
        task_event = {
            "event": "task_completed",
            "task_id": task.id,
            "content": "跟进记录已创建。",
            "next_task_id": 102,
            "interaction": interaction,
        }
        return {
            "task_projection": {"id": task.id, "task_key": task.task_key, "status": task.status},
            "tool_result": {"event": "tool_result", "tool_name": "create_customer_activity", "success": True},
            "task_event": task_event,
            "assistant_content": "还差商机金额。请补充。",
            "execution_status": "completed",
            "executed_task_snapshot": executed_task_snapshot,
            "active_task_snapshot": active_task_snapshot,
            "output_events": [
                {"event": "tool_result", "tool_name": "create_customer_activity", "success": True},
                task_event,
                {"event": "final", "content": "还差商机金额。请补充。"},
            ],
            "events": [
                {"event": "confirmed_task_graph_started"},
                {"event": "confirmed_task_execution_completed"},
                {"event": "confirmed_task_graph_finished"},
            ],
        }


@pytest.mark.asyncio
async def test_root_runtime_structured_follow_up_confirmation_uses_action_envelope_and_ledger(monkeypatch):
    execute_calls = []
    running_calls = []
    executed_calls = []
    published_events = []

    async def fake_execute_action_envelope(db, envelope, *, session, team_id, user_id, authorization, event_sink):
        execute_calls.append(
            {
                "db": db,
                "envelope": envelope,
                "session": session,
                "team_id": team_id,
                "user_id": user_id,
                "authorization": authorization,
                "event_sink": event_sink,
            }
        )
        return ActionToolExecutionResult(
            AgentToolResult(
                tool_name="resolve_follow_up_task_confirmation_case",
                success=True,
                data={
                    "event": "follow_up_task_confirmation_resolved",
                    "content": "已确认完成, 并更新了这项跟进任务。",
                    "content_format": "text",
                    "case_public_id": "fuc_structured",
                },
            )
        )

    def fake_mark_running(db, **kwargs):
        running_calls.append({"db": db, **kwargs})

    def fake_mark_executed(db, **kwargs):
        executed_calls.append({"db": db, **kwargs})

    async def capture_event(event):
        published_events.append(event)

    monkeypatch.setattr(root_runtime_module.task_execution, "execute_action_envelope", fake_execute_action_envelope)
    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "mark_action_running", fake_mark_running)
    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "mark_action_executed", fake_mark_executed)

    runtime = AgentRootRuntime(checkpointer=InMemorySaver())
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=3),
        turn_input=AgentTurnInput.text(
            "已完成",
            metadata={
                "business_action": "resolve_follow_up_task_confirmation_case",
                "case_public_id": "fuc_structured",
            },
        ),
        content="已完成",
        team_id=1,
        user_id=2,
        session_id=3,
        authorization="Bearer test-token",
        event_sink=capture_event,
    )

    state = await runtime.run_turn(
        turn_input=context.turn_input,
        content="已完成",
        team_id=1,
        user_id=2,
        session_id=3,
        session_key="session-key",
        current_customer={},
        context=context,
    )

    assert state["application_action"] == "run_new_flow"
    assert state["structured_business_action"]["status"] == "executed"
    assert execute_calls[0]["envelope"].action_type == "resolve_follow_up_task_confirmation_case"
    assert execute_calls[0]["envelope"].payload == {
        "case_id": "fuc_structured",
        "reply_text": "已完成",
    }
    assert execute_calls[0]["envelope"].task_key == execute_calls[0]["envelope"].action_id
    assert running_calls[0]["payload"] == {"case_id": "fuc_structured", "reply_text": "已完成"}
    assert executed_calls[0]["result"]["case_public_id"] == "fuc_structured"
    assert context.side_effects.new_flow_assistant_content == "已确认完成, 并更新了这项跟进任务。"
    assert any(event.get("event") == "follow_up_task_confirmation_resolved" for event in published_events)


def _test_workflow(action_id: str, *, action_type: str, dependency_json: dict | None = None) -> dict:
    workflow = action_workflow.required_write_contract(action=action_type)
    workflow["workflow_id"] = "wf_test"
    workflow["action_id"] = action_id
    workflow["action_type"] = action_type
    if dependency_json:
        workflow["dependency_json"] = dependency_json
    return workflow


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
        lookup_calls.append(
            {
                "db": db,
                "task_id": task_id,
                "team_id": team_id,
                "user_id": user_id,
            }
        )
        return checkpoint_task if task_id == checkpoint_task.id else None

    class RuntimeUnderTest(AgentRootRuntime):
        def __init__(self):
            self.resume_calls = []
            self.turn_intent_router = SimpleNamespace(route_resume=self._route_resume)

        async def _route_resume(self, db, **kwargs):
            return SimpleNamespace(
                decision=SimpleNamespace(
                    intent="CONFIRM_EXECUTION",
                    confidence=1.0,
                    target_task_id=kwargs["active_task"].id,
                    normalized_action="approve",
                    reason="测试确认输入。",
                ),
                resume_payload={
                    "action": "approve",
                    "task_projection_id": kwargs["current_interrupt"]["task_projection_id"],
                },
                source="test_router",
            )

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
    assert lookup_calls == [
        {
            "db": context.db,
            "task_id": checkpoint_task.id,
            "team_id": 1,
            "user_id": 2,
        }
    ]
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


class FakePendingInterruptProjector:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def project(self, request):
        self.calls.append(request)
        if not self.result.projection_key:
            self.result.projection_key = root_runtime_module.pending_interrupt_projection_key(
                request.continuation, request.interrupt
            )
        return self.result


class SequencedPendingInterruptProjector:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def project(self, request):
        self.calls.append(request)
        result = self.results[min(len(self.calls) - 1, len(self.results) - 1)]
        if not result.projection_key:
            result.projection_key = root_runtime_module.pending_interrupt_projection_key(
                request.continuation, request.interrupt
            )
        if result.status == "PROJECTED" and result.current_interrupt is None:
            result.current_interrupt = request.interrupt
        return result




class SequencedPendingApplicationStepProjector:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def project(self, request):
        self.calls.append(request)
        return self.results[min(len(self.calls) - 1, len(self.results) - 1)]


def completed_interaction_application_step(task):
    prompt = "商机信息齐了。要创建商机吗？"
    event = {
        "event": "confirmation_required",
        "task_id": task.id,
        "task_key": task.task_key,
        "action": "create_opportunity",
        "payload": {"customer_id": 7},
        "content": prompt,
    }
    current_interrupt = root_runtime_module.interrupt_from_waiting_event(
        event,
        interaction={
            "schema_version": "agent.interaction.v1",
            "type": "confirmation",
            "business_action": "create_opportunity",
            "status": "waiting_confirmation",
            "prompt": prompt,
            "payload": {"customer_id": 7},
            "task_id": task.id,
            "task_key": task.task_key,
        },
    )
    return PendingApplicationStepProjectionResult(
        status="COMPLETED",
        step_id="ignored-by-fake",
        result={
            "step_type": "interaction",
            "task_snapshot": agent_task_snapshot(task),
            "result": {
                "handled": True,
                "events": [event, {"event": "final", "content": prompt}],
                "assistant_content": prompt,
                "selected_customer": {},
                "remember_pending_task": True,
                "clear_pending_task_id": None,
                "current_interrupt": current_interrupt,
            },
        },
    )

class FakeNewFlowGraphService:
    def __init__(self):
        self.calls = []

    async def stream_events(self, input_state):
        self.calls.append(input_state)
        yield {"event": "agent_step", "step": "semantic_parse", "status": "started"}
        yield {"event": "final", "content": "已处理新流程"}


def test_snapshot_interrupt_identity_distinguishes_consecutive_application_steps():
    continuation = new_pending_task_continuation(
        team_id=2,
        user_id=3,
        session_id=4,
        task_id=101,
        root_thread_id="crm_agent:2:3:4:4",
        checkpoint_ns="pending_task_subgraph:application-step-identity",
    )
    common = {
        "continuation": continuation,
        "task_snapshot": {"id": 101, "task_key": "task-101"},
        "content": "补充金额 10 万",
        "turn_input": {"kind": "text", "content": "补充金额 10 万", "metadata": {}},
    }
    preflight = build_pending_application_step_request(step_type="preflight", **common)
    interaction = build_pending_application_step_request(step_type="interaction", **common)
    snapshot = SimpleNamespace(interrupts=[SimpleNamespace(id="interaction", value=interaction)])

    assert root_runtime_module._same_interrupt_payload(preflight, dict(preflight)) is True
    assert root_runtime_module._same_interrupt_payload(preflight, interaction) is False
    assert root_runtime_module._snapshot_interrupt_payload_except(
        snapshot,
        resumed_interrupt=preflight,
    ) == interaction


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


class FakeCustomerIntelligenceGraphService:
    def __init__(self):
        self.run_calls = []
        self.resume_calls = []

    async def run(self, input_state):
        self.run_calls.append(input_state)
        return {
            "event": {"event_key": "ci-event-1", "customer_id": 101},
            "route": "refresh_profile",
            "visible_trace": [
                {"title": "读取客户上下文", "content": "已读取客户、商机和跟进动态"},
                {"title": "复核客户事实", "content": "提炼出 1 条需复核事实"},
            ],
            "customer_fact_review": {
                "schema_version": "agent.interrupt.v1",
                "type": "confirm",
                "reason": "user_input_required",
                "business_action": "review_customer_facts",
                "allowed_resume_actions": ["approve", "reject", "cancel"],
                "draft_payload": {"customer_name": "越秀金融", "candidate_count": 1},
                "interaction": {
                    "schema_version": "agent.interrupt.v1",
                    "interaction_id": "ci-event-1",
                    "type": "confirm",
                    "business_action": "review_customer_facts",
                    "status": "waiting_confirmation",
                    "title": "确认是否沉淀客户事实",
                    "prompt": "是否沉淀到客户智能档案？",
                    "payload": {"customer_name": "越秀金融"},
                    "allow_cancel": True,
                },
                "source_event": "customer_fact_review_required",
            },
            "__interrupt__": [
                SimpleNamespace(
                    value={
                        "schema_version": "agent.interrupt.v1",
                        "type": "confirm",
                        "reason": "user_input_required",
                        "business_action": "review_customer_facts",
                        "allowed_resume_actions": ["approve", "reject", "cancel"],
                        "draft_payload": {"customer_name": "越秀金融", "candidate_count": 1},
                        "interaction": {
                            "schema_version": "agent.interrupt.v1",
                            "interaction_id": "ci-event-1",
                            "type": "confirm",
                            "business_action": "review_customer_facts",
                            "status": "waiting_confirmation",
                            "title": "确认是否沉淀客户事实",
                            "prompt": "是否沉淀到客户智能档案？",
                            "payload": {"customer_name": "越秀金融"},
                            "allow_cancel": True,
                        },
                        "source_event": "customer_fact_review_required",
                    }
                ),
            ],
            "events": [{"event": "customer_intelligence_fact_review_required"}],
        }

    async def resume_review(self, input_state):
        self.resume_calls.append(input_state)
        return {
            "event": {"event_key": input_state["event_key"], "customer_id": 101},
            "route": "refresh_profile",
            "visible_trace": [
                {"title": "复核客户事实", "content": "已确认沉淀"},
                {"title": "沉淀客户事实", "content": "已沉淀 1 条客户事实"},
            ],
            "customer_fact_review": {"status": "resolved", "resume_action": "approve"},
            "persisted_customer_fact_refs": [{"fact_id": 901}],
            "events": [{"event": "customer_intelligence_facts_persisted"}],
        }


class FakeAnsweringCustomerIntelligenceGraphService:
    def __init__(self):
        self.run_calls = []

    async def run(self, input_state):
        self.run_calls.append(input_state)
        event = input_state["event"]
        return {
            "event": {"event_key": event.event_key, "customer_id": event.customer_id},
            "route": "answer_context",
            "customer_context_answer": {
                "answer": "越秀金融当前正在推进 CRM 项目，商机处于 POC 阶段。",
                "confidence": 0.86,
                "used_sections": ["customer", "opportunities", "activities"],
                "missing_context": [],
            },
            "assistant_content": "越秀金融当前正在推进 CRM 项目，商机处于 POC 阶段。",
            "visible_trace": [
                {"title": "读取客户上下文", "content": "已读取客户智能上下文"},
                {"title": "制定更新计划", "content": "本次用于回答客户问题"},
                {"title": "生成客户回答", "content": "已基于客户档案、业务上下文和检索证据整理回答，置信度 86%"},
            ],
            "events": [{"event": "customer_intelligence_trace_ready"}],
        }


class FakeStreamingCustomerIntelligenceGraphService:
    def __init__(self):
        self.stream_calls = []

    async def stream_run(self, input_state):
        self.stream_calls.append(input_state)
        event = input_state["event"]
        yield {
            "kind": "event",
            "event": {
                "event": "agent_step",
                "step": "customer_intelligence",
                "status": "completed",
                "content": "读取客户上下文：已读取客户智能上下文",
            },
        }
        yield {
            "kind": "event",
            "event": {
                "event": "agent_step",
                "step": "customer_intelligence",
                "status": "completed",
                "content": "制定更新计划：本次用于回答客户问题",
            },
        }
        yield {
            "kind": "event",
            "event": {
                "event": "agent_step",
                "step": "customer_intelligence",
                "status": "completed",
                "content": "生成客户回答：已基于客户档案、业务上下文和检索证据整理回答，置信度 86%",
            },
        }
        yield {
            "kind": "result",
            "result": {
                "event": {"event_key": event.event_key, "customer_id": event.customer_id},
                "route": "answer_context",
                "customer_context_answer": {
                    "answer": "越秀金融当前正在推进 CRM 项目，商机处于 POC 阶段。",
                    "confidence": 0.86,
                    "used_sections": ["customer", "opportunities", "activities"],
                    "missing_context": [],
                },
                "assistant_content": "越秀金融当前正在推进 CRM 项目，商机处于 POC 阶段。",
                "visible_trace": [
                    {"title": "读取客户上下文", "content": "已读取客户智能上下文"},
                    {"title": "制定更新计划", "content": "本次用于回答客户问题"},
                    {"title": "生成客户回答", "content": "已基于客户档案、业务上下文和检索证据整理回答，置信度 86%"},
                ],
                "events": [{"event": "customer_intelligence_trace_ready"}],
            },
        }


class FakeEmptyAnswerCustomerIntelligenceGraphService:
    def __init__(self):
        self.run_calls = []

    async def run(self, input_state):
        self.run_calls.append(input_state)
        event = input_state["event"]
        return {
            "event": {"event_key": event.event_key, "customer_id": event.customer_id},
            "route": "answer_context",
            "customer_context_answer": {},
            "visible_trace": [
                {"title": "读取客户上下文", "content": "已读取客户智能上下文"},
                {"title": "生成客户回答", "content": "客户资料不足，暂时无法整理回答"},
            ],
            "events": [{"event": "customer_context_answer_empty"}],
        }


class FakeCustomerIntelligenceTriggerPolicy:
    def __init__(self, event=None):
        self.event = event
        self.new_flow_calls = []
        self.tool_result_calls = []

    def from_new_flow_events(self, events, *, turn):
        self.new_flow_calls.append({"events": events, "turn": turn})
        return self.event

    def from_confirmed_tool_result(self, db, tool_result, *, team_id):
        self.tool_result_calls.append({"db": db, "tool_result": tool_result, "team_id": team_id})
        return self.event


class FakeCustomerIntelligenceRefreshService:
    def __init__(self):
        self.trigger_calls = []
        self.bind_batch_calls = []
        self.kick_calls = []

    def bind_committed_events_to_agent(self, db, *, team_id, request_ids, binding):
        self.bind_batch_calls.append(
            {
                "db": db,
                "team_id": team_id,
                "request_ids": list(request_ids),
                "binding": binding,
            }
        )
        return tuple(
            SimpleNamespace(
                request_id=request_id,
                event=SimpleNamespace(trigger_type="customer_activity_created"),
                scope="brief",
                scheduled=True,
                kick_required=False,
                schedule_error=None,
                operation_public_id=f"aop-{request_id}",
            )
            for request_id in request_ids
        )

    def kick_committed_event_refresh(self, request):
        self.kick_calls.append(request)

    async def trigger_committed_event_refresh(self, db, *, event, scope="brief", agent_binding=None):
        self.trigger_calls.append(
            {
                "db": db,
                "event": event,
                "scope": scope,
                "agent_binding": agent_binding,
            }
        )
        return SimpleNamespace(
            request_id=f"business-event-{event.trigger_type}-test",
            event=event,
            scope=scope,
            scheduled=True,
            schedule_error=None,
            operation_public_id="aop_customer_intelligence_test",
        )


class FakeFailedCustomerIntelligenceRefreshService(FakeCustomerIntelligenceRefreshService):
    async def trigger_committed_event_refresh(self, db, *, event, scope="brief", agent_binding=None):
        self.trigger_calls.append(
            {
                "db": db,
                "event": event,
                "scope": scope,
                "agent_binding": agent_binding,
            }
        )
        return SimpleNamespace(
            request_id=f"business-event-{event.trigger_type}-failed",
            event=event,
            scope=scope,
            scheduled=False,
            schedule_error="operation projection unavailable",
            operation_public_id=None,
        )


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

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "记录一下客户跟进",
            "turn_kind": "text",
            "current_customer": {"id": 10, "account_name": "睿狐科技"},
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4),
            content="记录一下客户跟进",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
    )

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
async def test_root_runtime_bubbles_customer_intelligence_review_interrupt():
    customer_intelligence_graph_service = FakeCustomerIntelligenceGraphService()
    side_effects = AgentRootRuntimeSideEffects()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeNewFlowGraphService(),
        customer_intelligence_graph_service=customer_intelligence_graph_service,
    )

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "刷新客户档案",
            "turn_kind": "text",
            "customer_intelligence_requested": True,
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            content="刷新客户档案",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            customer_intelligence_event=SimpleNamespace(event_key="ci-event-1"),
            side_effects=side_effects,
        ),
    )

    assert customer_intelligence_graph_service.run_calls
    assert state["current_interrupt"]["business_action"] == "review_customer_facts"
    assert state["customer_intelligence_event"]["event_key"] == "ci-event-1"
    assert state["customer_intelligence_result"]["has_interrupt"] is True
    assert state["__interrupt__"][0].value["business_action"] == "review_customer_facts"
    assert side_effects.current_interrupt["business_action"] == "review_customer_facts"
    assert side_effects.customer_intelligence_events[-1]["event"] == "final"


@pytest.mark.asyncio
async def test_root_runtime_routes_customer_query_to_customer_intelligence_graph():
    customer_intelligence_event = SimpleNamespace(
        event_key="agent-question-1",
        customer_id=101,
    )
    customer_intelligence_graph_service = FakeAnsweringCustomerIntelligenceGraphService()
    trigger_policy = FakeCustomerIntelligenceTriggerPolicy(customer_intelligence_event)
    side_effects = AgentRootRuntimeSideEffects()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeNewFlowGraphService(),
        customer_intelligence_graph_service=customer_intelligence_graph_service,
        customer_intelligence_trigger_policy=trigger_policy,
    )

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "总结一下这个客户",
            "turn_kind": "text",
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            content="总结一下这个客户",
            team_id=2,
            user_id=3,
            session_id=4,
            user_message_id=88,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
    )

    assert trigger_policy.new_flow_calls
    assert customer_intelligence_graph_service.run_calls[0]["event"] == customer_intelligence_event
    assert state["customer_intelligence_requested"] is False
    assert state["customer_intelligence_result"]["route"] == "answer_context"
    assert state["assistant_content"] == "越秀金融当前正在推进 CRM 项目，商机处于 POC 阶段。"
    assert [event for event in side_effects.new_flow_events if event.get("event") == "final"] == []
    assert side_effects.customer_intelligence_assistant_content == "越秀金融当前正在推进 CRM 项目，商机处于 POC 阶段。"
    assert side_effects.customer_intelligence_events[-1] == {
        "event": "final",
        "content": "越秀金融当前正在推进 CRM 项目，商机处于 POC 阶段。",
        "content_format": "markdown",
    }
    output = project_turn_output(state, side_effects)
    assert [
        (event.get("content"), event.get("content_format")) for event in output.events if event.get("event") == "final"
    ] == [("越秀金融当前正在推进 CRM 项目，商机处于 POC 阶段。", "markdown")]
    assert output.assistant_content == "越秀金融当前正在推进 CRM 项目，商机处于 POC 阶段。"


@pytest.mark.asyncio
async def test_root_runtime_does_not_reuse_new_flow_completion_when_customer_answer_is_empty():
    customer_intelligence_event = SimpleNamespace(
        event_key="agent-question-empty-1",
        customer_id=101,
    )
    customer_intelligence_graph_service = FakeEmptyAnswerCustomerIntelligenceGraphService()
    trigger_policy = FakeCustomerIntelligenceTriggerPolicy(customer_intelligence_event)
    side_effects = AgentRootRuntimeSideEffects()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeNewFlowGraphService(),
        customer_intelligence_graph_service=customer_intelligence_graph_service,
        customer_intelligence_trigger_policy=trigger_policy,
    )

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "汇川技术现在是什么情况",
            "turn_kind": "text",
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            content="汇川技术现在是什么情况",
            team_id=2,
            user_id=3,
            session_id=4,
            user_message_id=88,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
    )

    output = project_turn_output(state, side_effects)
    final_contents = [event.get("content") for event in output.events if event.get("event") == "final"]
    assert output.assistant_content == "客户资料不足，暂时无法整理回答。"
    assert final_contents == ["客户资料不足，暂时无法整理回答。"]
    assert "已处理新流程" not in final_contents
    assert side_effects.new_flow_assistant_content == "已处理新流程"


@pytest.mark.asyncio
async def test_root_runtime_streams_customer_intelligence_trace_without_duplicate_batch_events():
    customer_intelligence_event = SimpleNamespace(
        event_key="agent-question-stream-1",
        customer_id=101,
    )
    customer_intelligence_graph_service = FakeStreamingCustomerIntelligenceGraphService()
    trigger_policy = FakeCustomerIntelligenceTriggerPolicy(customer_intelligence_event)
    side_effects = AgentRootRuntimeSideEffects()
    streamed_events = []
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeNewFlowGraphService(),
        customer_intelligence_graph_service=customer_intelligence_graph_service,
        customer_intelligence_trigger_policy=trigger_policy,
    )

    async def event_sink(event):
        streamed_events.append(event)

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "总结一下这个客户",
            "turn_kind": "text",
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            content="总结一下这个客户",
            team_id=2,
            user_id=3,
            session_id=4,
            user_message_id=88,
            authorization="Bearer test",
            event_sink=event_sink,
            side_effects=side_effects,
        ),
    )

    customer_intelligence_step_contents = [
        event["content"]
        for event in side_effects.customer_intelligence_events
        if event.get("event") == "agent_step" and event.get("step") == "customer_intelligence"
    ]
    assert customer_intelligence_graph_service.stream_calls[0]["event"] == customer_intelligence_event
    assert state["customer_intelligence_result"]["route"] == "answer_context"
    assert customer_intelligence_step_contents == [
        "更新客户智能档案",
        "读取客户上下文：已读取客户智能上下文",
        "制定更新计划：本次用于回答客户问题",
        "生成客户回答：已基于客户档案、业务上下文和检索证据整理回答，置信度 86%",
    ]
    assert [
        event["content"]
        for event in streamed_events
        if event.get("event") == "agent_step" and event.get("step") == "customer_intelligence"
    ] == customer_intelligence_step_contents
    assert [
        (event.get("content"), event.get("content_format"))
        for event in streamed_events
        if event.get("event") == "final"
    ] == [("越秀金融当前正在推进 CRM 项目，商机处于 POC 阶段。", "markdown")]
    assert state["assistant_content"] == "越秀金融当前正在推进 CRM 项目，商机处于 POC 阶段。"


@pytest.mark.asyncio
async def test_root_runtime_records_customer_intelligence_schedule_intent_without_projection_side_effects():
    customer_intelligence_event = SimpleNamespace(
        event_key="activity-created-1",
        trigger_type="customer_activity_created",
        customer_id=101,
    )
    customer_intelligence_graph_service = FakeAnsweringCustomerIntelligenceGraphService()
    customer_intelligence_refresh_service = FakeCustomerIntelligenceRefreshService()
    trigger_policy = FakeCustomerIntelligenceTriggerPolicy(customer_intelligence_event)
    side_effects = AgentRootRuntimeSideEffects()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        pending_graph_service=FakeConfirmingPendingGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
        customer_intelligence_graph_service=customer_intelligence_graph_service,
        customer_intelligence_trigger_policy=trigger_policy,
        customer_intelligence_refresh_service=customer_intelligence_refresh_service,
    )
    task = waiting_task_stub()

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
            "task_projection": {"id": task.id, "task_key": task.task_key},
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            task=task,
            turn_input=AgentTurnInput.confirm(source="web"),
            content="确认",
            team_id=2,
            user_id=3,
            session_id=4,
            user_message_id=91,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
    )

    assert trigger_policy.tool_result_calls
    assert customer_intelligence_graph_service.run_calls == []
    assert customer_intelligence_refresh_service.trigger_calls == []
    assert customer_intelligence_refresh_service.bind_batch_calls == []
    assert customer_intelligence_refresh_service.kick_calls == []
    assert state["customer_intelligence_schedule_intent"] == {
        "event": {
            "event_key": "activity-created-1",
            "trigger_type": "customer_activity_created",
            "customer_id": 101,
        },
        "scope": "brief",
        "request_ids": [],
    }
    assert state["customer_intelligence_result"] == {
        "handled": True,
        "mode": "background",
        "scheduled": False,
        "projection_status": "PENDING",
        "trigger_type": "customer_activity_created",
        "event_key": "activity-created-1",
        "customer_id": 101,
        "scope": "brief",
    }
    assert side_effects.confirmed_task_assistant_content == "跟进记录已创建。"
    assert side_effects.customer_intelligence_events == []
    assert any(
        event.get("event") == "agent_root_customer_intelligence_refresh_requested"
        for event in state["events"]
    )


@pytest.mark.asyncio
async def test_root_runtime_does_not_observe_projection_failure_inside_graph_node():
    customer_intelligence_event = SimpleNamespace(
        event_key="activity-created-failed",
        trigger_type="customer_activity_created",
        customer_id=101,
    )
    refresh_service = FakeFailedCustomerIntelligenceRefreshService()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        pending_graph_service=FakeConfirmingPendingGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
        customer_intelligence_trigger_policy=FakeCustomerIntelligenceTriggerPolicy(customer_intelligence_event),
        customer_intelligence_refresh_service=refresh_service,
    )
    task = waiting_task_stub()

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
            "task_projection": {"id": task.id, "task_key": task.task_key},
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            task=task,
            turn_input=AgentTurnInput.confirm(source="web"),
            content="确认",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
        ),
    )

    assert refresh_service.trigger_calls == []
    assert state["customer_intelligence_result"]["projection_status"] == "PENDING"
    assert state["customer_intelligence_result"]["scheduled"] is False


@pytest.mark.asyncio
async def test_root_runtime_resumes_customer_intelligence_review_through_root_interrupt():
    customer_intelligence_graph_service = FakeCustomerIntelligenceGraphService()
    side_effects = AgentRootRuntimeSideEffects()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeNewFlowGraphService(),
        customer_intelligence_graph_service=customer_intelligence_graph_service,
    )
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        content="刷新客户档案",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        customer_intelligence_event=SimpleNamespace(event_key="ci-event-1"),
        side_effects=side_effects,
    )

    first_state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "刷新客户档案",
            "turn_kind": "text",
            "customer_intelligence_requested": True,
        },
        context=context,
    )

    resumed_side_effects = AgentRootRuntimeSideEffects()
    resumed_state = await runtime.resume_interrupt(
        resume_payload={
            "action": "approve",
            "source": "web",
            "business_action": "review_customer_facts",
            "interrupt_reason": "user_input_required",
        },
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        current_interrupt=first_state["current_interrupt"],
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            content="确认",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=resumed_side_effects,
        ),
    )

    assert customer_intelligence_graph_service.resume_calls[0]["event_key"] == "ci-event-1"
    assert customer_intelligence_graph_service.resume_calls[0]["resume_payload"]["action"] == "approve"
    assert resumed_state["current_interrupt"] is None
    assert resumed_state["customer_intelligence_result"]["persisted_fact_count"] == 1
    assert resumed_side_effects.customer_intelligence_assistant_content == "客户智能档案已更新，沉淀了 1 条客户事实。"


@pytest.mark.asyncio
async def test_root_runtime_resets_turn_scoped_result_projections_between_invokes():
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeNewFlowGraphService(),
    )

    first_state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "记录一下客户跟进",
            "turn_kind": "text",
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            content="记录一下客户跟进",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=AgentRootRuntimeSideEffects(),
        ),
    )

    second_state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "确认",
            "turn_kind": "confirm",
            "current_interrupt": {"type": "confirm", "business_action": "CREATE_FOLLOW_UP"},
        }
    )

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
        waiting_events.append(event)
        return _persisted_waiting_task_from_event(
            event,
            team_id=team_id,
            user_id=user_id,
            session_id=session_arg.id,
        )

    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.task_factory._create_waiting_task_from_event",
        create_waiting_task,
    )
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeSideEffectNewFlowGraphService(),
    )
    side_effects = AgentRootRuntimeSideEffects()

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "今天和越秀金融沟通",
            "turn_kind": "text",
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            content="今天和越秀金融沟通",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            switch_notice="我先切到新流程处理。",
            side_effects=side_effects,
        ),
    )

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

    async def fake_execute_action_envelope(db, envelope, *, session, team_id, user_id, authorization, event_sink):
        return ActionToolExecutionResult(
            AgentToolResult(
                tool_name="create_customer_activity",
                success=True,
                data={"id": 901},
                tool_call_id=7001,
            )
        )

    monkeypatch.setattr(root_runtime_module.task_execution, "execute_action_envelope", fake_execute_action_envelope)
    monkeypatch.setattr(
        root_runtime_module.workflow_action_ledger, "mark_action_executed", lambda *args, **kwargs: None
    )
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=confirmed_task_graph_service,
    )
    side_effects = AgentRootRuntimeSideEffects()

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "今天和越秀金融沟通",
            "turn_kind": "text",
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            content="今天和越秀金融沟通",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
    )

    assert created_tasks == []
    assert confirmed_task_graph_service.calls == []
    assert state["current_interrupt"] is None
    assert state["new_flow_result"]["has_interrupt"] is False
    assert state["assistant_content"] == agent_copy.customer_activity_created()
    assert "请确认是否创建这条跟进记录？" not in [
        event.get("content") for event in side_effects.new_flow_events if event.get("event") == "final"
    ]
    assert [event["event"] for event in side_effects.new_flow_events].count("action_review_decided") == 1
    assert [event["event"] for event in side_effects.new_flow_events].count("action_auto_execution_queued") == 1
    assert {
        "event": "agent_step",
        "step": "auto_execute_action",
        "status": "started",
        "content": "记录跟进",
    } in side_effects.new_flow_events
    assert "确认记录跟进" not in str([event.get("content") for event in side_effects.new_flow_events])


@pytest.mark.asyncio
async def test_in_context_auto_execute_surfaces_confirmed_ownership_rejection():
    published_events: list[dict[str, object]] = []

    async def capture_event(event):
        published_events.append(event)

    class MismatchedNextOwnerGraph(FakeConfirmedTaskWithNextGraphService):
        async def run(self, state):
            result = await super().run(state)
            result["active_task_snapshot"]["session_id"] = 999
            return result

    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=MismatchedNextOwnerGraph(),
    )
    task = _persisted_waiting_task_from_event(
        {
            "action": "create_customer_activity",
            "payload": {"customer_id": 101, "content": "已沟通项目进展"},
            "content": "请确认是否创建这条跟进记录？",
        },
        team_id=2,
        user_id=3,
        session_id=4,
    )
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        turn_input=AgentTurnInput(content="自动执行", source="web"),
        content="自动执行",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        event_sink=capture_event,
        side_effects=AgentRootRuntimeSideEffects(),
    )

    result = await runtime._run_new_flow_auto_execute_task_in_context(
        context,
        task,
        include_graph_progress_events=True,
    )

    assert result["current_interrupt"] is None
    assert result["active_task_snapshot"] == {}
    assert result["ownership_rejection_event"] == {
        "event": "agent_root_confirmed_task_ownership_rejected",
        "reason": "active_task_owner_mismatch",
        "expected_task_id": 501,
        "executed_task_id": 501,
        "next_task_id": 102,
        "active_task_id": 102,
    }
    assert result["ownership_rejection_event"] in published_events


@pytest.mark.asyncio
async def test_parallel_auto_execute_fails_closed_when_branches_emit_distinct_active_tasks(monkeypatch):
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
    )

    async def fake_isolated(branch_input):
        source_task_id = branch_input["task_id"]
        active_task_id = 102 if source_task_id == 501 else 103
        return {
            "result": {"execution_status": "completed"},
            "tool_result": {"success": True, "task_id": source_task_id},
            "events": [],
            "emitted_event_count": 0,
            "active_task_snapshot": _waiting_task_snapshot(active_task_id),
        }

    monkeypatch.setattr(runtime, "_run_new_flow_auto_execute_task_isolated", fake_isolated)
    side_effects = AgentRootRuntimeSideEffects()
    result = await runtime._run_new_flow_auto_execute_tasks_parallel(
        AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            turn_input=AgentTurnInput(content="并行自动执行", source="web"),
            content="并行自动执行",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
        [
            SimpleNamespace(id=501, state_json={"action": "create_customer_activity"}),
            SimpleNamespace(id=502, state_json={"action": "transition_follow_up_task"}),
        ],
    )

    assert result["current_interrupt"] is None
    assert result["active_task_snapshot"] == {}
    assert result["ownership_rejection_event"] == {
        "event": "agent_root_active_task_ownership_rejected",
        "reason": "multiple_active_tasks",
        "source": "new_flow_auto_execute_parallel_tasks",
        "active_task_ids": [102, 103],
        "candidate_sources": ["parallel_task:501", "parallel_task:502"],
    }
    assert result["ownership_rejection_event"] in side_effects.new_flow_events


@pytest.mark.asyncio
async def test_root_checkpoints_next_task_from_new_flow_auto_execution(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.session_state._remember_current_customer",
        lambda db_arg, session_arg, customer: None,
    )
    monkeypatch.setattr(
        root_runtime_module.task_execution,
        "can_direct_execute_action_envelope",
        lambda envelope: False,
    )

    def create_waiting_task(db_arg, event, team_id, user_id, session_arg):
        return _persisted_waiting_task_from_event(
            event,
            team_id=team_id,
            user_id=user_id,
            session_id=session_arg.id,
        )

    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.task_factory._create_waiting_task_from_event",
        create_waiting_task,
    )
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskWithNextGraphService(),
    )
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        content="今天和越秀金融沟通",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "new-flow-auto-next-owner",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
        },
        context=context,
    )

    assert state["pending_task_snapshot"]["id"] == 102
    assert state["task_projection"]["id"] == 102
    assert state["pending_task_requested"] is True
    assert state["current_interrupt"]["task_projection_id"] == 102
    assert state["current_interrupt"]["task_projection_key"] == "task-102"
    assert state["current_interrupt"]["type"] == "form"


@pytest.mark.asyncio
async def test_root_runtime_serializes_ready_write_tasks_unless_parallel_safe(monkeypatch):
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
    )
    started: list[int] = []

    async def fake_in_context(context, node, *, include_graph_progress_events):
        task_id = node.task_id
        started.append(task_id)
        return {
            "result": {
                "assistant_content": f"任务 {task_id} 已执行。",
                "tool_result": {"event": "tool_result", "success": True, "task_id": task_id},
            },
            "tool_result": {"event": "tool_result", "success": True, "task_id": task_id},
            "events": [{"event": "task_completed", "task_id": task_id, "content": f"任务 {task_id} 已执行。"}],
            "emitted_event_count": 1,
            "assistant_content": f"任务 {task_id} 已执行。",
        }

    monkeypatch.setattr(runtime, "_run_new_flow_auto_execute_node_in_context", fake_in_context)
    side_effects = AgentRootRuntimeSideEffects()
    result = await runtime._run_new_flow_auto_execute_tasks(
        AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            turn_input=AgentTurnInput(content="批量自动执行", source="web"),
            content="批量自动执行",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
        SimpleNamespace(
            auto_execute_tasks=[
                SimpleNamespace(id=501, state_json={"action": "create_customer_activity"}),
                SimpleNamespace(id=502, state_json={"action": "transition_follow_up_task"}),
            ],
        ),
    )

    assert result["mode"] == "single_in_context"
    assert started == [501, 502]
    assert result["emitted_event_count"] == 4
    assert [event["event"] for event in side_effects.new_flow_events] == [
        "agent_root_auto_execute_plan_built",
        "task_completed",
        "agent_root_auto_execute_plan_built",
        "task_completed",
    ]
    assert side_effects.new_flow_events[0]["ready_count"] == 2
    assert side_effects.new_flow_events[2]["ready_count"] == 1


@pytest.mark.asyncio
async def test_root_runtime_executes_auto_execute_tasks_in_dependency_rounds(monkeypatch):
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
    )
    started: list[int] = []

    async def fake_in_context(context, task, *, include_graph_progress_events):
        started.append(task.id)
        return {
            "result": {"assistant_content": f"任务 {task.id} 已执行。"},
            "tool_result": {"event": "tool_result", "success": True, "task_id": task.id},
            "events": [{"event": "task_completed", "task_id": task.id}],
            "emitted_event_count": 1,
            "assistant_content": f"任务 {task.id} 已执行。",
        }

    monkeypatch.setattr(runtime, "_run_new_flow_auto_execute_task_in_context", fake_in_context)
    side_effects = AgentRootRuntimeSideEffects()
    result = await runtime._run_new_flow_auto_execute_tasks(
        AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            turn_input=AgentTurnInput(content="依赖自动执行", source="web"),
            content="依赖自动执行",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
        SimpleNamespace(
            auto_execute_tasks=[
                SimpleNamespace(
                    id=501,
                    state_json={
                        "action": "create_customer_activity",
                        "workflow": _test_workflow("act_first", action_type="create_customer_activity"),
                    },
                ),
                SimpleNamespace(
                    id=502,
                    state_json={
                        "action": "transition_follow_up_task",
                        "workflow": _test_workflow(
                            "act_second",
                            action_type="transition_follow_up_task",
                            dependency_json={"depends_on": ["act_first"]},
                        ),
                    },
                ),
            ],
        ),
    )

    assert started == [501, 502]
    assert result["executed_action_count"] == 2
    plan_events = [
        event for event in side_effects.new_flow_events if event["event"] == "agent_root_auto_execute_plan_built"
    ]
    assert [event["ready_count"] for event in plan_events] == [1, 1]
    assert [event["blocked_count"] for event in plan_events] == [1, 0]


@pytest.mark.asyncio
async def test_root_runtime_records_auto_execute_running_and_blocked_actions(monkeypatch):
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
    )
    ledger_events: list[dict] = []

    class FakeSession:
        def query(self, *args, **kwargs):
            return None

    def fake_ledger_state(db, *, action_ids, team_id, user_id, include_system_actions=True):
        return {
            "satisfied_action_ids": [],
            "terminal_action_ids": [],
        }

    def fake_mark_running(db, **kwargs):
        ledger_events.append(
            {
                "status": "RUNNING",
                "action_id": kwargs["workflow"]["action_id"],
                "task_id": kwargs["task_id"],
                "payload": kwargs["payload"],
                "target_type": kwargs["target_type"],
                "target_id": kwargs["target_id"],
                "reason": kwargs["reason"],
            }
        )

    def fake_mark_blocked(db, **kwargs):
        ledger_events.append(
            {
                "status": "BLOCKED",
                "action_id": kwargs["workflow"]["action_id"],
                "task_id": kwargs["task_id"],
                "payload": kwargs["payload"],
                "target_type": kwargs["target_type"],
                "target_id": kwargs["target_id"],
                "reason": kwargs["reason"],
            }
        )

    async def fake_in_context(context, task, *, include_graph_progress_events):
        return {
            "result": {"assistant_content": f"任务 {task.id} 已执行。"},
            "tool_result": {"event": "tool_result", "success": True, "task_id": task.id},
            "events": [{"event": "task_completed", "task_id": task.id}],
            "emitted_event_count": 1,
            "assistant_content": f"任务 {task.id} 已执行。",
        }

    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "execution_state_for_action_ids", fake_ledger_state)
    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "mark_action_running", fake_mark_running)
    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "mark_action_blocked", fake_mark_blocked)
    monkeypatch.setattr(runtime, "_run_new_flow_auto_execute_task_in_context", fake_in_context)
    side_effects = AgentRootRuntimeSideEffects()
    await runtime._run_new_flow_auto_execute_tasks(
        AgentRuntimeContext(
            db=FakeSession(),
            session=SimpleNamespace(id=4, context_json={}),
            turn_input=AgentTurnInput(content="ledger 状态记录", source="web"),
            content="ledger 状态记录",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
        SimpleNamespace(
            auto_execute_tasks=[
                SimpleNamespace(
                    id=501,
                    state_json={
                        "action": "create_customer_activity",
                        "payload": {"content": "今天拜访客户"},
                        "workflow": _test_workflow("act_first", action_type="create_customer_activity"),
                    },
                    input_json={},
                    target_type="customer",
                    target_id=9,
                ),
                SimpleNamespace(
                    id=502,
                    state_json={
                        "action": "transition_follow_up_task",
                        "workflow": _test_workflow(
                            "act_second",
                            action_type="transition_follow_up_task",
                            dependency_json={"depends_on": ["act_first"]},
                        ),
                    },
                    input_json={},
                    target_type="customer",
                    target_id=9,
                ),
            ],
        ),
    )

    assert ledger_events == [
        {
            "status": "BLOCKED",
            "action_id": "act_second",
            "task_id": 502,
            "payload": {},
            "target_type": "customer",
            "target_id": 9,
            "reason": "waiting_dependencies:act_first",
        },
        {
            "status": "RUNNING",
            "action_id": "act_first",
            "task_id": 501,
            "payload": {"content": "今天拜访客户"},
            "target_type": "customer",
            "target_id": 9,
            "reason": "AUTO_EXECUTION_READY",
        },
        {
            "status": "RUNNING",
            "action_id": "act_second",
            "task_id": 502,
            "payload": {},
            "target_type": "customer",
            "target_id": 9,
            "reason": "AUTO_EXECUTION_READY",
        },
    ]


@pytest.mark.asyncio
async def test_root_runtime_prefers_action_level_plan_items_over_legacy_task_payload(monkeypatch):
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
    )
    ledger_events: list[dict] = []

    class FakeSession:
        def query(self, *args, **kwargs):
            return None

    def fake_ledger_state(db, *, action_ids, team_id, user_id, include_system_actions=True):
        return {
            "satisfied_action_ids": [],
            "running_action_ids": [],
            "terminal_action_ids": [],
        }

    def fake_mark_running(db, **kwargs):
        ledger_events.append(
            {
                "action_id": kwargs["workflow"]["action_id"],
                "payload": kwargs["payload"],
                "target_type": kwargs["target_type"],
                "target_id": kwargs["target_id"],
            }
        )

    async def fake_in_context(context, task, *, include_graph_progress_events):
        return {
            "result": {"assistant_content": "已执行。"},
            "tool_result": {"event": "tool_result", "success": True, "task_id": task.id},
            "events": [{"event": "task_completed", "task_id": task.id}],
            "emitted_event_count": 1,
            "assistant_content": "已执行。",
        }

    workflow = _test_workflow("act_action_envelope", action_type="create_customer_activity")
    task = SimpleNamespace(
        id=501,
        state_json={
            "action": "create_customer_activity",
            "payload": {"content": "legacy payload should not win"},
            "workflow": workflow,
        },
        input_json={},
        target_type="customer",
        target_id=9,
    )
    action_item = action_plan.item_from_workflow(
        workflow,
        payload={"content": "action envelope payload"},
        task=task,
        task_id=501,
        target_type="customer",
        target_id=10,
    )
    assert action_item is not None

    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "execution_state_for_action_ids", fake_ledger_state)
    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "mark_action_running", fake_mark_running)
    monkeypatch.setattr(runtime, "_run_new_flow_auto_execute_task_in_context", fake_in_context)
    await runtime._run_new_flow_auto_execute_tasks(
        AgentRuntimeContext(
            db=FakeSession(),
            session=SimpleNamespace(id=4, context_json={}),
            turn_input=AgentTurnInput(content="action envelope 优先", source="web"),
            content="action envelope 优先",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=AgentRootRuntimeSideEffects(),
        ),
        SimpleNamespace(
            auto_execute_tasks=[task],
            auto_execute_actions=[action_item],
        ),
    )

    assert ledger_events == [
        {
            "action_id": "act_action_envelope",
            "payload": {"content": "action envelope payload"},
            "target_type": "customer",
            "target_id": 10,
        }
    ]


@pytest.mark.asyncio
async def test_root_runtime_blocks_action_level_plan_item_without_task_projection(monkeypatch):
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
    )
    ledger_events: list[dict] = []

    class FakeSession:
        def query(self, *args, **kwargs):
            return None

    def fake_ledger_state(db, *, action_ids, team_id, user_id, include_system_actions=True):
        return {
            "satisfied_action_ids": [],
            "running_action_ids": [],
            "terminal_action_ids": [],
        }

    def fake_mark_blocked(db, **kwargs):
        ledger_events.append(
            {
                "action_id": kwargs["workflow"]["action_id"],
                "reason": kwargs["reason"],
                "payload": kwargs["payload"],
            }
        )

    workflow = _test_workflow("act_without_task", action_type="create_customer_activity")
    action_item = action_plan.item_from_workflow(
        workflow,
        payload={"content": "action without task"},
        target_type="customer",
        target_id=10,
    )
    assert action_item is not None

    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "execution_state_for_action_ids", fake_ledger_state)
    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "mark_action_blocked", fake_mark_blocked)
    result = await runtime._run_new_flow_auto_execute_tasks(
        context := AgentRuntimeContext(
            db=FakeSession(),
            session=SimpleNamespace(id=4, context_json={}),
            turn_input=AgentTurnInput(content="缺少 task 投影", source="web"),
            content="缺少 task 投影",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=AgentRootRuntimeSideEffects(),
        ),
        SimpleNamespace(
            auto_execute_tasks=[],
            auto_execute_actions=[action_item],
        ),
    )

    assert result["executed_action_count"] == 0
    assert ledger_events == [
        {
            "action_id": "act_without_task",
            "reason": "missing_task_projection",
            "payload": {"content": "action without task"},
        }
    ]
    blocked_event = next(
        event
        for event in context.side_effects.new_flow_events
        if event["event"] == "agent_root_auto_execute_plan_blocked"
    )
    assert blocked_event["blocked_actions"] == [
        {
            "action_id": "act_without_task",
            "action_type": "create_customer_activity",
            "task_id": None,
            "reason": "missing_task_projection",
        }
    ]


@pytest.mark.asyncio
async def test_root_runtime_directly_executes_complete_action_level_plan_item_without_task_projection(monkeypatch):
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
    )
    executed = []
    ledger_executed = []

    class FakeSession:
        def query(self, *args, **kwargs):
            return None

    def fake_ledger_state(db, *, action_ids, team_id, user_id, include_system_actions=True):
        return {
            "satisfied_action_ids": [],
            "running_action_ids": [],
            "terminal_action_ids": [],
        }

    async def fake_execute_action_envelope(db, envelope, *, session, team_id, user_id, authorization, event_sink):
        executed.append(
            {
                "action_id": envelope.action_id,
                "action_type": envelope.action_type,
                "payload": envelope.payload,
                "customer": envelope.customer,
                "authorization": authorization,
            }
        )
        return ActionToolExecutionResult(
            AgentToolResult(
                tool_name="create_customer_activity",
                success=True,
                data={"id": 901},
                tool_call_id=7001,
            )
        )

    def fake_mark_executed(db, **kwargs):
        ledger_executed.append(kwargs)

    workflow = _test_workflow("act_without_task", action_type="create_customer_activity")
    action_item = action_plan.item_from_workflow(
        workflow,
        payload={
            "customer_id": 10,
            "source_content": "今天和客户确认了续费推进事项",
            "customer": {"id": 10, "account_name": "测试客户"},
        },
        target_type="customer",
        target_id=10,
    )
    assert action_item is not None

    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "execution_state_for_action_ids", fake_ledger_state)
    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "mark_action_executed", fake_mark_executed)
    monkeypatch.setattr(root_runtime_module.task_execution, "execute_action_envelope", fake_execute_action_envelope)

    result = await runtime._run_new_flow_auto_execute_tasks(
        AgentRuntimeContext(
            db=FakeSession(),
            session=SimpleNamespace(id=4, context_json={}),
            turn_input=AgentTurnInput(content="直接执行 action envelope", source="web"),
            content="直接执行 action envelope",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=AgentRootRuntimeSideEffects(),
        ),
        SimpleNamespace(
            auto_execute_tasks=[],
            auto_execute_actions=[action_item],
        ),
    )

    assert result["executed_action_count"] == 1
    assert result["mode"] == "single_action_in_context"
    assert executed == [
        {
            "action_id": "act_without_task",
            "action_type": "create_customer_activity",
            "payload": {
                "customer_id": 10,
                "source_content": "今天和客户确认了续费推进事项",
                "customer": {"id": 10, "account_name": "测试客户"},
            },
            "customer": {"id": 10, "account_name": "测试客户"},
            "authorization": "Bearer test",
        }
    ]
    assert ledger_executed[0]["workflow"] == workflow
    assert ledger_executed[0]["result"] == {"id": 901}


@pytest.mark.asyncio
async def test_root_runtime_blocks_user_authorized_action_without_authorization(monkeypatch):
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
    )
    blocked: list[dict] = []
    executed: list[str] = []

    class FakeSession:
        def query(self, *args, **kwargs):
            return None

    def fake_ledger_state(db, *, action_ids, team_id, user_id, include_system_actions=True):
        return {
            "satisfied_action_ids": [],
            "running_action_ids": [],
            "terminal_action_ids": [],
        }

    def fake_mark_blocked(db, **kwargs):
        blocked.append(kwargs)

    async def fake_execute_action_envelope(db, envelope, *, session, team_id, user_id, authorization, event_sink):
        executed.append(envelope.action_id)
        return ActionToolExecutionResult(None)

    workflow = _test_workflow("act_requires_auth", action_type="create_customer_activity")
    action_item = action_plan.item_from_workflow(
        workflow,
        payload={
            "customer_id": 10,
            "source_content": "今天和客户确认了续费推进事项",
        },
        target_type="customer",
        target_id=10,
    )
    assert action_item is not None

    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "execution_state_for_action_ids", fake_ledger_state)
    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "mark_action_blocked", fake_mark_blocked)
    monkeypatch.setattr(root_runtime_module.task_execution, "execute_action_envelope", fake_execute_action_envelope)

    side_effects = AgentRootRuntimeSideEffects()
    result = await runtime._run_new_flow_auto_execute_tasks(
        AgentRuntimeContext(
            db=FakeSession(),
            session=SimpleNamespace(id=4, context_json={}),
            turn_input=AgentTurnInput(content="后台恢复重放", source="api"),
            content="后台恢复重放",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="",
            side_effects=side_effects,
        ),
        SimpleNamespace(
            auto_execute_tasks=[],
            auto_execute_actions=[action_item],
        ),
    )

    assert result["executed_action_count"] == 0
    assert executed == []
    assert blocked[0]["workflow"] == workflow
    assert blocked[0]["reason"] == "missing_authorization"
    blocked_event = next(
        event for event in side_effects.new_flow_events if event["event"] == "agent_root_auto_execute_plan_blocked"
    )
    assert blocked_event["blocked_actions"] == [
        {
            "action_id": "act_requires_auth",
            "action_type": "create_customer_activity",
            "task_id": None,
            "reason": "missing_authorization",
        }
    ]


@pytest.mark.asyncio
async def test_root_runtime_stops_auto_execute_rounds_when_interrupt_is_created(monkeypatch):
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
    )
    started: list[int] = []

    async def fake_in_context(context, task, *, include_graph_progress_events):
        started.append(task.id)
        return {
            "result": {"assistant_content": "需要确认下一步。"},
            "tool_result": {"event": "tool_result", "success": True, "task_id": task.id},
            "events": [{"event": "confirmation_required", "task_id": 900}],
            "emitted_event_count": 1,
            "assistant_content": "需要确认下一步。",
            "current_interrupt": {
                "schema_version": "agent.interrupt.v1",
                "type": "confirm",
                "reason": "write_confirmation",
                "business_action": "collect_opportunity_fields",
                "target_refs": {},
                "draft_payload": {},
                "allowed_resume_actions": ["approve", "edit", "reject", "cancel"],
                "interaction": {},
                "source_event": "opportunity_fields_required",
                "task_projection_id": 900,
                "task_projection_key": "task-900",
            },
            "active_task_snapshot": _waiting_task_snapshot(900),
        }

    monkeypatch.setattr(runtime, "_run_new_flow_auto_execute_task_in_context", fake_in_context)
    side_effects = AgentRootRuntimeSideEffects()
    result = await runtime._run_new_flow_auto_execute_tasks(
        AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            turn_input=AgentTurnInput(content="依赖自动执行并中断", source="web"),
            content="依赖自动执行并中断",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
        SimpleNamespace(
            auto_execute_tasks=[
                SimpleNamespace(
                    id=501,
                    state_json={
                        "action": "create_customer_activity",
                        "workflow": _test_workflow("act_first", action_type="create_customer_activity"),
                    },
                ),
                SimpleNamespace(
                    id=502,
                    state_json={
                        "action": "transition_follow_up_task",
                        "workflow": _test_workflow(
                            "act_second",
                            action_type="transition_follow_up_task",
                            dependency_json={"depends_on": ["act_first"]},
                        ),
                    },
                ),
            ],
        ),
    )

    assert started == [501]
    assert result["executed_action_count"] == 1
    assert result["current_interrupt"]["task_projection_id"] == 900
    assert result["active_task_snapshot"]["id"] == 900
    assert result["ownership_rejection_event"] is None


@pytest.mark.asyncio
async def test_root_runtime_does_not_unlock_downstream_when_ready_branch_is_incomplete(monkeypatch):
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
    )
    started: list[int] = []

    async def fake_in_context(context, task, *, include_graph_progress_events):
        started.append(task.id)
        return {
            "result": {"assistant_content": "暂未完成。"},
            "tool_result": {"event": "tool_result", "success": False, "task_id": task.id},
            "events": [{"event": "agent_step", "status": "completed"}],
            "emitted_event_count": 1,
            "assistant_content": "暂未完成。",
        }

    monkeypatch.setattr(runtime, "_run_new_flow_auto_execute_task_in_context", fake_in_context)
    side_effects = AgentRootRuntimeSideEffects()
    result = await runtime._run_new_flow_auto_execute_tasks(
        AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            turn_input=AgentTurnInput(content="上游没有完成", source="web"),
            content="上游没有完成",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
        SimpleNamespace(
            auto_execute_tasks=[
                SimpleNamespace(
                    id=501,
                    state_json={
                        "action": "create_customer_activity",
                        "workflow": _test_workflow("act_first", action_type="create_customer_activity"),
                    },
                ),
                SimpleNamespace(
                    id=502,
                    state_json={
                        "action": "transition_follow_up_task",
                        "workflow": _test_workflow(
                            "act_second",
                            action_type="transition_follow_up_task",
                            dependency_json={"depends_on": ["act_first"]},
                        ),
                    },
                ),
            ],
        ),
    )

    assert started == [501]
    assert result["executed_action_count"] == 0
    assert [
        event["ready_count"]
        for event in side_effects.new_flow_events
        if event["event"] == "agent_root_auto_execute_plan_built"
    ] == [1]


@pytest.mark.asyncio
async def test_root_runtime_marks_downstream_blocked_after_ready_action_fails(monkeypatch):
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
    )
    blocked_actions: list[dict] = []

    class FakeSession:
        def query(self, *args, **kwargs):
            return None

    def fake_ledger_state(db, *, action_ids, team_id, user_id, include_system_actions=True):
        return {
            "satisfied_action_ids": [],
            "running_action_ids": [],
            "terminal_action_ids": [],
        }

    def fake_mark_running(db, **kwargs):
        return None

    def fake_mark_blocked(db, **kwargs):
        blocked_actions.append(
            {
                "action_id": kwargs["workflow"]["action_id"],
                "reason": kwargs["reason"],
            }
        )

    async def fake_in_context(context, task, *, include_graph_progress_events):
        return {
            "result": {"execution_status": "failed", "assistant_content": "执行失败：tool failed"},
            "tool_result": {"event": "tool_result", "success": False, "error": "tool failed", "task_id": task.id},
            "events": [{"event": "task_failed", "task_id": task.id, "reason": "tool failed"}],
            "emitted_event_count": 1,
            "assistant_content": "执行失败：tool failed",
        }

    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "execution_state_for_action_ids", fake_ledger_state)
    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "mark_action_running", fake_mark_running)
    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "mark_action_blocked", fake_mark_blocked)
    monkeypatch.setattr(runtime, "_run_new_flow_auto_execute_task_in_context", fake_in_context)
    side_effects = AgentRootRuntimeSideEffects()

    result = await runtime._run_new_flow_auto_execute_tasks(
        AgentRuntimeContext(
            db=FakeSession(),
            session=SimpleNamespace(id=4, context_json={}),
            turn_input=AgentTurnInput(content="上游执行失败", source="web"),
            content="上游执行失败",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
        SimpleNamespace(
            auto_execute_tasks=[
                SimpleNamespace(
                    id=501,
                    state_json={
                        "action": "create_customer_activity",
                        "workflow": _test_workflow("act_first", action_type="create_customer_activity"),
                    },
                ),
                SimpleNamespace(
                    id=502,
                    state_json={
                        "action": "transition_follow_up_task",
                        "workflow": _test_workflow(
                            "act_second",
                            action_type="transition_follow_up_task",
                            dependency_json={"depends_on": ["act_first"]},
                        ),
                    },
                ),
            ],
        ),
    )

    assert result["executed_action_count"] == 0
    assert blocked_actions == [
        {"action_id": "act_second", "reason": "waiting_dependencies:act_first"},
        {"action_id": "act_second", "reason": "terminal_dependencies:act_first"},
    ]
    plan_events = [
        event for event in side_effects.new_flow_events if event["event"] == "agent_root_auto_execute_plan_built"
    ]
    assert [event["ready_count"] for event in plan_events] == [1, 0]
    assert [event["terminal_action_count"] for event in plan_events] == [0, 1]
    blocked_event = next(
        event for event in side_effects.new_flow_events if event["event"] == "agent_root_auto_execute_plan_blocked"
    )
    assert blocked_event["blocked_actions"] == [
        {
            "action_id": "act_second",
            "action_type": "transition_follow_up_task",
            "task_id": 502,
            "reason": "terminal_dependencies:act_first",
        }
    ]


@pytest.mark.asyncio
async def test_root_runtime_uses_ledger_satisfied_actions_to_skip_rerun_and_unlock_downstream(monkeypatch):
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
    )
    started: list[int] = []
    ledger_calls = []

    def fake_ledger_state(db, *, action_ids, team_id, user_id, include_system_actions=True):
        ledger_calls.append(
            {
                "action_ids": action_ids,
                "team_id": team_id,
                "user_id": user_id,
                "include_system_actions": include_system_actions,
            }
        )
        return {
            "satisfied_action_ids": ["act_first"],
            "terminal_action_ids": [],
        }

    async def fake_in_context(context, task, *, include_graph_progress_events):
        started.append(task.id)
        return {
            "result": {"assistant_content": f"任务 {task.id} 已执行。"},
            "tool_result": {"event": "tool_result", "success": True, "task_id": task.id},
            "events": [{"event": "task_completed", "task_id": task.id}],
            "emitted_event_count": 1,
            "assistant_content": f"任务 {task.id} 已执行。",
        }

    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "execution_state_for_action_ids", fake_ledger_state)
    monkeypatch.setattr(runtime, "_run_new_flow_auto_execute_task_in_context", fake_in_context)
    side_effects = AgentRootRuntimeSideEffects()
    result = await runtime._run_new_flow_auto_execute_tasks(
        AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            turn_input=AgentTurnInput(content="ledger 防重跑", source="web"),
            content="ledger 防重跑",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
        SimpleNamespace(
            auto_execute_tasks=[
                SimpleNamespace(
                    id=501,
                    state_json={
                        "action": "create_customer_activity",
                        "workflow": _test_workflow("act_first", action_type="create_customer_activity"),
                    },
                ),
                SimpleNamespace(
                    id=502,
                    state_json={
                        "action": "transition_follow_up_task",
                        "workflow": _test_workflow(
                            "act_second",
                            action_type="transition_follow_up_task",
                            dependency_json={"depends_on": ["act_first"]},
                        ),
                    },
                ),
            ],
        ),
    )

    assert ledger_calls == [
        {
            "action_ids": ["act_first", "act_second"],
            "team_id": 2,
            "user_id": 3,
            "include_system_actions": True,
        }
    ]
    assert started == [502]
    assert result["executed_action_count"] == 1
    plan_events = [
        event for event in side_effects.new_flow_events if event["event"] == "agent_root_auto_execute_plan_built"
    ]
    assert plan_events[0]["terminal_count"] == 1
    assert plan_events[0]["satisfied_action_count"] == 1


@pytest.mark.asyncio
async def test_root_runtime_does_not_rerun_running_action_or_unlock_downstream(monkeypatch):
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
    )
    started: list[int] = []

    def fake_ledger_state(db, *, action_ids, team_id, user_id, include_system_actions=True):
        return {
            "satisfied_action_ids": [],
            "running_action_ids": ["act_first"],
            "terminal_action_ids": [],
        }

    async def fake_in_context(context, task, *, include_graph_progress_events):
        started.append(task.id)
        return {
            "result": {"assistant_content": f"任务 {task.id} 已执行。"},
            "tool_result": {"event": "tool_result", "success": True, "task_id": task.id},
            "events": [{"event": "task_completed", "task_id": task.id}],
            "emitted_event_count": 1,
            "assistant_content": f"任务 {task.id} 已执行。",
        }

    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "execution_state_for_action_ids", fake_ledger_state)
    monkeypatch.setattr(runtime, "_run_new_flow_auto_execute_task_in_context", fake_in_context)
    side_effects = AgentRootRuntimeSideEffects()
    result = await runtime._run_new_flow_auto_execute_tasks(
        AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            turn_input=AgentTurnInput(content="ledger RUNNING 防重入", source="web"),
            content="ledger RUNNING 防重入",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
        SimpleNamespace(
            auto_execute_tasks=[
                SimpleNamespace(
                    id=501,
                    state_json={
                        "action": "create_customer_activity",
                        "workflow": _test_workflow("act_first", action_type="create_customer_activity"),
                    },
                ),
                SimpleNamespace(
                    id=502,
                    state_json={
                        "action": "transition_follow_up_task",
                        "workflow": _test_workflow(
                            "act_second",
                            action_type="transition_follow_up_task",
                            dependency_json={"depends_on": ["act_first"]},
                        ),
                    },
                ),
            ],
        ),
    )

    assert started == []
    assert result["executed_action_count"] == 0
    plan_events = [
        event for event in side_effects.new_flow_events if event["event"] == "agent_root_auto_execute_plan_built"
    ]
    assert plan_events[0]["active_count"] == 1
    assert plan_events[0]["blocked_count"] == 1
    assert plan_events[0]["ready_count"] == 0


@pytest.mark.asyncio
async def test_root_runtime_checkpoints_new_flow_result_and_interrupt_snapshot(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.session_state._remember_current_customer",
        lambda db_arg, session_arg, customer: None,
    )

    def create_waiting_task(db_arg, event, team_id, user_id, session_arg):
        event["task_id"] = 501
        event["task_key"] = "task-501"
        snapshot = _waiting_task_snapshot(501, action=event["action"], target_id=101)
        snapshot["team_id"] = team_id
        snapshot["user_id"] = user_id
        snapshot["session_id"] = session_arg.id
        snapshot["state_json"] = {
            "action": event["action"],
            "payload": event["payload"],
        }
        return SimpleNamespace(**snapshot)

    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.task_factory._create_waiting_task_from_event",
        create_waiting_task,
    )
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeSideEffectNewFlowGraphService(),
    )

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "今天和越秀金融沟通",
            "turn_kind": "text",
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            content="今天和越秀金融沟通",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=AgentRootRuntimeSideEffects(),
        ),
    )

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
    assert checkpoint_state["pending_task_snapshot"]["id"] == 501
    assert checkpoint_state["task_projection"]["id"] == 501
    assert checkpoint_state["pending_task_requested"] is True


@pytest.mark.asyncio
async def test_root_runtime_exposes_checkpoint_history_for_replayable_audit():
    runtime = AgentRootRuntime(checkpointer=InMemorySaver())

    first_state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "确认",
            "turn_kind": "confirm",
            "current_interrupt": {"type": "confirm", "business_action": "CREATE_FOLLOW_UP"},
        }
    )
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

    await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "确认",
            "turn_kind": "confirm",
            "current_interrupt": {"type": "confirm", "business_action": "CREATE_FOLLOW_UP"},
        }
    )
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
    interrupted_checkpoint = next(item for item in history if isinstance(item["values"].get("current_interrupt"), dict))

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
        waiting_events.append(event)
        return _persisted_waiting_task_from_event(
            event,
            team_id=team_id,
            user_id=user_id,
            session_id=session_arg.id,
        )

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

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "今天和越秀金融沟通",
            "turn_kind": "text",
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            content="今天和越秀金融沟通",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
    )

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
        waiting_events.append(event)
        return _persisted_waiting_task_from_event(
            event,
            team_id=team_id,
            user_id=user_id,
            session_id=session_arg.id,
        )

    task = _persisted_waiting_task_from_event(
        {
            "action": "create_customer_activity",
            "payload": {"customer_id": 101, "content": "已沟通项目进展"},
            "content": "请确认是否创建这条跟进记录？",
        },
        team_id=2,
        user_id=3,
        session_id=4,
    )
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
    first_state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "今天和越秀金融沟通",
            "turn_kind": "text",
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            content="今天和越秀金融沟通",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=first_side_effects,
        ),
    )

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
    assert "task" not in pending_graph_service.calls[0]
    assert pending_graph_service.calls[0]["task_snapshot"] == agent_task_snapshot(task)
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
        waiting_events.append(event)
        return _persisted_waiting_task_from_event(
            event,
            team_id=team_id,
            user_id=user_id,
            session_id=session_arg.id,
        )

    task = _persisted_waiting_task_from_event(
        {
            "action": "create_customer_activity",
            "payload": {"customer_id": 101, "content": "已沟通项目进展"},
            "content": "请确认是否创建这条跟进记录？",
        },
        team_id=2,
        user_id=3,
        session_id=4,
    )
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
    first_state = await first_runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "今天和越秀金融沟通",
            "turn_kind": "text",
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            content="今天和越秀金融沟通",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=AgentRootRuntimeSideEffects(),
        ),
    )

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

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "确认",
            "turn_kind": "confirm",
            "current_interrupt": {"type": "confirm", "business_action": "CREATE_FOLLOW_UP"},
        }
    )

    assert state["route"] == "interrupt"
    assert "__interrupt__" in state
    assert state["__interrupt__"][0].value == {"type": "confirm", "business_action": "CREATE_FOLLOW_UP"}
    assert await runtime.has_pending_interrupt(team_id=2, user_id=3, session_id=4, session_key="abc") is True


@pytest.mark.asyncio
async def test_root_runtime_resumes_langgraph_interrupt_with_command():
    runtime = AgentRootRuntime(checkpointer=InMemorySaver())
    await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "确认",
            "turn_kind": "confirm",
            "current_interrupt": {"type": "confirm", "business_action": "CREATE_FOLLOW_UP"},
        }
    )

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
        "agent_root_interrupt_resume_validated",
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
    await runtime.checkpoint_turn_start(
        {
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
        }
    )

    with pytest.raises(ValueError, match="not allowed"):
        await runtime.resume_interrupt(
            resume_payload={"action": "submit", "content": "确认", "source": "web", "metadata": {}},
            team_id=2,
            user_id=3,
            session_id=4,
            session_key="abc",
        )


@pytest.mark.asyncio
async def test_root_runtime_terminalizes_legacy_pending_continuation_before_exposure():
    runtime = AgentRootRuntime(checkpointer=InMemorySaver())
    waiting_state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "确认",
            "turn_kind": "confirm",
            "current_interrupt": {
                "schema_version": "agent.interrupt.v1",
                "type": "confirm",
                "reason": "write_confirmation",
                "business_action": "create_opportunity",
                "allowed_resume_actions": ["approve", "edit", "reject", "cancel"],
                "checkpoint_ref": {
                    "runtime": "crm_agent_pending_task",
                    "thread_id": "crm_agent_pending:2:3:4:101",
                    "checkpoint_ns": "pending_task_subgraph:checkpoint-1",
                    "team_id": 2,
                    "user_id": 3,
                    "session_id": 4,
                    "task_id": 101,
                },
            },
        }
    )
    assert waiting_state["runtime_status"] == "checkpoint_recovery_failed"
    assert waiting_state["pending_task_result"]["failure_reason"] == "invalid_continuation"
    assert waiting_state["current_interrupt"] is None
    history = await runtime.state_history(
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        limit=20,
    )
    assert any("pending_resume_recovery_failure" in item["next_nodes"] for item in history)
    assert any("finish_turn" in item["next_nodes"] for item in history)


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

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "确认",
            "turn_kind": "confirm",
        },
        context=AgentRuntimeContext(side_effects=side_effects),
    )

    assert state["application_action"] == "no_pending_confirmation"
    expected_content = agent_copy.no_pending_confirmation()
    assert side_effects.no_pending_confirmation_events == [{"event": "final", "content": expected_content}]
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

    assert "task" not in pending_graph_service.calls[0]
    assert pending_graph_service.calls[0]["task_snapshot"] == agent_task_snapshot(task)
    assert pending_effects.calls[0]["graph_state"]["task_projection"]["id"] == 101
    assert pending_effects.calls[0]["context"].graph_side_effects.task is task
    assert side_effects.pending_task_result is not None
    assert side_effects.pending_task_result["task_projection"]["id"] == 101
    assert without_projection_metadata(side_effects.pending_task_events) == [
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
        "agent_root_pending_task_outcome_projected",
        "agent_root_application_action_decided",
        "agent_root_graph_checkpointed",
    ]
    assert state["application_action"] == "pending_handled"


@pytest.mark.asyncio
async def test_root_pending_node_uses_checkpoint_task_snapshot_without_loading_orm(monkeypatch):
    task = waiting_task_stub()
    task_snapshot = agent_task_snapshot(task)
    pending_graph_service = FakePendingGraphService()
    projector = SequencedPendingInterruptProjector([
        PendingInterruptProjectionResult(
            status="PROJECTED",
            projection_key="",
            task=None,
            events=[],
            assistant_content="请确认是否创建商机？",
            delivery_status="INLINE_VISIBLE",
        )
    ])

    def reject_graph_node_hydration(*args, **kwargs):
        raise AssertionError("root pending graph node must not load ORM task state")

    monkeypatch.setattr(root_runtime_module.agent_task_crud, "get_by_id", reject_graph_node_hydration)
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        pending_graph_service=pending_graph_service,
        pending_interrupt_projector=projector,
    )

    await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "snapshot-only",
            "channel": "web",
            "content": "补充金额 10 万",
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": task.id, "task_key": task.task_key},
            "pending_task_snapshot": task_snapshot,
        },
        context=AgentRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=4, context_json={}),
            task=None,
            turn_input=AgentTurnInput.text("补充金额 10 万"),
            content="补充金额 10 万",
            team_id=2,
            user_id=3,
            session_id=4,
            authorization="Bearer test",
            side_effects=AgentRootRuntimeSideEffects(),
        ),
    )

    assert len(pending_graph_service.calls) == 1
    assert "task" not in pending_graph_service.calls[0]
    assert pending_graph_service.calls[0]["task_snapshot"] == task_snapshot
    assert projector.calls[0].task is None
    assert projector.calls[0].continuation["task_id"] == task.id


@pytest.mark.asyncio
async def test_root_runtime_holds_terminal_pending_outcome_behind_durable_projection_barrier():
    class TerminalPendingGraphService(FakePendingGraphService):
        async def run_with_trace(self, state, *, side_effects=None):
            if side_effects is not None:
                side_effects.checkpoint_ref = new_pending_task_continuation(
                    team_id=state["team_id"],
                    user_id=state["user_id"],
                    session_id=state["session_id"],
                    task_id=state["task_snapshot"]["id"],
                    root_thread_id=f"crm_agent:{state['team_id']}:{state['user_id']}:{state['session_id']}:{state['session_id']}",
                    checkpoint_ns="pending_task_subgraph:terminal-outcome-1",
                )
            return await super().run_with_trace(state, side_effects=side_effects)

    pending_graph_service = TerminalPendingGraphService()
    pending_effects = FakePendingTaskSideEffectHandler()
    projector = SequencedPendingInterruptProjector([
        PendingInterruptProjectionResult(
            status="IN_PROGRESS",
            projection_key="",
            busy=True,
            retryable=True,
            failure_reason="projection_in_progress",
        ),
        PendingInterruptProjectionResult(
            status="PROJECTED",
            projection_key="",
            assistant_content="请确认是否创建商机？",
            delivery_status="INLINE_VISIBLE",
        ),
    ])
    new_flow_graph_service = FakeNewFlowGraphService()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        pending_graph_service=pending_graph_service,
        pending_task_side_effect_handler=pending_effects,
        pending_interrupt_projector=projector,
        new_flow_graph_service=new_flow_graph_service,
    )
    task = waiting_task_stub()
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充金额 10 万"),
        content="补充金额 10 万",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )

    first = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )

    assert first["runtime_status"] == "pending_projection_in_progress"
    assert first["runtime_retryable"] is True
    assert first.get("current_interrupt") is None
    assert pending_effects.calls == []
    assert len(projector.calls) == 1
    assert new_flow_graph_service.calls == []

    context.turn_input = AgentTurnInput.text("这条新输入不能被消费")
    context.content = "这条新输入不能被消费"
    second = await runtime.run_turn(
        turn_input=context.turn_input,
        content=context.content,
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        current_customer={},
        context=context,
    )

    assert len(projector.calls) == 2
    assert second["runtime_status"] == "pending_projection_projected"
    assert second["application_action"] == "pending_handled"
    assert pending_effects.calls == []
    assert new_flow_graph_service.calls == []


@pytest.mark.asyncio
async def test_root_runtime_routes_terminal_outcome_projection_failure_through_failure_node():
    class TerminalPendingGraphService(FakePendingGraphService):
        async def run_with_trace(self, state, *, side_effects=None):
            if side_effects is not None:
                side_effects.checkpoint_ref = new_pending_task_continuation(
                    team_id=state["team_id"],
                    user_id=state["user_id"],
                    session_id=state["session_id"],
                    task_id=state["task_snapshot"]["id"],
                    root_thread_id=(
                        f"crm_agent:{state['team_id']}:{state['user_id']}:"
                        f"{state['session_id']}:{state['session_id']}"
                    ),
                    checkpoint_ns="pending_task_subgraph:terminal-outcome-failure",
                )
            return await super().run_with_trace(state, side_effects=side_effects)

    projector = FakePendingInterruptProjector(
        PendingInterruptProjectionResult(
            status="FAILED",
            projection_key="",
            retryable=False,
            failure_reason="projection_write_failed",
        )
    )
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        pending_graph_service=TerminalPendingGraphService(),
        pending_task_side_effect_handler=FakePendingTaskSideEffectHandler(),
        pending_interrupt_projector=projector,
    )
    task = waiting_task_stub()
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充金额 10 万"),
        content="补充金额 10 万",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )

    assert state["runtime_status"] == "pending_projection_failed"
    assert state["runtime_retryable"] is False
    assert state["application_action"] == "finish"
    assert state["current_interrupt"] is None
    assert state["pending_task_continuation_ref"] is None
    assert state["pending_task_requested"] is False
    assert state["pending_task_result"]["failure_reason"] == "projection_write_failed"
    assert "projection_aborted" not in state["pending_task_result"]
    history = await runtime.state_history(
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        limit=30,
    )
    assert any("pending_projection_failure" in item["next_nodes"] for item in history)
    assert any("finish_turn" in item["next_nodes"] for item in history)


@pytest.mark.asyncio
async def test_root_runtime_projects_authoritative_pending_outcome_when_child_graph_interrupts():
    checkpointer = InMemorySaver()
    pending_graph_service = PendingTaskGraphService(
        preflight_graph_service=FakeNativeInterruptPreflightGraphService(),
        interaction_graph_service=FakeNativeInterruptInteractionGraphService(),
        checkpointer=checkpointer,
    )
    pending_effects = FakePendingTaskSideEffectHandler()
    runtime = AgentRootRuntime(
        checkpointer=checkpointer,
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

    assert state["application_action"] == "pending_handled"
    assert state["pending_task_result"]["handled"] is True
    assert state["pending_task_result"]["task"]["id"] == 101
    assert state["assistant_content"] == "商机信息齐了。要创建商机吗？"
    assert state["current_interrupt"]["source_event"] == "confirmation_required"
    checkpoint_ref = state["current_interrupt"]["checkpoint_ref"]
    assert checkpoint_ref["runtime"] == "crm_agent_pending_task"
    assert checkpoint_ref["continuation_id"]
    assert checkpoint_ref["persistence_scope"] == "root"
    assert checkpoint_ref["thread_id"] == "crm_agent:2:3:4:abc"
    assert checkpoint_ref["checkpoint_ns"].startswith("pending_task_subgraph:")
    assert checkpoint_ref["team_id"] == 2
    assert checkpoint_ref["user_id"] == 3
    assert checkpoint_ref["session_id"] == 4
    assert checkpoint_ref["task_id"] == 101
    assert side_effects.pending_task_result is not None
    assert side_effects.pending_task_result["task_projection"]["id"] == 101
    assert side_effects.pending_task_assistant_content == "商机信息齐了。要创建商机吗？"
    event_names = [event["event"] for event in side_effects.pending_task_events]
    assert event_names[0] == "agent_step"
    assert "pending_interruption_assessed" in event_names
    assert "confirmation_required" in event_names
    assert "final" in event_names
    assert event_names.index("pending_interruption_assessed") < event_names.index("confirmation_required")
    assert event_names.index("confirmation_required") < event_names.index("final")
    checkpoint_state = await runtime.current_checkpoint_state(
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
    )
    assert checkpoint_state["runtime_status"] == "pending_projection_projected"
    assert checkpoint_state["current_interrupt"] == state["current_interrupt"]
    assert checkpoint_state["pending_interrupt_projection"]["status"] == "PROJECTED"
    assert checkpoint_state["pending_interrupt_projection"]["delivery_status"] == "INLINE_VISIBLE"


@pytest.mark.asyncio
async def test_root_runtime_resumes_root_owned_pending_wait_through_exact_child_continuation():
    checkpointer = InMemorySaver()
    pending_graph_service = PendingTaskGraphService(
        preflight_graph_service=FakeNativeInterruptPreflightGraphService(),
        interaction_graph_service=FakeNativeInterruptInteractionGraphService(),
        checkpointer=checkpointer,
    )
    runtime = AgentRootRuntime(
        checkpointer=checkpointer,
        pending_graph_service=pending_graph_service,
        pending_task_side_effect_handler=FakePendingTaskSideEffectHandler(),
    )
    task = waiting_task_stub()
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充金额 10 万"),
        content="补充金额 10 万",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )

    waiting_state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )
    current_interrupt = waiting_state["current_interrupt"]
    continuation = current_interrupt["checkpoint_ref"]

    resumed_state = await runtime.resume_interrupt(
        resume_payload={
            "action": "approve",
            "content": "确认",
            "source": "web",
            "metadata": {},
            "business_action": current_interrupt["business_action"],
            "interrupt_reason": current_interrupt["reason"],
        },
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        current_interrupt=current_interrupt,
        context=context,
    )

    assert resumed_state["application_action"] == "execute_confirmed_task"
    assert resumed_state["current_interrupt"] is None
    assert resumed_state["pending_task_continuation_ref"] is None
    assert resumed_state["pending_task_result"]["confirmation_decision"]["intent"] == "confirm"
    recovery = await pending_graph_service.load_checkpointed_outcome(continuation)
    assert recovery.failure_reason is None
    assert recovery.outcome is not None
    assert recovery.outcome.get("current_interrupt") is None
    assert recovery.outcome["confirmation_decision"]["intent"] == "confirm"

    history = await runtime.state_history(
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        limit=30,
    )
    assert any("generated_interrupt_wait" in item["next_nodes"] for item in history)
    assert any("validate_interrupt_resume" in item["next_nodes"] for item in history)
    assert any("pending_task_subgraph" in item["next_nodes"] for item in history)


@pytest.mark.asyncio
async def test_root_runtime_terminates_when_native_child_checkpoint_disappears_before_resume():
    checkpointer = InMemorySaver()
    pending_graph_service = PendingTaskGraphService(
        preflight_graph_service=FakeNativeInterruptPreflightGraphService(),
        interaction_graph_service=FakeNativeInterruptInteractionGraphService(),
        checkpointer=checkpointer,
    )
    new_flow_graph_service = FakeNewFlowGraphService()
    runtime = AgentRootRuntime(
        checkpointer=checkpointer,
        pending_graph_service=pending_graph_service,
        pending_task_side_effect_handler=FakePendingTaskSideEffectHandler(),
        new_flow_graph_service=new_flow_graph_service,
    )
    task = waiting_task_stub()
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充金额 10 万"),
        content="补充金额 10 万",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )
    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )
    current_interrupt = state["current_interrupt"]
    checkpoint_ref = current_interrupt["checkpoint_ref"]
    thread_id = checkpoint_ref["thread_id"]
    checkpoint_ns = checkpoint_ref["checkpoint_ns"]

    del checkpointer.storage[thread_id][checkpoint_ns]
    for key in list(checkpointer.writes):
        if key[0] == thread_id and key[1] == checkpoint_ns:
            del checkpointer.writes[key]
    for key in list(checkpointer.blobs):
        if key[0] == thread_id and key[1] == checkpoint_ns:
            del checkpointer.blobs[key]

    result = await runtime.resume_interrupt(
        resume_payload={
            "action": "approve",
            "content": "确认",
            "source": "web",
            "metadata": {},
            "business_action": current_interrupt["business_action"],
            "interrupt_reason": current_interrupt["reason"],
        },
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        current_interrupt=current_interrupt,
        context=context,
    )

    assert result["runtime_status"] == "checkpoint_recovery_failed"
    assert result["runtime_retryable"] is False
    assert result["application_action"] == "finish"
    assert result["current_interrupt"] is None
    assert result["pending_task_continuation_ref"] is None
    assert result["pending_task_requested"] is False
    assert result["pending_task_result"]["failure_reason"] == "checkpoint_locator_not_found"
    assert any(
        event.get("event") == "pending_task_checkpoint_recovery_failed"
        for event in result["events"]
    )
    history = await runtime.state_history(
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        limit=30,
    )
    assert any("validate_interrupt_resume" in item["next_nodes"] for item in history)
    assert any("pending_resume_recovery_failure" in item["next_nodes"] for item in history)
    assert any("finish_turn" in item["next_nodes"] for item in history)

    context.task = None
    context.turn_input = AgentTurnInput.text("重新记录一个客户跟进")
    context.content = "重新记录一个客户跟进"
    next_state = await runtime.run_turn(
        turn_input=context.turn_input,
        content=context.content,
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        current_customer={},
        context=context,
    )
    assert next_state["runtime_status"] != "checkpoint_recovery_failed"
    assert len(new_flow_graph_service.calls) == 1


@pytest.mark.asyncio
async def test_root_runtime_keeps_root_wait_retryable_when_checkpoint_store_is_temporarily_unavailable():
    checkpointer = InMemorySaver()
    delegate = PendingTaskGraphService(
        preflight_graph_service=FakeNativeInterruptPreflightGraphService(),
        interaction_graph_service=FakeNativeInterruptInteractionGraphService(),
        checkpointer=checkpointer,
    )

    class TemporarilyUnavailablePendingGraphService:
        def __init__(self):
            self.fail_load = False
            self.run_calls = 0

        async def run_with_trace(self, state, *, side_effects=None):
            self.run_calls += 1
            return await delegate.run_with_trace(state, side_effects=side_effects)

        async def load_checkpointed_outcome(self, *args, **kwargs):
            if self.fail_load:
                return PendingTaskOutcomeRecovery(
                    failure_reason="checkpoint_store_unavailable"
                )
            return await delegate.load_checkpointed_outcome(*args, **kwargs)

    class ForbiddenSecondConfirmationRouter:
        async def route_resume(self, db, **kwargs):
            raise AssertionError("validated deferred resume must bypass turn intent routing")

    pending_graph_service = TemporarilyUnavailablePendingGraphService()
    runtime = AgentRootRuntime(
        checkpointer=checkpointer,
        pending_graph_service=pending_graph_service,
        pending_task_side_effect_handler=FakePendingTaskSideEffectHandler(),
        turn_intent_router=ForbiddenSecondConfirmationRouter(),
    )
    task = waiting_task_stub()
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充金额 10 万"),
        content="补充金额 10 万",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )
    waiting_state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )
    current_interrupt = waiting_state["current_interrupt"]
    continuation = current_interrupt["checkpoint_ref"]
    pending_graph_service.fail_load = True

    result = await runtime.resume_interrupt(
        resume_payload={
            "action": "approve",
            "content": "确认",
            "source": "web",
            "metadata": {},
            "business_action": current_interrupt["business_action"],
            "interrupt_reason": current_interrupt["reason"],
        },
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        current_interrupt=current_interrupt,
        context=context,
    )

    assert pending_graph_service.run_calls == 1
    assert result["runtime_status"] == "checkpoint_recovery_failed"
    assert result["runtime_retryable"] is True
    assert result["application_action"] == "finish"
    assert result["current_interrupt"]["checkpoint_ref"] == current_interrupt["checkpoint_ref"]
    assert result["current_interrupt"]["interaction"] == current_interrupt["interaction"]
    assert result["current_interrupt"]["business_action"] == current_interrupt["business_action"]
    assert result["pending_task_continuation_ref"] == continuation
    assert result["pending_interrupt_projection"] == {}
    assert result["pending_task_result"]["failure_reason"] == "checkpoint_store_unavailable"
    assert result["pending_task_deferred_resume"]["continuation"] == continuation
    assert result["pending_task_deferred_resume"]["interrupt"] == interrupt_payload_from_json(
        current_interrupt
    )
    assert result["pending_task_deferred_resume"]["resume_payload"]["action"] == "approve"
    assert result["pending_task_deferred_resume"]["resume_payload"]["content"] == "确认"
    assert result["assistant_content"] == "当前待确认流程暂时无法恢复，请稍后重试。"
    recovery_events = [
        event
        for event in context.side_effects.pending_task_events
        if event.get("event") == "pending_task_checkpoint_recovery_failed"
    ]
    assert recovery_events == [{
        "event": "pending_task_checkpoint_recovery_failed",
        "reason": "checkpoint_store_unavailable",
        "retryable": True,
    }]

    pending_graph_service.fail_load = False
    context.turn_input = AgentTurnInput.text("检查恢复状态")
    context.content = "检查恢复状态"
    recovered = await runtime.run_turn(
        turn_input=context.turn_input,
        content=context.content,
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        current_customer={},
        context=context,
    )

    assert pending_graph_service.run_calls == 2
    assert recovered["runtime_status"] != "checkpoint_recovery_failed"
    assert recovered["current_interrupt"] is None
    assert recovered["pending_task_continuation_ref"] is None
    assert recovered["pending_task_deferred_resume"] is None
    assert [
        event
        for event in context.side_effects.pending_task_events
        if event.get("event") == "pending_task_checkpoint_recovery_failed"
    ] == recovery_events


@pytest.mark.asyncio
async def test_root_runtime_fails_closed_when_deferred_resume_invariant_cannot_be_built(monkeypatch):
    checkpointer = InMemorySaver()
    delegate = PendingTaskGraphService(
        preflight_graph_service=FakeNativeInterruptPreflightGraphService(),
        interaction_graph_service=FakeNativeInterruptInteractionGraphService(),
        checkpointer=checkpointer,
    )

    class TemporarilyUnavailablePendingGraphService:
        def __init__(self):
            self.fail_load = False

        async def run_with_trace(self, state, *, side_effects=None):
            return await delegate.run_with_trace(state, side_effects=side_effects)

        async def load_checkpointed_outcome(self, *args, **kwargs):
            if self.fail_load:
                return PendingTaskOutcomeRecovery(
                    failure_reason="checkpoint_store_unavailable"
                )
            return await delegate.load_checkpointed_outcome(*args, **kwargs)

    def reject_invalid_capability(**kwargs):
        raise ValueError("deferred resume invariant failed")

    monkeypatch.setattr(
        root_runtime_module,
        "build_pending_task_deferred_resume",
        reject_invalid_capability,
    )
    pending_graph_service = TemporarilyUnavailablePendingGraphService()
    runtime = AgentRootRuntime(
        checkpointer=checkpointer,
        pending_graph_service=pending_graph_service,
        pending_task_side_effect_handler=FakePendingTaskSideEffectHandler(),
    )
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=waiting_task_stub(),
        turn_input=AgentTurnInput.text("补充金额 10 万"),
        content="补充金额 10 万",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )
    waiting_state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "invalid-deferred-invariant",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )
    current_interrupt = waiting_state["current_interrupt"]
    pending_graph_service.fail_load = True

    result = await runtime.resume_interrupt(
        resume_payload={
            "action": "approve",
            "content": "确认",
            "source": "web",
            "metadata": {},
            "business_action": current_interrupt["business_action"],
            "interrupt_reason": current_interrupt["reason"],
        },
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="invalid-deferred-invariant",
        current_interrupt=current_interrupt,
        context=context,
    )

    assert result["runtime_status"] == "checkpoint_recovery_failed"
    assert result["runtime_retryable"] is False
    assert result["pending_task_result"]["failure_reason"] == "invalid_continuation"
    assert result["current_interrupt"] is None
    assert result["pending_task_continuation_ref"] is None
    assert result["pending_task_deferred_resume"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper_kind", ["continuation", "interrupt", "resume_payload"])
async def test_root_runtime_fails_closed_when_deferred_resume_capability_is_invalid(tamper_kind):
    checkpointer = InMemorySaver()
    delegate = PendingTaskGraphService(
        preflight_graph_service=FakeNativeInterruptPreflightGraphService(),
        interaction_graph_service=FakeNativeInterruptInteractionGraphService(),
        checkpointer=checkpointer,
    )

    class TemporarilyUnavailablePendingGraphService:
        def __init__(self):
            self.fail_load = False
            self.run_calls = 0

        async def run_with_trace(self, state, *, side_effects=None):
            self.run_calls += 1
            return await delegate.run_with_trace(state, side_effects=side_effects)

        async def load_checkpointed_outcome(self, *args, **kwargs):
            if self.fail_load:
                return PendingTaskOutcomeRecovery(
                    failure_reason="checkpoint_store_unavailable"
                )
            return await delegate.load_checkpointed_outcome(*args, **kwargs)

    class ForbiddenIntentRouter:
        async def route_resume(self, db, **kwargs):
            raise AssertionError("invalid deferred resume must fail closed before intent routing")

    pending_graph_service = TemporarilyUnavailablePendingGraphService()
    runtime = AgentRootRuntime(
        checkpointer=checkpointer,
        pending_graph_service=pending_graph_service,
        pending_task_side_effect_handler=FakePendingTaskSideEffectHandler(),
        turn_intent_router=ForbiddenIntentRouter(),
    )
    task = waiting_task_stub()
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充金额 10 万"),
        content="补充金额 10 万",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )
    waiting_state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "invalid-deferred-resume",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )
    current_interrupt = waiting_state["current_interrupt"]
    pending_graph_service.fail_load = True
    failed = await runtime.resume_interrupt(
        resume_payload={
            "action": "approve",
            "content": "确认",
            "source": "web",
            "metadata": {},
            "business_action": current_interrupt["business_action"],
            "interrupt_reason": current_interrupt["reason"],
        },
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="invalid-deferred-resume",
        current_interrupt=current_interrupt,
        context=context,
    )
    capability = deepcopy(failed["pending_task_deferred_resume"])
    if tamper_kind == "continuation":
        capability["continuation"]["checkpoint_ns"] = "pending_task_subgraph:tampered"
    elif tamper_kind == "interrupt":
        capability["interrupt"]["interaction"]["prompt"] = "篡改后的确认提示"
    else:
        capability["resume_payload"]["action"] = "submit_text"

    config = root_runtime_module.build_agent_graph_config(
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="invalid-deferred-resume",
    )
    await runtime._graph.aupdate_state(
        config,
        {"pending_task_deferred_resume": capability},
    )
    pending_graph_service.fail_load = False
    context.turn_input = AgentTurnInput.text("检查恢复状态")
    context.content = "检查恢复状态"

    recovered = await runtime.run_turn(
        turn_input=context.turn_input,
        content=context.content,
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="invalid-deferred-resume",
        current_customer={},
        context=context,
    )

    assert pending_graph_service.run_calls == 1
    assert recovered["runtime_status"] == "checkpoint_recovery_failed"
    assert recovered["runtime_retryable"] is False
    assert recovered["pending_task_result"]["failure_reason"] == "invalid_continuation"
    assert recovered["current_interrupt"] is None
    assert recovered["pending_task_continuation_ref"] is None
    assert recovered["pending_task_deferred_resume"] is None
    history = await runtime.state_history(
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="invalid-deferred-resume",
        limit=30,
    )
    assert any("pending_resume_recovery_failure" in item["next_nodes"] for item in history)
    assert any("finish_turn" in item["next_nodes"] for item in history)


@pytest.mark.asyncio
async def test_root_runtime_preserves_first_child_interrupt_when_authoritative_load_is_temporarily_unavailable():
    checkpointer = InMemorySaver()
    pending_graph_service = PendingTaskGraphService(
        preflight_graph_service=FakeNativeInterruptPreflightGraphService(),
        interaction_graph_service=FakeNativeInterruptInteractionGraphService(),
        checkpointer=checkpointer,
    )
    durable_store = pending_graph_service._checkpoint_store

    class FailFirstAuthoritativeLoadStore:
        enabled = True

        def __init__(self):
            self.calls = 0

        async def load_result(self, checkpoint_ref, *, expected_interrupt=None):
            self.calls += 1
            if self.calls == 1:
                return PendingTaskCheckpointLoadResult(
                    failure_reason="checkpoint_store_unavailable"
                )
            return await durable_store.load_result(
                checkpoint_ref,
                expected_interrupt=expected_interrupt,
            )

    class ConfirmPendingTurnIntentRouter:
        async def route_resume(self, db, **kwargs):
            current_interrupt = kwargs["current_interrupt"]
            return SimpleNamespace(
                decision=SimpleNamespace(
                    intent="CONTINUE_PENDING",
                    confidence=1.0,
                    target_task_id=current_interrupt.get("task_projection_id"),
                    normalized_action="approve",
                    reason="测试首次权威读取瞬态失败后的恢复。",
                ),
                resume_payload={
                    "action": "approve",
                    "content": kwargs["turn_input"].content,
                    "source": "web",
                    "metadata": {},
                    "business_action": current_interrupt["business_action"],
                    "interrupt_reason": current_interrupt["reason"],
                },
                source="test_router",
            )

    failing_store = FailFirstAuthoritativeLoadStore()
    pending_graph_service._checkpoint_store = failing_store
    runtime = AgentRootRuntime(
        checkpointer=checkpointer,
        pending_graph_service=pending_graph_service,
        pending_task_side_effect_handler=FakePendingTaskSideEffectHandler(),
        turn_intent_router=ConfirmPendingTurnIntentRouter(),
    )
    task = waiting_task_stub()
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充金额 10 万"),
        content="补充金额 10 万",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )

    first = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "first-authoritative-load-retry",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )

    continuation = context.side_effects.pending_task_graph_side_effects.checkpoint_ref
    assert first["runtime_status"] == "checkpoint_recovery_failed"
    assert first["runtime_retryable"] is True
    assert first["current_interrupt"]["reason"] == "write_confirmation"
    assert first["current_interrupt"]["checkpoint_ref"] == continuation
    assert first["pending_task_continuation_ref"] == continuation
    assert first.get("pending_task_deferred_resume") is None

    context.turn_input = AgentTurnInput.text("确认")
    context.content = "确认"
    recovered = await runtime.run_turn(
        turn_input=context.turn_input,
        content=context.content,
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="first-authoritative-load-retry",
        current_customer={},
        context=context,
    )

    assert failing_store.calls >= 2
    assert recovered["runtime_status"] != "checkpoint_recovery_failed"
    assert recovered["current_interrupt"] is None
    assert recovered["pending_task_continuation_ref"] is None
    assert len([
        event
        for event in context.side_effects.pending_task_events
        if event.get("event") == "pending_task_checkpoint_recovery_failed"
    ]) == 1


@pytest.mark.asyncio
async def test_root_runtime_exposes_retryable_projection_in_progress_without_exposing_child_interrupt():
    checkpointer = InMemorySaver()
    pending_graph_service = PendingTaskGraphService(
        preflight_graph_service=FakeNativeInterruptPreflightGraphService(),
        interaction_graph_service=FakeNativeInterruptInteractionGraphService(),
        checkpointer=checkpointer,
    )
    projector = FakePendingInterruptProjector(
        PendingInterruptProjectionResult(
            status="IN_PROGRESS",
            projection_key="",
            busy=True,
            retryable=True,
            failure_reason="projection_in_progress",
        )
    )
    published_events = []

    async def capture_event(event):
        published_events.append(event)

    runtime = AgentRootRuntime(
        checkpointer=checkpointer,
        pending_graph_service=pending_graph_service,
        pending_interrupt_projector=projector,
    )
    task = waiting_task_stub()
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充金额 10 万"),
        content="补充金额 10 万",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
        event_sink=capture_event,
    )

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )

    assert len(projector.calls) == 1
    assert projector.calls[0].root_thread_id == "crm_agent:2:3:4:abc"
    assert state["runtime_status"] == "pending_projection_in_progress"
    assert state["runtime_retryable"] is True
    busy_projection_key = projector.calls[0] and root_runtime_module.pending_interrupt_projection_key(
        projector.calls[0].continuation, projector.calls[0].interrupt
    )
    projection_state = state["pending_interrupt_projection"]
    assert {
        key: projection_state.get(key)
        for key in (
            "status",
            "projection_key",
            "replayed",
            "busy",
            "retryable",
            "failure_reason",
            "delivery_status",
        )
    } == {
        "status": "IN_PROGRESS",
        "projection_key": busy_projection_key,
        "replayed": False,
        "busy": True,
        "retryable": True,
        "failure_reason": "projection_in_progress",
        "delivery_status": None,
    }
    assert projection_state["continuation"] == projector.calls[0].continuation
    assert projection_state["interrupt"] == projector.calls[0].interrupt
    assert "abort_status" not in projection_state
    recovery = await pending_graph_service.load_checkpointed_outcome(
        projector.calls[0].continuation,
        expected_interrupt=projector.calls[0].interrupt,
    )
    assert recovery.failure_reason is None
    assert recovery.outcome is not None
    assert recovery.outcome.get("current_interrupt") is not None
    assert recovery.outcome.get("projection_aborted") is not True
    assert state["application_action"] == "finish"
    assert state["pending_task_handled"] is False
    assert state["current_interrupt"] is None
    assert "__interrupt__" not in state
    assert state["assistant_content"] == "当前待确认流程正在完成状态同步，请稍后刷新或重试。"
    assert published_events[-1] == {
        "event": "pending_task_interrupt_projection_in_progress",
        "reason": "projection_in_progress",
        "projection_key": busy_projection_key,
        "retryable": True,
    }
    checkpoint_state = await runtime.current_checkpoint_state(
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
    )
    assert checkpoint_state["runtime_status"] == "pending_projection_in_progress"
    assert checkpoint_state["runtime_retryable"] is True
    assert checkpoint_state["pending_interrupt_projection"]["status"] == "IN_PROGRESS"
    assert checkpoint_state.get("current_interrupt") is None
    assert await runtime.current_interrupt(
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
    ) is None


@pytest.mark.asyncio
async def test_run_turn_retries_hidden_child_projection_before_consuming_new_user_input():
    checkpointer = InMemorySaver()
    pending_graph_service = PendingTaskGraphService(
        preflight_graph_service=FakeNativeInterruptPreflightGraphService(),
        interaction_graph_service=FakeNativeInterruptInteractionGraphService(),
        checkpointer=checkpointer,
    )
    projector = SequencedPendingInterruptProjector([
        PendingInterruptProjectionResult(
            status="IN_PROGRESS",
            projection_key="",
            busy=True,
            retryable=True,
            failure_reason="projection_in_progress",
        ),
        PendingInterruptProjectionResult(
            status="PROJECTED",
            projection_key="",
            assistant_content="商机信息齐了。要创建商机吗？",
            delivery_status="INLINE_VISIBLE",
        ),
    ])
    new_flow_graph_service = FakeNewFlowGraphService()
    runtime = AgentRootRuntime(
        checkpointer=checkpointer,
        pending_graph_service=pending_graph_service,
        pending_interrupt_projector=projector,
        new_flow_graph_service=new_flow_graph_service,
    )
    task = waiting_task_stub()
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充金额 10 万"),
        content="补充金额 10 万",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )
    first = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )
    assert first["runtime_status"] == "pending_projection_in_progress"
    checkpoint_before_retry = await runtime.current_checkpoint_state(
        team_id=2, user_id=3, session_id=4, session_key="abc"
    )
    assert checkpoint_before_retry.get("current_interrupt") is None

    context.turn_input = AgentTurnInput.text("这是不应该被消费的新消息")
    context.content = "这是不应该被消费的新消息"
    second = await runtime.run_turn(
        turn_input=context.turn_input,
        content=context.content,
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        current_customer={},
        context=context,
    )

    assert len(projector.calls) == 2
    assert second["runtime_status"] == "pending_projection_projected"
    assert second["current_interrupt"]["reason"] == "write_confirmation"
    assert second["assistant_content"] == "商机信息齐了。要创建商机吗？"
    assert new_flow_graph_service.calls == []


@pytest.mark.asyncio
async def test_root_runtime_projection_failure_remains_authoritative_when_failure_event_sink_raises():
    checkpointer = InMemorySaver()
    pending_graph_service = PendingTaskGraphService(
        preflight_graph_service=FakeNativeInterruptPreflightGraphService(),
        interaction_graph_service=FakeNativeInterruptInteractionGraphService(),
        checkpointer=checkpointer,
    )
    projector = FakePendingInterruptProjector(
        PendingInterruptProjectionResult(
            status="FAILED",
            projection_key="pending_interrupt_projection:v1:failed",
            retryable=False,
            failure_reason="projection_continuation_mismatch",
        )
    )

    async def failing_event_sink(event):
        if event.get("event") == "pending_task_interrupt_projection_failed":
            raise RuntimeError(f"transport unavailable: {event['event']}")

    new_flow_graph_service = FakeNewFlowGraphService()
    runtime = AgentRootRuntime(
        checkpointer=checkpointer,
        pending_graph_service=pending_graph_service,
        pending_interrupt_projector=projector,
        new_flow_graph_service=new_flow_graph_service,
    )
    task = waiting_task_stub()
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充金额 10 万"),
        content="补充金额 10 万",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
        event_sink=failing_event_sink,
    )

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )

    assert state["runtime_status"] == "pending_projection_failed"
    assert state["runtime_retryable"] is False
    projection_state = state["pending_interrupt_projection"]
    assert {
        key: projection_state.get(key)
        for key in (
            "status",
            "projection_key",
            "replayed",
            "busy",
            "retryable",
            "failure_reason",
            "delivery_status",
        )
    } == {
        "status": "FAILED",
        "projection_key": "pending_interrupt_projection:v1:failed",
        "replayed": False,
        "busy": False,
        "retryable": False,
        "failure_reason": "projection_continuation_mismatch",
        "delivery_status": None,
    }
    assert projection_state["continuation"] == projector.calls[0].continuation
    assert projection_state["interrupt"] == projector.calls[0].interrupt
    assert state["application_action"] == "finish"
    assert state["pending_task_handled"] is False
    assert state["pending_task_continuation_ref"] is None
    assert state["pending_task_requested"] is False
    assert state["current_interrupt"] is None
    assert "__interrupt__" not in state
    assert state["assistant_content"] == "当前待确认流程投影失败，本次流程已终止；你可以重新发起。"
    assert context.side_effects.pending_task_events[-1] == {
        "event": "pending_task_interrupt_projection_failed",
        "reason": "projection_continuation_mismatch",
        "projection_key": "pending_interrupt_projection:v1:failed",
        "retryable": False,
    }
    checkpoint_state = await runtime.current_checkpoint_state(
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
    )
    assert checkpoint_state["runtime_status"] == "pending_projection_failed"
    assert checkpoint_state.get("current_interrupt") is None
    assert await runtime.current_interrupt(
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
    ) is None
    history = await runtime.state_history(
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
    )
    assert any("pending_projection_failure" in item["next_nodes"] for item in history)
    assert any("finish_turn" in item["next_nodes"] for item in history)
    assert any(
        item["values"].get("pending_task_projection_error")
        == "projection_continuation_mismatch"
        for item in history
    )
    continuation = projector.calls[0].continuation
    recovery = await pending_graph_service.load_checkpointed_outcome(continuation)
    assert recovery.failure_reason is None
    assert recovery.outcome is not None
    assert recovery.outcome.get("current_interrupt") is not None
    assert recovery.outcome.get("projection_aborted") is not True

    context.event_sink = None
    context.turn_input = AgentTurnInput.text("重新记录一个客户跟进")
    context.content = "重新记录一个客户跟进"
    next_state = await runtime.run_turn(
        turn_input=context.turn_input,
        content=context.content,
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        current_customer={},
        context=context,
    )
    assert next_state["runtime_status"] != "pending_projection_failed"
    assert len(new_flow_graph_service.calls) == 1


@pytest.mark.asyncio
async def test_root_runtime_terminates_direct_pending_checkpoint_recovery_failure():
    checkpointer = InMemorySaver()
    new_flow_graph_service = FakeNewFlowGraphService()
    runtime = AgentRootRuntime(
        checkpointer=checkpointer,
        pending_graph_service=FakeTerminalRecoveryPendingGraphService(),
        new_flow_graph_service=new_flow_graph_service,
    )
    task = waiting_task_stub()
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充金额 10 万"),
        content="补充金额 10 万",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )

    assert state["application_action"] == "finish"
    assert state["runtime_status"] == "checkpoint_recovery_failed"
    assert state["runtime_retryable"] is False
    assert state["current_interrupt"] is None
    assert state["pending_task_continuation_ref"] is None
    assert state["pending_task_requested"] is False
    assert state["assistant_content"] == "当前待确认流程恢复失败，本次流程已终止；你可以重新发起。"
    assert len([
        event
        for event in context.side_effects.pending_task_events
        if event.get("event") == "pending_task_checkpoint_recovery_failed"
    ]) == 1

    context.task = None
    context.turn_input = AgentTurnInput.text("重新记录一个客户跟进")
    context.content = "重新记录一个客户跟进"
    next_state = await runtime.run_turn(
        turn_input=context.turn_input,
        content=context.content,
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        current_customer={},
        context=context,
    )
    assert next_state["runtime_status"] != "checkpoint_recovery_failed"
    assert len(new_flow_graph_service.calls) == 1


@pytest.mark.asyncio
async def test_root_runtime_does_not_resume_historical_suspended_candidate_without_active_interrupt():
    checkpointer = InMemorySaver()
    pending_graph_service = FakeTerminalRecoveryPendingGraphService()
    new_flow_graph_service = FakeNewFlowGraphService()
    runtime = AgentRootRuntime(
        checkpointer=checkpointer,
        pending_graph_service=pending_graph_service,
        new_flow_graph_service=new_flow_graph_service,
    )
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=2, context_json={}),
        task=None,
        turn_input=AgentTurnInput.text("历史轮次"),
        content="历史轮次",
        team_id=1,
        user_id=1,
        session_id=2,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )
    historical_candidate = {
        "id": 78,
        "task_key": "task-78",
        "status": "SUSPENDED",
        "intent": "CREATE_OPPORTUNITY",
        "target_type": "customer",
        "target_id": 9001,
        "summary": "华米商机字段补充确认",
        "suspend_reason": "用户选择先不处理",
    }

    failed = await runtime.checkpoint_turn_start(
        {
            "team_id": 1,
            "user_id": 1,
            "session_id": 2,
            "session_key": "session-2",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "current_interrupt": None,
            # Reproduce a checkpoint written by the pre-fix runtime, where a
            # historical candidate alone incorrectly requested pending resume.
            "pending_task_requested": True,
            "suspended_candidates": [historical_candidate],
        },
        context=context,
    )
    assert failed["runtime_status"] == "checkpoint_recovery_failed"
    assert failed["suspended_candidates"] == [historical_candidate]
    assert len(pending_graph_service.calls) == 1
    assert new_flow_graph_service.calls == []
    context.side_effects = AgentRootRuntimeSideEffects()
    context.turn_input = AgentTurnInput.text(
        "今天和国智技术沟通了项目进展并请整理成跟进记录"
    )
    context.content = context.turn_input.content

    result = await runtime.run_turn(
        turn_input=context.turn_input,
        content=context.content,
        team_id=1,
        user_id=1,
        session_id=2,
        session_key="session-2",
        current_customer={},
        context=context,
    )

    assert len(pending_graph_service.calls) == 1
    assert len(new_flow_graph_service.calls) == 1
    assert new_flow_graph_service.calls[0]["content"] == context.content
    assert result["runtime_status"] != "checkpoint_recovery_failed"
    assert result["route"] == "new_flow_graph"


@pytest.mark.asyncio
async def test_checkpoint_recovery_failure_survives_sink_failure_without_mutating_child_checkpoint():
    checkpointer = InMemorySaver()
    delegate = PendingTaskGraphService(
        preflight_graph_service=FakeNativeInterruptPreflightGraphService(),
        interaction_graph_service=FakeNativeInterruptInteractionGraphService(),
        checkpointer=checkpointer,
    )

    class RecoveryFailingPendingGraphService:
        async def run(self, state, *, side_effects=None):
            return await delegate.run(state, side_effects=side_effects)

        async def run_with_trace(self, state, *, side_effects=None):
            return await delegate.run_with_trace(state, side_effects=side_effects)

        async def load_checkpointed_outcome(self, *args, **kwargs):
            return PendingTaskOutcomeRecovery(failure_reason="checkpoint_corrupt")

    async def failing_event_sink(event):
        if event.get("event") == "pending_task_checkpoint_recovery_failed":
            raise RuntimeError("transport unavailable")

    new_flow_graph_service = FakeNewFlowGraphService()
    runtime = AgentRootRuntime(
        checkpointer=checkpointer,
        pending_graph_service=RecoveryFailingPendingGraphService(),
        new_flow_graph_service=new_flow_graph_service,
    )
    task = waiting_task_stub()
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充金额 10 万"),
        content="补充金额 10 万",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
        event_sink=failing_event_sink,
    )

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )

    assert state["runtime_status"] == "checkpoint_recovery_failed"
    assert state["runtime_retryable"] is False
    assert state["current_interrupt"] is None
    assert state["pending_interrupt_projection"] == {}
    assert state["pending_task_continuation_ref"] is None
    assert state["pending_task_requested"] is False
    assert len([
        event
        for event in context.side_effects.pending_task_events
        if event.get("event") == "pending_task_checkpoint_recovery_failed"
    ]) == 1
    continuation = context.side_effects.pending_task_graph_side_effects.checkpoint_ref
    recovery = await delegate.load_checkpointed_outcome(continuation)
    assert recovery.failure_reason is None
    assert recovery.outcome is not None
    assert recovery.outcome.get("current_interrupt") is not None
    assert recovery.outcome.get("projection_aborted") is not True
    assert recovery.outcome["pending_interrupt_requested"] is True

    context.event_sink = None
    context.task = None
    context.turn_input = AgentTurnInput.text("重新记录一个客户跟进")
    context.content = "重新记录一个客户跟进"
    next_state = await runtime.run_turn(
        turn_input=context.turn_input,
        content=context.content,
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        current_customer={},
        context=context,
    )
    assert next_state["runtime_status"] != "checkpoint_recovery_failed"
    assert len(new_flow_graph_service.calls) == 1


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
    assert "task" not in pending_graph_service.trace_calls[0]
    assert pending_graph_service.trace_calls[0]["task_snapshot"] == agent_task_snapshot(task)
    assert without_projection_metadata(side_effects.pending_task_events[:3]) == [
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
        "ownership_status": "accepted",
    }
    assert state["pending_task_snapshot"] == {}
    assert state["task_projection"] == {}
    assert state["pending_task_requested"] is False


@pytest.mark.asyncio
async def test_root_runtime_transfers_confirmed_task_ownership_to_next_snapshot_atomically():
    pending_graph_service = FakeConfirmingPendingGraphService()
    confirmed_task_graph_service = FakeConfirmedTaskWithNextGraphService()
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4),
        task=SimpleNamespace(
            id=101,
            task_key="task-101",
            team_id=2,
            user_id=3,
            session_id=4,
            status="WAITING_USER",
            state_json={"action": "create_customer_activity"},
        ),
        turn_input=AgentTurnInput.confirm(source="web"),
        content="确认",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        pending_graph_service=pending_graph_service,
        confirmed_task_graph_service=confirmed_task_graph_service,
        pending_task_side_effect_handler=FakePendingTaskSideEffectHandler(),
    )

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "confirmed-next-owner",
            "channel": "web",
            "content": "确认",
            "turn_kind": "confirm",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )

    assert state["pending_task_snapshot"]["id"] == 102
    assert state["task_projection"] == {
        "id": 102,
        "task_key": "task-102",
        "status": "WAITING_USER",
        "intent": "CREATE_OPPORTUNITY",
        "target_type": "customer",
        "target_id": 17,
    }
    assert state["pending_task_requested"] is True
    assert state["current_interrupt"]["task_projection_id"] == 102
    assert state["current_interrupt"]["task_projection_key"] == "task-102"
    assert context.task is None


def test_project_turn_output_preserves_pending_events_before_confirmed_task_events():
    side_effects = AgentRootRuntimeSideEffects()
    side_effects.pending_task_events.extend(
        [
            {"event": "confirmation_intent_assessed"},
        ]
    )
    side_effects.confirmed_task_events.extend(
        [
            {"event": "agent_step", "step": "confirmed_task_execute", "status": "started", "content": "执行记录跟进"},
            {"event": "agent_step", "step": "confirmed_task_execute", "status": "completed", "content": "执行记录跟进"},
            {"event": "tool_result", "success": True, "content": "记录跟进已执行"},
            {"event": "task_completed", "content": "跟进记录已创建。"},
            {"event": "final", "content": "跟进记录已创建。"},
        ]
    )
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
    side_effects.pending_task_events.extend(
        [
            {"event": "pending_task_interrupted"},
        ]
    )
    side_effects.pending_task_switch_notice = "这条是在说「汇川技术」。我先把刚才那一步放着，切过来处理。"
    side_effects.new_flow_events.extend(
        [
            {
                "event": "final",
                "content": "这条是在说「汇川技术」。我先把刚才那一步放着，切过来处理。\n\n已切换处理汇川技术的跟进。",
            },
        ]
    )
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


@pytest.mark.asyncio
async def test_root_runtime_retry_keeps_confirmation_action_waiting(monkeypatch):
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
    )
    original = SimpleNamespace(
        workflow_id="wf_retry_required",
        action_id="act_required",
        status="FAILED",
        execution_policy=action_workflow.EXECUTION_REQUIRES_CONFIRMATION,
        scope=action_workflow.SCOPE_REQUIRED_WRITE,
    )
    prepared = SimpleNamespace(
        **{
            **original.__dict__,
            "status": "WAITING_USER",
            "source": action_workflow.SOURCE_EXPLICIT_USER_REQUEST,
            "on_reject": action_workflow.ON_REJECT_CANCEL_ACTION,
            "blocking": True,
        }
    )
    prepare_calls = []

    def fake_prepare(db, action, *, retry_source, reason):
        prepare_calls.append(
            {
                "db": db,
                "action_id": action.action_id,
                "retry_source": retry_source,
                "reason": reason,
            }
        )
        return prepared

    async def fail_if_replayed(*args, **kwargs):
        raise AssertionError("confirmation-required retry must not auto execute")

    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "prepare_action_retry", fake_prepare)
    monkeypatch.setattr(runtime, "_run_new_flow_auto_execute_tasks", fail_if_replayed)

    db = object()
    result = await runtime.retry_workflow_action(
        db=db,
        action=original,
        session=SimpleNamespace(id=4),
        team_id=2,
        user_id=3,
        retry_source="manual_test",
        reason="用户手动重试",
    )

    assert result is prepared
    assert prepare_calls == [
        {
            "db": db,
            "action_id": "act_required",
            "retry_source": "manual_test",
            "reason": "用户手动重试",
        }
    ]


@pytest.mark.asyncio
async def test_root_runtime_retry_replays_auto_execute_actions_through_dag(monkeypatch):
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
    )
    failed_action = _ledger_action_stub(
        action_id="act_projection",
        status="FAILED",
        execution_policy=action_workflow.EXECUTION_AUTO_EXECUTE,
        scope=action_workflow.SCOPE_DERIVED_AUTOMATION,
        action_type="create_customer_activity",
        payload_json={
            "customer_id": 10,
            "source_content": "今天和客户确认续费推进",
        },
    )
    prepared_action = _ledger_action_stub(
        action_id="act_projection",
        status="PLANNED",
        execution_policy=action_workflow.EXECUTION_AUTO_EXECUTE,
        scope=action_workflow.SCOPE_DERIVED_AUTOMATION,
        action_type="create_customer_activity",
        payload_json={
            "customer_id": 10,
            "source_content": "今天和客户确认续费推进",
        },
    )
    downstream_action = _ledger_action_stub(
        action_id="act_profile_refresh",
        status="PLANNED",
        execution_policy=action_workflow.EXECUTION_AUTO_EXECUTE,
        scope=action_workflow.SCOPE_DERIVED_AUTOMATION,
        action_type="transition_follow_up_task",
        dependency_json={"depends_on": ["act_projection"]},
        payload_json={"task_id": 99, "transition_action": "complete"},
    )
    required_waiting_action = _ledger_action_stub(
        action_id="act_optional_opportunity",
        status="WAITING_USER",
        execution_policy=action_workflow.EXECUTION_REQUIRES_CONFIRMATION,
        scope=action_workflow.SCOPE_OPTIONAL_SUGGESTION,
        action_type="create_opportunity",
    )
    replay_calls = []
    refreshed = SimpleNamespace(**{**prepared_action.__dict__, "status": "EXECUTED"})

    def fake_prepare(db, action, *, retry_source, reason):
        return prepared_action

    class FakeWorkflowActionCrud:
        def list_by_workflow(self, db, workflow_id, team_id=None, user_id=None, include_system_actions=False):
            assert workflow_id == "wf_retry"
            assert include_system_actions is True
            return [prepared_action, downstream_action, required_waiting_action]

        def get_by_workflow_action(
            self,
            db,
            *,
            workflow_id,
            action_id,
            team_id=None,
            user_id=None,
            include_system_actions=False,
        ):
            assert workflow_id == "wf_retry"
            assert action_id == "act_projection"
            return refreshed

    async def fake_replay(context, side_effect_context):
        replay_calls.append(
            {
                "session_id": context.session_id,
                "authorization": context.authorization,
                "action_ids": [item.action_id for item in side_effect_context.auto_execute_actions],
            }
        )
        return {"executed_action_count": 2}

    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "prepare_action_retry", fake_prepare)
    monkeypatch.setattr(root_runtime_module, "agent_workflow_action_crud", FakeWorkflowActionCrud())
    monkeypatch.setattr(runtime, "_run_new_flow_auto_execute_tasks", fake_replay)

    result = await runtime.retry_workflow_action(
        db=object(),
        action=failed_action,
        session=SimpleNamespace(id=4),
        team_id=2,
        user_id=3,
        authorization="Bearer retry-test",
    )

    assert result is refreshed
    assert replay_calls == [
        {
            "session_id": 4,
            "authorization": "Bearer retry-test",
            "action_ids": ["act_projection", "act_profile_refresh"],
        }
    ]


@pytest.mark.asyncio
async def test_root_runtime_retry_workflow_prepares_retryable_actions_and_replays_auto_dag(monkeypatch):
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
    )
    failed_auto = _ledger_action_stub(
        action_id="act_auto_failed",
        status="FAILED",
        execution_policy=action_workflow.EXECUTION_AUTO_EXECUTE,
        scope=action_workflow.SCOPE_DERIVED_AUTOMATION,
        action_type="create_customer_activity",
        payload_json={"customer_id": 10, "source_content": "补偿写入跟进"},
    )
    blocked_auto = _ledger_action_stub(
        action_id="act_auto_blocked",
        status="BLOCKED",
        execution_policy=action_workflow.EXECUTION_AUTO_EXECUTE,
        scope=action_workflow.SCOPE_DERIVED_AUTOMATION,
        action_type="transition_follow_up_task",
        dependency_json={"depends_on": ["act_auto_failed"]},
        payload_json={"task_id": 99, "transition_action": "complete"},
    )
    failed_required = _ledger_action_stub(
        action_id="act_required_failed",
        status="FAILED",
        execution_policy=action_workflow.EXECUTION_REQUIRES_CONFIRMATION,
        scope=action_workflow.SCOPE_REQUIRED_WRITE,
        action_type="create_opportunity",
    )
    executed_auto = _ledger_action_stub(
        action_id="act_auto_done",
        status="EXECUTED",
        execution_policy=action_workflow.EXECUTION_AUTO_EXECUTE,
        scope=action_workflow.SCOPE_DERIVED_AUTOMATION,
        action_type="refresh_customer_profile",
    )
    prepared = {
        "act_auto_failed": _ledger_action_stub(
            action_id="act_auto_failed",
            status="PLANNED",
            execution_policy=action_workflow.EXECUTION_AUTO_EXECUTE,
            scope=action_workflow.SCOPE_DERIVED_AUTOMATION,
            action_type="create_customer_activity",
            payload_json={"customer_id": 10, "source_content": "补偿写入跟进"},
        ),
        "act_auto_blocked": _ledger_action_stub(
            action_id="act_auto_blocked",
            status="PLANNED",
            execution_policy=action_workflow.EXECUTION_AUTO_EXECUTE,
            scope=action_workflow.SCOPE_DERIVED_AUTOMATION,
            action_type="transition_follow_up_task",
            dependency_json={"depends_on": ["act_auto_failed"]},
            payload_json={"task_id": 99, "transition_action": "complete"},
        ),
        "act_required_failed": _ledger_action_stub(
            action_id="act_required_failed",
            status="WAITING_USER",
            execution_policy=action_workflow.EXECUTION_REQUIRES_CONFIRMATION,
            scope=action_workflow.SCOPE_REQUIRED_WRITE,
            action_type="create_opportunity",
        ),
    }
    prepare_calls: list[str] = []
    replay_calls: list[list[str]] = []

    def fake_prepare(db, action, *, retry_source, reason):
        prepare_calls.append(action.action_id)
        assert retry_source == "manual_test"
        assert reason == "恢复工作流"
        return prepared[action.action_id]

    class FakeWorkflowActionCrud:
        def list_by_workflow(self, db, workflow_id, team_id=None, user_id=None, include_system_actions=False):
            assert workflow_id == "wf_retry"
            assert include_system_actions is True
            return [
                prepared["act_auto_failed"],
                prepared["act_auto_blocked"],
                prepared["act_required_failed"],
                executed_auto,
            ]

    async def fake_replay(context, side_effect_context):
        replay_calls.append([item.action_id for item in side_effect_context.auto_execute_actions])
        return {"executed_action_count": 2}

    monkeypatch.setattr(root_runtime_module.workflow_action_ledger, "prepare_action_retry", fake_prepare)
    monkeypatch.setattr(root_runtime_module, "agent_workflow_action_crud", FakeWorkflowActionCrud())
    monkeypatch.setattr(runtime, "_run_new_flow_auto_execute_tasks", fake_replay)

    result = await runtime.retry_workflow(
        db=object(),
        workflow_id="wf_retry",
        actions=[failed_auto, blocked_auto, failed_required, executed_auto],
        session=SimpleNamespace(id=4),
        team_id=2,
        user_id=3,
        authorization="Bearer workflow-retry",
        retry_source="manual_test",
        reason="恢复工作流",
    )

    assert prepare_calls == ["act_auto_failed", "act_auto_blocked", "act_required_failed"]
    assert replay_calls == [["act_auto_failed", "act_auto_blocked", "act_auto_done"]]
    assert [action.action_id for action in result] == [
        "act_auto_failed",
        "act_auto_blocked",
        "act_required_failed",
        "act_auto_done",
    ]


def _ledger_action_stub(
    *,
    action_id: str,
    status: str,
    execution_policy: str,
    scope: str,
    action_type: str,
    workflow_id: str = "wf_retry",
    dependency_json: dict | None = None,
    payload_json: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        workflow_id=workflow_id,
        action_id=action_id,
        parent_action_id=None,
        team_id=2,
        user_id=3,
        session_id=4,
        task_id=None,
        source_message_id=None,
        source_type="agent_planning",
        action_type=action_type,
        status=status,
        scope=scope,
        source=(
            action_workflow.SOURCE_SYSTEM_AUTOMATION
            if execution_policy == action_workflow.EXECUTION_AUTO_EXECUTE
            else action_workflow.SOURCE_BUSINESS_SUGGESTION
        ),
        execution_policy=execution_policy,
        on_reject=action_workflow.ON_REJECT_ASK_CLARIFICATION,
        blocking=False,
        target_type="customer",
        target_id=10,
        dependency_json=dependency_json,
        payload_json=payload_json,
        result_json=None,
        decision_json=None,
        idempotency_key=None,
        status_reason=None,
        error_message=None,
    )


class FakeFollowUpConfirmationChannelService:
    def __init__(self):
        self.prepare_calls = []
        self.resolve_calls = []
        self.list_calls = []
        self.projected_prompt_keys = []
        self.failed_projection_calls = []
        self.pending_case_public_ids = []
        self.pending_checks = []

    def revalidate_case_pending_for_owner(self, *, team_id, user_id, case_public_id):
        self.pending_checks.append(
            {
                "team_id": team_id,
                "user_id": user_id,
                "case_public_id": case_public_id,
            }
        )
        return case_public_id in self.pending_case_public_ids

    def prepare_case_prompt_by_public_ids(
        self,
        db,
        *,
        team_id,
        user_id,
        case_public_ids,
        interaction_scope,
        turn_scope=None,
        prompt_override=None,
        reason_code="ROOT_GRAPH_INTERRUPT_PLANNED",
    ):
        self.prepare_calls.append(
            {
                "db": db,
                "team_id": team_id,
                "user_id": user_id,
                "case_public_ids": case_public_ids,
                "interaction_scope": interaction_scope,
                "prompt_override": prompt_override,
                "reason_code": reason_code,
            }
        )
        if not case_public_ids:
            return None
        case_public_id = case_public_ids[0]
        return {
            "event": "follow_up_task_confirmation_case_prompt",
            "content": prompt_override or "上次安排的任务这次是否已经完成?",
            "case_public_id": case_public_id,
            "interaction": {
                "schema_version": "agent.interaction.v1",
                "interaction_id": "int_follow_up_confirmation_stable",
                "type": "choice",
                "business_action": "resolve_follow_up_task_confirmation_case",
                "status": "waiting_user_input",
                "title": "确认跟进进展",
                "prompt": prompt_override or "上次安排的任务这次是否已经完成?",
                "payload": {
                    "case_public_id": case_public_id,
                    "prompt_delivery_key": FollowUpTaskConfirmationChannelService._projection_prompt_key(
                        case_public_id=case_public_id,
                        interaction_scope=interaction_scope,
                    ),
                },
                "choices": [
                    {
                        "label": "已完成",
                        "value": "已完成",
                        "metadata": {"case_public_id": case_public_id},
                    },
                ],
            },
        }

    def list_pending_cases(self, db, *, team_id, user_id, skip=0, limit=20):
        self.list_calls.append(
            {
                "db": db,
                "team_id": team_id,
                "user_id": user_id,
                "skip": skip,
                "limit": limit,
            }
        )
        items = [{"public_id": public_id} for public_id in self.pending_case_public_ids[skip : skip + limit]]
        return {
            "items": items,
            "total": len(self.pending_case_public_ids),
            "skip": skip,
            "limit": limit,
        }

    def mark_projection_projected(self, db, *, team_id, prompt_key):
        self.projected_prompt_keys.append(prompt_key)
        return {"status": "PROJECTED"}

    def mark_projection_failed(self, db, *, team_id, prompt_key, error_message):
        self.failed_projection_calls.append(
            {
                "db": db,
                "team_id": team_id,
                "prompt_key": prompt_key,
                "error_message": error_message,
            }
        )
        return {"status": "FAILED"}

    def resolve_reply_event(
        self,
        db,
        *,
        team_id,
        user_id,
        case_public_id,
        reply_text,
    ):
        self.resolve_calls.append(
            {
                "db": db,
                "team_id": team_id,
                "user_id": user_id,
                "case_public_id": case_public_id,
                "reply_text": reply_text,
            }
        )
        return {
            "event": "follow_up_task_confirmation_resolved",
            "case_public_id": case_public_id,
            "content": "已确认完成，并更新了这项跟进任务。",
        }


@pytest.mark.asyncio
async def test_root_runtime_projects_auto_executed_activity_confirmation_as_interrupt(monkeypatch):
    case_public_id = "fuc_b6184685cfcf4345b6d52e48d23bf170"

    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.session_state._remember_current_customer",
        lambda db_arg, session_arg, customer: None,
    )

    async def fake_execute_action_envelope(
        db,
        envelope,
        *,
        session,
        team_id,
        user_id,
        authorization,
        event_sink,
    ):
        return ActionToolExecutionResult(
            AgentToolResult(
                tool_name="create_customer_activity",
                success=True,
                data={
                    "id": 212,
                    "post_commit": {
                        "needs_user_confirmation": True,
                        "confirmation_case_public_ids": [case_public_id],
                    },
                },
                tool_call_id=7001,
            )
        )

    monkeypatch.setattr(root_runtime_module.task_execution, "execute_action_envelope", fake_execute_action_envelope)
    monkeypatch.setattr(
        root_runtime_module.workflow_action_ledger, "mark_action_executed", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        root_runtime_module.workflow_action_ledger, "execution_state_for_action_ids", lambda *args, **kwargs: {}
    )

    channel_service = FakeFollowUpConfirmationChannelService()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeAutoExecutableNewFlowGraphService(),
        confirmed_task_graph_service=FakeConfirmedTaskGraphService(),
        confirmation_channel_service=channel_service,
    )
    side_effects = AgentRootRuntimeSideEffects()
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        content="今天已经反馈分类分级表，明天提供测试报告",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=side_effects,
    )

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
        },
        context=context,
    )

    current_interrupt = state["current_interrupt"]
    assert current_interrupt["reason"] == "follow_up_task_confirmation"
    assert current_interrupt["business_action"] == "resolve_follow_up_task_confirmation_case"
    assert current_interrupt["interaction"]["interaction_id"] == "int_follow_up_confirmation_stable"
    assert current_interrupt["interaction"]["payload"]["case_public_id"] == case_public_id
    assert state["post_write_effects"] == {
        "follow_up_confirmation_case_public_ids": [case_public_id],
    }
    assert channel_service.prepare_calls[0]["case_public_ids"] == [case_public_id]
    assert channel_service.projected_prompt_keys == [current_interrupt["interaction"]["payload"]["prompt_delivery_key"]]
    assert len(channel_service.projected_prompt_keys[0]) <= 128
    assert [event for event in side_effects.new_flow_events if event.get("event") == "final"] == []
    prompt_events = [
        event
        for event in side_effects.business_interaction_events
        if event.get("event") == "follow_up_task_confirmation_case_prompt"
    ]
    assert len(prompt_events) == 1


@pytest.mark.asyncio
async def test_root_runtime_resumes_projected_follow_up_confirmation_through_channel_service(monkeypatch):
    case_public_id = "fuc_b6184685cfcf4345b6d52e48d23bf170"
    channel_service = FakeFollowUpConfirmationChannelService()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        confirmation_channel_service=channel_service,
    )
    side_effects = AgentRootRuntimeSideEffects()
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        turn_input=AgentTurnInput.text("已完成"),
        content="已完成",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=side_effects,
    )
    interrupt_payload = {
        "schema_version": "agent.interrupt.v1",
        "interrupt_id": "int_follow_up_confirmation_stable",
        "reason": "follow_up_task_confirmation",
        "business_action": "resolve_follow_up_task_confirmation_case",
        "content": "上次安排的任务这次是否已经完成?",
        "interaction": {
            "schema_version": "agent.interaction.v1",
            "interaction_id": "int_follow_up_confirmation_stable",
            "type": "choice",
            "business_action": "resolve_follow_up_task_confirmation_case",
            "status": "waiting_user_input",
            "title": "确认跟进进展",
            "prompt": "上次安排的任务这次是否已经完成?",
            "payload": {"case_public_id": case_public_id},
            "choices": [],
        },
    }

    await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "记录跟进",
            "turn_kind": "text",
            "current_interrupt": interrupt_payload,
        },
        context=context,
    )

    result = await runtime.resume_interrupt(
        resume_payload={
            "action": "submit",
            "content": "已完成",
            "metadata": {},
        },
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        context=context,
    )

    assert channel_service.resolve_calls == [
        {
            "db": context.db,
            "team_id": 2,
            "user_id": 3,
            "case_public_id": case_public_id,
            "reply_text": "已完成",
        }
    ]
    assert result["assistant_content"] == "已确认完成，并更新了这项跟进任务。"
    assert any(
        event.get("event") == "follow_up_task_confirmation_resolved"
        for event in side_effects.business_interaction_events
    )


@pytest.mark.asyncio
async def test_run_turn_discards_stale_follow_up_interrupt_before_processing_new_message():
    case_public_id = "fuc_resolved_in_confirmation_center"

    class RecordingTurnIntentRouter:
        def __init__(self):
            self.calls = []

        async def route_resume(self, db, **kwargs):
            self.calls.append({"db": db, **kwargs})
            return SimpleNamespace(
                decision=SimpleNamespace(
                    intent="CONTINUE_PENDING",
                    confidence=1.0,
                    target_task_id=None,
                    normalized_action="submit",
                    reason="测试旧确认中断。",
                ),
                resume_payload={
                    "action": "submit",
                    "content": kwargs["turn_input"].content,
                    "metadata": {},
                },
                source="test_router",
            )

    channel_service = FakeFollowUpConfirmationChannelService()
    channel_service.pending_case_public_ids = [case_public_id]
    new_flow_graph_service = FakeNewFlowGraphService()
    turn_intent_router = RecordingTurnIntentRouter()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=new_flow_graph_service,
        confirmation_channel_service=channel_service,
        turn_intent_router=turn_intent_router,
    )
    published_events = []

    async def capture_event(event):
        published_events.append(event)

    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        turn_input=AgentTurnInput.text("查看这个客户的最新进展"),
        content="查看这个客户的最新进展",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
        event_sink=capture_event,
    )
    initial_event = channel_service.prepare_case_prompt_by_public_ids(
        context.db,
        team_id=2,
        user_id=3,
        case_public_ids=[case_public_id],
        interaction_scope="crm_agent:2:3:4:abc",
    )
    interrupt_payload = {
        "schema_version": "agent.interrupt.v1",
        "interrupt_id": "int_stale_follow_up_confirmation",
        "type": "choice",
        "reason": "follow_up_task_confirmation",
        "business_action": "resolve_follow_up_task_confirmation_case",
        "interaction": initial_event["interaction"],
    }
    await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "记录跟进",
            "turn_kind": "text",
            "current_interrupt": interrupt_payload,
        },
        context=context,
    )

    channel_service.pending_case_public_ids = []
    published_events.clear()
    context.side_effects = AgentRootRuntimeSideEffects()

    result = await runtime.run_turn(
        turn_input=context.turn_input,
        content=context.content,
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        current_customer={},
        context=context,
    )

    assert turn_intent_router.calls == []
    assert channel_service.resolve_calls == []
    assert new_flow_graph_service.calls[0]["content"] == "查看这个客户的最新进展"
    assert result["assistant_content"] == "已处理新流程"
    assert any(
        event.get("event") == "follow_up_task_confirmation_stale_interrupt_discarded"
        and event.get("case_public_id") == case_public_id
        for event in published_events
    )


@pytest.mark.asyncio
async def test_root_runtime_keeps_follow_up_confirmation_interrupt_when_reply_is_unrecognized():
    case_public_id = "fuc_b6184685cfcf4345b6d52e48d23bf170"

    class UnresolvedChannelService(FakeFollowUpConfirmationChannelService):
        def resolve_reply_event(self, db, *, team_id, user_id, case_public_id, reply_text):
            self.resolve_calls.append(
                {
                    "db": db,
                    "team_id": team_id,
                    "user_id": user_id,
                    "case_public_id": case_public_id,
                    "reply_text": reply_text,
                }
            )
            return {
                "event": "follow_up_task_confirmation_case_resolved",
                "content": "请直接回复已完成、先放着、不管了，或说明延期时间。",
                "case": {"public_id": case_public_id, "unresolved_reply_count": 1},
                "assistant_follow_up_prompt": "请直接回复已完成、先放着、不管了，或说明延期时间。",
            }

    channel_service = UnresolvedChannelService()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        confirmation_channel_service=channel_service,
    )
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        turn_input=AgentTurnInput.text("再看看"),
        content="再看看",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )
    interrupt_payload = {
        "schema_version": "agent.interrupt.v1",
        "interrupt_id": "int_follow_up_confirmation_stable",
        "type": "choice",
        "reason": "follow_up_task_confirmation",
        "business_action": "resolve_follow_up_task_confirmation_case",
        "interaction": channel_service.prepare_case_prompt_by_public_ids(
            context.db,
            team_id=2,
            user_id=3,
            case_public_ids=[case_public_id],
            interaction_scope="initial",
        )["interaction"],
    }

    await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "记录跟进",
            "turn_kind": "text",
            "current_interrupt": interrupt_payload,
        },
        context=context,
    )

    result = await runtime.resume_interrupt(
        resume_payload={
            "action": "select",
            "content": "再看看",
            "metadata": {"selected_value": "再看看"},
        },
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        context=context,
    )

    assert result["current_interrupt"]["reason"] == "follow_up_task_confirmation"
    retry_interaction = result["current_interrupt"]["interaction"]
    assert retry_interaction["prompt"] == "请直接回复已完成、先放着、不管了，或说明延期时间。"
    assert retry_interaction["payload"]["prompt_delivery_key"] == (
        FollowUpTaskConfirmationChannelService._projection_prompt_key(
            case_public_id=case_public_id,
            interaction_scope="crm_agent:2:3:4:abc:clarification:1",
        )
    )
    assert result["runtime_status"] == "resumed"


@pytest.mark.asyncio
async def test_root_runtime_never_projects_owner_inbox_case_on_unrelated_later_turn():
    historical_case = "fuc_async_page_created_for_other_customer"
    channel_service = FakeFollowUpConfirmationChannelService()
    channel_service.pending_case_public_ids = [historical_case]
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeNewFlowGraphService(),
        confirmation_channel_service=channel_service,
    )
    side_effects = AgentRootRuntimeSideEffects()
    context = AgentRuntimeContext(
        db=SimpleNamespace(query=lambda *args, **kwargs: None),
        session=SimpleNamespace(id=4, context_json={}),
        content="给当前客户添加一条部署信息",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=side_effects,
    )

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "turn_scope": {
                "turn_id": "turn-current-customer",
                "session_id": 4,
                "channel": "web",
                "customer_id": 101,
                "operation_status": "active",
            },
        },
        context=context,
    )

    assert not state.get("current_interrupt")
    assert channel_service.prepare_calls == []
    assert channel_service.list_calls == []
    assert any(event.get("event") == "final" for event in side_effects.new_flow_events)
    assert state["assistant_content"] == "已处理新流程"


@pytest.mark.asyncio
async def test_resolving_current_confirmation_does_not_chain_next_owner_inbox_case():
    first_case = "fuc_first"
    second_case = "fuc_second"

    class MultiCaseChannelService(FakeFollowUpConfirmationChannelService):
        def resolve_reply_event(self, db, *, team_id, user_id, case_public_id, reply_text):
            result = super().resolve_reply_event(
                db,
                team_id=team_id,
                user_id=user_id,
                case_public_id=case_public_id,
                reply_text=reply_text,
            )
            self.pending_case_public_ids = [second_case]
            return result

    channel_service = MultiCaseChannelService()
    channel_service.pending_case_public_ids = [first_case]
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeNewFlowGraphService(),
        confirmation_channel_service=channel_service,
    )
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        content="记录当前客户跟进",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )
    initial_event = channel_service.prepare_case_prompt_by_public_ids(
        context.db,
        team_id=2,
        user_id=3,
        case_public_ids=[first_case],
        interaction_scope="crm_agent:2:3:4:abc",
    )
    interrupt_payload = {
        "schema_version": "agent.interrupt.v1",
        "interrupt_id": "int_follow_up_confirmation_stable",
        "type": "choice",
        "reason": "follow_up_task_confirmation",
        "business_action": "resolve_follow_up_task_confirmation_case",
        "interaction": initial_event["interaction"],
    }
    await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "current_interrupt": interrupt_payload,
        },
        context=context,
    )

    resumed = await runtime.resume_interrupt(
        resume_payload={
            "action": "select",
            "content": "已完成",
            "metadata": {"selected_value": "已完成"},
        },
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        context=context,
    )

    assert not resumed.get("current_interrupt")
    assert resumed["assistant_content"] == "已确认完成，并更新了这项跟进任务。"
    assert [call["case_public_ids"] for call in channel_service.prepare_calls] == [[first_case]]
    assert channel_service.list_calls == []


@pytest.mark.asyncio
async def test_follow_up_confirmation_is_published_only_after_checkpoint_projection():
    case_public_id = "fuc_checkpoint_safe"
    channel_service = FakeFollowUpConfirmationChannelService()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeNewFlowGraphService(),
        confirmation_channel_service=channel_service,
    )
    published_events = []

    async def capture_event(event):
        published_events.append(event)

    context = AgentRuntimeContext(
        db=SimpleNamespace(query=lambda *args, **kwargs: None),
        session=SimpleNamespace(id=4, context_json={}),
        content="查看客户最新进展",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
        event_sink=capture_event,
    )
    context.side_effects.new_flow_events.append({
        "event": "customer_activity_post_commit_completed",
        "post_commit": {
            "needs_user_confirmation": True,
            "confirmation_case_public_ids": [case_public_id],
        },
    })
    projection_calls = []
    original_mark_projected = channel_service.mark_projection_projected

    def mark_projected_after_checkpoint(db, *, team_id, prompt_key):
        assert not any(event.get("event") == FOLLOW_UP_CONFIRMATION_PROMPT_EVENT for event in published_events)
        projection_calls.append(prompt_key)
        return original_mark_projected(db, team_id=team_id, prompt_key=prompt_key)

    channel_service.mark_projection_projected = mark_projected_after_checkpoint

    await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
        },
        context=context,
    )

    prompt_events = [event for event in published_events if event.get("event") == FOLLOW_UP_CONFIRMATION_PROMPT_EVENT]
    assert projection_calls == [
        FollowUpTaskConfirmationChannelService._projection_prompt_key(
            case_public_id=case_public_id,
            interaction_scope="crm_agent:2:3:4:abc",
        )
    ]
    assert len(prompt_events) == 1
    assert prompt_events[0]["interaction"]["payload"]["case_public_id"] == case_public_id


@pytest.mark.asyncio
async def test_projection_revision_skip_suppresses_prompt_without_reclassifying_delivery_failed():
    case_public_id = "fuc_projection_revision_superseded"
    channel_service = FakeFollowUpConfirmationChannelService()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeNewFlowGraphService(),
        confirmation_channel_service=channel_service,
    )
    published_events = []

    async def capture_event(event):
        published_events.append(event)

    context = AgentRuntimeContext(
        db=SimpleNamespace(query=lambda *args, **kwargs: None),
        session=SimpleNamespace(id=4, context_json={}),
        content="查看客户最新进展",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
        event_sink=capture_event,
    )
    context.side_effects.new_flow_events.append({
        "event": "customer_activity_post_commit_completed",
        "post_commit": {
            "needs_user_confirmation": True,
            "confirmation_case_public_ids": [case_public_id],
        },
    })

    def skip_superseded_projection(db_arg, *, team_id, prompt_key):
        return {
            "status": "SKIPPED",
            "reason_code": "SUPERSEDED_ACTIVITY_REVISION",
        }

    channel_service.mark_projection_projected = skip_superseded_projection

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
        },
        context=context,
    )

    assert state.get("current_interrupt") is None
    assert channel_service.failed_projection_calls == []
    assert not any(event.get("event") == FOLLOW_UP_CONFIRMATION_PROMPT_EVENT for event in published_events)
    assert any(
        event.get("event") == "follow_up_task_confirmation_projection_suppressed"
        and event.get("reason_code") == "SUPERSEDED_ACTIVITY_REVISION"
        for event in published_events
    )


@pytest.mark.asyncio
async def test_projection_acknowledgement_failure_is_audited_without_exposing_prompt():
    case_public_id = "fuc_projection_ack_failed"
    channel_service = FakeFollowUpConfirmationChannelService()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeNewFlowGraphService(),
        confirmation_channel_service=channel_service,
    )
    published_events = []

    async def capture_event(event):
        published_events.append(event)

    class RollbackDB:
        def __init__(self):
            self.rollback_calls = 0

        def query(self, *args, **kwargs):
            return None

        def rollback(self):
            self.rollback_calls += 1

    db = RollbackDB()
    context = AgentRuntimeContext(
        db=db,
        session=SimpleNamespace(id=4, context_json={}),
        content="查看客户最新进展",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
        event_sink=capture_event,
    )
    context.side_effects.new_flow_events.append({
        "event": "customer_activity_post_commit_completed",
        "post_commit": {
            "needs_user_confirmation": True,
            "confirmation_case_public_ids": [case_public_id],
        },
    })

    def fail_projection(db_arg, *, team_id, prompt_key):
        raise RuntimeError("checkpoint acknowledgement failed")

    channel_service.mark_projection_projected = fail_projection

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
        },
        context=context,
    )

    prompt_key = FollowUpTaskConfirmationChannelService._projection_prompt_key(
        case_public_id=case_public_id,
        interaction_scope="crm_agent:2:3:4:abc",
    )
    assert state.get("current_interrupt") is None
    assert (
        await runtime.has_pending_interrupt(
            team_id=2,
            user_id=3,
            session_id=4,
            session_key="abc",
        )
        is False
    )
    assert db.rollback_calls == 1
    assert channel_service.failed_projection_calls == [
        {
            "db": db,
            "team_id": 2,
            "prompt_key": prompt_key,
            "error_message": "checkpoint acknowledgement failed",
        }
    ]
    assert not any(event.get("event") == FOLLOW_UP_CONFIRMATION_PROMPT_EVENT for event in published_events)
    assert any(
        event.get("event") == "follow_up_task_confirmation_projection_ack_failed"
        and event.get("prompt_key") == prompt_key
        for event in published_events
    )


@pytest.mark.asyncio
async def test_projection_ack_failure_discards_hidden_interrupt_and_retries_on_next_turn():
    case_public_id = "fuc_projection_retry"
    channel_service = FakeFollowUpConfirmationChannelService()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeNewFlowGraphService(),
        confirmation_channel_service=channel_service,
    )
    published_events = []

    async def capture_event(event):
        published_events.append(event)

    db = SimpleNamespace(query=lambda *args, **kwargs: None, rollback=lambda: None)
    context = AgentRuntimeContext(
        db=db,
        session=SimpleNamespace(id=4, context_json={}),
        content="查看客户最新进展",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
        event_sink=capture_event,
    )
    context.side_effects.new_flow_events.append({
        "event": "customer_activity_post_commit_completed",
        "post_commit": {
            "needs_user_confirmation": True,
            "confirmation_case_public_ids": [case_public_id],
        },
    })
    original_mark_projected = channel_service.mark_projection_projected
    attempts = 0

    def fail_once(db_arg, *, team_id, prompt_key):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("checkpoint acknowledgement failed")
        return original_mark_projected(db_arg, team_id=team_id, prompt_key=prompt_key)

    channel_service.mark_projection_projected = fail_once

    first = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
        },
        context=context,
    )

    assert first.get("current_interrupt") is None
    assert (
        await runtime.has_pending_interrupt(
            team_id=2,
            user_id=3,
            session_id=4,
            session_key="abc",
        )
        is False
    )

    second = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "继续处理客户事项",
            "turn_kind": "text",
        },
        context=context,
    )

    assert attempts == 2
    assert second["current_interrupt"]["reason"] == "follow_up_task_confirmation"
    assert second["current_interrupt"]["interaction"]["payload"]["case_public_id"] == case_public_id
    assert any(event.get("event") == FOLLOW_UP_CONFIRMATION_PROMPT_EVENT for event in published_events)


@pytest.mark.asyncio
async def test_unrecognized_confirmation_reply_is_only_exposed_after_retry_interrupt_is_checkpointed():
    case_public_id = "fuc_clarification_checkpoint_safe"

    class UnresolvedChannelService(FakeFollowUpConfirmationChannelService):
        def resolve_reply_event(self, db, *, team_id, user_id, case_public_id, reply_text):
            self.resolve_calls.append(
                {
                    "db": db,
                    "team_id": team_id,
                    "user_id": user_id,
                    "case_public_id": case_public_id,
                    "reply_text": reply_text,
                }
            )
            return {
                "event": "follow_up_task_confirmation_case_resolved",
                "content": "请直接回复已完成、先放着、不管了，或说明延期时间。",
                "case": {"public_id": case_public_id, "unresolved_reply_count": 1},
                "assistant_follow_up_prompt": "请直接回复已完成、先放着、不管了，或说明延期时间。",
            }

    channel_service = UnresolvedChannelService()
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        confirmation_channel_service=channel_service,
    )
    published_events = []

    async def capture_event(event):
        published_events.append(event)

    context = AgentRuntimeContext(
        db=SimpleNamespace(query=lambda *args, **kwargs: None),
        session=SimpleNamespace(id=4, context_json={}),
        turn_input=AgentTurnInput.text("再看看"),
        content="再看看",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
        event_sink=capture_event,
    )
    initial_event = channel_service.prepare_case_prompt_by_public_ids(
        context.db,
        team_id=2,
        user_id=3,
        case_public_ids=[case_public_id],
        interaction_scope="initial",
    )
    interrupt_payload = {
        "schema_version": "agent.interrupt.v1",
        "interrupt_id": "int_follow_up_confirmation_stable",
        "type": "choice",
        "reason": "follow_up_task_confirmation",
        "business_action": "resolve_follow_up_task_confirmation_case",
        "interaction": initial_event["interaction"],
    }
    await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "abc",
            "channel": "web",
            "content": "记录跟进",
            "turn_kind": "text",
            "current_interrupt": interrupt_payload,
        },
        context=context,
    )
    published_events.clear()

    original_mark_projected = channel_service.mark_projection_projected

    def assert_not_exposed_before_checkpoint(db, *, team_id, prompt_key):
        assert not any(
            event.get("event") == FOLLOW_UP_CONFIRMATION_PROMPT_EVENT or event.get("assistant_follow_up_prompt")
            for event in published_events
        )
        return original_mark_projected(db, team_id=team_id, prompt_key=prompt_key)

    channel_service.mark_projection_projected = assert_not_exposed_before_checkpoint

    result = await runtime.resume_interrupt(
        resume_payload={
            "action": "select",
            "content": "再看看",
            "metadata": {"selected_value": "再看看"},
        },
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="abc",
        context=context,
    )

    retry_interaction = result["current_interrupt"]["interaction"]
    assert retry_interaction["prompt"] == "请直接回复已完成、先放着、不管了，或说明延期时间。"
    assert retry_interaction["payload"]["prompt_delivery_key"] == (
        FollowUpTaskConfirmationChannelService._projection_prompt_key(
            case_public_id=case_public_id,
            interaction_scope="crm_agent:2:3:4:abc:clarification:1",
        )
    )
    prompt_events = [event for event in published_events if event.get("event") == FOLLOW_UP_CONFIRMATION_PROMPT_EVENT]
    assert len(prompt_events) == 1
    assert not any(event.get("event") == "follow_up_task_confirmation_case_resolved" for event in published_events)

@pytest.mark.asyncio
async def test_root_projects_hidden_pending_application_step_before_exposing_business_interrupt(monkeypatch):
    checkpointer = InMemorySaver()
    task = waiting_task_stub()
    task.team_id = 2
    task.user_id = 3
    task.session_id = 4
    task.input_json = {}
    task.state_json = {}
    lookup_calls = []

    def get_task(db, task_id, team_id=None, user_id=None):
        lookup_calls.append({
            "db": db,
            "task_id": task_id,
            "team_id": team_id,
            "user_id": user_id,
        })
        return task

    monkeypatch.setattr(root_runtime_module.agent_task_crud, "get_by_id", get_task)
    interaction = FakeNativeInterruptInteractionGraphService()
    pending_graph = PendingTaskGraphService(
        preflight_graph_service=FakeNativeInterruptPreflightGraphService(),
        interaction_graph_service=interaction,
        checkpointer=checkpointer,
        application_step_protocol=True,
    )
    projector = SequencedPendingApplicationStepProjector([
        PendingApplicationStepProjectionResult(
            status="COMPLETED",
            step_id="ignored-by-fake",
            result={
                "step_type": "preflight",
                "task_snapshot": agent_task_snapshot(task),
                "suspended_task_snapshot": {},
                "result": {
                    "handled": False,
                    "events": [{"event": "pending_interruption_assessed"}],
                    "confirmation_decision": {},
                },
            },
        ),
        completed_interaction_application_step(task),
    ])
    runtime = AgentRootRuntime(
        checkpointer=checkpointer,
        pending_graph_service=pending_graph,
        pending_application_step_projector=projector,
        pending_task_side_effect_handler=FakePendingTaskSideEffectHandler(),
    )
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充金额 10 万"),
        content="补充金额 10 万",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "application-step-root",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )

    assert len(projector.calls) == 2
    preflight_step = projector.calls[0].step
    interaction_step = projector.calls[1].step
    assert preflight_step["internal"] is True
    assert preflight_step["step_type"] == "preflight"
    assert interaction_step["internal"] is True
    assert interaction_step["step_type"] == "interaction"
    assert preflight_step["step_id"] != interaction_step["step_id"]
    assert preflight_step["checkpoint_ref"]["checkpoint_ns"].startswith("pending_task_subgraph:")
    assert interaction_step["checkpoint_ref"] == preflight_step["checkpoint_ref"]
    assert lookup_calls == [
        {
            "db": context.db,
            "task_id": 101,
            "team_id": 2,
            "user_id": 3,
        },
        {
            "db": context.db,
            "task_id": 101,
            "team_id": 2,
            "user_id": 3,
        },
    ]
    assert state["current_interrupt"]["reason"] == "write_confirmation"
    assert state["current_interrupt"].get("internal") is not True
    assert state["runtime_status"] == "pending_projection_projected"


@pytest.mark.asyncio
async def test_root_retries_hidden_application_step_before_accepting_new_turn(monkeypatch):
    checkpointer = InMemorySaver()
    task = waiting_task_stub()
    task.team_id = 2
    task.user_id = 3
    task.session_id = 4
    task.input_json = {}
    task.state_json = {}
    monkeypatch.setattr(
        root_runtime_module.agent_task_crud,
        "get_by_id",
        lambda db, task_id, team_id=None, user_id=None: task,
    )
    pending_graph = PendingTaskGraphService(
        preflight_graph_service=FakeNativeInterruptPreflightGraphService(),
        interaction_graph_service=FakeNativeInterruptInteractionGraphService(),
        checkpointer=checkpointer,
        application_step_protocol=True,
    )
    projector = SequencedPendingApplicationStepProjector([
        PendingApplicationStepProjectionResult(
            status="IN_PROGRESS",
            step_id="busy",
            busy=True,
            retryable=True,
            failure_reason="application_step_lease_busy",
        ),
        PendingApplicationStepProjectionResult(
            status="COMPLETED",
            step_id="completed",
            result={
                "step_type": "preflight",
                "task_snapshot": agent_task_snapshot(task),
                "suspended_task_snapshot": {},
                "result": {
                    "handled": False,
                    "events": [{"event": "pending_interruption_assessed"}],
                    "confirmation_decision": {},
                },
            },
        ),
        completed_interaction_application_step(task),
    ])
    new_flow = FakeNewFlowGraphService()
    runtime = AgentRootRuntime(
        checkpointer=checkpointer,
        pending_graph_service=pending_graph,
        pending_application_step_projector=projector,
        new_flow_graph_service=new_flow,
        pending_task_side_effect_handler=FakePendingTaskSideEffectHandler(),
    )
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充金额 10 万"),
        content="补充金额 10 万",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )

    first = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "application-step-retry",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )
    assert first["runtime_status"] == "pending_application_step_in_progress"
    assert first.get("current_interrupt") is None

    context.turn_input = AgentTurnInput.text("这条新输入不能被消费")
    context.content = "这条新输入不能被消费"
    second = await runtime.run_turn(
        turn_input=context.turn_input,
        content=context.content,
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="application-step-retry",
        current_customer={},
        context=context,
    )

    assert len(projector.calls) == 3
    assert projector.calls[0].step["step_id"] == projector.calls[1].step["step_id"]
    assert projector.calls[2].step["step_type"] == "interaction"
    assert projector.calls[2].step["content"] == "补充金额 10 万"
    assert second["current_interrupt"]["reason"] == "write_confirmation"
    assert new_flow.calls == []


@pytest.mark.asyncio
async def test_terminal_pending_application_step_failure_uses_root_projection_failure_branch(monkeypatch):
    checkpointer = InMemorySaver()
    task = waiting_task_stub()
    task.team_id = 2
    task.user_id = 3
    task.session_id = 4
    task.input_json = {}
    task.state_json = {}
    monkeypatch.setattr(
        root_runtime_module.agent_task_crud,
        "get_by_id",
        lambda db, task_id, team_id=None, user_id=None: task,
    )
    pending_graph = PendingTaskGraphService(
        checkpointer=checkpointer,
        application_step_protocol=True,
    )

    class TerminalFailingProjector:
        def __init__(self):
            self.calls = []

        async def project(self, request):
            self.calls.append(request)
            return PendingApplicationStepProjectionResult(
                status="FAILED",
                step_id=request.step["step_id"],
                retryable=False,
                failure_reason="application_step_validation_failed",
            )

    projector = TerminalFailingProjector()
    runtime = AgentRootRuntime(
        checkpointer=checkpointer,
        pending_graph_service=pending_graph,
        pending_application_step_projector=projector,
        pending_task_side_effect_handler=FakePendingTaskSideEffectHandler(),
    )
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充金额 10 万"),
        content="补充金额 10 万",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "terminal-application-step-failure",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )

    step = projector.calls[0].step
    assert state["runtime_status"] == "pending_projection_failed"
    assert state["runtime_retryable"] is False
    assert state["current_interrupt"] is None
    assert state["pending_task_continuation_ref"] is None
    assert state["pending_task_result"]["failure_reason"] == "application_step_validation_failed"
    assert len([
        event
        for event in context.side_effects.pending_task_events
        if event.get("event") == "pending_application_step_failed"
    ]) == 1
    recovery = await pending_graph.load_checkpointed_outcome(
        step["checkpoint_ref"],
        expected_interrupt=step,
    )
    assert recovery.failure_reason is None
    assert recovery.outcome is not None
    assert recovery.outcome["current_interrupt"] == step
    history = await runtime.state_history(
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="terminal-application-step-failure",
        limit=30,
    )
    assert any("pending_projection_failure" in item["next_nodes"] for item in history)
    assert any("finish_turn" in item["next_nodes"] for item in history)


@pytest.mark.asyncio
async def test_invalid_pending_application_step_continuation_fails_in_root_projection_branch(monkeypatch):
    checkpointer = InMemorySaver()
    task = waiting_task_stub()
    task.team_id = 2
    task.user_id = 3
    task.session_id = 4
    task.input_json = {}
    task.state_json = {}
    original_builder = pending_graph_module.build_pending_application_step_request

    def build_request_with_invalid_continuation(**kwargs):
        request = original_builder(**kwargs)
        request["checkpoint_ref"] = {
            **request["checkpoint_ref"],
            "team_id": 999,
        }
        request["step_id"] = pending_application_step_id(request)
        return request

    monkeypatch.setattr(
        pending_graph_module,
        "build_pending_application_step_request",
        build_request_with_invalid_continuation,
    )
    pending_graph = PendingTaskGraphService(
        checkpointer=checkpointer,
        application_step_protocol=True,
    )
    runtime = AgentRootRuntime(
        checkpointer=checkpointer,
        pending_graph_service=pending_graph,
        pending_task_side_effect_handler=FakePendingTaskSideEffectHandler(),
    )
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充金额 10 万"),
        content="补充金额 10 万",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )

    state = await runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "invalid-application-step-continuation",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )

    continuation = context.side_effects.pending_task_graph_side_effects.checkpoint_ref
    assert state["runtime_status"] == "pending_projection_failed"
    assert state["runtime_retryable"] is False
    assert state["current_interrupt"] is None
    assert state["pending_task_continuation_ref"] is None
    assert state["pending_task_result"]["failure_reason"] == "invalid_continuation"
    assert len([
        event
        for event in context.side_effects.pending_task_events
        if event.get("event") == "pending_application_step_failed"
    ]) == 1
    recovery = await pending_graph.load_checkpointed_outcome(continuation)
    assert recovery.failure_reason is None
    assert recovery.outcome is not None
    assert recovery.outcome["current_interrupt"]["reason"] == "pending_task_application_step"

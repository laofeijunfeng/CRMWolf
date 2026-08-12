"""Tests for the LangGraph-native CRM Agent root runtime."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.services.agent import action_plan, action_workflow, agent_copy
from app.services.agent import root_runtime as root_runtime_module
from app.services.agent.input import AgentTurnInput
from app.services.agent.root_runtime import (
    AgentRootRuntime,
    build_agent_thread_id,
    project_turn_output,
)
from app.services.agent.schemas import AgentConfirmationIntentDecision
from app.services.agent.state import AgentRootRuntimeSideEffects, AgentRuntimeContext
from app.services.agent.task_execution import ActionToolExecutionResult
from app.services.agent.tools.base import AgentToolResult
from app.services.customer_intelligence_refresh_service import AgentAsyncOperationBinding
from app.services.follow_up_task_confirmation_channel_service import (
    FOLLOW_UP_CONFIRMATION_PROMPT_EVENT,
    FollowUpTaskConfirmationChannelService,
)


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
            "task_projection": {
                "id": state["task"].id,
                "task_key": state["task"].task_key,
                "status": state["task"].status,
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
async def test_root_runtime_schedules_customer_intelligence_after_confirmed_activity_write():
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
    db = object()

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
            db=db,
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
    assert len(customer_intelligence_refresh_service.trigger_calls) == 1
    trigger_call = customer_intelligence_refresh_service.trigger_calls[0]
    assert trigger_call["db"] is db
    assert trigger_call["event"] is customer_intelligence_event
    assert trigger_call["scope"] == "brief"
    assert trigger_call["agent_binding"] == AgentAsyncOperationBinding(
        team_id=2,
        user_id=3,
        session_id=4,
        source_user_message_id=91,
    )
    assert state["customer_intelligence_result"] == {
        "handled": True,
        "mode": "background",
        "scheduled": True,
        "trigger_type": "customer_activity_created",
        "event_key": "activity-created-1",
        "customer_id": 101,
        "request_id": "business-event-customer_activity_created-test",
        "operation_public_id": "aop_customer_intelligence_test",
        "source_user_message_id": 91,
        "scope": "brief",
    }
    assert side_effects.confirmed_task_assistant_content == "跟进记录已创建。"
    assert side_effects.customer_intelligence_events == [
        {
            "event": "agent_root_customer_intelligence_refresh_scheduled",
            "mode": "background",
            "trigger_type": "customer_activity_created",
            "event_key": "activity-created-1",
            "customer_id": 101,
            "scheduled": True,
            "request_id": "business-event-customer_activity_created-test",
            "operation_public_id": "aop_customer_intelligence_test",
            "source_user_message_id": 91,
        }
    ]


@pytest.mark.asyncio
async def test_root_runtime_reports_committed_refresh_schedule_failure_instead_of_success():
    customer_intelligence_event = SimpleNamespace(
        event_key="activity-created-failed",
        trigger_type="customer_activity_created",
        customer_id=101,
    )
    refresh_service = FakeFailedCustomerIntelligenceRefreshService()
    side_effects = AgentRootRuntimeSideEffects()
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
            side_effects=side_effects,
        ),
    )

    assert state["customer_intelligence_result"] == {
        "handled": False,
        "mode": "background",
        "scheduled": False,
        "trigger_type": "customer_activity_created",
        "event_key": "activity-created-failed",
        "customer_id": 101,
        "request_id": "business-event-customer_activity_created-failed",
        "scope": "brief",
        "reason": "background_refresh_schedule_failed",
        "schedule_error": "operation projection unavailable",
    }
    assert side_effects.customer_intelligence_events == [
        {
            "event": "agent_root_customer_intelligence_refresh_schedule_failed",
            "mode": "background",
            "trigger_type": "customer_activity_created",
            "event_key": "activity-created-failed",
            "customer_id": 101,
            "scheduled": False,
            "request_id": "business-event-customer_activity_created-failed",
            "reason": "operation projection unavailable",
        }
    ]


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
                "type": "confirm",
                "task_projection_id": 900,
            },
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

    def is_case_pending_for_owner(self, db, *, team_id, user_id, case_public_id):
        self.pending_checks.append(
            {
                "db": db,
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
async def test_root_runtime_projects_async_owner_inbox_case_on_later_active_turn():
    case_public_id = "fuc_async_page_created"
    channel_service = FakeFollowUpConfirmationChannelService()
    channel_service.pending_case_public_ids = [case_public_id]
    runtime = AgentRootRuntime(
        checkpointer=InMemorySaver(),
        new_flow_graph_service=FakeNewFlowGraphService(),
        confirmation_channel_service=channel_service,
    )
    side_effects = AgentRootRuntimeSideEffects()
    context = AgentRuntimeContext(
        db=SimpleNamespace(query=lambda *args, **kwargs: None),
        session=SimpleNamespace(id=4, context_json={}),
        content="查看客户最新进展",
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

    assert state["current_interrupt"]["reason"] == "follow_up_task_confirmation"
    assert state["current_interrupt"]["interaction"]["payload"]["case_public_id"] == case_public_id
    assert channel_service.prepare_calls[0]["case_public_ids"] == []
    assert channel_service.prepare_calls[1]["case_public_ids"] == [case_public_id]
    assert channel_service.list_calls[0]["limit"] == 1
    assert [event for event in side_effects.new_flow_events if event.get("event") == "final"] == []
    assert side_effects.business_interaction_assistant_content == "上次安排的任务这次是否已经完成?"


@pytest.mark.asyncio
async def test_root_runtime_reconciles_next_owner_inbox_case_after_first_resolution():
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
        db=SimpleNamespace(query=lambda *args, **kwargs: None),
        session=SimpleNamespace(id=4, context_json={}),
        content="查看客户最新进展",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )

    first_state = await runtime.checkpoint_turn_start(
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
    assert first_state["current_interrupt"]["interaction"]["payload"]["case_public_id"] == first_case

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

    assert resumed["current_interrupt"]["reason"] == "follow_up_task_confirmation"
    assert resumed["current_interrupt"]["interaction"]["payload"]["case_public_id"] == second_case
    assert [call["case_public_ids"] for call in channel_service.prepare_calls][-1] == [second_case]


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
    channel_service.pending_case_public_ids = [case_public_id]
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
    channel_service.pending_case_public_ids = [case_public_id]

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
    channel_service.pending_case_public_ids = [case_public_id]
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

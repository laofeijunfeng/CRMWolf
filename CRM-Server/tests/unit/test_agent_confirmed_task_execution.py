from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.agent import AgentSession, AgentTask, AgentTaskStatus, AgentWorkflowAction
from app.services.agent import action_workflow, interactions
from app.services.agent.action_plan import ActionPlanNode
from app.services.agent.confirmed_task_graph import execute_confirmed_task
from app.services.agent.guardrails import AgentToolExecutionPolicy, AgentToolGuardrailError, agent_tool_guardrails
from app.services.agent.task_actions import _tool_payload_for_action
from app.services.agent.task_execution import (
    ActionExecutionEnvelope,
    WaitingTaskExecutionResult,
    _execute_opportunity_stage_move_plan,
    _execute_waiting_task,
    action_execution_blocking_reason,
    execute_action_envelope,
    execution_envelope_from_plan_node,
)
from app.services.agent.tools.base import AgentToolContext, AgentToolResult


@compiles(BigInteger, "sqlite")
def _confirmed_task_bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"




@pytest.mark.asyncio
async def test_confirmed_task_graph_execute_node_returns_completed_task_result(monkeypatch):
    db = object()
    session = SimpleNamespace(id=3)
    task = SimpleNamespace(
        id=11,
        state_json={"action": "create_customer_activity"},
    )
    next_task = SimpleNamespace(id=12, state_json={"action": "collect_opportunity_fields"})

    async def fake_execute_waiting_task(db_arg, task_arg, *, session, team_id, user_id, authorization, event_sink):
        assert db_arg is db
        assert task_arg is task
        assert session.id == 3
        assert team_id == 1
        assert user_id == 2
        assert authorization == "Bearer test"
        assert event_sink is None
        return WaitingTaskExecutionResult(
            AgentToolResult(
                tool_name="create_customer_activity",
                success=True,
                data={"id": 101},
                tool_call_id=501,
            ),
            "跟进记录已创建。请确认是否执行下一步动作？",
            next_task,
        )

    monkeypatch.setattr(
        "app.services.agent.confirmed_task_graph.task_execution._execute_waiting_task",
        fake_execute_waiting_task,
    )
    result = await execute_confirmed_task(
        db,
        task,
        session=session,
        team_id=1,
        user_id=2,
        authorization="Bearer test",
    )

    assert result.tool_event
    assert result.tool_event["event"] == "tool_result"
    assert result.tool_event["tool_name"] == "create_customer_activity"
    assert result.tool_event["success"] is True
    assert result.tool_event["data"] == {"id": 101}
    assert result.tool_event["tool_call_id"] == 501
    assert result.task_event == {
        "event": "task_completed",
        "task_id": 11,
        "content": "跟进记录已创建。请确认是否执行下一步动作？",
    }
    assert result.next_task is next_task


@pytest.mark.asyncio
async def test_confirmed_task_graph_execute_node_returns_failed_task_event(monkeypatch):
    db = object()
    session = SimpleNamespace(id=3)
    task = SimpleNamespace(id=11, state_json={"action": "unsupported"})

    async def fake_execute_waiting_task(*args, **kwargs):
        return WaitingTaskExecutionResult(None, "执行失败：暂不支持的执行动作：unsupported")

    monkeypatch.setattr(
        "app.services.agent.confirmed_task_graph.task_execution._execute_waiting_task",
        fake_execute_waiting_task,
    )
    result = await execute_confirmed_task(
        db,
        task,
        session=session,
        team_id=1,
        user_id=2,
        authorization="Bearer test",
    )

    assert result.tool_event is None
    assert result.task_event == {
        "event": "task_failed",
        "task_id": 11,
        "content": "执行失败：暂不支持的执行动作：unsupported",
    }


def test_next_opportunity_field_task_uses_form_interaction():
    task = SimpleNamespace(
        id=12,
        task_key="task_12",
        state_json={
            "action": "collect_opportunity_fields",
            "customer": {"id": 101, "account_name": "广州睿狐科技有限公司"},
            "payload": {
                "customer_id": 101,
                "missing_fields": ["total_amount", "license_type", "subscription_years", "procurement_method_id"],
                "interaction_fields": ["total_amount", "license_type", "subscription_years", "procurement_method_id"],
                "field_defaults": {},
            },
        },
    )

    interaction = interactions._pending_task_interaction(
        task,
        "好嘞，跟进已记录。这条还像「新增授权」商机，还差：预计成交金额、授权模式、订阅年限、采购方式。",
    )

    assert interaction["type"] == "form"
    assert interaction["status"] == "waiting_user_input"
    assert interaction["business_action"] == "create_opportunity"
    assert interaction["task_id"] == 12
    assert interaction["task_key"] == "task_12"


@pytest.mark.asyncio
async def test_stage_move_plan_executes_steps_in_order():
    class FakeRuntime:
        def __init__(self):
            self.calls = []

        async def execute(self, tool_name, context, payload, policy):
            self.calls.append((tool_name, payload, policy.allowed_tool_names))
            return AgentToolResult(
                tool_name=tool_name,
                success=True,
                data={
                    "id": payload["opportunity_id"],
                    "current_stage_snapshot": {
                        "procurement_stage_template_id": payload["stage_template_id"],
                        "stage_name": "签约" if payload["stage_template_id"] == 10 else "方案确认",
                    },
                },
                tool_call_id=500 + len(self.calls),
            )

    runtime = FakeRuntime()
    progress_events = []
    context = AgentToolContext(
        db=object(),
        team_id=1,
        user_id=2,
        session_id=3,
        authorization="Bearer test",
        confirmed_by_user=True,
    )

    result = await _execute_opportunity_stage_move_plan(
        runtime,
        context,
        {
            "customer_id": 101,
            "opportunity_id": 301,
            "stage_template_id": 10,
            "target_stage_name": "签约",
            "stage_move_steps": [
                {"stage_template_id": 9, "stage_name": "方案确认"},
                {"stage_template_id": 10, "stage_name": "签约"},
            ],
        },
        "task_11",
        progress_events=progress_events,
        event_sink=None,
    )

    assert result.success is True
    assert [call[1]["stage_template_id"] for call in runtime.calls] == [9, 10]
    assert [call[1]["idempotency_suffix"] for call in runtime.calls] == ["task_11:stage:1", "task_11:stage:2"]
    assert result.data["current_stage_snapshot"]["stage_name"] == "签约"
    assert result.data["stage_move_steps"] == [
        {"stage_template_id": 9, "stage_name": "方案确认", "tool_call_id": 501},
        {"stage_template_id": 10, "stage_name": "签约", "tool_call_id": 502},
    ]
    assert progress_events == [
        {"event": "agent_step", "step": "opportunity_stage_move_1", "status": "started", "content": "推进到「方案确认」"},
        {"event": "agent_step", "step": "opportunity_stage_move_1", "status": "completed", "content": "推进到「方案确认」"},
        {"event": "agent_step", "step": "opportunity_stage_move_2", "status": "started", "content": "推进到「签约」"},
        {"event": "agent_step", "step": "opportunity_stage_move_2", "status": "completed", "content": "推进到「签约」"},
    ]


@pytest.mark.asyncio
async def test_stage_move_plan_streams_each_stage_step():
    class FakeRuntime:
        async def execute(self, tool_name, context, payload, policy):
            return AgentToolResult(
                tool_name=tool_name,
                success=True,
                data={"current_stage_snapshot": {"stage_name": "产品试用"}},
            )

    streamed_events = []

    async def event_sink(event):
        streamed_events.append(event)

    progress_events = []
    context = AgentToolContext(
        db=object(),
        team_id=1,
        user_id=2,
        session_id=3,
        authorization="Bearer test",
        confirmed_by_user=True,
    )

    await _execute_opportunity_stage_move_plan(
        FakeRuntime(),
        context,
        {
            "customer_id": 101,
            "opportunity_id": 301,
            "stage_move_steps": [
                {"stage_template_id": 9, "stage_name": "方案交流"},
                {"stage_template_id": 10, "stage_name": "产品试用"},
            ],
        },
        "task_11",
        progress_events=progress_events,
        event_sink=event_sink,
    )

    assert streamed_events == progress_events
    assert [event["content"] for event in streamed_events] == [
        "推进到「方案交流」",
        "推进到「方案交流」",
        "推进到「产品试用」",
        "推进到「产品试用」",
    ]


@pytest.mark.asyncio
async def test_execute_action_envelope_uses_action_payload_without_task_projection(monkeypatch):
    calls = []

    class FakeRuntime:
        def __init__(self, registry):
            self.registry = registry

        async def execute(self, tool_name, context, payload, policy):
            calls.append((tool_name, context, payload, policy))
            return AgentToolResult(
                tool_name=tool_name,
                success=True,
                data={"id": 501},
                tool_call_id=7001,
            )

    monkeypatch.setattr("app.services.agent.task_execution.AgentToolRuntime", FakeRuntime)

    workflow = action_workflow.mark_auto_executable(
        action_workflow.required_write_contract(action="create_customer_activity"),
        reason="low_risk_high_confidence",
        source="action_review",
    )

    result = await execute_action_envelope(
        object(),
        ActionExecutionEnvelope(
            action_id=workflow["action_id"],
            action_type="create_customer_activity",
            workflow=workflow,
            payload={
                "customer_id": 101,
                "source_content": "今天和华米科技沟通了评估结论",
                "next_follow_time_iso": "2026-08-13T09:00:00",
            },
            customer={"id": 101, "account_name": "华米（北京）信息科技有限公司"},
            task_key=workflow["action_id"],
        ),
        session=SimpleNamespace(id=3),
        team_id=1,
        user_id=2,
        authorization="Bearer test",
    )

    assert result.tool_result.success is True
    assert calls[0][0] == "create_customer_activity"
    assert calls[0][1].task_id is None
    assert calls[0][1].confirmed_by_user is False
    assert calls[0][1].auto_execute_authorized is True
    assert calls[0][1].execution_policy == action_workflow.EXECUTION_AUTO_EXECUTE
    assert calls[0][1].authorization_source == "semantic_auto_execute_low_risk"
    assert calls[0][1].workflow_id == workflow["workflow_id"]
    assert calls[0][1].action_id == workflow["action_id"]
    assert calls[0][1].allowed_customer_ids == ["101"]
    assert calls[0][3].hitl_decision is None
    assert calls[0][3].auto_execute_authorized is True
    assert calls[0][2] == {
        "customer_id": 101,
        "customer_name": "华米（北京）信息科技有限公司",
        "activity_kind": "OTHER_FOLLOW_UP",
        "source_content": "今天和华米科技沟通了评估结论",
        "title": None,
        "next_action": None,
        "next_follow_time": "2026-08-13T09:00:00",
        "idempotency_suffix": workflow["action_id"],
    }


def test_guardrail_allows_auto_execute_write_with_action_workflow_authorization():
    context = AgentToolContext(
        db=object(),
        team_id=1,
        user_id=2,
        session_id=3,
        authorization="Bearer test",
        workflow_id="wf_123",
        action_id="act_123",
        execution_policy=action_workflow.EXECUTION_AUTO_EXECUTE,
        authorization_source="semantic_auto_execute_low_risk",
        auto_execute_authorized=True,
        allowed_tool_names=["create_customer_activity"],
        allowed_customer_ids=["101"],
    )

    agent_tool_guardrails.validate_before_execute(
        tool_name="create_customer_activity",
        is_write=True,
        requires_confirmation=True,
        context=context,
        payload={"customer_id": 101},
        policy=AgentToolExecutionPolicy(
            execution_policy=action_workflow.EXECUTION_AUTO_EXECUTE,
            workflow_id="wf_123",
            action_id="act_123",
            authorization_source="semantic_auto_execute_low_risk",
            auto_execute_authorized=True,
            allowed_tool_names=["create_customer_activity"],
            allowed_customer_ids=["101"],
        ),
    )


def test_guardrail_blocks_direct_write_without_hitl_or_auto_execute_authorization():
    context = AgentToolContext(
        db=object(),
        team_id=1,
        user_id=2,
        session_id=3,
        authorization="Bearer test",
        allowed_tool_names=["create_customer_activity"],
        allowed_customer_ids=["101"],
    )

    with pytest.raises(AgentToolGuardrailError):
        agent_tool_guardrails.validate_before_execute(
            tool_name="create_customer_activity",
            is_write=True,
            requires_confirmation=True,
            context=context,
            payload={"customer_id": 101},
            policy=AgentToolExecutionPolicy(
                allowed_tool_names=["create_customer_activity"],
                allowed_customer_ids=["101"],
            ),
        )


def test_execution_envelope_from_plan_node_prefers_action_payload_over_task_state():
    workflow = action_workflow.required_write_contract(action="create_customer_activity")
    task = SimpleNamespace(
        id=11,
        task_key="task_11",
        session_id=3,
        state_json={
            "action": "create_customer_activity",
            "payload": {"customer_id": 999, "source_content": "旧任务投影"},
            "customer": {"id": 999, "account_name": "旧客户"},
            "workflow": workflow,
        },
    )
    node = ActionPlanNode(
        action_id=workflow["action_id"],
        action_type="create_customer_activity",
        workflow=workflow,
        payload={"customer_id": 101, "source_content": "Action Envelope payload"},
        task=task,
        task_id=11,
        target_type="customer",
        target_id=101,
    )

    envelope = execution_envelope_from_plan_node(node)

    assert envelope.payload == {"customer_id": 101, "source_content": "Action Envelope payload"}
    assert envelope.customer == {"id": 999, "account_name": "旧客户"}
    assert envelope.task_key == "task_11"
    assert envelope.target_id == 101


def test_write_action_tool_payloads_include_explicit_idempotency_suffix():
    customer = {"id": 101, "account_name": "华米（北京）信息科技有限公司"}
    cases = [
        (
            "create_contact",
            {"customer_id": 101, "contact": {"name": "张三"}},
        ),
        (
            "create_invoice_title",
            {"customer_id": 101, "invoice_title": {"company_name": "华米科技"}},
        ),
        (
            "create_deployment_info",
            {"customer_id": 101, "deployment_info": {"deployment_method": "私有化"}},
        ),
        (
            "create_customer_member",
            {"customer_id": 101, "member": {"user_id": 2, "role": "owner"}},
        ),
    ]

    for action, payload in cases:
        tool_payload = _tool_payload_for_action(action, payload, customer, "act_write")
        assert tool_payload["idempotency_suffix"] == "act_write"


def test_action_execution_contract_validates_tool_schema_after_action_mapping():
    envelope = ActionExecutionEnvelope(
        action_id="act_contact",
        action_type="create_contact",
        payload={
            "customer_id": 101,
            "contact": {
                "name": "吕桂梅",
                "mobile": "13800000000",
            },
        },
        customer={"id": 101, "account_name": "矽递科技"},
        task_key="act_contact",
    )

    reason = action_execution_blocking_reason(envelope)

    assert reason
    assert reason.startswith("invalid_tool_payload:")
    assert "contact.position" in reason


def test_action_execution_contract_allows_customer_context_to_supply_activity_customer_id():
    envelope = ActionExecutionEnvelope(
        action_id="act_activity",
        action_type="create_customer_activity",
        payload={
            "source_content": "今天和华米科技沟通了评估结论",
        },
        customer={"id": 101, "account_name": "华米（北京）信息科技有限公司"},
        task_key="act_activity",
    )

    assert action_execution_blocking_reason(envelope) is None


@pytest.mark.asyncio
async def test_execute_action_envelope_blocks_write_without_explicit_idempotency_key(monkeypatch):
    calls = []

    class FakeRuntime:
        def __init__(self, registry):
            self.registry = registry

        async def execute(self, tool_name, context, payload, policy):
            calls.append((tool_name, payload))
            return AgentToolResult(tool_name=tool_name, success=True)

    monkeypatch.setattr("app.services.agent.task_execution.AgentToolRuntime", FakeRuntime)
    envelope = ActionExecutionEnvelope(
        action_id="",
        action_type="create_customer_activity",
        payload={"customer_id": 101, "source_content": "跟进记录"},
        customer={"id": 101},
        task_key="",
    )

    assert action_execution_blocking_reason(envelope) == "missing_idempotency_key"
    result = await execute_action_envelope(
        object(),
        envelope,
        session=SimpleNamespace(id=3),
        team_id=1,
        user_id=2,
        authorization="Bearer test",
    )

    assert calls == []
    assert result.tool_result.success is False
    assert result.tool_result.error_message == "missing_idempotency_key"
    assert result.tool_result.status_code == 409


@pytest.mark.asyncio
async def test_execute_waiting_task_marks_workflow_action_failed_when_tool_fails(monkeypatch):
    workflow = action_workflow.required_write_contract(action="create_customer_activity")
    task = SimpleNamespace(
        id=11,
        task_key="task_11",
        session_id=3,
        state_json={
            "action": "create_customer_activity",
            "payload": {"customer_id": 101, "source_content": "跟进记录"},
            "customer": {"id": 101, "account_name": "华米（北京）信息科技有限公司"},
            "workflow": workflow,
        },
    )
    updates = []
    failures = []

    def fake_update(db, task_arg, update):
        updates.append(update.status)
        return task_arg

    class FakeRuntime:
        def __init__(self, registry):
            self.registry = registry

        async def execute(self, tool_name, context, payload, policy):
            return AgentToolResult(
                tool_name=tool_name,
                success=False,
                error_message="API 写入失败",
            )

    def fake_mark_action_failed(db, **kwargs):
        failures.append(kwargs)

    monkeypatch.setattr("app.services.agent.task_execution.agent_task_crud.update", fake_update)
    monkeypatch.setattr("app.services.agent.task_execution.AgentToolRuntime", FakeRuntime)
    monkeypatch.setattr("app.services.agent.task_execution.workflow_action_ledger.mark_action_failed", fake_mark_action_failed)

    result = await _execute_waiting_task(
        object(),
        task,
        session=SimpleNamespace(id=3),
        team_id=1,
        user_id=2,
        authorization="Bearer test",
    )

    assert result.assistant_content == "执行失败：API 写入失败"
    assert updates == ["RUNNING", "FAILED"]
    assert failures[0]["workflow"] == workflow
    assert failures[0]["task_id"] == 11
    assert failures[0]["error_message"] == "API 写入失败"


@pytest.mark.asyncio
async def test_confirmed_payment_plan_replay_projects_one_stable_next_task(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AgentSession.__table__,
            AgentTask.__table__,
            AgentWorkflowAction.__table__,
        ],
    )
    db = sessionmaker(bind=engine)()
    workflow = action_workflow.required_write_contract(action="create_payment_plan")
    db.add(AgentSession(
        id=3,
        session_key="confirmed_payment_plan_replay",
        team_id=1,
        user_id=2,
        title="Confirmed payment plan replay",
        context_json={},
    ))
    db.add(AgentTask(
        id=11,
        task_key="task_confirmed_payment_plan",
        team_id=1,
        user_id=2,
        session_id=3,
        intent="PAYMENT_PLAN",
        status=AgentTaskStatus.WAITING_USER,
        target_type="customer",
        target_id=101,
        summary="创建回款计划",
        input_json={"contract_id": 501},
        state_json={
            "action": "create_payment_plan",
            "workflow": workflow,
            "customer": {"id": 101, "account_name": "示例客户"},
            "payload": {
                "contract_id": 501,
                "stage_name": "首付款",
                "planned_amount": 1000,
                "due_date": "2026-08-20",
                "pending_payment_record": {
                    "actual_amount": 1000,
                    "payment_date": "2026-08-14",
                    "commission_member_id": "usr_2",
                },
            },
        },
    ))
    db.commit()

    class ReplayRuntime:
        def __init__(self, registry):
            self.registry = registry

        async def execute(self, tool_name, context, payload, policy):
            assert tool_name == "create_payment_plan"
            return AgentToolResult(
                tool_name=tool_name,
                success=True,
                data={"items": [{"id": 9001}]},
                idempotent_replay=True,
            )

    monkeypatch.setattr("app.services.agent.task_execution.AgentToolRuntime", ReplayRuntime)
    monkeypatch.setattr("app.services.agent.task_execution._task_target_id", lambda *args, **kwargs: 101)

    try:
        task = db.get(AgentTask, 11)
        first = await execute_confirmed_task(
            db,
            task,
            session=db.get(AgentSession, 3),
            team_id=1,
            user_id=2,
            authorization="Bearer test",
        )
        replay = await execute_confirmed_task(
            db,
            db.get(AgentTask, 11),
            session=db.get(AgentSession, 3),
            team_id=1,
            user_id=2,
            authorization="Bearer test",
        )

        assert first.next_task.id == replay.next_task.id
        child_tasks = db.query(AgentTask).filter(AgentTask.id != 11).all()
        assert len(child_tasks) == 1
        child_actions = db.query(AgentWorkflowAction).all()
        assert len(child_actions) == 1
        assert child_actions[0].task_id == child_tasks[0].id
        assert child_actions[0].parent_action_id == workflow["action_id"]
    finally:
        db.close()
        engine.dispose()

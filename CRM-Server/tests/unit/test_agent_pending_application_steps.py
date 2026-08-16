"""Application-module tests for durable PendingTask application steps."""

# User-facing Chinese copy intentionally uses full-width punctuation.
# ruff: noqa: RUF001

import json
from types import SimpleNamespace

import pytest

from app.models.agent import AgentTaskStatus
from app.services.agent import pending_application_modules as application_modules
from app.services.agent.input import AgentTurnInput
from app.services.agent.pending_application_step_projection import PendingApplicationStepExecutionRequest
from app.services.agent.pending_application_steps import DefaultPendingApplicationStepExecutor
from app.services.agent.schemas import (
    AgentConfirmationIntentDecision,
    AgentPendingInterruptionDecision,
    AgentTurnRelationDecision,
)
from app.services.agent.task_projection import agent_task_snapshot


class FakeInteractionApplicationModule:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def execute(self, request):
        self.calls.append(request)
        return self.result


def _task(*, action: str = "create_customer_activity", status: str = AgentTaskStatus.WAITING_USER):
    return SimpleNamespace(
        id=101,
        task_key="task-101",
        team_id=1,
        user_id=2,
        session_id=3,
        status=status,
        intent="CREATE_OPPORTUNITY",
        target_type="customer",
        target_id=7,
        summary="等待确认创建商机",
        input_json={"customer_id": 7},
        state_json={"action": action},
        result_json={},
        error_message=None,
    )


def _request(task, *, step_type: str, content: str, metadata=None):
    turn_input = AgentTurnInput.text(content, metadata=metadata)
    return PendingApplicationStepExecutionRequest(
        db=object(),
        session=SimpleNamespace(id=3, context_json={}),
        task=task,
        team_id=1,
        user_id=2,
        session_id=3,
        authorization="Bearer test",
        step={
            "schema_version": "agent.pending_application_step.v1",
            "type": "confirm",
            "reason": "pending_task_application_step",
            "internal": True,
            "source_event": "pending_task_application_step_requested",
            "business_action": "execute_pending_application_step",
            "step_id": f"step-{step_type}",
            "step_type": step_type,
            "checkpoint_ref": {},
            "task_snapshot": agent_task_snapshot(task),
            "content": content,
            "turn_input": turn_input.model_dump(mode="json"),
            "interaction_metadata": metadata or {},
            "effect_intents": [],
        },
    )


def _assert_checkpoint_safe(value):
    assert json.loads(json.dumps(value, ensure_ascii=False)) == value


@pytest.mark.asyncio
async def test_interaction_application_step_returns_checkpoint_safe_business_interrupt():
    task = _task()
    module = FakeInteractionApplicationModule(SimpleNamespace(
        handled=True,
        assistant_content="请确认是否创建商机？",
        selected_customer=None,
        remember_pending_task=True,
        clear_pending_task_id=None,
        events=[{
            "event": "confirmation_required",
            "task_id": 101,
            "action": "create_opportunity",
            "payload": {"customer_id": 7},
            "content": "请确认是否创建商机？",
        }, {"event": "final", "content": "请确认是否创建商机？"}],
    ))
    executor = DefaultPendingApplicationStepExecutor(interaction_module=module)
    step = {
        "schema_version": "agent.pending_application_step.v1",
        "type": "confirm",
        "reason": "pending_task_application_step",
        "internal": True,
        "source_event": "pending_task_application_step_requested",
        "business_action": "execute_pending_application_step",
        "step_id": "step-1",
        "step_type": "interaction",
        "checkpoint_ref": {
            "runtime": "crm_agent_pending_task",
            "thread_id": "pending:1:2:3:101:abc",
            "checkpoint_ns": "pending_task_subgraph:abc",
            "team_id": 1,
            "user_id": 2,
            "session_id": 3,
            "task_id": 101,
            "continuation_id": "abc",
        },
        "task_snapshot": agent_task_snapshot(task),
        "content": "补充采购类型",
        "turn_input": {"kind": "text", "content": "补充采购类型", "metadata": {}},
        "interaction_metadata": {},
    }

    result = await executor.execute(PendingApplicationStepExecutionRequest(
        db=object(),
        session=SimpleNamespace(id=3),
        task=task,
        team_id=1,
        user_id=2,
        session_id=3,
        authorization="Bearer test",
        step=step,
    ))

    assert len(module.calls) == 1
    assert result["task_snapshot"] == agent_task_snapshot(task)
    interaction_result = result["result"]
    assert interaction_result["current_interrupt"]["reason"] == "write_confirmation"
    assert interaction_result["current_interrupt"]["task_projection_id"] == 101
    assert interaction_result["current_interrupt"]["interaction"]["prompt"] == "请确认是否创建商机？"
    _assert_checkpoint_safe(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("intent", "expected_handled", "expects_task", "expects_suspended"),
    [
        ("confirm", False, True, False),
        ("reject", True, False, True),
    ],
)
async def test_preflight_application_step_projects_executable_confirmation_paths(
    monkeypatch,
    intent,
    expected_handled,
    expects_task,
    expects_suspended,
):
    task = _task()
    monkeypatch.setattr(
        application_modules.agent_confirmation_intent_service,
        "is_executable_confirmation_task",
        lambda task_arg: True,
    )
    monkeypatch.setattr(
        application_modules.session_state,
        "_memory_snapshot_for_session",
        lambda session, task_arg: SimpleNamespace(),
    )

    async def fake_assess(*args, **kwargs):
        return AgentConfirmationIntentDecision(intent=intent, confidence=0.96, reason="用户明确表态")

    monkeypatch.setattr(application_modules.agent_confirmation_intent_service, "assess", fake_assess)

    result = await DefaultPendingApplicationStepExecutor().execute(
        _request(task, step_type="preflight", content="确认" if intent == "confirm" else "取消")
    )

    assert result["result"]["handled"] is expected_handled
    assert bool(result["task_snapshot"]) is expects_task
    assert bool(result["suspended_task_snapshot"]) is expects_suspended
    assert result["result"]["confirmation_decision"]["intent"] == intent
    if intent == "reject":
        assert result["result"]["clear_pending_task_id"] == 101
        assert result["result"]["events"][-1]["event"] == "final"
    _assert_checkpoint_safe(result)


@pytest.mark.asyncio
async def test_preflight_application_step_projects_high_confidence_new_flow(monkeypatch):
    task = _task(action="collect_customer_activity_fields")
    monkeypatch.setattr(
        application_modules.agent_confirmation_intent_service,
        "is_executable_confirmation_task",
        lambda task_arg: False,
    )
    monkeypatch.setattr(application_modules.session_state, "_is_rejection", lambda content: False)

    async def fake_assess_interruption(*args, **kwargs):
        return AgentPendingInterruptionDecision(
            decision="START_NEW_FLOW",
            confidence=0.94,
            detected_customer_name="新客户公司",
            detected_intent="CREATE_CUSTOMER",
            reason="用户明确开始新流程",
        )

    monkeypatch.setattr(application_modules.session_state, "_assess_pending_interruption", fake_assess_interruption)
    monkeypatch.setattr(application_modules.session_state, "_is_high_confidence_new_flow", lambda decision: True)
    monkeypatch.setattr(application_modules.session_state, "_is_ambiguous_pending_interruption", lambda decision: False)

    result = await DefaultPendingApplicationStepExecutor().execute(
        _request(task, step_type="preflight", content="新客户公司要建档")
    )

    assert result["task_snapshot"] == {}
    assert result["suspended_task_snapshot"]["id"] == 101
    assert result["result"]["suspension_kind"] == "paused"
    assert result["result"]["events"][-1]["event"] == "pending_task_interrupted"
    _assert_checkpoint_safe(result)


@pytest.mark.asyncio
async def test_preflight_application_step_projects_ambiguous_and_unknown_prompts(monkeypatch):
    task = _task()
    monkeypatch.setattr(
        application_modules.agent_confirmation_intent_service,
        "is_executable_confirmation_task",
        lambda task_arg: True,
    )
    monkeypatch.setattr(
        application_modules.session_state,
        "_memory_snapshot_for_session",
        lambda session, task_arg: SimpleNamespace(),
    )

    async def fake_confirm(*args, **kwargs):
        return AgentConfirmationIntentDecision(intent="unknown", confidence=0.2, reason="表达不明确")

    async def fake_ambiguous(*args, **kwargs):
        return AgentPendingInterruptionDecision(
            decision="ASK_USER",
            confidence=0.55,
            reason="可能是新流程，也可能是补充",
            question="这是继续当前任务，还是开始新需求？",
        )

    monkeypatch.setattr(application_modules.agent_confirmation_intent_service, "assess", fake_confirm)
    monkeypatch.setattr(application_modules.session_state, "_assess_pending_interruption", fake_ambiguous)
    monkeypatch.setattr(application_modules.session_state, "_is_high_confidence_new_flow", lambda decision: False)
    monkeypatch.setattr(application_modules.session_state, "_is_ambiguous_pending_interruption", lambda decision: True)

    ambiguous = await DefaultPendingApplicationStepExecutor().execute(
        _request(task, step_type="preflight", content="另外有个事情")
    )
    assert ambiguous["result"]["assistant_content"] == "这是继续当前任务，还是开始新需求？"
    assert ambiguous["result"]["events"][-2]["event"] == "pending_interruption_confirmation_required"

    async def fake_continue(*args, **kwargs):
        return AgentPendingInterruptionDecision(
            decision="CONTINUE_PENDING",
            confidence=0.8,
            reason="仍在当前上下文",
            is_field_supplement=True,
        )

    monkeypatch.setattr(application_modules.session_state, "_assess_pending_interruption", fake_continue)
    monkeypatch.setattr(application_modules.session_state, "_is_ambiguous_pending_interruption", lambda decision: False)
    unknown = await DefaultPendingApplicationStepExecutor().execute(
        _request(task, step_type="preflight", content="这个客户挺重要")
    )
    assert unknown["result"]["events"][-2]["event"] == "confirmation_intent_unknown"
    assert unknown["result"]["assistant_content"]
    _assert_checkpoint_safe(ambiguous)
    _assert_checkpoint_safe(unknown)


@pytest.mark.asyncio
async def test_interaction_application_step_executes_field_collection_through_public_seam(monkeypatch):
    task = _task(action="collect_opportunity_fields")

    async def fake_apply(db, task_arg, content):
        assert task_arg is not task
        assert task_arg.id == task.id
        assert content == "补充 100 人"
        return True, "商机信息已补齐。请确认是否创建商机？"

    monkeypatch.setattr(application_modules.opportunity_fields, "_apply_opportunity_fields", fake_apply)

    result = await DefaultPendingApplicationStepExecutor().execute(
        _request(task, step_type="interaction", content="补充 100 人")
    )

    assert result["result"]["handled"] is True
    assert result["result"]["remember_pending_task"] is True
    assert result["result"]["events"][0]["event"] == "confirmation_required"
    assert result["result"]["current_interrupt"]["reason"] == "write_confirmation"
    _assert_checkpoint_safe(result)


@pytest.mark.asyncio
async def test_interaction_application_step_executes_business_selection_through_public_seam(monkeypatch):
    task = _task(action="select_contract_for_payment_plan")

    async def fake_apply(db, task_arg, content, *, team_id, user_id, session_id, metadata):
        assert task_arg is not task
        assert task_arg.id == task.id
        assert (content, team_id, user_id, session_id) == ("合同 A", 1, 2, 3)
        assert metadata == {"selected_contract_id": 301}
        task_arg.state_json = {
            "action": "create_payment_plan",
            "contracts": [{"id": 301, "contract_name": "合同 A"}],
        }
        return {"id": 301, "contract_name": "合同 A"}, "已选择合同 A。"

    monkeypatch.setattr(application_modules.selection, "_apply_business_selection", fake_apply)

    result = await DefaultPendingApplicationStepExecutor().execute(
        _request(
            task,
            step_type="interaction",
            content="合同 A",
            metadata={"selected_contract_id": 301},
        )
    )

    assert result["result"]["events"][0]["event"] == "business_selected"
    assert result["result"]["events"][0]["selected"]["id"] == 301
    assert result["result"]["current_interrupt"]["reason"] == "write_confirmation"
    assert task.state_json["action"] == "select_contract_for_payment_plan"
    assert result["task_snapshot"]["state_json"]["action"] == "create_payment_plan"
    assert result["application_effect_intents"][0]["intent_type"] == "project_pending_task_state"
    _assert_checkpoint_safe(result)


@pytest.mark.asyncio
async def test_turn_relation_application_step_projects_model_decision_as_json(monkeypatch):
    task = _task()

    async def fake_assess(*args, **kwargs):
        assert kwargs["team_id"] == 1
        assert kwargs["user_id"] == 2
        assert kwargs["task"] is task
        assert kwargs["user_message"] == "部署信息补充到另一客户"
        return AgentTurnRelationDecision(
            relation="START_NEW_FLOW",
            confidence=0.92,
            detected_customer_name="另一客户",
            reason="客户主体不同",
        )

    monkeypatch.setattr(application_modules.session_state, "_assess_turn_relation", fake_assess)

    result = await DefaultPendingApplicationStepExecutor().execute(
        _request(task, step_type="turn_relation_assessment", content="部署信息补充到另一客户")
    )

    assert result["result"]["decision"] == {
        "relation": "START_NEW_FLOW",
        "confidence": 0.92,
        "target_task_id": None,
        "detected_customer_name": "另一客户",
        "detected_intent": None,
        "reason": "客户主体不同",
        "question": None,
    }
    _assert_checkpoint_safe(result)


@pytest.mark.asyncio
async def test_task_transition_application_step_projects_before_following_interaction():
    task = _task(status=AgentTaskStatus.SUSPENDED)

    class FakeTaskTransitionModule:
        def __init__(self):
            self.calls = []

        async def execute(self, request):
            self.calls.append(request)
            request.task.status = AgentTaskStatus.WAITING_USER
            return request.task

    module = FakeTaskTransitionModule()
    request = _request(task, step_type="task_transition", content="继续这个草稿")
    request.step["effect_intents"] = [{
        "intent_id": "project_pending_task_state:101:resume",
        "intent_type": "project_pending_task_state",
        "task_id": 101,
        "expected_task": {"status": AgentTaskStatus.SUSPENDED},
        "task_update": {"status": AgentTaskStatus.WAITING_USER},
    }]

    result = await DefaultPendingApplicationStepExecutor(
        task_transition_module=module
    ).execute(request)

    assert len(module.calls) == 1
    assert result["step_type"] == "task_transition"
    assert result["task_snapshot"]["status"] == AgentTaskStatus.WAITING_USER
    assert result["result"]["consumed_intent_ids"] == [
        "project_pending_task_state:101:resume"
    ]
    _assert_checkpoint_safe(result)

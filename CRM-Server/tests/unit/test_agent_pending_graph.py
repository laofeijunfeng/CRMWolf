"""Pending task LangGraph orchestration tests."""

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from app.services.agent.input import AgentTurnInput
from app.models.agent import AgentTaskStatus
from app.services.agent.schemas import AgentTurnRelationDecision
from app.services.agent import pending_graph as pending_graph_module
from app.services.agent import session_state
from app.services.agent.pending_graph import PendingTaskGraphService


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


class FakePreflightPlanner:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def plan(self, db, *, session, task, turn_input, team_id):
        self.calls.append({
            "db": db,
            "session": session,
            "task": task,
            "turn_input": turn_input,
            "team_id": team_id,
        })
        return self.result


class FakeInteractionPlanner:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def plan(self, db, task, content, *, team_id, user_id, session_id, authorization):
        self.calls.append({
            "db": db,
            "task": task,
            "content": content,
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "authorization": authorization,
        })
        return self.result


def _state(task):
    return {
        "db": object(),
        "session": SimpleNamespace(id=3),
        "task": task,
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
        "task": None,
        "turn_input": AgentTurnInput.text("张总说改成增购 20 个了"),
        "content": "张总说改成增购 20 个了",
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "authorization": "Bearer test",
        "events": [],
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


@pytest.mark.asyncio
async def test_pending_task_graph_ends_after_preflight_new_flow():
    task = SimpleNamespace(id=101)
    preflight = FakePreflightPlanner(FakePreflightResult(
        task=None,
        switch_notice="切换处理新流程。",
        suspended_task=task,
        suspend_reason="新客户流程",
        events=[{"event": "pending_task_interrupted"}],
    ))
    interaction = FakeInteractionPlanner(FakeInteractionResult())

    result = await PendingTaskGraphService(
        preflight_planner=preflight,
        interaction_planner=interaction,
    ).run(_state(task))

    assert result["task"] is None
    assert result["suspended_task"] is task
    assert result["switch_notice"] == "切换处理新流程。"
    assert result["events"] == [{"event": "pending_task_interrupted"}]
    assert interaction.calls == []


@pytest.mark.asyncio
async def test_pending_task_graph_runs_interaction_after_continue_pending():
    task = SimpleNamespace(id=101)
    preflight = FakePreflightPlanner(FakePreflightResult(
        task=task,
        events=[{"event": "pending_interruption_assessed"}],
    ))
    interaction = FakeInteractionPlanner(FakeInteractionResult(
        handled=True,
        assistant_content="请确认是否创建商机？",
        remember_pending_task=True,
        events=[{"event": "confirmation_required"}, {"event": "final"}],
    ))

    result = await PendingTaskGraphService(
        preflight_planner=preflight,
        interaction_planner=interaction,
    ).run(_state(task))

    assert result["handled"] is True
    assert result["task"] is task
    assert result["assistant_content"] == "请确认是否创建商机？"
    assert result["remember_pending_task"] is True
    assert result["events"] == [
        {"event": "pending_interruption_assessed"},
        {"event": "confirmation_required"},
        {"event": "final"},
    ]
    assert interaction.calls[0]["task"] is task


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

    monkeypatch.setattr(
        pending_graph_module.pending_tasks.session_state,
        "_suspended_task_snapshots",
        lambda db, session, team_id, user_id: [{"id": 202, "intent": "CREATE_OPPORTUNITY"}],
    )

    async def fake_assess(db, *, team_id, user_id, session, task, user_message):
        return AgentTurnRelationDecision(
            relation="RESUME_SUSPENDED_DRAFT",
            confidence=0.93,
            target_task_id=202,
            detected_intent="CREATE_OPPORTUNITY",
            reason="用户在修改最近暂停的商机草稿。",
        )

    monkeypatch.setattr(pending_graph_module.pending_tasks.session_state, "_assess_turn_relation", fake_assess)
    monkeypatch.setattr(pending_graph_module.agent_task_crud, "get_by_id", lambda db, task_id, team_id, user_id: task)

    def fake_resume(db, session, task_arg):
        task_arg.status = AgentTaskStatus.WAITING_USER
        return task_arg

    monkeypatch.setattr(pending_graph_module.pending_tasks.session_state, "_resume_suspended_task", fake_resume)

    interaction = FakeInteractionPlanner(FakeInteractionResult(
        handled=True,
        assistant_content="商机信息齐了，请确认。",
        remember_pending_task=True,
        events=[{"event": "confirmation_required"}, {"event": "final"}],
    ))

    result = await PendingTaskGraphService(
        preflight_planner=FakePreflightPlanner(FakePreflightResult()),
        interaction_planner=interaction,
    ).run(_state_without_task())

    assert result["task"] is task
    assert result["resumed_task"] is task
    assert result["handled"] is True
    assert interaction.calls[0]["task"] is task
    assert [event["event"] for event in result["events"]] == [
        "suspended_tasks_loaded",
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
        pending_graph_module.pending_tasks.session_state,
        "_suspended_task_snapshots",
        lambda db, session, team_id, user_id: [{"id": 202, "intent": "CREATE_OPPORTUNITY"}],
    )
    monkeypatch.setattr(
        pending_graph_module.pending_tasks.session_state,
        "_assess_turn_relation",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("structured choice should not call semantic routing")),
    )
    monkeypatch.setattr(pending_graph_module.agent_task_crud, "get_by_id", lambda db, task_id, team_id, user_id: task)

    def fake_resume(db, session, task_arg):
        task_arg.status = AgentTaskStatus.WAITING_USER
        return task_arg

    monkeypatch.setattr(pending_graph_module.pending_tasks.session_state, "_resume_suspended_task", fake_resume)

    interaction = FakeInteractionPlanner(FakeInteractionResult(
        handled=True,
        assistant_content="商机信息齐了，请确认。",
        remember_pending_task=True,
        events=[{"event": "confirmation_required"}, {"event": "final"}],
    ))
    state = _state_without_task()
    state["turn_input"] = AgentTurnInput.text("继续：广州睿狐创建商机确认", metadata={"selected_task_id": 202})
    state["content"] = "继续：广州睿狐创建商机确认"

    result = await PendingTaskGraphService(
        preflight_planner=FakePreflightPlanner(FakePreflightResult()),
        interaction_planner=interaction,
    ).run(state)

    assert result["task"] is task
    assert result["resumed_task"] is task
    assert interaction.calls[0]["task"] is task
    assert result["events"][1]["source"] == "interaction_metadata"


@pytest.mark.asyncio
async def test_pending_task_graph_asks_when_suspended_relation_is_ambiguous(monkeypatch):
    monkeypatch.setattr(
        pending_graph_module.pending_tasks.session_state,
        "_suspended_task_snapshots",
        lambda db, session, team_id, user_id: [{"id": 202, "intent": "CREATE_OPPORTUNITY"}],
    )

    async def fake_assess(db, *, team_id, user_id, session, task, user_message):
        return AgentTurnRelationDecision(
            relation="ASK_USER",
            confidence=0.66,
            target_task_id=202,
            reason="可能是修改旧商机，也可能是新跟进。",
            question="这句是继续刚才放下的商机，还是新记录一条跟进？",
        )

    monkeypatch.setattr(pending_graph_module.pending_tasks.session_state, "_assess_turn_relation", fake_assess)
    interaction = FakeInteractionPlanner(FakeInteractionResult())

    result = await PendingTaskGraphService(
        preflight_planner=FakePreflightPlanner(FakePreflightResult()),
        interaction_planner=interaction,
    ).run(_state_without_task())

    assert result["handled"] is True
    assert result["assistant_content"] == "这句是继续刚才放下的商机，还是新记录一条跟进？"
    assert interaction.calls == []
    assert result["events"][-1] == {"event": "final", "content": result["assistant_content"]}


@pytest.mark.asyncio
async def test_pending_task_graph_asks_when_resume_confidence_is_low(monkeypatch):
    monkeypatch.setattr(
        pending_graph_module.pending_tasks.session_state,
        "_suspended_task_snapshots",
        lambda db, session, team_id, user_id: [{"id": 202, "intent": "CREATE_OPPORTUNITY", "summary": "广州睿狐商机草稿"}],
    )

    async def fake_assess(db, *, team_id, user_id, session, task, user_message):
        return AgentTurnRelationDecision(
            relation="RESUME_SUSPENDED_DRAFT",
            confidence=0.62,
            target_task_id=202,
            detected_intent="CREATE_OPPORTUNITY",
            reason="可能是在修改暂停商机，但置信度不足。",
        )

    monkeypatch.setattr(pending_graph_module.pending_tasks.session_state, "_assess_turn_relation", fake_assess)
    monkeypatch.setattr(
        pending_graph_module.agent_task_crud,
        "get_by_id",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("low confidence must not resume task")),
    )

    result = await PendingTaskGraphService(
        preflight_planner=FakePreflightPlanner(FakePreflightResult()),
        interaction_planner=FakeInteractionPlanner(FakeInteractionResult()),
    ).run(_state_without_task())

    assert result["handled"] is True
    assert "广州睿狐商机草稿" in result["assistant_content"]
    assert result["events"][-2]["event"] == "turn_relation_clarification_required"


@pytest.mark.asyncio
async def test_pending_task_graph_asks_when_resume_target_is_not_a_candidate(monkeypatch):
    monkeypatch.setattr(
        pending_graph_module.pending_tasks.session_state,
        "_suspended_task_snapshots",
        lambda db, session, team_id, user_id: [{"id": 202, "intent": "CREATE_OPPORTUNITY", "summary": "广州睿狐商机草稿"}],
    )

    async def fake_assess(db, *, team_id, user_id, session, task, user_message):
        return AgentTurnRelationDecision(
            relation="RESUME_SUSPENDED_DRAFT",
            confidence=0.93,
            target_task_id=999,
            detected_intent="CREATE_OPPORTUNITY",
            reason="模型返回了不存在的目标任务。",
        )

    monkeypatch.setattr(pending_graph_module.pending_tasks.session_state, "_assess_turn_relation", fake_assess)
    monkeypatch.setattr(
        pending_graph_module.agent_task_crud,
        "get_by_id",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unknown target must not be loaded")),
    )

    result = await PendingTaskGraphService(
        preflight_planner=FakePreflightPlanner(FakePreflightResult()),
        interaction_planner=FakeInteractionPlanner(FakeInteractionResult()),
    ).run(_state_without_task())

    assert result["handled"] is True
    assert "广州睿狐商机草稿" in result["assistant_content"]
    assert result["events"][-2]["decision"]["target_task_id"] == 999

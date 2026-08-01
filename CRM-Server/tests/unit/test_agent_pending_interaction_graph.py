"""Pending interaction LangGraph subgraph tests."""

from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.models.agent import AgentTaskStatus
from app.services.agent import opportunity_fields, selection
from app.services.agent.selection import agent_task_crud
from app.services.agent.pending_interaction_graph import (
    PendingInteractionGraphService,
    build_pending_interaction_graph_config,
)


def _task(*, action: str, status: str = AgentTaskStatus.WAITING_USER):
    return SimpleNamespace(
        id=101,
        task_key="task-101",
        status=status,
        intent="CUSTOMER_ACTIVITY",
        target_type="customer",
        target_id=201,
        summary="创建客户跟进",
        input_json={"payload": "current"},
        state_json={"action": action},
    )


def _input(task, content: str = "补充 100 人", metadata: dict[str, object] | None = None):
    return {
        "db": object(),
        "task": task,
        "content": content,
        "interaction_metadata": metadata or {},
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "authorization": "Bearer test",
        "events": [],
    }


@pytest.mark.asyncio
async def test_pending_interaction_graph_checkpoints_completed_field_collection(monkeypatch):
    task = _task(action="collect_opportunity_fields")
    service = PendingInteractionGraphService(checkpointer=InMemorySaver())

    async def fake_apply(db, task_arg, content):
        assert task_arg is task
        assert content == "补充 100 人"
        return True, "商机信息已补齐。请确认是否创建商机？"

    monkeypatch.setattr(opportunity_fields, "_apply_opportunity_fields", fake_apply)

    result = await service.run(_input(task))
    snapshot = await service._graph.aget_state(build_pending_interaction_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
        task_id=101,
    ))

    assert result.handled is True
    assert result.remember_pending_task is True
    assert result.assistant_content == "商机信息已补齐。请确认是否创建商机？"
    assert result.events == [
        {
            "event": "confirmation_required",
            "task_id": 101,
            "content": "商机信息已补齐。请确认是否创建商机？",
            "payload": {"payload": "current"},
        },
        {"event": "final", "content": "商机信息已补齐。请确认是否创建商机？"},
    ]
    assert snapshot.values["field_result"]["handled"] is True
    assert snapshot.values["interaction_route"] == "opportunity_fields"
    assert snapshot.values["result_projection"]["remember_pending_task"] is True


@pytest.mark.asyncio
async def test_pending_interaction_graph_reports_business_selection(monkeypatch):
    task = _task(action="select_contract_for_payment_plan")
    service = PendingInteractionGraphService(checkpointer=InMemorySaver())

    async def fake_apply_business_selection(
        db,
        task_arg,
        content,
        *,
        team_id,
        user_id,
        session_id,
        metadata,
    ):
        assert (team_id, user_id, session_id) == (1, 2, 3)
        return False, "没有匹配到合同，请输入序号。"

    monkeypatch.setattr(
        selection,
        "_apply_business_selection",
        fake_apply_business_selection,
    )

    result = await service.run(_input(task, content="合同 A"))
    snapshot = await service._graph.aget_state(build_pending_interaction_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
        task_id=101,
    ))

    assert result.handled is True
    assert result.remember_pending_task is True
    assert snapshot.values["interaction_route"] == "business_choice"
    assert snapshot.values["business_choice_result"]["handled"] is True
    assert result.events[0] == {
        "event": "business_selection_failed",
        "task_id": 101,
        "content": "没有匹配到合同，请输入序号。",
        "selected": False,
    }


@pytest.mark.asyncio
async def test_pending_interaction_graph_selects_opportunity_for_stage_move(monkeypatch):
    task = _task(action="select_opportunity_for_stage_move")
    task.state_json = {
        "action": "select_opportunity_for_stage_move",
        "customer": {"id": 201, "account_name": "越秀金融"},
        "payload": {
            "customer_id": 201,
            "stage_template_id": 9,
            "target_stage_name": "签约",
            "suggestion_title": "推进到签约",
            "suggestion_reason": "张总说今天可以开始签合同。",
        },
        "opportunities": [
            {"id": 301, "opportunity_name": "CRM 一期", "target_stage_template_id": 9, "target_stage_name": "签约"},
            {"id": 302, "opportunity_name": "CRM 二期", "target_stage_template_id": 9, "target_stage_name": "签约"},
        ],
    }
    updates = []

    def fake_update(db, task_arg, update):
        updates.append(update)

    monkeypatch.setattr(agent_task_crud, "update", fake_update)
    service = PendingInteractionGraphService(checkpointer=InMemorySaver())

    result = await service.run(_input(task, content="2"))
    next_state = updates[0].state_json

    assert result.handled is True
    assert result.remember_pending_task is True
    assert result.events[0]["event"] == "business_selected"
    assert result.events[0]["selected"]["id"] == 302
    assert next_state["action"] == "move_opportunity_stage"
    assert next_state["payload"]["opportunity_id"] == 302
    assert next_state["payload"]["stage_template_id"] == 9
    assert next_state["hitl"]["required_for_tools"] == ["move_opportunity_stage"]


@pytest.mark.asyncio
async def test_pending_interaction_graph_selects_business_from_structured_metadata(monkeypatch):
    task = _task(action="select_opportunity_for_stage_move")
    task.state_json = {
        "action": "select_opportunity_for_stage_move",
        "customer": {"id": 201, "account_name": "越秀金融"},
        "payload": {"customer_id": 201, "stage_template_id": 9, "target_stage_name": "签约"},
        "opportunities": [
            {"id": 301, "opportunity_name": "CRM 一期", "target_stage_template_id": 9, "target_stage_name": "签约"},
            {"id": 302, "opportunity_name": "CRM 二期", "target_stage_template_id": 9, "target_stage_name": "签约"},
        ],
    }
    updates = []

    def fake_update(db, task_arg, update):
        updates.append(update)

    monkeypatch.setattr(agent_task_crud, "update", fake_update)
    service = PendingInteractionGraphService(checkpointer=InMemorySaver())

    result = await service.run(_input(
        task,
        content="CRM 一期",
        metadata={"resource_type": "opportunity", "selected_opportunity_id": 302},
    ))
    next_state = updates[0].state_json

    assert result.handled is True
    assert result.events[0]["selected"]["id"] == 302
    assert next_state["payload"]["opportunity_id"] == 302


@pytest.mark.asyncio
async def test_pending_interaction_graph_ranks_business_choice_with_model(monkeypatch):
    task = _task(action="select_opportunity_for_stage_move")
    task.state_json = {
        "action": "select_opportunity_for_stage_move",
        "customer": {"id": 201, "account_name": "越秀金融"},
        "payload": {"customer_id": 201, "stage_template_id": 9, "target_stage_name": "签约"},
        "opportunities": [
            {
                "id": 301,
                "opportunity_name": "CRM 一期",
                "target_stage_template_id": 9,
                "target_stage_name": "签约",
                "procurement_method_name": "竞争性磋商",
            },
            {
                "id": 302,
                "opportunity_name": "CRM 二期",
                "target_stage_template_id": 9,
                "target_stage_name": "签约",
                "procurement_method_name": "公开招标",
            },
        ],
    }
    updates = []

    def fake_update(db, task_arg, update):
        updates.append(update)

    async def fake_rank_resource_candidates(
        db,
        *,
        team_id,
        user_message,
        resource_kind,
        action_name,
        target,
        candidates,
        current_date=None,
    ):
        assert (team_id, resource_kind, action_name) == (1, "opportunity", "move_opportunity_stage")
        assert user_message == "要招标那个"
        assert candidates[1]["procurement_method_name"] == "公开招标"
        return [
            {"resource_id": 302, "confidence": 0.93, "evidence": ["用户表达匹配采购方式"], "risk_notes": []},
            {"resource_id": 301, "confidence": 0.38, "evidence": [], "risk_notes": ["采购方式不匹配"]},
        ]

    monkeypatch.setattr(agent_task_crud, "update", fake_update)
    monkeypatch.setattr(selection.agent_semantic_parser, "rank_resource_candidates", fake_rank_resource_candidates)
    service = PendingInteractionGraphService(checkpointer=InMemorySaver())

    result = await service.run(_input(task, content="要招标那个"))
    next_state = updates[0].state_json

    assert result.handled is True
    assert result.events[0]["event"] == "business_selected"
    assert result.events[0]["selected"]["id"] == 302
    assert next_state["payload"]["opportunity_id"] == 302


@pytest.mark.asyncio
async def test_pending_interaction_graph_returns_customer_memory_instruction(monkeypatch):
    task = _task(action="select_customer_for_activity", status=AgentTaskStatus.COMPLETED)
    selected_customer = {"id": 201, "account_name": "越秀金融"}
    service = PendingInteractionGraphService(checkpointer=InMemorySaver())

    async def fake_apply(db, task_arg, content, *, team_id, user_id, session_id, authorization, metadata):
        assert (team_id, user_id, session_id, authorization) == (1, 2, 3, "Bearer test")
        assert metadata == {}
        return selected_customer, "已选择越秀金融。请确认是否创建跟进？"

    monkeypatch.setattr(selection, "_apply_customer_selection", fake_apply)

    result = await service.run(_input(task, content="1"))
    snapshot = await service._graph.aget_state(build_pending_interaction_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
        task_id=101,
    ))

    assert result.handled is True
    assert result.selected_customer == selected_customer
    assert result.remember_pending_task is False
    assert result.clear_pending_task_id == 101
    assert snapshot.values["interaction_route"] == "customer_choice"
    assert snapshot.values["customer_choice_result"]["selected_customer"] == selected_customer
    assert result.events[0] == {
        "event": "customer_selected",
        "task_id": 101,
        "customer": selected_customer,
        "content": "已选择越秀金融。请确认是否创建跟进？",
    }


@pytest.mark.asyncio
async def test_pending_interaction_graph_returns_unhandled_when_no_field_or_choice_matches():
    task = _task(action="unrelated_pending_action")
    service = PendingInteractionGraphService(checkpointer=InMemorySaver())

    result = await service.run(_input(task, content="继续"))
    snapshot = await service._graph.aget_state(build_pending_interaction_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
        task_id=101,
    ))

    assert result.handled is False
    assert result.events == []
    assert snapshot.values["interaction_route"] == "end"

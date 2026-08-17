from types import SimpleNamespace

import pytest

from app.services.agent.pending_effects import PendingTaskSideEffectContext, PendingTaskSideEffectHandler
from app.services.agent.state import PendingTaskGraphSideEffects


def test_pending_task_side_effect_handler_applies_session_effects(monkeypatch):
    handler = PendingTaskSideEffectHandler()
    db = object()
    session = SimpleNamespace(id=3)
    task = SimpleNamespace(id=11)
    suspended_task = SimpleNamespace(id=12)
    suspended = []
    remembered_customers = []

    monkeypatch.setattr(
        "app.services.agent.pending_effects.session_state._suspend_pending_task",
        lambda db_arg, session_arg, task_arg, reason, **kwargs: suspended.append((task_arg, reason, kwargs)),
    )
    monkeypatch.setattr(
        "app.services.agent.pending_effects.session_state._remember_current_customer",
        lambda db_arg, session_arg, customer, **kwargs: remembered_customers.append((customer, kwargs)),
    )
    result = handler.apply(
        {
            "has_active_task": True,
            "task_projection": {"id": 11},
            "handled": True,
            "suspended_task_id": 12,
            "suspend_reason": "新客户流程",
            "selected_customer": {"id": 101, "account_name": "越秀金融"},
            "remember_pending_task": True,
            "assistant_content": "请确认是否创建商机？",
            "switch_notice": "切换处理新流程。",
            "events": [{"event": "confirmation_required"}, {"event": "final"}],
        },
        PendingTaskSideEffectContext(
            db=db,
            session=session,
            graph_side_effects=PendingTaskGraphSideEffects(task=task, suspended_task=suspended_task),
        ),
    )

    assert suspended == [(suspended_task, "新客户流程", {"suspension_kind": None, "commit": True})]
    assert remembered_customers == [({"id": 101, "account_name": "越秀金融"}, {"commit": True})]
    assert result.task is task
    assert result.events[0]["event"] == "confirmation_required"
    assert isinstance(result.events[0]["interaction"], dict)
    assert result.events[1] == {"event": "final"}
    assert result.assistant_content == "请确认是否创建商机？"
    assert result.switch_notice == "切换处理新流程。"
    assert result.current_interrupt is not None
    assert result.current_interrupt["type"] == "confirm"
    assert result.current_interrupt["reason"] == "write_confirmation"
    assert result.current_interrupt["allowed_resume_actions"] == ["approve", "edit", "reject", "cancel"]
    assert result.current_interrupt["source_event"] == "confirmation_required"


def test_pending_task_side_effect_handler_does_not_restore_cleared_task(monkeypatch):
    handler = PendingTaskSideEffectHandler()
    task = SimpleNamespace(id=11)
    suspended = []

    monkeypatch.setattr(
        "app.services.agent.pending_effects.session_state._suspend_pending_task",
        lambda db_arg, session_arg, task_arg, reason, **kwargs: suspended.append((task_arg, reason, kwargs)),
    )

    result = handler.apply(
        {
            "has_active_task": False,
            "handled": True,
            "suspended_task_id": 11,
            "suspend_reason": "用户选择先不处理。",
            "suspension_kind": "dismissed",
            "clear_pending_task_id": 11,
            "assistant_content": "好嘞，这一步先放着。",
            "events": [{"event": "task_cancelled"}, {"event": "final"}],
        },
        PendingTaskSideEffectContext(
            db=object(),
            session=SimpleNamespace(id=3),
            graph_side_effects=PendingTaskGraphSideEffects(task=task, suspended_task=task),
        ),
    )

    assert suspended == [(task, "用户选择先不处理。", {"suspension_kind": "dismissed", "commit": True})]
    assert result.task is None
    assert result.current_interrupt is None


def test_pending_task_side_effect_handler_projects_resume_intent_without_committing(monkeypatch):
    handler = PendingTaskSideEffectHandler()
    task = SimpleNamespace(
        id=21,
        team_id=7,
        user_id=11,
        session_id=13,
        status="SUSPENDED",
        state_json={"suspended_reason": "暂存", "action": "create_opportunity"},
    )
    updates = []
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_task_crud.get_by_id_for_update",
        lambda db, task_id, team_id, user_id: task,
    )
    monkeypatch.setattr(
        "app.services.agent.pending_effects.agent_task_crud.update",
        lambda db, task_arg, update, *, commit=True: updates.append((task_arg, update, commit)) or task_arg,
    )

    result = handler.apply(
        {
            "has_active_task": True,
            "task_projection": {"id": 21},
            "effect_intents": [{
                "intent_id": "resume_suspended_task:21",
                "intent_type": "resume_suspended_task",
                "task_id": 21,
            }],
            "events": [{"event": "suspended_task_resumed", "task_id": 21}],
        },
        PendingTaskSideEffectContext(
            db=object(),
            session=SimpleNamespace(id=13),
            team_id=7,
            user_id=11,
            task=task,
            graph_side_effects=PendingTaskGraphSideEffects(task=task),
            commit=False,
        ),
    )

    assert len(updates) == 1
    _, update, commit = updates[0]
    assert update.status == "WAITING_USER"
    assert update.state_json == {"action": "create_opportunity"}
    assert commit is False
    assert result.task is task
    assert task.status == "SUSPENDED"


def test_pending_task_side_effect_handler_rejects_cross_session_resume_intent(monkeypatch):
    handler = PendingTaskSideEffectHandler()
    task = SimpleNamespace(
        id=21,
        team_id=7,
        user_id=11,
        session_id=99,
        status="SUSPENDED",
        state_json={},
    )
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_task_crud.get_by_id_for_update",
        lambda db, task_id, team_id, user_id: task,
    )
    monkeypatch.setattr(
        "app.services.agent.pending_effects.agent_task_crud.update",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("cross-session task must not update")),
    )

    import pytest
    with pytest.raises(ValueError, match="session"):
        handler.apply(
            {
                "has_active_task": True,
                "effect_intents": [{
                    "intent_id": "resume_suspended_task:21",
                    "intent_type": "resume_suspended_task",
                    "task_id": 21,
                }],
                "events": [],
            },
            PendingTaskSideEffectContext(
                db=object(),
                session=SimpleNamespace(id=13),
                team_id=7,
                user_id=11,
                commit=False,
            ),
        )


def test_pending_task_side_effect_handler_projects_workflow_cancel_in_shared_transaction(monkeypatch):
    handler = PendingTaskSideEffectHandler()
    workflow = {
        "schema_version": "agent.action_workflow.v1",
        "workflow_id": "wf_1",
        "action_id": "act_1",
        "action_type": "create_opportunity",
        "status": "waiting_user",
        "policy": {
            "scope": "required_write",
            "source": "explicit_user_request",
            "execution_policy": "requires_confirmation",
            "on_reject": "cancel_action",
            "blocking": True,
        },
    }
    task = SimpleNamespace(
        id=21,
        team_id=7,
        user_id=11,
        session_id=13,
        status="WAITING_USER",
        state_json={"workflow": workflow, "payload": {"workflow": workflow}},
    )
    ledger = SimpleNamespace(
        workflow_id="wf_1",
        action_id="act_1",
        task_id=21,
        team_id=7,
        user_id=11,
        session_id=13,
        status="WAITING_USER",
        decision_json=None,
        status_reason=None,
    )
    task_updates = []
    db = SimpleNamespace(add=lambda obj: None, flush_calls=0, commit_calls=0)
    db.flush = lambda: setattr(db, "flush_calls", db.flush_calls + 1)
    db.commit = lambda: setattr(db, "commit_calls", db.commit_calls + 1)
    db.refresh = lambda obj: None
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_task_crud.get_by_id_for_update",
        lambda db, task_id, team_id, user_id: task,
    )
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_task_crud.update",
        lambda db, task_arg, update, *, commit=True: task_updates.append((update, commit)) or setattr(task_arg, "state_json", update.state_json) or task_arg,
    )
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_workflow_action_crud.get_by_action_id_for_update",
        lambda db, action_id, team_id, user_id: ledger,
    )

    handler.apply(
        {
            "handled": True,
            "effect_intents": [{
                "intent_id": "cancel_workflow_action:act_1:21",
                "intent_type": "cancel_workflow_action",
                "task_id": 21,
                "workflow": workflow,
                "expected_task": {
                    "status": "WAITING_USER",
                    "workflow": workflow,
                    "payload_workflow": workflow,
                },
                "expected_ledger": {
                    "workflow_id": "wf_1",
                    "action_id": "act_1",
                    "task_id": 21,
                    "status": "WAITING_USER",
                },
                "reason": "用户拒绝执行。",
                "source_type": "pending_resume",
                "decision": {"decision": "reject"},
            }],
            "events": [{"event": "task_cancelled"}],
        },
        PendingTaskSideEffectContext(
            db=db,
            session=SimpleNamespace(id=13),
            team_id=7,
            user_id=11,
            task=task,
            commit=False,
        ),
    )

    assert task_updates[0][1] is False
    assert task.state_json["workflow"]["status"] == "cancelled"
    assert task.state_json["payload"]["workflow"]["status"] == "cancelled"
    assert ledger.status == "CANCELLED"
    assert ledger.task_id == 21
    assert ledger.decision_json == {"decision": "reject", "source_type": "pending_resume"}
    assert ledger.status_reason == "用户拒绝执行。"
    assert ledger.finished_time is not None
    assert db.flush_calls == 1
    assert db.commit_calls == 0


def test_pending_task_side_effect_handler_fails_closed_on_task_workflow_conflict(monkeypatch):
    handler = PendingTaskSideEffectHandler()
    workflow = _waiting_workflow()
    changed_workflow = {**workflow, "status": "running"}
    task = SimpleNamespace(
        id=21,
        team_id=7,
        user_id=11,
        session_id=13,
        status="WAITING_USER",
        state_json={"workflow": changed_workflow, "payload": {"workflow": changed_workflow}},
    )
    ledger = SimpleNamespace(
        workflow_id="wf_1",
        action_id="act_1",
        task_id=21,
        team_id=7,
        user_id=11,
        session_id=13,
        status="WAITING_USER",
        decision_json=None,
        status_reason=None,
    )
    task_updates = []
    ledger_updates = []
    db = SimpleNamespace(commit=lambda: None, rollback=lambda: None, refresh=lambda obj: None)
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_task_crud.get_by_id_for_update",
        lambda db, task_id, team_id, user_id: task,
    )
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_workflow_action_crud.get_by_action_id_for_update",
        lambda db, action_id, team_id, user_id: ledger,
    )
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_task_crud.update",
        lambda *args, **kwargs: task_updates.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_workflow_action_crud.update",
        lambda *args, **kwargs: ledger_updates.append((args, kwargs)),
    )

    with pytest.raises(ValueError, match="optimistic conflict"):
        handler.apply(
            _workflow_cancellation_result(workflow),
            PendingTaskSideEffectContext(
                db=db,
                session=SimpleNamespace(id=13),
                team_id=7,
                user_id=11,
                task=task,
                commit=True,
            ),
        )

    assert task_updates == []
    assert ledger_updates == []


def test_pending_task_side_effect_handler_fails_closed_on_running_ledger(monkeypatch):
    handler = PendingTaskSideEffectHandler()
    workflow = _waiting_workflow()
    task = SimpleNamespace(
        id=21,
        team_id=7,
        user_id=11,
        session_id=13,
        status="WAITING_USER",
        state_json={"workflow": workflow, "payload": {"workflow": workflow}},
    )
    ledger = SimpleNamespace(
        workflow_id="wf_1",
        action_id="act_1",
        task_id=21,
        team_id=7,
        user_id=11,
        session_id=13,
        status="RUNNING",
        decision_json=None,
        status_reason=None,
    )
    task_updates = []
    db = SimpleNamespace(commit=lambda: None, rollback=lambda: None, refresh=lambda obj: None)
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_task_crud.get_by_id_for_update",
        lambda db, task_id, team_id, user_id: task,
    )
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_workflow_action_crud.get_by_action_id_for_update",
        lambda db, action_id, team_id, user_id: ledger,
    )
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_task_crud.update",
        lambda *args, **kwargs: task_updates.append((args, kwargs)),
    )

    with pytest.raises(ValueError, match="optimistic conflict"):
        handler.apply(
            _workflow_cancellation_result(workflow),
            PendingTaskSideEffectContext(
                db=db,
                session=SimpleNamespace(id=13),
                team_id=7,
                user_id=11,
                task=task,
                commit=True,
            ),
        )

    assert task_updates == []


def test_pending_task_side_effect_handler_recovers_partial_cancel_replay_in_one_commit(monkeypatch):
    handler = PendingTaskSideEffectHandler()
    workflow = _waiting_workflow()
    cancelled = {**workflow, "status": "cancelled", "status_reason": "用户拒绝执行。", "status_source": "langgraph_resume"}
    task = SimpleNamespace(
        id=21,
        team_id=7,
        user_id=11,
        session_id=13,
        status="WAITING_USER",
        state_json={"workflow": cancelled, "payload": {"workflow": cancelled}},
    )
    ledger = SimpleNamespace(
        workflow_id="wf_1",
        action_id="act_1",
        task_id=21,
        team_id=7,
        user_id=11,
        session_id=13,
        status="WAITING_USER",
        decision_json=None,
        status_reason=None,
    )
    task_updates = []
    ledger_updates = []
    db = SimpleNamespace(commit_calls=0, rollback=lambda: None, refresh=lambda obj: None)
    db.commit = lambda: setattr(db, "commit_calls", db.commit_calls + 1)
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_task_crud.get_by_id_for_update",
        lambda db, task_id, team_id, user_id: task,
    )
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_workflow_action_crud.get_by_action_id_for_update",
        lambda db, action_id, team_id, user_id: ledger,
    )
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_task_crud.update",
        lambda *args, **kwargs: task_updates.append((args, kwargs)),
    )
    def update_ledger(db, ledger_arg, update, *, commit=True):
        ledger_updates.append((update, commit))
        for key, value in update.model_dump(exclude_unset=True).items():
            setattr(ledger_arg, key, value)
        return ledger_arg
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_workflow_action_crud.update",
        update_ledger,
    )

    handler.apply(
        _workflow_cancellation_result(workflow),
        PendingTaskSideEffectContext(
            db=db,
            session=SimpleNamespace(id=13),
            team_id=7,
            user_id=11,
            task=task,
            commit=True,
        ),
    )

    assert task_updates == []
    assert ledger_updates[0][1] is False
    assert ledger.status == "CANCELLED"
    assert db.commit_calls == 1


def test_pending_task_side_effect_handler_recovers_reverse_partial_cancel_replay_in_one_commit(monkeypatch):
    handler = PendingTaskSideEffectHandler()
    workflow = _waiting_workflow()
    task = SimpleNamespace(
        id=21,
        team_id=7,
        user_id=11,
        session_id=13,
        status="WAITING_USER",
        state_json={"workflow": workflow, "payload": {"workflow": workflow}},
    )
    ledger = SimpleNamespace(
        workflow_id="wf_1",
        action_id="act_1",
        task_id=21,
        team_id=7,
        user_id=11,
        session_id=13,
        status="CANCELLED",
        decision_json={"decision": "reject", "source_type": "pending_resume"},
        status_reason="用户拒绝执行。",
    )
    task_updates = []
    ledger_updates = []
    db = SimpleNamespace(commit_calls=0, rollback=lambda: None, refresh=lambda obj: None)
    db.commit = lambda: setattr(db, "commit_calls", db.commit_calls + 1)
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_task_crud.get_by_id_for_update",
        lambda db, task_id, team_id, user_id: task,
    )
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_workflow_action_crud.get_by_action_id_for_update",
        lambda db, action_id, team_id, user_id: ledger,
    )

    def update_task(db, task_arg, update, *, commit=True):
        task_updates.append((update, commit))
        task_arg.state_json = update.state_json
        return task_arg

    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_task_crud.update",
        update_task,
    )
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_workflow_action_crud.update",
        lambda *args, **kwargs: ledger_updates.append((args, kwargs)),
    )

    handler.apply(
        _workflow_cancellation_result(workflow),
        PendingTaskSideEffectContext(
            db=db,
            session=SimpleNamespace(id=13),
            team_id=7,
            user_id=11,
            task=task,
            commit=True,
        ),
    )

    assert task_updates[0][1] is False
    assert task.state_json["workflow"]["status"] == "cancelled"
    assert ledger_updates == []
    assert db.commit_calls == 1


def test_pending_task_side_effect_handler_pure_cancel_replay_has_no_writes(monkeypatch):
    handler = PendingTaskSideEffectHandler()
    workflow = _waiting_workflow()
    cancelled = {
        **workflow,
        "status": "cancelled",
        "status_reason": "用户拒绝执行。",
        "status_source": "langgraph_resume",
    }
    task = SimpleNamespace(
        id=21,
        team_id=7,
        user_id=11,
        session_id=13,
        status="WAITING_USER",
        state_json={"workflow": cancelled, "payload": {"workflow": cancelled}},
    )
    ledger = SimpleNamespace(
        workflow_id="wf_1",
        action_id="act_1",
        task_id=21,
        team_id=7,
        user_id=11,
        session_id=13,
        status="CANCELLED",
        decision_json={"decision": "reject", "source_type": "pending_resume"},
        status_reason="用户拒绝执行。",
    )
    db = SimpleNamespace(
        commit=lambda: (_ for _ in ()).throw(AssertionError("pure replay must not commit")),
        rollback=lambda: None,
        refresh=lambda obj: None,
    )
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_task_crud.get_by_id_for_update",
        lambda db, task_id, team_id, user_id: task,
    )
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_workflow_action_crud.get_by_action_id_for_update",
        lambda db, action_id, team_id, user_id: ledger,
    )
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_task_crud.update",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("pure replay must not update task")),
    )
    monkeypatch.setattr(
        "app.services.agent.workflow_action_cancellation_projection.agent_workflow_action_crud.update",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("pure replay must not update ledger")),
    )

    result = handler.apply(
        _workflow_cancellation_result(workflow),
        PendingTaskSideEffectContext(
            db=db,
            session=SimpleNamespace(id=13),
            team_id=7,
            user_id=11,
            task=task,
            commit=True,
        ),
    )

    assert result.task is task


def _waiting_workflow():
    return {
        "schema_version": "agent.action_workflow.v1",
        "workflow_id": "wf_1",
        "action_id": "act_1",
        "action_type": "create_opportunity",
        "status": "waiting_user",
        "policy": {
            "scope": "required_write",
            "source": "explicit_user_request",
            "execution_policy": "requires_confirmation",
            "on_reject": "cancel_action",
            "blocking": True,
        },
    }


def _workflow_cancellation_result(workflow):
    return {
        "handled": True,
        "effect_intents": [{
            "intent_id": "cancel_workflow_action:act_1:21",
            "intent_type": "cancel_workflow_action",
            "task_id": 21,
            "workflow": workflow,
            "expected_task": {
                "status": "WAITING_USER",
                "workflow": workflow,
                "payload_workflow": workflow,
            },
            "expected_ledger": {
                "workflow_id": "wf_1",
                "action_id": "act_1",
                "task_id": 21,
                "status": "WAITING_USER",
            },
            "reason": "用户拒绝执行。",
            "source_type": "pending_resume",
            "decision": {"decision": "reject"},
        }],
        "events": [{"event": "task_cancelled"}],
    }


def test_pending_task_side_effect_handler_empty_outcome_has_no_business_mutation(monkeypatch):
    handler = PendingTaskSideEffectHandler()
    monkeypatch.setattr(
        "app.services.agent.pending_effects.agent_task_crud.update",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("abort must not update task")),
    )
    result = handler.apply(
        {
            "handled": False,
            "effect_intents": [],
            "events": [],
        },
        PendingTaskSideEffectContext(
            db=object(),
            session=SimpleNamespace(id=13),
            team_id=7,
            user_id=11,
            task=None,
            commit=False,
        ),
    )
    assert result.task is None
    assert result.events == []


def _task_projection_state(*, expected: dict, desired: dict) -> dict:
    return {
        "has_active_task": True,
        "task_projection": {"id": 21},
        "effect_intents": [{
            "intent_id": "project_pending_task_state:21:test",
            "intent_type": "project_pending_task_state",
            "task_id": 21,
            "expected_task": expected,
            "task_update": desired,
        }],
        "events": [],
    }


def _projection_context(task, *, commit=False, session_id=13):
    return PendingTaskSideEffectContext(
        db=object(),
        session=SimpleNamespace(id=session_id),
        team_id=7,
        user_id=11,
        task=task,
        graph_side_effects=PendingTaskGraphSideEffects(task=task),
        commit=commit,
    )


def test_pending_task_side_effect_handler_projects_complete_task_mutation_contract(monkeypatch):
    handler = PendingTaskSideEffectHandler()
    old_state = {"action": "select_customer_for_deployment"}
    desired_state = {"action": "create_deployment", "customer": {"id": 88}}
    task = SimpleNamespace(
        id=21,
        team_id=7,
        user_id=11,
        session_id=13,
        status="WAITING_USER",
        target_id=None,
        summary="请选择客户",
        input_json={},
        state_json=old_state,
    )
    updates = []

    monkeypatch.setattr(
        "app.services.agent.pending_effects.agent_task_crud.get_by_id_for_update",
        lambda db, task_id, team_id, user_id: task,
    )

    def update_task(db, task_arg, update, *, commit=True):
        updates.append((update, commit))
        for field, value in update.model_dump(exclude_unset=True).items():
            setattr(task_arg, field, value)
        return task_arg

    monkeypatch.setattr(
        "app.services.agent.pending_effects.agent_task_crud.update",
        update_task,
    )

    result = handler.apply(
        _task_projection_state(
            expected={
                "target_id": None,
                "summary": "请选择客户",
                "input_json": {},
                "state_json": old_state,
            },
            desired={
                "target_id": 88,
                "summary": "等待确认添加部署信息",
                "input_json": {"customer_id": 88, "environment": "production"},
                "state_json": desired_state,
            },
        ),
        _projection_context(task),
    )

    assert len(updates) == 1
    update, commit = updates[0]
    assert update.target_id == 88
    assert update.summary == "等待确认添加部署信息"
    assert update.input_json == {"customer_id": 88, "environment": "production"}
    assert update.state_json == desired_state
    assert commit is False
    assert result.task is task


def test_pending_task_side_effect_handler_completes_partial_projection_replay(monkeypatch):
    handler = PendingTaskSideEffectHandler()
    task = SimpleNamespace(
        id=21,
        team_id=7,
        user_id=11,
        session_id=13,
        status="WAITING_USER",
        summary="旧摘要",
        state_json={"action": "create_opportunity", "user_count": 10},
    )
    updates = []
    monkeypatch.setattr(
        "app.services.agent.pending_effects.agent_task_crud.get_by_id_for_update",
        lambda db, task_id, team_id, user_id: task,
    )

    def update_task(db, task_arg, update, *, commit=True):
        updates.append((update, commit))
        for field, value in update.model_dump(exclude_unset=True).items():
            setattr(task_arg, field, value)
        return task_arg

    monkeypatch.setattr(
        "app.services.agent.pending_effects.agent_task_crud.update",
        update_task,
    )

    state = _task_projection_state(
        expected={
            "status": "SUSPENDED",
            "summary": "旧摘要",
            "state_json": {"action": "create_opportunity", "user_count": 10},
        },
        desired={
            "status": "WAITING_USER",
            "summary": "等待确认创建增购商机",
            "state_json": {"action": "create_opportunity", "user_count": 20},
        },
    )
    context = _projection_context(task)

    handler.apply(state, context)
    handler.apply(state, context)

    assert len(updates) == 1
    assert task.status == "WAITING_USER"
    assert task.summary == "等待确认创建增购商机"
    assert task.state_json["user_count"] == 20
    assert context.graph_side_effects.resumed_task is task


def test_pending_task_side_effect_handler_skips_already_projected_task(monkeypatch):
    handler = PendingTaskSideEffectHandler()
    desired = {
        "status": "WAITING_USER",
        "summary": "等待确认创建商机",
        "state_json": {"action": "create_opportunity", "user_count": 20},
    }
    task = SimpleNamespace(
        id=21,
        team_id=7,
        user_id=11,
        session_id=13,
        **desired,
    )
    monkeypatch.setattr(
        "app.services.agent.pending_effects.agent_task_crud.get_by_id_for_update",
        lambda db, task_id, team_id, user_id: task,
    )
    monkeypatch.setattr(
        "app.services.agent.pending_effects.agent_task_crud.update",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("idempotent replay must not update")),
    )

    result = handler.apply(
        _task_projection_state(
            expected={
                "status": "SUSPENDED",
                "summary": "旧摘要",
                "state_json": {"action": "create_opportunity", "user_count": 10},
            },
            desired=desired,
        ),
        _projection_context(task),
    )

    assert result.task is task


def test_pending_task_side_effect_handler_fails_closed_on_projection_conflict(monkeypatch):
    import pytest

    handler = PendingTaskSideEffectHandler()
    task = SimpleNamespace(
        id=21,
        team_id=7,
        user_id=11,
        session_id=13,
        status="WAITING_USER",
        summary="并发写入的新摘要",
    )
    monkeypatch.setattr(
        "app.services.agent.pending_effects.agent_task_crud.get_by_id_for_update",
        lambda db, task_id, team_id, user_id: task,
    )
    monkeypatch.setattr(
        "app.services.agent.pending_effects.agent_task_crud.update",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("conflicted projection must not update")),
    )

    with pytest.raises(ValueError, match="projection conflict: summary"):
        handler.apply(
            _task_projection_state(
                expected={"status": "SUSPENDED", "summary": "旧摘要"},
                desired={"status": "WAITING_USER", "summary": "等待确认创建商机"},
            ),
            _projection_context(task),
        )


def test_pending_task_side_effect_handler_rejects_projection_without_expected_value(monkeypatch):
    import pytest

    handler = PendingTaskSideEffectHandler()
    task = SimpleNamespace(
        id=21,
        team_id=7,
        user_id=11,
        session_id=13,
        status="SUSPENDED",
        summary=None,
    )
    monkeypatch.setattr(
        "app.services.agent.pending_effects.agent_task_crud.get_by_id_for_update",
        lambda db, task_id, team_id, user_id: task,
    )
    monkeypatch.setattr(
        "app.services.agent.pending_effects.agent_task_crud.update",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("invalid projection must not update")),
    )

    with pytest.raises(ValueError, match="missing expected fields: summary"):
        handler.apply(
            _task_projection_state(
                expected={"status": "SUSPENDED"},
                desired={"status": "WAITING_USER", "summary": "等待确认创建商机"},
            ),
            _projection_context(task),
        )


def test_pending_task_side_effect_handler_rejects_cross_session_task_projection(monkeypatch):
    import pytest

    handler = PendingTaskSideEffectHandler()
    task = SimpleNamespace(
        id=21,
        team_id=7,
        user_id=11,
        session_id=99,
        status="SUSPENDED",
    )
    monkeypatch.setattr(
        "app.services.agent.pending_effects.agent_task_crud.get_by_id_for_update",
        lambda db, task_id, team_id, user_id: task,
    )
    monkeypatch.setattr(
        "app.services.agent.pending_effects.agent_task_crud.update",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("cross-session projection must not update")),
    )

    with pytest.raises(ValueError, match="session"):
        handler.apply(
            _task_projection_state(
                expected={"status": "SUSPENDED"},
                desired={"status": "WAITING_USER"},
            ),
            _projection_context(task),
        )

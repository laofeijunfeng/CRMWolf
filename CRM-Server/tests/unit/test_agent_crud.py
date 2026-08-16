"""CRM AI Agent CRUD tests."""
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.crud.agent import (
    agent_idempotency_key_crud,
    agent_message_crud,
    agent_session_crud,
    agent_task_crud,
    agent_tool_call_crud,
    agent_workflow_action_crud,
)
from app.models.agent import (
    AgentIdempotencyKey,
    AgentMessage,
    AgentMessageRole,
    AgentSession,
    AgentSessionStatus,
    AgentTask,
    AgentTaskStatus,
    AgentToolCall,
    AgentToolCallStatus,
    AgentWorkflowAction,
    AgentWorkflowActionStatus,
)
from app.schemas.agent import (
    AgentIdempotencyKeyCreate,
    AgentIdempotencyKeyUpdate,
    AgentMessageCreate,
    AgentSessionCreate,
    AgentSessionUpdate,
    AgentTaskCreate,
    AgentTaskUpdate,
    AgentToolCallCreate,
    AgentToolCallUpdate,
    AgentWorkflowActionCreate,
    AgentWorkflowActionUpdate,
)
from app.services.agent import action_workflow, workflow_action_ledger


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


def _db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        AgentSession.__table__,
        AgentMessage.__table__,
        AgentTask.__table__,
        AgentToolCall.__table__,
        AgentIdempotencyKey.__table__,
        AgentWorkflowAction.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    Session = sessionmaker(bind=engine)
    session = Session()
    return engine, session


def test_agent_crud_manages_agent_owned_state():
    engine, db = _db_session()
    try:
        session = agent_session_crud.create(
            db,
            AgentSessionCreate(
                session_key="session-001",
                team_id=1,
                user_id=2,
                title="跟进助手",
                context_json={"source": "test"},
            ),
        )
        assert session.id is not None
        assert agent_session_crud.get_by_key(db, "session-001", team_id=1, user_id=2).id == session.id

        message = agent_message_crud.create(
            db,
            AgentMessageCreate(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.USER,
                content="今天和客户沟通了项目进展",
            ),
        )
        messages, total = agent_message_crud.list_by_session(db, session.id, team_id=1, user_id=2)
        assert total == 1
        assert messages[0].id == message.id

        task = agent_task_crud.create(
            db,
            AgentTaskCreate(
                task_key="task-001",
                team_id=1,
                user_id=2,
                session_id=session.id,
                intent="CUSTOMER_ACTIVITY",
                input_json={"customer_name": "越秀金融"},
            ),
        )
        agent_task_crud.update(
            db,
            task,
            AgentTaskUpdate(status=AgentTaskStatus.COMPLETED, result_json={"follow_up_id": 1001}),
        )
        assert agent_task_crud.get_by_key(db, "task-001", team_id=1, user_id=2).status == AgentTaskStatus.COMPLETED

        tool_call = agent_tool_call_crud.create(
            db,
            AgentToolCallCreate(
                call_key="call-001",
                team_id=1,
                user_id=2,
                session_id=session.id,
                task_id=task.id,
                tool_name="create_customer_activity",
                request_json={"content": "今天和客户沟通了项目进展"},
            ),
        )
        agent_tool_call_crud.update(
            db,
            tool_call,
            AgentToolCallUpdate(status=AgentToolCallStatus.SUCCESS, response_json={"id": 1001}),
        )
        assert (
            agent_tool_call_crud.get_by_key(db, "call-001", team_id=1, user_id=2).status
            == AgentToolCallStatus.SUCCESS
        )

        workflow_action = agent_workflow_action_crud.get_or_create(
            db,
            AgentWorkflowActionCreate(
                workflow_id="wf_001",
                action_id="act_001",
                team_id=1,
                user_id=2,
                session_id=session.id,
                task_id=task.id,
                source_type="agent_planning",
                action_type="collect_opportunity_fields",
                status=AgentWorkflowActionStatus.WAITING_USER,
                scope="optional_suggestion",
                source="business_suggestion",
                execution_policy="requires_confirmation",
                on_reject="skip_and_continue",
                blocking=False,
                payload_json={"customer_id": 7},
            ),
        )
        agent_workflow_action_crud.update(
            db,
            workflow_action,
            AgentWorkflowActionUpdate(
                status=AgentWorkflowActionStatus.SKIPPED,
                status_reason="暂不处理",
                decision_json={"decision": "skip_current_action"},
            ),
        )
        actions = agent_workflow_action_crud.list_by_session(db, session.id, team_id=1, user_id=2)
        assert len(actions) == 1
        assert actions[0].status == AgentWorkflowActionStatus.SKIPPED
        waiting_action = agent_workflow_action_crud.create(
            db,
            AgentWorkflowActionCreate(
                workflow_id="wf_001",
                action_id="act_002",
                team_id=1,
                user_id=2,
                session_id=session.id,
                task_id=task.id,
                source_type="agent_planning",
                action_type="reconcile_follow_up_task",
                status=AgentWorkflowActionStatus.WAITING_USER,
                scope="optional_suggestion",
                source="business_suggestion",
                execution_policy="requires_confirmation",
                on_reject="skip_and_continue",
                blocking=False,
            ),
        )
        agent_workflow_action_crud.create(
            db,
            AgentWorkflowActionCreate(
                workflow_id="wf_002",
                action_id="act_other_user",
                team_id=1,
                user_id=3,
                session_id=session.id,
                source_type="agent_planning",
                action_type="create_opportunity",
                status=AgentWorkflowActionStatus.FAILED,
                scope="optional_suggestion",
                source="business_suggestion",
                execution_policy="requires_confirmation",
                on_reject="skip_and_continue",
                blocking=False,
            ),
        )
        agent_workflow_action_crud.create(
            db,
            AgentWorkflowActionCreate(
                workflow_id="wf_001",
                action_id="act_system",
                team_id=1,
                user_id=None,
                session_id=session.id,
                source_type="post_commit_projection",
                action_type="project_next_follow_up_tasks",
                status=AgentWorkflowActionStatus.EXECUTED,
                scope="derived_automation",
                source="system_automation",
                execution_policy="auto_execute",
                on_reject="ask_clarification",
                blocking=False,
            ),
        )
        status_counts = agent_workflow_action_crud.count_by_status_for_session(
            db,
            session.id,
            team_id=1,
            user_id=2,
        )
        assert status_counts == {
            AgentWorkflowActionStatus.SKIPPED: 1,
            AgentWorkflowActionStatus.WAITING_USER: 1,
        }
        status_counts_with_system = agent_workflow_action_crud.count_by_status_for_session(
            db,
            session.id,
            team_id=1,
            user_id=2,
            include_system_actions=True,
        )
        assert status_counts_with_system == {
            AgentWorkflowActionStatus.SKIPPED: 1,
            AgentWorkflowActionStatus.WAITING_USER: 1,
            AgentWorkflowActionStatus.EXECUTED: 1,
        }
        assert waiting_action.status == AgentWorkflowActionStatus.WAITING_USER

        idempotency_key = agent_idempotency_key_crud.get_or_create(
            db,
            AgentIdempotencyKeyCreate(
                team_id=1,
                user_id=2,
                session_id=session.id,
                task_id=task.id,
                action_key="follow-up:session-001:task-001",
                request_hash="abc123",
            ),
        )
        same_key = agent_idempotency_key_crud.get_or_create(
            db,
            AgentIdempotencyKeyCreate(
                team_id=1,
                user_id=2,
                session_id=session.id,
                task_id=task.id,
                action_key="follow-up:session-001:task-001",
                request_hash="abc123",
            ),
        )
        assert same_key.id == idempotency_key.id

        agent_idempotency_key_crud.update(
            db,
            idempotency_key,
            AgentIdempotencyKeyUpdate(status="SUCCESS", result_json={"id": 1001}),
        )
        agent_session_crud.update(db, session, AgentSessionUpdate(status=AgentSessionStatus.COMPLETED))
        assert session.status == AgentSessionStatus.COMPLETED
    finally:
        db.close()
        engine.dispose()


def test_workflow_action_ledger_marks_action_failed():
    engine, db = _db_session()
    try:
        session = agent_session_crud.create(
            db,
            AgentSessionCreate(
                session_key="session-ledger-failed",
                team_id=1,
                user_id=2,
                title="跟进助手",
            ),
        )
        task = agent_task_crud.create(
            db,
            AgentTaskCreate(
                task_key="task-ledger-failed",
                team_id=1,
                user_id=2,
                session_id=session.id,
                intent="CUSTOMER_ACTIVITY",
                status=AgentTaskStatus.WAITING_USER,
                summary="记录跟进",
            ),
        )
        workflow = action_workflow.required_write_contract(action="create_customer_activity")
        workflow_action_ledger.create_or_update_waiting_action(
            db,
            workflow=workflow,
            team_id=1,
            user_id=2,
            session_id=session.id,
            task_id=task.id,
            source_type=workflow_action_ledger.SOURCE_AGENT_PLANNING,
            payload={"content": "今天联系客户"},
            target_type="customer",
            target_id=7,
        )

        failed = workflow_action_ledger.mark_action_failed(
            db,
            workflow=workflow,
            team_id=1,
            user_id=2,
            task_id=task.id,
            error_message="tool execution failed",
            result={"success": False},
        )

        assert failed is not None
        assert failed.status == AgentWorkflowActionStatus.FAILED
        assert failed.error_message == "tool execution failed"
        assert failed.finished_time is not None
        assert failed.result_json == {"success": False}
    finally:
        db.close()
        engine.dispose()


def test_workflow_action_ledger_marks_action_cancelled():
    engine, db = _db_session()
    try:
        session = agent_session_crud.create(
            db,
            AgentSessionCreate(
                session_key="session-ledger-cancelled",
                team_id=1,
                user_id=2,
                title="跟进助手",
            ),
        )
        task = agent_task_crud.create(
            db,
            AgentTaskCreate(
                task_key="task-ledger-cancelled",
                team_id=1,
                user_id=2,
                session_id=session.id,
                intent="CREATE_OPPORTUNITY",
                status=AgentTaskStatus.WAITING_USER,
                summary="创建商机",
            ),
        )
        workflow = action_workflow.required_write_contract(action="create_opportunity")
        workflow_action_ledger.create_or_update_waiting_action(
            db,
            workflow=workflow,
            team_id=1,
            user_id=2,
            session_id=session.id,
            task_id=task.id,
            source_type=workflow_action_ledger.SOURCE_AGENT_PLANNING,
            payload={"customer_id": 7},
            target_type="customer",
            target_id=7,
        )

        cancelled = workflow_action_ledger.mark_action_cancelled(
            db,
            workflow=workflow,
            team_id=1,
            user_id=2,
            task_id=task.id,
            reason="用户拒绝执行。",
            decision={"decision": "reject"},
        )

        assert cancelled is not None
        assert cancelled.status == AgentWorkflowActionStatus.CANCELLED
        assert cancelled.finished_time is not None
        assert cancelled.status_reason == "用户拒绝执行。"
        assert cancelled.decision_json == {
            "decision": "reject",
            "source_type": workflow_action_ledger.SOURCE_PENDING_RESUME,
        }

        state = workflow_action_ledger.execution_state_for_action_ids(
            db,
            action_ids=[str(workflow["action_id"])],
            team_id=1,
            user_id=2,
        )

        assert state == {
            "satisfied_action_ids": [],
            "running_action_ids": [],
            "terminal_action_ids": [str(workflow["action_id"])],
        }
    finally:
        db.close()
        engine.dispose()


def test_workflow_action_ledger_marks_running_and_blocked_as_recoverable_state():
    engine, db = _db_session()
    try:
        session = agent_session_crud.create(
            db,
            AgentSessionCreate(
                session_key="session-ledger-running-blocked",
                team_id=1,
                user_id=2,
                title="跟进助手",
            ),
        )
        workflow = action_workflow.required_write_contract(action="transition_follow_up_task")

        running = workflow_action_ledger.mark_action_running(
            db,
            workflow=workflow,
            team_id=1,
            user_id=2,
            session_id=session.id,
            task_id=77,
            payload={"task_projection_id": 88},
            target_type="customer",
            target_id=9,
            reason="AUTO_EXECUTION_READY",
        )

        assert running is not None
        assert running.status == AgentWorkflowActionStatus.RUNNING
        assert running.started_time is not None
        assert running.finished_time is None
        assert running.payload_json == {"task_projection_id": 88}
        assert running.status_reason == "AUTO_EXECUTION_READY"

        blocked = workflow_action_ledger.mark_action_blocked(
            db,
            workflow=workflow,
            team_id=1,
            user_id=2,
            session_id=session.id,
            task_id=77,
            payload={"task_projection_id": 88},
            target_type="customer",
            target_id=9,
            reason="waiting_dependencies:act_create_activity",
        )

        assert blocked is not None
        assert blocked.id == running.id
        assert blocked.status == AgentWorkflowActionStatus.BLOCKED
        assert blocked.finished_time is not None
        assert blocked.status_reason == "waiting_dependencies:act_create_activity"

        rerunning = workflow_action_ledger.mark_action_running(
            db,
            workflow=workflow,
            team_id=1,
            user_id=2,
            session_id=session.id,
            task_id=77,
            payload={"task_projection_id": 88},
            target_type="customer",
            target_id=9,
            reason="DEPENDENCY_SATISFIED",
        )

        assert rerunning is not None
        assert rerunning.id == running.id
        assert rerunning.status == AgentWorkflowActionStatus.RUNNING
        assert rerunning.finished_time is None
        assert rerunning.status_reason == "DEPENDENCY_SATISFIED"

        state = workflow_action_ledger.execution_state_for_action_ids(
            db,
            action_ids=[str(workflow["action_id"])],
            team_id=1,
            user_id=2,
        )

        assert state == {
            "satisfied_action_ids": [],
            "running_action_ids": [str(workflow["action_id"])],
            "terminal_action_ids": [],
        }
    finally:
        db.close()
        engine.dispose()


def test_workflow_action_ledger_keeps_repeated_running_and_blocked_updates_idempotent():
    engine, db = _db_session()
    try:
        session = agent_session_crud.create(
            db,
            AgentSessionCreate(
                session_key="session-ledger-idempotent-status",
                team_id=1,
                user_id=2,
                title="跟进助手",
            ),
        )
        workflow = action_workflow.required_write_contract(action="transition_follow_up_task")

        running = workflow_action_ledger.mark_action_running(
            db,
            workflow=workflow,
            team_id=1,
            user_id=2,
            session_id=session.id,
            task_id=77,
            payload={"task_projection_id": 88},
            target_type="customer",
            target_id=9,
            reason="AUTO_EXECUTION_READY",
        )
        assert running is not None
        first_started_time = running.started_time

        repeated_running = workflow_action_ledger.mark_action_running(
            db,
            workflow=workflow,
            team_id=1,
            user_id=2,
            session_id=session.id,
            task_id=77,
            payload={"task_projection_id": 88},
            target_type="customer",
            target_id=9,
            reason="AUTO_EXECUTION_READY",
        )

        assert repeated_running is not None
        assert repeated_running.id == running.id
        assert repeated_running.started_time == first_started_time

        blocked = workflow_action_ledger.mark_action_blocked(
            db,
            workflow=workflow,
            team_id=1,
            user_id=2,
            session_id=session.id,
            task_id=77,
            payload={"task_projection_id": 88},
            target_type="customer",
            target_id=9,
            reason="waiting_dependencies:act_create_activity",
        )
        assert blocked is not None
        first_finished_time = blocked.finished_time

        repeated_blocked = workflow_action_ledger.mark_action_blocked(
            db,
            workflow=workflow,
            team_id=1,
            user_id=2,
            session_id=session.id,
            task_id=77,
            payload={"task_projection_id": 88},
            target_type="customer",
            target_id=9,
            reason="waiting_dependencies:act_create_activity",
        )

        assert repeated_blocked is not None
        assert repeated_blocked.id == blocked.id
        assert repeated_blocked.finished_time == first_finished_time
    finally:
        db.close()
        engine.dispose()


def test_workflow_action_ledger_execution_state_distinguishes_satisfied_from_terminal():
    engine, db = _db_session()
    try:
        session = agent_session_crud.create(
            db,
            AgentSessionCreate(
                session_key="session-ledger-state",
                team_id=1,
                user_id=2,
                title="跟进助手",
            ),
        )
        for action_id, status in [
            ("act_executed", AgentWorkflowActionStatus.EXECUTED),
            ("act_failed", AgentWorkflowActionStatus.FAILED),
            ("act_skipped", AgentWorkflowActionStatus.SKIPPED),
            ("act_cancelled", AgentWorkflowActionStatus.CANCELLED),
        ]:
            agent_workflow_action_crud.create(
                db,
                AgentWorkflowActionCreate(
                    workflow_id="wf_ledger_state",
                    action_id=action_id,
                    team_id=1,
                    user_id=2,
                    session_id=session.id,
                    source_type="agent_planning",
                    action_type="create_customer_activity",
                    status=status,
                    scope="required_write",
                    source="explicit_user_request",
                    execution_policy="requires_confirmation",
                    on_reject="cancel_action",
                    blocking=True,
                ),
            )

        state = workflow_action_ledger.execution_state_for_action_ids(
            db,
            action_ids=["act_executed", "act_failed", "act_skipped", "act_cancelled", "act_missing"],
            team_id=1,
            user_id=2,
        )

        assert state == {
            "satisfied_action_ids": ["act_executed"],
            "running_action_ids": [],
            "terminal_action_ids": ["act_cancelled", "act_failed", "act_skipped"],
        }
    finally:
        db.close()
        engine.dispose()


def test_workflow_action_ledger_prepares_retry_with_audit_history():
    engine, db = _db_session()
    try:
        session = agent_session_crud.create(
            db,
            AgentSessionCreate(
                session_key="session-ledger-retry",
                team_id=1,
                user_id=2,
                title="跟进助手",
            ),
        )
        failed_action = agent_workflow_action_crud.create(
            db,
            AgentWorkflowActionCreate(
                workflow_id="wf_retry",
                action_id="act_retry_required",
                team_id=1,
                user_id=2,
                session_id=session.id,
                source_type="agent_planning",
                action_type="create_customer_activity",
                status=AgentWorkflowActionStatus.FAILED,
                scope="required_write",
                source="explicit_user_request",
                execution_policy="requires_confirmation",
                on_reject="cancel_action",
                blocking=True,
                result_json={"success": False},
                status_reason="tool failed",
                error_message="database timeout",
            ),
        )

        retried = workflow_action_ledger.prepare_action_retry(
            db,
            failed_action,
            retry_source="manual_test",
            reason="修复数据库连接后重试",
        )

        assert retried.status == AgentWorkflowActionStatus.WAITING_USER
        assert retried.result_json is None
        assert retried.error_message is None
        assert retried.finished_time is None
        assert retried.status_reason == "修复数据库连接后重试"
        assert retried.decision_json["last_retry"]["retry_source"] == "manual_test"
        assert retried.decision_json["last_retry"]["previous_status"] == AgentWorkflowActionStatus.FAILED
        assert retried.decision_json["last_retry"]["previous_error_message"] == "database timeout"
        assert retried.decision_json["last_retry"]["previous_result_json"] == {"success": False}

        blocked_action = agent_workflow_action_crud.create(
            db,
            AgentWorkflowActionCreate(
                workflow_id="wf_retry",
                action_id="act_retry_auto",
                team_id=1,
                user_id=2,
                session_id=session.id,
                source_type="post_commit_projection",
                action_type="project_next_follow_up_tasks",
                status=AgentWorkflowActionStatus.BLOCKED,
                scope="derived_automation",
                source="system_automation",
                execution_policy="auto_execute",
                on_reject="ask_clarification",
                blocking=False,
                status_reason="waiting_dependencies:act_root",
            ),
        )

        retried_auto = workflow_action_ledger.prepare_action_retry(db, blocked_action)

        assert retried_auto.status == AgentWorkflowActionStatus.PLANNED
        assert retried_auto.status_reason == "retry_requested_from:BLOCKED"
        assert retried_auto.decision_json["last_retry"]["previous_status_reason"] == "waiting_dependencies:act_root"
    finally:
        db.close()
        engine.dispose()


def test_workflow_action_ledger_rejects_retry_for_non_retryable_terminal_action():
    engine, db = _db_session()
    try:
        action = agent_workflow_action_crud.create(
            db,
            AgentWorkflowActionCreate(
                workflow_id="wf_retry_reject",
                action_id="act_executed_retry",
                team_id=1,
                user_id=2,
                source_type="agent_planning",
                action_type="create_customer_activity",
                status=AgentWorkflowActionStatus.EXECUTED,
                scope="required_write",
                source="explicit_user_request",
                execution_policy="requires_confirmation",
                on_reject="cancel_action",
                blocking=True,
            ),
        )

        try:
            workflow_action_ledger.prepare_action_retry(db, action)
            assert False, "Expected non-retryable action to raise"
        except ValueError as exc:
            assert "cannot be retried" in str(exc)
    finally:
        db.close()
        engine.dispose()


def test_for_update_queries_refresh_cached_agent_state(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'agent-lock-refresh.db'}")
    Base.metadata.create_all(
        engine,
        tables=[
            AgentSession.__table__,
            AgentTask.__table__,
            AgentWorkflowAction.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    concurrent = Session()
    try:
        session = agent_session_crud.create(
            db,
            AgentSessionCreate(
                session_key="session-lock-refresh",
                team_id=1,
                user_id=2,
                title="锁刷新测试",
            ),
        )
        task = agent_task_crud.create(
            db,
            AgentTaskCreate(
                task_key="task-lock-refresh",
                team_id=1,
                user_id=2,
                session_id=session.id,
                intent="CREATE_CUSTOMER_ACTIVITY",
                summary="旧任务摘要",
            ),
        )
        action = agent_workflow_action_crud.create(
            db,
            AgentWorkflowActionCreate(
                workflow_id="wf_lock_refresh",
                action_id="act_lock_refresh",
                team_id=1,
                user_id=2,
                session_id=session.id,
                task_id=task.id,
                source_type="agent_planning",
                action_type="create_customer_activity",
                status=AgentWorkflowActionStatus.WAITING_USER,
                scope="primary_action",
                source="user_request",
                execution_policy="requires_confirmation",
                on_reject="cancel",
                blocking=True,
                payload_json={},
            ),
        )
        assert task.summary == "旧任务摘要"
        assert action.status == AgentWorkflowActionStatus.WAITING_USER

        concurrent_task = concurrent.get(AgentTask, task.id)
        concurrent_action = concurrent.get(AgentWorkflowAction, action.id)
        concurrent_task.summary = "并发更新后的任务摘要"
        concurrent_action.status = AgentWorkflowActionStatus.EXECUTED
        concurrent.commit()

        locked_task = agent_task_crud.get_by_id_for_update(
            db,
            task.id,
            team_id=1,
            user_id=2,
        )
        locked_action = agent_workflow_action_crud.get_by_action_id_for_update(
            db,
            action.action_id,
            team_id=1,
            user_id=2,
        )

        assert locked_task.summary == "并发更新后的任务摘要"
        assert locked_action.status == AgentWorkflowActionStatus.EXECUTED
        assert agent_task_crud.get_by_id_for_update(
            db,
            task.id,
            team_id=1,
            user_id=999,
        ) is None
        assert agent_workflow_action_crud.get_by_action_id_for_update(
            db,
            action.action_id,
            team_id=999,
            user_id=2,
        ) is None
    finally:
        concurrent.close()
        db.close()
        engine.dispose()

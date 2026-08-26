"""CRM AI Agent persistence tests."""

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
    agent_tool_call_crud,
    agent_workflow_action_crud,
)
from app.models.agent import (
    AgentIdempotencyKey,
    AgentMessage,
    AgentMessageRole,
    AgentSession,
    AgentToolCall,
    AgentToolCallStatus,
    AgentWorkflowAction,
    AgentWorkflowActionStatus,
)
from app.schemas.agent import (
    AgentIdempotencyKeyCreate,
    AgentMessageCreate,
    AgentSessionCreate,
    AgentToolCallCreate,
    AgentToolCallUpdate,
    AgentWorkflowActionCreate,
)
from app.services.agent import workflow_action_ledger


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


def _db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AgentSession.__table__,
            AgentMessage.__table__,
            AgentToolCall.__table__,
            AgentIdempotencyKey.__table__,
            AgentWorkflowAction.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    return engine, session


def test_agent_crud_manages_session_message_tool_audit_and_idempotency():
    engine, db = _db_session()
    try:
        agent_session = agent_session_crud.create(
            db,
            AgentSessionCreate(
                session_key="session-001",
                team_id=1,
                user_id=2,
                title="跟进助手",
                context_json={"source": "test"},
            ),
        )
        message = agent_message_crud.create(
            db,
            AgentMessageCreate(
                team_id=1,
                user_id=2,
                session_id=agent_session.id,
                role=AgentMessageRole.USER,
                content="今天和客户沟通了项目进展",
            ),
        )
        tool_call = agent_tool_call_crud.create(
            db,
            AgentToolCallCreate(
                call_key="call-001",
                team_id=1,
                user_id=2,
                session_id=agent_session.id,
                tool_name="create_customer_activity",
                request_json={"content": "今天和客户沟通了项目进展"},
            ),
        )
        agent_tool_call_crud.update(
            db,
            tool_call,
            AgentToolCallUpdate(status=AgentToolCallStatus.SUCCESS, response_json={"id": 1001}),
        )
        idempotency, created = agent_idempotency_key_crud.ensure(
            db,
            AgentIdempotencyKeyCreate(
                team_id=1,
                user_id=2,
                session_id=agent_session.id,
                action_key="create_customer_activity:001",
                request_hash="hash-001",
            ),
        )
        repeated, repeated_created = agent_idempotency_key_crud.ensure(
            db,
            AgentIdempotencyKeyCreate(
                team_id=1,
                user_id=2,
                session_id=agent_session.id,
                action_key="create_customer_activity:001",
                request_hash="hash-001",
            ),
        )

        messages, total = agent_message_crud.list_by_session(
            db,
            agent_session.id,
            team_id=1,
            user_id=2,
        )
        assert agent_session_crud.get_by_key(db, "session-001", team_id=1, user_id=2).id == agent_session.id
        assert total == 1
        assert messages[0].id == message.id
        assert agent_tool_call_crud.get_by_key(db, "call-001", team_id=1, user_id=2).status == "SUCCESS"
        assert created is True
        assert repeated_created is False
        assert repeated.id == idempotency.id
    finally:
        db.close()
        engine.dispose()


def test_record_system_action_is_idempotent_and_updates_durable_audit():
    engine, db = _db_session()
    try:
        first = workflow_action_ledger.record_system_action(
            db,
            team_id=1,
            user_id=2,
            session_id=None,
            workflow_id="wf_post_commit_001",
            action_id="act_project_001",
            action_type="project_next_follow_up_tasks",
            source_type="post_commit_projection",
            status=AgentWorkflowActionStatus.RUNNING,
            payload={"activity_id": 101},
        )
        second = workflow_action_ledger.record_system_action(
            db,
            team_id=1,
            user_id=2,
            session_id=None,
            workflow_id="wf_post_commit_001",
            action_id="act_project_001",
            action_type="project_next_follow_up_tasks",
            source_type="post_commit_projection",
            status=AgentWorkflowActionStatus.EXECUTED,
            payload={"activity_id": 101},
            result={"created_task_count": 1},
        )

        assert second.id == first.id
        assert second.status == AgentWorkflowActionStatus.EXECUTED
        assert second.result_json == {"created_task_count": 1}
        assert second.finished_time is not None
    finally:
        db.close()
        engine.dispose()


def test_workflow_action_for_update_refreshes_cached_state(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'agent-lock-refresh.db'}")
    Base.metadata.create_all(
        engine,
        tables=[AgentSession.__table__, AgentWorkflowAction.__table__],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    concurrent = Session()
    try:
        agent_session = agent_session_crud.create(
            db,
            AgentSessionCreate(
                session_key="session-lock-refresh",
                team_id=1,
                user_id=2,
                title="锁刷新测试",
            ),
        )
        action = agent_workflow_action_crud.create(
            db,
            AgentWorkflowActionCreate(
                workflow_id="wf_lock_refresh",
                action_id="act_lock_refresh",
                team_id=1,
                user_id=2,
                session_id=agent_session.id,
                source_type="post_commit_projection",
                action_type="project_next_follow_up_tasks",
                status=AgentWorkflowActionStatus.RUNNING,
                scope="derived_automation",
                source="system_automation",
                execution_policy="auto_execute",
                on_reject="ask_clarification",
                blocking=False,
            ),
        )
        concurrent_action = concurrent.get(AgentWorkflowAction, action.id)
        concurrent_action.status = AgentWorkflowActionStatus.EXECUTED
        concurrent.commit()

        locked_action = agent_workflow_action_crud.get_by_action_id_for_update(
            db,
            action.action_id,
            team_id=1,
            user_id=2,
        )

        assert locked_action.status == AgentWorkflowActionStatus.EXECUTED
        assert (
            agent_workflow_action_crud.get_by_action_id_for_update(
                db,
                action.action_id,
                team_id=999,
                user_id=2,
            )
            is None
        )
    finally:
        concurrent.close()
        db.close()
        engine.dispose()

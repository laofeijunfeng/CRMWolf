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
)


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
                intent="CUSTOMER_FOLLOW_UP",
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
                tool_name="create_customer_follow_up",
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

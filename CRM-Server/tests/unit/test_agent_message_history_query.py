"""Regression coverage for MySQL Agent history retrieval plans."""

from sqlalchemy import create_engine, event
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.crud.agent import agent_message_crud
from app.models.agent import AgentMessage, AgentSession


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def test_list_by_session_forces_the_owner_order_index_on_mysql() -> None:
    """Message history must not fall back to MySQL index_merge/filesort."""
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[AgentSession.__table__, AgentMessage.__table__])
    captured_statements = []

    with Session(engine) as db:
        @event.listens_for(db, "do_orm_execute")
        def _capture_statement(execute_state):
            captured_statements.append(execute_state.statement)

        items, total = agent_message_crud.list_by_session(
            db,
            session_id=2,
            team_id=1,
            user_id=3,
            skip=0,
            limit=12,
        )

    history_statement = next(
        statement
        for statement in captured_statements
        if getattr(statement, "_order_by_clauses", ())
    )
    compiled = str(
        history_statement.compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert items == []
    assert total == 0
    assert "FORCE INDEX (idx_agent_message_history_owner_order)" in compiled


def test_runtime_history_query_forces_the_owner_order_index_on_mysql() -> None:
    """The current Agent runtime history path must avoid MySQL index_merge/filesort."""
    from app.services.agent.turns import AgentTurnRepository

    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[AgentSession.__table__, AgentMessage.__table__])
    captured_statements = []

    with Session(engine) as db:
        db.add(AgentSession(session_key="history-query-session", team_id=1, user_id=3))
        db.commit()

        @event.listens_for(db, "do_orm_execute")
        def _capture_statement(execute_state):
            captured_statements.append(execute_state.statement)

        items, total = AgentTurnRepository().list_visible_by_session(
            db,
            session_id=1,
            team_id=1,
            user_id=3,
            skip=0,
            limit=12,
        )

    history_statement = next(
        statement
        for statement in captured_statements
        if getattr(statement, "_order_by_clauses", ())
    )
    compiled = str(
        history_statement.compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert items == []
    assert total == 0
    assert "FORCE INDEX (idx_agent_message_history_owner_order)" in compiled

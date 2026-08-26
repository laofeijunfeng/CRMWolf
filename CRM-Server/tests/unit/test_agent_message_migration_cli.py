"""Behavior tests for the controlled historical-message migration command."""

import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.agent import AgentMessage, AgentMessageRole, AgentSession
from scripts.migrate_agent_messages import execute_message_migration, run_message_migration


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def test_controlled_message_migration_runs_committed_batches_to_completion() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[AgentSession.__table__, AgentMessage.__table__])
    created_at = datetime(2026, 8, 20, 22, 0, 0)
    with Session(engine) as db, db.begin():
        session = AgentSession(session_key="legacy-session-cli", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add_all(
            [
                AgentMessage(
                    team_id=1,
                    user_id=2,
                    session_id=session.id,
                    role=AgentMessageRole.USER,
                    event_type="user_message",
                    content=content,
                    created_time=created_at,
                    last_modified_time=created_at,
                )
                for content in ("第一轮", "第二轮")
            ]
        )

    report = run_message_migration(engine, start_after_id=0, batch_size=1)

    assert report.model_dump(mode="json") == {
        "schema_version": "crm.agent.message-migration-run.v1",
        "status": "COMPLETED",
        "failure_code": None,
        "start_after_id": 0,
        "last_id": 2,
        "batch_size": 1,
        "batch_count": 2,
        "source_row_count": 2,
        "target_row_count": 2,
        "migrated_row_count": 2,
        "schema_validated_count": 2,
        "batches": [
            report.batches[0].model_dump(mode="json"),
            report.batches[1].model_dump(mode="json"),
        ],
    }
    assert report.batches[0].last_id == 1
    assert report.batches[0].has_more is True
    assert report.batches[1].last_id == 2
    assert report.batches[1].has_more is False

    with Session(engine) as db:
        assert all(row.ui_json is not None for row in db.query(AgentMessage).all())
    engine.dispose()


def test_controlled_message_migration_reports_empty_source_without_writing_batches() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[AgentSession.__table__, AgentMessage.__table__])

    report = run_message_migration(engine, start_after_id=0, batch_size=100)

    assert report.last_id is None
    assert report.batch_count == 0
    assert report.source_row_count == 0
    assert report.target_row_count == 0
    assert report.migrated_row_count == 0
    assert report.schema_validated_count == 0
    assert report.batches == []
    engine.dispose()


def test_controlled_message_migration_resumes_strictly_after_the_requested_cursor() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[AgentSession.__table__, AgentMessage.__table__])
    created_at = datetime(2026, 8, 20, 22, 30, 0)
    with Session(engine) as db, db.begin():
        session = AgentSession(session_key="legacy-session-cli-resume", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add_all(
            [
                AgentMessage(
                    team_id=1,
                    user_id=2,
                    session_id=session.id,
                    role=AgentMessageRole.USER,
                    event_type="user_message",
                    content=content,
                    created_time=created_at,
                    last_modified_time=created_at,
                )
                for content in ("跳过此行", "从这里恢复", "继续迁移")
            ]
        )

    report = run_message_migration(engine, start_after_id=1, batch_size=1)

    assert report.start_after_id == 1
    assert report.last_id == 3
    assert report.batch_count == 2
    assert report.source_row_count == 2
    with Session(engine) as db:
        rows = db.query(AgentMessage).order_by(AgentMessage.id).all()
        assert rows[0].ui_json is None
        assert rows[1].ui_json is not None
        assert rows[2].ui_json is not None
    engine.dispose()


def test_controlled_message_migration_rejects_invalid_batch_size_before_accessing_rows() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[AgentSession.__table__, AgentMessage.__table__])

    with pytest.raises(ValueError, match="batch_size must be at least 1"):
        run_message_migration(engine, batch_size=0)

    engine.dispose()


def test_controlled_message_migration_keeps_prior_batches_when_a_later_batch_fails() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[AgentSession.__table__, AgentMessage.__table__])
    created_at = datetime(2026, 8, 20, 23, 0, 0)
    with Session(engine) as db, db.begin():
        session = AgentSession(session_key="legacy-session-cli-rollback", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add_all(
            [
                AgentMessage(
                    team_id=1,
                    user_id=2,
                    session_id=session.id,
                    role=AgentMessageRole.USER,
                    event_type="user_message",
                    content="第一批提交",
                    created_time=created_at,
                    last_modified_time=created_at,
                ),
                AgentMessage(
                    team_id=1,
                    user_id=2,
                    session_id=session.id,
                    role=AgentMessageRole.USER,
                    event_type="assistant_message",
                    content="第二批失败",
                    created_time=created_at,
                    last_modified_time=created_at,
                ),
                AgentMessage(
                    team_id=1,
                    user_id=2,
                    session_id=session.id,
                    role=AgentMessageRole.USER,
                    event_type="user_message",
                    content="第三批未执行",
                    created_time=created_at,
                    last_modified_time=created_at,
                ),
            ]
        )

    with pytest.raises(RuntimeError, match="event type does not match role"):
        run_message_migration(engine, batch_size=1)

    with Session(engine) as db:
        rows = db.query(AgentMessage).order_by(AgentMessage.id).all()
        assert rows[0].ui_json is not None
        assert rows[0].turn_id == "turn_legacy_1"
        assert rows[1].ui_json is None
        assert rows[1].turn_id is None
        assert rows[2].ui_json is None
        assert rows[2].turn_id is None
    engine.dispose()


def test_controlled_message_migration_persists_committed_progress_when_a_later_batch_fails(tmp_path) -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[AgentSession.__table__, AgentMessage.__table__])
    created_at = datetime(2026, 8, 20, 23, 30, 0)
    with Session(engine) as db, db.begin():
        session = AgentSession(session_key="legacy-session-cli-report", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add_all(
            [
                AgentMessage(
                    team_id=1,
                    user_id=2,
                    session_id=session.id,
                    role=AgentMessageRole.USER,
                    event_type="user_message",
                    content="第一批提交",
                    created_time=created_at,
                    last_modified_time=created_at,
                ),
                AgentMessage(
                    team_id=1,
                    user_id=2,
                    session_id=session.id,
                    role=AgentMessageRole.USER,
                    event_type="assistant_message",
                    content="第二批失败且不可写入报告",
                    created_time=created_at,
                    last_modified_time=created_at,
                ),
            ]
        )

    report_path = tmp_path / "migration-report.json"
    exit_code = execute_message_migration(engine, output_path=report_path, batch_size=1)

    assert exit_code == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "FAILED"
    assert report["failure_code"] == "INVALID_SOURCE_DATA"
    assert report["last_id"] == 1
    assert report["batch_count"] == 1
    assert report["source_row_count"] == 1
    assert report["target_row_count"] == 1
    assert report["migrated_row_count"] == 1
    assert report["schema_validated_count"] == 1
    assert len(report["batches"]) == 1
    assert "第二批失败" not in report_path.read_text(encoding="utf-8")
    engine.dispose()


def test_controlled_message_migration_persists_failed_report_for_invalid_arguments(tmp_path) -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[AgentSession.__table__, AgentMessage.__table__])
    report_path = tmp_path / "invalid-argument-report.json"

    exit_code = execute_message_migration(engine, output_path=report_path, batch_size=0)

    assert exit_code == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "FAILED"
    assert report["failure_code"] == "INVALID_ARGUMENT"
    assert report["batch_size"] == 0
    assert report["batch_count"] == 0
    assert report["batches"] == []
    engine.dispose()


def test_message_migration_cli_requires_explicit_execute_acknowledgement(tmp_path) -> None:
    from scripts.migrate_agent_messages import main

    report_path = tmp_path / "migration-report.json"

    with pytest.raises(SystemExit) as exc_info:
        main(["--output", str(report_path)])

    assert exc_info.value.code == 2
    assert not report_path.exists()

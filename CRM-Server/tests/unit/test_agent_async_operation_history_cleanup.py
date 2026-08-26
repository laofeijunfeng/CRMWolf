"""Regression tests for the offline Agent async-operation history cleanup."""

from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import Column, DateTime, ForeignKey, Integer, MetaData, String, Table, create_engine, text
from sqlalchemy.pool import StaticPool

from app.services.agent.async_operation_history_cleanup import (
    AGENT_ASYNC_OPERATION_HISTORY_CLEANUP_KEY,
    AgentAsyncOperationHistoryCleanupError,
    AgentAsyncOperationHistoryCleanupService,
)


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata = MetaData()
    Table(
        "crm_agent_async_operations",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("status", String, nullable=False),
    )
    Table(
        "crm_agent_async_operation_events",
        metadata,
        Column("id", Integer, primary_key=True),
        Column(
            "operation_id",
            Integer,
            ForeignKey("crm_agent_async_operations.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    for table_name in (
        "crm_customer_activity_post_commit_jobs",
        "crm_follow_up_task_confirmation_cases",
        "crm_follow_up_task_confirmation_prompt_deliveries",
    ):
        Table(table_name, metadata, Column("id", Integer, primary_key=True))
    Table(
        "crm_agent_checkpoint_migration_journal",
        metadata,
        Column("migration_key", String, primary_key=True),
        Column("schema_version", String, nullable=False),
        Column("evidence_sha256", String, nullable=False),
        Column("created_time", DateTime),
    )
    metadata.create_all(engine)
    return engine


def _count(connection, table_name: str) -> int:
    return int(connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())


def test_cleanup_deletes_only_terminal_agent_operation_history_and_keeps_protected_records() -> None:
    engine = _engine()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO crm_agent_async_operations (id, status) VALUES "
                "(1, 'SUCCEEDED'), (2, 'DEGRADED'), (3, 'FAILED'), (4, 'CANCELLED')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO crm_agent_async_operation_events (id, operation_id) VALUES "
                "(1, 1), (2, 1), (3, 2), (4, 3), (5, 4)"
            )
        )
        connection.execute(text("INSERT INTO crm_customer_activity_post_commit_jobs (id) VALUES (1)"))
        connection.execute(text("INSERT INTO crm_follow_up_task_confirmation_cases (id) VALUES (1)"))
        connection.execute(text("INSERT INTO crm_follow_up_task_confirmation_prompt_deliveries (id) VALUES (1)"))

        result = AgentAsyncOperationHistoryCleanupService(connection).run()

    assert result.deleted_operation_count == 4
    assert result.deleted_event_count == 5
    assert result.retained_post_commit_job_count == 1
    assert result.retained_confirmation_case_count == 1
    assert result.retained_confirmation_delivery_count == 1
    with engine.connect() as connection:
        assert _count(connection, "crm_agent_async_operations") == 0
        assert _count(connection, "crm_agent_async_operation_events") == 0
        assert _count(connection, "crm_customer_activity_post_commit_jobs") == 1
        assert _count(connection, "crm_follow_up_task_confirmation_cases") == 1
        assert _count(connection, "crm_follow_up_task_confirmation_prompt_deliveries") == 1
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM crm_agent_checkpoint_migration_journal WHERE migration_key = :key"),
                {"key": AGENT_ASYNC_OPERATION_HISTORY_CLEANUP_KEY},
            ).scalar_one()
            == 1
        )


@pytest.mark.parametrize("status", ["QUEUED", "RUNNING", "WAITING_USER", "RETRY_SCHEDULED", "UNKNOWN"])
def test_cleanup_fails_closed_when_an_agent_operation_is_not_terminal(status: str) -> None:
    engine = _engine()
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO crm_agent_async_operations (id, status) VALUES (1, :status)"),
            {"status": status},
        )
        connection.execute(text("INSERT INTO crm_agent_async_operation_events (id, operation_id) VALUES (1, 1)"))

    with pytest.raises(AgentAsyncOperationHistoryCleanupError) as error, engine.begin() as connection:
        AgentAsyncOperationHistoryCleanupService(connection).run()

    assert error.value.blockers == [f"agent_async_operation_history_cleanup:nonterminal_status:{status}"]
    with engine.connect() as connection:
        assert _count(connection, "crm_agent_async_operations") == 1
        assert _count(connection, "crm_agent_async_operation_events") == 1


def test_cleanup_rolls_back_if_completed_evidence_cannot_be_staged() -> None:
    engine = _engine()
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO crm_agent_async_operations (id, status) VALUES (1, 'SUCCEEDED')"))
        connection.execute(text("INSERT INTO crm_agent_async_operation_events (id, operation_id) VALUES (1, 1)"))

    with pytest.raises(OSError, match="evidence volume"), engine.begin() as connection:
        AgentAsyncOperationHistoryCleanupService(connection).run(
            stage_completed_result=lambda _result: (_ for _ in ()).throw(OSError("evidence volume unavailable"))
        )

    with engine.connect() as connection:
        assert _count(connection, "crm_agent_async_operations") == 1
        assert _count(connection, "crm_agent_async_operation_events") == 1
        assert _count(connection, "crm_agent_checkpoint_migration_journal") == 0


def test_cleanup_rejects_tampered_completed_evidence() -> None:
    engine = _engine()
    with engine.begin() as connection:
        result = AgentAsyncOperationHistoryCleanupService(connection).run()

    with pytest.raises(AgentAsyncOperationHistoryCleanupError) as error, engine.connect() as connection:
        AgentAsyncOperationHistoryCleanupService(connection).verify_committed_post_state(
            replace(result, deleted_operation_count=1)
        )

    assert error.value.blockers == ["agent_async_operation_history_cleanup:completed_evidence_invalid"]


def test_cleanup_blocks_unexpected_referencing_records() -> None:
    engine = _engine()
    with engine.begin() as connection:
        connection.execute(
            text(
                """CREATE TABLE crm_agent_async_operation_references (
                   id INTEGER PRIMARY KEY,
                   operation_id INTEGER NOT NULL REFERENCES crm_agent_async_operations(id)
                )"""
            )
        )
        connection.execute(text("INSERT INTO crm_agent_async_operations (id, status) VALUES (1, 'SUCCEEDED')"))
        connection.execute(text("INSERT INTO crm_agent_async_operation_references (id, operation_id) VALUES (1, 1)"))

    with pytest.raises(AgentAsyncOperationHistoryCleanupError) as error, engine.begin() as connection:
        AgentAsyncOperationHistoryCleanupService(connection).run()

    assert error.value.blockers == [
        "agent_async_operation_history_cleanup:unexpected_dependency:crm_agent_async_operation_references"
    ]
    with engine.connect() as connection:
        assert _count(connection, "crm_agent_async_operations") == 1


def test_cleanup_cli_requires_all_explicit_acknowledgements() -> None:
    from scripts import cleanup_agent_async_operation_history as cleanup_cli

    with pytest.raises(SystemExit):
        cleanup_cli._parse_args(
            [
                "--output",
                "/tmp/agent-async-operation-history-cleanup.json",
                "--execute",
                "--offline-confirmed",
            ]
        )

    args = cleanup_cli._parse_args(
        [
            "--output",
            "/tmp/agent-async-operation-history-cleanup.json",
            "--execute",
            "--offline-confirmed",
            "--accept-terminal-agent-task-history-loss",
        ]
    )
    assert args.offline_confirmed is True

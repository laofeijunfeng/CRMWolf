"""Regression tests for the explicit forced Agent forward-recovery seam."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from stat import S_IMODE

import pytest
from sqlalchemy import Column, DateTime, ForeignKey, Integer, LargeBinary, MetaData, String, Table, create_engine, text
from sqlalchemy.pool import StaticPool

from app.services.agent.forced_schema_recovery import (
    FORCED_SCHEMA_RECOVERY_KEY,
    ForcedSchemaRecoveryError,
    ForcedSchemaRecoveryService,
)
from scripts import recover_agent_runtime_after_forced_schema_upgrade as recovery_cli


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata = MetaData()
    Table(
        "crm_langgraph_checkpoints",
        metadata,
        Column("thread_id", String, primary_key=True),
        Column("checkpoint_ns", String, primary_key=True, default=""),
        Column("checkpoint_id", String, primary_key=True),
        Column("checkpoint_blob", LargeBinary, nullable=False),
    )
    Table(
        "crm_langgraph_checkpoint_blobs",
        metadata,
        Column("thread_id", String, primary_key=True),
        Column("checkpoint_ns", String, primary_key=True, default=""),
        Column("channel", String, primary_key=True),
        Column("version", String, primary_key=True),
        Column("blob", LargeBinary, nullable=False),
    )
    Table(
        "crm_langgraph_checkpoint_writes",
        metadata,
        Column("thread_id", String, primary_key=True),
        Column("checkpoint_ns", String, primary_key=True, default=""),
        Column("checkpoint_id", String, primary_key=True),
        Column("task_id", String, primary_key=True),
        Column("write_idx", Integer, primary_key=True),
        Column("blob", LargeBinary, nullable=False),
    )
    Table(
        "crm_agent_messages",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("turn_id", String),
        Column("ui_json", String),
    )
    Table(
        "crm_agent_query_result_sets",
        metadata,
        Column("id", Integer, primary_key=True),
        Column(
            "source_message_id",
            Integer,
            ForeignKey("crm_agent_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    Table(
        "crm_customer_intelligence_runs",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("status", String, nullable=False),
    )
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


def _put_checkpoint_family(engine, *, thread_id: str, checkpoint_ns: str = "") -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO crm_langgraph_checkpoints
                   (thread_id, checkpoint_ns, checkpoint_id, checkpoint_blob)
                   VALUES (:thread_id, :checkpoint_ns, 'checkpoint', :blob)"""
            ),
            {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "blob": b"checkpoint"},
        )
        connection.execute(
            text(
                """INSERT INTO crm_langgraph_checkpoint_blobs
                   (thread_id, checkpoint_ns, channel, version, blob)
                   VALUES (:thread_id, :checkpoint_ns, 'channel', '1', :blob)"""
            ),
            {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "blob": b"blob"},
        )
        connection.execute(
            text(
                """INSERT INTO crm_langgraph_checkpoint_writes
                   (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx, blob)
                   VALUES (:thread_id, :checkpoint_ns, 'checkpoint', 'task', 0, :blob)"""
            ),
            {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "blob": b"write"},
        )


def test_forced_recovery_deletes_only_accepted_runtime_and_legacy_messages() -> None:
    engine = _engine()
    _put_checkpoint_family(engine, thread_id="crm_agent:1:2:3:legacy")
    _put_checkpoint_family(engine, thread_id="crm_agent_customer_intelligence:1:event-1")
    _put_checkpoint_family(engine, thread_id="customer_activity:9")
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO crm_agent_messages (id) VALUES (1), (2)"))
        connection.execute(text("INSERT INTO crm_customer_intelligence_runs (id, status) VALUES (1, 'SUCCESS')"))

    with engine.begin() as connection:
        result = ForcedSchemaRecoveryService(connection).run()

    assert result.deleted_agent_message_count == 2
    assert result.deleted_legacy_checkpoint_rows.checkpoints == 1
    assert result.deleted_customer_intelligence_checkpoint_rows.checkpoints == 1
    assert result.retained_adjacent_checkpoint_rows == result.retained_adjacent_checkpoint_rows.__class__(
        checkpoints=1,
        blobs=1,
        writes=1,
    )
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM crm_agent_messages")).scalar_one() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM crm_langgraph_checkpoints")).scalar_one() == 1
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM crm_agent_checkpoint_migration_journal WHERE migration_key = :key"),
                {"key": FORCED_SCHEMA_RECOVERY_KEY},
            ).scalar_one()
            == 1
        )


def test_forced_recovery_fails_closed_when_a_target_runtime_exists() -> None:
    engine = _engine()
    _put_checkpoint_family(engine, thread_id="crm_agent:1:2:3")
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO crm_agent_messages (id) VALUES (1)"))

    try:
        with engine.begin() as connection:
            ForcedSchemaRecoveryService(connection).run()
    except ForcedSchemaRecoveryError as error:
        assert error.blockers == ["recovery:checkpoint_category:target_root"]
    else:
        raise AssertionError("target runtime must block destructive recovery")

    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM crm_agent_messages")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM crm_langgraph_checkpoints")).scalar_one() == 1


def test_forced_recovery_fails_closed_for_nonterminal_customer_intelligence_run() -> None:
    engine = _engine()
    _put_checkpoint_family(engine, thread_id="crm_agent_customer_intelligence:1:event-1")
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO crm_customer_intelligence_runs (id, status) VALUES (1, 'RUNNING')"))

    try:
        with engine.begin() as connection:
            ForcedSchemaRecoveryService(connection).run()
    except ForcedSchemaRecoveryError as error:
        assert error.blockers == ["recovery:customer_intelligence_nonterminal:RUNNING"]
    else:
        raise AssertionError("active Customer Intelligence run must block destructive recovery")

    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM crm_langgraph_checkpoints")).scalar_one() == 1


def test_forced_recovery_rejects_partially_migrated_message_history() -> None:
    engine = _engine()
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO crm_agent_messages (id, turn_id) VALUES (1, 'turn_existing')")
        )

    try:
        with engine.begin() as connection:
            ForcedSchemaRecoveryService(connection).run()
    except ForcedSchemaRecoveryError as error:
        assert error.blockers == ["recovery:agent_message_partial_target_state"]
    else:
        raise AssertionError("partially migrated history must not be discarded")


def test_forced_recovery_blocks_agent_message_cascade_dependencies() -> None:
    engine = _engine()
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO crm_agent_messages (id) VALUES (1)"))
        connection.execute(
            text("INSERT INTO crm_agent_query_result_sets (id, source_message_id) VALUES (1, 1)")
        )

    with (
        pytest.raises(ForcedSchemaRecoveryError, match="recovery:agent_message_dependency") as error,
        engine.begin() as connection,
    ):
        ForcedSchemaRecoveryService(connection).run()

    assert error.value.blockers == ["recovery:agent_message_dependency:crm_agent_query_result_sets"]
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM crm_agent_messages")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM crm_agent_query_result_sets")).scalar_one() == 1
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM crm_agent_checkpoint_migration_journal")
            ).scalar_one()
            == 0
        )


def test_forced_recovery_rolls_back_when_completed_evidence_cannot_be_staged() -> None:
    engine = _engine()
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO crm_agent_messages (id) VALUES (1)"))

    def fail_to_stage(_result) -> None:
        raise OSError("evidence volume is unavailable")

    with pytest.raises(OSError, match="evidence volume"), engine.begin() as connection:
        ForcedSchemaRecoveryService(connection).run(stage_completed_result=fail_to_stage)

    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM crm_agent_messages")).scalar_one() == 1
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM crm_agent_checkpoint_migration_journal")
            ).scalar_one()
            == 0
        )


def test_forced_recovery_rejects_tampered_completed_evidence() -> None:
    engine = _engine()
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO crm_agent_messages (id) VALUES (1)"))
        result = ForcedSchemaRecoveryService(connection).run()

    tampered = replace(result, deleted_agent_message_count=result.deleted_agent_message_count + 1)
    with pytest.raises(ForcedSchemaRecoveryError) as error, engine.connect() as connection:
        ForcedSchemaRecoveryService(connection).verify_committed_post_state(tampered)

    assert error.value.blockers == ["recovery:completed_evidence_invalid"]


def test_recovery_cli_recovers_committed_staged_evidence_and_enforces_permissions(tmp_path) -> None:
    engine = _engine()
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO crm_agent_messages (id) VALUES (1)"))
    output = tmp_path / "evidence" / "recovery.json"
    staged = output.with_name(f".{output.name}.completed.tmp")

    with engine.begin() as connection:
        service = ForcedSchemaRecoveryService(connection)
        service.run(
            stage_completed_result=lambda result: recovery_cli._write_payload(
                staged,
                recovery_cli._report_payload(status="COMPLETED", result=result, blockers=[]),
            )
        )

    assert recovery_cli.execute_forced_schema_recovery(engine, output_path=output) == 0
    assert not staged.exists()
    assert recovery_cli._read_completed_result(output).deleted_agent_message_count == 1
    assert S_IMODE(output.parent.stat().st_mode) == 0o700
    assert S_IMODE(output.stat().st_mode) == 0o600


def test_recovery_cli_requires_every_explicit_acknowledgement() -> None:
    with pytest.raises(SystemExit):
        recovery_cli._parse_args(
            [
                "--output",
                "/tmp/recovery.json",
                "--execute",
                "--accept-legacy-agent-runtime-loss",
                "--accept-agent-message-history-loss",
                "--reset-terminal-customer-intelligence-checkpoints",
            ]
        )

    args = recovery_cli._parse_args(
        [
            "--output",
            "/tmp/recovery.json",
            "--execute",
            "--offline-confirmed",
            "--accept-legacy-agent-runtime-loss",
            "--accept-agent-message-history-loss",
            "--reset-terminal-customer-intelligence-checkpoints",
        ]
    )
    assert args.offline_confirmed is True


def test_recovery_cli_locks_all_database_tables_before_the_destructive_transaction(monkeypatch) -> None:
    statements: list[str] = []

    class FakeConnection:
        class dialect:
            name = "mysql"

        def commit(self) -> None:
            statements.append("COMMIT")

        def rollback(self) -> None:
            statements.append("ROLLBACK")

        def execute(self, statement):
            statements.append(str(statement))

    class FakeEngine:
        @contextmanager
        def connect(self):
            yield FakeConnection()

    class FakeInspector:
        @staticmethod
        def get_table_names() -> list[str]:
            return ["agent_channel_sessions", "alembic_version", "crm_agent_messages", "crm_langgraph_checkpoints"]

    monkeypatch.setattr(recovery_cli, "inspect", lambda _connection: FakeInspector())

    with recovery_cli._locked_recovery_connection(FakeEngine()):
        assert any(statement.startswith("LOCK TABLES") for statement in statements)

    lock_statement = next(statement for statement in statements if statement.startswith("LOCK TABLES"))
    assert "`crm_agent_messages` WRITE" in lock_statement
    assert "`crm_langgraph_checkpoints` WRITE" in lock_statement
    assert "`agent_channel_sessions` WRITE" in lock_statement
    assert "`alembic_version` WRITE" in lock_statement
    assert "UNLOCK TABLES" in statements

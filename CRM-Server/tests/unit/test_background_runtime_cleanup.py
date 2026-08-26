"""Regression tests for the offline background-runtime cleanup seam."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from stat import S_IMODE

import pytest
from sqlalchemy import Column, DateTime, Integer, LargeBinary, MetaData, String, Table, create_engine, text
from sqlalchemy.pool import StaticPool

from app.services.agent.background_runtime_cleanup import (
    BACKGROUND_RUNTIME_CLEANUP_KEY,
    BackgroundRuntimeCleanupError,
    BackgroundRuntimeCleanupService,
)
from scripts import cleanup_background_runtime_after_agent_recovery as cleanup_cli


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
        "crm_customer_intelligence_runs",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("status", String, nullable=False),
    )
    Table(
        "crm_customer_activity_post_commit_jobs",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("status", String, nullable=False),
    )
    Table(
        "crm_follow_up_task_confirmation_cases",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("status", String, nullable=False),
    )
    Table(
        "crm_follow_up_task_confirmation_prompt_deliveries",
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


def _count(connection, table_name: str) -> int:
    return connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()


def test_cleanup_deletes_only_terminal_background_runtime_and_keeps_business_records() -> None:
    engine = _engine()
    _put_checkpoint_family(engine, thread_id="customer_activity:9")
    _put_checkpoint_family(engine, thread_id="customer_activity_post_commit:9")
    _put_checkpoint_family(engine, thread_id="confirmation_delivery:9")
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO crm_customer_intelligence_runs (id, status) VALUES (1, 'SUCCESS'), (2, 'FAILED')")
        )
        connection.execute(
            text(
                "INSERT INTO crm_customer_activity_post_commit_jobs (id, status) "
                "VALUES (1, 'COMPLETED'), (2, 'SKIPPED')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO crm_follow_up_task_confirmation_cases (id, status) VALUES (1, 'PENDING'), (2, 'RESOLVED')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO crm_follow_up_task_confirmation_prompt_deliveries (id, status) "
                "VALUES (1, 'SENT'), (2, 'SKIPPED')"
            )
        )
        result = BackgroundRuntimeCleanupService(connection).run()

    assert result.deleted_adjacent_runtime_rows.checkpoints == 3
    assert result.deleted_adjacent_runtime_rows.blobs == 3
    assert result.deleted_adjacent_runtime_rows.writes == 3
    assert result.deleted_customer_intelligence_run_count == 2
    assert result.retained_post_commit_job_count == 2
    assert result.retained_confirmation_case_count == 2
    assert result.retained_confirmation_delivery_count == 2
    with engine.connect() as connection:
        for table_name in (
            "crm_langgraph_checkpoints",
            "crm_langgraph_checkpoint_blobs",
            "crm_langgraph_checkpoint_writes",
            "crm_customer_intelligence_runs",
        ):
            assert _count(connection, table_name) == 0
        assert _count(connection, "crm_customer_activity_post_commit_jobs") == 2
        assert _count(connection, "crm_follow_up_task_confirmation_cases") == 2
        assert _count(connection, "crm_follow_up_task_confirmation_prompt_deliveries") == 2
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM crm_agent_checkpoint_migration_journal WHERE migration_key = :key"),
                {"key": BACKGROUND_RUNTIME_CLEANUP_KEY},
            ).scalar_one()
            == 1
        )


def test_cleanup_fails_closed_when_any_checkpoint_is_not_adjacent_runtime() -> None:
    engine = _engine()
    _put_checkpoint_family(engine, thread_id="crm_agent:1:2:3")

    with pytest.raises(BackgroundRuntimeCleanupError) as error, engine.begin() as connection:
        BackgroundRuntimeCleanupService(connection).run()

    assert error.value.blockers == ["background_cleanup:checkpoint_category:target_root"]
    with engine.connect() as connection:
        assert _count(connection, "crm_langgraph_checkpoints") == 1


@pytest.mark.parametrize(
    ("table_name", "status", "blocker"),
    [
        (
            "crm_customer_intelligence_runs",
            "RUNNING",
            "background_cleanup:customer_intelligence_nonterminal:RUNNING",
        ),
        (
            "crm_customer_activity_post_commit_jobs",
            "RUNNING",
            "background_cleanup:post_commit_job_nonterminal:RUNNING",
        ),
        (
            "crm_follow_up_task_confirmation_prompt_deliveries",
            "QUEUED",
            "background_cleanup:confirmation_delivery_nonterminal:QUEUED",
        ),
    ],
)
def test_cleanup_fails_closed_when_protected_runtime_is_nonterminal(table_name, status, blocker) -> None:
    engine = _engine()
    _put_checkpoint_family(engine, thread_id="customer_activity:9")
    with engine.begin() as connection:
        connection.execute(text(f"INSERT INTO {table_name} (id, status) VALUES (1, :status)"), {"status": status})

    with pytest.raises(BackgroundRuntimeCleanupError) as error, engine.begin() as connection:
        BackgroundRuntimeCleanupService(connection).run()

    assert error.value.blockers == [blocker]
    with engine.connect() as connection:
        assert _count(connection, "crm_langgraph_checkpoints") == 1


def test_cleanup_blocks_customer_intelligence_runs_with_foreign_key_dependencies() -> None:
    engine = _engine()
    with engine.begin() as connection:
        connection.execute(
            text(
                """CREATE TABLE crm_customer_intelligence_run_references (
                   id INTEGER PRIMARY KEY,
                   run_id INTEGER NOT NULL REFERENCES crm_customer_intelligence_runs(id)
                )"""
            )
        )
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO crm_customer_intelligence_runs (id, status) VALUES (1, 'SUCCESS')"))
        connection.execute(text("INSERT INTO crm_customer_intelligence_run_references (id, run_id) VALUES (1, 1)"))

    with pytest.raises(BackgroundRuntimeCleanupError) as error, engine.begin() as connection:
        BackgroundRuntimeCleanupService(connection).run()

    assert error.value.blockers == [
        "background_cleanup:customer_intelligence_dependency:crm_customer_intelligence_run_references"
    ]
    with engine.connect() as connection:
        assert _count(connection, "crm_customer_intelligence_runs") == 1


def test_cleanup_rolls_back_when_completed_evidence_cannot_be_staged() -> None:
    engine = _engine()
    _put_checkpoint_family(engine, thread_id="customer_activity:9")
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO crm_customer_intelligence_runs (id, status) VALUES (1, 'SUCCESS')"))

    def fail_to_stage(_result) -> None:
        raise OSError("evidence volume is unavailable")

    with pytest.raises(OSError, match="evidence volume"), engine.begin() as connection:
        BackgroundRuntimeCleanupService(connection).run(stage_completed_result=fail_to_stage)

    with engine.connect() as connection:
        assert _count(connection, "crm_langgraph_checkpoints") == 1
        assert _count(connection, "crm_customer_intelligence_runs") == 1
        assert _count(connection, "crm_agent_checkpoint_migration_journal") == 0


def test_cleanup_rejects_tampered_completed_evidence() -> None:
    engine = _engine()
    with engine.begin() as connection:
        result = BackgroundRuntimeCleanupService(connection).run()

    tampered = replace(result, deleted_customer_intelligence_run_count=1)
    with pytest.raises(BackgroundRuntimeCleanupError) as error, engine.connect() as connection:
        BackgroundRuntimeCleanupService(connection).verify_committed_post_state(tampered)

    assert error.value.blockers == ["background_cleanup:completed_evidence_invalid"]


def test_cleanup_cli_recovers_committed_staged_evidence_and_enforces_permissions(tmp_path) -> None:
    engine = _engine()
    _put_checkpoint_family(engine, thread_id="customer_activity:9")
    output = tmp_path / "evidence" / "background-runtime-cleanup.json"
    staged = output.with_name(f".{output.name}.completed.tmp")

    with engine.begin() as connection:
        service = BackgroundRuntimeCleanupService(connection)
        service.run(
            stage_completed_result=lambda result: cleanup_cli._write_payload(
                staged,
                cleanup_cli._report_payload(status="COMPLETED", result=result, blockers=[]),
            )
        )

    assert cleanup_cli.execute_background_runtime_cleanup(engine, output_path=output) == 0
    assert not staged.exists()
    assert cleanup_cli._read_completed_result(output).deleted_adjacent_runtime_rows.checkpoints == 1
    assert S_IMODE(output.parent.stat().st_mode) == 0o700
    assert S_IMODE(output.stat().st_mode) == 0o600


def test_cleanup_cli_requires_every_explicit_acknowledgement() -> None:
    with pytest.raises(SystemExit):
        cleanup_cli._parse_args(
            [
                "--output",
                "/tmp/background-runtime-cleanup.json",
                "--execute",
                "--accept-adjacent-background-runtime-loss",
                "--accept-customer-intelligence-run-audit-loss",
            ]
        )

    args = cleanup_cli._parse_args(
        [
            "--output",
            "/tmp/background-runtime-cleanup.json",
            "--execute",
            "--offline-confirmed",
            "--accept-adjacent-background-runtime-loss",
            "--accept-customer-intelligence-run-audit-loss",
        ]
    )
    assert args.offline_confirmed is True


def test_cleanup_cli_locks_all_database_tables_before_the_destructive_transaction(monkeypatch) -> None:
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
            return ["agent_channel_sessions", "alembic_version", "crm_customer_intelligence_runs"]

    monkeypatch.setattr(cleanup_cli, "inspect", lambda _connection: FakeInspector())

    with cleanup_cli._locked_cleanup_connection(FakeEngine()):
        assert any(statement.startswith("LOCK TABLES") for statement in statements)

    lock_statement = next(statement for statement in statements if statement.startswith("LOCK TABLES"))
    assert "`crm_customer_intelligence_runs` WRITE" in lock_statement
    assert "`agent_channel_sessions` WRITE" in lock_statement
    assert "`alembic_version` WRITE" in lock_statement
    assert "UNLOCK TABLES" in statements

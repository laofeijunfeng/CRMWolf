"""Regression coverage for the non-destructive assistant conversation bridge."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.compiler import compiles

if TYPE_CHECKING:
    from types import ModuleType

    from sqlalchemy.engine import Engine


@compiles(sa.BigInteger, "sqlite")
def _bigint_to_sqlite_int(element: sa.BigInteger, compiler: Any, **kw: Any) -> str:
    return "INTEGER"


CONVERSATIONS = "crm_assistant_conversations"
ARCHIVE = "crm_assistant_conversations_legacy_156"
ENTRIES = "crm_assistant_conversation_entries"
MAPPING = "crm_assistant_conversation_legacy_map"
ORIGINAL_TABLES = (
    "crm_assistant_messages",
    "crm_assistant_tasks",
    "crm_assistant_actions",
    "crm_assistant_turns",
    "crm_assistant_turn_events",
    "crm_assistant_requests",
    "crm_assistant_references",
)
BASE_TIME = datetime(2026, 7, 1, 8, 30)


def _load_migration() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "157_merge_assistant_conversation_paths.py"
    spec = importlib.util.spec_from_file_location("assistant_conversation_bridge_157", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy_schema() -> tuple[sa.MetaData, dict[str, sa.Table]]:
    metadata = sa.MetaData()
    conversations = sa.Table(
        CONVERSATIONS,
        metadata,
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("public_id", sa.String(64), nullable=False, unique=True),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_time", sa.DateTime(), nullable=False),
        sa.Column("last_modified_time", sa.DateTime(), nullable=False),
        sa.Column("next_message_seq", sa.Integer(), nullable=False),
    )
    messages = sa.Table(
        "crm_assistant_messages",
        metadata,
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.BigInteger(),
            sa.ForeignKey(f"{CONVERSATIONS}.id"),
            nullable=False,
        ),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
    )
    tasks = sa.Table(
        "crm_assistant_tasks",
        metadata,
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("public_id", sa.String(64), nullable=False, unique=True),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "conversation_id",
            sa.BigInteger(),
            sa.ForeignKey(f"{CONVERSATIONS}.id"),
            nullable=False,
        ),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("created_time", sa.DateTime(), nullable=False),
    )
    tables = {"conversations": conversations, "messages": messages, "tasks": tasks}
    for table_name in ORIGINAL_TABLES[2:]:
        tables[table_name] = sa.Table(
            table_name,
            metadata,
            sa.Column("id", sa.BigInteger(), primary_key=True),
            sa.Column("payload", sa.Text(), nullable=True),
        )
    return metadata, tables


def _seed_legacy(engine: Engine, tables: dict[str, sa.Table]) -> dict[str, int]:
    conversations = tables["conversations"]
    messages = tables["messages"]
    tasks = tables["tasks"]
    with engine.begin() as connection:
        conversation_rows = []
        for index in range(137):
            created = BASE_TIME + timedelta(minutes=index)
            conversation_rows.append(
                {
                    "id": index + 1,
                    "public_id": f"asc_legacy_seed_{index + 1}",
                    "team_id": 1 if index < 134 else 6,
                    "user_id": 1 if index < 134 else 13,
                    "created_time": created,
                    "last_modified_time": created + timedelta(minutes=1),
                    "next_message_seq": (index % 17) + 1,
                }
            )
        connection.execute(conversations.insert(), conversation_rows)

        task_rows = []
        for index in range(606):
            if index < 553:
                legacy_conversation_id = (index % 134) + 1
                team_id, user_id = 1, 1
            else:
                legacy_conversation_id = 135 + ((index - 553) % 3)
                team_id, user_id = 6, 13
            task_rows.append(
                {
                    "id": index + 1,
                    "public_id": f"AT-{index + 1:04d}",
                    "team_id": team_id,
                    "user_id": user_id,
                    "conversation_id": legacy_conversation_id,
                    "goal": f"历史跟进 {index + 1}",
                    # Repeated timestamps prove the id tie-breaker is stable.
                    "created_time": BASE_TIME + timedelta(minutes=(index * 7) % 251, seconds=index % 3),
                }
            )
        connection.execute(tasks.insert(), task_rows)

        message_rows = []
        for index in range(2063):
            message_rows.append(
                {
                    "id": index + 1,
                    "conversation_id": (index % 137) + 1,
                    "team_id": 1,
                    "user_id": 1,
                    "seq": (index // 137) + 1,
                }
            )
        connection.execute(messages.insert(), message_rows)

        for table_name, count in zip(
            ORIGINAL_TABLES[2:],
            (900, 120, 700, 240, 310),
            strict=True,
        ):
            connection.execute(
                tables[table_name].insert(),
                [{"id": index + 1, "payload": f"{table_name}-{index + 1}"} for index in range(count)],
            )

        counts = {}
        for table_name in (CONVERSATIONS, *ORIGINAL_TABLES):
            counts[table_name] = int(connection.execute(sa.text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())
        return counts


@pytest.fixture
def legacy_database() -> tuple[Engine, dict[str, sa.Table], dict[str, int], ModuleType]:
    engine = sa.create_engine("sqlite:///:memory:")
    metadata, tables = _legacy_schema()
    metadata.create_all(engine)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()
    counts = _seed_legacy(engine, tables)
    yield engine, tables, counts, _load_migration()
    engine.dispose()


def _run(
    engine: Engine,
    migration: ModuleType,
    operation: str,
) -> None:
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        migration.op = Operations(context)
        getattr(migration, operation)()


def _count(engine: Engine, table_name: str) -> int:
    with engine.connect() as connection:
        return int(connection.execute(sa.text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())


def _columns(engine: Engine, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(engine).get_columns(table_name)}


def test_legacy_bridge_preserves_every_row_and_projects_ordered_history(
    legacy_database: tuple[Engine, dict[str, sa.Table], dict[str, int], ModuleType],
) -> None:
    engine, _tables, before, migration = legacy_database

    _run(engine, migration, "upgrade")

    assert _count(engine, ARCHIVE) == before[CONVERSATIONS] == 137
    for table_name in ORIGINAL_TABLES:
        assert _count(engine, table_name) == before[table_name]
    assert _count(engine, CONVERSATIONS) == 2
    assert _count(engine, MAPPING) == 137
    assert _count(engine, ENTRIES) == 606

    current_columns = _columns(engine, CONVERSATIONS)
    assert {
        "version",
        "focused_task_public_id",
        "pending_choice_id",
        "busy_entry_id",
        "lease_expires_at",
    } <= current_columns
    assert not {"last_modified_time", "next_message_seq"} & current_columns

    with engine.connect() as connection:
        mappings = (
            connection.execute(
                sa.text(
                    f"SELECT legacy_conversation_id, conversation_id, team_id, user_id "
                    f"FROM {MAPPING} ORDER BY legacy_conversation_id"
                )
            )
            .mappings()
            .all()
        )
        assert [row["legacy_conversation_id"] for row in mappings] == list(range(1, 138))
        owner_one = [row for row in mappings if (row["team_id"], row["user_id"]) == (1, 1)]
        owner_two = [row for row in mappings if (row["team_id"], row["user_id"]) == (6, 13)]
        assert len({row["conversation_id"] for row in owner_one}) == 1
        assert len({row["conversation_id"] for row in owner_two}) == 1
        assert len({row["conversation_id"] for row in mappings}) == 2

        task_foreign_keys = (
            connection.exec_driver_sql("PRAGMA foreign_key_list('crm_assistant_tasks')").mappings().all()
        )
        message_foreign_keys = (
            connection.exec_driver_sql("PRAGMA foreign_key_list('crm_assistant_messages')").mappings().all()
        )
        assert {row["table"] for row in task_foreign_keys} == {ARCHIVE}
        assert {row["table"] for row in message_foreign_keys} == {ARCHIVE}

        owner_one_entries = (
            connection.execute(
                sa.text(
                    f"SELECT e.task_public_id, e.created_time, e.command_json, e.user_text "
                    f"FROM {ENTRIES} e WHERE e.team_id = 1 AND e.user_id = 1 "
                    "ORDER BY e.created_time, e.id"
                )
            )
            .mappings()
            .all()
        )
        assert len(owner_one_entries) == 553
        assert all(row["command_json"] for row in owner_one_entries)
        assert all(row["user_text"].startswith("历史跟进 ") for row in owner_one_entries)
        ordered_pairs = [(row["created_time"], row["task_public_id"]) for row in owner_one_entries]
        assert ordered_pairs == sorted(
            ordered_pairs,
            key=lambda pair: (pair[0], int(pair[1].split("-")[-1])),
        )

        connection.execute(
            sa.text(
                f"INSERT INTO {CONVERSATIONS} "
                "(public_id, team_id, user_id, version, created_time) "
                "VALUES ('asc_post_bridge', 9, 9, 0, :created_time)"
            ),
            {"created_time": BASE_TIME + timedelta(days=1)},
        )


def test_legacy_bridge_rerun_recovers_a_partial_projection_idempotently(
    legacy_database: tuple[Engine, dict[str, sa.Table], dict[str, int], ModuleType],
) -> None:
    engine, _tables, before, migration = legacy_database
    _run(engine, migration, "upgrade")
    first_snapshot = {
        table_name: _count(engine, table_name)
        for table_name in (ARCHIVE, CONVERSATIONS, MAPPING, ENTRIES, *ORIGINAL_TABLES)
    }

    _run(engine, migration, "upgrade")
    assert {
        table_name: _count(engine, table_name)
        for table_name in (ARCHIVE, CONVERSATIONS, MAPPING, ENTRIES, *ORIGINAL_TABLES)
    } == first_snapshot

    with engine.begin() as connection:
        removed_entry = connection.execute(
            sa.text(f"SELECT id FROM {ENTRIES} WHERE task_public_id = 'AT-0553'")
        ).scalar_one()
        connection.execute(
            sa.text(f"DELETE FROM {ENTRIES} WHERE id = :entry_id"),
            {"entry_id": removed_entry},
        )
        connection.execute(sa.text(f"DELETE FROM {MAPPING} WHERE legacy_conversation_id = 137"))

    _run(engine, migration, "upgrade")

    assert _count(engine, MAPPING) == 137
    assert _count(engine, ENTRIES) == 606
    assert _count(engine, ARCHIVE) == before[CONVERSATIONS]
    for table_name in ORIGINAL_TABLES:
        assert _count(engine, table_name) == before[table_name]
    with engine.connect() as connection:
        restored = (
            connection.execute(
                sa.text(f"SELECT e.task_public_id, e.command_json FROM {ENTRIES} e WHERE e.task_public_id = 'AT-0553'")
            )
            .mappings()
            .one()
        )
        assert restored["task_public_id"] == "AT-0553"
        assert restored["command_json"]


def test_legacy_bridge_downgrade_restores_legacy_schema_without_losing_rows(
    legacy_database: tuple[Engine, dict[str, sa.Table], dict[str, int], ModuleType],
) -> None:
    engine, _tables, before, migration = legacy_database
    _run(engine, migration, "upgrade")

    _run(engine, migration, "downgrade")

    assert _count(engine, CONVERSATIONS) == before[CONVERSATIONS] == 137
    assert not sa.inspect(engine).has_table(ARCHIVE)
    assert not sa.inspect(engine).has_table(ENTRIES)
    assert not sa.inspect(engine).has_table(MAPPING)
    assert "next_message_seq" in _columns(engine, CONVERSATIONS)
    assert not {"version", "lease_expires_at"} & _columns(engine, CONVERSATIONS)
    for table_name in ORIGINAL_TABLES:
        assert _count(engine, table_name) == before[table_name]
    with engine.connect() as connection:
        task_foreign_keys = (
            connection.exec_driver_sql("PRAGMA foreign_key_list('crm_assistant_tasks')").mappings().all()
        )
        message_foreign_keys = (
            connection.exec_driver_sql("PRAGMA foreign_key_list('crm_assistant_messages')").mappings().all()
        )
        assert {row["table"] for row in task_foreign_keys} == {CONVERSATIONS}
        assert {row["table"] for row in message_foreign_keys} == {CONVERSATIONS}


def test_legacy_bridge_downgrade_refuses_to_drop_post_migration_data(
    legacy_database: tuple[Engine, dict[str, sa.Table], dict[str, int], ModuleType],
) -> None:
    engine, _tables, _before, migration = legacy_database
    _run(engine, migration, "upgrade")
    with engine.begin() as connection:
        canonical_id = connection.execute(
            sa.text(f"SELECT id FROM {CONVERSATIONS} WHERE team_id = 1 AND user_id = 1")
        ).scalar_one()
        connection.execute(
            sa.text(
                f"INSERT INTO {ENTRIES} "
                "(public_id, conversation_id, team_id, user_id, client_request_id, "
                "input_fingerprint, user_text, command_json, decision_json, state, created_time) "
                "VALUES ('acm_post_bridge', :conversation_id, 1, 1, 'post-bridge', "
                "'fingerprint', '新增内容', '{}', '{}', 'READY', :created_time)"
            ),
            {"conversation_id": canonical_id, "created_time": BASE_TIME + timedelta(days=2)},
        )

    with pytest.raises(RuntimeError, match="refusing lossy downgrade"):
        _run(engine, migration, "downgrade")

    assert sa.inspect(engine).has_table(ARCHIVE)
    assert _count(engine, ENTRIES) == 607


def test_current_schema_upgrade_does_not_create_a_second_history_path() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    migration = _load_migration()
    metadata = sa.MetaData()
    sa.Table(
        CONVERSATIONS,
        metadata,
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("public_id", sa.String(64), nullable=False, unique=True),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("focused_task_public_id", sa.String(64), nullable=True),
        sa.Column("pending_choice_id", sa.String(64), nullable=True),
        sa.Column("busy_entry_id", sa.String(64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_time", sa.DateTime(), nullable=False),
    )
    metadata.create_all(engine)
    try:
        _run(engine, migration, "upgrade")

        assert sa.inspect(engine).has_table(ENTRIES)
        assert not sa.inspect(engine).has_table(ARCHIVE)
        assert not sa.inspect(engine).has_table(MAPPING)
        assert _count(engine, CONVERSATIONS) == 0
        assert _run(engine, migration, "downgrade") is None
    finally:
        engine.dispose()

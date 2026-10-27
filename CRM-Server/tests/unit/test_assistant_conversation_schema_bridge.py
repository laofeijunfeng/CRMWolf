"""Data-preservation and fail-closed coverage for the assistant migration bridge."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations" / "versions"
CURRENT = "02352b41bcb6_assistant_continuous_conversations.py"
LEGACY = "154_assistant_conversations.py"
IDENTITY = "155_assistant_message_identity.py"
HISTORY = "156_assistant_historical_messages.py"
BRIDGE = "157_merge_assistant_conversation_paths.py"


def _load(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), MIGRATIONS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply(filename: str, connection: sa.Connection) -> None:
    module = _load(filename)
    module.op = Operations(MigrationContext.configure(connection))
    module.upgrade()
    connection.commit()


def _dependencies(connection: sa.Connection) -> None:
    """Only synthetic assistant state; retain real child-FK dependency directions."""
    for ddl in (
        """
        CREATE TABLE crm_assistant_tasks (
            id INTEGER PRIMARY KEY,
            public_id VARCHAR(64) NOT NULL UNIQUE,
            team_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            status VARCHAR(20) NOT NULL,
            goal TEXT NOT NULL,
            draft_json JSON NOT NULL,
            waiting_json JSON NOT NULL,
            authority_json JSON NOT NULL,
            committed_json JSON NOT NULL,
            created_time DATETIME NOT NULL,
            last_modified_time DATETIME NOT NULL
        )
        """,
        """
        CREATE TABLE crm_assistant_actions (
            id INTEGER PRIMARY KEY,
            public_id VARCHAR(64) NOT NULL UNIQUE,
            task_id BIGINT NOT NULL REFERENCES crm_assistant_tasks(id),
            team_id BIGINT NOT NULL,
            actor VARCHAR(20) NOT NULL,
            action VARCHAR(64) NOT NULL,
            input_json JSON NOT NULL,
            result_json JSON NOT NULL,
            created_time DATETIME NOT NULL
        )
        """,
        """
        CREATE TABLE crm_assistant_requests (
            id INTEGER PRIMARY KEY,
            team_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            client_request_id VARCHAR(128) NOT NULL,
            input_fingerprint VARCHAR(64) NOT NULL,
            task_id BIGINT NOT NULL REFERENCES crm_assistant_tasks(id),
            turn_id BIGINT,
            created_time DATETIME NOT NULL
        )
        """,
        """
        CREATE TABLE crm_assistant_turns (
            id INTEGER PRIMARY KEY,
            public_id VARCHAR(64) NOT NULL UNIQUE,
            team_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            task_id BIGINT NOT NULL REFERENCES crm_assistant_tasks(id),
            request_id BIGINT NOT NULL UNIQUE REFERENCES crm_assistant_requests(id),
            input_json JSON NOT NULL,
            created_time DATETIME NOT NULL
        )
        """,
        """
        CREATE TABLE crm_assistant_turn_events (
            id INTEGER PRIMARY KEY,
            turn_id BIGINT NOT NULL REFERENCES crm_assistant_turns(id),
            seq INTEGER NOT NULL,
            event VARCHAR(32) NOT NULL,
            data_json JSON NOT NULL,
            created_time DATETIME NOT NULL,
            UNIQUE (turn_id, seq)
        )
        """,
    ):
        connection.exec_driver_sql(ddl)
    connection.exec_driver_sql(
        """
        INSERT INTO crm_assistant_tasks
            (id, public_id, team_id, user_id, status, goal, draft_json,
             waiting_json, authority_json, committed_json, created_time,
             last_modified_time)
        VALUES
            (1, 'ast_legacy_1', 1, 2, 'ACTIVE', '历史任务', '{}', '{}',
             '{}', '{}', '2026-01-01', '2026-01-01'),
            (2, 'ast_legacy_2', 1, 2, 'ACTIVE', '无回合历史任务', '{}', '{}',
             '{}', '{}', '2026-01-02', '2026-01-02')
        """
    )
    connection.exec_driver_sql(
        """
        INSERT INTO crm_assistant_actions
            (id, public_id, task_id, team_id, actor, action, input_json,
             result_json, created_time)
        VALUES
            (1, 'asa_legacy_1', 1, 1, 'MODEL', 'WAIT',
             '{"prompt": "历史助手回复"}', '{"message": "历史助手回复"}',
             '2026-01-01'),
            (2, 'asa_legacy_2', 2, 1, 'MODEL', 'WAIT',
             '{"prompt": "无回合助手回复"}', '{"message": "无回合助手回复"}',
             '2026-01-02')
        """
    )
    connection.exec_driver_sql(
        """
        INSERT INTO crm_assistant_requests
            (id, team_id, user_id, client_request_id, input_fingerprint,
             task_id, turn_id, created_time)
        VALUES (1, 1, 2, 'legacy-request', 'fingerprint', 1, 1, '2026-01-01')
        """
    )
    connection.exec_driver_sql(
        """
        INSERT INTO crm_assistant_turns
            (id, public_id, team_id, user_id, task_id, request_id, input_json, created_time)
        VALUES (1, 'atr_legacy_1', 1, 2, 1, 1, '{"text": "历史用户输入"}', '2026-01-01')
        """
    )
    connection.exec_driver_sql(
        """
        INSERT INTO crm_assistant_turn_events
            (id, turn_id, seq, event, data_json, created_time)
        VALUES (1, 1, 1, 'waiting', '{"prompt": "历史助手回复"}', '2026-01-01')
        """
    )
    connection.commit()


def _legacy_conversation(connection: sa.Connection, *, owner_columns: str = "id, team_id, user_id") -> None:
    connection.exec_driver_sql(
        f"""
        CREATE TABLE crm_assistant_conversations (
            id INTEGER NOT NULL PRIMARY KEY,
            public_id VARCHAR(64) NOT NULL UNIQUE,
            team_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            created_time DATETIME NOT NULL,
            last_modified_time DATETIME NOT NULL,
            next_message_seq INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT uq_assistant_conversation_owner UNIQUE ({owner_columns})
        )
        """
    )
    connection.exec_driver_sql(
        """
        INSERT INTO crm_assistant_conversations
            (id, public_id, team_id, user_id, created_time, last_modified_time)
        VALUES (7, 'acv_legacy_1_2', 1, 2, '2026-01-01', '2026-01-01')
        """
    )
    connection.commit()


def _existing_message_and_reference(connection: sa.Connection) -> None:
    connection.exec_driver_sql(
        """
        INSERT INTO crm_assistant_references
            (id, public_id, team_id, user_id, conversation_id, source_phrase,
             kind, status, candidate_work_item_ids, resolved_task_id,
             created_time, last_modified_time)
        SELECT 3, 'are_existing', 1, 2, id, '既有引用', 'TASK', 'OPEN',
               '["ast_legacy_1"]', 1, '2025-12-31', '2025-12-31'
        FROM crm_assistant_conversations WHERE team_id = 1 AND user_id = 2
        """
    )
    connection.exec_driver_sql(
        """
        INSERT INTO crm_assistant_messages
            (id, public_id, team_id, user_id, conversation_id, role, text,
             task_id, client_request_id, turn_id, seq, created_time, last_modified_time)
        SELECT 9, 'ams_existing', 1, 2, id, 'USER', '既有消息', 1,
               'existing-request', NULL, 5, '2025-12-31', '2025-12-31'
        FROM crm_assistant_conversations WHERE team_id = 1 AND user_id = 2
        """
    )
    connection.commit()


def _rows(connection: sa.Connection, table_name: str) -> list[dict[str, object]]:
    table = sa.Table(table_name, sa.MetaData(), autoload_with=connection)
    return [dict(row) for row in connection.execute(sa.select(table).order_by(table.c.id)).mappings()]


def test_bridge_revision_merges_both_reachable_paths() -> None:
    bridge = _load(BRIDGE)
    assert bridge.revision == "157_merge_assistant_conversation_paths"
    assert set(bridge.down_revision) == {"02352b41bcb6", "156_assistant_historical_messages"}


@pytest.mark.parametrize("path", ["current_first", "legacy_first", "existing_156"])
def test_paths_preserve_history_foreign_keys_and_retry_state(path: str) -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()
        _dependencies(connection)
        original_dependencies = {
            table: _rows(connection, table)
            for table in (
                "crm_assistant_actions", "crm_assistant_requests",
                "crm_assistant_turns", "crm_assistant_turn_events",
            )
        }
        if path == "current_first":
            _apply(CURRENT, connection)
        if path == "existing_156":
            _legacy_conversation(connection)
        _apply(LEGACY, connection)
        _existing_message_and_reference(connection)
        original_message = _rows(connection, "crm_assistant_messages")[0]
        original_reference = _rows(connection, "crm_assistant_references")[0]
        _apply(IDENTITY, connection)
        connection.exec_driver_sql("UPDATE crm_assistant_messages SET reference_id = 3 WHERE id = 9")
        connection.commit()
        _apply(HISTORY, connection)
        if path != "current_first":
            _apply(CURRENT, connection)
        _apply(BRIDGE, connection)

        messages = connection.execute(sa.text(
            "SELECT public_id, role, text, task_id, turn_id, seq "
            "FROM crm_assistant_messages ORDER BY seq"
        )).all()
        assert messages == [
            ("ams_existing", "USER", "既有消息", 1, None, 5),
            ("ams_m156_user_turn_1", "USER", "历史用户输入", 1, 1, 6),
            ("ams_m156_assistant_turn_1", "ASSISTANT", "历史助手回复", 1, 1, 7),
            ("ams_m156_user_task_2", "USER", "无回合历史任务", 2, None, 8),
            ("ams_m156_assistant_task_2", "ASSISTANT", "无回合助手回复", 2, None, 9),
        ]
        assert connection.exec_driver_sql(
            "SELECT next_message_seq FROM crm_assistant_conversations"
        ).scalar_one() == 10
        preserved_message = _rows(connection, "crm_assistant_messages")[0]
        assert {key: preserved_message[key] for key in original_message} == original_message
        assert preserved_message["reference_id"] == 3
        assert _rows(connection, "crm_assistant_references") == [original_reference]
        for table, rows in original_dependencies.items():
            assert _rows(connection, table) == rows

        expected_fks = {
            "crm_assistant_tasks": ("fk_assistant_task_conversation_owner", ["conversation_id", "team_id", "user_id"]),
            "crm_assistant_messages": ("fk_assistant_message_conversation_owner", ["conversation_id", "team_id", "user_id"]),
            "crm_assistant_references": ("fk_assistant_reference_conversation_owner", ["conversation_id", "team_id", "user_id"]),
            "crm_assistant_conversation_entries": ("fk_assistant_entry_conversation", ["conversation_id"]),
        }
        inspector = sa.inspect(connection)
        for table, (name, columns) in expected_fks.items():
            fks = [fk for fk in inspector.get_foreign_keys(table) if fk["referred_table"] == "crm_assistant_conversations"]
            assert len(fks) == 1
            assert fks[0]["name"] == name
            assert fks[0]["constrained_columns"] == columns
            assert fks[0]["referred_columns"] == (["id"] if len(columns) == 1 else ["id", "team_id", "user_id"])
        keys = {item["name"]: item["column_names"] for item in inspector.get_unique_constraints("crm_assistant_conversations")}
        assert keys["uq_assistant_conversation_owner"] == ["team_id", "user_id"]
        assert keys["uq_assistant_conversation_owner_legacy"] == ["id", "team_id", "user_id"]
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        connection.exec_driver_sql("UPDATE crm_assistant_conversations SET next_message_seq = 50")
        connection.commit()
        before_retry = {
            table: _rows(connection, table)
            for table in ("crm_assistant_conversations", "crm_assistant_messages", "crm_assistant_references")
        }
        for filename in (IDENTITY, HISTORY, BRIDGE):
            _apply(filename, connection)
        for table, rows in before_retry.items():
            assert _rows(connection, table) == rows
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        if path == "existing_156":
            assert connection.exec_driver_sql("SELECT id FROM crm_assistant_conversations").scalar_one() == 7


def test_bridge_allows_current_orm_insert_without_legacy_timestamp() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        _legacy_conversation(connection)
        _apply(BRIDGE, connection)
        connection.exec_driver_sql(
            "INSERT INTO crm_assistant_conversations "
            "(id, public_id, team_id, user_id, version, created_time) "
            "VALUES (8, 'asc_current_insert', 1, 3, 0, '2026-01-03')"
        )
        assert connection.exec_driver_sql(
            "SELECT public_id FROM crm_assistant_conversations WHERE id = 8"
        ).scalar_one() == "asc_current_insert"


def test_bridge_refuses_duplicate_owners_before_rewrite() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        _legacy_conversation(connection)
        connection.exec_driver_sql(
            "INSERT INTO crm_assistant_conversations "
            "(id, public_id, team_id, user_id, created_time, last_modified_time) "
            "VALUES (8, 'acv_duplicate', 1, 2, '2026-01-02', '2026-01-02')"
        )
        connection.commit()
        before = _rows(connection, "crm_assistant_conversations")
        with pytest.raises(RuntimeError, match="duplicate"):
            _apply(BRIDGE, connection)
        assert _rows(connection, "crm_assistant_conversations") == before


def test_identity_refuses_wrong_named_reference_key() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        _dependencies(connection)
        _apply(LEGACY, connection)
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX uq_assistant_reference_owner "
            "ON crm_assistant_references(public_id)"
        )
        connection.commit()
        with pytest.raises(RuntimeError, match="uq_assistant_reference_owner"):
            _apply(IDENTITY, connection)


def test_legacy_refuses_wrong_named_task_index() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        _dependencies(connection)
        connection.exec_driver_sql(
            "CREATE INDEX idx_assistant_task_conversation ON crm_assistant_tasks(team_id)"
        )
        connection.commit()
        with pytest.raises(RuntimeError, match="idx_assistant_task_conversation"):
            _apply(LEGACY, connection)


@pytest.mark.parametrize("filename", [LEGACY, BRIDGE])
def test_migrations_refuse_unknown_owner_key_shape(filename: str) -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        _dependencies(connection)
        _legacy_conversation(connection, owner_columns="public_id")
        with pytest.raises(RuntimeError, match="owner"):
            _apply(filename, connection)


def test_bridge_refuses_constraint_index_name_collision() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        _legacy_conversation(connection)
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX uq_assistant_conversation_owner "
            "ON crm_assistant_conversations(team_id, user_id)"
        )
        connection.commit()
        with pytest.raises(RuntimeError, match="uq_assistant_conversation_owner"):
            _apply(BRIDGE, connection)
def test_bridge_refuses_unmarked_unique_name_mismatch(monkeypatch) -> None:
    bridge = _load(BRIDGE)

    class _Inspector:
        def get_unique_constraints(self, table_name: str) -> list[dict[str, object]]:
            return [
                {
                    "name": "constraint_name",
                    "column_names": ["conversation_id", "client_request_id"],
                    "duplicates_index": "shared_index",
                }
            ]

        def get_indexes(self, table_name: str) -> list[dict[str, object]]:
            return [
                {
                    "name": "shared_index",
                    "column_names": ["conversation_id", "client_request_id"],
                    "unique": True,
                }
            ]

    monkeypatch.setattr(bridge, "_bind", lambda: object())
    monkeypatch.setattr(bridge.sa, "inspect", lambda _bind: _Inspector())

    with pytest.raises(RuntimeError, match="same named unique object"):
        bridge._unique_objects("crm_assistant_conversation_entries")


def test_bridge_collapses_explicit_mysql_unique_reflection_duplicates(monkeypatch) -> None:
    bridge = _load(BRIDGE)

    class _Inspector:
        def get_unique_constraints(self, table_name: str) -> list[dict[str, object]]:
            assert table_name == "crm_assistant_conversation_entries"
            return [
                {
                    "name": "public_id",
                    "column_names": ["public_id"],
                    "duplicates_index": "public_id",
                },
                {
                    "name": "uq_assistant_conversation_request",
                    "column_names": ["conversation_id", "client_request_id"],
                    "duplicates_index": "uq_assistant_conversation_request",
                },
            ]

        def get_indexes(self, table_name: str) -> list[dict[str, object]]:
            assert table_name == "crm_assistant_conversation_entries"
            return [
                {
                    "name": "idx_assistant_conversation_page",
                    "column_names": ["team_id", "user_id", "conversation_id", "id"],
                    "unique": False,
                },
                {"name": "public_id", "column_names": ["public_id"], "unique": True},
                {
                    "name": "uq_assistant_conversation_request",
                    "column_names": ["conversation_id", "client_request_id"],
                    "unique": True,
                },
            ]

    monkeypatch.setattr(bridge, "_bind", lambda: object())
    monkeypatch.setattr(bridge.sa, "inspect", lambda _bind: _Inspector())

    assert bridge._named_unique(
        "crm_assistant_conversation_entries",
        "uq_assistant_conversation_request",
        ["conversation_id", "client_request_id"],
    ) == {
        "kind": "constraint",
        "name": "uq_assistant_conversation_request",
        "columns": ["conversation_id", "client_request_id"],
        "unique": True,
        "duplicates_index": "uq_assistant_conversation_request",
    }
    assert [item["name"] for item in bridge._unique_objects("crm_assistant_conversation_entries")] == [
        "public_id",
        "uq_assistant_conversation_request",
    ]


def test_legacy_collapses_explicit_mysql_unique_reflection_duplicates(monkeypatch) -> None:
    legacy = _load(LEGACY)

    class _Inspector:
        def get_unique_constraints(self, table_name: str) -> list[dict[str, object]]:
            return [
                {
                    "name": "public_id",
                    "column_names": ["public_id"],
                    "duplicates_index": "public_id",
                }
            ]

        def get_indexes(self, table_name: str) -> list[dict[str, object]]:
            return [
                {"name": "public_id", "column_names": ["public_id"], "unique": True}
            ]

    monkeypatch.setattr(legacy, "_inspector", lambda: _Inspector())

    assert legacy._unique_objects("crm_assistant_conversations") == [
        {
            "kind": "constraint",
            "name": "public_id",
            "columns": ["public_id"],
            "unique": True,
            "duplicates_index": "public_id",
        }
    ]


def test_identity_collapses_explicit_mysql_unique_reflection_duplicates(monkeypatch) -> None:
    identity = _load(IDENTITY)

    class _Inspector:
        def get_unique_constraints(self, table_name: str) -> list[dict[str, object]]:
            return [
                {
                    "name": "public_id",
                    "column_names": ["public_id"],
                    "duplicates_index": "public_id",
                }
            ]

        def get_indexes(self, table_name: str) -> list[dict[str, object]]:
            return [
                {"name": "public_id", "column_names": ["public_id"], "unique": True}
            ]

    monkeypatch.setattr(identity, "_inspector", lambda: _Inspector())

    assert identity._unique_objects("crm_assistant_references") == [
        {
            "kind": "constraint",
            "name": "public_id",
            "columns": ["public_id"],
            "unique": True,
            "duplicates_index": "public_id",
        }
    ]
def test_bridge_normalizes_named_entry_foreign_key() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE crm_assistant_conversations "
            "(id INTEGER PRIMARY KEY)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE crm_assistant_conversation_entries ("
            "id INTEGER PRIMARY KEY, "
            "conversation_id INTEGER NOT NULL, "
            "CONSTRAINT crm_assistant_conversation_entries_ibfk_1 "
            "FOREIGN KEY (conversation_id) "
            "REFERENCES crm_assistant_conversations(id))"
        )
        bridge = _load(BRIDGE)
        bridge.op = Operations(MigrationContext.configure(connection))

        bridge._ensure_entry_conversation_fk()
        connection.commit()

        fks = sa.inspect(connection).get_foreign_keys("crm_assistant_conversation_entries")
        assert fks == [
            {
                "name": "fk_assistant_entry_conversation",
                "constrained_columns": ["conversation_id"],
                "referred_schema": None,
                "referred_table": "crm_assistant_conversations",
                "referred_columns": ["id"],
                "options": {},
            }
        ]


def test_bridge_mysql_entry_foreign_key_renames_in_one_statement(monkeypatch) -> None:
    bridge = _load(BRIDGE)
    calls: list[str] = []

    class _Connection:
        class dialect:
            name = "mysql"

    class _Inspector:
        def get_foreign_keys(self, table_name: str) -> list[dict[str, object]]:
            assert table_name == "crm_assistant_conversation_entries"
            if calls:
                return [
                    {
                        "name": "fk_assistant_entry_conversation",
                        "constrained_columns": ["conversation_id"],
                        "referred_schema": None,
                        "referred_table": "crm_assistant_conversations",
                        "referred_columns": ["id"],
                        "options": {},
                    }
                ]
            return [
                {
                    "name": "crm_assistant_conversation_entries_ibfk_1",
                    "constrained_columns": ["conversation_id"],
                    "referred_schema": None,
                    "referred_table": "crm_assistant_conversations",
                    "referred_columns": ["id"],
                    "options": {},
                }
            ]

    class _Operations:
        def execute(self, statement: object) -> None:
            calls.append(str(statement))

    monkeypatch.setattr(bridge, "_bind", lambda: _Connection())
    monkeypatch.setattr(bridge.sa, "inspect", lambda _bind: _Inspector())
    bridge.op = _Operations()

    bridge._ensure_entry_conversation_fk()

    assert calls == [
        "ALTER TABLE crm_assistant_conversation_entries "
        "DROP FOREIGN KEY `crm_assistant_conversation_entries_ibfk_1`, "
        "ADD CONSTRAINT `fk_assistant_entry_conversation` "
        "FOREIGN KEY (`conversation_id`) "
        "REFERENCES `crm_assistant_conversations` (`id`)"
    ]



@pytest.mark.parametrize("object_kind", ["index", "unique"])
def test_bridge_refuses_wrong_named_entry_object(object_kind: str) -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        _apply(CURRENT, connection)
        if object_kind == "index":
            connection.exec_driver_sql("DROP INDEX idx_assistant_conversation_page")
            connection.exec_driver_sql(
                "CREATE INDEX idx_assistant_conversation_page "
                "ON crm_assistant_conversation_entries(team_id)"
            )
            name = "idx_assistant_conversation_page"
        else:
            with Operations(MigrationContext.configure(connection)).batch_alter_table(
                "crm_assistant_conversation_entries"
            ) as batch:
                batch.drop_constraint("uq_assistant_conversation_request", type_="unique")
                batch.create_unique_constraint("uq_assistant_conversation_request", ["public_id"])
            name = "uq_assistant_conversation_request"
        connection.commit()
        with pytest.raises(RuntimeError, match=name):
            _apply(BRIDGE, connection)


@pytest.mark.parametrize("name", [None, "fk_unknown_conversation"])
def test_bridge_refuses_unrecognized_conversation_foreign_key(name: str | None) -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        _legacy_conversation(connection)
        constraint = f"CONSTRAINT {name} " if name else ""
        connection.exec_driver_sql(
            "CREATE TABLE crm_assistant_tasks (id INTEGER PRIMARY KEY, conversation_id BIGINT, "
            f"{constraint}FOREIGN KEY (conversation_id) REFERENCES crm_assistant_conversations(id))"
        )
        connection.commit()
        original = sa.inspect(connection).get_foreign_keys("crm_assistant_tasks")
        with pytest.raises(RuntimeError, match="foreign key"):
            _apply(BRIDGE, connection)
        assert sa.inspect(connection).get_foreign_keys("crm_assistant_tasks") == original


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("crm_assistant_tasks", "goal"),
        ("crm_assistant_turns", "input_json"),
        ("crm_assistant_actions", "result_json"),
        ("crm_assistant_turn_events", "data_json"),
        ("crm_assistant_messages", "text"),
        ("crm_assistant_conversations", "next_message_seq"),
    ],
)
def test_history_refuses_missing_dependency_column(table: str, column: str) -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        _dependencies(connection)
        _apply(LEGACY, connection)
        _apply(IDENTITY, connection)
        connection.exec_driver_sql(f"ALTER TABLE {table} DROP COLUMN {column}")
        connection.commit()
        with pytest.raises(RuntimeError, match=table):
            _apply(HISTORY, connection)


def test_history_refuses_missing_event_table_even_without_turns() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        _dependencies(connection)
        _apply(LEGACY, connection)
        _apply(IDENTITY, connection)
        connection.exec_driver_sql("DELETE FROM crm_assistant_turns")
        connection.exec_driver_sql("DROP TABLE crm_assistant_turn_events")
        connection.commit()
        with pytest.raises(RuntimeError, match="crm_assistant_turn_events"):
            _apply(HISTORY, connection)

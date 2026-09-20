"""Regression coverage for legacy business journey saved-view migration."""

from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "136_business_journey_saved_views.py"
)
LEGACY_VIEW_KEY = "business-journey-board.board"
TARGET_VIEW_KEY = "business-journeys.list"
MIGRATION_ORIGIN_KEY = "_migration_136_origin"
MIGRATION_ORIGIN_FALLBACK_KEY = "_migration_136_origin_1"


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("business_journey_saved_views_136", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _view_preferences_table(metadata: sa.MetaData) -> sa.Table:
    return sa.Table(
        "crm_view_preferences",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("team_id", sa.Integer, nullable=False),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("view_key", sa.String(100), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("preference_key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(100)),
        sa.Column("is_default", sa.Integer, nullable=False),
        sa.Column("sort_order", sa.Integer),
        sa.Column("config_json", sa.Text, nullable=False),
        sa.Column("created_by", sa.Integer, nullable=False),
        sa.Column("updated_by", sa.Integer, nullable=False),
        sa.UniqueConstraint(
            "team_id",
            "view_key",
            "scope",
            "user_id",
            "preference_key",
            name="uk_view_pref_owner_key",
        ),
    )


def _connection_with_table() -> tuple[sa.Connection, sa.Table]:
    engine = sa.create_engine("sqlite:///:memory:")
    connection = engine.connect()
    metadata = sa.MetaData()
    table = _view_preferences_table(metadata)
    metadata.create_all(connection)
    return connection, table


def _run(connection: sa.Connection, migration: ModuleType, operation: str) -> None:
    context = MigrationContext.configure(connection)
    migration.op = Operations(context)
    getattr(migration, operation)()


def _insert_view(table: sa.Table, connection: sa.Connection, **overrides: object) -> None:
    values: dict[str, object] = {
        "team_id": 1,
        "user_id": 7,
        "view_key": LEGACY_VIEW_KEY,
        "scope": "personal",
        "preference_key": "custom:42",
        "name": "我的看板",
        "is_default": 0,
        "sort_order": 9,
        "config_json": json.dumps(
            {
                "version": 1,
                "columns": [],
                "filters": [{"field": "owner_id", "op": "eq", "value": "me"}],
                "sorts": [{"field": "updated_time", "order": "desc"}],
            }
        ),
        "created_by": 7,
        "updated_by": 7,
    }
    values.update(overrides)
    connection.execute(table.insert().values(**values))


def _rows(table: sa.Table, connection: sa.Connection) -> list[sa.RowMapping]:
    return list(connection.execute(sa.select(table).order_by(table.c.id)).mappings())


def _migration_marker(
    origin: str, row_id: int, original_config: dict[str, object]
) -> dict[str, object]:
    canonical = json.dumps(original_config, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return {
        "origin": origin,
        "row_id": row_id,
        "config_digest": hashlib.sha256(canonical.encode()).hexdigest(),
    }


def test_migration_revision_follows_deal_journey_public_ids() -> None:
    migration = _load_migration()

    assert migration.revision == "136_business_journey_saved_views"
    assert migration.down_revision == "135_deal_journey_public_ids"


def test_upgrade_migrates_legacy_board_view_and_is_idempotent() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    try:
        _insert_view(table, connection)

        _run(connection, migration, "upgrade")
        _run(connection, migration, "upgrade")

        rows = _rows(table, connection)
    finally:
        connection.close()

    assert len(rows) == 1
    row = rows[0]
    config = json.loads(row["config_json"])
    assert row["view_key"] == TARGET_VIEW_KEY
    assert row["name"] == "我的看板"
    assert row["sort_order"] == 9
    assert config["display_mode"] == "board"
    assert config[MIGRATION_ORIGIN_KEY] == _migration_marker(
        "renamed",
        1,
        {
            "version": 1,
            "columns": [],
            "filters": [{"field": "owner_id", "op": "eq", "value": "me"}],
            "sorts": [{"field": "updated_time", "order": "desc"}],
        },
    )
    assert config["filters"] == [{"field": "owner_id", "op": "eq", "value": "me"}]
    assert config["sorts"] == [{"field": "updated_time", "order": "desc"}]


def test_upgrade_merges_collision_into_target_without_replacing_target_identity() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    try:
        _insert_view(table, connection, id=10, name="旧看板", sort_order=99)
        _insert_view(
            table,
            connection,
            id=20,
            view_key=TARGET_VIEW_KEY,
            name="旅程视图",
            sort_order=2,
            config_json=json.dumps(
                {
                    "version": 1,
                    "columns": [{"key": "customer"}],
                    "filters": [{"field": "stage", "op": "eq", "value": "active"}],
                    "sorts": [{"field": "name", "order": "asc"}],
                }
            ),
        )

        _run(connection, migration, "upgrade")

        rows = _rows(table, connection)
    finally:
        connection.close()

    assert len(rows) == 1
    row = rows[0]
    config = json.loads(row["config_json"])
    assert row["id"] == 20
    assert row["view_key"] == TARGET_VIEW_KEY
    assert row["name"] == "旅程视图"
    assert row["sort_order"] == 2
    assert config == {
        "version": 1,
        "columns": [{"key": "customer"}],
        "filters": [{"field": "stage", "op": "eq", "value": "active"}],
        "sorts": [{"field": "name", "order": "asc"}],
        "display_mode": "board",
        MIGRATION_ORIGIN_KEY: _migration_marker(
            "collision",
            20,
            {
                "version": 1,
                "columns": [{"key": "customer"}],
                "filters": [{"field": "stage", "op": "eq", "value": "active"}],
                "sorts": [{"field": "name", "order": "asc"}],
            },
        ),
    }


def test_downgrade_restores_collision_target_config_without_rekeying() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    original_config = {
        "version": 1,
        "columns": [{"key": "customer"}],
        "filters": [{"field": "stage", "op": "eq", "value": "active"}],
        MIGRATION_ORIGIN_KEY: {"origin": "renamed", "row_id": 20},
        "_migration_136_origin_9": {"origin": "collision", "row_id": 20},
    }
    try:
        _insert_view(table, connection, id=10)
        _insert_view(
            table,
            connection,
            id=20,
            view_key=TARGET_VIEW_KEY,
            config_json=json.dumps(original_config),
        )
        _run(connection, migration, "upgrade")

        upgraded = _rows(table, connection)
        upgraded_config = json.loads(upgraded[0]["config_json"])
        assert upgraded_config[MIGRATION_ORIGIN_KEY] == {"origin": "renamed", "row_id": 20}
        assert upgraded_config["_migration_136_origin_9"] == {
            "origin": "collision",
            "row_id": 20,
        }
        assert upgraded_config[MIGRATION_ORIGIN_FALLBACK_KEY] == _migration_marker(
            "collision", 20, original_config
        )

        _run(connection, migration, "downgrade")

        rows = _rows(table, connection)
    finally:
        connection.close()

    assert len(rows) == 1
    assert rows[0]["id"] == 20
    assert rows[0]["view_key"] == TARGET_VIEW_KEY
    assert json.loads(rows[0]["config_json"]) == original_config


def test_upgrade_does_not_override_existing_target_display_mode() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    original_config_json = '{"version": 1, "columns": [], "display_mode": "table"}'
    try:
        _insert_view(table, connection, id=10)
        _insert_view(
            table,
            connection,
            id=20,
            view_key=TARGET_VIEW_KEY,
            config_json=original_config_json,
        )

        _run(connection, migration, "upgrade")
        _run(connection, migration, "downgrade")

        rows = _rows(table, connection)
    finally:
        connection.close()

    assert len(rows) == 1
    assert rows[0]["config_json"] == original_config_json


def test_upgrade_preserves_malformed_collision_target_config_bytes() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    malformed_config = '{"version": 1, "columns": ['
    try:
        _insert_view(table, connection, id=10)
        _insert_view(
            table,
            connection,
            id=20,
            view_key=TARGET_VIEW_KEY,
            config_json=malformed_config,
        )

        _run(connection, migration, "upgrade")

        rows = _rows(table, connection)
    finally:
        connection.close()

    assert len(rows) == 1
    assert rows[0]["id"] == 20
    assert rows[0]["view_key"] == TARGET_VIEW_KEY
    assert rows[0]["config_json"] == malformed_config


def test_upgrade_marker_does_not_duplicate_large_legacy_config() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    original_config = {
        "version": 1,
        "columns": [],
        "filters": [{"field": "notes", "op": "eq", "value": "x" * 40_000}],
    }
    original_config_json = json.dumps(original_config)
    try:
        _insert_view(table, connection, config_json=original_config_json)

        _run(connection, migration, "upgrade")

        upgraded_config_json = _rows(table, connection)[0]["config_json"]
    finally:
        connection.close()

    assert len(upgraded_config_json) < len(original_config_json) + 500


def test_upgrade_recovers_invalid_legacy_config() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    try:
        _insert_view(table, connection, config_json="not-json")

        _run(connection, migration, "upgrade")

        row = _rows(table, connection)[0]
    finally:
        connection.close()

    assert row["view_key"] == TARGET_VIEW_KEY
    assert json.loads(row["config_json"]) == {
        "version": 1,
        "columns": [],
        "display_mode": "board",
        MIGRATION_ORIGIN_KEY: _migration_marker(
            "renamed", 1, {"version": 1, "columns": []}
        ),
    }


def test_downgrade_restores_legacy_key_and_removes_display_mode() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    try:
        _insert_view(table, connection)
        _run(connection, migration, "upgrade")

        _run(connection, migration, "downgrade")

        row = _rows(table, connection)[0]
    finally:
        connection.close()

    config = json.loads(row["config_json"])
    assert row["view_key"] == LEGACY_VIEW_KEY
    assert "display_mode" not in config
    assert MIGRATION_ORIGIN_KEY not in config
    assert config["filters"] == [{"field": "owner_id", "op": "eq", "value": "me"}]



def test_renamed_source_preserves_existing_migration_marker_keys() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    original_config = {
        "version": 1,
        "columns": [],
        MIGRATION_ORIGIN_KEY: {"origin": "collision", "row_id": 1},
        "_migration_136_origin_4": {"origin": "renamed", "row_id": 1},
    }
    try:
        _insert_view(table, connection, config_json=json.dumps(original_config))

        _run(connection, migration, "upgrade")

        upgraded = _rows(table, connection)[0]
        upgraded_config = json.loads(upgraded["config_json"])
        assert upgraded_config[MIGRATION_ORIGIN_KEY] == {"origin": "collision", "row_id": 1}
        assert upgraded_config["_migration_136_origin_4"] == {
            "origin": "renamed",
            "row_id": 1,
        }
        assert upgraded_config[MIGRATION_ORIGIN_FALLBACK_KEY] == _migration_marker(
            "renamed", 1, original_config
        )
        _run(connection, migration, "downgrade")

        row = _rows(table, connection)[0]
    finally:
        connection.close()

    assert row["view_key"] == LEGACY_VIEW_KEY
    assert json.loads(row["config_json"]) == original_config

def test_downgrade_keeps_renamed_target_key_when_legacy_collision_exists() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    try:
        _insert_view(table, connection, id=10)
        _insert_view(
            table,
            connection,
            id=20,
            view_key=TARGET_VIEW_KEY,
            config_json=json.dumps(
                {
                    "version": 1,
                    "columns": [],
                    "display_mode": "board",
                    MIGRATION_ORIGIN_KEY: _migration_marker(
                        "renamed", 20, {"version": 1, "columns": []}
                    ),
                }
            ),
        )

        _run(connection, migration, "downgrade")

        rows = _rows(table, connection)
    finally:
        connection.close()

    assert [row["view_key"] for row in rows] == [LEGACY_VIEW_KEY, TARGET_VIEW_KEY]
    assert json.loads(rows[1]["config_json"]) == {"version": 1, "columns": []}

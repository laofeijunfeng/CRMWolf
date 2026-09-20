"""Regression coverage for legacy business journey saved-view migration."""

from __future__ import annotations

import importlib.util
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
    }


def test_upgrade_does_not_override_existing_target_display_mode() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    try:
        _insert_view(table, connection, id=10)
        _insert_view(
            table,
            connection,
            id=20,
            view_key=TARGET_VIEW_KEY,
            config_json=json.dumps({"version": 1, "columns": [], "display_mode": "table"}),
        )

        _run(connection, migration, "upgrade")

        rows = _rows(table, connection)
    finally:
        connection.close()

    assert len(rows) == 1
    assert json.loads(rows[0]["config_json"])["display_mode"] == "table"


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
    assert config["filters"] == [{"field": "owner_id", "op": "eq", "value": "me"}]


def test_downgrade_keeps_target_key_when_legacy_collision_exists() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    try:
        _insert_view(table, connection, id=10)
        _insert_view(
            table,
            connection,
            id=20,
            view_key=TARGET_VIEW_KEY,
            config_json=json.dumps({"version": 1, "columns": [], "display_mode": "board"}),
        )

        _run(connection, migration, "downgrade")

        rows = _rows(table, connection)
    finally:
        connection.close()

    assert [row["view_key"] for row in rows] == [LEGACY_VIEW_KEY, TARGET_VIEW_KEY]
    assert "display_mode" not in json.loads(rows[1]["config_json"])

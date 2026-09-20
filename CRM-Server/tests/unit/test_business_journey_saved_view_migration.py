"""Regression coverage for legacy business journey saved-view migration."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.schemas.view_preference import ViewPreferenceConfig


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "136_business_journey_saved_views.py"
)
LEGACY_VIEW_KEY = "business-journey-board.board"
TARGET_VIEW_KEY = "business-journeys.list"
ORIGIN_TABLE_NAME = "_migration_136_saved_view_origins"


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


def _origin_rows(connection: sa.Connection) -> list[sa.RowMapping]:
    table = sa.Table(ORIGIN_TABLE_NAME, sa.MetaData(), autoload_with=connection)
    return list(connection.execute(sa.select(table).order_by(table.c.preference_id)).mappings())


def _origin_table_exists(connection: sa.Connection) -> bool:
    return sa.inspect(connection).has_table(ORIGIN_TABLE_NAME)


def test_migration_revision_follows_deal_journey_public_ids() -> None:
    migration = _load_migration()

    assert migration.revision == "136_business_journey_saved_views"
    assert migration.down_revision == "135_deal_journey_public_ids"


def test_upgrade_migrates_legacy_board_view_and_is_idempotent() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    original_config_json = '{ "version": 1, "columns": [], "filters": [], "sorts": [] }'
    try:
        _insert_view(table, connection, config_json=original_config_json)

        _run(connection, migration, "upgrade")
        _run(connection, migration, "upgrade")

        rows = _rows(table, connection)
        origins = _origin_rows(connection)
    finally:
        connection.close()

    assert len(rows) == 1
    row = rows[0]
    assert row["view_key"] == TARGET_VIEW_KEY
    assert row["name"] == "我的看板"
    assert row["sort_order"] == 9
    assert json.loads(row["config_json"]) == {
        "version": 1,
        "columns": [],
        "filters": [],
        "sorts": [],
        "display_mode": "board",
    }
    assert len(origins) == 1
    assert origins[0]["preference_id"] == row["id"]
    assert origins[0]["origin"] == "renamed"
    assert origins[0]["original_config_json"] == original_config_json
    assert len(origins[0]["migrated_config_hash"]) == 64


def test_upgrade_merges_collision_into_target_without_replacing_target_identity() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    target_config_json = (
        '{"version":1,"columns":[{"key":"customer"}],'
        '"filters":[],"sorts":[],"_migration_136_forged":"user-value"}'
    )
    try:
        _insert_view(table, connection, id=10, name="旧看板", sort_order=99)
        _insert_view(
            table,
            connection,
            id=20,
            view_key=TARGET_VIEW_KEY,
            name="旅程视图",
            sort_order=2,
            config_json=target_config_json,
        )

        _run(connection, migration, "upgrade")

        rows = _rows(table, connection)
        origins = _origin_rows(connection)
    finally:
        connection.close()

    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == 20
    assert row["view_key"] == TARGET_VIEW_KEY
    assert row["name"] == "旅程视图"
    assert row["sort_order"] == 2
    assert json.loads(row["config_json"]) == {
        "version": 1,
        "columns": [{"key": "customer"}],
        "filters": [],
        "sorts": [],
        "_migration_136_forged": "user-value",
        "display_mode": "board",
    }
    assert len(origins) == 1
    assert origins[0]["preference_id"] == 20
    assert origins[0]["origin"] == "collision"
    assert origins[0]["original_config_json"] == target_config_json


def test_downgrade_restores_collision_target_exactly_without_rekeying() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    target_config_json = '{ "version": 1, "columns": [], "filters": [], "sorts": [] }'
    try:
        _insert_view(table, connection, id=10)
        _insert_view(
            table,
            connection,
            id=20,
            view_key=TARGET_VIEW_KEY,
            config_json=target_config_json,
        )
        _run(connection, migration, "upgrade")

        _run(connection, migration, "downgrade")

        rows = _rows(table, connection)
        origin_table_exists = _origin_table_exists(connection)
    finally:
        connection.close()

    assert len(rows) == 1
    assert rows[0]["id"] == 20
    assert rows[0]["view_key"] == TARGET_VIEW_KEY
    assert rows[0]["config_json"] == target_config_json
    assert origin_table_exists is False


def test_upgrade_does_not_touch_malformed_collision_target_or_record_provenance() -> None:
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
        origins = _origin_rows(connection)
    finally:
        connection.close()

    assert len(rows) == 1
    assert rows[0]["id"] == 20
    assert rows[0]["config_json"] == malformed_config
    assert origins == []


def test_upgrade_does_not_touch_existing_target_display_mode_or_record_provenance() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    original_config_json = (
        '{"version":1,"columns":[],"display_mode":"table",'
        '"_migration_136_origin":{"origin":"renamed"}}'
    )
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
        origins = _origin_rows(connection)
        _run(connection, migration, "downgrade")

        rows = _rows(table, connection)
    finally:
        connection.close()

    assert len(rows) == 1
    assert rows[0]["view_key"] == TARGET_VIEW_KEY
    assert rows[0]["config_json"] == original_config_json
    assert origins == []


def test_downgrade_restores_renamed_source_exact_bytes_and_user_migration_keys() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    original_config_json = (
        '{ "version": 1, "columns": [], "filters": [], "sorts": [], '
        '"_migration_136_origin": {"origin": "collision", "row_id": 1} }'
    )
    try:
        _insert_view(table, connection, config_json=original_config_json)
        _run(connection, migration, "upgrade")

        upgraded = _rows(table, connection)[0]
        assert json.loads(upgraded["config_json"])["_migration_136_origin"] == {
            "origin": "collision",
            "row_id": 1,
        }

        _run(connection, migration, "downgrade")

        row = _rows(table, connection)[0]
    finally:
        connection.close()

    assert row["view_key"] == LEGACY_VIEW_KEY
    assert row["config_json"] == original_config_json


def test_downgrade_survives_normal_config_schema_round_trip() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    original_config_json = '{"version":1,"columns":[],"filters":[],"sorts":[]}'
    try:
        _insert_view(table, connection, config_json=original_config_json)
        _run(connection, migration, "upgrade")

        row = _rows(table, connection)[0]
        round_tripped_config_json = ViewPreferenceConfig(
            **json.loads(row["config_json"])
        ).model_dump_json()
        connection.execute(
            table.update()
            .where(table.c.id == row["id"])
            .values(config_json=round_tripped_config_json)
        )

        _run(connection, migration, "downgrade")

        downgraded = _rows(table, connection)[0]
    finally:
        connection.close()

    assert downgraded["view_key"] == LEGACY_VIEW_KEY
    assert downgraded["config_json"] == original_config_json


def test_downgrade_restores_coercible_legacy_config_after_schema_round_trip() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    original_config_json = (
        '{"version":"1","columns":[{"key":"customer","order":"2",'
        '"visible":"false","width":"120","fixed":null,'
        '"unknown_column":"drop-me"}],"sorts":[],"filters":[],'
        '"unknown_top":"drop-me"}'
    )
    try:
        _insert_view(table, connection, config_json=original_config_json)
        _run(connection, migration, "upgrade")

        row = _rows(table, connection)[0]
        round_tripped_config_json = ViewPreferenceConfig(
            **json.loads(row["config_json"])
        ).model_dump_json()
        connection.execute(
            table.update()
            .where(table.c.id == row["id"])
            .values(config_json=round_tripped_config_json)
        )

        _run(connection, migration, "downgrade")

        downgraded = _rows(table, connection)[0]
    finally:
        connection.close()

    assert downgraded["view_key"] == LEGACY_VIEW_KEY
    assert downgraded["config_json"] == original_config_json


def test_downgrade_restores_coercible_collision_config_after_schema_round_trip() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    original_target_config_json = (
        '{"version":"1","columns":[{"key":"customer","order":"2",'
        '"visible":"false","width":"120","fixed":null,'
        '"unknown_column":"drop-me"}],"sorts":[],"filters":[],'
        '"unknown_top":"drop-me"}'
    )
    try:
        _insert_view(table, connection, id=10)
        _insert_view(
            table,
            connection,
            id=20,
            view_key=TARGET_VIEW_KEY,
            config_json=original_target_config_json,
        )
        _run(connection, migration, "upgrade")

        row = _rows(table, connection)[0]
        round_tripped_config_json = ViewPreferenceConfig(
            **json.loads(row["config_json"])
        ).model_dump_json()
        connection.execute(
            table.update()
            .where(table.c.id == row["id"])
            .values(config_json=round_tripped_config_json)
        )

        _run(connection, migration, "downgrade")

        downgraded = _rows(table, connection)[0]
    finally:
        connection.close()

    assert downgraded["view_key"] == TARGET_VIEW_KEY
    assert downgraded["config_json"] == original_target_config_json


def test_downgrade_preserves_known_field_change_after_schema_round_trip() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    original_config_json = (
        '{"version":"1","columns":[{"key":"customer","order":"2",'
        '"visible":"false","width":"120","unknown_column":"drop-me"}],'
        '"sorts":[],"filters":[],"unknown_top":"drop-me"}'
    )
    try:
        _insert_view(table, connection, config_json=original_config_json)
        _run(connection, migration, "upgrade")

        row = _rows(table, connection)[0]
        round_tripped_config = json.loads(
            ViewPreferenceConfig(
                **json.loads(row["config_json"])
            ).model_dump_json()
        )
        round_tripped_config["columns"][0]["width"] = 121
        changed_config_json = json.dumps(round_tripped_config, separators=(",", ":"))
        connection.execute(
            table.update()
            .where(table.c.id == row["id"])
            .values(config_json=changed_config_json)
        )

        _run(connection, migration, "downgrade")

        downgraded = _rows(table, connection)[0]
    finally:
        connection.close()

    assert downgraded["view_key"] == TARGET_VIEW_KEY
    assert downgraded["config_json"] == changed_config_json


def test_downgrade_preserves_migrated_row_changed_to_table_mode() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    try:
        _insert_view(table, connection)
        _run(connection, migration, "upgrade")

        row = _rows(table, connection)[0]
        table_config = json.loads(row["config_json"])
        table_config["display_mode"] = "table"
        table_config_json = json.dumps(table_config)
        connection.execute(
            table.update().where(table.c.id == row["id"]).values(config_json=table_config_json)
        )

        _run(connection, migration, "downgrade")

        downgraded = _rows(table, connection)[0]
    finally:
        connection.close()

    assert downgraded["view_key"] == TARGET_VIEW_KEY
    assert downgraded["config_json"] == table_config_json


def test_downgrade_preserves_semantically_changed_board_config() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    try:
        _insert_view(table, connection)
        _run(connection, migration, "upgrade")

        row = _rows(table, connection)[0]
        changed_config = json.loads(row["config_json"])
        changed_config["filters"].append({"field": "stage", "op": "eq", "value": "won"})
        changed_config_json = json.dumps(changed_config)
        connection.execute(
            table.update().where(table.c.id == row["id"]).values(config_json=changed_config_json)
        )

        _run(connection, migration, "downgrade")

        downgraded = _rows(table, connection)[0]
    finally:
        connection.close()

    assert downgraded["view_key"] == TARGET_VIEW_KEY
    assert downgraded["config_json"] == changed_config_json


def test_upgrade_recovers_invalid_legacy_config_and_downgrade_restores_exact_bytes() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    original_config_json = "not-json"
    try:
        _insert_view(table, connection, config_json=original_config_json)

        _run(connection, migration, "upgrade")

        upgraded = _rows(table, connection)[0]
        origins = _origin_rows(connection)
        assert json.loads(upgraded["config_json"]) == {
            "version": 1,
            "columns": [],
            "display_mode": "board",
        }
        assert origins[0]["original_config_json"] == original_config_json

        _run(connection, migration, "downgrade")

        downgraded = _rows(table, connection)[0]
    finally:
        connection.close()

    assert downgraded["view_key"] == LEGACY_VIEW_KEY
    assert downgraded["config_json"] == original_config_json


def test_downgrade_skips_missing_migrated_target_and_drops_provenance_table() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    try:
        _insert_view(table, connection)
        _run(connection, migration, "upgrade")
        migrated_id = _rows(table, connection)[0]["id"]
        connection.execute(table.delete().where(table.c.id == migrated_id))

        _run(connection, migration, "downgrade")

        rows = _rows(table, connection)
        origin_table_exists = _origin_table_exists(connection)
    finally:
        connection.close()

    assert rows == []
    assert origin_table_exists is False


def test_downgrade_keeps_renamed_target_key_when_legacy_unique_key_is_occupied() -> None:
    migration = _load_migration()
    connection, table = _connection_with_table()
    original_config_json = '{"version":1,"columns":[],"filters":[],"sorts":[]}'
    try:
        _insert_view(table, connection, id=20, config_json=original_config_json)
        _run(connection, migration, "upgrade")
        _insert_view(table, connection, id=30, name="new legacy view")

        _run(connection, migration, "downgrade")

        rows = _rows(table, connection)
    finally:
        connection.close()

    assert [row["view_key"] for row in rows] == [TARGET_VIEW_KEY, LEGACY_VIEW_KEY]
    assert rows[0]["config_json"] == original_config_json

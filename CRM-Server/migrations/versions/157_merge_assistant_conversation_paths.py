"""Bridge recovered assistant history into the current conversation schema.

Revision ID: 157_merge_assistant_conversation_paths
Revises: 02352b41bcb6, 156_assistant_historical_messages

The recovered 154-156 path used a different conversation contract. This
revision never mutates those message/task/action/turn rows: it renames the old
parent table, lets existing foreign keys follow that archive, creates the
current ORM schema at the original name, and seeds one historical entry per
task.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "157_merge_assistant_conversation_paths"
down_revision: str | tuple[str, str] | None = (
    "02352b41bcb6",
    "156_assistant_historical_messages",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONVERSATION_TABLE = "crm_assistant_conversations"
_ARCHIVE_TABLE = "crm_assistant_conversations_legacy_156"
_ENTRY_TABLE = "crm_assistant_conversation_entries"
_MAP_TABLE = "crm_assistant_conversation_legacy_map"
_ENTRY_INDEX = "idx_assistant_conversation_page"
_MAP_INDEX = "idx_assistant_conversation_legacy_owner"

_LEGACY_REQUIRED = {
    "id",
    "public_id",
    "team_id",
    "user_id",
    "created_time",
    "last_modified_time",
    "next_message_seq",
}
_CURRENT_REQUIRED = {
    "id",
    "public_id",
    "team_id",
    "user_id",
    "version",
    "focused_task_public_id",
    "pending_choice_id",
    "busy_entry_id",
    "lease_expires_at",
    "created_time",
}
_ENTRY_REQUIRED = {
    "id",
    "public_id",
    "conversation_id",
    "team_id",
    "user_id",
    "client_request_id",
    "input_fingerprint",
    "user_text",
    "command_json",
    "decision_json",
    "state",
    "task_public_id",
    "turn_public_id",
    "reply_text",
    "task_snapshot_json",
    "created_time",
}
_ORIGINAL_COUNT_TABLES = (
    "crm_assistant_messages",
    "crm_assistant_tasks",
    "crm_assistant_actions",
    "crm_assistant_turns",
    "crm_assistant_turn_events",
    "crm_assistant_requests",
    "crm_assistant_references",
)


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _columns(table_name: str) -> set[str]:
    return {str(column["name"]) for column in _inspector().get_columns(table_name)}


def _require_columns(table_name: str, required: set[str]) -> None:
    if not _table_exists(table_name):
        raise RuntimeError(f"assistant migration requires table {table_name}")
    missing = required - _columns(table_name)
    if missing:
        raise RuntimeError(f"assistant migration table {table_name} is missing columns: " + ", ".join(sorted(missing)))


def _schema_kind(table_name: str) -> str:
    columns = _columns(table_name)
    if columns >= _CURRENT_REQUIRED and not ({"last_modified_time", "next_message_seq"} & columns):
        return "current"
    if columns >= _LEGACY_REQUIRED and "version" not in columns:
        return "legacy"
    return "unknown"


def _row_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    connection = op.get_bind()
    for table_name in (_CONVERSATION_TABLE, *_ORIGINAL_COUNT_TABLES):
        actual_table = (
            _ARCHIVE_TABLE if table_name == _CONVERSATION_TABLE and _table_exists(_ARCHIVE_TABLE) else table_name
        )
        if _table_exists(actual_table):
            counts[table_name] = int(connection.execute(sa.text(f"SELECT COUNT(*) FROM `{actual_table}`")).scalar_one())
    return counts


def _assert_original_counts(before: dict[str, int]) -> None:
    connection = op.get_bind()
    for table_name, expected in before.items():
        actual_table = _ARCHIVE_TABLE if table_name == _CONVERSATION_TABLE else table_name
        if not _table_exists(actual_table):
            raise RuntimeError(f"assistant migration lost original table {actual_table}")
        actual = int(connection.execute(sa.text(f"SELECT COUNT(*) FROM `{actual_table}`")).scalar_one())
        if actual != expected:
            raise RuntimeError(f"assistant migration changed row count for {actual_table}: {expected} -> {actual}")


def _create_current_conversation_table() -> None:
    if _table_exists(_CONVERSATION_TABLE):
        if _schema_kind(_CONVERSATION_TABLE) != "current":
            raise RuntimeError("assistant current conversation table has unexpected schema")
        return
    op.create_table(
        _CONVERSATION_TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("public_id", sa.String(64), nullable=False, unique=True),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("focused_task_public_id", sa.String(64), nullable=True),
        sa.Column("pending_choice_id", sa.String(64), nullable=True),
        sa.Column("busy_entry_id", sa.String(64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_time", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "team_id",
            "user_id",
            name="uq_assistant_conversation_owner",
        ),
    )


def _create_entry_table() -> None:
    if _table_exists(_ENTRY_TABLE):
        _require_columns(_ENTRY_TABLE, _ENTRY_REQUIRED)
    else:
        op.create_table(
            _ENTRY_TABLE,
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("public_id", sa.String(64), nullable=False, unique=True),
            sa.Column(
                "conversation_id",
                sa.BigInteger(),
                sa.ForeignKey(
                    f"{_CONVERSATION_TABLE}.id",
                    name="fk_assistant_entry_conversation",
                ),
                nullable=False,
            ),
            sa.Column("team_id", sa.BigInteger(), nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("client_request_id", sa.String(128), nullable=False),
            sa.Column("input_fingerprint", sa.String(64), nullable=False),
            sa.Column("user_text", sa.Text(), nullable=False),
            sa.Column("command_json", sa.JSON(), nullable=False),
            sa.Column("decision_json", sa.JSON(), nullable=False),
            sa.Column("state", sa.String(20), nullable=False),
            sa.Column("task_public_id", sa.String(64), nullable=True),
            sa.Column("turn_public_id", sa.String(64), nullable=True),
            sa.Column("reply_text", sa.Text(), nullable=True),
            sa.Column("task_snapshot_json", sa.JSON(), nullable=True),
            sa.Column("created_time", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "conversation_id",
                "client_request_id",
                name="uq_assistant_conversation_request",
            ),
        )
    if not any(index.get("name") == _ENTRY_INDEX for index in _inspector().get_indexes(_ENTRY_TABLE)):
        op.create_index(
            _ENTRY_INDEX,
            _ENTRY_TABLE,
            ["team_id", "user_id", "conversation_id", "id"],
        )


def _create_map_table() -> None:
    if not _table_exists(_MAP_TABLE):
        op.create_table(
            _MAP_TABLE,
            sa.Column("legacy_conversation_id", sa.BigInteger(), primary_key=True),
            sa.Column("legacy_public_id", sa.String(64), nullable=False, unique=True),
            sa.Column(
                "conversation_id",
                sa.BigInteger(),
                sa.ForeignKey(
                    f"{_CONVERSATION_TABLE}.id",
                    name="fk_assistant_legacy_map_conversation",
                ),
                nullable=False,
            ),
            sa.Column("canonical_public_id", sa.String(64), nullable=False),
            sa.Column("team_id", sa.BigInteger(), nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("legacy_created_time", sa.DateTime(), nullable=False),
            sa.Column("legacy_last_modified_time", sa.DateTime(), nullable=False),
            sa.Column("created_time", sa.DateTime(), nullable=False),
        )
    _require_columns(
        _MAP_TABLE,
        {
            "legacy_conversation_id",
            "legacy_public_id",
            "conversation_id",
            "canonical_public_id",
            "team_id",
            "user_id",
            "legacy_created_time",
            "legacy_last_modified_time",
            "created_time",
        },
    )
    if not any(index.get("name") == _MAP_INDEX for index in _inspector().get_indexes(_MAP_TABLE)):
        op.create_index(
            _MAP_INDEX,
            _MAP_TABLE,
            ["team_id", "user_id", "legacy_conversation_id"],
        )


def _next_id(table_name: str) -> int:
    return int(op.get_bind().execute(sa.text(f"SELECT COALESCE(MAX(id), 0) + 1 FROM `{table_name}`")).scalar_one())


def _fingerprint(payload: dict[str, object]) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _canonical_for_owner(
    conversations: sa.TableClause,
    *,
    team_id: int,
    user_id: int,
) -> tuple[int, str]:
    connection = op.get_bind()
    rows = (
        connection.execute(
            sa.select(
                conversations.c.id,
                conversations.c.public_id,
                conversations.c.version,
                conversations.c.focused_task_public_id,
                conversations.c.pending_choice_id,
                conversations.c.busy_entry_id,
                conversations.c.lease_expires_at,
            ).where(
                conversations.c.team_id == team_id,
                conversations.c.user_id == user_id,
            )
        )
        .mappings()
        .all()
    )
    if len(rows) > 1:
        raise RuntimeError(f"assistant migration found duplicate canonical owner {team_id}/{user_id}")
    if rows:
        row = rows[0]
        if (
            any(
                row[key] is not None
                for key in (
                    "focused_task_public_id",
                    "pending_choice_id",
                    "busy_entry_id",
                    "lease_expires_at",
                )
            )
            or int(row["version"]) != 0
        ):
            raise RuntimeError("assistant migration would merge a canonical conversation with active state")
        return int(row["id"]), str(row["public_id"])

    public_id = f"asc_legacy_{team_id}_{user_id}"
    collision = connection.execute(sa.select(conversations.c.id).where(conversations.c.public_id == public_id)).first()
    if collision is not None:
        raise RuntimeError("assistant canonical public id collision")
    canonical_id = _next_id(_CONVERSATION_TABLE)
    connection.execute(
        conversations.insert().values(
            id=canonical_id,
            public_id=public_id,
            team_id=team_id,
            user_id=user_id,
            version=0,
            focused_task_public_id=None,
            pending_choice_id=None,
            busy_entry_id=None,
            lease_expires_at=None,
            created_time=datetime.now(),
        )
    )
    return canonical_id, public_id


def _bridge_owners(
    archive: sa.TableClause,
    conversations: sa.TableClause,
    mapping: sa.TableClause,
) -> None:
    connection = op.get_bind()
    legacy_rows = (
        connection.execute(
            sa.select(
                archive.c.id,
                archive.c.public_id,
                archive.c.team_id,
                archive.c.user_id,
                archive.c.created_time,
                archive.c.last_modified_time,
            ).order_by(
                archive.c.team_id,
                archive.c.user_id,
                archive.c.created_time,
                archive.c.id,
            )
        )
        .mappings()
        .all()
    )
    if not legacy_rows:
        return

    for row in legacy_rows:
        legacy_id = int(row["id"])
        team_id = int(row["team_id"])
        user_id = int(row["user_id"])
        mapped = (
            connection.execute(
                sa.select(
                    mapping.c.conversation_id,
                    mapping.c.canonical_public_id,
                    mapping.c.team_id,
                    mapping.c.user_id,
                ).where(mapping.c.legacy_conversation_id == legacy_id)
            )
            .mappings()
            .first()
        )
        if mapped is not None:
            if int(mapped["team_id"]) != team_id or int(mapped["user_id"]) != user_id:
                raise RuntimeError("assistant legacy conversation mapping changed owners")
            current = connection.execute(
                sa.select(conversations.c.id, conversations.c.public_id).where(
                    conversations.c.id == int(mapped["conversation_id"]),
                    conversations.c.team_id == team_id,
                    conversations.c.user_id == user_id,
                )
            ).first()
            if current is None or str(current.public_id) != str(mapped["canonical_public_id"]):
                raise RuntimeError("assistant legacy conversation mapping is incomplete")
            continue

        canonical_id, canonical_public_id = _canonical_for_owner(
            conversations,
            team_id=team_id,
            user_id=user_id,
        )
        connection.execute(
            mapping.insert().values(
                legacy_conversation_id=legacy_id,
                legacy_public_id=str(row["public_id"]),
                conversation_id=canonical_id,
                canonical_public_id=canonical_public_id,
                team_id=team_id,
                user_id=user_id,
                legacy_created_time=row["created_time"],
                legacy_last_modified_time=row["last_modified_time"],
                created_time=datetime.now(),
            )
        )

    map_count = int(connection.execute(sa.select(sa.func.count()).select_from(mapping)).scalar_one())
    if map_count != len(legacy_rows):
        raise RuntimeError(f"assistant legacy mapping is incomplete: {map_count}/{len(legacy_rows)}")
    owner_pairs = (
        sa.select(archive.c.team_id, archive.c.user_id).group_by(archive.c.team_id, archive.c.user_id).subquery()
    )
    owner_count = int(connection.execute(sa.select(sa.func.count()).select_from(owner_pairs)).scalar_one())
    canonical_count = int(connection.execute(sa.select(sa.func.count()).select_from(conversations)).scalar_one())
    if canonical_count != owner_count:
        raise RuntimeError(
            f"assistant migration found unexpected canonical conversations: {canonical_count}/{owner_count}"
        )


def _backfill_entries(
    archive: sa.TableClause,
    mapping: sa.TableClause,
    entries: sa.TableClause,
    tasks: sa.TableClause,
) -> None:
    connection = op.get_bind()
    task_count = int(connection.execute(sa.select(sa.func.count()).select_from(tasks)).scalar_one())
    task_rows = (
        connection.execute(
            sa.select(
                tasks.c.id,
                tasks.c.public_id,
                tasks.c.team_id,
                tasks.c.user_id,
                tasks.c.conversation_id,
                tasks.c.goal,
                tasks.c.created_time,
            )
        )
        .mappings()
        .all()
    )
    if task_count != len(task_rows):
        raise RuntimeError("assistant task count changed during migration")

    resolved: list[tuple[int, datetime, int, Any]] = []
    for task in task_rows:
        conversation_id = task["conversation_id"]
        if conversation_id is None:
            raise RuntimeError(f"assistant task {task['public_id']} has no legacy conversation identity")
        legacy = (
            connection.execute(
                sa.select(
                    archive.c.team_id,
                    archive.c.user_id,
                    mapping.c.conversation_id,
                )
                .select_from(
                    archive.join(
                        mapping,
                        mapping.c.legacy_conversation_id == archive.c.id,
                    )
                )
                .where(archive.c.id == int(conversation_id))
            )
            .mappings()
            .first()
        )
        if legacy is None:
            raise RuntimeError(f"assistant task {task['public_id']} references an unmapped conversation")
        if int(legacy["team_id"]) != int(task["team_id"]) or int(legacy["user_id"]) != int(task["user_id"]):
            raise RuntimeError(f"assistant task {task['public_id']} has mismatched conversation owners")
        resolved.append(
            (
                int(legacy["conversation_id"]),
                task["created_time"],
                int(task["id"]),
                task,
            )
        )

    for canonical_id, created_time, _task_id, task in sorted(
        resolved,
        key=lambda item: (item[0], item[1], item[2]),
    ):
        public_id = str(task["public_id"])
        client_request_id = f"legacy-{public_id}"
        existing = (
            connection.execute(
                sa.select(entries.c.id, entries.c.task_public_id).where(
                    entries.c.conversation_id == canonical_id,
                    entries.c.client_request_id == client_request_id,
                )
            )
            .mappings()
            .first()
        )
        if existing is not None:
            if existing["task_public_id"] != public_id:
                raise RuntimeError("assistant legacy entry identity changed")
            continue

        entry_public_id = f"acm_legacy_{int(task['id'])}"
        collision = connection.execute(sa.select(entries.c.id).where(entries.c.public_id == entry_public_id)).first()
        if collision is not None:
            raise RuntimeError("assistant legacy entry public id collision")
        connection.execute(
            entries.insert().values(
                id=_next_id(_ENTRY_TABLE),
                public_id=entry_public_id,
                conversation_id=canonical_id,
                team_id=int(task["team_id"]),
                user_id=int(task["user_id"]),
                client_request_id=client_request_id,
                input_fingerprint=_fingerprint({"operation": "legacy", "task_public_id": public_id}),
                user_text=str(task["goal"]),
                command_json={
                    "operation": "legacy",
                    "legacy_conversation_id": int(task["conversation_id"]),
                },
                decision_json={"legacy": True},
                state="READY",
                task_public_id=public_id,
                turn_public_id=None,
                reply_text=None,
                task_snapshot_json=None,
                created_time=created_time,
            )
        )

    entry_count = int(connection.execute(sa.select(sa.func.count()).select_from(entries)).scalar_one())
    if entry_count != task_count:
        raise RuntimeError(f"assistant historical entry backfill is incomplete: {entry_count}/{task_count}")


def _bridge_from_archive(before: dict[str, int]) -> None:
    _require_columns(
        _ARCHIVE_TABLE,
        _LEGACY_REQUIRED,
    )
    _create_current_conversation_table()
    _create_entry_table()
    _create_map_table()

    archive = sa.table(
        _ARCHIVE_TABLE,
        sa.column("id", sa.BigInteger()),
        sa.column("public_id", sa.String(64)),
        sa.column("team_id", sa.BigInteger()),
        sa.column("user_id", sa.BigInteger()),
        sa.column("created_time", sa.DateTime()),
        sa.column("last_modified_time", sa.DateTime()),
        sa.column("next_message_seq", sa.Integer()),
    )
    conversations = sa.table(
        _CONVERSATION_TABLE,
        sa.column("id", sa.BigInteger()),
        sa.column("public_id", sa.String(64)),
        sa.column("team_id", sa.BigInteger()),
        sa.column("user_id", sa.BigInteger()),
        sa.column("version", sa.Integer()),
        sa.column("focused_task_public_id", sa.String(64)),
        sa.column("pending_choice_id", sa.String(64)),
        sa.column("busy_entry_id", sa.String(64)),
        sa.column("lease_expires_at", sa.DateTime()),
        sa.column("created_time", sa.DateTime()),
    )
    mapping = sa.table(
        _MAP_TABLE,
        sa.column("legacy_conversation_id", sa.BigInteger()),
        sa.column("legacy_public_id", sa.String(64)),
        sa.column("conversation_id", sa.BigInteger()),
        sa.column("canonical_public_id", sa.String(64)),
        sa.column("team_id", sa.BigInteger()),
        sa.column("user_id", sa.BigInteger()),
        sa.column("legacy_created_time", sa.DateTime()),
        sa.column("legacy_last_modified_time", sa.DateTime()),
        sa.column("created_time", sa.DateTime()),
    )
    entries = sa.table(
        _ENTRY_TABLE,
        sa.column("id", sa.BigInteger()),
        sa.column("public_id", sa.String(64)),
        sa.column("conversation_id", sa.BigInteger()),
        sa.column("team_id", sa.BigInteger()),
        sa.column("user_id", sa.BigInteger()),
        sa.column("client_request_id", sa.String(128)),
        sa.column("input_fingerprint", sa.String(64)),
        sa.column("user_text", sa.Text()),
        sa.column("command_json", sa.JSON()),
        sa.column("decision_json", sa.JSON()),
        sa.column("state", sa.String(20)),
        sa.column("task_public_id", sa.String(64)),
        sa.column("turn_public_id", sa.String(64)),
        sa.column("reply_text", sa.Text()),
        sa.column("task_snapshot_json", sa.JSON()),
        sa.column("created_time", sa.DateTime()),
    )
    tasks = sa.table(
        "crm_assistant_tasks",
        sa.column("id", sa.BigInteger()),
        sa.column("public_id", sa.String(64)),
        sa.column("team_id", sa.BigInteger()),
        sa.column("user_id", sa.BigInteger()),
        sa.column("conversation_id", sa.BigInteger()),
        sa.column("goal", sa.Text()),
        sa.column("created_time", sa.DateTime()),
    )
    _bridge_owners(archive, conversations, mapping)
    _backfill_entries(archive, mapping, entries, tasks)
    _assert_original_counts(before)


def upgrade() -> None:
    before = _row_counts()
    if _table_exists(_ARCHIVE_TABLE):
        if _table_exists(_CONVERSATION_TABLE) and _schema_kind(_CONVERSATION_TABLE) == "legacy":
            raise RuntimeError("assistant migration found both legacy and archived conversations")
        _bridge_from_archive(before)
        return

    if not _table_exists(_CONVERSATION_TABLE):
        raise RuntimeError("assistant migration requires crm_assistant_conversations")

    kind = _schema_kind(_CONVERSATION_TABLE)
    if kind == "current":
        _create_entry_table()
        return
    if kind != "legacy":
        raise RuntimeError("assistant conversation table has an unsupported schema")

    _require_columns(
        "crm_assistant_messages",
        {"conversation_id", "team_id", "user_id", "seq"},
    )
    op.rename_table(_CONVERSATION_TABLE, _ARCHIVE_TABLE)
    _bridge_from_archive(before)


def downgrade() -> None:
    if not _table_exists(_ARCHIVE_TABLE):
        return
    if not _table_exists(_CONVERSATION_TABLE) or _schema_kind(_CONVERSATION_TABLE) != "current":
        raise RuntimeError("assistant bridge downgrade requires the current conversation table")
    _require_columns(_MAP_TABLE, {"legacy_conversation_id", "conversation_id"})
    _require_columns(_ENTRY_TABLE, _ENTRY_REQUIRED)

    connection = op.get_bind()
    archive_count = int(connection.execute(sa.text(f"SELECT COUNT(*) FROM `{_ARCHIVE_TABLE}`")).scalar_one())
    owner_count = int(
        connection.execute(
            sa.text(
                f"SELECT COUNT(*) FROM (SELECT team_id, user_id "
                f"FROM `{_ARCHIVE_TABLE}` GROUP BY team_id, user_id) owners"
            )
        ).scalar_one()
    )
    task_count = int(connection.execute(sa.text("SELECT COUNT(*) FROM `crm_assistant_tasks`")).scalar_one())
    map_count = int(connection.execute(sa.text(f"SELECT COUNT(*) FROM `{_MAP_TABLE}`")).scalar_one())
    canonical_count = int(connection.execute(sa.text(f"SELECT COUNT(*) FROM `{_CONVERSATION_TABLE}`")).scalar_one())
    entry_count = int(connection.execute(sa.text(f"SELECT COUNT(*) FROM `{_ENTRY_TABLE}`")).scalar_one())
    if map_count != archive_count or canonical_count != owner_count or entry_count != task_count:
        raise RuntimeError("assistant bridge contains post-migration data; refusing lossy downgrade")
    active = connection.execute(
        sa.text(
            f"SELECT COUNT(*) FROM `{_CONVERSATION_TABLE}` "
            "WHERE version <> 0 OR focused_task_public_id IS NOT NULL "
            "OR pending_choice_id IS NOT NULL OR busy_entry_id IS NOT NULL "
            "OR lease_expires_at IS NOT NULL"
        )
    ).scalar_one()
    if int(active) != 0:
        raise RuntimeError("assistant bridge contains post-migration state; refusing lossy downgrade")
    unexpected_entries = connection.execute(
        sa.text(
            f"SELECT COUNT(*) FROM `{_ENTRY_TABLE}` "
            "WHERE client_request_id NOT LIKE 'legacy-%' "
            "OR task_public_id IS NULL"
        )
    ).scalar_one()
    if int(unexpected_entries) != 0:
        raise RuntimeError("assistant bridge contains post-migration entries; refusing lossy downgrade")

    op.drop_table(_ENTRY_TABLE)
    op.drop_table(_MAP_TABLE)
    op.drop_table(_CONVERSATION_TABLE)
    op.rename_table(_ARCHIVE_TABLE, _CONVERSATION_TABLE)

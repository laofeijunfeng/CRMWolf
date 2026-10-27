"""Persist owner-scoped assistant conversations and attach legacy tasks.

Revision ID: 154_assistant_conversations
Revises: 153_remove_customer_profile_complete
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "154_assistant_conversations"
down_revision: str | None = "153_remove_customer_profile_complete"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_OWNER_CONSTRAINT = "uq_assistant_conversation_owner_legacy"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _require_table_columns(table_name: str, columns: Sequence[str]) -> None:
    if not _table_exists(table_name):
        raise RuntimeError(f"assistant migration requires table {table_name}")
    actual = {str(column["name"]) for column in _inspector().get_columns(table_name)}
    missing = [column for column in columns if column not in actual]
    if missing:
        raise RuntimeError(
            f"assistant migration table {table_name} is missing required columns {missing}"
        )


def _column_exists(table_name: str, column_name: str) -> bool:
    return column_name in {
        str(column["name"]) for column in _inspector().get_columns(table_name)
    }


def _unique_objects(table_name: str) -> list[dict[str, object]]:
    inspector = _inspector()
    constraints = [
        {
            "kind": "constraint",
            "name": item.get("name"),
            "columns": list(item.get("column_names", [])),
            "unique": True,
            "duplicates_index": item.get("duplicates_index"),
        }
        for item in inspector.get_unique_constraints(table_name)
    ]
    indexes = [
        {
            "kind": "index",
            "name": item.get("name"),
            "columns": list(item.get("column_names", [])),
            "unique": bool(item.get("unique")),
        }
        for item in inspector.get_indexes(table_name)
    ]
    for constraint in constraints:
        marker = constraint.get("duplicates_index")
        if not marker:
            continue
        matches = [item for item in indexes if item.get("name") == marker]
        if len(matches) != 1:
            raise RuntimeError(
                f"assistant migration table {table_name} unique constraint "
                f"{constraint.get('name')!r} has invalid duplicates_index marker {marker!r}"
            )
        index = matches[0]
        if (
            constraint.get("name") != index.get("name")
            or constraint["columns"] != index["columns"]
            or index["unique"] is not True
        ):
            raise RuntimeError(
                f"assistant migration table {table_name} unique reflection marker "
                f"{marker!r} does not describe the same named unique object"
            )
    objects = list(constraints)
    for index in indexes:
        if index["unique"] is True:
            matches = [item for item in constraints if item.get("name") == index.get("name")]
            if matches:
                if len(matches) != 1 or matches[0].get("duplicates_index") != index.get("name"):
                    raise RuntimeError(
                        f"assistant migration table {table_name} unique constraint/index "
                        f"collision for {index.get('name')!r} lacks an exact duplicates_index marker"
                    )
                continue
        objects.append(index)
    named: dict[str, dict[str, object]] = {}
    for item in objects:
        name = item.get("name")
        if name is None:
            continue
        previous = named.get(str(name))
        if previous is not None:
            raise RuntimeError(
                f"assistant migration table {table_name} has duplicate object name "
                f"{name!r} ({previous['kind']} and {item['kind']})"
            )
        named[str(name)] = item
    return objects


def _has_unique_columns(table_name: str, columns: Sequence[str]) -> bool:
    expected = list(columns)
    return any(item["unique"] and item["columns"] == expected for item in _unique_objects(table_name))


def _named_unique_matches(table_name: str, name: str, columns: Sequence[str]) -> bool:
    matches = [item for item in _unique_objects(table_name) if item.get("name") == name]
    if not matches:
        return False
    expected = list(columns)
    item = matches[0]
    if not item["unique"] or item["columns"] != expected:
        raise RuntimeError(f"assistant migration table {table_name} unique {name!r} is {item['kind']} with columns {item['columns']!r}, expected unique columns {expected!r}")
    return True



def _named_index_matches(
    table_name: str, name: str, columns: Sequence[str]
) -> bool:
    expected = list(columns)
    inspector = _inspector()
    indexes = [item for item in inspector.get_indexes(table_name) if item.get("name") == name]
    constraints = [
        item for item in inspector.get_unique_constraints(table_name) if item.get("name") == name
    ]
    if len(indexes) + len(constraints) > 1:
        raise RuntimeError(
            f"assistant migration table {table_name} has duplicate index/unique object name {name!r}"
        )
    if not indexes:
        if constraints:
            raise RuntimeError(
                f"assistant migration table {table_name} object {name!r} is a unique "
                "constraint, expected an index"
            )
        return False
    actual = list(indexes[0].get("column_names", []))
    if actual != expected:
        raise RuntimeError(
            f"assistant migration table {table_name} index {name!r} has columns "
            f"{actual!r}, expected {expected!r}"
        )
    return True


def _named_foreign_key_matches(
    table_name: str,
    name: str,
    constrained_columns: Sequence[str],
    referred_table: str,
    referred_columns: Sequence[str],
) -> bool:
    expected_local = list(constrained_columns)
    expected_remote = list(referred_columns)
    matches = [item for item in _inspector().get_foreign_keys(table_name) if item.get("name") == name]
    if len(matches) > 1:
        raise RuntimeError(
            f"assistant migration table {table_name} has duplicate foreign key name {name!r}"
        )
    if not matches:
        return False
    item = matches[0]
    actual_local = list(item.get("constrained_columns", []))
    actual_remote = list(item.get("referred_columns", []))
    actual_table = item.get("referred_table")
    if (
        actual_local != expected_local
        or actual_table != referred_table
        or actual_remote != expected_remote
    ):
        raise RuntimeError(
            f"assistant migration table {table_name} foreign key {name!r} has "
            f"({actual_local!r}) -> {actual_table!r}({actual_remote!r}), expected "
            f"({expected_local!r}) -> {referred_table}({expected_remote!r})"
        )
    return True



def _validate_existing_owner_constraints() -> None:
    expected = {
        "uq_assistant_conversation_owner": (
            ["team_id", "user_id"],
            ["id", "team_id", "user_id"],
        ),
        _LEGACY_OWNER_CONSTRAINT: (["id", "team_id", "user_id"],),
    }
    for item in _unique_objects("crm_assistant_conversations"):
        name = item.get("name")
        if name not in expected:
            continue
        if not item["unique"] or list(item["columns"]) not in expected[name]:
            raise RuntimeError(
                f"assistant migration conversation owner constraint {name!r} has "
                f"unexpected columns {item['columns']!r}"
            )


def _ensure_last_modified_time() -> None:
    if _column_exists("crm_assistant_conversations", "last_modified_time"):
        return

    connection = op.get_bind()
    op.add_column(
        "crm_assistant_conversations",
        sa.Column("last_modified_time", sa.DateTime(), nullable=True),
    )
    connection.execute(
        sa.text(
            "UPDATE crm_assistant_conversations "
            "SET last_modified_time = created_time "
            "WHERE last_modified_time IS NULL"
        )
    )
_TASK_FK_NAMING = {"fk": "fk_assistant_inbound_%(table_name)s_%(column_0_name)s"}
_DEPENDENCY_FK_SHAPES: dict[
    tuple[str, str], tuple[list[str], list[str]]
] = {
    ("crm_assistant_actions", "crm_assistant_tasks"): (["task_id"], ["id"]),
    ("crm_assistant_requests", "crm_assistant_tasks"): (["task_id"], ["id"]),
    ("crm_assistant_turns", "crm_assistant_tasks"): (["task_id"], ["id"]),
    ("crm_assistant_turns", "crm_assistant_requests"): (["request_id"], ["id"]),
    ("crm_assistant_turn_events", "crm_assistant_turns"): (["turn_id"], ["id"]),
}
_DEPENDENCY_TABLES = {"crm_assistant_tasks", "crm_assistant_requests", "crm_assistant_turns"}
_DETACH_ORDER = (
    "crm_assistant_turn_events",
    "crm_assistant_turns",
    "crm_assistant_requests",
    "crm_assistant_actions",
)
_RESTORE_ORDER = (
    "crm_assistant_requests",
    "crm_assistant_turns",
    "crm_assistant_actions",
    "crm_assistant_turn_events",
)


def _generated_fk_name(table_name: str, constrained_columns: Sequence[str]) -> str:
    return f"fk_assistant_inbound_{table_name}_{constrained_columns[0]}"


def _dependency_foreign_key_specs() -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for table_name in _inspector().get_table_names():
        for foreign_key in _inspector().get_foreign_keys(table_name):
            referred_table = str(foreign_key.get("referred_table"))
            if referred_table not in _DEPENDENCY_TABLES:
                continue
            key = (table_name, referred_table)
            expected = _DEPENDENCY_FK_SHAPES.get(key)
            if expected is None:
                raise RuntimeError(
                    f"assistant migration table {table_name} has unknown foreign key "
                    f"to {referred_table}"
                )
            if key in seen:
                raise RuntimeError(
                    f"assistant migration table {table_name} has duplicate foreign keys "
                    f"to {referred_table}"
                )
            expected_local, expected_remote = expected
            actual_local = list(foreign_key.get("constrained_columns", []))
            actual_remote = list(foreign_key.get("referred_columns", []))
            if actual_local != expected_local or actual_remote != expected_remote:
                raise RuntimeError(
                    f"assistant migration table {table_name} foreign key to "
                    f"{referred_table} has ({actual_local!r}) -> ({actual_remote!r}), "
                    f"expected ({expected_local!r}) -> ({expected_remote!r})"
                )
            seen.add(key)
            specs.append(
                {
                    "table_name": table_name,
                    "name": foreign_key.get("name")
                    or _generated_fk_name(table_name, actual_local),
                    "constrained_columns": actual_local,
                    "referred_table": referred_table,
                    "referred_columns": actual_remote,
                    "referred_schema": foreign_key.get("referred_schema"),
                    "options": dict(foreign_key.get("options", {})),
                }
            )
    return specs


def _ordered_dependency_specs(
    specs: Sequence[dict[str, object]], order: Sequence[str]
) -> list[tuple[str, list[dict[str, object]]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for spec in specs:
        grouped.setdefault(str(spec["table_name"]), []).append(dict(spec))
    result: list[tuple[str, list[dict[str, object]]]] = []
    for table_name in order:
        items = grouped.pop(table_name, None)
        if items:
            result.append((table_name, items))
    for table_name in sorted(grouped):
        result.append((table_name, grouped[table_name]))
    return result


def _detach_dependency_foreign_keys(specs: Sequence[dict[str, object]]) -> None:
    for table_name, table_specs in _ordered_dependency_specs(specs, _DETACH_ORDER):
        with op.batch_alter_table(
            table_name, recreate="always", naming_convention=_TASK_FK_NAMING
        ) as batch:
            for spec in table_specs:
                batch.drop_constraint(str(spec["name"]), type_="foreignkey")
        remaining = [
            item
            for item in _inspector().get_foreign_keys(table_name)
            if item.get("referred_table") in _DEPENDENCY_TABLES
        ]
        if remaining:
            raise RuntimeError(
                f"assistant migration table {table_name} retained dependency foreign keys"
            )


def _restore_dependency_foreign_keys(specs: Sequence[dict[str, object]]) -> None:
    for table_name, table_specs in _ordered_dependency_specs(specs, _RESTORE_ORDER):
        missing = [
            spec
            for spec in table_specs
            if not any(
                item.get("name") == spec["name"]
                for item in _inspector().get_foreign_keys(table_name)
            )
        ]
        if not missing:
            continue
        with op.batch_alter_table(
            table_name, recreate="always", naming_convention=_TASK_FK_NAMING
        ) as batch:
            for spec in missing:
                kwargs = dict(spec.get("options", {}))
                if spec.get("referred_schema") is not None:
                    kwargs["referent_schema"] = spec["referred_schema"]
                batch.create_foreign_key(
                    str(spec["name"]),
                    str(spec["referred_table"]),
                    list(spec["constrained_columns"]),
                    list(spec["referred_columns"]),
                    **kwargs,
                )
        for spec in missing:
            if not any(
                item.get("name") == spec["name"]
                for item in _inspector().get_foreign_keys(table_name)
            ):
                raise RuntimeError(
                    f"assistant migration foreign key {table_name}.{spec['name']} "
                    "was absent after restore"
                )
 
 


def _ensure_conversation_table() -> None:
    table_name = "crm_assistant_conversations"
    if not _table_exists(table_name):
        op.create_table(
            table_name,
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("public_id", sa.String(64), nullable=False),
            sa.Column("team_id", sa.BigInteger(), nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("last_modified_time", sa.DateTime(), nullable=False),
            sa.Column("created_time", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("public_id"),
            sa.UniqueConstraint(
                "id", "team_id", "user_id", name=_LEGACY_OWNER_CONSTRAINT
            ),
        )
    else:
        _require_table_columns(
            table_name, ["id", "public_id", "team_id", "user_id", "created_time"]
        )
        _validate_existing_owner_constraints()

    _ensure_last_modified_time()
    _require_table_columns(
        table_name,
        ["id", "public_id", "team_id", "user_id", "created_time", "last_modified_time"],
    )
    if not _named_index_matches(
        table_name,
        "idx_assistant_conversation_owner",
        ["team_id", "user_id", "last_modified_time", "id"],
    ):
        op.create_index(
            "idx_assistant_conversation_owner",
            table_name,
            ["team_id", "user_id", "last_modified_time", "id"],
        )
    named_legacy = _named_unique_matches(
        table_name, _LEGACY_OWNER_CONSTRAINT, ["id", "team_id", "user_id"]
    )
    if not _has_unique_columns(table_name, ["id", "team_id", "user_id"]):
        if not named_legacy:
            op.create_index(
                _LEGACY_OWNER_CONSTRAINT,
                table_name,
                ["id", "team_id", "user_id"],
                unique=True,
            )


def _ensure_task_conversation_link() -> None:
    connection = op.get_bind()
    table_name = "crm_assistant_tasks"
    _require_table_columns(
        table_name, ["id", "team_id", "user_id", "created_time", "last_modified_time"]
    )
    has_column = _column_exists(table_name, "conversation_id")
    has_index = _named_index_matches(
        table_name,
        "idx_assistant_task_conversation",
        ["team_id", "user_id", "conversation_id", "id"],
    )
    has_owner = _named_unique_matches(
        table_name, "uq_assistant_task_owner", ["id", "team_id", "user_id"]
    )
    has_owner = _has_unique_columns(table_name, ["id", "team_id", "user_id"]) or has_owner
    has_foreign_key = _named_foreign_key_matches(
        table_name,
        "fk_assistant_task_conversation_owner",
        ["conversation_id", "team_id", "user_id"],
        "crm_assistant_conversations",
        ["id", "team_id", "user_id"],
    )
    if has_column and has_index and has_owner and has_foreign_key:
        return
    sqlite = connection.dialect.name == "sqlite"
    specs = _dependency_foreign_key_specs() if sqlite else []
    _detach_dependency_foreign_keys(specs)
    with op.batch_alter_table(table_name) as batch:
        if not has_column:
            batch.add_column(sa.Column("conversation_id", sa.BigInteger(), nullable=True))
        if not has_index:
            batch.create_index(
                "idx_assistant_task_conversation", ["team_id", "user_id", "conversation_id", "id"]
            )
        if not has_owner:
            batch.create_unique_constraint("uq_assistant_task_owner", ["id", "team_id", "user_id"])
        if not has_foreign_key:
            batch.create_foreign_key(
                "fk_assistant_task_conversation_owner",
                "crm_assistant_conversations",
                ["conversation_id", "team_id", "user_id"],
                ["id", "team_id", "user_id"],
            )
    _restore_dependency_foreign_keys(specs)
    if sqlite and connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
        raise RuntimeError("assistant conversation migration violated historical foreign keys")




def _ensure_legacy_tables() -> None:
    connection = op.get_bind()
    if not _table_exists("crm_assistant_messages"):
        op.create_table(
            "crm_assistant_messages",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("public_id", sa.String(64), nullable=False),
            sa.Column("team_id", sa.BigInteger(), nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("conversation_id", sa.BigInteger(), nullable=False),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("task_id", sa.BigInteger(), nullable=True),
            sa.Column("client_request_id", sa.String(128), nullable=True),
            sa.Column("turn_id", sa.BigInteger(), nullable=True),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("created_time", sa.DateTime(), nullable=False),
            sa.Column("last_modified_time", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("public_id"),
            sa.UniqueConstraint("conversation_id", "seq", name="uq_assistant_message_sequence"),
            sa.UniqueConstraint(
                "team_id",
                "user_id",
                "client_request_id",
                name="uq_assistant_message_request_owner",
            ),
            sa.UniqueConstraint(
                "conversation_id",
                "turn_id",
                "role",
                name="uq_assistant_message_turn_role",
            ),
            sa.ForeignKeyConstraint(
                ["conversation_id", "team_id", "user_id"],
                [
                    "crm_assistant_conversations.id",
                    "crm_assistant_conversations.team_id",
                    "crm_assistant_conversations.user_id",
                ],
                name="fk_assistant_message_conversation_owner",
            ),
            sa.ForeignKeyConstraint(
                ["task_id", "team_id", "user_id"],
                [
                    "crm_assistant_tasks.id",
                    "crm_assistant_tasks.team_id",
                    "crm_assistant_tasks.user_id",
                ],
                name="fk_assistant_message_task_owner",
            ),
        )
    if not _named_index_matches("crm_assistant_messages", "idx_assistant_message_conversation_order", ["team_id", "user_id", "conversation_id", "seq"]):
        op.create_index(
            "idx_assistant_message_conversation_order",
            "crm_assistant_messages",
            ["team_id", "user_id", "conversation_id", "seq"],
        )
    if not _table_exists("crm_assistant_references"):
        op.create_table(
            "crm_assistant_references",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("public_id", sa.String(64), nullable=False),
            sa.Column("team_id", sa.BigInteger(), nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("conversation_id", sa.BigInteger(), nullable=False),
            sa.Column("source_phrase", sa.Text(), nullable=False),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("candidate_work_item_ids", sa.JSON(), nullable=False),
            sa.Column("resolved_task_id", sa.BigInteger(), nullable=True),
            sa.Column("created_time", sa.DateTime(), nullable=False),
            sa.Column("last_modified_time", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("public_id"),
            sa.ForeignKeyConstraint(
                ["conversation_id", "team_id", "user_id"],
                [
                    "crm_assistant_conversations.id",
                    "crm_assistant_conversations.team_id",
                    "crm_assistant_conversations.user_id",
                ],
                name="fk_assistant_reference_conversation_owner",
            ),
            sa.ForeignKeyConstraint(
                ["resolved_task_id", "team_id", "user_id"],
                [
                    "crm_assistant_tasks.id",
                    "crm_assistant_tasks.team_id",
                    "crm_assistant_tasks.user_id",
                ],
                name="fk_assistant_reference_task_owner",
            ),
        )
    _require_table_columns(
        "crm_assistant_messages",
        ["id", "public_id", "team_id", "user_id", "conversation_id", "role", "text", "task_id", "client_request_id", "turn_id", "seq", "created_time", "last_modified_time"],
    )
    for name, local, remote_table, remote in (
        ("fk_assistant_message_conversation_owner", ["conversation_id", "team_id", "user_id"], "crm_assistant_conversations", ["id", "team_id", "user_id"]),
        ("fk_assistant_message_task_owner", ["task_id", "team_id", "user_id"], "crm_assistant_tasks", ["id", "team_id", "user_id"]),
    ):
        if not _named_foreign_key_matches("crm_assistant_messages", name, local, remote_table, remote):
            raise RuntimeError(f"assistant migration table crm_assistant_messages is missing foreign key {name}")
    if not _named_index_matches("crm_assistant_messages", "idx_assistant_message_conversation_order", ["team_id", "user_id", "conversation_id", "seq"]):
        raise RuntimeError("assistant migration table crm_assistant_messages is missing index idx_assistant_message_conversation_order")
    _require_table_columns(
        "crm_assistant_references",
        ["id", "public_id", "team_id", "user_id", "conversation_id", "source_phrase", "kind", "status", "candidate_work_item_ids", "resolved_task_id", "created_time", "last_modified_time"],
    )
    for name, local, remote_table, remote in (
        ("fk_assistant_reference_conversation_owner", ["conversation_id", "team_id", "user_id"], "crm_assistant_conversations", ["id", "team_id", "user_id"]),
        ("fk_assistant_reference_task_owner", ["resolved_task_id", "team_id", "user_id"], "crm_assistant_tasks", ["id", "team_id", "user_id"]),
    ):
        if not _named_foreign_key_matches("crm_assistant_references", name, local, remote_table, remote):
            raise RuntimeError(f"assistant migration table crm_assistant_references is missing foreign key {name}")
    if not _named_index_matches("crm_assistant_references", "idx_assistant_reference_conversation", ["team_id", "user_id", "conversation_id", "id"]):
        op.create_index(
            "idx_assistant_reference_conversation",
            "crm_assistant_references",
            ["team_id", "user_id", "conversation_id", "id"],
        )

    _require_table_columns("crm_assistant_tasks", ["team_id", "user_id", "conversation_id", "created_time", "last_modified_time"])
    tasks = sa.table(
        "crm_assistant_tasks",
        sa.column("team_id", sa.BigInteger()),
        sa.column("user_id", sa.BigInteger()),
        sa.column("conversation_id", sa.BigInteger()),
        sa.column("created_time", sa.DateTime()),
        sa.column("last_modified_time", sa.DateTime()),
    )
    conversations = sa.table(
        "crm_assistant_conversations",
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
        sa.column("last_modified_time", sa.DateTime()),
    )
    owner_groups = connection.execute(
        sa.select(
            tasks.c.team_id,
            tasks.c.user_id,
            sa.func.min(tasks.c.created_time).label("created_time"),
            sa.func.max(tasks.c.last_modified_time).label("last_modified_time"),
        )
        .group_by(tasks.c.team_id, tasks.c.user_id)
        .order_by(tasks.c.team_id, tasks.c.user_id)
    ).mappings()
    for group in owner_groups:
        existing = connection.execute(
            sa.select(conversations.c.id).where(
                conversations.c.team_id == group["team_id"],
                conversations.c.user_id == group["user_id"],
            )
        ).scalar_one_or_none()
        if existing is None:
            values = {
                "public_id": f"acv_legacy_{group['team_id']}_{group['user_id']}",
                "team_id": group["team_id"],
                "user_id": group["user_id"],
                "created_time": group["created_time"],
                "last_modified_time": group["last_modified_time"],
            }
            conversation_columns = {
                column["name"]
                for column in sa.inspect(connection).get_columns(
                    "crm_assistant_conversations"
                )
            }
            if "version" in conversation_columns:
                values["version"] = 0
            if "focused_task_public_id" in conversation_columns:
                values["focused_task_public_id"] = None
            if "pending_choice_id" in conversation_columns:
                values["pending_choice_id"] = None
            if "busy_entry_id" in conversation_columns:
                values["busy_entry_id"] = None
            if "lease_expires_at" in conversation_columns:
                values["lease_expires_at"] = None
            if "id" not in values and connection.dialect.name == "sqlite":
                values["id"] = int(
                    connection.execute(
                        sa.select(sa.func.coalesce(sa.func.max(conversations.c.id), 0) + 1)
                    ).scalar_one()
                )
            connection.execute(conversations.insert().values(**values))
    owner_conversation = sa.select(conversations.c.id).where(
        conversations.c.team_id == tasks.c.team_id,
        conversations.c.user_id == tasks.c.user_id,
    ).scalar_subquery()
    connection.execute(
        tasks.update()
        .where(tasks.c.conversation_id.is_(None))
        .values(conversation_id=owner_conversation)
    )


def upgrade() -> None:
    _ensure_conversation_table()
    _ensure_task_conversation_link()
    _ensure_legacy_tables()


def downgrade() -> None:
    op.drop_index("idx_assistant_reference_conversation", table_name="crm_assistant_references")
    op.drop_table("crm_assistant_references")
    op.drop_index("idx_assistant_message_conversation_order", table_name="crm_assistant_messages")
    op.drop_table("crm_assistant_messages")
    with op.batch_alter_table("crm_assistant_tasks") as batch:
        batch.drop_constraint("fk_assistant_task_conversation_owner", type_="foreignkey")
        batch.drop_constraint("uq_assistant_task_owner", type_="unique")
        batch.drop_index("idx_assistant_task_conversation")
        batch.drop_column("conversation_id")
    op.drop_index("idx_assistant_conversation_owner", table_name="crm_assistant_conversations")
    op.drop_table("crm_assistant_conversations")

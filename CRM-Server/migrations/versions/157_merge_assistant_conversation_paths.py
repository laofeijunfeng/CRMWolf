"""Merge the current conversation schema with the recovered legacy path."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "157_merge_assistant_conversation_paths"
down_revision: tuple[str, str] = (
    "02352b41bcb6",
    "156_assistant_historical_messages",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONVERSATION_TABLE = "crm_assistant_conversations"
_ENTRY_TABLE = "crm_assistant_conversation_entries"
_ENTRY_FK_NAME = "fk_assistant_entry_conversation"
_ENTRY_AUTOMATIC_FK_NAME = "crm_assistant_conversation_entries_ibfk_1"
_LEGACY_OWNER_CONSTRAINT = "uq_assistant_conversation_owner_legacy"
_OWNER_CONSTRAINT = "uq_assistant_conversation_owner"
_REQUEST_CONSTRAINT = "uq_assistant_conversation_request"
_PAGE_INDEX = "idx_assistant_conversation_page"

def _bind() -> sa.Connection:
    return op.get_bind()


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(_bind()).get_table_names()


def _column_info(table_name: str) -> dict[str, dict[str, object]]:
    return {item["name"]: item for item in sa.inspect(_bind()).get_columns(table_name)}


def _column_exists(table_name: str, column_name: str) -> bool:
    return column_name in _column_info(table_name)


def _objects(table_name: str) -> list[dict[str, object]]:
    inspector = sa.inspect(_bind())
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
                f"{table_name} unique constraint {constraint.get('name')!r} has "
                f"invalid duplicates_index marker {marker!r}"
            )
        index = matches[0]
        if (
            constraint.get("name") != index.get("name")
            or constraint["columns"] != index["columns"]
            or index["unique"] is not True
        ):
            raise RuntimeError(
                f"{table_name} unique reflection marker {marker!r} does not "
                "describe the same named unique object"
            )
    result = list(constraints)
    for item in indexes:
        if item["unique"] is True:
            matches = [constraint for constraint in constraints if constraint.get("name") == item.get("name")]
            if matches:
                if len(matches) != 1 or matches[0].get("duplicates_index") != item.get("name"):
                    raise RuntimeError(
                        f"{table_name} unique constraint/index collision for {item.get('name')!r} "
                        "lacks an exact duplicates_index marker"
                    )
                continue
        result.append(item)
    return result



def _named_objects(table_name: str, name: str) -> list[dict[str, object]]:
    return [item for item in _objects(table_name) if item.get("name") == name]


def _unique_objects(table_name: str) -> list[dict[str, object]]:
    result = [item for item in _objects(table_name) if item["unique"]]
    seen: dict[str, dict[str, object]] = {}
    for item in result:
        name = item.get("name")
        if not name:
            continue
        if name in seen:
            raise RuntimeError(
                f"{table_name} has duplicate unique objects named {name!r}: "
                f"{seen[name]['kind']} {seen[name]['columns']} and "
                f"{item['kind']} {item['columns']}"
            )
        seen[name] = item
    return result


def _named_unique(table_name: str, name: str, columns: Sequence[str]) -> dict[str, object] | None:
    matches = _named_objects(table_name, name)
    if len(matches) > 1:
        raise RuntimeError(f"{table_name} has duplicate schema objects named {name!r}")
    if not matches:
        return None
    item = matches[0]
    if item["unique"] is not True or item["columns"] != list(columns):
        raise RuntimeError(
            f"{table_name}.{name} has unexpected {item['kind']} shape: "
            f"{item['columns']}; expected unique {list(columns)}"
        )
    return item


def _has_unique(table_name: str, columns: Sequence[str]) -> bool:
    return any(item["columns"] == list(columns) for item in _unique_objects(table_name))


def _unique_candidates(table_name: str, columns: Sequence[str]) -> list[dict[str, object]]:
    return [item for item in _unique_objects(table_name) if item["columns"] == list(columns)]


def _drop_candidate(batch: object, item: dict[str, object], table_name: str) -> None:
    name = item.get("name")
    if not name:
        raise RuntimeError(
            f"{table_name} has an unnamed unique {list(item['columns'])} candidate; "
            "cannot safely rename it to the canonical key"
        )
    if item["kind"] == "index":
        batch.drop_index(str(name))
    else:
        batch.drop_constraint(str(name), type_="unique")


def _foreign_keys(table_name: str) -> list[dict[str, object]]:
    return list(sa.inspect(_bind()).get_foreign_keys(table_name))


def _foreign_key(table_name: str, name: str) -> dict[str, object] | None:
    matches = [item for item in _foreign_keys(table_name) if item.get("name") == name]
    if len(matches) > 1:
        raise RuntimeError(f"{table_name} has duplicate foreign keys named {name!r}")
    return matches[0] if matches else None


def _default_text(value: object) -> str | None:
    if value is None:
        return None
    value = getattr(value, "arg", value)
    text = str(value).strip().strip("'").strip('"').strip("()").lower()
    return text or None
def _type_matches(actual: object, expected: str) -> bool:
    if expected == "bigint":
        return isinstance(actual, sa.BigInteger) or (
            _bind().dialect.name == "sqlite" and isinstance(actual, sa.Integer)
        )
    if expected == "integer":
        return isinstance(actual, sa.Integer)
    if expected == "string64":
        return isinstance(actual, sa.String) and not isinstance(actual, sa.Text) and actual.length == 64
    if expected == "string128":
        return isinstance(actual, sa.String) and not isinstance(actual, sa.Text) and actual.length == 128
    if expected == "string20":
        return isinstance(actual, sa.String) and not isinstance(actual, sa.Text) and actual.length == 20
    if expected == "text":
        return isinstance(actual, sa.Text)
    if expected == "datetime":
        return isinstance(actual, sa.DateTime) and not bool(actual.timezone)
    if expected == "json":
        return isinstance(actual, sa.JSON)
    raise AssertionError(f"unknown expected type {expected!r}")


def _validate_columns(
    table_name: str,
    specs: dict[str, tuple[str, bool, str | None]],
) -> None:
    columns = _column_info(table_name)
    for name, (expected_type, nullable, default) in specs.items():
        column = columns.get(name)
        if column is None:
            raise RuntimeError(f"{table_name}.{name} is missing")
        if not _type_matches(column.get("type"), expected_type):
            raise RuntimeError(
                f"{table_name}.{name} has unexpected type {column.get('type')!r}; "
                f"expected {expected_type}"
            )
        if column.get("nullable") is not nullable:
            raise RuntimeError(
                f"{table_name}.{name} has unexpected nullability {column.get('nullable')!r}; "
                f"expected {nullable!r}"
            )
        if default is not None and _default_text(column.get("default")) != default:
            raise RuntimeError(
                f"{table_name}.{name} has unexpected default {column.get('default')!r}; "
                f"expected {default!r}"
            )


def _ensure_conversation_columns() -> None:
    if not _table_exists(_CONVERSATION_TABLE):
        raise RuntimeError("assistant conversation table is missing; cannot bridge history")
    _validate_columns(
        _CONVERSATION_TABLE,
        {
            "id": ("bigint", False, None),
            "public_id": ("string64", False, None),
            "team_id": ("bigint", False, None),
            "user_id": ("bigint", False, None),
            "created_time": ("datetime", False, None),
        },
    )
    additions = (
        ("version", sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0"))),
        ("focused_task_public_id", sa.Column("focused_task_public_id", sa.String(64), nullable=True)),
        ("pending_choice_id", sa.Column("pending_choice_id", sa.String(64), nullable=True)),
        ("busy_entry_id", sa.Column("busy_entry_id", sa.String(64), nullable=True)),
        ("lease_expires_at", sa.Column("lease_expires_at", sa.DateTime(), nullable=True)),
        ("last_modified_time", sa.Column("last_modified_time", sa.DateTime(), nullable=True)),
        ("next_message_seq", sa.Column("next_message_seq", sa.Integer(), nullable=False, server_default=sa.text("1"))),
    )
    for name, column in additions:
        if not _column_exists(_CONVERSATION_TABLE, name):
            op.add_column(_CONVERSATION_TABLE, column)

    columns = _column_info(_CONVERSATION_TABLE)
    last_modified_nullable = bool(columns["last_modified_time"].get("nullable"))
    _validate_columns(
        _CONVERSATION_TABLE,
        {
            "version": ("integer", False, None),
            "focused_task_public_id": ("string64", True, None),
            "pending_choice_id": ("string64", True, None),
            "busy_entry_id": ("string64", True, None),
            "lease_expires_at": ("datetime", True, None),
            "last_modified_time": ("datetime", last_modified_nullable, None),
            "next_message_seq": ("integer", False, "1"),
        },
    )
    _bind().execute(
        sa.text(
            f"UPDATE {_CONVERSATION_TABLE} SET last_modified_time = created_time "
            "WHERE last_modified_time IS NULL"
        )
    )
    if _bind().execute(
        sa.text(f"SELECT 1 FROM {_CONVERSATION_TABLE} WHERE last_modified_time IS NULL LIMIT 1")
    ).first() is not None:
        raise RuntimeError("assistant conversations contain rows whose last_modified_time cannot be backfilled")


def _validate_entry_columns() -> None:
    _validate_columns(
        _ENTRY_TABLE,
        {
            "id": ("bigint", False, None),
            "public_id": ("string64", False, None),
            "conversation_id": ("bigint", False, None),
            "team_id": ("bigint", False, None),
            "user_id": ("bigint", False, None),
            "client_request_id": ("string128", False, None),
            "input_fingerprint": ("string64", False, None),
            "user_text": ("text", False, None),
            "command_json": ("json", False, None),
            "decision_json": ("json", False, None),
            "state": ("string20", False, None),
            "task_public_id": ("string64", True, None),
            "turn_public_id": ("string64", True, None),
            "reply_text": ("text", True, None),
            "task_snapshot_json": ("json", True, None),
            "created_time": ("datetime", False, None),
        },
    )


def _ensure_entry_conversation_fk() -> None:
    fks = [item for item in _foreign_keys(_ENTRY_TABLE) if item.get("referred_table") == _CONVERSATION_TABLE]
    if len(fks) != 1:
        raise RuntimeError(
            f"{_ENTRY_TABLE} must have exactly one conversation foreign key; found {len(fks)}"
        )
    fk = fks[0]
    constrained = list(fk.get("constrained_columns", []))
    referred = list(fk.get("referred_columns", []))
    if constrained != ["conversation_id"] or referred != ["id"]:
        raise RuntimeError(
            f"{_ENTRY_TABLE} conversation foreign key has unexpected shape: "
            f"{fk.get('name')!r} {constrained} -> {referred}"
        )
    current_name = fk.get("name")
    if current_name == _ENTRY_FK_NAME:
        return
    if current_name not in (None, _ENTRY_AUTOMATIC_FK_NAME):
        raise RuntimeError(
            f"{_ENTRY_TABLE} has unknown conversation foreign key name {current_name!r}"
        )
    options = {
        key: value
        for key, value in dict(fk.get("options", {})).items()
        if key in {"onupdate", "ondelete", "deferrable", "initially", "match"}
        and value is not None
    }
    if fk.get("referred_schema") is not None:
        options["referent_schema"] = fk["referred_schema"]
    try:
        if _bind().dialect.name == "mysql":
            if current_name is None:
                raise RuntimeError(f"{_ENTRY_TABLE} has an unnamed MySQL conversation foreign key")
            if options or fk.get("referred_schema") is not None:
                raise RuntimeError(
                    f"{_ENTRY_TABLE} conversation foreign key has unexpected referential options"
                )
            # One statement so MySQL cannot commit the drop without the replacement.
            op.execute(
                sa.text(
                    f"ALTER TABLE {_ENTRY_TABLE} "
                    f"DROP FOREIGN KEY `{current_name}`, "
                    f"ADD CONSTRAINT `{_ENTRY_FK_NAME}` "
                    "FOREIGN KEY (`conversation_id`) "
                    f"REFERENCES `{_CONVERSATION_TABLE}` (`id`)"
                )
            )
        else:
            with op.batch_alter_table(
                _ENTRY_TABLE,
                recreate="always",
                naming_convention={"fk": _ENTRY_FK_NAME},
            ) as batch:
                if current_name is not None:
                    batch.drop_constraint(str(current_name), type_="foreignkey")
                    batch.create_foreign_key(
                        _ENTRY_FK_NAME,
                        _CONVERSATION_TABLE,
                        ["conversation_id"],
                        ["id"],
                        **options,
                    )
    except Exception as exc:
        raise RuntimeError(f"{_ENTRY_TABLE} conversation FK could not be normalized safely") from exc
    fk = _foreign_key(_ENTRY_TABLE, _ENTRY_FK_NAME)
    if fk is None or list(fk.get("constrained_columns", [])) != ["conversation_id"] or list(
        fk.get("referred_columns", [])
    ) != ["id"]:
        raise RuntimeError(f"{_ENTRY_TABLE} conversation FK was absent or changed after normalization")


def _ensure_entry_table() -> None:
    if not _table_exists(_ENTRY_TABLE):
        op.create_table(
            _ENTRY_TABLE,
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("public_id", sa.String(64), nullable=False, unique=True),
            sa.Column("conversation_id", sa.BigInteger(), nullable=False),
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
            sa.ForeignKeyConstraint(["conversation_id"], [_CONVERSATION_TABLE + ".id"], name="fk_assistant_entry_conversation"),
            sa.UniqueConstraint("conversation_id", "client_request_id", name=_REQUEST_CONSTRAINT),
        )
    else:
        required = {
            "id", "public_id", "conversation_id", "team_id", "user_id", "client_request_id",
            "input_fingerprint", "user_text", "command_json", "decision_json", "state",
            "task_public_id", "turn_public_id", "reply_text", "task_snapshot_json", "created_time",
        }
        missing = sorted(required - _column_info(_ENTRY_TABLE).keys())
        if missing:
            raise RuntimeError("assistant conversation entries table has unexplained missing columns: " + ", ".join(missing))
    _validate_entry_columns()
    named_request = _named_unique(_ENTRY_TABLE, _REQUEST_CONSTRAINT, ["conversation_id", "client_request_id"])
    if named_request is None:
        duplicate = _bind().execute(
            sa.text(
                f"SELECT conversation_id, client_request_id FROM {_ENTRY_TABLE} "
                "GROUP BY conversation_id, client_request_id HAVING COUNT(*) > 1 LIMIT 1"
            )
        ).first()
        if duplicate is not None:
            raise RuntimeError("assistant conversation entries contain duplicate request identities")
        with op.batch_alter_table(_ENTRY_TABLE) as batch:
            batch.create_unique_constraint(_REQUEST_CONSTRAINT, ["conversation_id", "client_request_id"])
    page_objects = _named_objects(_ENTRY_TABLE, _PAGE_INDEX)
    if len(page_objects) > 1:
        raise RuntimeError(f"{_ENTRY_TABLE} has duplicate objects named {_PAGE_INDEX!r}")
    if page_objects and (
        page_objects[0]["kind"] != "index"
        or page_objects[0]["unique"]
        or page_objects[0]["columns"] != ["team_id", "user_id", "conversation_id", "id"]
    ):
        raise RuntimeError(f"{_ENTRY_TABLE}.{_PAGE_INDEX} has unexpected shape")
    if not page_objects:
        op.create_index(_PAGE_INDEX, _ENTRY_TABLE, ["team_id", "user_id", "conversation_id", "id"])
    _ensure_entry_conversation_fk()


def _ensure_next_message_seq() -> None:
    if not _table_exists("crm_assistant_messages"):
        return
    _validate_columns(
        "crm_assistant_messages",
        {
            "conversation_id": ("bigint", False, None),
            "team_id": ("bigint", False, None),
            "user_id": ("bigint", False, None),
            "seq": ("integer", False, None),
        },
    )
    conversations = sa.table(
        _CONVERSATION_TABLE,
        sa.column("id", sa.BigInteger()),
        sa.column("team_id", sa.BigInteger()),
        sa.column("user_id", sa.BigInteger()),
        sa.column("next_message_seq", sa.Integer()),
    )
    messages = sa.table(
        "crm_assistant_messages",
        sa.column("conversation_id", sa.BigInteger()),
        sa.column("team_id", sa.BigInteger()),
        sa.column("user_id", sa.BigInteger()),
        sa.column("seq", sa.Integer()),
    )
    next_seq = sa.select(sa.func.coalesce(sa.func.max(messages.c.seq), 0) + 1).where(
        messages.c.conversation_id == conversations.c.id,
        messages.c.team_id == conversations.c.team_id,
        messages.c.user_id == conversations.c.user_id,
    ).scalar_subquery()
    _bind().execute(conversations.update().where(conversations.c.next_message_seq < next_seq).values(next_message_seq=next_seq))


_EXPECTED_CONVERSATION_FKS: dict[str, tuple[str, list[str], list[str]]] = {
    "crm_assistant_tasks": ("fk_assistant_task_conversation_owner", ["conversation_id", "team_id", "user_id"], ["id", "team_id", "user_id"]),
    "crm_assistant_messages": ("fk_assistant_message_conversation_owner", ["conversation_id", "team_id", "user_id"], ["id", "team_id", "user_id"]),
    "crm_assistant_references": ("fk_assistant_reference_conversation_owner", ["conversation_id", "team_id", "user_id"], ["id", "team_id", "user_id"]),
    _ENTRY_TABLE: ("fk_assistant_entry_conversation", ["conversation_id"], ["id"]),
}


def _conversation_child_fks() -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    expected_tables = set(_EXPECTED_CONVERSATION_FKS)
    for table_name in sa.inspect(_bind()).get_table_names():
        fks = [item for item in _foreign_keys(table_name) if item.get("referred_table") == _CONVERSATION_TABLE]
        if not fks:
            continue
        if table_name not in expected_tables:
            raise RuntimeError(f"{table_name} has an unknown foreign key to {_CONVERSATION_TABLE}")
        expected_name, expected_columns, expected_referred = _EXPECTED_CONVERSATION_FKS[table_name]
        if len(fks) > 1:
            raise RuntimeError(f"{table_name} has multiple conversation foreign keys")
        fk = fks[0]
        if fk.get("name") != expected_name:
            raise RuntimeError(f"{table_name} has unknown or unnamed conversation foreign key {fk.get('name')!r}")
        constrained = list(fk.get("constrained_columns", []))
        referred = list(fk.get("referred_columns", []))
        if constrained != expected_columns or referred != expected_referred:
            raise RuntimeError(f"{table_name}.{expected_name} has unexpected shape: {constrained} -> {referred}")
        specs.append(
            {
                "table_name": table_name,
                "name": expected_name,
                "constrained_columns": constrained,
                "referred_table": _CONVERSATION_TABLE,
                "referred_columns": referred,
                "referred_schema": fk.get("referred_schema"),
                "options": dict(fk.get("options", {})),
            }
        )
    return specs


_KNOWN_INDIRECT_FKS: dict[tuple[str, str], tuple[str, list[str], list[str]]] = {
    ("crm_assistant_actions", "crm_assistant_tasks"): ("fk_m157_actions_task", ["task_id"], ["id"]),
    ("crm_assistant_requests", "crm_assistant_tasks"): ("fk_m157_requests_task", ["task_id"], ["id"]),
    ("crm_assistant_turns", "crm_assistant_tasks"): ("fk_m157_turns_task", ["task_id"], ["id"]),
    ("crm_assistant_turns", "crm_assistant_requests"): ("fk_m157_turns_request", ["request_id"], ["id"]),
    ("crm_assistant_turn_events", "crm_assistant_turns"): ("fk_m157_turn_events_turn", ["turn_id"], ["id"]),
    (
        "crm_assistant_messages",
        "crm_assistant_tasks",
    ): ("fk_assistant_message_task_owner", ["task_id", "team_id", "user_id"], ["id", "team_id", "user_id"]),
    (
        "crm_assistant_references",
        "crm_assistant_tasks",
    ): ("fk_assistant_reference_task_owner", ["resolved_task_id", "team_id", "user_id"], ["id", "team_id", "user_id"]),
    (
        "crm_assistant_messages",
        "crm_assistant_references",
    ): ("fk_assistant_message_reference_owner", ["reference_id", "team_id", "user_id"], ["id", "team_id", "user_id"]),
}
_FK_DETACH_ORDER = (
    "crm_assistant_turn_events",
    "crm_assistant_turns",
    "crm_assistant_requests",
    "crm_assistant_actions",
    "crm_assistant_messages",
    "crm_assistant_references",
    "crm_assistant_tasks",
    _ENTRY_TABLE,
)
_FK_RESTORE_ORDER = (
    "crm_assistant_tasks",
    "crm_assistant_requests",
    "crm_assistant_turns",
    "crm_assistant_actions",
    "crm_assistant_references",
    "crm_assistant_messages",
    "crm_assistant_turn_events",
    _ENTRY_TABLE,
)


def _ordered_fk_groups(
    specs: Sequence[dict[str, object]], order: Sequence[str]
) -> list[tuple[str, list[dict[str, object]]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for spec in specs:
        grouped.setdefault(str(spec["table_name"]), []).append(spec)
    result: list[tuple[str, list[dict[str, object]]]] = []
    for table_name in order:
        items = grouped.pop(table_name, None)
        if items:
            result.append((table_name, items))
    if grouped:
        raise RuntimeError(
            "assistant conversation migration found foreign keys on unexpected tables: "
            + ", ".join(sorted(grouped))
        )
    return result




def _normalize_indirect_fks(targets: set[str]) -> None:
    for table_name in sa.inspect(_bind()).get_table_names():
        relevant = [item for item in _foreign_keys(table_name) if item.get("referred_table") in targets]
        if not relevant:
            continue
        unnamed = False
        for fk in relevant:
            referred = str(fk.get("referred_table"))
            if table_name == referred:
                continue
            expected = _KNOWN_INDIRECT_FKS.get((table_name, referred))
            if expected is None:
                raise RuntimeError(f"{table_name} has unknown foreign key to recreated table {referred}")
            _, constrained, referred_columns = expected
            if list(fk.get("constrained_columns", [])) != constrained or list(fk.get("referred_columns", [])) != referred_columns:
                raise RuntimeError(f"{table_name} foreign key to {referred} has unexpected shape")
            unnamed = unnamed or fk.get("name") is None
        if not unnamed:
            continue
        try:
            with op.batch_alter_table(
                table_name,
                recreate="always",
                naming_convention={"fk": "fk_m157_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"},
            ):
                pass
        except Exception as exc:
            raise RuntimeError(f"{table_name} known unnamed foreign keys could not be normalized") from exc
        if any(item.get("name") is None for item in _foreign_keys(table_name) if item.get("referred_table") in targets):
            raise RuntimeError(f"{table_name} retained an unnamed foreign key after normalization")


def _indirect_fks(targets: set[str]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for table_name in sa.inspect(_bind()).get_table_names():
        for fk in _foreign_keys(table_name):
            referred = str(fk.get("referred_table"))
            if referred not in targets or table_name == referred:
                continue
            expected = _KNOWN_INDIRECT_FKS.get((table_name, referred))
            if expected is None:
                raise RuntimeError(f"{table_name} has unknown foreign key to recreated table {referred}")
            expected_name, expected_columns, expected_referred = expected
            constrained = list(fk.get("constrained_columns", []))
            referred_columns = list(fk.get("referred_columns", []))
            if constrained != expected_columns or referred_columns != expected_referred:
                raise RuntimeError(f"{table_name} foreign key to {referred} has unexpected shape")
            name = fk.get("name")
            if not name:
                raise RuntimeError(f"{table_name} has unnamed foreign key to {referred} after normalization")
            result.append(
                {
                    "table_name": table_name,
                    "name": name,
                    "constrained_columns": constrained,
                    "referred_table": referred,
                    "referred_columns": referred_columns,
                    "referred_schema": fk.get("referred_schema"),
                    "options": dict(fk.get("options", {})),
                }
            )
    return result


def _detach_fks(specs: list[dict[str, object]]) -> None:
    for table_name, items in _ordered_fk_groups(specs, _FK_DETACH_ORDER):
        try:
            with op.batch_alter_table(table_name, recreate="always") as batch:
                for spec in items:
                    name = spec.get("name")
                    if not name:
                        raise RuntimeError(f"{table_name} has an unnamed recognized foreign key")
                    batch.drop_constraint(str(name), type_="foreignkey")
        except Exception as exc:
            raise RuntimeError(f"failed to detach foreign keys from {table_name}") from exc
        for spec in items:
            if _foreign_key(table_name, str(spec["name"])) is not None:
                raise RuntimeError(f"{table_name}.{spec['name']} remained after detach")




def _restore_fks(specs: list[dict[str, object]]) -> None:
    for table_name, items in _ordered_fk_groups(specs, _FK_RESTORE_ORDER):
        missing = [item for item in items if _foreign_key(table_name, str(item["name"])) is None]
        if not missing:
            continue
        try:
            with op.batch_alter_table(table_name, recreate="always") as batch:
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
        except Exception as exc:
            raise RuntimeError(f"failed to restore foreign keys on {table_name}") from exc
        for spec in missing:
            fk = _foreign_key(table_name, str(spec["name"]))
            if fk is None:
                raise RuntimeError(f"{table_name}.{spec['name']} is absent after restore")
            if (
                fk.get("referred_table") != spec["referred_table"]
                or list(fk.get("constrained_columns", []))
                != list(spec["constrained_columns"])
                or list(fk.get("referred_columns", []))
                != list(spec["referred_columns"])
            ):
                raise RuntimeError(f"{table_name}.{spec['name']} was restored with unexpected shape")

def _assert_no_duplicate_owners() -> None:
    if _bind().execute(
        sa.text(
            f"SELECT team_id, user_id FROM {_CONVERSATION_TABLE} "
            "GROUP BY team_id, user_id HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first() is not None:
        raise RuntimeError("assistant conversation migration found duplicate team/user owners; refusing merge")


def _normalize_parent_constraints() -> None:
    _assert_no_duplicate_owners()
    # Validate every conversation dependency before inspecting canonical names so an
    # unsafe child shape is never masked by an unrelated parent collision.
    child_specs = _conversation_child_fks()
    target_tables = set(_EXPECTED_CONVERSATION_FKS)
    for child_table, parent_table in _KNOWN_INDIRECT_FKS:
        target_tables.add(child_table)
        target_tables.add(parent_table)
    _normalize_indirect_fks(target_tables)
    indirect_specs = _indirect_fks(target_tables)

    legacy = _named_unique(
        _CONVERSATION_TABLE,
        _LEGACY_OWNER_CONSTRAINT,
        ["id", "team_id", "user_id"],
    )
    owner_alias: dict[str, object] | None = None
    owner_matches = _named_objects(_CONVERSATION_TABLE, _OWNER_CONSTRAINT)
    if len(owner_matches) > 1:
        raise RuntimeError(
            f"{_CONVERSATION_TABLE} has duplicate schema objects named {_OWNER_CONSTRAINT!r}"
        )
    owner: dict[str, object] | None = None
    if owner_matches:
        candidate = owner_matches[0]
        if candidate["unique"] is not True:
            raise RuntimeError(
                f"{_CONVERSATION_TABLE}.{_OWNER_CONSTRAINT} has unexpected "
                f"{candidate['kind']} shape: {candidate['columns']}"
            )
        if candidate["columns"] == ["team_id", "user_id"]:
            owner = candidate
        elif candidate["columns"] == ["id", "team_id", "user_id"]:
            owner_alias = candidate
        else:
            raise RuntimeError(
                f"{_CONVERSATION_TABLE}.{_OWNER_CONSTRAINT} has unexpected "
                f"constraint shape: {candidate['columns']}; expected unique "
                "['team_id', 'user_id']"
            )

    columns = _column_info(_CONVERSATION_TABLE)
    last_modified = columns["last_modified_time"]
    needs_rewrite = (
        owner_alias is not None
        or legacy is None
        or legacy.get("kind") != "constraint"
        or owner is None
        or owner.get("kind") != "constraint"
        or bool(last_modified.get("nullable"))
        or _default_text(last_modified.get("default")) != "current_timestamp"
    )
    if not needs_rewrite:
        return

    all_specs = child_specs + indirect_specs
    _detach_fks(all_specs)
    try:
        with op.batch_alter_table(_CONVERSATION_TABLE, recreate="always") as batch:
            if owner_alias is not None:
                _drop_candidate(batch, owner_alias, _CONVERSATION_TABLE)
            if legacy is not None and legacy.get("kind") != "constraint":
                _drop_candidate(batch, legacy, _CONVERSATION_TABLE)
            if owner is not None and owner.get("kind") != "constraint":
                _drop_candidate(batch, owner, _CONVERSATION_TABLE)
            if legacy is None or legacy.get("kind") != "constraint":
                batch.create_unique_constraint(
                    _LEGACY_OWNER_CONSTRAINT, ["id", "team_id", "user_id"]
                )
            if owner is None or owner.get("kind") != "constraint":
                batch.create_unique_constraint(_OWNER_CONSTRAINT, ["team_id", "user_id"])
            if last_modified.get("nullable") or _default_text(last_modified.get("default")) != "current_timestamp":
                batch.alter_column(
                    "last_modified_time",
                    existing_type=sa.DateTime(),
                    nullable=False,
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                )
    except Exception as exc:
        try:
            _restore_fks(all_specs)
        except Exception as restore_exc:
            raise RuntimeError("parent rewrite failed and child FK restoration also failed") from restore_exc
        raise RuntimeError("assistant conversation parent constraint rewrite failed") from exc
    _restore_fks(all_specs)


def upgrade() -> None:
    if not _table_exists(_CONVERSATION_TABLE):
        raise RuntimeError("assistant conversation table is missing; cannot bridge history")
    _assert_no_duplicate_owners()
    _ensure_conversation_columns()
    _ensure_entry_table()
    _ensure_next_message_seq()
    _normalize_parent_constraints()


def downgrade() -> None:
    raise RuntimeError("Conversation schema bridge cannot be safely downgraded")

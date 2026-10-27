"""Add durable identity and reference linkage to assistant messages."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "155_assistant_message_identity"
down_revision: str | None = "154_assistant_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _require_table_columns(table_name: str, columns: Sequence[str]) -> None:
    if not _inspector().has_table(table_name):
        raise RuntimeError(f"assistant identity migration requires table {table_name}")
    actual = {str(column["name"]) for column in _inspector().get_columns(table_name)}
    missing = [column for column in columns if column not in actual]
    if missing:
        raise RuntimeError(
            f"assistant identity migration table {table_name} is missing required columns {missing}"
        )


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(item.get("name") == index_name for item in _inspector().get_indexes(table_name))


def _foreign_key_exists(table_name: str, constraint_name: str) -> bool:
    return any(item.get("name") == constraint_name for item in _inspector().get_foreign_keys(table_name))



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
                f"assistant identity migration table {table_name} unique constraint "
                f"{constraint.get('name')!r} has invalid duplicates_index marker {marker!r}"
            )
        index = matches[0]
        if (
            constraint.get("name") != index.get("name")
            or constraint["columns"] != index["columns"]
            or index["unique"] is not True
        ):
            raise RuntimeError(
                f"assistant identity migration table {table_name} unique reflection marker "
                f"{marker!r} does not describe the same named unique object"
            )
    objects = list(constraints)
    for index in indexes:
        if index["unique"] is True:
            matches = [item for item in constraints if item.get("name") == index.get("name")]
            if matches:
                if len(matches) != 1 or matches[0].get("duplicates_index") != index.get("name"):
                    raise RuntimeError(
                        f"assistant identity migration table {table_name} unique constraint/index "
                        f"collision for {index.get('name')!r} lacks an exact duplicates_index marker"
                    )
                continue
        objects.append(index)
    names: dict[str, dict[str, object]] = {}
    for item in objects:
        name = item.get("name")
        if name is None:
            continue
        if str(name) in names:
            raise RuntimeError(
                f"assistant identity migration table {table_name} has duplicate object name {name!r}"
            )
        names[str(name)] = item
    return objects
def _unique_exists(table_name: str, constraint_name: str) -> bool:
    return any(item.get("name") == constraint_name and item["unique"] for item in _unique_objects(table_name))


def _named_unique_matches(table_name: str, name: str, columns: Sequence[str]) -> bool:
    matches = [item for item in _unique_objects(table_name) if item.get("name") == name]
    if not matches:
        return False
    expected = list(columns)
    if not matches[0]["unique"] or matches[0]["columns"] != expected:
        raise RuntimeError(f"assistant identity migration table {table_name} unique {name!r} has columns {matches[0]['columns']!r}, expected {expected!r}")
    return True


def _named_index_matches(table_name: str, name: str, columns: Sequence[str]) -> bool:
    indexes = [item for item in _inspector().get_indexes(table_name) if item.get("name") == name]
    constraints = [item for item in _inspector().get_unique_constraints(table_name) if item.get("name") == name]
    if len(indexes) + len(constraints) > 1:
        raise RuntimeError(f"assistant identity migration table {table_name} has duplicate index/unique object name {name!r}")
    if constraints:
        raise RuntimeError(f"assistant identity migration table {table_name} object {name!r} is a unique constraint, expected an index")
    if not indexes:
        return False
    expected = list(columns)
    actual = list(indexes[0].get("column_names", []))
    if actual != expected:
        raise RuntimeError(f"assistant identity migration table {table_name} index {name!r} has columns {actual!r}, expected {expected!r}")
    return True


def _named_foreign_key_matches(table_name: str, name: str, local: Sequence[str], remote_table: str, remote: Sequence[str]) -> bool:
    matches = [item for item in _inspector().get_foreign_keys(table_name) if item.get("name") == name]
    if len(matches) > 1:
        raise RuntimeError(f"assistant identity migration table {table_name} has duplicate foreign key name {name!r}")
    if not matches:
        return False
    item = matches[0]
    expected_local, expected_remote = list(local), list(remote)
    actual_local, actual_remote = list(item.get("constrained_columns", [])), list(item.get("referred_columns", []))
    if actual_local != expected_local or item.get("referred_table") != remote_table or actual_remote != expected_remote:
        raise RuntimeError(f"assistant identity migration table {table_name} foreign key {name!r} has ({actual_local!r}) -> {item.get('referred_table')!r}({actual_remote!r}), expected ({expected_local!r}) -> {remote_table}({expected_remote!r})")
    return True

def upgrade() -> None:
    _require_table_columns("crm_assistant_conversations", ["id", "team_id", "user_id"])
    _require_table_columns("crm_assistant_messages", ["conversation_id", "team_id", "user_id", "seq"])
    _require_table_columns("crm_assistant_references", ["id", "team_id", "user_id"])
    if not _column_exists("crm_assistant_conversations", "next_message_seq"):
        op.add_column(
            "crm_assistant_conversations",
            sa.Column(
                "next_message_seq",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            ),
        )
    allocator = next(
        column for column in _inspector().get_columns("crm_assistant_conversations")
        if column["name"] == "next_message_seq"
    )
    if not isinstance(allocator["type"], sa.Integer) or allocator.get("nullable") is not False:
        raise RuntimeError(
            "assistant identity migration table crm_assistant_conversations column "
            "next_message_seq must be a non-null integer"
        )
    conversations = sa.table(
        "crm_assistant_conversations",
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
    # Retrying a partially applied migration must never rewind a populated allocator.
    op.get_bind().execute(
        conversations.update()
        .where(conversations.c.next_message_seq < next_seq)
        .values(next_message_seq=next_seq)
    )
    if not _named_unique_matches("crm_assistant_references", "uq_assistant_reference_owner", ["id", "team_id", "user_id"]):
        with op.batch_alter_table("crm_assistant_references") as batch:
            batch.create_unique_constraint(
                "uq_assistant_reference_owner",
                ["id", "team_id", "user_id"],
            )
    with op.batch_alter_table("crm_assistant_messages") as batch:
        if not _column_exists("crm_assistant_messages", "input_fingerprint"):
            batch.add_column(sa.Column("input_fingerprint", sa.String(64), nullable=True))
        if not _column_exists("crm_assistant_messages", "reference_id"):
            batch.add_column(sa.Column("reference_id", sa.BigInteger(), nullable=True))
        if not _named_foreign_key_matches(
            "crm_assistant_messages", "fk_assistant_message_reference_owner",
            ["reference_id", "team_id", "user_id"], "crm_assistant_references", ["id", "team_id", "user_id"],
        ):
            batch.create_foreign_key(
                "fk_assistant_message_reference_owner",
                "crm_assistant_references",
                ["reference_id", "team_id", "user_id"],
                ["id", "team_id", "user_id"],
            )
    if not _named_index_matches("crm_assistant_messages", "idx_assistant_message_reference_owner", ["team_id", "user_id", "conversation_id", "reference_id"]):
        op.create_index(
            "idx_assistant_message_reference_owner",
            "crm_assistant_messages",
            ["team_id", "user_id", "conversation_id", "reference_id"],
        )


def downgrade() -> None:
    if _index_exists("crm_assistant_messages", "idx_assistant_message_reference_owner"):
        op.drop_index(
            "idx_assistant_message_reference_owner",
            table_name="crm_assistant_messages",
        )
    with op.batch_alter_table("crm_assistant_messages") as batch:
        if _foreign_key_exists(
            "crm_assistant_messages", "fk_assistant_message_reference_owner"
        ):
            batch.drop_constraint(
                "fk_assistant_message_reference_owner",
                type_="foreignkey",
            )
        if _column_exists("crm_assistant_messages", "reference_id"):
            batch.drop_column("reference_id")
        if _column_exists("crm_assistant_messages", "input_fingerprint"):
            batch.drop_column("input_fingerprint")
    if _unique_exists("crm_assistant_references", "uq_assistant_reference_owner"):
        with op.batch_alter_table("crm_assistant_references") as batch:
            batch.drop_constraint("uq_assistant_reference_owner", type_="unique")
    if _column_exists("crm_assistant_conversations", "next_message_seq"):
        # Avoid rebuilding the parent table while migration154's children reference it.
        op.drop_column("crm_assistant_conversations", "next_message_seq")

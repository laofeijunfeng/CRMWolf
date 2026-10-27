"""Add durable identity and reference linkage to assistant messages."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "155_assistant_message_identity"
down_revision: str | None = "154_assistant_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in sa.inspect(op.get_bind()).get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name))


def _foreign_key_exists(table_name: str, constraint_name: str) -> bool:
    return any(
        item.get("name") == constraint_name
        for item in sa.inspect(op.get_bind()).get_foreign_keys(table_name)
    )

def _unique_exists(table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if any(item.get("name") == constraint_name for item in inspector.get_unique_constraints(table_name)):
        return True
    return any(item.get("name") == constraint_name and item.get("unique") for item in inspector.get_indexes(table_name))


def _recovered_branch_should_continue() -> bool:
    inspector = sa.inspect(op.get_bind())
    if "crm_assistant_conversations" not in inspector.get_table_names():
        return False
    return not _column_exists("crm_assistant_conversations", "version")


def upgrade() -> None:
    if not _recovered_branch_should_continue():
        return
    if not _column_exists("crm_assistant_conversations", "next_message_seq"):
        op.add_column(
            "crm_assistant_conversations",
            sa.Column("next_message_seq", sa.Integer(), nullable=False, server_default=sa.text("1")),
        )
    conversations = sa.table(
        "crm_assistant_conversations", sa.column("id", sa.BigInteger()),
        sa.column("team_id", sa.BigInteger()), sa.column("user_id", sa.BigInteger()),
        sa.column("next_message_seq", sa.Integer()),
    )
    messages = sa.table(
        "crm_assistant_messages", sa.column("conversation_id", sa.BigInteger()),
        sa.column("team_id", sa.BigInteger()), sa.column("user_id", sa.BigInteger()),
        sa.column("seq", sa.Integer()),
    )
    next_seq = sa.select(sa.func.coalesce(sa.func.max(messages.c.seq), 0) + 1).where(
        messages.c.conversation_id == conversations.c.id,
        messages.c.team_id == conversations.c.team_id,
        messages.c.user_id == conversations.c.user_id,
    ).scalar_subquery()
    # Retrying a partially applied migration must never rewind a populated allocator.
    op.get_bind().execute(
        conversations.update().where(conversations.c.next_message_seq < next_seq)
        .values(next_message_seq=next_seq)
    )
    if not _unique_exists("crm_assistant_references", "uq_assistant_reference_owner"):
        with op.batch_alter_table("crm_assistant_references") as batch:
            batch.create_unique_constraint("uq_assistant_reference_owner", ["id", "team_id", "user_id"])
    with op.batch_alter_table("crm_assistant_messages") as batch:
        if not _column_exists("crm_assistant_messages", "input_fingerprint"):
            batch.add_column(sa.Column("input_fingerprint", sa.String(64), nullable=True))
        if not _column_exists("crm_assistant_messages", "reference_id"):
            batch.add_column(sa.Column("reference_id", sa.BigInteger(), nullable=True))
        if not _foreign_key_exists("crm_assistant_messages", "fk_assistant_message_reference_owner"):
            batch.create_foreign_key(
                "fk_assistant_message_reference_owner", "crm_assistant_references",
                ["reference_id", "team_id", "user_id"], ["id", "team_id", "user_id"],
            )
    if not _index_exists("crm_assistant_messages", "idx_assistant_message_reference_owner"):
        op.create_index(
            "idx_assistant_message_reference_owner", "crm_assistant_messages",
            ["team_id", "user_id", "conversation_id", "reference_id"],
        )


def downgrade() -> None:
    if _index_exists("crm_assistant_messages", "idx_assistant_message_reference_owner"):
        op.drop_index("idx_assistant_message_reference_owner", table_name="crm_assistant_messages")
    with op.batch_alter_table("crm_assistant_messages") as batch:
        if _foreign_key_exists("crm_assistant_messages", "fk_assistant_message_reference_owner"):
            batch.drop_constraint("fk_assistant_message_reference_owner", type_="foreignkey")
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

"""Persist owner-scoped assistant conversations and attach legacy tasks.

Revision ID: 154_assistant_conversations
Revises: 153_remove_customer_profile_complete

This is the recovered parent of 156. It does not run again for a database
already stamped on this branch, and it refuses to create a legacy table when
the current 023 schema is already present or the install is still empty.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "154_assistant_conversations"
down_revision: str | None = "153_remove_customer_profile_complete"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in sa.inspect(op.get_bind()).get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name))


def _unique_exists(table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if any(item.get("name") == constraint_name for item in inspector.get_unique_constraints(table_name)):
        return True
    return any(
        item.get("name") == constraint_name and item.get("unique")
        for item in inspector.get_indexes(table_name)
    )


def _foreign_key_exists(table_name: str, constraint_name: str) -> bool:
    return any(
        item.get("name") == constraint_name
        for item in sa.inspect(op.get_bind()).get_foreign_keys(table_name)
    )


def _ensure_conversation_table() -> None:
    if not _table_exists("crm_assistant_conversations"):
        op.create_table(
            "crm_assistant_conversations",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("public_id", sa.String(64), nullable=False),
            sa.Column("team_id", sa.BigInteger(), nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("created_time", sa.DateTime(), nullable=False),
            sa.Column("last_modified_time", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("public_id"),
            sa.UniqueConstraint("id", "team_id", "user_id", name="uq_assistant_conversation_owner"),
        )
    if not _index_exists("crm_assistant_conversations", "idx_assistant_conversation_owner"):
        op.create_index(
            "idx_assistant_conversation_owner",
            "crm_assistant_conversations",
            ["team_id", "user_id", "last_modified_time", "id"],
        )
    if not _unique_exists("crm_assistant_conversations", "uq_assistant_conversation_owner"):
        with op.batch_alter_table("crm_assistant_conversations") as batch:
            batch.create_unique_constraint(
                "uq_assistant_conversation_owner", ["id", "team_id", "user_id"]
            )


def _ensure_task_conversation_link() -> None:
    connection = op.get_bind()
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        connection.exec_driver_sql("PRAGMA defer_foreign_keys=ON")
    with op.batch_alter_table("crm_assistant_tasks") as batch:
        if not _column_exists("crm_assistant_tasks", "conversation_id"):
            batch.add_column(sa.Column("conversation_id", sa.BigInteger(), nullable=True))
        if not _index_exists("crm_assistant_tasks", "idx_assistant_task_conversation"):
            batch.create_index("idx_assistant_task_conversation", ["team_id", "user_id", "conversation_id", "id"])
        if not _unique_exists("crm_assistant_tasks", "uq_assistant_task_owner"):
            batch.create_unique_constraint("uq_assistant_task_owner", ["id", "team_id", "user_id"])
        if not _foreign_key_exists("crm_assistant_tasks", "fk_assistant_task_conversation_owner"):
            batch.create_foreign_key(
                "fk_assistant_task_conversation_owner", "crm_assistant_conversations",
                ["conversation_id", "team_id", "user_id"], ["id", "team_id", "user_id"],
            )
    if sqlite:
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError("assistant conversation migration violated historical foreign keys")
        connection.exec_driver_sql("PRAGMA defer_foreign_keys=OFF")



def _recovered_branch_should_continue() -> bool:
    """Replay recovered DDL only when a legacy conversation table is already present.

    Databases stamped at 156 do not execute this revision again. A database that
    already has the current `version` column, or that has no conversation table
    yet, must not start a second history path; revision 023 creates the current
    schema and revision 157 merges the two branches.
    """
    if not _table_exists("crm_assistant_conversations"):
        return False
    return not _column_exists("crm_assistant_conversations", "version")


def upgrade() -> None:
    if not _recovered_branch_should_continue():
        return
    _ensure_conversation_table()
    _ensure_task_conversation_link()

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
            sa.UniqueConstraint("team_id", "user_id", "client_request_id", name="uq_assistant_message_request_owner"),
            sa.UniqueConstraint("conversation_id", "turn_id", "role", name="uq_assistant_message_turn_role"),
            sa.ForeignKeyConstraint(
                ["conversation_id", "team_id", "user_id"],
                ["crm_assistant_conversations.id", "crm_assistant_conversations.team_id", "crm_assistant_conversations.user_id"],
                name="fk_assistant_message_conversation_owner",
            ),
            sa.ForeignKeyConstraint(
                ["task_id", "team_id", "user_id"],
                ["crm_assistant_tasks.id", "crm_assistant_tasks.team_id", "crm_assistant_tasks.user_id"],
                name="fk_assistant_message_task_owner",
            ),
        )
    if not _index_exists("crm_assistant_messages", "idx_assistant_message_conversation_order"):
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
                ["crm_assistant_conversations.id", "crm_assistant_conversations.team_id", "crm_assistant_conversations.user_id"],
                name="fk_assistant_reference_conversation_owner",
            ),
            sa.ForeignKeyConstraint(
                ["resolved_task_id", "team_id", "user_id"],
                ["crm_assistant_tasks.id", "crm_assistant_tasks.team_id", "crm_assistant_tasks.user_id"],
                name="fk_assistant_reference_task_owner",
            ),
        )
    if not _index_exists("crm_assistant_references", "idx_assistant_reference_conversation"):
        op.create_index(
            "idx_assistant_reference_conversation",
            "crm_assistant_references",
            ["team_id", "user_id", "conversation_id", "id"],
        )

    tasks = sa.table(
        "crm_assistant_tasks", sa.column("team_id", sa.BigInteger()), sa.column("user_id", sa.BigInteger()),
        sa.column("conversation_id", sa.BigInteger()), sa.column("created_time", sa.DateTime()),
        sa.column("last_modified_time", sa.DateTime()),
    )
    conversations = sa.table(
        "crm_assistant_conversations", sa.column("id", sa.BigInteger()), sa.column("public_id", sa.String(64)),
        sa.column("team_id", sa.BigInteger()), sa.column("user_id", sa.BigInteger()),
        sa.column("created_time", sa.DateTime()), sa.column("last_modified_time", sa.DateTime()),
    )
    owner_groups = connection.execute(
        sa.select(
            tasks.c.team_id, tasks.c.user_id,
            sa.func.min(tasks.c.created_time).label("created_time"),
            sa.func.max(tasks.c.last_modified_time).label("last_modified_time"),
        ).group_by(tasks.c.team_id, tasks.c.user_id).order_by(tasks.c.team_id, tasks.c.user_id)
    ).mappings()
    for group in owner_groups:
        existing = connection.execute(
            sa.select(conversations.c.id).where(
                conversations.c.team_id == group["team_id"],
                conversations.c.user_id == group["user_id"],
            )
        ).scalar_one_or_none()
        if existing is None:
            connection.execute(conversations.insert().values(
                public_id=f"acv_legacy_{group['team_id']}_{group['user_id']}",
                team_id=group["team_id"], user_id=group["user_id"],
                created_time=group["created_time"], last_modified_time=group["last_modified_time"],
            ))
    owner_conversation = sa.select(conversations.c.id).where(
        conversations.c.team_id == tasks.c.team_id, conversations.c.user_id == tasks.c.user_id,
    ).scalar_subquery()
    connection.execute(tasks.update().where(tasks.c.conversation_id.is_(None)).values(conversation_id=owner_conversation))


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

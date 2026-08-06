"""add public id to follow up task events

Revision ID: 070_follow_up_task_event_public_id
Revises: 069_follow_up_task_confirmation_cases
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "070_follow_up_task_event_public_id"
down_revision: str | None = "069_follow_up_task_confirmation_cases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"),
            {"table_name": table_name},
        ).all()
        return bool(rows)

    return (
        conn.execute(
            text("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
            """),
            {"table_name": table_name},
        ).scalar()
        > 0
    )


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).all()
        return any(row[1] == column_name for row in rows)

    return (
        conn.execute(
            text("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
                  AND column_name = :column_name
            """),
            {"table_name": table_name, "column_name": column_name},
        ).scalar()
        > 0
    )


def _index_exists(table_name: str, index_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(text(f"PRAGMA index_list({table_name})")).all()
        return any(row[1] == index_name for row in rows)

    return (
        conn.execute(
            text("""
                SELECT COUNT(*) FROM information_schema.statistics
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
                  AND index_name = :index_name
            """),
            {"table_name": table_name, "index_name": index_name},
        ).scalar()
        > 0
    )


def _backfill_public_ids() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        conn.execute(
            text("""
                UPDATE crm_follow_up_task_events
                SET public_id = 'fte_' || lower(hex(randomblob(16)))
                WHERE public_id IS NULL OR public_id = ''
            """)
        )
        return

    conn.execute(
        text("""
            UPDATE crm_follow_up_task_events
            SET public_id = CONCAT('fte_', REPLACE(UUID(), '-', ''))
            WHERE public_id IS NULL OR public_id = ''
        """)
    )


def upgrade() -> None:
    table_name = "crm_follow_up_task_events"
    if not _table_exists(table_name):
        return

    if not _column_exists(table_name, "public_id"):
        op.add_column(table_name, sa.Column("public_id", sa.String(length=64), nullable=True, comment="对外任务事件ID"))

    _backfill_public_ids()

    if op.get_bind().dialect.name != "sqlite":
        op.alter_column(table_name, "public_id", existing_type=sa.String(length=64), nullable=False)

    dialect_name = op.get_bind().dialect.name
    if not _index_exists(table_name, "idx_follow_up_task_event_public_id"):
        op.create_index("idx_follow_up_task_event_public_id", table_name, ["public_id"])
    if dialect_name != "sqlite" and not _index_exists(table_name, "uq_follow_up_task_event_public_id"):
        op.create_unique_constraint("uq_follow_up_task_event_public_id", table_name, ["public_id"])


def downgrade() -> None:
    table_name = "crm_follow_up_task_events"
    if not _table_exists(table_name) or not _column_exists(table_name, "public_id"):
        return

    dialect_name = op.get_bind().dialect.name
    if dialect_name != "sqlite" and _index_exists(table_name, "uq_follow_up_task_event_public_id"):
        op.drop_constraint("uq_follow_up_task_event_public_id", table_name, type_="unique")
    if _index_exists(table_name, "idx_follow_up_task_event_public_id"):
        op.drop_index("idx_follow_up_task_event_public_id", table_name=table_name)
    op.drop_column(table_name, "public_id")

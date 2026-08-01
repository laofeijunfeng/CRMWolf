"""view preference sort order

Revision ID: 054_view_preference_sort_order
Revises: 053_view_preference_custom_view_keys
Create Date: 2026-08-01

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "054_view_preference_sort_order"
down_revision: str | None = "053_view_preference_custom_view_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
    """), {"table_name": table_name}).scalar() > 0


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
          AND column_name = :column_name
    """), {"table_name": table_name, "column_name": column_name}).scalar() > 0


def upgrade() -> None:
    if not _table_exists("crm_view_preferences"):
        return

    if not _column_exists("crm_view_preferences", "sort_order"):
        op.add_column(
            "crm_view_preferences",
            sa.Column("sort_order", sa.BigInteger(), nullable=True, comment="自定义视图排序值，越小越靠前"),
        )


def downgrade() -> None:
    if not _table_exists("crm_view_preferences"):
        return

    if _column_exists("crm_view_preferences", "sort_order"):
        op.drop_column("crm_view_preferences", "sort_order")

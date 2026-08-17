"""Align Agent async operation collation with customer intelligence runs.

Revision ID: 095_agent_async_operation_collation
Revises: 094_confirmation_delivery_activity_revision
Create Date: 2026-08-17
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "095_agent_async_operation_collation"
down_revision: str | None = "094_confirmation_delivery_activity_revision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("crm_agent_async_operations",)


def _table_exists(table_name: str) -> bool:
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        return bool(connection.execute(
            text("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = :table_name"),
            {"table_name": table_name},
        ).scalar())
    return bool(connection.execute(text("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
    """), {"table_name": table_name}).scalar())


def _convert_mysql_tables(collation: str) -> None:
    connection = op.get_bind()
    if connection.dialect.name != "mysql":
        return
    for table_name in TABLES:
        if _table_exists(table_name):
            op.execute(
                f"ALTER TABLE {table_name} "
                f"CONVERT TO CHARACTER SET utf8mb4 COLLATE {collation}"
            )


def upgrade() -> None:
    _convert_mysql_tables("utf8mb4_general_ci")


def downgrade() -> None:
    _convert_mysql_tables("utf8mb4_unicode_ci")

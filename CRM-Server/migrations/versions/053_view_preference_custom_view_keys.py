"""view preference custom view keys

Revision ID: 053_view_preference_custom_view_keys
Revises: 052_view_preferences
Create Date: 2026-08-01

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "053_view_preference_custom_view_keys"
down_revision: str | None = "052_view_preferences"
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


def _constraint_exists(table_name: str, constraint_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.table_constraints
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
          AND constraint_name = :constraint_name
    """), {"table_name": table_name, "constraint_name": constraint_name}).scalar() > 0


def upgrade() -> None:
    if not _table_exists("crm_view_preferences"):
        return

    if not _column_exists("crm_view_preferences", "preference_key"):
        op.add_column(
            "crm_view_preferences",
            sa.Column(
                "preference_key",
                sa.String(length=120),
                nullable=False,
                server_default="default",
                comment="偏好标识，默认偏好为default",
            ),
        )

    if _constraint_exists("crm_view_preferences", "uk_view_pref_owner"):
        op.drop_constraint("uk_view_pref_owner", "crm_view_preferences", type_="unique")

    if not _constraint_exists("crm_view_preferences", "uk_view_pref_owner_key"):
        op.create_unique_constraint(
            "uk_view_pref_owner_key",
            "crm_view_preferences",
            ["team_id", "view_key", "scope", "user_id", "preference_key"],
        )


def downgrade() -> None:
    if not _table_exists("crm_view_preferences"):
        return

    if _constraint_exists("crm_view_preferences", "uk_view_pref_owner_key"):
        op.drop_constraint("uk_view_pref_owner_key", "crm_view_preferences", type_="unique")

    if _column_exists("crm_view_preferences", "preference_key"):
        op.drop_column("crm_view_preferences", "preference_key")

    if not _constraint_exists("crm_view_preferences", "uk_view_pref_owner"):
        op.create_unique_constraint(
            "uk_view_pref_owner",
            "crm_view_preferences",
            ["team_id", "view_key", "scope", "user_id"],
        )

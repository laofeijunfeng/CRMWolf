"""view preferences

Revision ID: 052_view_preferences
Revises: 051_customer_activity_next_follow_time_source
Create Date: 2026-07-30

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "052_view_preferences"
down_revision: str | None = "051_customer_activity_next_follow_time_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
    """), {"table_name": table_name}).scalar() > 0


def upgrade() -> None:
    if _table_exists("crm_view_preferences"):
        return

    op.create_table(
        "crm_view_preferences",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, server_default="0", comment="用户ID，团队级配置为0"),
        sa.Column("view_key", sa.String(length=100), nullable=False, comment="视图标识，如 customers.list"),
        sa.Column("scope", sa.String(length=20), nullable=False, comment="作用域：personal/team"),
        sa.Column("preference_key", sa.String(length=120), nullable=False, server_default="default", comment="偏好标识，默认偏好为default"),
        sa.Column("name", sa.String(length=100), nullable=True, comment="视图名称"),
        sa.Column("is_default", sa.BigInteger(), nullable=False, server_default="1", comment="是否默认视图"),
        sa.Column("config_json", sa.Text(), nullable=False, comment="视图偏好JSON"),
        sa.Column("created_by", sa.BigInteger(), nullable=False, comment="创建人ID"),
        sa.Column("updated_by", sa.BigInteger(), nullable=False, comment="更新人ID"),
        sa.Column("created_time", sa.DateTime(), nullable=True, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=True, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "view_key", "scope", "user_id", "preference_key", name="uk_view_pref_owner_key"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="视图偏好配置表",
    )
    op.create_index("idx_view_pref_team_view", "crm_view_preferences", ["team_id", "view_key"])
    op.create_index("idx_view_pref_user", "crm_view_preferences", ["team_id", "user_id"])


def downgrade() -> None:
    if _table_exists("crm_view_preferences"):
        op.drop_index("idx_view_pref_user", table_name="crm_view_preferences")
        op.drop_index("idx_view_pref_team_view", table_name="crm_view_preferences")
        op.drop_table("crm_view_preferences")

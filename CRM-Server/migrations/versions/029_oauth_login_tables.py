"""add oauth login tables

Revision ID: 029_oauth_login_tables
Revises: 028_normalize_opportunity_names
Create Date: 2026-07-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "029_oauth_login_tables"
down_revision: Union[str, None] = "028_normalize_opportunity_names"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oauth_provider_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False, comment="团队ID"),
        sa.Column("provider", sa.String(length=32), nullable=False, comment="OAuth 提供方"),
        sa.Column("app_id", sa.String(length=128), nullable=False, comment="应用 ID"),
        sa.Column("app_secret_encrypted", sa.String(length=1000), nullable=True, comment="加密后的应用密钥"),
        sa.Column("redirect_uri", sa.String(length=500), nullable=False, comment="授权回调地址"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("0"), comment="是否启用"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=True, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "provider", name="uq_oauth_provider_config_team_provider"),
    )
    op.create_index("idx_oauth_provider_configs_team_id", "oauth_provider_configs", ["team_id"])
    op.create_index("idx_oauth_provider_configs_team_provider", "oauth_provider_configs", ["team_id", "provider"])

    op.create_table(
        "user_oauth_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="CRM 用户ID"),
        sa.Column("team_id", sa.Integer(), nullable=False, comment="团队ID"),
        sa.Column("provider", sa.String(length=32), nullable=False, comment="OAuth 提供方"),
        sa.Column("provider_user_id", sa.String(length=128), nullable=True, comment="提供方用户ID"),
        sa.Column("open_id", sa.String(length=128), nullable=True, comment="Open ID"),
        sa.Column("union_id", sa.String(length=128), nullable=True, comment="Union ID"),
        sa.Column("tenant_key", sa.String(length=128), nullable=True, comment="租户标识"),
        sa.Column("email", sa.String(length=255), nullable=True, comment="邮箱"),
        sa.Column("mobile", sa.String(length=32), nullable=True, comment="手机号"),
        sa.Column("name", sa.String(length=100), nullable=True, comment="第三方用户名"),
        sa.Column("avatar_url", sa.String(length=500), nullable=True, comment="头像"),
        sa.Column("raw_profile", mysql.JSON(), nullable=True, comment="原始用户资料"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=True, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "provider", "open_id", name="uq_user_oauth_team_provider_open_id"),
        sa.UniqueConstraint("team_id", "provider", "user_id", name="uq_user_oauth_team_provider_user"),
    )
    op.create_index("idx_user_oauth_accounts_user_id", "user_oauth_accounts", ["user_id"])
    op.create_index("idx_user_oauth_accounts_team_id", "user_oauth_accounts", ["team_id"])
    op.create_index("idx_user_oauth_accounts_lookup", "user_oauth_accounts", ["team_id", "provider", "open_id"])


def downgrade() -> None:
    op.drop_index("idx_user_oauth_accounts_lookup", table_name="user_oauth_accounts")
    op.drop_index("idx_user_oauth_accounts_team_id", table_name="user_oauth_accounts")
    op.drop_index("idx_user_oauth_accounts_user_id", table_name="user_oauth_accounts")
    op.drop_table("user_oauth_accounts")
    op.drop_index("idx_oauth_provider_configs_team_provider", table_name="oauth_provider_configs")
    op.drop_index("idx_oauth_provider_configs_team_id", table_name="oauth_provider_configs")
    op.drop_table("oauth_provider_configs")

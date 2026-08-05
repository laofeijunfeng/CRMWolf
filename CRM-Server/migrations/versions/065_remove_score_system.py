"""remove score system

Revision ID: 065_remove_score_system
Revises: 064_customer_identity_terms
Create Date: 2026-08-05

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "065_remove_score_system"
down_revision: str | None = "064_customer_identity_terms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        return bool(conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"),
            {"table_name": table_name},
        ).all())
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
    """), {"table_name": table_name}).scalar() > 0


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(text(f'PRAGMA table_info("{table_name}")')).mappings().all()
        return any(row["name"] == column_name for row in rows)
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
          AND column_name = :column_name
    """), {"table_name": table_name, "column_name": column_name}).scalar() > 0


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    if _table_exists(table_name) and _column_exists(table_name, column_name):
        op.drop_column(table_name, column_name)


def upgrade() -> None:
    if _table_exists("crm_score_details"):
        op.drop_table("crm_score_details")
    if _table_exists("crm_score_weight_configs"):
        op.drop_table("crm_score_weight_configs")

    for table_name in ("crm_leads", "crm_customers"):
        _drop_column_if_exists(table_name, "score_updated_at")
        _drop_column_if_exists(table_name, "score")


def downgrade() -> None:
    for table_name in ("crm_leads", "crm_customers"):
        if _table_exists(table_name) and not _column_exists(table_name, "score"):
            op.add_column(table_name, sa.Column("score", sa.Integer(), nullable=True, comment="热力值分数（0-100）"))
        if _table_exists(table_name) and not _column_exists(table_name, "score_updated_at"):
            op.add_column(table_name, sa.Column("score_updated_at", sa.DateTime(), nullable=True, comment="热力值最后更新时间"))

    if not _table_exists("crm_score_weight_configs"):
        op.create_table(
            "crm_score_weight_configs",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("team_id", sa.BigInteger(), nullable=True, comment="团队ID（NULL表示系统默认）"),
            sa.Column("module_type", sa.String(20), nullable=False, comment="模块类型：LEAD/CUSTOMER"),
            sa.Column("factor_key", sa.String(50), nullable=False, comment="因子键名"),
            sa.Column("factor_name", sa.String(100), nullable=False, comment="因子显示名称"),
            sa.Column("weight_value", sa.Integer(), nullable=False, comment="权重值（正负整数）"),
            sa.Column("is_enabled", sa.Integer(), nullable=False, server_default="1", comment="是否启用：1启用，0禁用"),
            sa.Column("condition_rules", sa.Text(), nullable=True, comment="条件规则JSON"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0", comment="排序序号"),
            sa.Column("created_by", sa.String(100), nullable=False, comment="创建人"),
            sa.Column("created_time", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_by", sa.String(100), nullable=True, comment="更新人"),
            sa.Column("updated_time", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            comment="热力值权重配置表",
        )
        op.create_index("idx_score_weight_team_module", "crm_score_weight_configs", ["team_id", "module_type"])
        op.create_index("idx_score_weight_factor_key", "crm_score_weight_configs", ["factor_key"])

    if not _table_exists("crm_score_details"):
        op.create_table(
            "crm_score_details",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("module_type", sa.String(20), nullable=False, comment="模块类型：LEAD/CUSTOMER"),
            sa.Column("record_id", sa.BigInteger(), nullable=False, comment="线索或客户ID"),
            sa.Column("factor_key", sa.String(50), nullable=False, comment="因子键名"),
            sa.Column("factor_name", sa.String(100), nullable=False, comment="因子名称"),
            sa.Column("weight_value", sa.Integer(), nullable=False, comment="权重值"),
            sa.Column("actual_value", sa.String(200), nullable=True, comment="实际值"),
            sa.Column("score_change", sa.Integer(), nullable=False, comment="分数变化"),
            sa.Column("reason", sa.String(500), nullable=True, comment="计算原因说明"),
            sa.Column("calculated_time", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            comment="热力值计算明细表",
        )
        op.create_index("idx_score_detail_record", "crm_score_details", ["module_type", "record_id"])
        op.create_index("idx_score_detail_calculated_time", "crm_score_details", ["calculated_time"])
        op.create_index("idx_score_detail_team_id", "crm_score_details", ["team_id"])

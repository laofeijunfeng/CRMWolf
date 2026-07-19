"""repair score system tables

Revision ID: 025_repair_score_system_tables
Revises: 024_contract_attachment_fields
Create Date: 2026-07-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "025_repair_score_system_tables"
down_revision: Union[str, None] = "024_contract_attachment_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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


def _index_exists(table_name: str, index_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.statistics
        WHERE table_schema = DATABASE()
        AND table_name = :table_name
        AND index_name = :index_name
    """), {"table_name": table_name, "index_name": index_name}).scalar() > 0


def _ensure_score_columns() -> None:
    for table_name in ("crm_leads", "crm_customers"):
        if not _column_exists(table_name, "score"):
            op.add_column(table_name, sa.Column("score", sa.Integer(), nullable=True, comment="热力值分数（0-100）"))
        if not _column_exists(table_name, "score_updated_at"):
            op.add_column(table_name, sa.Column("score_updated_at", sa.DateTime(), nullable=True, comment="热力值最后更新时间"))


def _ensure_weight_table() -> None:
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

    if not _index_exists("crm_score_weight_configs", "idx_score_weight_team_module"):
        op.create_index("idx_score_weight_team_module", "crm_score_weight_configs", ["team_id", "module_type"])
    if not _index_exists("crm_score_weight_configs", "idx_score_weight_factor_key"):
        op.create_index("idx_score_weight_factor_key", "crm_score_weight_configs", ["factor_key"])


def _ensure_detail_table() -> None:
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

    if not _index_exists("crm_score_details", "idx_score_detail_record"):
        op.create_index("idx_score_detail_record", "crm_score_details", ["module_type", "record_id"])
    if not _index_exists("crm_score_details", "idx_score_detail_calculated_time"):
        op.create_index("idx_score_detail_calculated_time", "crm_score_details", ["calculated_time"])
    if not _index_exists("crm_score_details", "idx_score_detail_team_id"):
        op.create_index("idx_score_detail_team_id", "crm_score_details", ["team_id"])


def _insert_default_weights() -> None:
    conn = op.get_bind()
    defaults = [
        ("LEAD", "source", "线索来源", 10, '{"客户推荐": 20, "市场活动": 12, "线上注册": 15, "展会": 10, "网站咨询": 8, "电话营销": 5, "其他": 3}', 1),
        ("LEAD", "company_scale", "公司规模", 8, '{"1000人以上": 15, "501-1000人": 12, "201-500人": 8, "51-200人": 5, "1-50人": 2}', 2),
        ("LEAD", "status", "状态", 5, '{"FOLLOWING": 10, "NEW": 5, "CONVERTED": 0, "INVALID": 0}', 3),
        ("LEAD", "in_pool", "在公海池", -10, None, 4),
        ("LEAD", "last_follow_up_days", "最近跟进时间", 0, '{"<=7": 5, "7-30": -5, ">30": -10, "none": -10}', 5),
        ("LEAD", "next_follow_time", "下次跟进时间", 5, '{"has_plan": 5, "no_plan": 0}', 6),
        ("CUSTOMER", "opportunity_count", "商机数量", 10, '{"max_count": 3, "per_count": 10}', 1),
        ("CUSTOMER", "opportunity_amount", "商机金额", 15, '{"per_100k": 1, "max_score": 30}', 2),
        ("CUSTOMER", "opportunity_win_prob", "商机赢率", 12, '{"weighted_by_probability": true}', 3),
        ("CUSTOMER", "contract_count", "合同数量", 15, '{"max_count": 2, "per_count": 15}', 4),
        ("CUSTOMER", "contract_amount", "合同金额", 20, '{"per_100k": 2, "max_score": 40}', 5),
        ("CUSTOMER", "payment_status", "回款状态", 10, '{"COMPLETED": 15, "PARTIAL": 8, "UNPAID": 0, "OVERDUE": -5}', 6),
        ("CUSTOMER", "decision_maker_count", "决策人数量", 8, '{"has_dm": 8, "no_dm": 0}', 7),
        ("CUSTOMER", "primary_contact", "主联系人", 5, '{"has_primary": 5, "no_primary": 0}', 8),
        ("CUSTOMER", "status", "客户状态", 5, '{"WON": 20, "FOLLOWING": 10, "LOST": -10, "INACTIVE": -15}', 9),
        ("CUSTOMER", "return_count", "退回公海次数", -10, '{"has_return": -10, "no_return": 0}', 10),
    ]

    for module_type, factor_key, factor_name, weight_value, rules, sort_order in defaults:
        exists = conn.execute(text("""
            SELECT COUNT(*) FROM crm_score_weight_configs
            WHERE team_id IS NULL
            AND module_type = :module_type
            AND factor_key = :factor_key
        """), {"module_type": module_type, "factor_key": factor_key}).scalar()
        if exists:
            continue

        conn.execute(text("""
            INSERT INTO crm_score_weight_configs
            (team_id, module_type, factor_key, factor_name, weight_value, is_enabled, condition_rules, sort_order, created_by, created_time, updated_time)
            VALUES (NULL, :module_type, :factor_key, :factor_name, :weight_value, 1, :rules, :sort_order, 'system', NOW(), NOW())
        """), {
            "module_type": module_type,
            "factor_key": factor_key,
            "factor_name": factor_name,
            "weight_value": weight_value,
            "rules": rules,
            "sort_order": sort_order,
        })


def upgrade() -> None:
    _ensure_score_columns()
    _ensure_weight_table()
    _ensure_detail_table()
    _insert_default_weights()


def downgrade() -> None:
    pass

"""customer context answer telemetry

Revision ID: 063_customer_context_answer_telemetry
Revises: 062_customer_lead_public_ids
Create Date: 2026-08-04

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "063_customer_context_answer_telemetry"
down_revision: str | None = "062_customer_lead_public_ids"
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
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
    """), {"table_name": table_name}).scalar() > 0


def upgrade() -> None:
    if _table_exists("crm_customer_context_answer_telemetry"):
        return

    op.create_table(
        "crm_customer_context_answer_telemetry",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="租户ID，当前与团队ID一致"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("customer_id", sa.BigInteger(), nullable=True, comment="客户ID"),
        sa.Column("question_text", sa.Text(), nullable=True, comment="用户问题"),
        sa.Column("answer_source", sa.String(length=80), nullable=False, comment="回答来源"),
        sa.Column("answer_mode", sa.String(length=30), nullable=False, comment="回答模式"),
        sa.Column("model", sa.String(length=120), nullable=True, comment="模型"),
        sa.Column("fallback_reason", sa.String(length=120), nullable=True, comment="降级原因"),
        sa.Column("fallback_error", sa.Text(), nullable=True, comment="降级错误"),
        sa.Column("retrieval_status", sa.String(length=40), nullable=True, comment="检索状态"),
        sa.Column("retrieval_strategy", sa.String(length=80), nullable=True, comment="检索策略"),
        sa.Column("semantic_evidence_count", sa.Integer(), nullable=False, server_default="0", comment="语义证据数量"),
        sa.Column("citation_count", sa.Integer(), nullable=False, server_default="0", comment="引用数量"),
        sa.Column("top_score", sa.Float(), nullable=True, comment="最高召回分"),
        sa.Column("min_score", sa.Float(), nullable=True, comment="最低接纳分"),
        sa.Column("raw_count", sa.Integer(), nullable=True, comment="原始召回数量"),
        sa.Column("returned_count", sa.Integer(), nullable=True, comment="返回证据数量"),
        sa.Column("dropped_count", sa.Integer(), nullable=True, comment="被阈值过滤数量"),
        sa.Column("used_sections_json", sa.JSON(), nullable=True, comment="回答使用的上下文分区"),
        sa.Column("missing_context_json", sa.JSON(), nullable=True, comment="缺失上下文"),
        sa.Column("citations_json", sa.JSON(), nullable=True, comment="回答引用"),
        sa.Column("retrieval_json", sa.JSON(), nullable=True, comment="检索状态快照"),
        sa.Column("created_time", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="创建时间"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
        comment="客户上下文回答质量遥测表",
    )
    table_name = "crm_customer_context_answer_telemetry"
    op.create_index("ix_crm_customer_context_answer_telemetry_answer_mode", table_name, ["answer_mode"])
    op.create_index("ix_crm_customer_context_answer_telemetry_answer_source", table_name, ["answer_source"])
    op.create_index("ix_crm_customer_context_answer_telemetry_created_time", table_name, ["created_time"])
    op.create_index("ix_crm_customer_context_answer_telemetry_customer_id", table_name, ["customer_id"])
    op.create_index("ix_crm_customer_context_answer_telemetry_fallback_reason", table_name, ["fallback_reason"])
    op.create_index("ix_crm_customer_context_answer_telemetry_model", table_name, ["model"])
    op.create_index("ix_crm_customer_context_answer_telemetry_retrieval_status", table_name, ["retrieval_status"])
    op.create_index("ix_crm_customer_context_answer_telemetry_retrieval_strategy", table_name, ["retrieval_strategy"])
    op.create_index("ix_crm_customer_context_answer_telemetry_team_id", table_name, ["team_id"])
    op.create_index("ix_crm_customer_context_answer_telemetry_tenant_id", table_name, ["tenant_id"])
    op.create_index("idx_customer_context_answer_customer_time", table_name, ["team_id", "customer_id", "created_time"])
    op.create_index("idx_customer_context_answer_quality", table_name, ["team_id", "answer_mode", "retrieval_status"])


def downgrade() -> None:
    if _table_exists("crm_customer_context_answer_telemetry"):
        op.drop_table("crm_customer_context_answer_telemetry")

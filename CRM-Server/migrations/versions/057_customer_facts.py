"""customer facts

Revision ID: 057_customer_facts
Revises: 056_agent_memory_entries
Create Date: 2026-08-02

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "057_customer_facts"
down_revision: str | None = "056_agent_memory_entries"
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
    if not _table_exists("crm_customer_facts"):
        op.create_table(
            "crm_customer_facts",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("fact_key", sa.String(length=64), nullable=False, comment="客户事实幂等键"),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="租户ID，当前与团队ID一致"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="客户ID"),
            sa.Column("fact_type", sa.String(length=50), nullable=False, comment="事实类型"),
            sa.Column("subject", sa.String(length=255), nullable=True, comment="事实主体"),
            sa.Column("content", sa.Text(), nullable=False, comment="事实内容"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0", comment="事实置信度"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE", comment="事实状态"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1", comment="事实版本号"),
            sa.Column("occurred_at", sa.DateTime(), nullable=True, comment="事实发生时间"),
            sa.Column("extracted_at", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="事实提取时间"),
            sa.Column("created_time", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="创建时间"),
            sa.Column("updated_time", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="更新时间"),
            sa.ForeignKeyConstraint(["customer_id"], ["crm_customers.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("fact_key"),
            sa.UniqueConstraint("team_id", "customer_id", "fact_type", "subject", name="uq_customer_fact_subject"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="客户智能事实表",
        )
        op.create_index("ix_crm_customer_facts_customer_id", "crm_customer_facts", ["customer_id"])
        op.create_index("ix_crm_customer_facts_fact_key", "crm_customer_facts", ["fact_key"])
        op.create_index("ix_crm_customer_facts_fact_type", "crm_customer_facts", ["fact_type"])
        op.create_index("ix_crm_customer_facts_occurred_at", "crm_customer_facts", ["occurred_at"])
        op.create_index("ix_crm_customer_facts_status", "crm_customer_facts", ["status"])
        op.create_index("ix_crm_customer_facts_team_id", "crm_customer_facts", ["team_id"])
        op.create_index("ix_crm_customer_facts_tenant_id", "crm_customer_facts", ["tenant_id"])
        op.create_index("idx_customer_fact_customer_status", "crm_customer_facts", ["team_id", "customer_id", "status"])
        op.create_index("idx_customer_fact_type_time", "crm_customer_facts", ["team_id", "customer_id", "fact_type", "occurred_at"])
    elif not _column_exists("crm_customer_facts", "version"):
        op.add_column(
            "crm_customer_facts",
            sa.Column("version", sa.Integer(), nullable=False, server_default="1", comment="事实版本号"),
        )

    if not _table_exists("crm_customer_fact_sources"):
        op.create_table(
            "crm_customer_fact_sources",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("fact_id", sa.BigInteger(), nullable=False, comment="客户事实ID"),
            sa.Column("source_type", sa.String(length=50), nullable=False, comment="来源类型"),
            sa.Column("source_object_id", sa.String(length=100), nullable=False, comment="来源对象ID"),
            sa.Column("business_object_type", sa.String(length=50), nullable=True, comment="业务对象类型"),
            sa.Column("business_object_id", sa.String(length=100), nullable=True, comment="业务对象ID"),
            sa.Column("evidence_id", sa.String(length=64), nullable=True, comment="向量证据ID"),
            sa.Column("quote", sa.Text(), nullable=True, comment="引用片段"),
            sa.Column("created_time", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="创建时间"),
            sa.ForeignKeyConstraint(["fact_id"], ["crm_customer_facts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("fact_id", "source_type", "source_object_id", name="uq_customer_fact_source"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="客户智能事实来源表",
        )
        op.create_index("ix_crm_customer_fact_sources_evidence_id", "crm_customer_fact_sources", ["evidence_id"])
        op.create_index("ix_crm_customer_fact_sources_fact_id", "crm_customer_fact_sources", ["fact_id"])
        op.create_index("ix_crm_customer_fact_sources_source_type", "crm_customer_fact_sources", ["source_type"])
        op.create_index("idx_customer_fact_source_business", "crm_customer_fact_sources", ["business_object_type", "business_object_id"])

    if not _table_exists("crm_customer_fact_revisions"):
        op.create_table(
            "crm_customer_fact_revisions",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("fact_id", sa.BigInteger(), nullable=False, comment="客户事实ID"),
            sa.Column("version", sa.Integer(), nullable=False, comment="修订后的事实版本号"),
            sa.Column("change_type", sa.String(length=20), nullable=False, comment="修订类型"),
            sa.Column("previous_content", sa.Text(), nullable=True, comment="修订前事实内容"),
            sa.Column("new_content", sa.Text(), nullable=False, comment="修订后事实内容"),
            sa.Column("previous_confidence", sa.Float(), nullable=True, comment="修订前置信度"),
            sa.Column("new_confidence", sa.Float(), nullable=False, comment="修订后置信度"),
            sa.Column("previous_status", sa.String(length=20), nullable=True, comment="修订前状态"),
            sa.Column("new_status", sa.String(length=20), nullable=False, comment="修订后状态"),
            sa.Column("previous_occurred_at", sa.DateTime(), nullable=True, comment="修订前发生时间"),
            sa.Column("new_occurred_at", sa.DateTime(), nullable=True, comment="修订后发生时间"),
            sa.Column("source_type", sa.String(length=50), nullable=True, comment="触发本次修订的来源类型"),
            sa.Column("source_object_id", sa.String(length=100), nullable=True, comment="触发本次修订的来源对象ID"),
            sa.Column("business_object_type", sa.String(length=50), nullable=True, comment="业务对象类型"),
            sa.Column("business_object_id", sa.String(length=100), nullable=True, comment="业务对象ID"),
            sa.Column("evidence_id", sa.String(length=64), nullable=True, comment="向量证据ID"),
            sa.Column("quote", sa.Text(), nullable=True, comment="引用片段"),
            sa.Column("created_time", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="创建时间"),
            sa.ForeignKeyConstraint(["fact_id"], ["crm_customer_facts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("fact_id", "version", name="uq_customer_fact_revision_version"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="客户智能事实版本审计表",
        )
        op.create_index("ix_crm_customer_fact_revisions_change_type", "crm_customer_fact_revisions", ["change_type"])
        op.create_index("ix_crm_customer_fact_revisions_evidence_id", "crm_customer_fact_revisions", ["evidence_id"])
        op.create_index("ix_crm_customer_fact_revisions_fact_id", "crm_customer_fact_revisions", ["fact_id"])
        op.create_index("ix_crm_customer_fact_revisions_source_type", "crm_customer_fact_revisions", ["source_type"])
        op.create_index("idx_customer_fact_revision_source", "crm_customer_fact_revisions", ["source_type", "source_object_id"])

    if not _table_exists("crm_customer_fact_review_audits"):
        op.create_table(
            "crm_customer_fact_review_audits",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("review_key", sa.String(length=64), nullable=False, comment="复核幂等键"),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="租户ID，当前与团队ID一致"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="客户ID"),
            sa.Column("event_key", sa.String(length=120), nullable=False, comment="触发事件键"),
            sa.Column("fact_id", sa.BigInteger(), nullable=True, comment="采纳后事实ID"),
            sa.Column("existing_fact_id", sa.BigInteger(), nullable=True, comment="冲突的既有事实ID"),
            sa.Column("existing_version", sa.Integer(), nullable=True, comment="冲突的既有事实版本"),
            sa.Column("fact_type", sa.String(length=50), nullable=False, comment="候选事实类型"),
            sa.Column("subject", sa.String(length=255), nullable=True, comment="候选事实主体"),
            sa.Column("candidate_content", sa.Text(), nullable=False, comment="候选事实内容"),
            sa.Column("candidate_confidence", sa.Float(), nullable=False, server_default="0", comment="候选事实置信度"),
            sa.Column("decision", sa.String(length=20), nullable=False, comment="人工决策"),
            sa.Column("decision_source", sa.String(length=50), nullable=True, comment="决策来源"),
            sa.Column("reviewer_id", sa.BigInteger(), nullable=True, comment="复核人ID"),
            sa.Column("reason", sa.Text(), nullable=True, comment="复核原因"),
            sa.Column("conflict_reason", sa.Text(), nullable=True, comment="冲突原因"),
            sa.Column("evidence_quote", sa.Text(), nullable=True, comment="引用片段"),
            sa.Column("created_time", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="创建时间"),
            sa.Column("updated_time", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="更新时间"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("review_key"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="客户智能事实人工复核审计表",
        )
        op.create_index("ix_crm_customer_fact_review_audits_review_key", "crm_customer_fact_review_audits", ["review_key"])
        op.create_index("ix_crm_customer_fact_review_audits_tenant_id", "crm_customer_fact_review_audits", ["tenant_id"])
        op.create_index("ix_crm_customer_fact_review_audits_team_id", "crm_customer_fact_review_audits", ["team_id"])
        op.create_index("ix_crm_customer_fact_review_audits_customer_id", "crm_customer_fact_review_audits", ["customer_id"])
        op.create_index("ix_crm_customer_fact_review_audits_event_key", "crm_customer_fact_review_audits", ["event_key"])
        op.create_index("ix_crm_customer_fact_review_audits_fact_id", "crm_customer_fact_review_audits", ["fact_id"])
        op.create_index("ix_crm_customer_fact_review_audits_existing_fact_id", "crm_customer_fact_review_audits", ["existing_fact_id"])
        op.create_index("ix_crm_customer_fact_review_audits_fact_type", "crm_customer_fact_review_audits", ["fact_type"])
        op.create_index("ix_crm_customer_fact_review_audits_decision", "crm_customer_fact_review_audits", ["decision"])
        op.create_index("ix_crm_customer_fact_review_audits_reviewer_id", "crm_customer_fact_review_audits", ["reviewer_id"])
        op.create_index("idx_customer_fact_review_customer", "crm_customer_fact_review_audits", ["team_id", "customer_id", "created_time"])
        op.create_index("idx_customer_fact_review_event", "crm_customer_fact_review_audits", ["team_id", "event_key"])


def downgrade() -> None:
    if _table_exists("crm_customer_fact_review_audits"):
        op.drop_table("crm_customer_fact_review_audits")
    if _table_exists("crm_customer_fact_revisions"):
        op.drop_table("crm_customer_fact_revisions")
    if _table_exists("crm_customer_fact_sources"):
        op.drop_table("crm_customer_fact_sources")
    if _table_exists("crm_customer_facts"):
        op.drop_table("crm_customer_facts")

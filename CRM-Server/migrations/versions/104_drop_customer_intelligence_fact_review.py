"""Remove the obsolete customer-intelligence fact review workflow.

Revision ID: 104_drop_ci_fact_review
Revises: 103_migrate_agent_entity_list_items
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "104_drop_ci_fact_review"
down_revision: str | None = "103_migrate_agent_entity_list_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN_TABLE = "crm_customer_intelligence_runs"
REVIEW_TABLE = "crm_agent_review_cases"
FACT_REVIEW_AUDIT_TABLE = "crm_customer_fact_review_audits"


def upgrade() -> None:
    # Review-required runs cannot be resumed after the non-blocking fact policy
    # becomes authoritative. Requeue them once so the graph restarts from its
    # durable event/checkpoint under the new single-path implementation.
    op.execute(
        sa.text(
            f"""UPDATE {RUN_TABLE}
                SET status = 'RETRY_PENDING',
                    next_retry_at = CURRENT_TIMESTAMP,
                    lease_token = NULL,
                    lease_expires_at = NULL,
                    finished_time = NULL,
                    error_message = NULL
                WHERE status = 'REVIEW_REQUIRED'"""
        )
    )
    op.drop_index("idx_customer_intelligence_run_review", table_name=RUN_TABLE)
    op.drop_index(
        "ix_crm_customer_intelligence_runs_review_case_public_id",
        table_name=RUN_TABLE,
    )
    op.drop_column(RUN_TABLE, "review_case_public_id")
    op.drop_table(REVIEW_TABLE)
    op.drop_table(FACT_REVIEW_AUDIT_TABLE)


def downgrade() -> None:
    op.create_table(
        FACT_REVIEW_AUDIT_TABLE,
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
        sa.Column(
            "candidate_confidence",
            sa.Float(),
            nullable=False,
            server_default="0",
            comment="候选事实置信度",
        ),
        sa.Column("decision", sa.String(length=20), nullable=False, comment="人工决策"),
        sa.Column("decision_source", sa.String(length=50), nullable=True, comment="决策来源"),
        sa.Column("reviewer_id", sa.BigInteger(), nullable=True, comment="复核人ID"),
        sa.Column("reason", sa.Text(), nullable=True, comment="复核原因"),
        sa.Column("conflict_reason", sa.Text(), nullable=True, comment="冲突原因"),
        sa.Column("evidence_quote", sa.Text(), nullable=True, comment="引用片段"),
        sa.Column(
            "created_time",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "updated_time",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
            comment="更新时间",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_key"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
        comment="客户智能事实人工复核审计表",
    )
    for index_name, columns in (
        ("ix_crm_customer_fact_review_audits_review_key", ["review_key"]),
        ("ix_crm_customer_fact_review_audits_tenant_id", ["tenant_id"]),
        ("ix_crm_customer_fact_review_audits_team_id", ["team_id"]),
        ("ix_crm_customer_fact_review_audits_customer_id", ["customer_id"]),
        ("ix_crm_customer_fact_review_audits_event_key", ["event_key"]),
        ("ix_crm_customer_fact_review_audits_fact_id", ["fact_id"]),
        ("ix_crm_customer_fact_review_audits_existing_fact_id", ["existing_fact_id"]),
        ("ix_crm_customer_fact_review_audits_fact_type", ["fact_type"]),
        ("ix_crm_customer_fact_review_audits_decision", ["decision"]),
        ("ix_crm_customer_fact_review_audits_reviewer_id", ["reviewer_id"]),
        ("idx_customer_fact_review_customer", ["team_id", "customer_id", "created_time"]),
        ("idx_customer_fact_review_event", ["team_id", "event_key"]),
    ):
        op.create_index(index_name, FACT_REVIEW_AUDIT_TABLE, columns)

    op.create_table(
        REVIEW_TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, comment="主键"),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="服务端签发的Review Case ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="交互归属用户ID"),
        sa.Column("session_id", sa.BigInteger(), nullable=False, comment="交互归属Agent会话ID"),
        sa.Column("customer_public_id", sa.String(length=64), nullable=False, comment="目标客户对外ID"),
        sa.Column("event_key", sa.String(length=160), nullable=False, comment="Customer Intelligence事件幂等键"),
        sa.Column("candidate_facts_json", sa.JSON(), nullable=False, comment="不可变候选事实"),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False, comment="不可变证据引用"),
        sa.Column("status", sa.String(length=20), nullable=False, comment="Review状态"),
        sa.Column("expires_at", sa.DateTime(), nullable=False, comment="Review提交截止时间"),
        sa.Column("decision_json", sa.JSON(), nullable=True, comment="Workflow验证后的用户决定"),
        sa.Column("decision_request_id", sa.String(length=36), nullable=True, comment="决定请求client_request_id"),
        sa.Column("resolved_by_user_id", sa.BigInteger(), nullable=True, comment="处理用户ID"),
        sa.Column("resolved_at", sa.DateTime(), nullable=True, comment="处理时间"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("last_modified_time", sa.DateTime(), nullable=False, comment="最后修改时间"),
        sa.ForeignKeyConstraint(["session_id"], ["crm_agent_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("team_id", "event_key", name="uq_agent_review_case_team_event"),
        comment="CRM Agent Customer Intelligence人工Review Case",
    )
    op.create_index(
        "idx_agent_review_case_owner_status_expiry",
        REVIEW_TABLE,
        ["team_id", "user_id", "session_id", "status", "expires_at"],
    )
    op.create_index("idx_agent_review_case_customer", REVIEW_TABLE, ["team_id", "customer_public_id"])
    op.create_index("idx_agent_review_case_decision_request", REVIEW_TABLE, ["decision_request_id"])
    op.create_index(op.f(f"ix_{REVIEW_TABLE}_public_id"), REVIEW_TABLE, ["public_id"], unique=True)

    op.add_column(
        RUN_TABLE,
        sa.Column("review_case_public_id", sa.String(length=64), nullable=True, comment="待处理客户事实复核Case对外ID"),
    )
    op.create_index(
        "ix_crm_customer_intelligence_runs_review_case_public_id",
        RUN_TABLE,
        ["review_case_public_id"],
    )
    op.create_index(
        "idx_customer_intelligence_run_review",
        RUN_TABLE,
        ["team_id", "review_case_public_id"],
    )

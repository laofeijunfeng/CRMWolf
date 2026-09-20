"""Add durable customer initial enrichment jobs.

Revision ID: 136_customer_initial_enrichment
Revises: 135_deal_journey_public_ids
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "136_customer_initial_enrichment"
down_revision: str | None = "135_deal_journey_public_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JOB_TABLE = "crm_customer_enrichment_jobs"
RUN_TABLE = "crm_customer_intelligence_runs"


def upgrade() -> None:
    op.create_table(
        JOB_TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="对外任务ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="客户ID"),
        sa.Column("purpose", sa.String(length=32), nullable=False, comment="登记用途"),
        sa.Column("plan_version", sa.String(length=64), nullable=False, comment="补全计划版本"),
        sa.Column("requested_fields_json", sa.JSON(), nullable=False, comment="请求补全字段"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="QUEUED", comment="任务状态"),
        sa.Column("available_at", sa.DateTime(), nullable=False, comment="最早可执行时间"),
        sa.Column("profile_gate_deadline_at", sa.DateTime(), nullable=True, comment="档案等待截止时间"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0", comment="执行次数"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3", comment="最大执行次数"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True, comment="下次恢复时间"),
        sa.Column("lease_token", sa.String(length=64), nullable=True, comment="当前执行租约令牌"),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True, comment="当前执行租约过期时间"),
        sa.Column("run_id", sa.String(length=100), nullable=False, comment="稳定运行ID"),
        sa.Column("graph_thread_id", sa.String(length=240), nullable=False, comment="LangGraph线程ID"),
        sa.Column("first_attempt_finished_at", sa.DateTime(), nullable=True, comment="首次执行结束时间"),
        sa.Column("profile_refresh_request_id", sa.String(length=120), nullable=True, comment="档案刷新请求ID"),
        sa.Column("profile_refresh_enqueued_at", sa.DateTime(), nullable=True, comment="档案刷新入队时间"),
        sa.Column("requeue_count", sa.Integer(), nullable=False, server_default="0", comment="人工重新入队次数"),
        sa.Column("result_json", sa.JSON(), nullable=True, comment="执行结果"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="最近错误"),
        sa.Column("started_at", sa.DateTime(), nullable=True, comment="首次开始时间"),
        sa.Column("finished_at", sa.DateTime(), nullable=True, comment="结束时间"),
        sa.Column(
            "created_time",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间",
        ),
        sa.Column(
            "updated_time",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="更新时间",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'RETRY_PENDING', 'COMPLETED', 'SKIPPED', 'EXHAUSTED')",
            name="ck_customer_enrichment_job_status",
        ),
        sa.CheckConstraint(
            "purpose IN ('INITIAL_CREATION', 'HISTORICAL_BACKFILL')",
            name="ck_customer_enrichment_job_purpose",
        ),
        sa.UniqueConstraint("team_id", "customer_id", "plan_version", name="uq_customer_enrichment_job_plan"),
        comment="客户首次信息补全持久任务表",
    )
    op.create_index("ix_crm_customer_enrichment_jobs_public_id", JOB_TABLE, ["public_id"], unique=True)
    op.create_index("ix_crm_customer_enrichment_jobs_team_id", JOB_TABLE, ["team_id"])
    op.create_index("ix_crm_customer_enrichment_jobs_customer_id", JOB_TABLE, ["customer_id"])
    op.create_index("ix_crm_customer_enrichment_jobs_purpose", JOB_TABLE, ["purpose"])
    op.create_index("ix_crm_customer_enrichment_jobs_status", JOB_TABLE, ["status"])
    op.create_index("ix_crm_customer_enrichment_jobs_available_at", JOB_TABLE, ["available_at"])
    op.create_index(
        "ix_crm_customer_enrichment_jobs_profile_gate_deadline_at",
        JOB_TABLE,
        ["profile_gate_deadline_at"],
    )
    op.create_index("ix_crm_customer_enrichment_jobs_next_attempt_at", JOB_TABLE, ["next_attempt_at"])
    op.create_index("ix_crm_customer_enrichment_jobs_lease_token", JOB_TABLE, ["lease_token"])
    op.create_index("ix_crm_customer_enrichment_jobs_lease_expires_at", JOB_TABLE, ["lease_expires_at"])
    op.create_index("ix_crm_customer_enrichment_jobs_run_id", JOB_TABLE, ["run_id"])
    op.create_index("ix_crm_customer_enrichment_jobs_graph_thread_id", JOB_TABLE, ["graph_thread_id"])
    op.create_index(
        "ix_crm_customer_enrichment_jobs_first_attempt_finished_at",
        JOB_TABLE,
        ["first_attempt_finished_at"],
    )
    op.create_index(
        "ix_crm_customer_enrichment_jobs_profile_refresh_request_id",
        JOB_TABLE,
        ["profile_refresh_request_id"],
    )
    op.create_index(
        "idx_customer_enrichment_job_recovery",
        JOB_TABLE,
        ["status", "available_at", "next_attempt_at", "lease_expires_at", "attempt_count", "created_time"],
    )
    op.create_index(
        "idx_customer_enrichment_job_customer_plan",
        JOB_TABLE,
        ["team_id", "customer_id", "plan_version"],
    )
    op.add_column(RUN_TABLE, sa.Column("not_before_at", sa.DateTime(), nullable=True))
    op.create_index("idx_customer_intelligence_run_not_before", RUN_TABLE, ["not_before_at"])


def downgrade() -> None:
    op.drop_index("idx_customer_intelligence_run_not_before", table_name=RUN_TABLE)
    op.drop_column(RUN_TABLE, "not_before_at")
    op.drop_table(JOB_TABLE)

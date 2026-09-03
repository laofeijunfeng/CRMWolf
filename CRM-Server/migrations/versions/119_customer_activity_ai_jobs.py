"""Add durable AI jobs for form-submitted customer activities.

Revision ID: 119_customer_activity_ai_jobs
Revises: 118_customer_activity_workflow_contracts
Create Date: 2026-09-02
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "119_customer_activity_ai_jobs"
down_revision: str | None = "118_customer_activity_workflow_contracts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "crm_customer_activity_ai_jobs"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="对外任务ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("activity_id", sa.BigInteger(), nullable=False, comment="客户活动ID快照"),
        sa.Column("activity_revision", sa.Integer(), nullable=False, comment="待最终化的活动修订号"),
        sa.Column(
            "job_type",
            sa.String(length=40),
            nullable=False,
            server_default="STRUCTURE_AND_EVALUATE",
            comment="任务类型",
        ),
        sa.Column("submission_source", sa.String(length=32), nullable=False, comment="活动提交来源"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="QUEUED", comment="任务状态"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0", comment="执行次数"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True, comment="下次恢复时间"),
        sa.Column("lease_token", sa.String(length=64), nullable=True, comment="当前执行租约令牌"),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True, comment="当前执行租约过期时间"),
        sa.Column("run_id", sa.String(length=100), nullable=False, comment="稳定运行ID"),
        sa.Column("graph_thread_id", sa.String(length=240), nullable=False, comment="LangGraph线程ID"),
        sa.Column("result_json", sa.JSON(), nullable=True, comment="最终结果摘要"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="最近错误"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.Column("started_at", sa.DateTime(), nullable=True, comment="首次开始时间"),
        sa.Column("finished_at", sa.DateTime(), nullable=True, comment="结束时间"),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'RETRY_PENDING', 'COMPLETED', 'SKIPPED', 'EXHAUSTED')",
            name="ck_customer_activity_ai_job_status",
        ),
        sa.CheckConstraint(
            "submission_source IN ('FORM', 'CUTOVER_MIGRATION')",
            name="ck_customer_activity_ai_job_submission_source",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint(
            "team_id",
            "activity_id",
            "activity_revision",
            "job_type",
            name="uq_customer_activity_ai_job_revision",
        ),
        comment="页面客户活动 AI 整理评分持久任务表",
    )
    op.create_index("idx_customer_activity_ai_jobs_public_id", TABLE, ["public_id"], unique=True)
    op.create_index("idx_customer_activity_ai_jobs_team_id", TABLE, ["team_id"])
    op.create_index("idx_customer_activity_ai_jobs_activity_id", TABLE, ["activity_id"])
    op.create_index("idx_customer_activity_ai_jobs_status", TABLE, ["status"])
    op.create_index("idx_customer_activity_ai_jobs_next_attempt_at", TABLE, ["next_attempt_at"])
    op.create_index("idx_customer_activity_ai_jobs_lease_token", TABLE, ["lease_token"])
    op.create_index("idx_customer_activity_ai_jobs_lease_expires_at", TABLE, ["lease_expires_at"])
    op.create_index("idx_customer_activity_ai_jobs_run_id", TABLE, ["run_id"])
    op.create_index("idx_customer_activity_ai_jobs_graph_thread_id", TABLE, ["graph_thread_id"])
    op.create_index(
        "idx_customer_activity_ai_job_recovery",
        TABLE,
        ["status", "next_attempt_at", "lease_expires_at", "attempt_count", "created_time"],
    )
    op.create_index(
        "idx_customer_activity_ai_job_activity",
        TABLE,
        ["team_id", "activity_id", "activity_revision"],
    )


def downgrade() -> None:
    op.drop_index("idx_customer_activity_ai_job_activity", table_name=TABLE)
    op.drop_index("idx_customer_activity_ai_job_recovery", table_name=TABLE)
    op.drop_index("idx_customer_activity_ai_jobs_graph_thread_id", table_name=TABLE)
    op.drop_index("idx_customer_activity_ai_jobs_run_id", table_name=TABLE)
    op.drop_index("idx_customer_activity_ai_jobs_lease_expires_at", table_name=TABLE)
    op.drop_index("idx_customer_activity_ai_jobs_lease_token", table_name=TABLE)
    op.drop_index("idx_customer_activity_ai_jobs_next_attempt_at", table_name=TABLE)
    op.drop_index("idx_customer_activity_ai_jobs_status", table_name=TABLE)
    op.drop_index("idx_customer_activity_ai_jobs_activity_id", table_name=TABLE)
    op.drop_index("idx_customer_activity_ai_jobs_team_id", table_name=TABLE)
    op.drop_index("idx_customer_activity_ai_jobs_public_id", table_name=TABLE)
    op.drop_table(TABLE)

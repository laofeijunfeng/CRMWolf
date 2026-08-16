"""add durable customer activity post commit jobs

Revision ID: 085_customer_activity_post_commit_jobs
Revises: 084_follow_up_confirmation_delivery_workflow
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "085_customer_activity_post_commit_jobs"
down_revision: str | None = "084_follow_up_confirmation_delivery_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVITY_TABLE = "crm_customer_activities"
JOB_TABLE = "crm_customer_activity_post_commit_jobs"


def upgrade() -> None:
    op.add_column(
        ACTIVITY_TABLE,
        sa.Column(
            "post_commit_revision",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="后提交工作流修订号",
        ),
    )
    op.create_table(
        JOB_TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="对外任务ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("activity_id", sa.BigInteger(), nullable=False, comment="客户活动ID"),
        sa.Column("activity_revision", sa.Integer(), nullable=False, comment="活动后处理修订号"),
        sa.Column("trigger_type", sa.String(length=80), nullable=False, comment="触发类型"),
        sa.Column("actor_id", sa.String(length=100), nullable=True, comment="触发用户ID"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="QUEUED", comment="执行状态"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0", comment="执行次数"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True, comment="下次恢复时间"),
        sa.Column("run_id", sa.String(length=100), nullable=False, comment="稳定LangGraph运行ID"),
        sa.Column("graph_thread_id", sa.String(length=240), nullable=False, comment="LangGraph线程ID"),
        sa.Column("result_json", sa.JSON(), nullable=True, comment="执行结果"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="最近错误"),
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
        sa.Column("started_at", sa.DateTime(), nullable=True, comment="首次开始时间"),
        sa.Column("finished_at", sa.DateTime(), nullable=True, comment="结束时间"),
        sa.ForeignKeyConstraint(["activity_id"], [f"{ACTIVITY_TABLE}.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "team_id",
            "activity_id",
            "trigger_type",
            "activity_revision",
            name="uq_customer_activity_post_commit_job_revision",
        ),
        comment="客户活动后提交持久任务表",
    )
    op.create_index(op.f("ix_crm_customer_activity_post_commit_jobs_public_id"), JOB_TABLE, ["public_id"], unique=True)
    op.create_index(op.f("ix_crm_customer_activity_post_commit_jobs_team_id"), JOB_TABLE, ["team_id"])
    op.create_index(op.f("ix_crm_customer_activity_post_commit_jobs_activity_id"), JOB_TABLE, ["activity_id"])
    op.create_index(op.f("ix_crm_customer_activity_post_commit_jobs_status"), JOB_TABLE, ["status"])
    op.create_index(op.f("ix_crm_customer_activity_post_commit_jobs_next_attempt_at"), JOB_TABLE, ["next_attempt_at"])
    op.create_index(op.f("ix_crm_customer_activity_post_commit_jobs_run_id"), JOB_TABLE, ["run_id"])
    op.create_index(op.f("ix_crm_customer_activity_post_commit_jobs_graph_thread_id"), JOB_TABLE, ["graph_thread_id"])
    op.create_index(
        "idx_customer_activity_post_commit_recovery",
        JOB_TABLE,
        ["status", "next_attempt_at", "attempt_count", "created_time"],
    )
    op.create_index(
        "idx_customer_activity_post_commit_activity",
        JOB_TABLE,
        ["team_id", "activity_id", "activity_revision"],
    )


def downgrade() -> None:
    op.drop_index("idx_customer_activity_post_commit_activity", table_name=JOB_TABLE)
    op.drop_index("idx_customer_activity_post_commit_recovery", table_name=JOB_TABLE)
    for index_name in (
        op.f("ix_crm_customer_activity_post_commit_jobs_graph_thread_id"),
        op.f("ix_crm_customer_activity_post_commit_jobs_run_id"),
        op.f("ix_crm_customer_activity_post_commit_jobs_next_attempt_at"),
        op.f("ix_crm_customer_activity_post_commit_jobs_status"),
        op.f("ix_crm_customer_activity_post_commit_jobs_activity_id"),
        op.f("ix_crm_customer_activity_post_commit_jobs_team_id"),
        op.f("ix_crm_customer_activity_post_commit_jobs_public_id"),
    ):
        op.drop_index(index_name, table_name=JOB_TABLE)
    op.drop_table(JOB_TABLE)
    op.drop_column(ACTIVITY_TABLE, "post_commit_revision")

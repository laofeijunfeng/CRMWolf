"""Add durable outbound notification jobs.

Revision ID: 130_outbound_notification_jobs
Revises: 129_command_execution_records
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "130_outbound_notification_jobs"
down_revision: str | None = "129_command_execution_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JOB_TABLE = "crm_outbound_notification_jobs"


def upgrade() -> None:
    op.create_table(
        JOB_TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="对外任务ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("event_type", sa.String(length=40), nullable=False, comment="通知事件类型"),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False, comment="幂等键"),
        sa.Column("approval_id", sa.BigInteger(), nullable=True, comment="审批实例ID"),
        sa.Column("node_id", sa.BigInteger(), nullable=True, comment="目标审批节点ID"),
        sa.Column("business_type", sa.String(length=40), nullable=False, comment="业务类型"),
        sa.Column("business_id", sa.BigInteger(), nullable=False, comment="业务单据ID"),
        sa.Column("actor_id", sa.String(length=100), nullable=True, comment="触发用户ID"),
        sa.Column("recipient_user_ids", sa.JSON(), nullable=False, comment="接收人用户ID列表"),
        sa.Column("payload_json", sa.JSON(), nullable=True, comment="通知意图附加数据"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="QUEUED", comment="执行状态"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0", comment="执行次数"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True, comment="下次恢复时间"),
        sa.Column("lease_token", sa.String(length=64), nullable=True, comment="当前执行租约令牌"),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True, comment="当前执行租约过期时间"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "idempotency_key", name="uq_outbound_notification_job_idempotency"),
        sa.CheckConstraint(
            "event_type IN ('approval_pending', 'approval_approved', 'approval_rejected', "
            "'approval_cancelled', 'approval_issued', 'approval_reminder', "
            "'account_created', 'account_status_won', 'account_status_lost', "
            "'customer_returned', 'lead_claimed', 'lead_assigned', "
            "'opportunity_won', 'opportunity_lost')",
            name="ck_outbound_notification_job_event_type",
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'FAILED', 'COMPLETED', 'SKIPPED', 'EXHAUSTED')",
            name="ck_outbound_notification_job_status",
        ),
        comment="出站通知持久任务表",
    )
    op.create_index(op.f("ix_crm_outbound_notification_jobs_public_id"), JOB_TABLE, ["public_id"], unique=True)
    op.create_index(op.f("ix_crm_outbound_notification_jobs_team_id"), JOB_TABLE, ["team_id"])
    op.create_index(op.f("ix_crm_outbound_notification_jobs_event_type"), JOB_TABLE, ["event_type"])
    op.create_index(op.f("ix_crm_outbound_notification_jobs_approval_id"), JOB_TABLE, ["approval_id"])
    op.create_index(op.f("ix_crm_outbound_notification_jobs_status"), JOB_TABLE, ["status"])
    op.create_index(op.f("ix_crm_outbound_notification_jobs_next_attempt_at"), JOB_TABLE, ["next_attempt_at"])
    op.create_index(op.f("ix_crm_outbound_notification_jobs_lease_token"), JOB_TABLE, ["lease_token"])
    op.create_index(op.f("ix_crm_outbound_notification_jobs_lease_expires_at"), JOB_TABLE, ["lease_expires_at"])
    op.create_index(
        "idx_outbound_notification_job_recovery",
        JOB_TABLE,
        ["status", "next_attempt_at", "lease_expires_at", "attempt_count", "created_time"],
    )


def downgrade() -> None:
    op.drop_index("idx_outbound_notification_job_recovery", table_name=JOB_TABLE)
    for index_name in (
        op.f("ix_crm_outbound_notification_jobs_lease_expires_at"),
        op.f("ix_crm_outbound_notification_jobs_lease_token"),
        op.f("ix_crm_outbound_notification_jobs_next_attempt_at"),
        op.f("ix_crm_outbound_notification_jobs_status"),
        op.f("ix_crm_outbound_notification_jobs_approval_id"),
        op.f("ix_crm_outbound_notification_jobs_event_type"),
        op.f("ix_crm_outbound_notification_jobs_team_id"),
        op.f("ix_crm_outbound_notification_jobs_public_id"),
    ):
        op.drop_index(index_name, table_name=JOB_TABLE)
    op.drop_table(JOB_TABLE)

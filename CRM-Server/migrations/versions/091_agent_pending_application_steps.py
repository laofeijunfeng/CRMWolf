"""Add durable PendingTask application-step ledger.

Revision ID: 091_agent_pending_application_steps
Revises: 090_agent_pending_interrupt_projections
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "091_agent_pending_application_steps"
down_revision: str | None = "090_agent_pending_interrupt_projections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "crm_agent_pending_application_steps"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="用户ID"),
        sa.Column("session_id", sa.BigInteger(), nullable=False, comment="Agent会话ID"),
        sa.Column("task_id", sa.BigInteger(), nullable=True, comment="待处理Agent任务ID"),
        sa.Column("step_id", sa.String(length=255), nullable=False, comment="稳定应用步骤幂等键"),
        sa.Column("step_type", sa.String(length=64), nullable=False, comment="应用步骤类型"),
        sa.Column("continuation_json", sa.JSON(), nullable=False, comment="PendingTask精确continuation"),
        sa.Column("request_json", sa.JSON(), nullable=False, comment="checkpoint-safe步骤请求"),
        sa.Column("status", sa.String(length=20), nullable=False, comment="执行状态"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0", comment="执行尝试次数"),
        sa.Column("lease_token", sa.String(length=64), nullable=True, comment="执行租约"),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True, comment="执行租约过期时间"),
        sa.Column("result_json", sa.JSON(), nullable=True, comment="稳定JSON执行结果"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="最近错误"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("last_modified_time", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.Column("completed_at", sa.DateTime(), nullable=True, comment="完成时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "user_id", "step_id", name="uq_agent_pending_application_step_id"),
        comment="Agent PendingTask内部应用步骤持久执行账本",
    )
    for column in (
        "team_id",
        "user_id",
        "session_id",
        "task_id",
        "step_type",
        "status",
        "lease_token",
        "lease_expires_at",
    ):
        op.create_index(op.f(f"ix_{TABLE}_{column}"), TABLE, [column])
    op.create_index(
        "idx_agent_pending_application_step_recovery",
        TABLE,
        ["status", "lease_expires_at", "attempt_count", "created_time"],
    )
    op.create_index(
        "idx_agent_pending_application_step_owner",
        TABLE,
        ["team_id", "user_id", "session_id", "created_time"],
    )


def downgrade() -> None:
    op.drop_table(TABLE)

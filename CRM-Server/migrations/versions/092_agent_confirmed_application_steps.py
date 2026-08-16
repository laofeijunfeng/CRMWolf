"""Add durable confirmed Agent application-step ledger.

Revision ID: 092_agent_confirmed_application_steps
Revises: 091_agent_pending_application_steps
Create Date: 2026-08-14
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "092_agent_confirmed_application_steps"
down_revision: str | None = "091_agent_pending_application_steps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "crm_agent_confirmed_application_steps"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="用户ID"),
        sa.Column("session_id", sa.BigInteger(), nullable=False, comment="Agent会话ID"),
        sa.Column("task_id", sa.BigInteger(), nullable=False, comment="已确认Agent任务ID"),
        sa.Column("step_id", sa.String(length=255), nullable=False, comment="稳定应用步骤幂等键"),
        sa.Column("step_type", sa.String(length=64), nullable=False, comment="应用步骤类型"),
        sa.Column("request_json", sa.JSON(), nullable=False, comment="checkpoint-safe执行意图"),
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
        sa.UniqueConstraint("team_id", "user_id", "step_id", name="uq_agent_confirmed_application_step_id"),
        comment="Agent已确认写操作应用投影执行账本",
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
        "idx_agent_confirmed_application_step_recovery",
        TABLE,
        ["status", "lease_expires_at", "attempt_count", "created_time"],
    )
    op.create_index(
        "idx_agent_confirmed_application_step_owner",
        TABLE,
        ["team_id", "user_id", "session_id", "task_id", "created_time"],
    )


def downgrade() -> None:
    op.drop_table(TABLE)

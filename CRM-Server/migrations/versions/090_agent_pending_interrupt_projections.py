"""add durable PendingTask interrupt projection ledger

Revision ID: 090_agent_pending_interrupt_projections
Revises: 089_customer_intelligence_run_leases
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "090_agent_pending_interrupt_projections"
down_revision: str | None = "089_customer_intelligence_run_leases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "crm_agent_pending_interrupt_projections"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="用户ID"),
        sa.Column("session_id", sa.BigInteger(), nullable=False, comment="Agent会话ID"),
        sa.Column("task_id", sa.BigInteger(), nullable=True, comment="待处理Agent任务ID"),
        sa.Column("projection_key", sa.String(length=255), nullable=False, comment="中断投影幂等键"),
        sa.Column("continuation_json", sa.JSON(), nullable=False, comment="PendingTask精确continuation"),
        sa.Column("interrupt_json", sa.JSON(), nullable=False, comment="原生interrupt载荷"),
        sa.Column("status", sa.String(length=20), nullable=False, comment="业务投影状态"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0", comment="业务投影尝试次数"),
        sa.Column("lease_token", sa.String(length=64), nullable=True, comment="业务投影租约"),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True, comment="业务投影租约过期时间"),
        sa.Column("result_json", sa.JSON(), nullable=True, comment="权威投影结果及稳定事件"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="业务投影最近错误"),
        sa.Column("delivery_status", sa.String(length=20), nullable=False, comment="事件投递状态"),
        sa.Column(
            "delivery_attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="事件投递尝试次数",
        ),
        sa.Column("delivery_lease_token", sa.String(length=64), nullable=True, comment="事件投递租约"),
        sa.Column("delivery_lease_expires_at", sa.DateTime(), nullable=True, comment="事件投递租约过期时间"),
        sa.Column("delivery_reason_code", sa.String(length=80), nullable=True, comment="事件投递结果原因码"),
        sa.Column("delivery_error_message", sa.Text(), nullable=True, comment="事件投递最近错误"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("last_modified_time", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.Column("projected_at", sa.DateTime(), nullable=True, comment="业务投影完成时间"),
        sa.Column("delivered_at", sa.DateTime(), nullable=True, comment="事件投递完成时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "user_id", "projection_key", name="uq_agent_pending_interrupt_projection_key"),
        comment="Agent PendingTask原生中断持久投影与事件投递表",
    )
    for column in (
        "team_id",
        "user_id",
        "session_id",
        "task_id",
        "status",
        "lease_token",
        "lease_expires_at",
        "delivery_status",
        "delivery_lease_token",
        "delivery_lease_expires_at",
    ):
        op.create_index(op.f(f"ix_{TABLE}_{column}"), TABLE, [column])
    op.create_index(
        "idx_agent_pending_interrupt_projection_recovery",
        TABLE,
        ["status", "lease_expires_at", "attempt_count", "created_time"],
    )
    op.create_index(
        "idx_agent_pending_interrupt_delivery_recovery",
        TABLE,
        ["delivery_status", "delivery_lease_expires_at", "delivery_attempt_count", "created_time"],
    )
    op.create_index(
        "idx_agent_pending_interrupt_owner",
        TABLE,
        ["team_id", "user_id", "session_id", "created_time"],
    )


def downgrade() -> None:
    op.drop_table(TABLE)

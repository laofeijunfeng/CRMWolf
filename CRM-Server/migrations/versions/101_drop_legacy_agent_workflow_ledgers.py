"""Drop ledgers owned by the removed legacy Pending/Confirmed runtimes.

Revision ID: 101_drop_legacy_agent_workflow_ledgers
Revises: 100_agent_checkpoint_migration_journal
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "101_drop_legacy_agent_workflow_ledgers"
down_revision: str | None = "100_agent_checkpoint_migration_journal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PENDING_INTERRUPT_TABLE = "crm_agent_pending_interrupt_projections"
PENDING_STEP_TABLE = "crm_agent_pending_application_steps"
CONFIRMED_STEP_TABLE = "crm_agent_confirmed_application_steps"


def upgrade() -> None:
    op.drop_table(CONFIRMED_STEP_TABLE)
    op.drop_table(PENDING_STEP_TABLE)
    op.drop_table(PENDING_INTERRUPT_TABLE)


def downgrade() -> None:
    _create_pending_interrupt_table()
    _create_pending_step_table()
    _create_confirmed_step_table()


def _create_pending_interrupt_table() -> None:
    op.create_table(
        PENDING_INTERRUPT_TABLE,
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
        sa.UniqueConstraint(
            "team_id",
            "user_id",
            "projection_key",
            name="uq_agent_pending_interrupt_projection_key",
        ),
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
        op.create_index(op.f(f"ix_{PENDING_INTERRUPT_TABLE}_{column}"), PENDING_INTERRUPT_TABLE, [column])
    op.create_index(
        "idx_agent_pending_interrupt_projection_recovery",
        PENDING_INTERRUPT_TABLE,
        ["status", "lease_expires_at", "attempt_count", "created_time"],
    )
    op.create_index(
        "idx_agent_pending_interrupt_delivery_recovery",
        PENDING_INTERRUPT_TABLE,
        ["delivery_status", "delivery_lease_expires_at", "delivery_attempt_count", "created_time"],
    )
    op.create_index(
        "idx_agent_pending_interrupt_owner",
        PENDING_INTERRUPT_TABLE,
        ["team_id", "user_id", "session_id", "created_time"],
    )


def _create_pending_step_table() -> None:
    op.create_table(
        PENDING_STEP_TABLE,
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
    _create_step_indexes(PENDING_STEP_TABLE, owner_columns=["team_id", "user_id", "session_id", "created_time"])


def _create_confirmed_step_table() -> None:
    op.create_table(
        CONFIRMED_STEP_TABLE,
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
        sa.UniqueConstraint("team_id", "user_id", "task_id", name="uq_agent_confirmed_application_task"),
        comment="Agent已确认写操作应用投影执行账本",
    )
    _create_step_indexes(
        CONFIRMED_STEP_TABLE,
        owner_columns=["team_id", "user_id", "session_id", "task_id", "created_time"],
    )


def _create_step_indexes(table: str, *, owner_columns: list[str]) -> None:
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
        op.create_index(op.f(f"ix_{table}_{column}"), table, [column])
    kind = "confirmed" if table == CONFIRMED_STEP_TABLE else "pending"
    op.create_index(
        f"idx_agent_{kind}_application_step_recovery",
        table,
        ["status", "lease_expires_at", "attempt_count", "created_time"],
    )
    op.create_index(f"idx_agent_{kind}_application_step_owner", table, owner_columns)

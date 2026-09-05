"""Add durable execution records for non-Agent user commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "129_command_execution_records"
down_revision: str | None = "128_agent_ui_action_submitted_values"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_command_executions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("operation_id", sa.String(length=64), nullable=False, comment="对外操作ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("actor_id", sa.String(length=100), nullable=False, comment="操作人ID"),
        sa.Column("command_type", sa.String(length=80), nullable=False, comment="命令类型"),
        sa.Column("resource_type", sa.String(length=40), nullable=True, comment="资源类型"),
        sa.Column("resource_public_id", sa.String(length=128), nullable=True, comment="资源对外ID"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True, comment="客户端幂等键"),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True, comment="请求指纹"),
        sa.Column("status", sa.String(length=20), nullable=False, comment="执行状态"),
        sa.Column("result_json", sa.JSON(), nullable=True, comment="脱敏结果摘要"),
        sa.Column("error_code", sa.String(length=80), nullable=True, comment="稳定错误码"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="面向用户的错误摘要"),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false(), comment="是否允许重试"),
        sa.Column("correlation_id", sa.String(length=128), nullable=True, comment="链路追踪ID"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.Column("completed_time", sa.DateTime(), nullable=True, comment="完成时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_id"),
        sa.UniqueConstraint("team_id", "idempotency_key", name="uq_command_execution_team_idempotency"),
        comment="非 Agent 用户命令执行记录",
    )
    op.create_index("ix_crm_command_executions_operation_id", "crm_command_executions", ["operation_id"], unique=False)
    op.create_index("ix_crm_command_executions_team_id", "crm_command_executions", ["team_id"], unique=False)
    op.create_index("ix_crm_command_executions_status", "crm_command_executions", ["status"], unique=False)
    op.create_index(
        "idx_command_execution_team_status_created",
        "crm_command_executions",
        ["team_id", "status", "created_time"],
        unique=False,
    )
    op.create_index(
        "idx_command_execution_resource",
        "crm_command_executions",
        ["team_id", "resource_type", "resource_public_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_command_execution_resource", table_name="crm_command_executions")
    op.drop_index("idx_command_execution_team_status_created", table_name="crm_command_executions")
    op.drop_index("ix_crm_command_executions_status", table_name="crm_command_executions")
    op.drop_index("ix_crm_command_executions_team_id", table_name="crm_command_executions")
    op.drop_index("ix_crm_command_executions_operation_id", table_name="crm_command_executions")
    op.drop_table("crm_command_executions")

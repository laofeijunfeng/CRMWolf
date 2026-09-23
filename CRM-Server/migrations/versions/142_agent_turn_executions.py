"""Add durable CRM Agent turn execution ledger.

Revision ID: 142_agent_turn_executions
Revises: 141_reminder_rule_revision
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "142_agent_turn_executions"
down_revision: str | None = "141_reminder_rule_revision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_agent_turn_executions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="执行记录对外ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="用户ID"),
        sa.Column("session_id", sa.BigInteger(), nullable=False, comment="Agent会话ID"),
        sa.Column("turn_id", sa.String(length=64), nullable=False, comment="Agent轮次ID"),
        sa.Column("client_request_id", sa.String(length=36), nullable=False, comment="客户端请求UUID"),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False, comment="规范化输入SHA-256"),
        sa.Column("request_input_json", sa.JSON(), nullable=False, comment="冻结的类型化输入"),
        sa.Column("root_input_json", sa.JSON(), nullable=False, comment="冻结的Root输入"),
        sa.Column("permission_codes_json", sa.JSON(), nullable=False, comment="受理时权限代码快照"),
        sa.Column("channel_context_json", sa.JSON(), nullable=False, comment="可信渠道上下文"),
        sa.Column("selected_entity_ref_json", sa.JSON(), nullable=True, comment="受理时服务端解析的实体引用"),
        sa.Column("message_display", sa.String(length=20), nullable=False, comment="用户消息展示类型"),
        sa.Column("entity_action_claim_id", sa.String(length=128), nullable=True, comment="实体动作消费ID"),
        sa.Column("status", sa.String(length=32), nullable=False, comment="执行状态"),
        sa.Column("lease_version", sa.Integer(), nullable=False, server_default="0", comment="租约栅栏版本"),
        sa.Column("lease_owner", sa.String(length=64), nullable=True, comment="当前租约持有者"),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True, comment="当前租约到期时间"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0", comment="执行尝试次数"),
        sa.Column("result_message_id", sa.BigInteger(), nullable=True, comment="权威助手结果消息ID"),
        sa.Column("committed_resources_json", sa.JSON(), nullable=False, comment="已确认提交的业务资源"),
        sa.Column("completed_command_ids_json", sa.JSON(), nullable=False, comment="已确认完成的业务命令ID"),
        sa.Column("failed_command_id", sa.String(length=128), nullable=True, comment="失败的业务命令ID"),
        sa.Column("last_error_code", sa.String(length=128), nullable=True, comment="最近错误代码"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("last_modified_time", sa.DateTime(), nullable=False, comment="最后修改时间"),
        sa.ForeignKeyConstraint(["session_id"], ["crm_agent_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["result_message_id"], ["crm_agent_messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("team_id", "user_id", "client_request_id", name="uq_agent_turn_execution_owner_request"),
        comment="CRM Agent持久执行与请求恢复账本",
    )
    op.create_index("idx_agent_turn_execution_session_request", "crm_agent_turn_executions", ["session_id", "client_request_id"])
    op.create_index("idx_agent_turn_execution_recovery", "crm_agent_turn_executions", ["status", "lease_expires_at", "id"])


def downgrade() -> None:
    op.drop_index("idx_agent_turn_execution_recovery", table_name="crm_agent_turn_executions")
    op.drop_index("idx_agent_turn_execution_session_request", table_name="crm_agent_turn_executions")
    op.drop_table("crm_agent_turn_executions")

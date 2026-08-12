"""add durable agent async operation projections

Revision ID: 082_agent_async_operations
Revises: 081_follow_up_confirmation_delivery_lifecycle
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "082_agent_async_operations"
down_revision: str | None = "081_follow_up_confirmation_delivery_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_agent_async_operations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="对外操作ID"),
        sa.Column("operation_key", sa.String(length=200), nullable=False, comment="操作幂等键"),
        sa.Column("request_id", sa.String(length=120), nullable=False, comment="后台请求ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="用户ID"),
        sa.Column("session_id", sa.BigInteger(), nullable=True, comment="来源 Agent 会话ID"),
        sa.Column("source_user_message_id", sa.BigInteger(), nullable=True, comment="来源用户消息ID"),
        sa.Column("source_assistant_message_id", sa.BigInteger(), nullable=True, comment="来源助手消息ID"),
        sa.Column("operation_type", sa.String(length=80), nullable=False, comment="异步操作类型"),
        sa.Column("resource_type", sa.String(length=50), nullable=False, comment="业务资源类型"),
        sa.Column("resource_id", sa.BigInteger(), nullable=True, comment="内部业务资源ID"),
        sa.Column("resource_public_id", sa.String(length=80), nullable=True, comment="对外业务资源ID"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="QUEUED", comment="状态"),
        sa.Column("summary", sa.Text(), nullable=True, comment="用户可见摘要"),
        sa.Column("current_step", sa.String(length=120), nullable=True, comment="当前步骤"),
        sa.Column("graph_thread_id", sa.String(length=240), nullable=True, comment="LangGraph thread ID"),
        sa.Column("result_json", sa.JSON(), nullable=True, comment="可回放结果摘要"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
        sa.Column("started_time", sa.DateTime(), nullable=True, comment="开始时间"),
        sa.Column("finished_time", sa.DateTime(), nullable=True, comment="结束时间"),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True, comment="下次重试时间"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.ForeignKeyConstraint(["session_id"], ["crm_agent_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_key", name="uq_agent_async_operation_key"),
        comment="Agent 异步操作用户可见投影表",
    )
    for name, columns, unique in (
        ("ix_crm_agent_async_operations_public_id", ["public_id"], True),
        ("ix_crm_agent_async_operations_operation_key", ["operation_key"], True),
        ("ix_crm_agent_async_operations_request_id", ["request_id"], False),
        ("ix_crm_agent_async_operations_team_id", ["team_id"], False),
        ("ix_crm_agent_async_operations_user_id", ["user_id"], False),
        ("ix_crm_agent_async_operations_session_id", ["session_id"], False),
        ("ix_crm_agent_async_operations_status", ["status"], False),
        ("idx_agent_async_operation_owner_session", ["team_id", "user_id", "session_id", "created_time"], False),
        ("idx_agent_async_operation_owner_status", ["team_id", "user_id", "status", "updated_time"], False),
        ("idx_agent_async_operation_resource", ["team_id", "resource_type", "resource_id"], False),
    ):
        op.create_index(name, "crm_agent_async_operations", columns, unique=unique)

    op.create_table(
        "crm_agent_async_operation_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("operation_id", sa.BigInteger(), nullable=False, comment="异步操作ID"),
        sa.Column("event_key", sa.String(length=200), nullable=False, comment="操作内事件幂等键"),
        sa.Column("sequence", sa.Integer(), nullable=False, comment="操作内递增序号"),
        sa.Column("event_type", sa.String(length=30), nullable=False, comment="事件类型"),
        sa.Column("status", sa.String(length=30), nullable=False, comment="事件后的操作状态"),
        sa.Column("step", sa.String(length=120), nullable=True, comment="步骤标识"),
        sa.Column("message", sa.Text(), nullable=True, comment="用户可见进度说明"),
        sa.Column("payload_json", sa.JSON(), nullable=True, comment="结构化事件载荷"),
        sa.Column("occurred_at", sa.DateTime(), nullable=False, comment="业务发生时间"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.ForeignKeyConstraint(["operation_id"], ["crm_agent_async_operations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_id", "event_key", name="uq_agent_async_operation_event_key"),
        sa.UniqueConstraint("operation_id", "sequence", name="uq_agent_async_operation_event_sequence"),
        comment="Agent 异步操作追加事件表",
    )
    for name, columns in (
        ("ix_crm_agent_async_operation_events_operation_id", ["operation_id"]),
        ("ix_crm_agent_async_operation_events_event_type", ["event_type"]),
        ("ix_crm_agent_async_operation_events_status", ["status"]),
        ("ix_crm_agent_async_operation_events_occurred_at", ["occurred_at"]),
        ("idx_agent_async_operation_event_replay", ["operation_id", "sequence"]),
    ):
        op.create_index(name, "crm_agent_async_operation_events", columns)


def downgrade() -> None:
    op.drop_table("crm_agent_async_operation_events")
    op.drop_table("crm_agent_async_operations")

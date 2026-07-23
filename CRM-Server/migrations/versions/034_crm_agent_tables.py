"""crm agent tables

Revision ID: 034_crm_agent_tables
Revises: 033_payment_record_commission_member
Create Date: 2026-07-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "034_crm_agent_tables"
down_revision: Union[str, None] = "033_payment_record_commission_member"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE()
        AND table_name = :table_name
    """), {"table_name": table_name}).scalar() > 0


def _index_exists(table_name: str, index_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.statistics
        WHERE table_schema = DATABASE()
        AND table_name = :table_name
        AND index_name = :index_name
    """), {"table_name": table_name, "index_name": index_name}).scalar() > 0


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str], unique: bool = False) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _index_exists(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not _table_exists("crm_agent_sessions"):
        op.create_table(
            "crm_agent_sessions",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("session_key", sa.String(length=64), nullable=False, comment="Agent会话唯一标识"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("user_id", sa.BigInteger(), nullable=False, comment="系统用户ID"),
            sa.Column("title", sa.String(length=200), nullable=True, comment="会话标题"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE", comment="会话状态"),
            sa.Column("summary", sa.Text(), nullable=True, comment="会话摘要"),
            sa.Column("context_json", sa.JSON(), nullable=True, comment="会话上下文快照"),
            sa.Column(
                "created_time",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
                comment="创建时间",
            ),
            sa.Column(
                "last_modified_time",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
                comment="最后修改时间",
            ),
            sa.PrimaryKeyConstraint("id"),
            comment="CRM AI Agent会话表",
        )
    _create_index_if_missing("ix_crm_agent_sessions_session_key", "crm_agent_sessions", ["session_key"], unique=True)
    _create_index_if_missing("ix_crm_agent_sessions_team_id", "crm_agent_sessions", ["team_id"])
    _create_index_if_missing("ix_crm_agent_sessions_user_id", "crm_agent_sessions", ["user_id"])
    _create_index_if_missing("ix_crm_agent_sessions_status", "crm_agent_sessions", ["status"])
    _create_index_if_missing(
        "idx_agent_session_team_user_status",
        "crm_agent_sessions",
        ["team_id", "user_id", "status"],
    )
    _create_index_if_missing("idx_agent_session_created_time", "crm_agent_sessions", ["created_time"])

    if not _table_exists("crm_agent_messages"):
        op.create_table(
            "crm_agent_messages",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("user_id", sa.BigInteger(), nullable=False, comment="系统用户ID"),
            sa.Column("session_id", sa.BigInteger(), nullable=False, comment="Agent会话ID"),
            sa.Column("role", sa.String(length=20), nullable=False, comment="消息角色"),
            sa.Column("event_type", sa.String(length=50), nullable=True, comment="SSE或业务事件类型"),
            sa.Column("content", sa.Text(), nullable=True, comment="消息正文"),
            sa.Column("payload_json", sa.JSON(), nullable=True, comment="结构化消息载荷"),
            sa.Column(
                "created_time",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
                comment="创建时间",
            ),
            sa.ForeignKeyConstraint(["session_id"], ["crm_agent_sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            comment="CRM AI Agent消息表",
        )
    _create_index_if_missing("ix_crm_agent_messages_team_id", "crm_agent_messages", ["team_id"])
    _create_index_if_missing("ix_crm_agent_messages_user_id", "crm_agent_messages", ["user_id"])
    _create_index_if_missing("ix_crm_agent_messages_session_id", "crm_agent_messages", ["session_id"])
    _create_index_if_missing("ix_crm_agent_messages_event_type", "crm_agent_messages", ["event_type"])
    _create_index_if_missing("ix_crm_agent_messages_created_time", "crm_agent_messages", ["created_time"])
    _create_index_if_missing("idx_agent_message_session_created", "crm_agent_messages", ["session_id", "created_time"])
    _create_index_if_missing(
        "idx_agent_message_team_user_created",
        "crm_agent_messages",
        ["team_id", "user_id", "created_time"],
    )

    if not _table_exists("crm_agent_tasks"):
        op.create_table(
            "crm_agent_tasks",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("task_key", sa.String(length=64), nullable=False, comment="Agent任务唯一标识"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("user_id", sa.BigInteger(), nullable=False, comment="系统用户ID"),
            sa.Column("session_id", sa.BigInteger(), nullable=False, comment="Agent会话ID"),
            sa.Column("intent", sa.String(length=80), nullable=True, comment="识别出的意图"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING", comment="任务状态"),
            sa.Column("target_type", sa.String(length=50), nullable=True, comment="目标业务对象类型"),
            sa.Column("target_id", sa.BigInteger(), nullable=True, comment="目标业务对象ID"),
            sa.Column("summary", sa.Text(), nullable=True, comment="任务摘要"),
            sa.Column("input_json", sa.JSON(), nullable=True, comment="用户输入解析快照"),
            sa.Column("state_json", sa.JSON(), nullable=True, comment="LangGraph状态快照"),
            sa.Column("result_json", sa.JSON(), nullable=True, comment="任务结果快照"),
            sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
            sa.Column(
                "created_time",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
                comment="创建时间",
            ),
            sa.Column(
                "last_modified_time",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
                comment="最后修改时间",
            ),
            sa.ForeignKeyConstraint(["session_id"], ["crm_agent_sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            comment="CRM AI Agent任务表",
        )
    _create_index_if_missing("ix_crm_agent_tasks_task_key", "crm_agent_tasks", ["task_key"], unique=True)
    _create_index_if_missing("ix_crm_agent_tasks_team_id", "crm_agent_tasks", ["team_id"])
    _create_index_if_missing("ix_crm_agent_tasks_user_id", "crm_agent_tasks", ["user_id"])
    _create_index_if_missing("ix_crm_agent_tasks_session_id", "crm_agent_tasks", ["session_id"])
    _create_index_if_missing("ix_crm_agent_tasks_intent", "crm_agent_tasks", ["intent"])
    _create_index_if_missing("ix_crm_agent_tasks_status", "crm_agent_tasks", ["status"])
    _create_index_if_missing("ix_crm_agent_tasks_target_type", "crm_agent_tasks", ["target_type"])
    _create_index_if_missing("ix_crm_agent_tasks_target_id", "crm_agent_tasks", ["target_id"])
    _create_index_if_missing("ix_crm_agent_tasks_created_time", "crm_agent_tasks", ["created_time"])
    _create_index_if_missing("idx_agent_task_session_status", "crm_agent_tasks", ["session_id", "status"])
    _create_index_if_missing("idx_agent_task_team_user_status", "crm_agent_tasks", ["team_id", "user_id", "status"])

    if not _table_exists("crm_agent_tool_calls"):
        op.create_table(
            "crm_agent_tool_calls",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("call_key", sa.String(length=64), nullable=False, comment="Tool调用唯一标识"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("user_id", sa.BigInteger(), nullable=False, comment="系统用户ID"),
            sa.Column("session_id", sa.BigInteger(), nullable=False, comment="Agent会话ID"),
            sa.Column("task_id", sa.BigInteger(), nullable=True, comment="Agent任务ID"),
            sa.Column("tool_name", sa.String(length=100), nullable=False, comment="Tool名称"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING", comment="调用状态"),
            sa.Column("request_json", sa.JSON(), nullable=True, comment="Tool请求参数快照"),
            sa.Column("response_json", sa.JSON(), nullable=True, comment="Tool响应结果快照"),
            sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
            sa.Column("started_time", sa.DateTime(), nullable=True, comment="开始时间"),
            sa.Column("finished_time", sa.DateTime(), nullable=True, comment="结束时间"),
            sa.Column(
                "created_time",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
                comment="创建时间",
            ),
            sa.Column(
                "last_modified_time",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
                comment="最后修改时间",
            ),
            sa.ForeignKeyConstraint(["session_id"], ["crm_agent_sessions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["task_id"], ["crm_agent_tasks.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            comment="CRM AI Agent Tool调用审计表",
        )
    _create_index_if_missing("ix_crm_agent_tool_calls_call_key", "crm_agent_tool_calls", ["call_key"], unique=True)
    _create_index_if_missing("ix_crm_agent_tool_calls_team_id", "crm_agent_tool_calls", ["team_id"])
    _create_index_if_missing("ix_crm_agent_tool_calls_user_id", "crm_agent_tool_calls", ["user_id"])
    _create_index_if_missing("ix_crm_agent_tool_calls_session_id", "crm_agent_tool_calls", ["session_id"])
    _create_index_if_missing("ix_crm_agent_tool_calls_task_id", "crm_agent_tool_calls", ["task_id"])
    _create_index_if_missing("ix_crm_agent_tool_calls_tool_name", "crm_agent_tool_calls", ["tool_name"])
    _create_index_if_missing("ix_crm_agent_tool_calls_status", "crm_agent_tool_calls", ["status"])
    _create_index_if_missing("ix_crm_agent_tool_calls_created_time", "crm_agent_tool_calls", ["created_time"])
    _create_index_if_missing(
        "idx_agent_tool_call_session_created",
        "crm_agent_tool_calls",
        ["session_id", "created_time"],
    )
    _create_index_if_missing("idx_agent_tool_call_task_status", "crm_agent_tool_calls", ["task_id", "status"])
    _create_index_if_missing(
        "idx_agent_tool_call_team_user_tool",
        "crm_agent_tool_calls",
        ["team_id", "user_id", "tool_name"],
    )

    if not _table_exists("crm_agent_idempotency_keys"):
        op.create_table(
            "crm_agent_idempotency_keys",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("user_id", sa.BigInteger(), nullable=False, comment="系统用户ID"),
            sa.Column("session_id", sa.BigInteger(), nullable=True, comment="Agent会话ID"),
            sa.Column("task_id", sa.BigInteger(), nullable=True, comment="Agent任务ID"),
            sa.Column("action_key", sa.String(length=160), nullable=False, comment="幂等动作键"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING", comment="幂等状态"),
            sa.Column("request_hash", sa.String(length=64), nullable=True, comment="请求内容Hash"),
            sa.Column("result_json", sa.JSON(), nullable=True, comment="执行结果快照"),
            sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
            sa.Column(
                "created_time",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
                comment="创建时间",
            ),
            sa.Column(
                "last_modified_time",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
                comment="最后修改时间",
            ),
            sa.ForeignKeyConstraint(["session_id"], ["crm_agent_sessions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["task_id"], ["crm_agent_tasks.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("team_id", "user_id", "action_key", name="uk_agent_idempotency_team_user_action"),
            comment="CRM AI Agent幂等键表",
        )
    _create_index_if_missing("ix_crm_agent_idempotency_keys_team_id", "crm_agent_idempotency_keys", ["team_id"])
    _create_index_if_missing("ix_crm_agent_idempotency_keys_user_id", "crm_agent_idempotency_keys", ["user_id"])
    _create_index_if_missing("ix_crm_agent_idempotency_keys_session_id", "crm_agent_idempotency_keys", ["session_id"])
    _create_index_if_missing("ix_crm_agent_idempotency_keys_task_id", "crm_agent_idempotency_keys", ["task_id"])
    _create_index_if_missing("ix_crm_agent_idempotency_keys_status", "crm_agent_idempotency_keys", ["status"])
    _create_index_if_missing(
        "ix_crm_agent_idempotency_keys_created_time",
        "crm_agent_idempotency_keys",
        ["created_time"],
    )
    _create_index_if_missing(
        "idx_agent_idempotency_session_task",
        "crm_agent_idempotency_keys",
        ["session_id", "task_id"],
    )
    _create_index_if_missing(
        "idx_agent_idempotency_team_user_status",
        "crm_agent_idempotency_keys",
        ["team_id", "user_id", "status"],
    )


def downgrade() -> None:
    if _table_exists("crm_agent_idempotency_keys"):
        _drop_index_if_exists("idx_agent_idempotency_team_user_status", "crm_agent_idempotency_keys")
        _drop_index_if_exists("idx_agent_idempotency_session_task", "crm_agent_idempotency_keys")
        _drop_index_if_exists("ix_crm_agent_idempotency_keys_created_time", "crm_agent_idempotency_keys")
        _drop_index_if_exists("ix_crm_agent_idempotency_keys_status", "crm_agent_idempotency_keys")
        _drop_index_if_exists("ix_crm_agent_idempotency_keys_task_id", "crm_agent_idempotency_keys")
        _drop_index_if_exists("ix_crm_agent_idempotency_keys_session_id", "crm_agent_idempotency_keys")
        _drop_index_if_exists("ix_crm_agent_idempotency_keys_user_id", "crm_agent_idempotency_keys")
        _drop_index_if_exists("ix_crm_agent_idempotency_keys_team_id", "crm_agent_idempotency_keys")
        op.drop_table("crm_agent_idempotency_keys")

    if _table_exists("crm_agent_tool_calls"):
        _drop_index_if_exists("idx_agent_tool_call_team_user_tool", "crm_agent_tool_calls")
        _drop_index_if_exists("idx_agent_tool_call_task_status", "crm_agent_tool_calls")
        _drop_index_if_exists("idx_agent_tool_call_session_created", "crm_agent_tool_calls")
        _drop_index_if_exists("ix_crm_agent_tool_calls_created_time", "crm_agent_tool_calls")
        _drop_index_if_exists("ix_crm_agent_tool_calls_status", "crm_agent_tool_calls")
        _drop_index_if_exists("ix_crm_agent_tool_calls_tool_name", "crm_agent_tool_calls")
        _drop_index_if_exists("ix_crm_agent_tool_calls_task_id", "crm_agent_tool_calls")
        _drop_index_if_exists("ix_crm_agent_tool_calls_session_id", "crm_agent_tool_calls")
        _drop_index_if_exists("ix_crm_agent_tool_calls_user_id", "crm_agent_tool_calls")
        _drop_index_if_exists("ix_crm_agent_tool_calls_team_id", "crm_agent_tool_calls")
        _drop_index_if_exists("ix_crm_agent_tool_calls_call_key", "crm_agent_tool_calls")
        op.drop_table("crm_agent_tool_calls")

    if _table_exists("crm_agent_tasks"):
        _drop_index_if_exists("idx_agent_task_team_user_status", "crm_agent_tasks")
        _drop_index_if_exists("idx_agent_task_session_status", "crm_agent_tasks")
        _drop_index_if_exists("ix_crm_agent_tasks_created_time", "crm_agent_tasks")
        _drop_index_if_exists("ix_crm_agent_tasks_target_id", "crm_agent_tasks")
        _drop_index_if_exists("ix_crm_agent_tasks_target_type", "crm_agent_tasks")
        _drop_index_if_exists("ix_crm_agent_tasks_status", "crm_agent_tasks")
        _drop_index_if_exists("ix_crm_agent_tasks_intent", "crm_agent_tasks")
        _drop_index_if_exists("ix_crm_agent_tasks_session_id", "crm_agent_tasks")
        _drop_index_if_exists("ix_crm_agent_tasks_user_id", "crm_agent_tasks")
        _drop_index_if_exists("ix_crm_agent_tasks_team_id", "crm_agent_tasks")
        _drop_index_if_exists("ix_crm_agent_tasks_task_key", "crm_agent_tasks")
        op.drop_table("crm_agent_tasks")

    if _table_exists("crm_agent_messages"):
        _drop_index_if_exists("idx_agent_message_team_user_created", "crm_agent_messages")
        _drop_index_if_exists("idx_agent_message_session_created", "crm_agent_messages")
        _drop_index_if_exists("ix_crm_agent_messages_created_time", "crm_agent_messages")
        _drop_index_if_exists("ix_crm_agent_messages_event_type", "crm_agent_messages")
        _drop_index_if_exists("ix_crm_agent_messages_session_id", "crm_agent_messages")
        _drop_index_if_exists("ix_crm_agent_messages_user_id", "crm_agent_messages")
        _drop_index_if_exists("ix_crm_agent_messages_team_id", "crm_agent_messages")
        op.drop_table("crm_agent_messages")

    if _table_exists("crm_agent_sessions"):
        _drop_index_if_exists("idx_agent_session_created_time", "crm_agent_sessions")
        _drop_index_if_exists("idx_agent_session_team_user_status", "crm_agent_sessions")
        _drop_index_if_exists("ix_crm_agent_sessions_status", "crm_agent_sessions")
        _drop_index_if_exists("ix_crm_agent_sessions_user_id", "crm_agent_sessions")
        _drop_index_if_exists("ix_crm_agent_sessions_team_id", "crm_agent_sessions")
        _drop_index_if_exists("ix_crm_agent_sessions_session_key", "crm_agent_sessions")
        op.drop_table("crm_agent_sessions")

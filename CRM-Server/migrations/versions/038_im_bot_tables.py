"""im channel tables and feishu bot integration fields

Revision ID: 038_im_bot_tables
Revises: 037_team_scoped_customer_name_uniqueness
Create Date: 2026-07-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "038_im_bot_tables"
down_revision: Union[str, None] = "037_team_scoped_customer_name_uniqueness"
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


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE()
        AND table_name = :table_name
        AND column_name = :column_name
    """), {"table_name": table_name, "column_name": column_name}).scalar() > 0


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str], unique: bool = False) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _index_exists(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if _table_exists("oauth_provider_configs"):
        if not _column_exists("oauth_provider_configs", "bot_enabled"):
            op.add_column("oauth_provider_configs", sa.Column("bot_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0"), comment="是否启用AI Agent机器人"))
        if not _column_exists("oauth_provider_configs", "bot_verification_token"):
            op.add_column("oauth_provider_configs", sa.Column("bot_verification_token", sa.String(length=255), nullable=True, comment="机器人事件订阅校验Token"))
        if not _column_exists("oauth_provider_configs", "bot_encrypt_key"):
            op.add_column("oauth_provider_configs", sa.Column("bot_encrypt_key", sa.String(length=255), nullable=True, comment="机器人事件订阅加密Key"))
        if not _column_exists("oauth_provider_configs", "bot_open_id"):
            op.add_column("oauth_provider_configs", sa.Column("bot_open_id", sa.String(length=128), nullable=True, comment="机器人Open ID"))
        if not _column_exists("oauth_provider_configs", "bot_callback_path"):
            op.add_column("oauth_provider_configs", sa.Column("bot_callback_path", sa.String(length=200), nullable=True, comment="机器人事件回调路径"))

    if not _table_exists("agent_channel_sessions"):
        op.create_table(
            "agent_channel_sessions",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("user_id", sa.BigInteger(), nullable=False, comment="系统用户ID"),
            sa.Column("provider", sa.String(length=30), nullable=False, comment="IM渠道"),
            sa.Column("external_tenant_key", sa.String(length=128), nullable=True, comment="外部租户标识"),
            sa.Column("chat_id", sa.String(length=128), nullable=False, comment="外部会话ID"),
            sa.Column("thread_id", sa.String(length=128), nullable=False, server_default="", comment="外部话题/线程ID"),
            sa.Column("agent_session_id", sa.BigInteger(), nullable=False, comment="Agent会话ID"),
            sa.Column("last_message_id", sa.String(length=128), nullable=True, comment="最近处理的外部消息ID"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active", comment="状态"),
            sa.Column("created_time", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False, comment="创建时间"),
            sa.Column("updated_time", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False, comment="更新时间"),
            sa.ForeignKeyConstraint(["agent_session_id"], ["crm_agent_sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "provider",
                "team_id",
                "user_id",
                "chat_id",
                "thread_id",
                name="uq_agent_channel_session_scope",
            ),
            comment="Agent IM渠道会话映射表",
        )
    _create_index_if_missing("ix_agent_channel_sessions_team_id", "agent_channel_sessions", ["team_id"])
    _create_index_if_missing("ix_agent_channel_sessions_user_id", "agent_channel_sessions", ["user_id"])
    _create_index_if_missing("ix_agent_channel_sessions_provider", "agent_channel_sessions", ["provider"])
    _create_index_if_missing("ix_agent_channel_sessions_agent_session_id", "agent_channel_sessions", ["agent_session_id"])
    _create_index_if_missing("ix_agent_channel_sessions_status", "agent_channel_sessions", ["status"])
    _create_index_if_missing("idx_agent_channel_session_lookup", "agent_channel_sessions", ["provider", "team_id", "chat_id", "user_id"])

    if not _table_exists("im_inbound_events"):
        op.create_table(
            "im_inbound_events",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("provider", sa.String(length=30), nullable=False, comment="IM渠道"),
            sa.Column("team_id", sa.BigInteger(), nullable=True, comment="团队ID"),
            sa.Column("event_id", sa.String(length=128), nullable=False, comment="渠道事件ID"),
            sa.Column("message_id", sa.String(length=128), nullable=True, comment="渠道消息ID"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="received", comment="处理状态"),
            sa.Column("request_hash", sa.String(length=64), nullable=True, comment="请求Hash"),
            sa.Column("response_message_id", sa.String(length=128), nullable=True, comment="回复消息ID"),
            sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
            sa.Column("raw_event", sa.JSON(), nullable=True, comment="必要事件快照"),
            sa.Column("created_time", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False, comment="创建时间"),
            sa.Column("processed_time", sa.DateTime(), nullable=True, comment="处理时间"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("provider", "event_id", name="uq_im_inbound_provider_event"),
            comment="IM入站事件幂等表",
        )
    _create_index_if_missing("ix_im_inbound_events_provider", "im_inbound_events", ["provider"])
    _create_index_if_missing("ix_im_inbound_events_team_id", "im_inbound_events", ["team_id"])
    _create_index_if_missing("ix_im_inbound_events_message_id", "im_inbound_events", ["message_id"])
    _create_index_if_missing("ix_im_inbound_events_status", "im_inbound_events", ["status"])
    _create_index_if_missing("idx_im_inbound_team_status", "im_inbound_events", ["team_id", "status"])


def downgrade() -> None:
    _drop_index_if_exists("idx_im_inbound_team_status", "im_inbound_events")
    _drop_index_if_exists("ix_im_inbound_events_status", "im_inbound_events")
    _drop_index_if_exists("ix_im_inbound_events_message_id", "im_inbound_events")
    _drop_index_if_exists("ix_im_inbound_events_team_id", "im_inbound_events")
    _drop_index_if_exists("ix_im_inbound_events_provider", "im_inbound_events")
    if _table_exists("im_inbound_events"):
        op.drop_table("im_inbound_events")

    _drop_index_if_exists("idx_agent_channel_session_lookup", "agent_channel_sessions")
    _drop_index_if_exists("ix_agent_channel_sessions_status", "agent_channel_sessions")
    _drop_index_if_exists("ix_agent_channel_sessions_agent_session_id", "agent_channel_sessions")
    _drop_index_if_exists("ix_agent_channel_sessions_provider", "agent_channel_sessions")
    _drop_index_if_exists("ix_agent_channel_sessions_user_id", "agent_channel_sessions")
    _drop_index_if_exists("ix_agent_channel_sessions_team_id", "agent_channel_sessions")
    if _table_exists("agent_channel_sessions"):
        op.drop_table("agent_channel_sessions")

    if _table_exists("oauth_provider_configs"):
        for column_name in [
            "bot_callback_path",
            "bot_open_id",
            "bot_encrypt_key",
            "bot_verification_token",
            "bot_enabled",
        ]:
            if _column_exists("oauth_provider_configs", column_name):
                op.drop_column("oauth_provider_configs", column_name)

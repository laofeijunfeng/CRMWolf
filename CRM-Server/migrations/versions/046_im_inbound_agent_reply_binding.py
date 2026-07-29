"""add hidden Agent reply binding to IM inbound events

Revision ID: 046_im_inbound_agent_reply_binding
Revises: 045_backfill_deal_journey_stage_events
Create Date: 2026-07-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "046_im_inbound_agent_reply_binding"
down_revision: Union[str, None] = "045_backfill_deal_journey_stage_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE()
        AND table_name = :table_name
        AND column_name = :column_name
    """), {"table_name": table_name, "column_name": column_name}).scalar() > 0


def _index_exists(table_name: str, index_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.statistics
        WHERE table_schema = DATABASE()
        AND table_name = :table_name
        AND index_name = :index_name
    """), {"table_name": table_name, "index_name": index_name}).scalar() > 0


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _index_exists(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not _column_exists("im_inbound_events", "agent_session_id"):
        op.add_column("im_inbound_events", sa.Column("agent_session_id", sa.BigInteger(), nullable=True, comment="回复绑定的Agent会话ID"))
    if not _column_exists("im_inbound_events", "agent_task_id"):
        op.add_column("im_inbound_events", sa.Column("agent_task_id", sa.BigInteger(), nullable=True, comment="回复绑定的Agent任务ID"))
    if not _column_exists("im_inbound_events", "agent_interaction_type"):
        op.add_column("im_inbound_events", sa.Column("agent_interaction_type", sa.String(length=80), nullable=True, comment="回复绑定的Agent交互事件类型"))

    _create_index_if_missing("ix_im_inbound_events_agent_session_id", "im_inbound_events", ["agent_session_id"])
    _create_index_if_missing("ix_im_inbound_events_agent_task_id", "im_inbound_events", ["agent_task_id"])


def downgrade() -> None:
    _drop_index_if_exists("ix_im_inbound_events_agent_task_id", "im_inbound_events")
    _drop_index_if_exists("ix_im_inbound_events_agent_session_id", "im_inbound_events")
    if _column_exists("im_inbound_events", "agent_interaction_type"):
        op.drop_column("im_inbound_events", "agent_interaction_type")
    if _column_exists("im_inbound_events", "agent_task_id"):
        op.drop_column("im_inbound_events", "agent_task_id")
    if _column_exists("im_inbound_events", "agent_session_id"):
        op.drop_column("im_inbound_events", "agent_session_id")

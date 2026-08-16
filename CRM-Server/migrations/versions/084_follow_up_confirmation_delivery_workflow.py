"""add durable follow up confirmation delivery workflow fields

Revision ID: 084_follow_up_confirmation_delivery_workflow
Revises: 083_agent_async_operation_counters
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "084_follow_up_confirmation_delivery_workflow"
down_revision: str | None = "083_agent_async_operation_counters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "crm_follow_up_task_confirmation_prompt_deliveries"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            "purpose",
            sa.String(length=40),
            nullable=False,
            server_default="INBOX_VISIBILITY",
            comment="投递用途/展示语义",
        ),
    )
    op.add_column(
        TABLE,
        sa.Column("provider_message_id", sa.String(length=160), nullable=True, comment="渠道返回的消息或可见对象ID"),
    )
    op.add_column(TABLE, sa.Column("recipient_id", sa.String(length=160), nullable=True, comment="渠道接收人ID"))
    op.add_column(TABLE, sa.Column("origin_turn_id", sa.String(length=160), nullable=True, comment="来源Agent轮次ID"))
    op.add_column(TABLE, sa.Column("origin_message_id", sa.String(length=160), nullable=True, comment="来源消息ID"))
    op.add_column(
        TABLE, sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0", comment="实际投递尝试次数")
    )
    op.add_column(TABLE, sa.Column("next_attempt_at", sa.DateTime(), nullable=True, comment="下次允许重试时间"))
    op.add_column(
        TABLE,
        sa.Column(
            "updated_time",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="更新时间",
        ),
    )

    op.alter_column(TABLE, "attempted_at", existing_type=sa.DateTime(), nullable=True)
    op.alter_column(TABLE, "prompted_at", existing_type=sa.DateTime(), nullable=True)
    op.alter_column(TABLE, "status", existing_type=sa.String(length=20), server_default="QUEUED")

    op.create_index("idx_follow_up_confirmation_purpose", TABLE, ["team_id", "purpose", "status", "created_time"])
    op.create_index("idx_follow_up_confirmation_provider_message", TABLE, ["provider_message_id"])
    op.create_index("idx_follow_up_confirmation_recipient", TABLE, ["recipient_id"])
    op.create_index("idx_follow_up_confirmation_origin_turn", TABLE, ["origin_turn_id"])
    op.create_index("idx_follow_up_confirmation_origin_message", TABLE, ["origin_message_id"])
    op.create_index("idx_follow_up_confirmation_next_attempt", TABLE, ["next_attempt_at"])
    op.create_index(
        "idx_follow_up_confirmation_recovery",
        TABLE,
        ["status", "next_attempt_at", "attempt_count", "created_time"],
    )


def downgrade() -> None:
    for index_name in (
        "idx_follow_up_confirmation_recovery",
        "idx_follow_up_confirmation_next_attempt",
        "idx_follow_up_confirmation_origin_message",
        "idx_follow_up_confirmation_origin_turn",
        "idx_follow_up_confirmation_recipient",
        "idx_follow_up_confirmation_provider_message",
        "idx_follow_up_confirmation_purpose",
    ):
        op.drop_index(index_name, table_name=TABLE)
    op.alter_column(TABLE, "status", existing_type=sa.String(length=20), server_default="SENT")
    op.alter_column(TABLE, "prompted_at", existing_type=sa.DateTime(), nullable=False)
    op.alter_column(TABLE, "attempted_at", existing_type=sa.DateTime(), nullable=False)
    for column_name in (
        "updated_time",
        "next_attempt_at",
        "attempt_count",
        "origin_message_id",
        "origin_turn_id",
        "recipient_id",
        "provider_message_id",
        "purpose",
    ):
        op.drop_column(TABLE, column_name)

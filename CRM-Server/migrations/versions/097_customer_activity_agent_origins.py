"""Persist immutable Agent origins for customer activities.

Revision ID: 097_customer_activity_agent_origins
Revises: 096_acquisition_sources
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "097_customer_activity_agent_origins"
down_revision: str | None = "096_acquisition_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "crm_customer_activity_agent_origins"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, comment="主键"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column(
            "activity_id",
            sa.BigInteger(),
            sa.ForeignKey("crm_customer_activities.id", ondelete="CASCADE"),
            nullable=False,
            comment="客户活动ID",
        ),
        sa.Column("owner_id", sa.String(length=100), nullable=False, comment="Agent归属用户ID"),
        sa.Column("agent_session_id", sa.BigInteger(), nullable=False, comment="来源Agent会话ID"),
        sa.Column("source_user_message_id", sa.BigInteger(), nullable=True, comment="来源用户消息ID"),
        sa.Column("source_assistant_message_id", sa.BigInteger(), nullable=False, comment="来源助手消息ID"),
        sa.Column("agent_operation_public_id", sa.String(length=64), nullable=False, comment="来源Agent异步操作ID"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.UniqueConstraint("team_id", "activity_id", name="uq_customer_activity_agent_origin"),
        comment="客户活动Agent来源归属表",
    )
    op.create_index(op.f("ix_crm_customer_activity_agent_origins_team_id"), TABLE, ["team_id"])
    op.create_index(op.f("ix_crm_customer_activity_agent_origins_owner_id"), TABLE, ["owner_id"])
    op.create_index(op.f("ix_crm_customer_activity_agent_origins_agent_session_id"), TABLE, ["agent_session_id"])
    op.create_index(
        op.f("ix_crm_customer_activity_agent_origins_source_user_message_id"),
        TABLE,
        ["source_user_message_id"],
    )
    op.create_index(
        op.f("ix_crm_customer_activity_agent_origins_source_assistant_message_id"),
        TABLE,
        ["source_assistant_message_id"],
    )
    op.create_index(
        op.f("ix_crm_customer_activity_agent_origins_agent_operation_public_id"),
        TABLE,
        ["agent_operation_public_id"],
    )
    op.create_index(
        "idx_customer_activity_agent_origin_session",
        TABLE,
        ["team_id", "owner_id", "agent_session_id"],
    )
    op.create_index(
        "idx_customer_activity_agent_origin_assistant",
        TABLE,
        ["team_id", "source_assistant_message_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_customer_activity_agent_origin_assistant", table_name=TABLE)
    op.drop_index("idx_customer_activity_agent_origin_session", table_name=TABLE)
    op.drop_index(op.f("ix_crm_customer_activity_agent_origins_agent_operation_public_id"), table_name=TABLE)
    op.drop_index(op.f("ix_crm_customer_activity_agent_origins_source_assistant_message_id"), table_name=TABLE)
    op.drop_index(op.f("ix_crm_customer_activity_agent_origins_source_user_message_id"), table_name=TABLE)
    op.drop_index(op.f("ix_crm_customer_activity_agent_origins_agent_session_id"), table_name=TABLE)
    op.drop_index(op.f("ix_crm_customer_activity_agent_origins_owner_id"), table_name=TABLE)
    op.drop_index(op.f("ix_crm_customer_activity_agent_origins_team_id"), table_name=TABLE)
    op.drop_table(TABLE)

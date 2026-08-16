"""add exact IM confirmation delivery bindings

Revision ID: 086_im_confirmation_delivery_binding
Revises: 085_customer_activity_post_commit_jobs
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "086_im_confirmation_delivery_binding"
down_revision: str | None = "085_customer_activity_post_commit_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "im_inbound_events"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            "confirmation_delivery_public_id", sa.String(length=64), nullable=True, comment="精确绑定的确认提示投递ID"
        ),
    )
    op.add_column(
        TABLE,
        sa.Column("confirmation_case_public_id", sa.String(length=64), nullable=True, comment="精确绑定的确认Case ID"),
    )
    op.add_column(
        TABLE, sa.Column("agent_interaction_id", sa.String(length=80), nullable=True, comment="精确绑定的Agent交互ID")
    )
    op.add_column(
        TABLE, sa.Column("prompt_delivery_key", sa.String(length=128), nullable=True, comment="确认提示幂等归因键")
    )
    op.create_index(
        "idx_im_inbound_confirmation_delivery", TABLE, ["provider", "team_id", "confirmation_delivery_public_id"]
    )
    op.create_index("idx_im_inbound_confirmation_case", TABLE, ["provider", "team_id", "confirmation_case_public_id"])
    op.create_index(op.f("ix_im_inbound_events_agent_interaction_id"), TABLE, ["agent_interaction_id"])
    op.create_index(op.f("ix_im_inbound_events_prompt_delivery_key"), TABLE, ["prompt_delivery_key"])


def downgrade() -> None:
    op.drop_index(op.f("ix_im_inbound_events_prompt_delivery_key"), table_name=TABLE)
    op.drop_index(op.f("ix_im_inbound_events_agent_interaction_id"), table_name=TABLE)
    op.drop_index("idx_im_inbound_confirmation_case", table_name=TABLE)
    op.drop_index("idx_im_inbound_confirmation_delivery", table_name=TABLE)
    for column_name in (
        "prompt_delivery_key",
        "agent_interaction_id",
        "confirmation_case_public_id",
        "confirmation_delivery_public_id",
    ):
        op.drop_column(TABLE, column_name)

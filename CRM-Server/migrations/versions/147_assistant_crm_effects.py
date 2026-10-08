"""Add atomic assistant CRM target effect receipts.

Revision ID: 147_assistant_crm_effects
Revises: 146_assistant_conversation_events
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "147_assistant_crm_effects"
down_revision: str | None = "146_assistant_conversation_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_assistant_crm_effects",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("effect_kind", sa.String(40), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("target_public_id", sa.String(64), nullable=False),
        sa.Column("approval_id", sa.BigInteger(), nullable=True),
        sa.Column("stage_snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column("previous_snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column("previous_version", sa.Integer(), nullable=True),
        sa.Column("resulting_version", sa.Integer(), nullable=True),
        sa.Column("created_time", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("team_id", "command_id", "effect_kind", name="uq_assistant_crm_effect_command"),
    )


def downgrade() -> None:
    op.drop_table("crm_assistant_crm_effects")

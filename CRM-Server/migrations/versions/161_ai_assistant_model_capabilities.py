"""Persist assistant model output protocol and capability verification.

Revision ID: 161_ai_assistant_model_capabilities
Revises: 160_payment_record_composition
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "161_ai_assistant_model_capabilities"
down_revision: str | None = "160_payment_record_composition"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "crm_ai_config",
        sa.Column("structured_output_mode", sa.String(16), nullable=False, server_default="json_object"),
    )
    op.add_column("crm_ai_config", sa.Column("assistant_verified_fingerprint", sa.String(64), nullable=True))
    op.add_column("crm_ai_config", sa.Column("assistant_verified_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("crm_ai_config", "assistant_verified_at")
    op.drop_column("crm_ai_config", "assistant_verified_fingerprint")
    op.drop_column("crm_ai_config", "structured_output_mode")

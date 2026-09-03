"""Persist final Agent UI interaction values for immutable history display."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "128_agent_ui_action_submitted_values"
down_revision: str | None = "127_canonicalize_follow_up_confirmation_questions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "crm_agent_ui_actions",
        sa.Column(
            "submitted_values",
            sa.JSON(),
            nullable=True,
            comment="一次性交互最终提交值(只读展示快照)",
        ),
    )


def downgrade() -> None:
    op.drop_column("crm_agent_ui_actions", "submitted_values")

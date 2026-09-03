"""Expand customer profile publication status storage.

Revision ID: 126_expand_customer_profile_publication_status
Revises: 125_merge_activity_and_payment_heads
Create Date: 2026-09-02
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "126_expand_customer_profile_publication_status"
down_revision: str | None = "125_merge_activity_and_payment_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "crm_customer_profile_projection_versions",
        "publication_status",
        existing_type=sa.String(length=20),
        type_=sa.String(length=32),
        existing_nullable=False,
    )


def downgrade() -> None:
    # The current canonical status ``PUBLISHED_WITH_WARNINGS`` is 23 characters
    # long, so shrinking this column would be destructive for valid rows.
    raise RuntimeError("Cannot safely downgrade publication_status below 32 characters")

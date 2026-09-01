"""Retire legacy API permissions from the assignable permission catalog.

Revision ID: 112_retire_legacy_api_permissions
Revises: 111_customer_activity_deletion_tombstones
Create Date: 2026-08-31
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "112_retire_legacy_api_permissions"
down_revision: str | None = "111_customer_activity_deletion_tombstones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_API_PERMISSION_CODES = (
    "apikey:manage",
    "lead:api:list",
    "lead:api:read",
    "customer:api:list",
    "customer:api:read",
    "opportunity:api:list",
    "opportunity:api:read",
    "contract:api:list",
    "contract:api:read",
    "payment:api:create",
    "payment:api:list",
    "payment:api:read",
    "invoice:api:list",
)


def upgrade() -> None:
    op.add_column(
        "permissions",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
            comment="是否可用于新授权",
        ),
    )
    permissions = sa.table(
        "permissions",
        sa.column("code", sa.String()),
        sa.column("is_active", sa.Boolean()),
    )
    op.execute(
        permissions.update()
        .where(permissions.c.code.in_(LEGACY_API_PERMISSION_CODES))
        .values(is_active=False)
    )
    op.alter_column("permissions", "is_active", server_default=None)


def downgrade() -> None:
    op.drop_column("permissions", "is_active")

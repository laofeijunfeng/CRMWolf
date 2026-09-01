"""Add monotonic customer-member revision for Customer Intelligence events.

Revision ID: 115_customer_member_intelligence_revision
Revises: 114_sales_commitment_intelligence_revision
Create Date: 2026-08-31
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "115_customer_member_intelligence_revision"
down_revision: str | None = "114_sales_commitment_intelligence_revision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    if "post_commit_revision" not in _columns("crm_customer_members"):
        op.add_column(
            "crm_customer_members",
            sa.Column(
                "post_commit_revision",
                sa.Integer(),
                nullable=False,
                server_default="1",
                comment="客户智能后提交事件修订号",
            ),
        )
    op.alter_column(
        "crm_customer_members",
        "post_commit_revision",
        existing_type=sa.Integer(),
        server_default=None,
    )


def downgrade() -> None:
    if "post_commit_revision" in _columns("crm_customer_members"):
        op.drop_column("crm_customer_members", "post_commit_revision")

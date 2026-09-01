"""Add monotonic contact revision for customer intelligence events.

Revision ID: 113_contact_intelligence_revision
Revises: 112_retire_legacy_api_permissions
Create Date: 2026-08-31
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "113_contact_intelligence_revision"
down_revision: str | None = "112_retire_legacy_api_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    columns = _columns("crm_contacts")
    if "post_commit_revision" not in columns:
        op.add_column(
            "crm_contacts",
            sa.Column(
                "post_commit_revision",
                sa.Integer(),
                nullable=False,
                server_default="1",
                comment="客户智能后提交事件修订号",
            ),
        )
    # The first attempt may have added the column before Alembic recorded the
    # revision.  Re-applying the normalization is safe and makes the migration
    # recoverable on MySQL, whose DDL is not transactional.
    op.alter_column(
        "crm_contacts",
        "post_commit_revision",
        existing_type=sa.Integer(),
        server_default=None,
    )

    if "updated_time" not in columns:
        op.add_column(
            "crm_contacts",
            sa.Column("updated_time", sa.DateTime(), nullable=True, comment="更新时间"),
        )
    op.execute(sa.text("UPDATE crm_contacts SET updated_time = created_time WHERE updated_time IS NULL"))
    op.alter_column(
        "crm_contacts",
        "updated_time",
        existing_type=sa.DateTime(),
        nullable=False,
    )


def downgrade() -> None:
    columns = _columns("crm_contacts")
    if "updated_time" in columns:
        op.drop_column("crm_contacts", "updated_time")
    if "post_commit_revision" in columns:
        op.drop_column("crm_contacts", "post_commit_revision")

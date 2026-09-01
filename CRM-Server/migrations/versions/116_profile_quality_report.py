"""Persist non-blocking customer profile quality diagnostics.

Revision ID: 116_profile_quality_report
Revises: 115_customer_member_intelligence_revision
Create Date: 2026-09-01
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "116_profile_quality_report"
down_revision: str | None = "115_customer_member_intelligence_revision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("crm_customer_profile_projection_versions")}
    if "quality_report_json" not in columns:
        op.add_column(
            "crm_customer_profile_projection_versions",
            sa.Column(
                "quality_report_json",
                sa.JSON(),
                nullable=True,
                comment="内部内容质量诊断, 不展示在档案正文",
            ),
        )
        op.execute(
            sa.text(
                "UPDATE crm_customer_profile_projection_versions "
                "SET quality_report_json = '{}' WHERE quality_report_json IS NULL"
            )
        )
        op.alter_column(
            "crm_customer_profile_projection_versions",
            "quality_report_json",
            existing_type=sa.JSON(),
            nullable=False,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("crm_customer_profile_projection_versions")}
    if "quality_report_json" in columns:
        op.drop_column("crm_customer_profile_projection_versions", "quality_report_json")

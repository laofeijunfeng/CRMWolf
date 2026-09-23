"""Add team reminder rules.

Revision ID: 138_reminder_rules
Revises: 137_datatable_export_permissions
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "138_reminder_rules"
down_revision: str | None = "137_datatable_export_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_reminder_rules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("name", sa.String(length=100), nullable=False, comment="规则名称"),
        sa.Column("object_type", sa.String(length=40), nullable=False, comment="业务对象"),
        sa.Column("trigger", sa.String(length=20), nullable=False, comment="schedule/change/date"),
        sa.Column("rule", sa.JSON(), nullable=False, comment="提醒规则JSON"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true(), comment="是否启用"),
        sa.Column("created_by", sa.Integer(), nullable=True, comment="创建人用户ID"),
        sa.Column("created_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
        sa.Column("last_modified_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="最后修改时间"),
        sa.PrimaryKeyConstraint("id"),
        comment="团队提醒规则",
    )
    op.create_index("idx_crm_reminder_rules_team", "crm_reminder_rules", ["team_id"])
    op.create_index("idx_crm_reminder_rules_object", "crm_reminder_rules", ["team_id", "object_type"])


def downgrade() -> None:
    op.drop_index("idx_crm_reminder_rules_object", table_name="crm_reminder_rules")
    op.drop_index("idx_crm_reminder_rules_team", table_name="crm_reminder_rules")
    op.drop_table("crm_reminder_rules")

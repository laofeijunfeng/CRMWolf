"""Add CRMWolf workflow definitions table.

Revision ID: 131_crm_workflows
Revises: 130_outbound_notification_jobs
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "131_crm_workflows"
down_revision: str | None = "130_outbound_notification_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKFLOW_TABLE = "crm_workflows"


def upgrade() -> None:
    op.create_table(
        WORKFLOW_TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("team_id", sa.BigInteger(), nullable=True, comment="团队ID（NULL表示系统级）"),
        sa.Column("name", sa.String(length=100), nullable=False, comment="工作流名称"),
        sa.Column("description", sa.Text(), nullable=True, comment="描述"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft", comment="draft/published/paused"),
        sa.Column("dsl", sa.JSON(), nullable=False, comment="Workflow DSL JSON"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人用户ID"),
        sa.Column(
            "created_time",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间",
        ),
        sa.Column(
            "last_modified_time",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="最后修改时间（兼乐观锁版本）",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="CRMWolf 工作流定义表",
    )
    op.create_index("idx_crm_workflows_team_id", WORKFLOW_TABLE, ["team_id"])
    op.create_index("idx_crm_workflows_status", WORKFLOW_TABLE, ["status"])


def downgrade() -> None:
    op.drop_index("idx_crm_workflows_status", table_name=WORKFLOW_TABLE)
    op.drop_index("idx_crm_workflows_team_id", table_name=WORKFLOW_TABLE)
    op.drop_table(WORKFLOW_TABLE)

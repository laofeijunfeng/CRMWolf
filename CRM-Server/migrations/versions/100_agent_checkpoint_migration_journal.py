"""Add the one-time Agent checkpoint migration evidence journal.

Revision ID: 100_agent_checkpoint_migration_journal
Revises: 099_customer_intelligence_review_runtime
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "100_agent_checkpoint_migration_journal"
down_revision: str | None = "099_customer_intelligence_review_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "crm_agent_checkpoint_migration_journal"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("migration_key", sa.String(length=100), primary_key=True, comment="一次性迁移阶段标识"),
        sa.Column("schema_version", sa.String(length=100), nullable=False, comment="证据契约版本"),
        sa.Column("evidence_sha256", sa.String(length=64), nullable=False, comment="证据字节SHA-256"),
        sa.Column(
            "created_time",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="迁移事务提交时间",
        ),
        comment="WP10一次性checkpoint迁移事务证据 / Epic收口时删除",
    )


def downgrade() -> None:
    op.drop_table(TABLE)

"""Add reminder rule run ledger.

Revision ID: 139_reminder_rule_runs
Revises: 138_reminder_rules
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "139_reminder_rule_runs"
down_revision: str | None = "138_reminder_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_reminder_rule_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("rule_id", sa.BigInteger(), nullable=False, comment="提醒规则ID"),
        sa.Column("object_type", sa.String(length=40), nullable=False, comment="业务对象"),
        sa.Column("object_id", sa.BigInteger(), nullable=False, comment="业务对象ID"),
        sa.Column("window_key", sa.String(length=120), nullable=False, comment="同一静默窗口去重键"),
        sa.Column("recipient_ids", sa.String(length=500), nullable=False, comment="接收用户ID"),
        sa.Column("message", sa.Text(), nullable=False, comment="实际发送文案"),
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0", comment="送达人数"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0", comment="跳过人数"),
        sa.Column("created_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="发送时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id", "object_id", "window_key", name="uq_reminder_rule_run_window"),
        comment="提醒规则运行记录",
    )
    op.create_index("idx_crm_reminder_rule_runs_team", "crm_reminder_rule_runs", ["team_id", "created_time"])


def downgrade() -> None:
    op.drop_index("idx_crm_reminder_rule_runs_team", table_name="crm_reminder_rule_runs")
    op.drop_table("crm_reminder_rule_runs")

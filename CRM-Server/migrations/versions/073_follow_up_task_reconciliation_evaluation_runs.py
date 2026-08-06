"""create follow up task reconciliation evaluation run logs

Revision ID: 073_follow_up_task_reconciliation_evaluation_runs
Revises: 072_follow_up_task_reconciliation_and_llm_run_logs
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "073_follow_up_task_reconciliation_evaluation_runs"
down_revision: str | None = "072_follow_up_task_reconciliation_and_llm_run_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(
            sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"),
            {"table_name": table_name},
        ).all()
        return bool(rows)

    return (
        conn.execute(
            sa.text("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
            """),
            {"table_name": table_name},
        ).scalar()
        > 0
    )


def upgrade() -> None:
    table_name = "crm_follow_up_task_reconciliation_evaluation_runs"
    if _table_exists(table_name):
        return

    op.create_table(
        table_name,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="对外reconciliation评测运行ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=True, comment="团队ID；系统级评测可为空"),
        sa.Column("suite_name", sa.String(length=120), nullable=False, comment="评测套件名称"),
        sa.Column("fixture_path", sa.String(length=500), nullable=True, comment="评测样本路径"),
        sa.Column("fixture_hash", sa.String(length=64), nullable=True, comment="评测样本内容hash"),
        sa.Column("status", sa.String(length=20), nullable=False, comment="运行状态"),
        sa.Column("ok", sa.Boolean(), nullable=False, comment="质量门禁是否通过"),
        sa.Column("total_cases", sa.Integer(), nullable=False, server_default="0", comment="样本总数"),
        sa.Column("passed_cases", sa.Integer(), nullable=False, server_default="0", comment="通过样本数"),
        sa.Column("failed_cases", sa.Integer(), nullable=False, server_default="0", comment="失败样本数"),
        sa.Column("false_close_count", sa.Integer(), nullable=False, server_default="0", comment="误关闭样本数"),
        sa.Column("false_close_rate", sa.Float(), nullable=False, server_default="0", comment="误关闭率"),
        sa.Column("false_delay_count", sa.Integer(), nullable=False, server_default="0", comment="误延期样本数"),
        sa.Column("false_delay_rate", sa.Float(), nullable=False, server_default="0", comment="误延期率"),
        sa.Column(
            "missed_confirmation_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="该追问未追问样本数",
        ),
        sa.Column(
            "missed_confirmation_rate",
            sa.Float(),
            nullable=False,
            server_default="0",
            comment="该追问未追问率",
        ),
        sa.Column("over_confirmation_count", sa.Integer(), nullable=False, server_default="0", comment="过度追问样本数"),
        sa.Column("over_confirmation_rate", sa.Float(), nullable=False, server_default="0", comment="过度追问率"),
        sa.Column("metrics_json", sa.JSON(), nullable=True, comment="完整指标快照"),
        sa.Column("failure_cases_json", sa.JSON(), nullable=True, comment="失败样本摘要"),
        sa.Column("case_results_json", sa.JSON(), nullable=True, comment="全部样本结果快照"),
        sa.Column("thresholds_json", sa.JSON(), nullable=True, comment="质量门禁阈值快照"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="运行错误摘要"),
        sa.Column("duration_ms", sa.Integer(), nullable=True, comment="耗时毫秒"),
        sa.Column(
            "started_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="开始时间",
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="结束时间",
        ),
        sa.Column(
            "created_time",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id", name="uq_follow_up_recon_eval_public_id"),
        comment="跟进任务reconciliation评测运行表",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_follow_up_recon_eval_public", table_name, ["public_id"])
    op.create_index("idx_follow_up_recon_eval_team", table_name, ["team_id"])
    op.create_index("idx_follow_up_recon_eval_suite", table_name, ["suite_name"])
    op.create_index("idx_follow_up_recon_eval_fixture_hash", table_name, ["fixture_hash"])
    op.create_index("idx_follow_up_recon_eval_status", table_name, ["status"])
    op.create_index("idx_follow_up_recon_eval_ok", table_name, ["ok"])
    op.create_index("idx_follow_up_recon_eval_finished", table_name, ["finished_at"])
    op.create_index("idx_follow_up_recon_eval_created", table_name, ["created_time"])
    op.create_index("idx_follow_up_recon_eval_team_suite_time", table_name, ["team_id", "suite_name", "created_time"])
    op.create_index("idx_follow_up_recon_eval_status_time", table_name, ["status", "created_time"])
    op.create_index("idx_follow_up_recon_eval_ok_time", table_name, ["ok", "created_time"])


def downgrade() -> None:
    table_name = "crm_follow_up_task_reconciliation_evaluation_runs"
    if _table_exists(table_name):
        op.drop_table(table_name)

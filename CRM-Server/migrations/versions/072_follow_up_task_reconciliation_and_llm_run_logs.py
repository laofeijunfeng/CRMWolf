"""create follow up task reconciliation and llm run logs

Revision ID: 072_follow_up_task_reconciliation_and_llm_run_logs
Revises: 071_follow_up_task_transition_policy_decision_logs
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "072_follow_up_task_reconciliation_and_llm_run_logs"
down_revision: str | None = "071_follow_up_task_transition_policy_decision_logs"
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
    reconciliation_table = "crm_follow_up_task_reconciliation_runs"
    if not _table_exists(reconciliation_table):
        op.create_table(
            reconciliation_table,
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("public_id", sa.String(length=64), nullable=False, comment="对外reconciliation运行ID"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("customer_id", sa.BigInteger(), nullable=True, comment="客户ID"),
            sa.Column("owner_id", sa.String(length=100), nullable=True, comment="活动/任务归属人"),
            sa.Column("actor_id", sa.String(length=100), nullable=True, comment="触发人"),
            sa.Column("source_activity_id", sa.BigInteger(), nullable=True, comment="来源客户活动ID"),
            sa.Column("source_public_id", sa.String(length=64), nullable=True, comment="来源对象对外ID"),
            sa.Column("status", sa.String(length=20), nullable=False, comment="运行状态"),
            sa.Column("skip_reason", sa.String(length=80), nullable=True, comment="跳过原因"),
            sa.Column(
                "include_cross_owner",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
                comment="是否纳入跨owner候选",
            ),
            sa.Column("lookback_days", sa.Integer(), nullable=False, server_default="90", comment="候选回看天数"),
            sa.Column("lookahead_days", sa.Integer(), nullable=False, server_default="30", comment="候选前看天数"),
            sa.Column("limit", sa.Integer(), nullable=False, server_default="20", comment="候选数量上限"),
            sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0", comment="候选任务数量"),
            sa.Column("candidate_public_ids_json", sa.JSON(), nullable=True, comment="候选任务对外ID快照"),
            sa.Column("filters_json", sa.JSON(), nullable=True, comment="候选过滤条件快照"),
            sa.Column("usage_policy_json", sa.JSON(), nullable=True, comment="使用策略快照"),
            sa.Column("error_message", sa.Text(), nullable=True, comment="错误摘要"),
            sa.Column("duration_ms", sa.Integer(), nullable=True, comment="耗时毫秒"),
            sa.Column("anchor_at", sa.DateTime(), nullable=True, comment="候选窗口锚点时间"),
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
            sa.ForeignKeyConstraint(["customer_id"], ["crm_customers.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["source_activity_id"], ["crm_customer_activities.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("public_id", name="uq_follow_up_reconciliation_run_public_id"),
            comment="跟进任务reconciliation运行日志表",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index("idx_follow_up_reconciliation_team", reconciliation_table, ["team_id"])
        op.create_index("idx_follow_up_reconciliation_customer", reconciliation_table, ["customer_id"])
        op.create_index("idx_follow_up_reconciliation_owner", reconciliation_table, ["owner_id"])
        op.create_index("idx_follow_up_reconciliation_actor", reconciliation_table, ["actor_id"])
        op.create_index("idx_follow_up_reconciliation_activity", reconciliation_table, ["source_activity_id"])
        op.create_index("idx_follow_up_reconciliation_status", reconciliation_table, ["status"])
        op.create_index("idx_follow_up_reconciliation_skip_reason", reconciliation_table, ["skip_reason"])
        op.create_index("idx_follow_up_reconciliation_cross_owner", reconciliation_table, ["include_cross_owner"])
        op.create_index("idx_follow_up_reconciliation_anchor", reconciliation_table, ["anchor_at"])
        op.create_index("idx_follow_up_reconciliation_finished", reconciliation_table, ["finished_at"])
        op.create_index("idx_follow_up_reconciliation_created", reconciliation_table, ["created_time"])
        op.create_index("idx_follow_up_reconciliation_owner_time", reconciliation_table, ["team_id", "owner_id", "created_time"])
        op.create_index("idx_follow_up_reconciliation_status_time", reconciliation_table, ["team_id", "status", "created_time"])
        op.create_index(
            "idx_follow_up_reconciliation_activity_time",
            reconciliation_table,
            ["team_id", "source_activity_id", "created_time"],
        )

    llm_table = "crm_follow_up_task_llm_matcher_runs"
    if not _table_exists(llm_table):
        op.create_table(
            llm_table,
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("public_id", sa.String(length=64), nullable=False, comment="对外LLM匹配运行ID"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("owner_id", sa.String(length=100), nullable=True, comment="活动/任务归属人"),
            sa.Column("actor_id", sa.String(length=100), nullable=True, comment="触发人"),
            sa.Column("source_activity_id", sa.BigInteger(), nullable=True, comment="来源客户活动ID"),
            sa.Column("source_public_id", sa.String(length=64), nullable=True, comment="来源对象对外ID"),
            sa.Column("reconciliation_run_public_id", sa.String(length=64), nullable=True, comment="reconciliation运行对外ID"),
            sa.Column("status", sa.String(length=20), nullable=False, comment="运行状态"),
            sa.Column("source", sa.String(length=80), nullable=False, comment="匹配结果来源"),
            sa.Column("decision", sa.String(length=30), nullable=True, comment="归一化决策"),
            sa.Column("task_public_id", sa.String(length=64), nullable=True, comment="候选任务对外ID"),
            sa.Column("candidate_public_ids_json", sa.JSON(), nullable=True, comment="候选任务对外ID快照"),
            sa.Column("confidence", sa.Float(), nullable=True, comment="归一化置信度"),
            sa.Column(
                "needs_confirmation",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
                comment="是否需要用户确认",
            ),
            sa.Column("forbid_auto_reasons_json", sa.JSON(), nullable=True, comment="禁止自动迁移原因"),
            sa.Column("evidence_terms_json", sa.JSON(), nullable=True, comment="证据词快照"),
            sa.Column("referenced_source_public_ids_json", sa.JSON(), nullable=True, comment="引用来源对外ID"),
            sa.Column("evaluation_failures_json", sa.JSON(), nullable=True, comment="安全评测失败项"),
            sa.Column("model_name", sa.String(length=120), nullable=True, comment="LLM模型名"),
            sa.Column("structured_output_strategy", sa.String(length=40), nullable=True, comment="结构化输出策略"),
            sa.Column("schema_error_type", sa.String(length=80), nullable=True, comment="结构化输出错误类型"),
            sa.Column("schema_error_message", sa.Text(), nullable=True, comment="结构化输出错误摘要"),
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
            sa.ForeignKeyConstraint(["source_activity_id"], ["crm_customer_activities.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("public_id", name="uq_follow_up_llm_matcher_run_public_id"),
            comment="跟进任务LLM语义匹配运行日志表",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index("idx_follow_up_llm_matcher_team", llm_table, ["team_id"])
        op.create_index("idx_follow_up_llm_matcher_owner", llm_table, ["owner_id"])
        op.create_index("idx_follow_up_llm_matcher_actor", llm_table, ["actor_id"])
        op.create_index("idx_follow_up_llm_matcher_activity", llm_table, ["source_activity_id"])
        op.create_index("idx_follow_up_llm_matcher_reconciliation", llm_table, ["reconciliation_run_public_id"])
        op.create_index("idx_follow_up_llm_matcher_status", llm_table, ["status"])
        op.create_index("idx_follow_up_llm_matcher_source", llm_table, ["source"])
        op.create_index("idx_follow_up_llm_matcher_decision", llm_table, ["decision"])
        op.create_index("idx_follow_up_llm_matcher_task_public", llm_table, ["task_public_id"])
        op.create_index("idx_follow_up_llm_matcher_needs_confirmation", llm_table, ["needs_confirmation"])
        op.create_index("idx_follow_up_llm_matcher_schema_error", llm_table, ["schema_error_type"])
        op.create_index("idx_follow_up_llm_matcher_finished", llm_table, ["finished_at"])
        op.create_index("idx_follow_up_llm_matcher_created", llm_table, ["created_time"])
        op.create_index("idx_follow_up_llm_matcher_owner_time", llm_table, ["team_id", "owner_id", "created_time"])
        op.create_index("idx_follow_up_llm_matcher_status_time", llm_table, ["team_id", "status", "created_time"])
        op.create_index("idx_follow_up_llm_matcher_decision_time", llm_table, ["team_id", "decision", "created_time"])
        op.create_index("idx_follow_up_llm_matcher_schema_time", llm_table, ["team_id", "schema_error_type", "created_time"])


def downgrade() -> None:
    if _table_exists("crm_follow_up_task_llm_matcher_runs"):
        op.drop_table("crm_follow_up_task_llm_matcher_runs")
    if _table_exists("crm_follow_up_task_reconciliation_runs"):
        op.drop_table("crm_follow_up_task_reconciliation_runs")

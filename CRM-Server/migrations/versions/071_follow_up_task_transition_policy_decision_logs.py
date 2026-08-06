"""create follow up task transition policy decision logs

Revision ID: 071_follow_up_task_transition_policy_decision_logs
Revises: 070_follow_up_task_event_public_id
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "071_follow_up_task_transition_policy_decision_logs"
down_revision: str | None = "070_follow_up_task_event_public_id"
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
    table_name = "crm_follow_up_task_transition_policy_decision_logs"
    if _table_exists(table_name):
        return

    op.create_table(
        table_name,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="对外策略决策日志ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("owner_id", sa.String(length=100), nullable=True, comment="任务归属人"),
        sa.Column("actor_id", sa.String(length=100), nullable=True, comment="触发人"),
        sa.Column("task_id", sa.BigInteger(), nullable=True, comment="跟进任务ID"),
        sa.Column("source_type", sa.String(length=50), nullable=True, comment="来源类型"),
        sa.Column("source_activity_id", sa.BigInteger(), nullable=True, comment="来源客户活动ID"),
        sa.Column("source_public_id", sa.String(length=64), nullable=True, comment="来源对象对外ID"),
        sa.Column("action", sa.String(length=30), nullable=True, comment="计划迁移动作"),
        sa.Column("allowed", sa.Boolean(), nullable=False, comment="是否允许自动执行"),
        sa.Column("reason", sa.String(length=80), nullable=False, comment="策略决策原因"),
        sa.Column("enabled", sa.Boolean(), nullable=False, comment="团队自动迁移开关是否开启"),
        sa.Column(
            "owner_allowlist_configured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="是否配置归属人白名单",
        ),
        sa.Column("allowed_actions_json", sa.JSON(), nullable=True, comment="命中的动作白名单快照"),
        sa.Column("config_errors_json", sa.JSON(), nullable=True, comment="配置错误快照"),
        sa.Column("policy_result_json", sa.JSON(), nullable=True, comment="完整策略决策快照"),
        sa.Column("context_json", sa.JSON(), nullable=True, comment="决策上下文快照"),
        sa.Column(
            "created_time",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["crm_follow_up_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id", name="uq_follow_up_transition_policy_public_id"),
        comment="跟进任务自动迁移策略决策日志表",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_follow_up_transition_policy_team", table_name, ["team_id"])
    op.create_index("idx_follow_up_transition_policy_owner", table_name, ["owner_id"])
    op.create_index("idx_follow_up_transition_policy_actor", table_name, ["actor_id"])
    op.create_index("idx_follow_up_transition_policy_task", table_name, ["task_id"])
    op.create_index("idx_follow_up_transition_policy_source_type", table_name, ["source_type"])
    op.create_index("idx_follow_up_transition_policy_activity", table_name, ["source_activity_id"])
    op.create_index("idx_follow_up_transition_policy_action", table_name, ["action"])
    op.create_index("idx_follow_up_transition_policy_allowed", table_name, ["allowed"])
    op.create_index("idx_follow_up_transition_policy_reason", table_name, ["reason"])
    op.create_index("idx_follow_up_transition_policy_enabled", table_name, ["enabled"])
    op.create_index("idx_follow_up_transition_policy_created", table_name, ["created_time"])
    op.create_index("idx_follow_up_transition_policy_owner_time", table_name, ["team_id", "owner_id", "created_time"])
    op.create_index("idx_follow_up_transition_policy_reason_time", table_name, ["team_id", "reason", "created_time"])
    op.create_index("idx_follow_up_transition_policy_task_time", table_name, ["team_id", "task_id", "created_time"])


def downgrade() -> None:
    table_name = "crm_follow_up_task_transition_policy_decision_logs"
    if _table_exists(table_name):
        op.drop_table(table_name)

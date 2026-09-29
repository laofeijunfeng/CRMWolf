"""Add sales-assistant task and action tables.

Revision ID: 143_assistant_tasks
Revises: 142_agent_turn_executions
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "143_assistant_tasks"
down_revision: str | None = "142_agent_turn_executions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_assistant_tasks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="任务对外ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="用户ID"),
        sa.Column("status", sa.String(length=20), nullable=False, comment="任务状态"),
        sa.Column("goal", sa.Text(), nullable=False, comment="任务目标"),
        sa.Column("activity_kind", sa.String(length=32), nullable=True, comment="活动类型"),
        sa.Column("draft_json", sa.JSON(), nullable=False, comment="字段级草稿"),
        sa.Column("waiting_type", sa.String(length=32), nullable=True, comment="当前等待类型"),
        sa.Column("waiting_field", sa.String(length=64), nullable=True, comment="等待中的字段名"),
        sa.Column("waiting_json", sa.JSON(), nullable=False, comment="等待点完整载荷（question_id/prompt）"),
        sa.Column("authority_json", sa.JSON(), nullable=False, comment="权威区"),
        sa.Column("committed_json", sa.JSON(), nullable=False, comment="已提交结果（只增不减）"),
        sa.Column("budget_steps", sa.Integer(), nullable=False, server_default="0", comment="已消耗步数"),
        sa.Column("budget_max_steps", sa.Integer(), nullable=False, server_default="50", comment="步数上限"),
        sa.Column("last_error_code", sa.String(length=128), nullable=True, comment="最近错误代码"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0", comment="乐观锁版本"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("last_modified_time", sa.DateTime(), nullable=False, comment="最后修改时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        comment="销售助手任务状态表（Agent 2.0 单一事实来源）",
    )
    op.create_index(
        "idx_assistant_task_owner_active",
        "crm_assistant_tasks",
        ["team_id", "user_id", "status"],
    )
    op.create_table(
        "crm_assistant_actions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="动作对外ID"),
        sa.Column("task_id", sa.BigInteger(), nullable=False, comment="助手任务ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("actor", sa.String(length=20), nullable=False, comment="触发者：MODEL/USER/SYSTEM"),
        sa.Column("action", sa.String(length=64), nullable=False, comment="动作名"),
        sa.Column("input_json", sa.JSON(), nullable=False, comment="输入摘要"),
        sa.Column("result_json", sa.JSON(), nullable=False, comment="结果"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        comment="销售助手动作日志（只追加）",
    )
    op.create_index("idx_assistant_action_task", "crm_assistant_actions", ["task_id", "id"])


def downgrade() -> None:
    op.drop_index("idx_assistant_action_task", table_name="crm_assistant_actions")
    op.drop_table("crm_assistant_actions")
    op.drop_index("idx_assistant_task_owner_active", table_name="crm_assistant_tasks")
    op.drop_table("crm_assistant_tasks")

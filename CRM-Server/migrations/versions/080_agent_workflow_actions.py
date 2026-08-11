"""add agent workflow action ledger

Revision ID: 080_agent_workflow_actions
Revises: 079_invoice_red_offsets
Create Date: 2026-08-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "080_agent_workflow_actions"
down_revision: str | None = "079_invoice_red_offsets"
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


def _index_exists(table_name: str, index_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(
            sa.text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:table_name AND name=:index_name"),
            {"table_name": table_name, "index_name": index_name},
        ).all()
        return bool(rows)
    return (
        conn.execute(
            sa.text("""
                SELECT COUNT(*) FROM information_schema.statistics
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
                  AND index_name = :index_name
            """),
            {"table_name": table_name, "index_name": index_name},
        ).scalar()
        > 0
    )


def _create_index_if_needed(table_name: str, index_name: str, columns: list[str], *, unique: bool = False) -> None:
    if _index_exists(table_name, index_name):
        return
    op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    table_name = "crm_agent_workflow_actions"
    if not _table_exists(table_name):
        op.create_table(
            table_name,
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("workflow_id", sa.String(length=64), nullable=False, comment="Agent工作流ID"),
            sa.Column("action_id", sa.String(length=64), nullable=False, comment="Agent动作ID"),
            sa.Column("parent_action_id", sa.String(length=64), nullable=True, comment="父动作ID"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("user_id", sa.BigInteger(), nullable=True, comment="系统用户ID"),
            sa.Column("session_id", sa.BigInteger(), nullable=True, comment="Agent会话ID"),
            sa.Column("task_id", sa.BigInteger(), nullable=True, comment="兼容挂起任务ID"),
            sa.Column("source_message_id", sa.BigInteger(), nullable=True, comment="来源消息ID"),
            sa.Column("source_type", sa.String(length=80), nullable=False, comment="动作来源"),
            sa.Column("action_type", sa.String(length=100), nullable=False, comment="动作类型"),
            sa.Column("status", sa.String(length=20), nullable=False, comment="动作状态"),
            sa.Column("scope", sa.String(length=50), nullable=False, comment="动作范围"),
            sa.Column("source", sa.String(length=80), nullable=False, comment="业务来源策略"),
            sa.Column("execution_policy", sa.String(length=80), nullable=False, comment="执行策略"),
            sa.Column("on_reject", sa.String(length=80), nullable=False, comment="拒绝策略"),
            sa.Column("blocking", sa.Boolean(), nullable=False, comment="是否阻塞工作流"),
            sa.Column("target_type", sa.String(length=50), nullable=True, comment="目标业务对象类型"),
            sa.Column("target_id", sa.BigInteger(), nullable=True, comment="目标业务对象ID"),
            sa.Column("dependency_json", sa.JSON(), nullable=True, comment="动作依赖"),
            sa.Column("payload_json", sa.JSON(), nullable=True, comment="动作输入载荷"),
            sa.Column("result_json", sa.JSON(), nullable=True, comment="动作结果"),
            sa.Column("decision_json", sa.JSON(), nullable=True, comment="用户或路由决策"),
            sa.Column("idempotency_key", sa.String(length=160), nullable=True, comment="业务幂等键"),
            sa.Column("status_reason", sa.Text(), nullable=True, comment="状态原因"),
            sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
            sa.Column("started_time", sa.DateTime(), nullable=True, comment="开始时间"),
            sa.Column("finished_time", sa.DateTime(), nullable=True, comment="结束时间"),
            sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.Column("last_modified_time", sa.DateTime(), nullable=False, comment="最后修改时间"),
            sa.ForeignKeyConstraint(["session_id"], ["crm_agent_sessions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["task_id"], ["crm_agent_tasks.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["source_message_id"], ["crm_agent_messages.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("workflow_id", "action_id", name="uk_agent_workflow_action_identity"),
            sa.UniqueConstraint("action_id", name="uq_crm_agent_workflow_actions_action_id"),
        )

    _create_index_if_needed(table_name, "idx_agent_workflow_action_workflow_id", ["workflow_id"])
    _create_index_if_needed(table_name, "idx_agent_workflow_action_parent_action", ["parent_action_id"])
    _create_index_if_needed(table_name, "idx_agent_workflow_action_team_id", ["team_id"])
    _create_index_if_needed(table_name, "idx_agent_workflow_action_user_id", ["user_id"])
    _create_index_if_needed(table_name, "idx_agent_workflow_action_session_id", ["session_id"])
    _create_index_if_needed(table_name, "idx_agent_workflow_action_task_id", ["task_id"])
    _create_index_if_needed(table_name, "idx_agent_workflow_action_source_message", ["source_message_id"])
    _create_index_if_needed(table_name, "idx_agent_workflow_action_source_type", ["source_type"])
    _create_index_if_needed(table_name, "idx_agent_workflow_action_action_type", ["action_type"])
    _create_index_if_needed(table_name, "idx_agent_workflow_action_status", ["status"])
    _create_index_if_needed(table_name, "idx_agent_workflow_action_scope", ["scope"])
    _create_index_if_needed(table_name, "idx_agent_workflow_action_target", ["target_type", "target_id"])
    _create_index_if_needed(table_name, "idx_agent_workflow_action_idempotency", ["idempotency_key"])
    _create_index_if_needed(table_name, "idx_agent_workflow_action_created_time", ["created_time"])
    _create_index_if_needed(table_name, "idx_agent_workflow_action_session_status", ["session_id", "status"])
    _create_index_if_needed(table_name, "idx_agent_workflow_action_task_status", ["task_id", "status"])
    _create_index_if_needed(table_name, "idx_agent_workflow_action_team_user_status", ["team_id", "user_id", "status"])
    _create_index_if_needed(table_name, "idx_agent_workflow_action_workflow_created", ["workflow_id", "created_time"])


def downgrade() -> None:
    table_name = "crm_agent_workflow_actions"
    if not _table_exists(table_name):
        return
    for index_name in (
        "idx_agent_workflow_action_workflow_created",
        "idx_agent_workflow_action_team_user_status",
        "idx_agent_workflow_action_task_status",
        "idx_agent_workflow_action_session_status",
        "idx_agent_workflow_action_created_time",
        "idx_agent_workflow_action_idempotency",
        "idx_agent_workflow_action_target",
        "idx_agent_workflow_action_scope",
        "idx_agent_workflow_action_status",
        "idx_agent_workflow_action_action_type",
        "idx_agent_workflow_action_source_type",
        "idx_agent_workflow_action_source_message",
        "idx_agent_workflow_action_task_id",
        "idx_agent_workflow_action_session_id",
        "idx_agent_workflow_action_user_id",
        "idx_agent_workflow_action_team_id",
        "idx_agent_workflow_action_parent_action",
        "idx_agent_workflow_action_workflow_id",
    ):
        if _index_exists(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
    op.drop_table(table_name)

"""Remove the legacy AgentTask persistence model and reply bindings.

Revision ID: 102_drop_agent_task_compatibility
Revises: 101_drop_legacy_agent_workflow_ledgers
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "102_drop_agent_task_compatibility"
down_revision: str | None = "101_drop_legacy_agent_workflow_ledgers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AGENT_TASK_TABLE = "crm_agent_tasks"
WORKFLOW_ACTION_TABLE = "crm_agent_workflow_actions"
TOOL_CALL_TABLE = "crm_agent_tool_calls"
IDEMPOTENCY_TABLE = "crm_agent_idempotency_keys"
IM_INBOUND_EVENT_TABLE = "im_inbound_events"


def upgrade() -> None:
    _drop_task_reference(
        WORKFLOW_ACTION_TABLE,
        indexes=(
            "idx_agent_workflow_action_task_status",
            "idx_agent_workflow_action_task_id",
        ),
    )
    _drop_task_reference(
        TOOL_CALL_TABLE,
        indexes=(
            "idx_agent_tool_call_task_status",
            "ix_crm_agent_tool_calls_task_id",
        ),
    )
    _drop_task_reference(
        IDEMPOTENCY_TABLE,
        indexes=(
            "idx_agent_idempotency_session_task",
            "ix_crm_agent_idempotency_keys_task_id",
        ),
    )
    if _table_exists(IDEMPOTENCY_TABLE):
        _create_index_if_missing(
            "idx_agent_idempotency_session",
            IDEMPOTENCY_TABLE,
            ["session_id"],
        )

    if _table_exists(IM_INBOUND_EVENT_TABLE):
        _drop_index_if_exists("ix_im_inbound_events_agent_task_id", IM_INBOUND_EVENT_TABLE)
        if _column_exists(IM_INBOUND_EVENT_TABLE, "agent_task_id"):
            op.drop_column(IM_INBOUND_EVENT_TABLE, "agent_task_id")

    if _table_exists(AGENT_TASK_TABLE):
        op.drop_table(AGENT_TASK_TABLE)


def downgrade() -> None:
    _create_agent_task_table()

    _drop_index_if_exists("idx_agent_idempotency_session", IDEMPOTENCY_TABLE)
    _restore_task_reference(
        TOOL_CALL_TABLE,
        foreign_key_name="fk_agent_tool_call_task",
        indexes=(
            ("ix_crm_agent_tool_calls_task_id", ["task_id"]),
            ("idx_agent_tool_call_task_status", ["task_id", "status"]),
        ),
        comment="Agent任务ID",
    )
    _restore_task_reference(
        IDEMPOTENCY_TABLE,
        foreign_key_name="fk_agent_idempotency_task",
        indexes=(
            ("ix_crm_agent_idempotency_keys_task_id", ["task_id"]),
            ("idx_agent_idempotency_session_task", ["session_id", "task_id"]),
        ),
        comment="Agent任务ID",
    )
    _restore_task_reference(
        WORKFLOW_ACTION_TABLE,
        foreign_key_name="fk_agent_workflow_action_task",
        indexes=(
            ("idx_agent_workflow_action_task_id", ["task_id"]),
            ("idx_agent_workflow_action_task_status", ["task_id", "status"]),
        ),
        comment="兼容挂起任务ID",
    )

    if _table_exists(IM_INBOUND_EVENT_TABLE) and not _column_exists(IM_INBOUND_EVENT_TABLE, "agent_task_id"):
        op.add_column(
            IM_INBOUND_EVENT_TABLE,
            sa.Column("agent_task_id", sa.BigInteger(), nullable=True, comment="回复绑定的Agent任务ID"),
        )
        _create_index_if_missing(
            "ix_im_inbound_events_agent_task_id",
            IM_INBOUND_EVENT_TABLE,
            ["agent_task_id"],
        )


def _drop_task_reference(table_name: str, *, indexes: tuple[str, ...]) -> None:
    if not _table_exists(table_name) or not _column_exists(table_name, "task_id"):
        return
    _drop_foreign_keys_for_column(table_name, "task_id")
    for index_name in indexes:
        _drop_index_if_exists(index_name, table_name)
    op.drop_column(table_name, "task_id")


def _restore_task_reference(
    table_name: str,
    *,
    foreign_key_name: str,
    indexes: tuple[tuple[str, list[str]], ...],
    comment: str,
) -> None:
    if not _table_exists(table_name):
        return
    if not _column_exists(table_name, "task_id"):
        op.add_column(
            table_name,
            sa.Column("task_id", sa.BigInteger(), nullable=True, comment=comment),
        )
        op.create_foreign_key(
            foreign_key_name,
            table_name,
            AGENT_TASK_TABLE,
            ["task_id"],
            ["id"],
            ondelete="SET NULL",
        )
    for index_name, columns in indexes:
        _create_index_if_missing(index_name, table_name, columns)


def _create_agent_task_table() -> None:
    if _table_exists(AGENT_TASK_TABLE):
        return
    op.create_table(
        AGENT_TASK_TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("task_key", sa.String(length=64), nullable=False, comment="Agent任务唯一标识"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="系统用户ID"),
        sa.Column("session_id", sa.BigInteger(), nullable=False, comment="Agent会话ID"),
        sa.Column("intent", sa.String(length=80), nullable=True, comment="识别出的意图"),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="PENDING",
            comment="任务状态",
        ),
        sa.Column("target_type", sa.String(length=50), nullable=True, comment="目标业务对象类型"),
        sa.Column("target_id", sa.BigInteger(), nullable=True, comment="目标业务对象ID"),
        sa.Column("summary", sa.Text(), nullable=True, comment="任务摘要"),
        sa.Column("input_json", sa.JSON(), nullable=True, comment="用户输入解析快照"),
        sa.Column("state_json", sa.JSON(), nullable=True, comment="LangGraph状态快照"),
        sa.Column("result_json", sa.JSON(), nullable=True, comment="任务结果快照"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
        sa.Column(
            "created_time",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "last_modified_time",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="最后修改时间",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["crm_agent_sessions.id"],
            name="fk_agent_task_session",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="CRM AI Agent任务表",
    )
    for index_name, columns, unique in (
        ("ix_crm_agent_tasks_task_key", ["task_key"], True),
        ("ix_crm_agent_tasks_team_id", ["team_id"], False),
        ("ix_crm_agent_tasks_user_id", ["user_id"], False),
        ("ix_crm_agent_tasks_session_id", ["session_id"], False),
        ("ix_crm_agent_tasks_intent", ["intent"], False),
        ("ix_crm_agent_tasks_status", ["status"], False),
        ("ix_crm_agent_tasks_target_type", ["target_type"], False),
        ("ix_crm_agent_tasks_target_id", ["target_id"], False),
        ("ix_crm_agent_tasks_created_time", ["created_time"], False),
        ("idx_agent_task_session_status", ["session_id", "status"], False),
        ("idx_agent_task_team_user_status", ["team_id", "user_id", "status"], False),
    ):
        _create_index_if_missing(index_name, AGENT_TASK_TABLE, columns, unique=unique)


def _drop_foreign_keys_for_column(table_name: str, column_name: str) -> None:
    inspector = sa.inspect(op.get_bind())
    for foreign_key in inspector.get_foreign_keys(table_name):
        if column_name not in foreign_key.get("constrained_columns", ()):
            continue
        constraint_name = foreign_key.get("name")
        if constraint_name:
            op.drop_constraint(constraint_name, table_name, type_="foreignkey")


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return column_name in {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return index_name in {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _index_exists(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)

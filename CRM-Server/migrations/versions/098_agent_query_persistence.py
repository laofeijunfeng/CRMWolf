"""Add CRM Agent query result, UI action, and review registries.

Revision ID: 098_agent_query_persistence
Revises: 097_customer_activity_agent_origins
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "098_agent_query_persistence"
down_revision: str | None = "097_customer_activity_agent_origins"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESULT_SET_TABLE = "crm_agent_query_result_sets"
ACTION_TABLE = "crm_agent_ui_actions"
REVIEW_TABLE = "crm_agent_review_cases"
MESSAGE_TABLE = "crm_agent_messages"


def upgrade() -> None:
    op.add_column(
        MESSAGE_TABLE,
        sa.Column("turn_id", sa.String(length=64), nullable=True, comment="目标协议轮次ID, 迁移完成后非空"),
    )
    op.add_column(
        MESSAGE_TABLE,
        sa.Column("client_request_id", sa.String(length=36), nullable=True, comment="用户请求幂等ID, 仅USER消息非空"),
    )
    op.add_column(
        MESSAGE_TABLE,
        sa.Column("ui_json", sa.JSON(), nullable=True, comment="crm.agent.ui.v1完整消息, 迁移完成后非空"),
    )
    op.add_column(
        MESSAGE_TABLE,
        sa.Column("diagnostics_json", sa.JSON(), nullable=True, comment="内部诊断与可观测性数据"),
    )
    op.add_column(
        MESSAGE_TABLE,
        sa.Column("last_modified_time", sa.DateTime(), nullable=True, comment="最后修改时间"),
    )
    op.execute(sa.text(f"UPDATE {MESSAGE_TABLE} SET last_modified_time = created_time"))
    op.alter_column(MESSAGE_TABLE, "last_modified_time", existing_type=sa.DateTime(), nullable=False)
    op.drop_index("idx_agent_message_session_created", table_name=MESSAGE_TABLE)
    op.create_index(
        "idx_agent_message_session_created",
        MESSAGE_TABLE,
        ["session_id", "created_time", "id"],
    )
    op.create_index(op.f(f"ix_{MESSAGE_TABLE}_turn_id"), MESSAGE_TABLE, ["turn_id"])
    op.create_unique_constraint(
        "uq_agent_message_owner_client_request",
        MESSAGE_TABLE,
        ["team_id", "user_id", "client_request_id"],
    )
    op.create_unique_constraint(
        "uq_agent_message_turn_role",
        MESSAGE_TABLE,
        ["session_id", "turn_id", "role"],
    )
    op.create_table(
        RESULT_SET_TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, comment="主键"),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="服务端签发的结果集ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="用户ID"),
        sa.Column("session_id", sa.BigInteger(), nullable=False, comment="Agent会话ID"),
        sa.Column("source_message_id", sa.BigInteger(), nullable=False, comment="生成该结果集的助手消息ID"),
        sa.Column("parent_result_set_id", sa.BigInteger(), nullable=True, comment="分页或细化查询的父结果集"),
        sa.Column("resource", sa.String(length=50), nullable=False, comment="Query Catalog资源"),
        sa.Column("query_json", sa.JSON(), nullable=False, comment="Canonical CRMQuerySpec"),
        sa.Column("ordered_entity_refs_json", sa.JSON(), nullable=False, comment="当前页有序实体引用"),
        sa.Column("page_json", sa.JSON(), nullable=False, comment="Opaque分页上下文"),
        sa.Column("row_count", sa.Integer(), nullable=False, comment="当前页实体数量"),
        sa.Column("expires_at", sa.DateTime(), nullable=False, comment="结果集失效时间"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.ForeignKeyConstraint(["session_id"], ["crm_agent_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_message_id"], ["crm_agent_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_result_set_id"],
            [f"{RESULT_SET_TABLE}.id"],
            ondelete="SET NULL",
        ),
        comment="CRM Agent不可变查询结果集注册表",
    )
    op.create_index(
        "idx_agent_query_result_set_owner_expiry",
        RESULT_SET_TABLE,
        ["team_id", "user_id", "session_id", "expires_at"],
    )
    op.create_index(
        "idx_agent_query_result_set_source_message",
        RESULT_SET_TABLE,
        ["source_message_id"],
    )
    op.create_index("idx_agent_query_result_set_parent", RESULT_SET_TABLE, ["parent_result_set_id"])
    op.create_index(op.f(f"ix_{RESULT_SET_TABLE}_public_id"), RESULT_SET_TABLE, ["public_id"], unique=True)

    op.create_table(
        ACTION_TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, comment="主键"),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="服务端签发的Action ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="用户ID"),
        sa.Column("session_id", sa.BigInteger(), nullable=False, comment="Agent会话ID"),
        sa.Column("message_id", sa.BigInteger(), nullable=False, comment="Action所属消息ID"),
        sa.Column("action_type", sa.String(length=40), nullable=False, comment="Agent UI Action类型"),
        sa.Column("target_json", sa.JSON(), nullable=False, comment="服务端签发的不可变Action目标"),
        sa.Column("consumption_mode", sa.String(length=20), nullable=False, comment="REUSABLE或ONE_SHOT"),
        sa.Column("status", sa.String(length=20), nullable=False, comment="Action状态"),
        sa.Column("expires_at", sa.DateTime(), nullable=False, comment="Action失效时间"),
        sa.Column("consumed_at", sa.DateTime(), nullable=True, comment="消费完成时间"),
        sa.Column("consumed_request_id", sa.String(length=36), nullable=True, comment="消费请求client_request_id"),
        sa.Column("result_message_id", sa.BigInteger(), nullable=True, comment="幂等重放的结果消息ID"),
        sa.Column("lock_version", sa.Integer(), nullable=False, comment="乐观锁版本"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("last_modified_time", sa.DateTime(), nullable=False, comment="最后修改时间"),
        sa.ForeignKeyConstraint(["session_id"], ["crm_agent_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["crm_agent_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["result_message_id"], ["crm_agent_messages.id"], ondelete="SET NULL"),
        comment="CRM Agent UI Action注册与消费表",
    )
    op.create_index(
        "idx_agent_ui_action_owner_status_expiry",
        ACTION_TABLE,
        ["team_id", "user_id", "session_id", "status", "expires_at"],
    )
    op.create_index("idx_agent_ui_action_message", ACTION_TABLE, ["message_id"])
    op.create_index("idx_agent_ui_action_consumed_request", ACTION_TABLE, ["consumed_request_id"])
    op.create_index(op.f(f"ix_{ACTION_TABLE}_public_id"), ACTION_TABLE, ["public_id"], unique=True)

    op.create_table(
        REVIEW_TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, comment="主键"),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="服务端签发的Review Case ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="交互归属用户ID"),
        sa.Column("session_id", sa.BigInteger(), nullable=False, comment="交互归属Agent会话ID"),
        sa.Column("customer_public_id", sa.String(length=64), nullable=False, comment="目标客户对外ID"),
        sa.Column("event_key", sa.String(length=160), nullable=False, comment="Customer Intelligence事件幂等键"),
        sa.Column("candidate_facts_json", sa.JSON(), nullable=False, comment="不可变候选事实"),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False, comment="不可变证据引用"),
        sa.Column("status", sa.String(length=20), nullable=False, comment="Review状态"),
        sa.Column("expires_at", sa.DateTime(), nullable=False, comment="Review提交截止时间"),
        sa.Column("decision_json", sa.JSON(), nullable=True, comment="Workflow验证后的用户决定"),
        sa.Column("decision_request_id", sa.String(length=36), nullable=True, comment="决定请求client_request_id"),
        sa.Column("resolved_by_user_id", sa.BigInteger(), nullable=True, comment="处理用户ID"),
        sa.Column("resolved_at", sa.DateTime(), nullable=True, comment="处理时间"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("last_modified_time", sa.DateTime(), nullable=False, comment="最后修改时间"),
        sa.ForeignKeyConstraint(["session_id"], ["crm_agent_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("team_id", "event_key", name="uq_agent_review_case_team_event"),
        comment="CRM Agent Customer Intelligence人工Review Case",
    )
    op.create_index(
        "idx_agent_review_case_owner_status_expiry",
        REVIEW_TABLE,
        ["team_id", "user_id", "session_id", "status", "expires_at"],
    )
    op.create_index("idx_agent_review_case_customer", REVIEW_TABLE, ["team_id", "customer_public_id"])
    op.create_index("idx_agent_review_case_decision_request", REVIEW_TABLE, ["decision_request_id"])
    op.create_index(op.f(f"ix_{REVIEW_TABLE}_public_id"), REVIEW_TABLE, ["public_id"], unique=True)


def downgrade() -> None:
    op.drop_table(REVIEW_TABLE)
    op.drop_table(ACTION_TABLE)
    op.drop_table(RESULT_SET_TABLE)
    op.drop_constraint("uq_agent_message_turn_role", MESSAGE_TABLE, type_="unique")
    op.drop_constraint("uq_agent_message_owner_client_request", MESSAGE_TABLE, type_="unique")
    op.drop_index(op.f(f"ix_{MESSAGE_TABLE}_turn_id"), table_name=MESSAGE_TABLE)
    op.drop_index("idx_agent_message_session_created", table_name=MESSAGE_TABLE)
    op.create_index(
        "idx_agent_message_session_created",
        MESSAGE_TABLE,
        ["session_id", "created_time"],
    )
    op.drop_column(MESSAGE_TABLE, "last_modified_time")
    op.drop_column(MESSAGE_TABLE, "diagnostics_json")
    op.drop_column(MESSAGE_TABLE, "ui_json")
    op.drop_column(MESSAGE_TABLE, "client_request_id")
    op.drop_column(MESSAGE_TABLE, "turn_id")

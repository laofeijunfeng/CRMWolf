"""create follow up task confirmation cases

Revision ID: 069_follow_up_task_confirmation_cases
Revises: 068_sales_commitment_task_tables
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "069_follow_up_task_confirmation_cases"
down_revision: str | None = "068_sales_commitment_task_tables"
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
    if not _table_exists("crm_follow_up_task_confirmation_cases"):
        op.create_table(
            "crm_follow_up_task_confirmation_cases",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("public_id", sa.String(length=64), nullable=False, comment="对外确认Case ID"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("task_id", sa.BigInteger(), nullable=False, comment="跟进任务ID"),
            sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="客户ID"),
            sa.Column("owner_id", sa.String(length=100), nullable=False, comment="确认归属人"),
            sa.Column("creator_id", sa.String(length=100), nullable=False, comment="确认创建人"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING", comment="确认状态"),
            sa.Column("suggested_action", sa.String(length=30), nullable=False, comment="建议处理动作"),
            sa.Column("confirmation_hash", sa.String(length=64), nullable=False, comment="确认Case幂等哈希"),
            sa.Column("question_text", sa.Text(), nullable=False, comment="确认问题"),
            sa.Column("source_activity_id", sa.BigInteger(), nullable=True, comment="来源客户活动ID"),
            sa.Column("source_public_id", sa.String(length=64), nullable=True, comment="来源对象对外ID"),
            sa.Column("source_plan_json", sa.JSON(), nullable=True, comment="状态迁移计划快照"),
            sa.Column("expires_at", sa.DateTime(), nullable=True, comment="确认Case过期时间"),
            sa.Column("last_prompted_at", sa.DateTime(), nullable=True, comment="最近提醒时间"),
            sa.Column("prompt_count", sa.Integer(), nullable=False, server_default="0", comment="提醒次数"),
            sa.Column(
                "unresolved_reply_count", sa.Integer(), nullable=False, server_default="0", comment="无法解析回复次数"
            ),
            sa.Column("last_unresolved_reply_text", sa.Text(), nullable=True, comment="最近一次无法解析的用户回复"),
            sa.Column(
                "last_unresolved_reply_by_id", sa.String(length=100), nullable=True, comment="最近一次无法解析回复人"
            ),
            sa.Column("last_unresolved_reply_at", sa.DateTime(), nullable=True, comment="最近一次无法解析回复时间"),
            sa.Column("resolved_action", sa.String(length=30), nullable=True, comment="用户确认后的处理动作"),
            sa.Column("resolved_due_at", sa.DateTime(), nullable=True, comment="用户确认后的延期时间"),
            sa.Column("resolved_due_at_text", sa.String(length=255), nullable=True, comment="用户确认后的原始时间表达"),
            sa.Column("resolution_text", sa.Text(), nullable=True, comment="用户原始回复"),
            sa.Column("resolved_by_id", sa.String(length=100), nullable=True, comment="确认处理人"),
            sa.Column("resolved_at", sa.DateTime(), nullable=True, comment="确认处理时间"),
            sa.Column("expired_at", sa.DateTime(), nullable=True, comment="确认Case实际过期时间"),
            sa.Column("application_status", sa.String(length=20), nullable=True, comment="确认应用状态"),
            sa.Column("application_skip_reason", sa.String(length=80), nullable=True, comment="确认应用跳过原因"),
            sa.Column("application_result_json", sa.JSON(), nullable=True, comment="确认应用结果快照"),
            sa.Column("applied_by_id", sa.String(length=100), nullable=True, comment="确认应用执行人"),
            sa.Column("applied_at", sa.DateTime(), nullable=True, comment="确认应用时间"),
            sa.Column(
                "created_time",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
                comment="创建时间",
            ),
            sa.Column(
                "updated_time",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
                comment="更新时间",
            ),
            sa.ForeignKeyConstraint(["customer_id"], ["crm_customers.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["task_id"], ["crm_follow_up_tasks.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("public_id", name="uq_follow_up_confirmation_public_id"),
            sa.UniqueConstraint("team_id", "confirmation_hash", name="uq_follow_up_task_confirmation_hash"),
            comment="跟进任务确认Case表",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index("idx_follow_up_confirmation_team", "crm_follow_up_task_confirmation_cases", ["team_id"])
        op.create_index("idx_follow_up_confirmation_task", "crm_follow_up_task_confirmation_cases", ["task_id"])
        op.create_index("idx_follow_up_confirmation_customer", "crm_follow_up_task_confirmation_cases", ["customer_id"])
        op.create_index("idx_follow_up_confirmation_owner", "crm_follow_up_task_confirmation_cases", ["owner_id"])
        op.create_index("idx_follow_up_confirmation_creator", "crm_follow_up_task_confirmation_cases", ["creator_id"])
        op.create_index("idx_follow_up_confirmation_status", "crm_follow_up_task_confirmation_cases", ["status"])
        op.create_index(
            "idx_follow_up_confirmation_action", "crm_follow_up_task_confirmation_cases", ["suggested_action"]
        )
        op.create_index(
            "idx_follow_up_confirmation_hash", "crm_follow_up_task_confirmation_cases", ["confirmation_hash"]
        )
        op.create_index(
            "idx_follow_up_confirmation_expires_at", "crm_follow_up_task_confirmation_cases", ["expires_at"]
        )
        op.create_index(
            "idx_follow_up_confirmation_activity", "crm_follow_up_task_confirmation_cases", ["source_activity_id"]
        )
        op.create_index(
            "idx_follow_up_confirmation_resolved_action", "crm_follow_up_task_confirmation_cases", ["resolved_action"]
        )
        op.create_index(
            "idx_follow_up_confirmation_resolved_by", "crm_follow_up_task_confirmation_cases", ["resolved_by_id"]
        )
        op.create_index(
            "idx_follow_up_confirmation_unresolved_by",
            "crm_follow_up_task_confirmation_cases",
            ["last_unresolved_reply_by_id"],
        )
        op.create_index(
            "idx_follow_up_confirmation_application_status",
            "crm_follow_up_task_confirmation_cases",
            ["application_status"],
        )
        op.create_index(
            "idx_follow_up_confirmation_applied_by", "crm_follow_up_task_confirmation_cases", ["applied_by_id"]
        )
        op.create_index(
            "idx_follow_up_confirmation_owner_status",
            "crm_follow_up_task_confirmation_cases",
            ["team_id", "owner_id", "status", "created_time"],
        )
        op.create_index(
            "idx_follow_up_confirmation_owner_status_expiry",
            "crm_follow_up_task_confirmation_cases",
            ["team_id", "owner_id", "status", "expires_at"],
        )
        op.create_index(
            "idx_follow_up_confirmation_task_status",
            "crm_follow_up_task_confirmation_cases",
            ["team_id", "task_id", "status"],
        )
        op.create_index(
            "idx_follow_up_confirmation_source",
            "crm_follow_up_task_confirmation_cases",
            ["team_id", "source_activity_id"],
        )

    if _table_exists("crm_follow_up_task_confirmation_prompt_deliveries"):
        return

    op.create_table(
        "crm_follow_up_task_confirmation_prompt_deliveries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="对外确认提示投递ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("case_id", sa.BigInteger(), nullable=False, comment="确认Case ID"),
        sa.Column("owner_id", sa.String(length=100), nullable=False, comment="提示接收人"),
        sa.Column("channel", sa.String(length=30), nullable=False, comment="渠道"),
        sa.Column("provider", sa.String(length=30), nullable=True, comment="渠道供应商"),
        sa.Column("agent_session_id", sa.BigInteger(), nullable=True, comment="Agent会话ID"),
        sa.Column("interaction_id", sa.String(length=80), nullable=False, comment="Agent交互ID"),
        sa.Column("prompt_key", sa.String(length=128), nullable=False, comment="提示幂等/归因键"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="SENT", comment="投递状态"),
        sa.Column("payload_json", sa.JSON(), nullable=True, comment="投递载荷快照"),
        sa.Column(
            "prompted_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="提示时间",
        ),
        sa.Column(
            "created_time",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["crm_follow_up_task_confirmation_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id", name="uq_follow_up_confirmation_prompt_public_id"),
        comment="跟进任务确认提示投递日志表",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "idx_follow_up_confirmation_prompt_team", "crm_follow_up_task_confirmation_prompt_deliveries", ["team_id"]
    )
    op.create_index(
        "idx_follow_up_confirmation_prompt_case", "crm_follow_up_task_confirmation_prompt_deliveries", ["case_id"]
    )
    op.create_index(
        "idx_follow_up_confirmation_prompt_owner", "crm_follow_up_task_confirmation_prompt_deliveries", ["owner_id"]
    )
    op.create_index(
        "idx_follow_up_confirmation_prompt_channel", "crm_follow_up_task_confirmation_prompt_deliveries", ["channel"]
    )
    op.create_index(
        "idx_follow_up_confirmation_prompt_provider", "crm_follow_up_task_confirmation_prompt_deliveries", ["provider"]
    )
    op.create_index(
        "idx_follow_up_confirmation_prompt_session_id",
        "crm_follow_up_task_confirmation_prompt_deliveries",
        ["agent_session_id"],
    )
    op.create_index(
        "idx_follow_up_confirmation_prompt_interaction",
        "crm_follow_up_task_confirmation_prompt_deliveries",
        ["interaction_id"],
    )
    op.create_index(
        "idx_follow_up_confirmation_prompt_key", "crm_follow_up_task_confirmation_prompt_deliveries", ["prompt_key"]
    )
    op.create_index(
        "idx_follow_up_confirmation_prompt_status", "crm_follow_up_task_confirmation_prompt_deliveries", ["status"]
    )
    op.create_index(
        "idx_follow_up_confirmation_prompted_at", "crm_follow_up_task_confirmation_prompt_deliveries", ["prompted_at"]
    )
    op.create_index(
        "idx_follow_up_confirmation_prompt_owner_time",
        "crm_follow_up_task_confirmation_prompt_deliveries",
        ["team_id", "owner_id", "prompted_at"],
    )
    op.create_index(
        "idx_follow_up_confirmation_prompt_case_time",
        "crm_follow_up_task_confirmation_prompt_deliveries",
        ["team_id", "case_id", "prompted_at"],
    )
    op.create_index(
        "idx_follow_up_confirmation_prompt_session",
        "crm_follow_up_task_confirmation_prompt_deliveries",
        ["team_id", "agent_session_id", "created_time"],
    )


def downgrade() -> None:
    if _table_exists("crm_follow_up_task_confirmation_prompt_deliveries"):
        op.drop_table("crm_follow_up_task_confirmation_prompt_deliveries")
    if _table_exists("crm_follow_up_task_confirmation_cases"):
        op.drop_table("crm_follow_up_task_confirmation_cases")

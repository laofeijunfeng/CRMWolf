"""Add versioned customer profile projection and current pointer.

Revision ID: 110_customer_profile_projection_tables
Revises: 109_agent_ui_action_root_context_role
Create Date: 2026-08-28
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "110_customer_profile_projection_tables"
down_revision: str | None = "109_agent_ui_action_root_context_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_customer_profile_projection_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="档案版本对外ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="客户ID"),
        sa.Column("schema_version", sa.String(length=20), nullable=False, comment="档案Schema版本"),
        sa.Column("profile_version", sa.BigInteger(), nullable=False, comment="客户内单调递增版本号"),
        sa.Column("publication_status", sa.String(length=20), nullable=False, comment="发布状态"),
        sa.Column("current_situation_json", sa.JSON(), nullable=False, comment="当前情况"),
        sa.Column("current_journeys_json", sa.JSON(), nullable=False, comment="当前业务旅程"),
        sa.Column("important_changes_json", sa.JSON(), nullable=False, comment="重要变化"),
        sa.Column("long_term_context_json", sa.JSON(), nullable=False, comment="长期情况"),
        sa.Column("follow_up_process_json", sa.JSON(), nullable=False, comment="跟进过程"),
        sa.Column("recorded_follow_ups_json", sa.JSON(), nullable=False, comment="已记录后续事项"),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False, comment="证据引用"),
        sa.Column("source_watermark_json", sa.JSON(), nullable=False, comment="来源水位"),
        sa.Column("source_watermark_hash", sa.CHAR(length=64), nullable=False, comment="来源水位哈希"),
        sa.Column("fact_watermark", sa.BigInteger(), nullable=False, server_default="0", comment="事实水位"),
        sa.Column("journey_watermark", sa.BigInteger(), nullable=False, server_default="0", comment="旅程水位"),
        sa.Column("task_watermark", sa.BigInteger(), nullable=False, server_default="0", comment="任务水位"),
        sa.Column("commitment_watermark", sa.BigInteger(), nullable=False, server_default="0", comment="承诺水位"),
        sa.Column("source_event_key", sa.String(length=120), nullable=True, comment="主要触发事件"),
        sa.Column("run_id", sa.BigInteger(), nullable=True, comment="生成运行ID"),
        sa.Column("graph_version", sa.String(length=40), nullable=False, comment="Graph/规则版本"),
        sa.Column("content_hash", sa.CHAR(length=64), nullable=False, comment="内容哈希"),
        sa.Column("generated_at", sa.DateTime(), nullable=False, comment="生成时间"),
        sa.Column("published_at", sa.DateTime(), nullable=True, comment="发布时间"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.ForeignKeyConstraint(["customer_id"], ["crm_customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["crm_customer_intelligence_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("team_id", "customer_id", "profile_version", name="uq_customer_profile_projection_version"),
        sa.UniqueConstraint(
            "team_id",
            "customer_id",
            "content_hash",
            "source_watermark_hash",
            name="uq_customer_profile_projection_content_watermark",
        ),
        comment="客户档案不可变投影版本表",
    )
    op.create_index(
        "idx_customer_profile_projection_team_customer",
        "crm_customer_profile_projection_versions",
        ["team_id", "customer_id"],
    )
    op.create_index(
        "idx_customer_profile_projection_lookup",
        "crm_customer_profile_projection_versions",
        ["team_id", "customer_id", "publication_status", "profile_version"],
    )
    op.create_index(
        "idx_customer_profile_projection_created",
        "crm_customer_profile_projection_versions",
        ["team_id", "customer_id", "created_time"],
    )
    op.create_index("idx_customer_profile_projection_run", "crm_customer_profile_projection_versions", ["run_id"])
    op.create_index(
        "idx_customer_profile_projection_event",
        "crm_customer_profile_projection_versions",
        ["source_event_key"],
    )
    op.create_index(
        "idx_customer_profile_projection_published",
        "crm_customer_profile_projection_versions",
        ["published_at"],
    )

    op.create_table(
        "crm_customer_profile_current",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="客户ID"),
        sa.Column("current_profile_version_id", sa.BigInteger(), nullable=True, comment="当前档案版本ID"),
        sa.Column("profile_status", sa.String(length=20), nullable=False, comment="档案状态"),
        sa.Column("last_successful_version", sa.BigInteger(), nullable=True, comment="最近成功版本号"),
        sa.Column("last_successful_published_at", sa.DateTime(), nullable=True, comment="最近成功发布时间"),
        sa.Column("latest_source_watermark_json", sa.JSON(), nullable=False, comment="已知来源水位"),
        sa.Column("latest_fact_watermark", sa.BigInteger(), nullable=False, server_default="0", comment="已知事实水位"),
        sa.Column(
            "latest_journey_watermark", sa.BigInteger(), nullable=False, server_default="0", comment="已知旅程水位"
        ),
        sa.Column("latest_task_watermark", sa.BigInteger(), nullable=False, server_default="0", comment="已知任务水位"),
        sa.Column(
            "latest_commitment_watermark", sa.BigInteger(), nullable=False, server_default="0", comment="已知承诺水位"
        ),
        sa.Column("stale_reason", sa.String(length=255), nullable=True, comment="新鲜度说明"),
        sa.Column("active_run_id", sa.BigInteger(), nullable=True, comment="当前活跃运行ID"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.ForeignKeyConstraint(["customer_id"], ["crm_customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["current_profile_version_id"], ["crm_customer_profile_projection_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["active_run_id"], ["crm_customer_intelligence_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "customer_id", name="uq_customer_profile_current_team_customer"),
        comment="客户档案当前指针和新鲜度表",
    )
    op.create_index("idx_customer_profile_current_team", "crm_customer_profile_current", ["team_id"])
    op.create_index(
        "idx_customer_profile_current_status",
        "crm_customer_profile_current",
        ["team_id", "profile_status", "updated_time"],
    )
    op.create_index(
        "idx_customer_profile_current_version", "crm_customer_profile_current", ["current_profile_version_id"]
    )
    op.create_index("idx_customer_profile_current_run", "crm_customer_profile_current", ["active_run_id"])

    op.add_column(
        "crm_sales_commitments",
        sa.Column("deal_journey_id", sa.BigInteger(), nullable=True, comment="业务旅程ID"),
    )
    op.create_foreign_key(
        "fk_sales_commitment_deal_journey",
        "crm_sales_commitments",
        "crm_customer_deal_journeys",
        ["deal_journey_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_sales_commitment_customer_journey",
        "crm_sales_commitments",
        ["team_id", "customer_id", "deal_journey_id", "status"],
    )
    op.add_column(
        "crm_follow_up_tasks",
        sa.Column("deal_journey_id", sa.BigInteger(), nullable=True, comment="业务旅程ID"),
    )
    op.create_foreign_key(
        "fk_follow_up_task_deal_journey",
        "crm_follow_up_tasks",
        "crm_customer_deal_journeys",
        ["deal_journey_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_follow_up_task_customer_journey",
        "crm_follow_up_tasks",
        ["team_id", "customer_id", "deal_journey_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_customer_profile_projection_published",
        table_name="crm_customer_profile_projection_versions",
    )
    op.drop_index("idx_follow_up_task_customer_journey", table_name="crm_follow_up_tasks")
    op.drop_constraint("fk_follow_up_task_deal_journey", "crm_follow_up_tasks", type_="foreignkey")
    op.drop_column("crm_follow_up_tasks", "deal_journey_id")
    op.drop_index("idx_sales_commitment_customer_journey", table_name="crm_sales_commitments")
    op.drop_constraint("fk_sales_commitment_deal_journey", "crm_sales_commitments", type_="foreignkey")
    op.drop_column("crm_sales_commitments", "deal_journey_id")
    op.drop_table("crm_customer_profile_current")
    op.drop_table("crm_customer_profile_projection_versions")

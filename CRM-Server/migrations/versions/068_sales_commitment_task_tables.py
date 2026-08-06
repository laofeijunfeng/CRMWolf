"""create sales commitment and follow up task tables

Revision ID: 068_sales_commitment_task_tables
Revises: 067_customer_activity_owner_id
Create Date: 2026-08-06

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "068_sales_commitment_task_tables"
down_revision: str | None = "067_customer_activity_owner_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"), {"table_name": table_name}).all()
        return bool(rows)

    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
    """), {"table_name": table_name}).scalar() > 0


def _drop_table_if_exists(table_name: str) -> None:
    if _table_exists(table_name):
        op.drop_table(table_name)


def upgrade() -> None:
    if not _table_exists("crm_sales_commitments"):
        op.create_table(
            "crm_sales_commitments",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("public_id", sa.String(length=64), nullable=False, comment="对外承诺ID"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="客户ID"),
            sa.Column("owner_id", sa.String(length=100), nullable=False, comment="承诺归属人"),
            sa.Column("creator_id", sa.String(length=100), nullable=False, comment="承诺创建人"),
            sa.Column("title", sa.String(length=255), nullable=False, comment="承诺标题"),
            sa.Column("content", sa.Text(), nullable=False, comment="承诺内容"),
            sa.Column("commitment_type", sa.String(length=50), nullable=False, server_default="FOLLOW_UP", comment="承诺类型"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="OPEN", comment="承诺状态"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0", comment="抽取置信度"),
            sa.Column("source_type", sa.String(length=50), nullable=False, comment="来源类型"),
            sa.Column("source_key", sa.String(length=128), nullable=False, comment="幂等来源键"),
            sa.Column("source_activity_id", sa.BigInteger(), nullable=True, comment="来源客户活动ID"),
            sa.Column("source_public_id", sa.String(length=64), nullable=True, comment="来源对象对外ID"),
            sa.Column("due_at", sa.DateTime(), nullable=True, comment="承诺到期时间"),
            sa.Column("due_at_text", sa.String(length=255), nullable=True, comment="原始时间表达"),
            sa.Column("due_at_granularity", sa.String(length=20), nullable=False, server_default="UNKNOWN", comment="到期时间粒度"),
            sa.Column("due_at_timezone", sa.String(length=64), nullable=False, server_default="Asia/Shanghai", comment="到期时间业务时区"),
            sa.Column("evidence_json", sa.JSON(), nullable=True, comment="抽取证据和上下文"),
            sa.Column("commitment_hash", sa.String(length=64), nullable=False, comment="承诺幂等哈希"),
            sa.Column("created_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
            sa.Column("updated_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
            sa.ForeignKeyConstraint(["customer_id"], ["crm_customers.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["source_activity_id"], ["crm_customer_activities.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("public_id", name="uq_sales_commitment_public_id"),
            sa.UniqueConstraint("team_id", "source_type", "source_key", "commitment_hash", name="uq_sales_commitment_source_hash"),
            comment="销售承诺表",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index("idx_sales_commitment_team", "crm_sales_commitments", ["team_id"])
        op.create_index("idx_sales_commitment_customer", "crm_sales_commitments", ["customer_id"])
        op.create_index("idx_sales_commitment_owner", "crm_sales_commitments", ["owner_id"])
        op.create_index("idx_sales_commitment_creator", "crm_sales_commitments", ["creator_id"])
        op.create_index("idx_sales_commitment_type", "crm_sales_commitments", ["commitment_type"])
        op.create_index("idx_sales_commitment_status", "crm_sales_commitments", ["status"])
        op.create_index("idx_sales_commitment_source_type", "crm_sales_commitments", ["source_type"])
        op.create_index("idx_sales_commitment_source_key", "crm_sales_commitments", ["source_key"])
        op.create_index("idx_sales_commitment_activity", "crm_sales_commitments", ["source_activity_id"])
        op.create_index("idx_sales_commitment_due_at", "crm_sales_commitments", ["due_at"])
        op.create_index("idx_sales_commitment_hash", "crm_sales_commitments", ["commitment_hash"])
        op.create_index("idx_sales_commitment_owner_status_due", "crm_sales_commitments", ["team_id", "owner_id", "status", "due_at"])
        op.create_index("idx_sales_commitment_customer_status_due", "crm_sales_commitments", ["team_id", "customer_id", "status", "due_at"])

    if not _table_exists("crm_follow_up_tasks"):
        op.create_table(
            "crm_follow_up_tasks",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("public_id", sa.String(length=64), nullable=False, comment="对外跟进任务ID"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="客户ID"),
            sa.Column("commitment_id", sa.BigInteger(), nullable=True, comment="关联承诺ID"),
            sa.Column("owner_id", sa.String(length=100), nullable=False, comment="任务归属人"),
            sa.Column("creator_id", sa.String(length=100), nullable=False, comment="任务创建人"),
            sa.Column("title", sa.String(length=255), nullable=False, comment="任务标题"),
            sa.Column("description", sa.Text(), nullable=True, comment="任务描述"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="OPEN", comment="任务状态"),
            sa.Column("due_at", sa.DateTime(), nullable=False, comment="任务到期时间"),
            sa.Column("due_at_text", sa.String(length=255), nullable=True, comment="原始时间表达"),
            sa.Column("due_at_granularity", sa.String(length=20), nullable=False, server_default="DATETIME", comment="到期时间粒度"),
            sa.Column("due_at_timezone", sa.String(length=64), nullable=False, server_default="Asia/Shanghai", comment="到期时间业务时区"),
            sa.Column("source_type", sa.String(length=50), nullable=False, comment="来源类型"),
            sa.Column("source_key", sa.String(length=128), nullable=False, comment="幂等来源键"),
            sa.Column("source_activity_id", sa.BigInteger(), nullable=True, comment="来源客户活动ID"),
            sa.Column("source_public_id", sa.String(length=64), nullable=True, comment="来源对象对外ID"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0", comment="抽取置信度"),
            sa.Column("evidence_json", sa.JSON(), nullable=True, comment="抽取证据和上下文"),
            sa.Column("task_hash", sa.String(length=64), nullable=False, comment="任务幂等哈希"),
            sa.Column("completed_at", sa.DateTime(), nullable=True, comment="完成时间"),
            sa.Column("cancelled_at", sa.DateTime(), nullable=True, comment="取消时间"),
            sa.Column("created_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
            sa.Column("updated_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
            sa.ForeignKeyConstraint(["customer_id"], ["crm_customers.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["commitment_id"], ["crm_sales_commitments.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["source_activity_id"], ["crm_customer_activities.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("public_id", name="uq_follow_up_task_public_id"),
            sa.UniqueConstraint("team_id", "source_type", "source_key", "task_hash", name="uq_follow_up_task_source_hash"),
            comment="客户跟进任务表",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index("idx_follow_up_task_team", "crm_follow_up_tasks", ["team_id"])
        op.create_index("idx_follow_up_task_customer", "crm_follow_up_tasks", ["customer_id"])
        op.create_index("idx_follow_up_task_commitment", "crm_follow_up_tasks", ["commitment_id"])
        op.create_index("idx_follow_up_task_owner", "crm_follow_up_tasks", ["owner_id"])
        op.create_index("idx_follow_up_task_creator", "crm_follow_up_tasks", ["creator_id"])
        op.create_index("idx_follow_up_task_status", "crm_follow_up_tasks", ["status"])
        op.create_index("idx_follow_up_task_due_at", "crm_follow_up_tasks", ["due_at"])
        op.create_index("idx_follow_up_task_source_type", "crm_follow_up_tasks", ["source_type"])
        op.create_index("idx_follow_up_task_source_key", "crm_follow_up_tasks", ["source_key"])
        op.create_index("idx_follow_up_task_activity", "crm_follow_up_tasks", ["source_activity_id"])
        op.create_index("idx_follow_up_task_hash", "crm_follow_up_tasks", ["task_hash"])
        op.create_index("idx_follow_up_task_owner_status_due", "crm_follow_up_tasks", ["team_id", "owner_id", "status", "due_at"])
        op.create_index("idx_follow_up_task_customer_status_due", "crm_follow_up_tasks", ["team_id", "customer_id", "status", "due_at"])
        op.create_index("idx_follow_up_task_source", "crm_follow_up_tasks", ["team_id", "source_type", "source_key"])

    if not _table_exists("crm_follow_up_task_events"):
        op.create_table(
            "crm_follow_up_task_events",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("public_id", sa.String(length=64), nullable=False, comment="对外任务事件ID"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("task_id", sa.BigInteger(), nullable=False, comment="跟进任务ID"),
            sa.Column("event_type", sa.String(length=30), nullable=False, comment="事件类型"),
            sa.Column("actor_id", sa.String(length=100), nullable=True, comment="触发人"),
            sa.Column("source_type", sa.String(length=50), nullable=True, comment="来源类型"),
            sa.Column("source_activity_id", sa.BigInteger(), nullable=True, comment="来源客户活动ID"),
            sa.Column("source_public_id", sa.String(length=64), nullable=True, comment="来源对象对外ID"),
            sa.Column("previous_status", sa.String(length=20), nullable=True, comment="变更前状态"),
            sa.Column("new_status", sa.String(length=20), nullable=True, comment="变更后状态"),
            sa.Column("payload_json", sa.JSON(), nullable=True, comment="事件载荷"),
            sa.Column("created_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
            sa.ForeignKeyConstraint(["task_id"], ["crm_follow_up_tasks.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("public_id", name="uq_follow_up_task_event_public_id"),
            comment="客户跟进任务事件表",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index("idx_follow_up_task_event_public_id", "crm_follow_up_task_events", ["public_id"])
        op.create_index("idx_follow_up_task_event_team", "crm_follow_up_task_events", ["team_id"])
        op.create_index("idx_follow_up_task_event_task", "crm_follow_up_task_events", ["task_id"])
        op.create_index("idx_follow_up_task_event_type", "crm_follow_up_task_events", ["event_type"])
        op.create_index("idx_follow_up_task_event_actor", "crm_follow_up_task_events", ["actor_id"])
        op.create_index("idx_follow_up_task_event_source_type", "crm_follow_up_task_events", ["source_type"])
        op.create_index("idx_follow_up_task_event_activity", "crm_follow_up_task_events", ["source_activity_id"])
        op.create_index("idx_follow_up_task_event_created", "crm_follow_up_task_events", ["created_time"])
        op.create_index("idx_follow_up_task_event_task_time", "crm_follow_up_task_events", ["task_id", "created_time"])
        op.create_index("idx_follow_up_task_event_source", "crm_follow_up_task_events", ["team_id", "source_type", "source_activity_id"])

    if not _table_exists("crm_follow_up_task_projection_runs"):
        op.create_table(
            "crm_follow_up_task_projection_runs",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("public_id", sa.String(length=64), nullable=False, comment="对外投影运行ID"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("trigger_type", sa.String(length=50), nullable=False, comment="投影触发类型"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="RUNNING", comment="投影状态"),
            sa.Column("source_type", sa.String(length=50), nullable=False, comment="来源类型"),
            sa.Column("source_key", sa.String(length=128), nullable=False, comment="幂等来源键"),
            sa.Column("source_activity_id", sa.BigInteger(), nullable=True, comment="来源客户活动ID"),
            sa.Column("source_public_id", sa.String(length=64), nullable=True, comment="来源对象对外ID"),
            sa.Column("actor_id", sa.String(length=100), nullable=True, comment="触发人"),
            sa.Column("skip_reason", sa.String(length=80), nullable=True, comment="跳过原因"),
            sa.Column("input_snapshot_hash", sa.String(length=64), nullable=True, comment="输入快照哈希"),
            sa.Column("projection_hash", sa.String(length=64), nullable=True, comment="投影结果哈希"),
            sa.Column("task_count", sa.Integer(), nullable=False, server_default="0", comment="涉及任务数量"),
            sa.Column("commitment_count", sa.Integer(), nullable=False, server_default="0", comment="涉及承诺数量"),
            sa.Column("created_task_ids_json", sa.JSON(), nullable=True, comment="新建任务内部ID列表"),
            sa.Column("updated_task_ids_json", sa.JSON(), nullable=True, comment="更新任务内部ID列表"),
            sa.Column("cancelled_task_ids_json", sa.JSON(), nullable=True, comment="取消任务内部ID列表"),
            sa.Column("created_commitment_ids_json", sa.JSON(), nullable=True, comment="新建承诺内部ID列表"),
            sa.Column("updated_commitment_ids_json", sa.JSON(), nullable=True, comment="更新承诺内部ID列表"),
            sa.Column("error_message", sa.Text(), nullable=True, comment="错误摘要"),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1", comment="尝试次数"),
            sa.Column("duration_ms", sa.Integer(), nullable=True, comment="耗时毫秒"),
            sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="开始时间"),
            sa.Column("finished_at", sa.DateTime(), nullable=True, comment="结束时间"),
            sa.Column("created_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
            sa.Column("updated_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("public_id", name="uq_follow_up_projection_public_id"),
            comment="客户跟进任务投影运行表",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index("idx_follow_up_projection_team", "crm_follow_up_task_projection_runs", ["team_id"])
        op.create_index("idx_follow_up_projection_trigger", "crm_follow_up_task_projection_runs", ["trigger_type"])
        op.create_index("idx_follow_up_projection_status_only", "crm_follow_up_task_projection_runs", ["status"])
        op.create_index("idx_follow_up_projection_source_type", "crm_follow_up_task_projection_runs", ["source_type"])
        op.create_index("idx_follow_up_projection_source_key", "crm_follow_up_task_projection_runs", ["source_key"])
        op.create_index("idx_follow_up_projection_activity", "crm_follow_up_task_projection_runs", ["source_activity_id"])
        op.create_index("idx_follow_up_projection_actor", "crm_follow_up_task_projection_runs", ["actor_id"])
        op.create_index("idx_follow_up_projection_skip", "crm_follow_up_task_projection_runs", ["skip_reason"])
        op.create_index("idx_follow_up_projection_input_hash", "crm_follow_up_task_projection_runs", ["input_snapshot_hash"])
        op.create_index("idx_follow_up_projection_hash", "crm_follow_up_task_projection_runs", ["projection_hash"])
        op.create_index("idx_follow_up_projection_source", "crm_follow_up_task_projection_runs", ["team_id", "source_type", "source_key", "created_time"])
        op.create_index("idx_follow_up_projection_status", "crm_follow_up_task_projection_runs", ["team_id", "status", "created_time"])


def downgrade() -> None:
    _drop_table_if_exists("crm_follow_up_task_projection_runs")
    _drop_table_if_exists("crm_follow_up_task_events")
    _drop_table_if_exists("crm_follow_up_tasks")
    _drop_table_if_exists("crm_sales_commitments")

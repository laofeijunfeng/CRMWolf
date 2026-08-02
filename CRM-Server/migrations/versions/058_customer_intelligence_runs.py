"""customer intelligence runs

Revision ID: 058_customer_intelligence_runs
Revises: 057_customer_facts
Create Date: 2026-08-02

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "058_customer_intelligence_runs"
down_revision: str | None = "057_customer_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
    """), {"table_name": table_name}).scalar() > 0


def upgrade() -> None:
    if _table_exists("crm_customer_intelligence_runs"):
        return

    op.create_table(
        "crm_customer_intelligence_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("run_key", sa.String(length=64), nullable=False, comment="运行幂等键"),
        sa.Column("request_id", sa.String(length=120), nullable=False, comment="刷新请求ID"),
        sa.Column("event_key", sa.String(length=120), nullable=False, comment="客户智能事件键"),
        sa.Column("event_json", sa.JSON(), nullable=True, comment="客户智能事件快照"),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="租户ID，当前与团队ID一致"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="客户ID"),
        sa.Column("actor_id", sa.String(length=80), nullable=True, comment="触发人ID"),
        sa.Column("trigger_type", sa.String(length=60), nullable=False, comment="触发类型"),
        sa.Column("scope", sa.String(length=20), nullable=False, comment="刷新范围"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING", comment="运行状态"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0", comment="已尝试次数"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3", comment="最大尝试次数"),
        sa.Column("last_duration_ms", sa.Integer(), nullable=True, comment="最近一次运行耗时毫秒"),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True, comment="下次可重试时间"),
        sa.Column("started_time", sa.DateTime(), nullable=True, comment="开始时间"),
        sa.Column("finished_time", sa.DateTime(), nullable=True, comment="结束时间"),
        sa.Column("route", sa.String(length=50), nullable=True, comment="Graph 路由"),
        sa.Column("result_json", sa.JSON(), nullable=True, comment="Graph 结果摘要"),
        sa.Column("visible_trace_json", sa.JSON(), nullable=True, comment="用户可见执行轨迹"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
        sa.Column("created_time", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_key", name="uq_customer_intelligence_run_key"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="客户智能 LangGraph 运行审计表",
    )
    op.create_index("ix_crm_customer_intelligence_runs_actor_id", "crm_customer_intelligence_runs", ["actor_id"])
    op.create_index("ix_crm_customer_intelligence_runs_customer_id", "crm_customer_intelligence_runs", ["customer_id"])
    op.create_index("ix_crm_customer_intelligence_runs_event_key", "crm_customer_intelligence_runs", ["event_key"])
    op.create_index("ix_crm_customer_intelligence_runs_finished_time", "crm_customer_intelligence_runs", ["finished_time"])
    op.create_index("ix_crm_customer_intelligence_runs_next_retry_at", "crm_customer_intelligence_runs", ["next_retry_at"])
    op.create_index("ix_crm_customer_intelligence_runs_request_id", "crm_customer_intelligence_runs", ["request_id"])
    op.create_index("ix_crm_customer_intelligence_runs_route", "crm_customer_intelligence_runs", ["route"])
    op.create_index("ix_crm_customer_intelligence_runs_run_key", "crm_customer_intelligence_runs", ["run_key"])
    op.create_index("ix_crm_customer_intelligence_runs_scope", "crm_customer_intelligence_runs", ["scope"])
    op.create_index("ix_crm_customer_intelligence_runs_started_time", "crm_customer_intelligence_runs", ["started_time"])
    op.create_index("ix_crm_customer_intelligence_runs_status", "crm_customer_intelligence_runs", ["status"])
    op.create_index("ix_crm_customer_intelligence_runs_team_id", "crm_customer_intelligence_runs", ["team_id"])
    op.create_index("ix_crm_customer_intelligence_runs_tenant_id", "crm_customer_intelligence_runs", ["tenant_id"])
    op.create_index("ix_crm_customer_intelligence_runs_trigger_type", "crm_customer_intelligence_runs", ["trigger_type"])
    op.create_index("idx_customer_intelligence_run_customer", "crm_customer_intelligence_runs", ["team_id", "customer_id", "created_time"])
    op.create_index("idx_customer_intelligence_run_retry", "crm_customer_intelligence_runs", ["status", "next_retry_at"])
    op.create_index("idx_customer_intelligence_run_event", "crm_customer_intelligence_runs", ["team_id", "event_key"])


def downgrade() -> None:
    if _table_exists("crm_customer_intelligence_runs"):
        op.drop_table("crm_customer_intelligence_runs")

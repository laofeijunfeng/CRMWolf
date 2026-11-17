"""Create Assistant 2.0 follow-up projection jobs."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "164_assistant_follow_up_projection_jobs"
down_revision: str | None = "163_contract_amount_changes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "crm_assistant_follow_up_projection_jobs"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="对外任务ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("activity_id", sa.BigInteger(), nullable=False, comment="客户活动ID"),
        sa.Column("activity_revision", sa.Integer(), nullable=False, comment="活动修订号"),
        sa.Column("trigger_type", sa.String(length=80), nullable=False, comment="投影触发类型"),
        sa.Column("actor_id", sa.String(length=100), nullable=True, comment="触发用户ID"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="QUEUED", comment="持久任务状态"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0", comment="执行尝试次数"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True, comment="下次重试时间"),
        sa.Column("lease_token", sa.String(length=64), nullable=True, comment="执行租约令牌"),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True, comment="租约过期时间"),
        sa.Column("result_json", sa.JSON(), nullable=True, comment="投影结果"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="最近错误"),
        sa.Column("created_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.Column("started_at", sa.DateTime(), nullable=True, comment="首次开始时间"),
        sa.Column("finished_at", sa.DateTime(), nullable=True, comment="完成时间"),
        sa.ForeignKeyConstraint(["activity_id"], ["crm_customer_activities.id"], name="fk_assistant_follow_up_projection_jobs_activity"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id", name="uq_assistant_follow_up_projection_jobs_public_id"),
        sa.UniqueConstraint("team_id", "activity_id", "activity_revision", "trigger_type", name="uq_assistant_follow_up_projection_job_identity"),
        comment="Assistant 2.0 客户活动跟进任务投影持久任务表",
    )
    op.create_index("idx_assistant_follow_up_projection_jobs_team", _TABLE, ["team_id", "activity_id"])
    op.create_index("idx_assistant_follow_up_projection_jobs_status", _TABLE, ["status", "next_attempt_at", "lease_expires_at"])
    op.create_index("idx_assistant_follow_up_projection_jobs_lease", _TABLE, ["lease_token"])


def downgrade() -> None:
    op.drop_index("idx_assistant_follow_up_projection_jobs_lease", table_name=_TABLE)
    op.drop_index("idx_assistant_follow_up_projection_jobs_status", table_name=_TABLE)
    op.drop_index("idx_assistant_follow_up_projection_jobs_team", table_name=_TABLE)
    op.drop_table(_TABLE)

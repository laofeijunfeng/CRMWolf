"""add customer intelligence review runtime state

Revision ID: 099_customer_intelligence_review_runtime
Revises: 098_agent_query_persistence
Create Date: 2026-08-21
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

_RUN_STATUS_PRIORITY = {
    "SUCCESS": 7,
    "REVIEW_REQUIRED": 6,
    "RUNNING": 5,
    "RETRY_PENDING": 4,
    "PENDING": 3,
    "FAILED": 2,
    "CANCELLED": 1,
}


def _datetime_sort_key(value: datetime | None) -> tuple[int, int, int, int, int, int, int]:
    if value is None:
        return (0, 0, 0, 0, 0, 0, 0)
    return (
        int(value.year),
        int(value.month),
        int(value.day),
        int(value.hour),
        int(value.minute),
        int(value.second),
        int(value.microsecond),
    )

revision = "099_customer_intelligence_review_runtime"
down_revision = "098_agent_query_persistence"
branch_labels = None
depends_on = None


def _deduplicate_customer_intelligence_events() -> None:
    bind = op.get_bind()
    runs = sa.table(
        "crm_customer_intelligence_runs",
        sa.column("id", sa.BigInteger()),
        sa.column("team_id", sa.BigInteger()),
        sa.column("event_key", sa.String()),
        sa.column("status", sa.String()),
        sa.column("updated_time", sa.DateTime()),
        sa.column("finished_time", sa.DateTime()),
    )
    duplicate_events = bind.execute(
        sa.select(runs.c.team_id, runs.c.event_key)
        .group_by(runs.c.team_id, runs.c.event_key)
        .having(sa.func.count(runs.c.id) > 1)
    ).all()
    for team_id, event_key in duplicate_events:
        rows = bind.execute(
            sa.select(
                runs.c.id,
                runs.c.status,
                runs.c.updated_time,
                runs.c.finished_time,
            ).where(
                runs.c.team_id == team_id,
                runs.c.event_key == event_key,
            )
        ).all()
        survivor = max(
            rows,
            key=lambda row: (
                _RUN_STATUS_PRIORITY.get(str(row.status), 0),
                row.finished_time is not None,
                _datetime_sort_key(row.updated_time or row.finished_time),
                int(row.id),
            ),
        )
        duplicate_ids = [int(row.id) for row in rows if int(row.id) != int(survivor.id)]
        if duplicate_ids:
            bind.execute(sa.delete(runs).where(runs.c.id.in_(duplicate_ids)))


def upgrade() -> None:
    op.add_column(
        "crm_customer_intelligence_runs",
        sa.Column("review_case_public_id", sa.String(length=64), nullable=True, comment="待处理客户事实复核Case对外ID"),
    )
    op.create_index(
        "ix_crm_customer_intelligence_runs_review_case_public_id",
        "crm_customer_intelligence_runs",
        ["review_case_public_id"],
    )
    op.create_index(
        "idx_customer_intelligence_run_review",
        "crm_customer_intelligence_runs",
        ["team_id", "review_case_public_id"],
    )
    _deduplicate_customer_intelligence_events()
    op.drop_index("idx_customer_intelligence_run_event", table_name="crm_customer_intelligence_runs")
    op.create_unique_constraint(
        "uq_customer_intelligence_run_team_event",
        "crm_customer_intelligence_runs",
        ["team_id", "event_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_customer_intelligence_run_team_event",
        "crm_customer_intelligence_runs",
        type_="unique",
    )
    op.create_index(
        "idx_customer_intelligence_run_event",
        "crm_customer_intelligence_runs",
        ["team_id", "event_key"],
    )
    op.drop_index("idx_customer_intelligence_run_review", table_name="crm_customer_intelligence_runs")
    op.drop_index(
        "ix_crm_customer_intelligence_runs_review_case_public_id",
        table_name="crm_customer_intelligence_runs",
    )
    op.drop_column("crm_customer_intelligence_runs", "review_case_public_id")

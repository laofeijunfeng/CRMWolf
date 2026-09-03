"""Cut over unfinished customer activities to the durable Workflow pipeline.

Revision ID: 122_customer_activity_cutover
Revises: 121_customer_opportunity_suggestion_jobs
Create Date: 2026-09-02

The application cutover is intentionally data-driven and rerunnable:

* completed historical activities are left untouched;
* activities still in PENDING/PROCESSING/GENERATING are handed to exactly one
  CUTOVER_MIGRATION CustomerActivityAIJob;
* old post-commit work created before activity finalization is terminalized as
  replaced, while post-commit work for finalized activities is preserved;
* task rows for deleted activities remain as evidence and are skipped; and
* one durable evidence row records the watermark and cumulative counters.

No old in-process task or LangGraph checkpoint is resumed by this migration.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

from app.utils.public_id import generate_public_id
from app.utils.time import business_now

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.engine import Connection

revision: str = "122_customer_activity_cutover"
down_revision: str | None = "121_customer_opportunity_suggestion_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVITY_TABLE = "crm_customer_activities"
AI_JOB_TABLE = "crm_customer_activity_ai_jobs"
POST_COMMIT_TABLE = "crm_customer_activity_post_commit_jobs"
EVIDENCE_TABLE = "crm_customer_activity_cutover_runs"
RUN_KEY = "customer_activity_cutover:122"
TERMINAL_STATUSES = ("COMPLETED", "SKIPPED", "EXHAUSTED")
ACTIVE_PROCESSING_STATUSES = ("PENDING", "PROCESSING")
ACTIVE_EFFECTIVENESS_STATUSES = ("PENDING", "GENERATING")


class CutoverMigrationResult(dict[str, Any]):
    """JSON-friendly counters returned by the data-migration helper."""


def _evidence_table_definition() -> tuple[sa.Column[Any], ...]:
    return (
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, comment="主键"),
        sa.Column("run_key", sa.String(length=100), nullable=False, comment="迁移运行幂等键"),
        sa.Column("cutover_watermark", sa.DateTime(), nullable=False, comment="切换水位时间"),
        sa.Column("status", sa.String(length=20), nullable=False, comment="迁移状态"),
        sa.Column("active_activity_count", sa.Integer(), nullable=False, server_default="0", comment="接管活动数"),
        sa.Column("pending_activity_count", sa.Integer(), nullable=False, server_default="0", comment="PENDING活动数"),
        sa.Column(
            "processing_activity_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="PROCESSING活动数",
        ),
        sa.Column(
            "generating_activity_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="GENERATING活动数",
        ),
        sa.Column(
            "agent_activity_reclassified_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="被切换接管的历史Agent活动数",
        ),
        sa.Column(
            "ai_jobs_created_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="新建AIJob数",
        ),
        sa.Column(
            "ai_jobs_deleted_skipped_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="已删除活动AIJob跳过数",
        ),
        sa.Column(
            "post_commit_replaced_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="被AIJob替代的PostCommitJob数",
        ),
        sa.Column(
            "post_commit_preserved_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="保留待恢复PostCommitJob数",
        ),
        sa.Column(
            "post_commit_deleted_skipped_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="已删除活动PostCommitJob跳过数",
        ),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.UniqueConstraint("run_key", name="uq_customer_activity_cutover_run_key"),
        sa.CheckConstraint("status IN ('RUNNING', 'COMPLETED')", name="ck_customer_activity_cutover_run_status"),
    )


def _is_bind(bind: object) -> bool:
    return hasattr(bind, "execute")


def _json_value(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _database_now(bind: Connection) -> datetime:
    value = bind.execute(text("SELECT CURRENT_TIMESTAMP")).scalar_one()
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    # SQLite returns a string for CURRENT_TIMESTAMP while MySQL normally
    # returns a datetime.  business_now keeps the fallback in business time.
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=None)
    except ValueError:
        return business_now()


def _load_or_create_evidence(
    bind: Connection, *, requested_watermark: datetime | None
) -> tuple[dict[str, Any], datetime]:
    row = bind.execute(
        text(f"SELECT * FROM {EVIDENCE_TABLE} WHERE run_key = :run_key"),
        {"run_key": RUN_KEY},
    ).mappings().first()
    if row is not None:
        evidence = dict(row)
        watermark = evidence["cutover_watermark"]
        if isinstance(watermark, str):
            watermark = datetime.fromisoformat(watermark).replace(tzinfo=None)
        elif isinstance(watermark, datetime) and watermark.tzinfo:
            watermark = watermark.replace(tzinfo=None)
        evidence["cutover_watermark"] = watermark
        return evidence, watermark

    watermark = requested_watermark or _database_now(bind)
    now = business_now()
    bind.execute(
        text(
            f"""INSERT INTO {EVIDENCE_TABLE}
            (run_key, cutover_watermark, status, created_time, updated_time)
            VALUES (:run_key, :cutover_watermark, 'RUNNING', :created_time, :updated_time)"""
        ),
        {
            "run_key": RUN_KEY,
            "cutover_watermark": watermark,
            "created_time": now,
            "updated_time": now,
        },
    )
    return {
        "run_key": RUN_KEY,
        "cutover_watermark": watermark,
        "status": "RUNNING",
        "active_activity_count": 0,
        "pending_activity_count": 0,
        "processing_activity_count": 0,
        "generating_activity_count": 0,
        "agent_activity_reclassified_count": 0,
        "ai_jobs_created_count": 0,
        "ai_jobs_deleted_skipped_count": 0,
        "post_commit_replaced_count": 0,
        "post_commit_preserved_count": 0,
        "post_commit_deleted_skipped_count": 0,
    }, watermark


def _increment(evidence: dict[str, Any], key: str, amount: int = 1) -> None:
    evidence[key] = int(evidence.get(key) or 0) + amount


def _write_evidence(bind: Connection, evidence: dict[str, Any], *, status: str) -> None:
    now = business_now()
    values = {
        "status": status,
        "updated_time": now,
        **{
            key: int(evidence.get(key) or 0)
            for key in (
                "active_activity_count",
                "pending_activity_count",
                "processing_activity_count",
                "generating_activity_count",
                "agent_activity_reclassified_count",
                "ai_jobs_created_count",
                "ai_jobs_deleted_skipped_count",
                "post_commit_replaced_count",
                "post_commit_preserved_count",
                "post_commit_deleted_skipped_count",
            )
        },
        "run_key": RUN_KEY,
    }
    bind.execute(
        text(
            f"""UPDATE {EVIDENCE_TABLE}
               SET status = :status,
                   active_activity_count = :active_activity_count,
                   pending_activity_count = :pending_activity_count,
                   processing_activity_count = :processing_activity_count,
                   generating_activity_count = :generating_activity_count,
                   agent_activity_reclassified_count = :agent_activity_reclassified_count,
                   ai_jobs_created_count = :ai_jobs_created_count,
                   ai_jobs_deleted_skipped_count = :ai_jobs_deleted_skipped_count,
                   post_commit_replaced_count = :post_commit_replaced_count,
                   post_commit_preserved_count = :post_commit_preserved_count,
                   post_commit_deleted_skipped_count = :post_commit_deleted_skipped_count,
                   updated_time = :updated_time
             WHERE run_key = :run_key"""
        ),
        values,
    )


def _create_ai_job(bind: Connection, activity: dict[str, Any], *, watermark: datetime) -> bool:
    identity = {
        "team_id": int(activity["team_id"]),
        "activity_id": int(activity["id"]),
        "activity_revision": int(activity["activity_revision"] or 1),
        "job_type": "STRUCTURE_AND_EVALUATE",
    }
    existing = bind.execute(
        text(
            f"""SELECT id FROM {AI_JOB_TABLE}
             WHERE team_id = :team_id AND activity_id = :activity_id
               AND activity_revision = :activity_revision AND job_type = :job_type"""
        ),
        identity,
    ).first()
    if existing is not None:
        return False

    run_id = (
        f"customer_activity_ai:cutover:{identity['team_id']}:{identity['activity_id']}"
        f":{identity['activity_revision']}"
    )
    bind.execute(
        text(
            f"""INSERT INTO {AI_JOB_TABLE}
            (public_id, team_id, activity_id, activity_revision, job_type,
             submission_source, status, attempt_count, run_id, graph_thread_id,
             created_time, updated_time)
            VALUES (:public_id, :team_id, :activity_id, :activity_revision, :job_type,
                    'CUTOVER_MIGRATION', 'QUEUED', 0, :run_id, :graph_thread_id,
                    :created_time, :updated_time)"""
        ),
        {
            **identity,
            "public_id": generate_public_id("caij"),
            "run_id": run_id,
            "graph_thread_id": run_id,
            "created_time": watermark,
            "updated_time": watermark,
        },
    )
    return True


def _mark_skipped(bind: Connection, *, table: str, row: dict[str, Any], reason: str, watermark: datetime) -> None:
    result_json = _json_value(row.get("result_json"))
    result_json["skip_reason"] = reason
    result_json["cutover_migration"] = True
    if row.get("error_message"):
        result_json.setdefault("previous_error", row["error_message"])
    statement = text(
        f"""UPDATE {table}
           SET status = 'SKIPPED', result_json = :result_json,
               error_message = :error_message, next_attempt_at = NULL,
               lease_token = NULL, lease_expires_at = NULL,
               finished_at = :finished_at, updated_time = :updated_time
         WHERE id = :id AND status NOT IN ('COMPLETED', 'SKIPPED', 'EXHAUSTED')"""
    ).bindparams(sa.bindparam("result_json", type_=sa.JSON))
    bind.execute(
        statement,
        {
            "result_json": result_json,
            "error_message": reason,
            "finished_at": watermark,
            "updated_time": watermark,
            "id": int(row["id"]),
        },
    )


def _migrate_unfinished_activities(bind: Connection, evidence: dict[str, Any], *, watermark: datetime) -> None:
    activities = bind.execute(
        text(
            f"""SELECT id, team_id, activity_revision, submission_source,
                       processing_status, effectiveness_status, created_time
                  FROM {ACTIVITY_TABLE}
                 WHERE created_time <= :watermark
                   AND (processing_status IN ('PENDING', 'PROCESSING')
                        OR effectiveness_status IN ('PENDING', 'GENERATING'))
                 ORDER BY team_id, id"""
        ),
        {"watermark": watermark},
    ).mappings().all()
    for activity_row in activities:
        activity = dict(activity_row)
        _increment(evidence, "active_activity_count")
        if activity.get("processing_status") == "PENDING":
            _increment(evidence, "pending_activity_count")
        if activity.get("processing_status") == "PROCESSING":
            _increment(evidence, "processing_activity_count")
        if activity.get("effectiveness_status") == "GENERATING":
            _increment(evidence, "generating_activity_count")

        # A historical Agent write could be left unfinished by the old
        # in-process path.  Reclassify that exceptional row at the cutover
        # boundary so the canonical AIJob finalization gate can safely take it
        # over without treating it as a new Agent double-score.
        if activity.get("submission_source") == "AGENT":
            bind.execute(
                text(
                    f"UPDATE {ACTIVITY_TABLE} SET submission_source = 'CUTOVER_MIGRATION', "
                    "updated_time = :updated_time WHERE id = :id"
                ),
                {"updated_time": watermark, "id": int(activity["id"])},
            )
            _increment(evidence, "agent_activity_reclassified_count")

        if _create_ai_job(bind, activity, watermark=watermark):
            _increment(evidence, "ai_jobs_created_count")


def _migrate_orphan_ai_jobs(bind: Connection, evidence: dict[str, Any], *, watermark: datetime) -> None:
    rows = bind.execute(
        text(
            f"""SELECT job.id, job.result_json, job.error_message
                  FROM {AI_JOB_TABLE} job
             LEFT JOIN {ACTIVITY_TABLE} activity
                    ON activity.team_id = job.team_id AND activity.id = job.activity_id
                 WHERE job.created_time <= :watermark
                   AND job.status NOT IN ('COMPLETED', 'SKIPPED', 'EXHAUSTED')
                   AND activity.id IS NULL"""
        ),
        {"watermark": watermark},
    ).mappings().all()
    for row in rows:
        _mark_skipped(
            bind,
            table=AI_JOB_TABLE,
            row=dict(row),
            reason="SOURCE_ACTIVITY_DELETED",
            watermark=watermark,
        )
        _increment(evidence, "ai_jobs_deleted_skipped_count")


def _migrate_post_commit_jobs(bind: Connection, evidence: dict[str, Any], *, watermark: datetime) -> None:
    rows = bind.execute(
        text(
            f"""SELECT job.id, job.team_id, job.activity_id, job.result_json,
                       job.error_message, activity.id AS source_activity_id,
                       activity.processing_status, activity.effectiveness_status
                  FROM {POST_COMMIT_TABLE} job
             LEFT JOIN {ACTIVITY_TABLE} activity
                    ON activity.team_id = job.team_id AND activity.id = job.activity_id
                 WHERE job.created_time <= :watermark
                   AND job.status NOT IN ('COMPLETED', 'SKIPPED', 'EXHAUSTED')"""
        ),
        {"watermark": watermark},
    ).mappings().all()
    for row in rows:
        row_dict = dict(row)
        if row_dict.get("source_activity_id") is None:
            _mark_skipped(
                bind,
                table=POST_COMMIT_TABLE,
                row=row_dict,
                reason="SOURCE_ACTIVITY_DELETED",
                watermark=watermark,
            )
            _increment(evidence, "post_commit_deleted_skipped_count")
            continue

        unfinished = row_dict.get("processing_status") in ACTIVE_PROCESSING_STATUSES or row_dict.get(
            "effectiveness_status"
        ) in ACTIVE_EFFECTIVENESS_STATUSES
        if unfinished:
            _mark_skipped(
                bind,
                table=POST_COMMIT_TABLE,
                row=row_dict,
                reason="REPLACED_BY_ACTIVITY_AI_JOB",
                watermark=watermark,
            )
            _increment(evidence, "post_commit_replaced_count")
        else:
            _increment(evidence, "post_commit_preserved_count")


def run_customer_activity_cutover(
    bind: Connection,
    *,
    watermark: datetime | None = None,
) -> CutoverMigrationResult:
    """Run the idempotent historical cutover against an Alembic connection.

    The helper is intentionally separate from ``upgrade()`` so it can be
    exercised on a disposable database and rerun during a deployment dry run.
    The caller owns the transaction; the Alembic upgrade runs it in the same
    migration transaction where the target dialect supports transactional DML.
    """

    if not _is_bind(bind):
        return CutoverMigrationResult({"status": "SKIPPED_NO_BIND"})

    evidence, effective_watermark = _load_or_create_evidence(
        bind,
        requested_watermark=watermark,
    )
    # A completed fixed-key cutover is a one-shot operation.  Returning the
    # recorded evidence instead of scanning again keeps counters stable and
    # prevents a later dry-run from changing rows created after the cutover.
    if evidence.get("status") == "COMPLETED":
        return CutoverMigrationResult(evidence)

    _migrate_unfinished_activities(bind, evidence, watermark=effective_watermark)
    _migrate_orphan_ai_jobs(bind, evidence, watermark=effective_watermark)
    _migrate_post_commit_jobs(bind, evidence, watermark=effective_watermark)
    _write_evidence(bind, evidence, status="COMPLETED")
    evidence["status"] = "COMPLETED"
    evidence["cutover_watermark"] = effective_watermark
    return CutoverMigrationResult(evidence)


def upgrade() -> None:
    op.create_table(EVIDENCE_TABLE, *_evidence_table_definition(), comment="客户活动 Workflow 切换迁移证据表")
    bind = op.get_bind()
    if bind is not None:
        run_customer_activity_cutover(bind)


def downgrade() -> None:
    op.drop_table(EVIDENCE_TABLE)

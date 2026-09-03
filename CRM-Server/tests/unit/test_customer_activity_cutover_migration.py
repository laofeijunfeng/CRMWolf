"""Behavior tests for the one-time customer-activity cutover migration."""

from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import CustomerActivityCutoverRun
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_ai_job import CustomerActivityAIJob
from app.models.customer_activity_post_commit_job import CustomerActivityPostCommitJob


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


if TYPE_CHECKING:
    from types import ModuleType


def _load_migration() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "122_customer_activity_cutover.py"
    spec = importlib.util.spec_from_file_location("customer_activity_cutover_122", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerActivity.__table__,
            CustomerActivityAIJob.__table__,
            CustomerActivityPostCommitJob.__table__,
        ],
    )
    migration = _load_migration()
    evidence = migration.EVIDENCE_TABLE
    evidence_table = migration.sa.Table(
        evidence,
        migration.sa.MetaData(),
        *migration._evidence_table_definition(),
    )
    evidence_table.create(engine)
    return engine, sessionmaker(bind=engine)()


def _activity(
    *,
    team_id: int,
    source: str,
    processing: str,
    effectiveness: str,
    created: datetime,
    score: int | None = None,
):
    return CustomerActivity(
        team_id=team_id,
        customer_id=None,
        activity_kind="PHONE_FOLLOW_UP",
        source_content="客户活动",
        submission_source=source,
        processing_status=processing,
        effectiveness_status=effectiveness,
        effectiveness_score=score,
        occurred_at=created,
        creator_id="u1",
        owner_id="u1",
        created_time=created,
        updated_time=created,
        activity_revision=1,
    )


def _post_commit(*, team_id: int, activity_id: int, status: str, created: datetime):
    return CustomerActivityPostCommitJob(
        team_id=team_id,
        activity_id=activity_id,
        activity_revision=1,
        trigger_type="ACTIVITY_CREATED",
        status=status,
        run_id=f"run-{activity_id}-{status}",
        graph_thread_id=f"thread-{activity_id}-{status}",
        created_time=created,
        updated_time=created,
    )


def test_cutover_only_claims_unfinished_rows_preserves_completed_and_is_rerunnable():
    migration = _load_migration()
    engine, db = _session()
    watermark = datetime(2026, 9, 2, 12, 0, 0)
    try:
        completed = _activity(
            team_id=1,
            source="FORM",
            processing="COMPLETED",
            effectiveness="COMPLETED",
            created=datetime(2026, 9, 1, 10, 0),
            score=88,
        )
        pending = _activity(
            team_id=1,
            source="FORM",
            processing="PENDING",
            effectiveness="PENDING",
            created=datetime(2026, 9, 1, 11, 0),
        )
        processing = _activity(
            team_id=1,
            source="FORM",
            processing="PROCESSING",
            effectiveness="GENERATING",
            created=datetime(2026, 9, 1, 12, 0),
        )
        old_agent = _activity(
            team_id=1,
            source="AGENT",
            processing="PENDING",
            effectiveness="PENDING",
            created=datetime(2026, 9, 1, 13, 0),
        )
        after_watermark = _activity(
            team_id=1,
            source="FORM",
            processing="PENDING",
            effectiveness="PENDING",
            created=datetime(2026, 9, 2, 13, 0),
        )
        db.add_all([completed, pending, processing, old_agent, after_watermark])
        db.flush()

        completed_post_commit = _post_commit(
            team_id=1, activity_id=completed.id, status="QUEUED", created=datetime(2026, 9, 1, 10, 1)
        )
        pending_post_commit = _post_commit(
            team_id=1, activity_id=pending.id, status="QUEUED", created=datetime(2026, 9, 1, 11, 1)
        )
        deleted_post_commit = _post_commit(
            team_id=1, activity_id=999999, status="RUNNING", created=datetime(2026, 9, 1, 11, 2)
        )
        db.add_all([completed_post_commit, pending_post_commit, deleted_post_commit])
        db.commit()

        first = migration.run_customer_activity_cutover(db.connection(), watermark=watermark)
        db.commit()

        assert first["active_activity_count"] == 3
        assert first["pending_activity_count"] == 2
        assert first["processing_activity_count"] == 1
        assert first["generating_activity_count"] == 1
        assert first["agent_activity_reclassified_count"] == 1
        assert first["ai_jobs_created_count"] == 3
        assert first["post_commit_replaced_count"] == 1
        assert first["post_commit_preserved_count"] == 1
        assert first["post_commit_deleted_skipped_count"] == 1

        db.expire_all()
        assert db.query(CustomerActivityAIJob).count() == 3
        assert (
            db.query(CustomerActivityAIJob)
            .filter(CustomerActivityAIJob.submission_source == "CUTOVER_MIGRATION")
            .count()
            == 3
        )
        assert db.get(CustomerActivity, old_agent.id).submission_source == "CUTOVER_MIGRATION"
        assert db.get(CustomerActivity, completed.id).effectiveness_score == 88
        assert db.get(CustomerActivity, after_watermark.id).processing_status == "PENDING"
        assert db.get(CustomerActivityPostCommitJob, completed_post_commit.id).status == "QUEUED"
        assert db.get(CustomerActivityPostCommitJob, pending_post_commit.id).status == "SKIPPED"
        assert (
            db.get(CustomerActivityPostCommitJob, pending_post_commit.id).error_message == "REPLACED_BY_ACTIVITY_AI_JOB"
        )
        assert db.get(CustomerActivityPostCommitJob, deleted_post_commit.id).status == "SKIPPED"
        assert db.get(CustomerActivityPostCommitJob, deleted_post_commit.id).error_message == "SOURCE_ACTIVITY_DELETED"

        post_cutover = _activity(
            team_id=1,
            source="FORM",
            processing="PENDING",
            effectiveness="PENDING",
            created=datetime(2026, 9, 2, 12, 1),
        )
        db.add(post_cutover)
        db.commit()

        second = migration.run_customer_activity_cutover(db.connection(), watermark=datetime(2026, 9, 3, 12, 0))
        db.commit()
        assert second["status"] == "COMPLETED"
        assert second["cutover_watermark"] == watermark
        assert second["active_activity_count"] == 3
        assert second["ai_jobs_created_count"] == 3
        assert db.query(CustomerActivityAIJob).count() == 3
        assert db.query(CustomerActivityAIJob).filter(CustomerActivityAIJob.activity_id == post_cutover.id).count() == 0
        assert (
            db.query(CustomerActivityPostCommitJob).filter(CustomerActivityPostCommitJob.status == "SKIPPED").count()
            == 2
        )
    finally:
        db.close()
        engine.dispose()


def test_cutover_skips_orphan_ai_job_and_records_evidence():
    migration = _load_migration()
    engine, db = _session()
    watermark = datetime(2026, 9, 2, 12, 0, 0)
    try:
        orphan = CustomerActivityAIJob(
            team_id=1,
            activity_id=404,
            activity_revision=1,
            job_type="STRUCTURE_AND_EVALUATE",
            submission_source="CUTOVER_MIGRATION",
            status="QUEUED",
            attempt_count=0,
            run_id="orphan-run",
            graph_thread_id="orphan-thread",
            created_time=datetime(2026, 9, 1, 10, 0),
            updated_time=datetime(2026, 9, 1, 10, 0),
        )
        db.add(orphan)
        db.commit()

        result = migration.run_customer_activity_cutover(db.connection(), watermark=watermark)
        db.commit()

        db.expire_all()
        assert db.get(CustomerActivityAIJob, orphan.id).status == "SKIPPED"
        assert db.get(CustomerActivityAIJob, orphan.id).error_message == "SOURCE_ACTIVITY_DELETED"
        evidence = db.execute(
            migration.sa.text(
                f"SELECT ai_jobs_deleted_skipped_count, status FROM {migration.EVIDENCE_TABLE} WHERE run_key = :run_key"
            ),
            {"run_key": migration.RUN_KEY},
        ).one()
        assert result["ai_jobs_deleted_skipped_count"] == 1
        assert evidence.ai_jobs_deleted_skipped_count == 1
        assert evidence.status == "COMPLETED"
    finally:
        db.close()
        engine.dispose()


def test_migration_122_creates_cutover_evidence_table_and_delegates_to_helper(monkeypatch):
    migration = _load_migration()

    class _Operations:
        def __init__(self):
            self.calls = []

        def create_table(self, *args, **kwargs):
            self.calls.append(("create_table", args, kwargs))

        def get_bind(self):
            return None

        def drop_table(self, *args, **kwargs):
            self.calls.append(("drop_table", args, kwargs))

    operations = _Operations()
    migration.op = operations
    migration.upgrade()

    create_table = operations.calls[0]
    assert create_table[0] == "create_table"
    assert create_table[1][0] == migration.EVIDENCE_TABLE
    names = {item.name for item in create_table[1][1:] if hasattr(item, "name")}
    assert {
        "run_key",
        "cutover_watermark",
        "active_activity_count",
        "ai_jobs_created_count",
        "post_commit_replaced_count",
        "post_commit_preserved_count",
    } <= names
    assert create_table[2]["comment"] == "客户活动 Workflow 切换迁移证据表"


def test_cutover_evidence_model_is_registered_with_shared_model_registry():
    from app.models import CustomerActivityCutoverRun as RegisteredCutoverRun

    assert RegisteredCutoverRun is CustomerActivityCutoverRun
    assert RegisteredCutoverRun.__tablename__ == "crm_customer_activity_cutover_runs"

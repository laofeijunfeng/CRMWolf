"""A worker must execute an accepted legacy job without prewarming its module."""

from datetime import datetime
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.customer_activity_post_commit_job import (
    CustomerActivityPostCommitJob,
    CustomerActivityPostCommitJobStatus,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.mark.asyncio
async def test_cold_worker_executes_and_completes_accepted_legacy_job(monkeypatch):
    module = import_module("app.services.customer_activity_post_commit_job_service")
    workflow_module = import_module("app.services.customer_activity_post_commit_workflow")
    # Patch the dependency at its definition, not via the service's lazy
    # attribute: a dotted patch there would prewarm the missing global.
    run_workflow = AsyncMock(return_value={})
    monkeypatch.setattr(workflow_module.customer_activity_post_commit_workflow, "run", run_workflow)
    monkeypatch.delitem(module.__dict__, "customer_activity_post_commit_workflow", raising=False)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[CustomerActivityPostCommitJob.__table__])
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(module, "SessionLocal", sessions)
    monkeypatch.setattr(
        module.customer_activity_crud,
        "get_by_id",
        lambda db, activity_id, team_id: SimpleNamespace(submission_source="FORM", activity_revision=7),
    )
    monkeypatch.setattr(module.customer_activity_post_commit_operation_projector, "project_job", lambda db, job: None)
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: SimpleNamespace(
            CUSTOMER_ACTIVITY_POST_COMMIT_LEASE_SECONDS=60,
            CUSTOMER_ACTIVITY_POST_COMMIT_MAX_ATTEMPTS=5,
            CUSTOMER_ACTIVITY_POST_COMMIT_RETRY_BASE_SECONDS=1,
        ),
    )
    try:
        with sessions() as db:
            db.add(
                CustomerActivityPostCommitJob(
                    public_id="pcj_cold_worker",
                    team_id=2,
                    activity_id=212,
                    activity_revision=7,
                    trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
                    actor_id="9",
                    status=CustomerActivityPostCommitJobStatus.QUEUED,
                    attempt_count=0,
                    run_id="cold-worker-run",
                    graph_thread_id="cold-worker-thread",
                    created_time=datetime(2026, 8, 14, 10, 0),
                    updated_time=datetime(2026, 8, 14, 10, 0),
                )
            )
            db.commit()

        result = await module.CustomerActivityPostCommitJobService().run(
            module.CustomerActivityPostCommitJobRequest(job_public_id="pcj_cold_worker", team_id=2)
        )

        assert result["success"] is True
        run_workflow.assert_awaited_once_with(
            activity_id=212,
            team_id=2,
            expected_activity_revision=7,
            trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
            actor_id="9",
            run_id="cold-worker-run",
            thread_id="cold-worker-thread",
        )
        with sessions() as db:
            persisted = db.query(CustomerActivityPostCommitJob).filter_by(public_id="pcj_cold_worker").one()
            assert persisted.status == CustomerActivityPostCommitJobStatus.COMPLETED
            assert persisted.result_json == result
            assert persisted.error_message is None
    finally:
        engine.dispose()

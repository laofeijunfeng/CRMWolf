from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.customer_enrichment_reconciliation_service import (
    CustomerEnrichmentReconciliationResult,
)
from app.tasks import customer_enrichment_reconciliation as module


class FakeDB:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class FakeService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def reconcile_once(self, db, **kwargs):
        del db
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return CustomerEnrichmentReconciliationResult(
            scanned=2,
            jobs_created=1,
            gates_released=1,
            gates_cancelled=2,
            refreshes_repaired=0,
            errors=0,
            next_customer_id=11,
            next_orphan_job_id=17,
            dry_run=bool(kwargs.get("dry_run")),
        )


@pytest.mark.asyncio
async def test_scheduler_reconcile_once_commits_and_returns_cursor(monkeypatch):
    db = FakeDB()
    service = FakeService()
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: SimpleNamespace(CUSTOMER_INITIAL_ENRICHMENT_RECONCILIATION_BATCH_SIZE=50),
    )
    scheduler = module.CustomerEnrichmentReconciliationScheduler(
        reconciliation_service=service,
        session_factory=lambda: db,
    )

    result = await scheduler.reconcile_once(
        limit=7,
        after_customer_id=3,
        after_orphan_job_id=5,
    )

    assert result["jobs_created"] == 1
    assert result["gates_cancelled"] == 2
    assert result["next_customer_id"] == 11
    assert result["next_orphan_job_id"] == 17
    assert service.calls == [
        {
            "team_id": None,
            "limit": 7,
            "after_customer_id": 3,
            "after_orphan_job_id": 5,
            "dry_run": False,
        }
    ]
    assert db.committed is True
    assert db.rolled_back is False
    assert db.closed is True


@pytest.mark.asyncio
async def test_scheduler_dry_run_does_not_commit(monkeypatch):
    db = FakeDB()
    service = FakeService()
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: SimpleNamespace(CUSTOMER_INITIAL_ENRICHMENT_RECONCILIATION_BATCH_SIZE=50),
    )
    scheduler = module.CustomerEnrichmentReconciliationScheduler(
        reconciliation_service=service,
        session_factory=lambda: db,
    )

    result = await scheduler.reconcile_once(team_id=2, dry_run=True)

    assert result["dry_run"] is True
    assert service.calls == [
        {
            "team_id": 2,
            "limit": 50,
            "after_customer_id": None,
            "after_orphan_job_id": None,
            "dry_run": True,
        }
    ]
    assert db.committed is False
    assert db.rolled_back is False
    assert db.closed is True


@pytest.mark.asyncio
async def test_scheduler_rolls_back_and_closes_on_failure(monkeypatch):
    db = FakeDB()
    service = FakeService(RuntimeError("boom"))
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: SimpleNamespace(CUSTOMER_INITIAL_ENRICHMENT_RECONCILIATION_BATCH_SIZE=50),
    )
    scheduler = module.CustomerEnrichmentReconciliationScheduler(
        reconciliation_service=service,
        session_factory=lambda: db,
    )

    with pytest.raises(RuntimeError, match="boom"):
        await scheduler.reconcile_once()

    assert db.committed is False
    assert db.rolled_back is True
    assert db.closed is True



@pytest.mark.asyncio
async def test_scheduler_advances_and_resets_customer_and_orphan_cursors_independently(monkeypatch):
    scheduler = module.CustomerEnrichmentReconciliationScheduler(
        reconciliation_service=FakeService(),
        session_factory=FakeDB,
    )
    scheduler._running = True
    scheduler._after_customer_id = 3
    scheduler._after_orphan_job_id = 5
    results = iter(
        [
            {
                "jobs_created": 0,
                "gates_released": 0,
                "gates_cancelled": 0,
                "refreshes_repaired": 0,
                "errors": 0,
                "next_customer_id": 11,
                "next_orphan_job_id": None,
            },
            {
                "jobs_created": 0,
                "gates_released": 0,
                "gates_cancelled": 0,
                "refreshes_repaired": 0,
                "errors": 0,
                "next_customer_id": None,
                "next_orphan_job_id": 17,
            },
        ]
    )
    calls = []

    async def reconcile_once(**kwargs):
        calls.append(kwargs)
        result = next(results)
        if len(calls) == 2:
            scheduler._running = False
        return result

    monkeypatch.setattr(scheduler, "reconcile_once", reconcile_once)
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: SimpleNamespace(
            CUSTOMER_INITIAL_ENRICHMENT_RECONCILIATION_INTERVAL_SECONDS=60,
            CUSTOMER_INITIAL_ENRICHMENT_RECONCILIATION_BATCH_SIZE=50,
        ),
    )
    monkeypatch.setattr(module.asyncio, "sleep", lambda seconds: _noop())

    await scheduler._run_scheduler()

    assert calls == [
        {"limit": 50, "after_customer_id": 3, "after_orphan_job_id": 5},
        {"limit": 50, "after_customer_id": 11, "after_orphan_job_id": None},
    ]
    assert scheduler._after_customer_id is None
    assert scheduler._after_orphan_job_id == 17


async def _noop():
    return None

def test_scheduler_start_and_stop_respect_configuration(monkeypatch):
    created = []

    class FakeTask:
        def __init__(self) -> None:
            self.cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

    task = FakeTask()
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: SimpleNamespace(CUSTOMER_INITIAL_ENRICHMENT_RECONCILIATION_ENABLED=True),
    )
    monkeypatch.setattr(module.asyncio, "create_task", lambda coro: created.append(coro) or task)
    scheduler = module.CustomerEnrichmentReconciliationScheduler(
        reconciliation_service=FakeService(),
        session_factory=FakeDB,
    )

    scheduler.start()
    scheduler.stop()

    assert scheduler._running is False
    assert len(created) == 1
    created[0].close()
    assert task.cancelled is True

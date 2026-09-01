from types import SimpleNamespace

import pytest

from app.services.customer_intelligence_reconciliation_service import (
    CustomerIntelligenceReconciliationResult,
)
from app.tasks import customer_intelligence_reconciliation as module


class FakeDB:
    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class FakeService:
    def __init__(self):
        self.calls = []

    def reconcile_once(self, db, **kwargs):
        self.calls.append(kwargs)
        return CustomerIntelligenceReconciliationResult(
            success=True,
            scanned=2,
            stale=1,
            scheduled=1,
            skipped=1,
            errors=0,
            customer_ids=[10, 11],
            scheduled_customer_ids=[10],
            error_customer_ids=[],
            next_customer_id=11,
        )


@pytest.mark.asyncio
async def test_scheduler_reconcile_once_commits_and_returns_cursor(monkeypatch):
    db = FakeDB()
    service = FakeService()
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: SimpleNamespace(CUSTOMER_INTELLIGENCE_RECONCILIATION_BATCH_SIZE=50),
    )
    scheduler = module.CustomerIntelligenceReconciliationScheduler(
        reconciliation_service=service,
        session_factory=lambda: db,
    )

    result = await scheduler.reconcile_once(limit=7, after_customer_id=3)

    assert result["success"] is True
    assert result["scheduled"] == 1
    assert result["next_customer_id"] == 11
    assert service.calls == [{"team_id": None, "limit": 7, "after_customer_id": 3, "dry_run": False}]
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
        lambda: SimpleNamespace(CUSTOMER_INTELLIGENCE_RECONCILIATION_BATCH_SIZE=50),
    )
    scheduler = module.CustomerIntelligenceReconciliationScheduler(
        reconciliation_service=service,
        session_factory=lambda: db,
    )

    await scheduler.reconcile_once(dry_run=True)

    assert db.committed is False
    assert db.closed is True

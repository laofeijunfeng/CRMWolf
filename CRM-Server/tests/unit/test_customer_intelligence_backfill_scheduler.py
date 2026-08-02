from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app.services.customer_intelligence_refresh_service import CustomerIntelligenceHistoricalBackfillResult
from app.tasks.customer_intelligence_backfill import CustomerIntelligenceBackfillScheduler


@dataclass(frozen=True)
class FakeSettings:
    CUSTOMER_INTELLIGENCE_BACKFILL_ENABLED: bool = True
    CUSTOMER_INTELLIGENCE_BACKFILL_INTERVAL_SECONDS: int = 300
    CUSTOMER_INTELLIGENCE_BACKFILL_BATCH_SIZE: int = 20


class FakeSession:
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


class FakeRefreshService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.retry_calls: list[dict[str, object]] = []

    async def trigger_missing_historical_backfill(
        self,
        db,
        *,
        team_id: int | None = None,
        limit: int = 20,
        schedule_runs: bool = True,
    ) -> CustomerIntelligenceHistoricalBackfillResult:
        self.calls.append({
            "db": db,
            "team_id": team_id,
            "limit": limit,
            "schedule_runs": schedule_runs,
        })
        return CustomerIntelligenceHistoricalBackfillResult(
            success=True,
            request_id="historical-backfill-test",
            scope="full",
            total=1,
            scheduled=1,
            customer_ids=[101],
        )

    async def run_due_retries(self, *, team_id: int | None = None, limit: int = 20) -> dict[str, object]:
        self.retry_calls.append({"team_id": team_id, "limit": limit})
        return {
            "success": True,
            "total": 1,
            "succeeded": 1,
            "failed": 0,
            "results": [{"success": True}],
        }


@pytest.mark.asyncio
async def test_customer_intelligence_backfill_scheduler_runs_missing_backfill_with_configured_limit(
    monkeypatch,
) -> None:
    fake_session = FakeSession()
    refresh_service = FakeRefreshService()
    scheduler = CustomerIntelligenceBackfillScheduler(refresh_service=refresh_service)
    monkeypatch.setattr(
        "app.tasks.customer_intelligence_backfill.get_settings",
        lambda: FakeSettings(CUSTOMER_INTELLIGENCE_BACKFILL_BATCH_SIZE=12),
    )
    monkeypatch.setattr(
        "app.tasks.customer_intelligence_backfill.SessionLocal",
        lambda: fake_session,
    )

    result = await scheduler.backfill_once()

    assert result["success"] is True
    assert result["scheduled"] == 1
    assert result["profile_vector_reindexed"] == 0
    assert result["profile_vector_customer_ids"] == []
    assert refresh_service.calls == [{
        "db": fake_session,
        "team_id": None,
        "limit": 12,
        "schedule_runs": False,
    }]
    assert refresh_service.retry_calls == [{"team_id": None, "limit": 1}]
    assert fake_session.committed is True
    assert fake_session.rolled_back is False
    assert fake_session.closed is True


def test_customer_intelligence_backfill_scheduler_does_not_start_when_disabled(monkeypatch) -> None:
    scheduler = CustomerIntelligenceBackfillScheduler(refresh_service=FakeRefreshService())
    monkeypatch.setattr(
        "app.tasks.customer_intelligence_backfill.get_settings",
        lambda: FakeSettings(CUSTOMER_INTELLIGENCE_BACKFILL_ENABLED=False),
    )

    scheduler.start()

    assert scheduler._running is False
    assert scheduler._task is None


def test_customer_intelligence_backfill_scheduler_does_not_start_twice(monkeypatch) -> None:
    created_coroutines = []

    def fake_create_task(coro):
        created_coroutines.append(coro)
        return SimpleNamespace(cancel=lambda: None)

    scheduler = CustomerIntelligenceBackfillScheduler(refresh_service=FakeRefreshService())
    monkeypatch.setattr(
        "app.tasks.customer_intelligence_backfill.get_settings",
        lambda: FakeSettings(),
    )
    monkeypatch.setattr("app.tasks.customer_intelligence_backfill.asyncio.create_task", fake_create_task)

    scheduler.start()
    scheduler.start()
    scheduler.stop()

    assert len(created_coroutines) == 1
    created_coroutines[0].close()

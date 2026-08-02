from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app.tasks.customer_intelligence_refresh_retry import CustomerIntelligenceRefreshRetryScheduler


@dataclass(frozen=True)
class FakeSettings:
    CUSTOMER_INTELLIGENCE_RETRY_ENABLED: bool = True
    CUSTOMER_INTELLIGENCE_RETRY_INTERVAL_SECONDS: int = 60
    CUSTOMER_INTELLIGENCE_RETRY_BATCH_SIZE: int = 20


class FakeRefreshService:
    def __init__(self) -> None:
        self.limits: list[int] = []

    async def run_due_retries(self, *, limit: int = 20) -> dict[str, object]:
        self.limits.append(limit)
        return {"success": True, "total": 1, "succeeded": 1, "failed": 0, "results": []}


@pytest.mark.asyncio
async def test_customer_intelligence_retry_scheduler_runs_due_retries_with_configured_limit(monkeypatch) -> None:
    refresh_service = FakeRefreshService()
    scheduler = CustomerIntelligenceRefreshRetryScheduler(refresh_service=refresh_service)
    monkeypatch.setattr(
        "app.tasks.customer_intelligence_refresh_retry.get_settings",
        lambda: FakeSettings(CUSTOMER_INTELLIGENCE_RETRY_BATCH_SIZE=12),
    )

    result = await scheduler.retry_once()

    assert result["success"] is True
    assert refresh_service.limits == [12]


@pytest.mark.asyncio
async def test_customer_intelligence_retry_scheduler_accepts_explicit_limit(monkeypatch) -> None:
    refresh_service = FakeRefreshService()
    scheduler = CustomerIntelligenceRefreshRetryScheduler(refresh_service=refresh_service)
    monkeypatch.setattr(
        "app.tasks.customer_intelligence_refresh_retry.get_settings",
        lambda: FakeSettings(CUSTOMER_INTELLIGENCE_RETRY_BATCH_SIZE=12),
    )

    await scheduler.retry_once(limit=3)

    assert refresh_service.limits == [3]


def test_customer_intelligence_retry_scheduler_does_not_start_when_disabled(monkeypatch) -> None:
    scheduler = CustomerIntelligenceRefreshRetryScheduler(refresh_service=FakeRefreshService())
    monkeypatch.setattr(
        "app.tasks.customer_intelligence_refresh_retry.get_settings",
        lambda: FakeSettings(CUSTOMER_INTELLIGENCE_RETRY_ENABLED=False),
    )

    scheduler.start()

    assert scheduler._running is False
    assert scheduler._task is None


def test_customer_intelligence_retry_scheduler_does_not_start_twice(monkeypatch) -> None:
    created_coroutines = []

    def fake_create_task(coro):
        created_coroutines.append(coro)
        return SimpleNamespace(cancel=lambda: None)

    scheduler = CustomerIntelligenceRefreshRetryScheduler(refresh_service=FakeRefreshService())
    monkeypatch.setattr(
        "app.tasks.customer_intelligence_refresh_retry.get_settings",
        lambda: FakeSettings(),
    )
    monkeypatch.setattr("app.tasks.customer_intelligence_refresh_retry.asyncio.create_task", fake_create_task)

    scheduler.start()
    scheduler.start()
    scheduler.stop()

    assert len(created_coroutines) == 1
    created_coroutines[0].close()

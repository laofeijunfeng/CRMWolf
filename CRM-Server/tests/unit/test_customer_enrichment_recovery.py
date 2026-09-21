from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.customer_enrichment_contracts import CustomerEnrichmentPurpose
from app.tasks.customer_enrichment_recovery import CustomerEnrichmentRecoveryScheduler


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeJobCRUD:
    def __init__(self, candidates) -> None:
        self.candidates = candidates
        self.calls: list[dict[str, int]] = []

    def list_system_recovery_candidates(self, db, **kwargs):
        self.calls.append(kwargs)
        return self.candidates


class FakeJobService:
    def __init__(self, outcomes: dict[str, str | Exception]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    async def run(self, request):
        self.calls.append(request.job_public_id)
        outcome = self.outcomes[request.job_public_id]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(execution_status=outcome)


def _candidate(public_id: str, purpose: str, *, team_id: int = 7):
    return SimpleNamespace(team_id=team_id, job_public_id=public_id, purpose=purpose)


@pytest.mark.asyncio
async def test_recovery_uses_fair_purpose_quotas_and_processes_initial_first(monkeypatch) -> None:
    candidates = [
        _candidate("cej_initial_1", CustomerEnrichmentPurpose.INITIAL_CREATION.value),
        _candidate("cej_initial_2", CustomerEnrichmentPurpose.INITIAL_CREATION.value),
        _candidate("cej_backfill_1", CustomerEnrichmentPurpose.HISTORICAL_BACKFILL.value),
    ]
    crud = FakeJobCRUD(candidates)
    service = FakeJobService(
        {
            "cej_initial_1": "COMPLETED",
            "cej_initial_2": "RETRY_PENDING",
            "cej_backfill_1": "BUSY",
        }
    )
    db = FakeSession()
    monkeypatch.setattr(
        "app.tasks.customer_enrichment_recovery.get_settings",
        lambda: SimpleNamespace(
            CUSTOMER_INITIAL_ENRICHMENT_BATCH_SIZE=20,
            CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_BATCH_SIZE=5,
        ),
    )
    scheduler = CustomerEnrichmentRecoveryScheduler(
        job_crud=crud,
        job_service=service,
        session_factory=lambda: db,
    )

    result = await scheduler.recover_once()

    assert crud.calls == [{"initial_limit": 20, "backfill_limit": 5}]
    assert service.calls == ["cej_initial_1", "cej_initial_2", "cej_backfill_1"]
    assert result == {
        "scanned": 3,
        "completed": 1,
        "retry_pending": 1,
        "exhausted": 0,
        "skipped": 0,
        "busy": 1,
        "failed": 0,
    }
    assert db.closed is True


@pytest.mark.asyncio
async def test_recovery_isolates_one_job_failure_and_continues(monkeypatch) -> None:
    candidates = [
        _candidate("cej_initial_1", CustomerEnrichmentPurpose.INITIAL_CREATION.value),
        _candidate("cej_initial_2", CustomerEnrichmentPurpose.INITIAL_CREATION.value),
        _candidate("cej_backfill_1", CustomerEnrichmentPurpose.HISTORICAL_BACKFILL.value),
    ]
    service = FakeJobService(
        {
            "cej_initial_1": RuntimeError("boom"),
            "cej_initial_2": "EXHAUSTED",
            "cej_backfill_1": "SKIPPED",
        }
    )
    monkeypatch.setattr(
        "app.tasks.customer_enrichment_recovery.get_settings",
        lambda: SimpleNamespace(
            CUSTOMER_INITIAL_ENRICHMENT_BATCH_SIZE=20,
            CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_BATCH_SIZE=5,
        ),
    )
    scheduler = CustomerEnrichmentRecoveryScheduler(
        job_crud=FakeJobCRUD(candidates),
        job_service=service,
        session_factory=FakeSession,
    )

    result = await scheduler.recover_once()

    assert service.calls == ["cej_initial_1", "cej_initial_2", "cej_backfill_1"]
    assert result == {
        "scanned": 3,
        "completed": 0,
        "retry_pending": 0,
        "exhausted": 1,
        "skipped": 1,
        "busy": 0,
        "failed": 1,
    }

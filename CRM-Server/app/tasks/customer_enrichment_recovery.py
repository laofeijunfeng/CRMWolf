"""Recovery scheduler for durable customer-enrichment jobs."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.crud.customer_enrichment_job import CustomerEnrichmentJobCRUD, customer_enrichment_job_crud
from app.services.customer_enrichment_contracts import CustomerEnrichmentJobRequest
from app.services.customer_enrichment_job_service import (
    CustomerEnrichmentJobService,
    customer_enrichment_job_service,
)

logger = logging.getLogger(__name__)


class CustomerEnrichmentRecoveryScheduler:
    def __init__(
        self,
        *,
        job_crud: CustomerEnrichmentJobCRUD | None = None,
        job_service: CustomerEnrichmentJobService | None = None,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self.job_crud = job_crud or customer_enrichment_job_crud
        self.job_service = job_service or customer_enrichment_job_service
        self.session_factory = session_factory
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def recover_once(self) -> dict[str, int]:
        settings = get_settings()
        db = self.session_factory()
        try:
            candidates = self.job_crud.list_system_recovery_candidates(
                db,
                initial_limit=max(0, int(settings.CUSTOMER_INITIAL_ENRICHMENT_BATCH_SIZE)),
                backfill_limit=max(0, int(settings.CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_BATCH_SIZE)),
            )
            requests = [
                CustomerEnrichmentJobRequest(
                    team_id=int(candidate.team_id),
                    job_public_id=str(candidate.job_public_id),
                )
                for candidate in candidates
            ]
        finally:
            db.close()

        counts = {
            "scanned": len(requests),
            "completed": 0,
            "retry_pending": 0,
            "exhausted": 0,
            "skipped": 0,
            "busy": 0,
            "failed": 0,
        }
        for request in requests:
            try:
                result = await self.job_service.run(request)
            except Exception:
                counts["failed"] += 1
                logger.exception("客户初始补全任务恢复失败: %s", request.job_public_id)
                continue
            key = {
                "COMPLETED": "completed",
                "RETRY_PENDING": "retry_pending",
                "EXHAUSTED": "exhausted",
                "SKIPPED": "skipped",
                "BUSY": "busy",
            }.get(result.execution_status, "failed")
            counts[key] += 1
        return counts

    async def _run_scheduler(self) -> None:
        settings = get_settings()
        interval = max(10, int(settings.CUSTOMER_INITIAL_ENRICHMENT_RECOVERY_INTERVAL_SECONDS))
        while self._running:
            try:
                result = await self.recover_once()
                if result["scanned"]:
                    logger.info("客户初始补全任务恢复扫描完成: %s", result)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("客户初始补全任务恢复扫描失败")
            await asyncio.sleep(interval)

    def start(self) -> None:
        settings = get_settings()
        if not settings.CUSTOMER_INITIAL_ENRICHMENT_RECOVERY_ENABLED or self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("客户初始补全任务恢复调度已启动")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
        logger.info("客户初始补全任务恢复调度已停止")


customer_enrichment_recovery_scheduler = CustomerEnrichmentRecoveryScheduler()


def start_customer_enrichment_recovery_scheduler() -> None:
    customer_enrichment_recovery_scheduler.start()


def stop_customer_enrichment_recovery_scheduler() -> None:
    customer_enrichment_recovery_scheduler.stop()

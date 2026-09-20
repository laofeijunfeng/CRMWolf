"""Background scheduler for historical customer-enrichment registration."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.customer_enrichment_backfill_service import (
    CustomerEnrichmentBackfillService,
    customer_enrichment_backfill_service,
)
from app.tasks.customer_enrichment_recovery import (
    CustomerEnrichmentRecoveryScheduler,
    customer_enrichment_recovery_scheduler,
)

logger = logging.getLogger(__name__)


class CustomerEnrichmentBackfillScheduler:
    def __init__(
        self,
        *,
        backfill_service: CustomerEnrichmentBackfillService | None = None,
        recovery_scheduler: CustomerEnrichmentRecoveryScheduler | None = None,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self.backfill_service = backfill_service or customer_enrichment_backfill_service
        self.recovery_scheduler = recovery_scheduler or customer_enrichment_recovery_scheduler
        self.session_factory = session_factory
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def backfill_once(
        self,
        *,
        limit: int | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        settings = get_settings()
        batch_size = (
            int(limit)
            if limit is not None
            else int(settings.CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_BATCH_SIZE)
        )
        db = self.session_factory()
        try:
            result = self.backfill_service.scan_and_ensure(
                db,
                limit=max(1, batch_size),
                dry_run=dry_run,
            )
            if not dry_run:
                db.commit()
                if result.scheduled > 0:
                    await self.recovery_scheduler.recover_once()
            return result.to_dict()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def _run_scheduler(self) -> None:
        settings = get_settings()
        interval_seconds = max(
            60,
            int(settings.CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_INTERVAL_SECONDS),
        )
        batch_size = max(1, int(settings.CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_BATCH_SIZE))
        while self._running:
            try:
                result = await self.backfill_once(limit=batch_size)
                if result["scheduled"]:
                    logger.info("客户初始补全历史回填已调度: %s", result)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("客户初始补全历史回填调度异常")
            await asyncio.sleep(interval_seconds)

    def start(self) -> None:
        settings = get_settings()
        if not settings.CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_ENABLED or self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("客户初始补全历史回填调度已启动")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
        logger.info("客户初始补全历史回填调度已停止")


customer_enrichment_backfill_scheduler = CustomerEnrichmentBackfillScheduler()


def start_customer_enrichment_backfill_scheduler() -> None:
    customer_enrichment_backfill_scheduler.start()


def stop_customer_enrichment_backfill_scheduler() -> None:
    customer_enrichment_backfill_scheduler.stop()

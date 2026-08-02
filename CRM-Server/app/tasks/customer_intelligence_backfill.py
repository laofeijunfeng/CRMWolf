"""Background scheduler for missing historical customer intelligence profiles."""

from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.agent.types import JSONDict
from app.services.customer_intelligence_refresh_service import (
    CustomerIntelligenceRefreshService,
    customer_intelligence_refresh_service,
)

logger = logging.getLogger(__name__)


class CustomerIntelligenceBackfillScheduler:
    def __init__(
        self,
        *,
        refresh_service: CustomerIntelligenceRefreshService | None = None,
    ) -> None:
        self.refresh_service = refresh_service or customer_intelligence_refresh_service
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def backfill_once(self, *, limit: int | None = None) -> JSONDict:
        settings = get_settings()
        batch_size = limit if limit is not None else settings.CUSTOMER_INTELLIGENCE_BACKFILL_BATCH_SIZE
        db = SessionLocal()
        try:
            result = await self.refresh_service.trigger_missing_historical_backfill(
                db,
                limit=max(1, batch_size),
                schedule_runs=False,
            )
            db.commit()
            if result.scheduled > 0:
                await self.refresh_service.run_due_retries(limit=result.scheduled)
            return {
                "success": result.success,
                "request_id": result.request_id,
                "scope": result.scope,
                "total": result.total,
                "scheduled": result.scheduled,
                "customer_ids": result.customer_ids,
                "profile_vector_reindexed": result.profile_vector_reindexed,
                "profile_vector_customer_ids": list(result.profile_vector_customer_ids),
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def _run_scheduler(self) -> None:
        settings = get_settings()
        interval_seconds = max(settings.CUSTOMER_INTELLIGENCE_BACKFILL_INTERVAL_SECONDS, 60)
        batch_size = max(1, settings.CUSTOMER_INTELLIGENCE_BACKFILL_BATCH_SIZE)
        while self._running:
            try:
                result = await self.backfill_once(limit=batch_size)
                total = result.get("total")
                if isinstance(total, int) and total > 0:
                    logger.info("客户智能历史补档已调度: %s", result)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("客户智能历史补档调度异常")
            await asyncio.sleep(interval_seconds)

    def start(self) -> None:
        settings = get_settings()
        if not settings.CUSTOMER_INTELLIGENCE_BACKFILL_ENABLED:
            logger.info("客户智能历史补档调度未启用")
            return
        if self._running:
            logger.warning("客户智能历史补档调度已在运行中")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("客户智能历史补档调度已启动")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("客户智能历史补档调度已停止")


customer_intelligence_backfill_scheduler = CustomerIntelligenceBackfillScheduler()


def start_customer_intelligence_backfill_scheduler() -> None:
    customer_intelligence_backfill_scheduler.start()


def stop_customer_intelligence_backfill_scheduler() -> None:
    customer_intelligence_backfill_scheduler.stop()

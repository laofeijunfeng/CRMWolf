"""Background scheduler for retryable customer intelligence refresh runs."""

from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.services.agent.types import JSONDict
from app.services.customer_intelligence_refresh_service import (
    CustomerIntelligenceRefreshService,
    customer_intelligence_refresh_service,
)

logger = logging.getLogger(__name__)


class CustomerIntelligenceRefreshRetryScheduler:
    def __init__(
        self,
        *,
        refresh_service: CustomerIntelligenceRefreshService | None = None,
    ) -> None:
        self.refresh_service = refresh_service or customer_intelligence_refresh_service
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def retry_once(self, *, limit: int | None = None) -> JSONDict:
        settings = get_settings()
        batch_size = limit if limit is not None else settings.CUSTOMER_INTELLIGENCE_RETRY_BATCH_SIZE
        return await self.refresh_service.run_due_retries(limit=max(1, batch_size))

    async def _run_scheduler(self) -> None:
        settings = get_settings()
        interval_seconds = max(settings.CUSTOMER_INTELLIGENCE_RETRY_INTERVAL_SECONDS, 10)
        batch_size = max(1, settings.CUSTOMER_INTELLIGENCE_RETRY_BATCH_SIZE)
        while self._running:
            try:
                result = await self.retry_once(limit=batch_size)
                total = result.get("total")
                if isinstance(total, int) and total > 0:
                    logger.info("客户智能档案刷新重试完成: %s", result)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("客户智能档案刷新重试调度异常")
            await asyncio.sleep(interval_seconds)

    def start(self) -> None:
        settings = get_settings()
        if not settings.CUSTOMER_INTELLIGENCE_RETRY_ENABLED:
            logger.info("客户智能档案刷新重试调度未启用")
            return
        if self._running:
            logger.warning("客户智能档案刷新重试调度已在运行中")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("客户智能档案刷新重试调度已启动")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("客户智能档案刷新重试调度已停止")


customer_intelligence_refresh_retry_scheduler = CustomerIntelligenceRefreshRetryScheduler()


def start_customer_intelligence_refresh_retry_scheduler() -> None:
    customer_intelligence_refresh_retry_scheduler.start()


def stop_customer_intelligence_refresh_retry_scheduler() -> None:
    customer_intelligence_refresh_retry_scheduler.stop()

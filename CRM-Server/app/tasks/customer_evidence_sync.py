"""Background scheduler for customer evidence vector synchronization."""

import asyncio
import logging

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.customer_vector_sync_service import customer_vector_sync_service

logger = logging.getLogger(__name__)


class CustomerEvidenceSyncScheduler:
    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def sync_once(self) -> dict[str, int]:
        db = SessionLocal()
        try:
            stats = customer_vector_sync_service.sync_once(db)
            return {
                "scanned": stats.scanned,
                "upserted": stats.upserted,
                "deleted": stats.deleted,
                "failed": stats.failed,
            }
        finally:
            db.close()

    async def _run_scheduler(self) -> None:
        settings = get_settings()
        interval_seconds = max(settings.CUSTOMER_EVIDENCE_SYNC_INTERVAL_SECONDS, 5)
        while self._running:
            try:
                stats = await self.sync_once()
                if stats["scanned"] > 0:
                    logger.info("客户证据向量同步完成: %s", stats)
            except Exception:
                logger.exception("客户证据向量同步调度异常")
            await asyncio.sleep(interval_seconds)

    def start(self) -> None:
        settings = get_settings()
        if not settings.QDRANT_ENABLED:
            logger.info("Qdrant 未启用, 跳过客户证据向量同步调度")
            return
        if self._running:
            logger.warning("客户证据向量同步调度已在运行中")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("客户证据向量同步调度已启动")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("客户证据向量同步调度已停止")


customer_evidence_sync_scheduler = CustomerEvidenceSyncScheduler()


def start_customer_evidence_sync_scheduler() -> None:
    customer_evidence_sync_scheduler.start()


def stop_customer_evidence_sync_scheduler() -> None:
    customer_evidence_sync_scheduler.stop()

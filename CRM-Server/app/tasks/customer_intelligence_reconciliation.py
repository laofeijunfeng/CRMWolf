"""Background reconciliation for customer-intelligence source watermarks."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.customer_intelligence_reconciliation_service import (
    CustomerIntelligenceReconciliationResult,
    CustomerIntelligenceReconciliationService,
    customer_intelligence_reconciliation_service,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from app.services.agent.types import JSONDict

logger = logging.getLogger(__name__)


class CustomerIntelligenceReconciliationScheduler:
    """Periodically schedule durable refresh intents for missed source changes."""

    def __init__(
        self,
        *,
        reconciliation_service: CustomerIntelligenceReconciliationService | None = None,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self.reconciliation_service = reconciliation_service or customer_intelligence_reconciliation_service
        self.session_factory = session_factory or SessionLocal
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._after_customer_id: int | None = None

    async def reconcile_once(
        self,
        *,
        limit: int | None = None,
        team_id: int | None = None,
        after_customer_id: int | None = None,
        dry_run: bool = False,
    ) -> JSONDict:
        settings = get_settings()
        batch_size = limit if limit is not None else settings.CUSTOMER_INTELLIGENCE_RECONCILIATION_BATCH_SIZE
        db = self.session_factory()
        try:
            result = self.reconciliation_service.reconcile_once(
                db,
                team_id=team_id,
                limit=max(1, batch_size),
                after_customer_id=after_customer_id,
                dry_run=dry_run,
            )
            if not dry_run:
                db.commit()
            return _result_to_dict(result)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def _run_scheduler(self) -> None:
        settings = get_settings()
        interval_seconds = max(settings.CUSTOMER_INTELLIGENCE_RECONCILIATION_INTERVAL_SECONDS, 30)
        batch_size = max(1, settings.CUSTOMER_INTELLIGENCE_RECONCILIATION_BATCH_SIZE)
        while self._running:
            try:
                result = await self.reconcile_once(
                    limit=batch_size,
                    after_customer_id=self._after_customer_id,
                )
                next_customer_id = result.get("next_customer_id")
                self._after_customer_id = next_customer_id if isinstance(next_customer_id, int) else None
                if result.get("scanned", 0) or result.get("errors", 0):
                    logger.info("客户智能档案对账扫描完成: %s", result)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("客户智能档案对账调度异常")
            await asyncio.sleep(interval_seconds)

    def start(self) -> None:
        settings = get_settings()
        if not settings.CUSTOMER_INTELLIGENCE_RECONCILIATION_ENABLED:
            logger.info("客户智能档案对账调度未启用")
            return
        if self._running:
            logger.warning("客户智能档案对账调度已在运行中")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("客户智能档案对账调度已启动")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._after_customer_id = None
        if self._task is not None:
            self._task.cancel()
        logger.info("客户智能档案对账调度已停止")


def _result_to_dict(result: CustomerIntelligenceReconciliationResult) -> JSONDict:
    return {
        "success": result.success,
        "scanned": result.scanned,
        "stale": result.stale,
        "scheduled": result.scheduled,
        "skipped": result.skipped,
        "errors": result.errors,
        "customer_ids": result.customer_ids,
        "scheduled_customer_ids": result.scheduled_customer_ids,
        "error_customer_ids": result.error_customer_ids,
        "next_customer_id": result.next_customer_id,
        "dry_run": result.dry_run,
    }


customer_intelligence_reconciliation_scheduler = CustomerIntelligenceReconciliationScheduler()


def start_customer_intelligence_reconciliation_scheduler() -> None:
    customer_intelligence_reconciliation_scheduler.start()


def stop_customer_intelligence_reconciliation_scheduler() -> None:
    customer_intelligence_reconciliation_scheduler.stop()

"""Periodic repair for customer initial-enrichment state."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.customer_enrichment_reconciliation_service import (
    CustomerEnrichmentReconciliationResult,
    CustomerEnrichmentReconciliationService,
    customer_enrichment_reconciliation_service,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class CustomerEnrichmentReconciliationScheduler:
    def __init__(
        self,
        *,
        reconciliation_service: CustomerEnrichmentReconciliationService | None = None,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self.reconciliation_service = (
            reconciliation_service or customer_enrichment_reconciliation_service
        )
        self.session_factory = session_factory
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._after_customer_id: int | None = None

    async def reconcile_once(
        self,
        *,
        team_id: int | None = None,
        limit: int | None = None,
        after_customer_id: int | None = None,
        dry_run: bool = False,
    ) -> dict[str, object]:
        settings = get_settings()
        batch_size = (
            int(limit)
            if limit is not None
            else int(settings.CUSTOMER_INITIAL_ENRICHMENT_RECONCILIATION_BATCH_SIZE)
        )
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
        interval_seconds = max(
            60,
            int(settings.CUSTOMER_INITIAL_ENRICHMENT_RECONCILIATION_INTERVAL_SECONDS),
        )
        batch_size = max(
            1,
            int(settings.CUSTOMER_INITIAL_ENRICHMENT_RECONCILIATION_BATCH_SIZE),
        )
        while self._running:
            try:
                result = await self.reconcile_once(
                    limit=batch_size,
                    after_customer_id=self._after_customer_id,
                )
                next_customer_id = result.get("next_customer_id")
                self._after_customer_id = (
                    int(next_customer_id) if next_customer_id is not None else None
                )
                if any(
                    int(result[key])
                    for key in (
                        "jobs_created",
                        "gates_released",
                        "refreshes_repaired",
                        "errors",
                    )
                ):
                    logger.info("客户初始补全对账完成: %s", result)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("客户初始补全对账调度异常")
            await asyncio.sleep(interval_seconds)

    def start(self) -> None:
        settings = get_settings()
        if not settings.CUSTOMER_INITIAL_ENRICHMENT_RECONCILIATION_ENABLED or self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("客户初始补全对账调度已启动")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
        logger.info("客户初始补全对账调度已停止")


def _result_to_dict(result: CustomerEnrichmentReconciliationResult) -> dict[str, object]:
    return result.to_dict()


customer_enrichment_reconciliation_scheduler = CustomerEnrichmentReconciliationScheduler()


def start_customer_enrichment_reconciliation_scheduler() -> None:
    customer_enrichment_reconciliation_scheduler.start()


def stop_customer_enrichment_reconciliation_scheduler() -> None:
    customer_enrichment_reconciliation_scheduler.stop()

"""Coordinate initial enrichment completion with customer profile refreshes."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.core.database import SessionLocal
from app.crud.customer_enrichment_job import (
    CustomerEnrichmentJobCRUD,
    customer_enrichment_job_crud,
)
from app.services.customer_enrichment_contracts import CustomerEnrichmentJobStatus
from app.services.customer_intelligence_event_publication_service import (
    CustomerIntelligenceEventPublicationService,
    customer_intelligence_event_publication_service,
)
from app.services.customer_intelligence_event_service import (
    CustomerIntelligenceEventService,
    customer_intelligence_event_service,
)
from app.services.customer_intelligence_refresh_service import (
    CustomerIntelligenceRefreshService,
    customer_intelligence_refresh_service,
)
from app.services.customer_intelligence_run_service import (
    CustomerIntelligenceRunService,
    customer_intelligence_run_service,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from sqlalchemy.orm import Session

    from app.models.customer_enrichment_job import CustomerEnrichmentJob
    from app.services.customer_enrichment_contracts import CustomerEnrichmentRunResult
    from app.services.customer_intelligence_event_service import CustomerIntelligenceEvent

logger = logging.getLogger(__name__)
_TERMINAL_SUCCESS = {
    CustomerEnrichmentJobStatus.COMPLETED.value,
    CustomerEnrichmentJobStatus.SKIPPED.value,
}


class CustomerEnrichmentProfileCoordinator:
    """Release a gated run or register one durable refresh receipt, never both."""

    def __init__(
        self,
        *,
        job_crud: CustomerEnrichmentJobCRUD | None = None,
        run_service: CustomerIntelligenceRunService | None = None,
        refresh_service: CustomerIntelligenceRefreshService | None = None,
        event_service: CustomerIntelligenceEventService | None = None,
        publication_service: CustomerIntelligenceEventPublicationService | None = None,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self.job_crud = job_crud or customer_enrichment_job_crud
        self.run_service = run_service or customer_intelligence_run_service
        self.refresh_service = refresh_service or customer_intelligence_refresh_service
        self.event_service = event_service or customer_intelligence_event_service
        self.publication_service = publication_service or customer_intelligence_event_publication_service
        self._session_factory = session_factory

    def on_first_attempt_finished(self, job: CustomerEnrichmentJob) -> None:
        released: list[int] = []
        db = self._session_factory()
        try:
            locked = self.job_crud.get_by_public_id(
                db,
                team_id=int(job.team_id),
                public_id=str(job.public_id),
                for_update=True,
            )
            if locked is None:
                return
            released = self.run_service.release_deferred_for_customer(
                db,
                team_id=int(locked.team_id),
                customer_id=int(locked.customer_id),
            )
            if (
                released
                and str(locked.status) in _TERMINAL_SUCCESS
                and locked.profile_refresh_request_id is None
            ):
                locked.profile_refresh_request_id = f"released:{released[0]}"
                locked.profile_refresh_enqueued_at = business_now()
                db.add(locked)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("释放首次客户档案 gate 失败: job=%s", job.public_id)
            return
        finally:
            db.close()

        self._kick_released_runs(team_id=int(job.team_id), released=released)

    def on_terminal_success(
        self,
        job: CustomerEnrichmentJob,
        result: CustomerEnrichmentRunResult,
    ) -> None:
        del result
        released: list[int] = []
        event = None
        db = self._session_factory()
        try:
            locked = self.job_crud.get_by_public_id(
                db,
                team_id=int(job.team_id),
                public_id=str(job.public_id),
                for_update=True,
            )
            if locked is None or locked.profile_refresh_request_id is not None:
                return

            released = self.run_service.release_deferred_for_customer(
                db,
                team_id=int(locked.team_id),
                customer_id=int(locked.customer_id),
            )
            receipt_time = business_now()
            if released:
                locked.profile_refresh_request_id = f"released:{released[0]}"
            else:
                event = self._terminal_refresh_event(locked, occurred_at=receipt_time)
                locked.profile_refresh_request_id = self._request_id(event)
            locked.profile_refresh_enqueued_at = receipt_time
            db.add(locked)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("登记客户补全档案刷新凭据失败: job=%s", job.public_id)
            return
        finally:
            db.close()

        if released:
            self._kick_released_runs(team_id=int(job.team_id), released=released)
            return
        if event is not None:
            self.publication_service.enqueue_after_commit(event=event, scope="full")

    def _terminal_refresh_event(
        self,
        job: CustomerEnrichmentJob,
        *,
        occurred_at: datetime,
    ) -> CustomerIntelligenceEvent:
        return self.event_service.business_object_changed(
            team_id=int(job.team_id),
            customer_id=int(job.customer_id),
            actor_id=None,
            trigger_type="customer_business_object_updated",
            source_type="customer",
            source_id=int(job.customer_id),
            change_id=f"initial-enrichment:{job.public_id}",
            source_version=str(job.public_id),
            summary="客户初始信息补全已完成，刷新客户智能档案",  # noqa: RUF001
            payload={"change_origin": "CUSTOMER_INITIAL_ENRICHMENT"},
            occurred_at=occurred_at,
        )

    def _kick_released_runs(self, *, team_id: int, released: list[int]) -> None:
        if not released:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("当前线程没有运行中的事件循环, 已释放档案任务交由恢复器执行")
            return
        task = asyncio.create_task(
            self.refresh_service.run_due_retries(
                team_id=team_id,
                limit=max(1, len(released)),
            )
        )
        task.add_done_callback(self._consume_task_exception)

    @staticmethod
    def _request_id(event: CustomerIntelligenceEvent) -> str:
        return f"business-event-{event.trigger_type}-{event.event_key[:16]}"

    @staticmethod
    def _consume_task_exception(task: asyncio.Task[object]) -> None:
        if task.cancelled():
            return
        try:
            task.exception()
        except Exception:
            logger.exception("唤醒已释放客户档案任务失败")


customer_enrichment_profile_coordinator = CustomerEnrichmentProfileCoordinator()

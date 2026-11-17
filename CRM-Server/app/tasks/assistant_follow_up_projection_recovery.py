"""Recover committed Assistant 2.0 follow-up projection jobs."""

from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.crud.assistant_follow_up_projection_job import assistant_follow_up_projection_job_crud
from app.services.assistant_follow_up_projection_job_service import (
    AssistantFollowUpProjectionJobRequest,
    assistant_follow_up_projection_job_service,
)

logger = logging.getLogger(__name__)


class AssistantFollowUpProjectionRecoveryScheduler:
    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def recover_once(self, *, limit: int | None = None) -> dict[str, int]:
        settings = get_settings()
        db = SessionLocal()
        try:
            jobs = assistant_follow_up_projection_job_crud.list_system_recovery_candidates(
                db,
                max_attempts=max(1, settings.CUSTOMER_ACTIVITY_POST_COMMIT_MAX_ATTEMPTS),
                limit=limit or max(1, settings.CUSTOMER_ACTIVITY_POST_COMMIT_RECOVERY_BATCH_SIZE),
            )
            requests = [
                AssistantFollowUpProjectionJobRequest(job_public_id=str(job.public_id), team_id=int(job.team_id))
                for job in jobs
            ]
        finally:
            db.close()

        completed = failed = skipped = busy = 0
        for request in requests:
            try:
                result = await assistant_follow_up_projection_job_service.run(request)
            except Exception:
                failed += 1
                logger.exception("Assistant 2.0 跟进任务投影恢复失败: %s", request.job_public_id)
                continue
            if result.get("execution_status") == "BUSY":
                busy += 1
            elif result.get("projection_run_status") == "SKIPPED":
                skipped += 1
            elif result.get("success"):
                completed += 1
            else:
                failed += 1
        return {"scanned": len(requests), "completed": completed, "failed": failed, "skipped": skipped, "busy": busy}

    async def _run_scheduler(self) -> None:
        interval = max(10, get_settings().CUSTOMER_ACTIVITY_POST_COMMIT_RECOVERY_INTERVAL_SECONDS)
        while self._running:
            try:
                result = await self.recover_once()
                if result["scanned"]:
                    logger.info("Assistant 2.0 跟进任务投影恢复扫描完成: %s", result)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Assistant 2.0 跟进任务投影恢复扫描失败")
            await asyncio.sleep(interval)

    def start(self) -> None:
        if not get_settings().CUSTOMER_ACTIVITY_POST_COMMIT_RECOVERY_ENABLED or self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()


assistant_follow_up_projection_recovery_scheduler = AssistantFollowUpProjectionRecoveryScheduler()


def start_assistant_follow_up_projection_recovery_scheduler() -> None:
    assistant_follow_up_projection_recovery_scheduler.start()


def stop_assistant_follow_up_projection_recovery_scheduler() -> None:
    assistant_follow_up_projection_recovery_scheduler.stop()

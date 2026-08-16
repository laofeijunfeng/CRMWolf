"""Recovery scheduler for durable customer-activity post-commit jobs."""

from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.crud.customer_activity_post_commit_job import customer_activity_post_commit_job_crud
from app.services.customer_activity_post_commit_job_service import (
    CustomerActivityPostCommitJobRequest,
    customer_activity_post_commit_job_service,
)

logger = logging.getLogger(__name__)


class CustomerActivityPostCommitRecoveryScheduler:
    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def recover_once(self, *, limit: int | None = None) -> dict[str, int]:
        settings = get_settings()
        db = SessionLocal()
        try:
            jobs = customer_activity_post_commit_job_crud.list_system_recovery_candidates(
                db,
                max_attempts=max(1, settings.CUSTOMER_ACTIVITY_POST_COMMIT_MAX_ATTEMPTS),
                limit=limit or max(1, settings.CUSTOMER_ACTIVITY_POST_COMMIT_RECOVERY_BATCH_SIZE),
            )
            requests = [
                CustomerActivityPostCommitJobRequest(
                    job_public_id=candidate.job_public_id,
                    team_id=candidate.team_id,
                )
                for candidate in jobs
            ]
        finally:
            db.close()

        completed = failed = skipped = busy = 0
        for request in requests:
            try:
                result = await customer_activity_post_commit_job_service.run(request)
            except Exception:
                failed += 1
                logger.exception("客户活动后提交任务恢复失败: %s", request.job_public_id)
                continue
            if result.get("execution_status") == "BUSY":
                busy += 1
            elif result.get("skip_reason"):
                skipped += 1
            elif result.get("success"):
                completed += 1
            else:
                failed += 1
        return {
            "scanned": len(requests),
            "completed": completed,
            "failed": failed,
            "skipped": skipped,
            "busy": busy,
        }

    async def _run_scheduler(self) -> None:
        settings = get_settings()
        interval = max(10, settings.CUSTOMER_ACTIVITY_POST_COMMIT_RECOVERY_INTERVAL_SECONDS)
        while self._running:
            try:
                result = await self.recover_once()
                if result["scanned"]:
                    logger.info("客户活动后提交任务恢复扫描完成: %s", result)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("客户活动后提交任务恢复扫描失败")
            await asyncio.sleep(interval)

    def start(self) -> None:
        settings = get_settings()
        if not settings.CUSTOMER_ACTIVITY_POST_COMMIT_RECOVERY_ENABLED or self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("客户活动后提交任务恢复调度已启动")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
        logger.info("客户活动后提交任务恢复调度已停止")


customer_activity_post_commit_recovery_scheduler = CustomerActivityPostCommitRecoveryScheduler()


def start_customer_activity_post_commit_recovery_scheduler() -> None:
    customer_activity_post_commit_recovery_scheduler.start()


def stop_customer_activity_post_commit_recovery_scheduler() -> None:
    customer_activity_post_commit_recovery_scheduler.stop()

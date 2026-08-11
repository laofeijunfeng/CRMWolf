"""Background scheduler for Agent workflow recovery classification."""
from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.agent.workflow_recovery_service import agent_workflow_recovery_service
from app.services.agent.types import JSONDict

logger = logging.getLogger(__name__)


class AgentWorkflowRecoveryScheduler:
    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def recover_once(self, *, limit: int | None = None) -> JSONDict:
        db = SessionLocal()
        try:
            return await agent_workflow_recovery_service.recover_once(db, limit=limit)
        finally:
            db.close()

    async def _run_scheduler(self) -> None:
        settings = get_settings()
        interval_seconds = max(settings.AGENT_WORKFLOW_RECOVERY_INTERVAL_SECONDS, 10)
        batch_size = max(1, settings.AGENT_WORKFLOW_RECOVERY_BATCH_SIZE)
        while self._running:
            try:
                result = await self.recover_once(limit=batch_size)
                if int(result.get("scanned_actions") or 0) > 0:
                    logger.info("Agent workflow recovery scan completed: %s", result)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Agent workflow recovery scheduler failed")
            await asyncio.sleep(interval_seconds)

    def start(self) -> None:
        settings = get_settings()
        if not settings.AGENT_WORKFLOW_RECOVERY_ENABLED:
            logger.info("Agent workflow recovery scheduler disabled")
            return
        if self._running:
            logger.warning("Agent workflow recovery scheduler already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("Agent workflow recovery scheduler started")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Agent workflow recovery scheduler stopped")


agent_workflow_recovery_scheduler = AgentWorkflowRecoveryScheduler()


def start_agent_workflow_recovery_scheduler() -> None:
    agent_workflow_recovery_scheduler.start()


def stop_agent_workflow_recovery_scheduler() -> None:
    agent_workflow_recovery_scheduler.stop()

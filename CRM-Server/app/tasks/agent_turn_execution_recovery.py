"""Recovery scheduler for accepted CRM Agent executions."""

from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.services.agent.application import agent_application_service

logger = logging.getLogger(__name__)


class AgentTurnExecutionRecoveryScheduler:
    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def _run(self) -> None:
        interval = max(5, get_settings().AGENT_TURN_RECOVERY_INTERVAL_SECONDS)
        while self._running:
            try:
                result = await agent_application_service.recover_expired_executions()
                if result["recovered"]:
                    logger.info("Agent 持久执行恢复扫描完成: %s", result)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Agent 持久执行恢复扫描失败")
            await asyncio.sleep(interval)

    def start(self) -> None:
        if not get_settings().AGENT_TURN_RECOVERY_ENABLED or self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()


agent_turn_execution_recovery_scheduler = AgentTurnExecutionRecoveryScheduler()


def start_agent_turn_execution_recovery_scheduler() -> None:
    agent_turn_execution_recovery_scheduler.start()


def stop_agent_turn_execution_recovery_scheduler() -> None:
    agent_turn_execution_recovery_scheduler.stop()

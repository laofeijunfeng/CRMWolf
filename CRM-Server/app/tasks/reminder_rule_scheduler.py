"""Periodic scan for enabled reminder rules."""


import asyncio
import logging
from datetime import datetime

from app.core.database import SessionLocal
from app.services.feishu_notification import FeishuNotificationService
from app.services.reminder_rule_execution import execute_due_reminder_rules
from app.utils.time import business_now

logger = logging.getLogger(__name__)
SCAN_INTERVAL_SECONDS = 15 * 60


class ReminderRuleScheduler:
    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._notifier = FeishuNotificationService()

    async def scan_once(self, *, now: datetime | None = None) -> int:
        db = SessionLocal()
        try:
            async def deliver(team_id: int, user_ids: list[int], title: str, content: str) -> dict[str, int]:
                result = await self._notifier.notify_markdown_card(
                    db, team_id, user_ids, title=title, markdown=content,
                )
                return {"sent": int(result.get("success", 0)), "skipped": int(result.get("skipped", 0))}

            result = await execute_due_reminder_rules(db, now=now or business_now(), deliver=deliver)
            return result.sent_count
        finally:
            db.close()

    async def _run(self) -> None:
        while self._running:
            try:
                sent = await self.scan_once()
                if sent:
                    logger.info("提醒规则扫描完成，新发送 %s 条", sent)  # noqa: RUF001
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("提醒规则扫描失败")
            await asyncio.sleep(SCAN_INTERVAL_SECONDS)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("提醒规则扫描已启动")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
        logger.info("提醒规则扫描已停止")


reminder_rule_scheduler = ReminderRuleScheduler()


def start_reminder_rule_scheduler() -> None:
    reminder_rule_scheduler.start()


def stop_reminder_rule_scheduler() -> None:
    reminder_rule_scheduler.stop()

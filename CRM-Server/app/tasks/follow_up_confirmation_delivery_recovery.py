"""Recovery scheduler for durable follow-up confirmation deliveries."""

from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.crud.sales_commitment import follow_up_task_confirmation_prompt_delivery_crud
from app.models.sales_commitment import FollowUpTaskConfirmationPromptStatus
from app.services.follow_up_confirmation_delivery_workflow import (
    ConfirmationDeliveryInput,
    follow_up_confirmation_delivery_workflow,
)

logger = logging.getLogger(__name__)


class FollowUpConfirmationDeliveryRecoveryScheduler:
    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def recover_once(self, *, limit: int | None = None) -> dict[str, int]:
        settings = get_settings()
        db = SessionLocal()
        try:
            deliveries = follow_up_task_confirmation_prompt_delivery_crud.list_system_recovery_candidates(
                db,
                max_attempts=max(1, settings.FOLLOW_UP_CONFIRMATION_DELIVERY_MAX_ATTEMPTS),
                limit=limit or max(1, settings.FOLLOW_UP_CONFIRMATION_DELIVERY_RECOVERY_BATCH_SIZE),
            )
            requests = [
                ConfirmationDeliveryInput(
                    delivery_public_id=candidate.delivery_public_id,
                    case_public_id=candidate.case_public_id,
                    team_id=candidate.team_id,
                    owner_id=candidate.owner_id,
                    channel=candidate.channel,
                    purpose=candidate.purpose,
                    provider=candidate.provider,
                    recipient_id=candidate.recipient_id,
                    agent_session_id=candidate.agent_session_id,
                    origin_turn_id=candidate.origin_turn_id,
                    origin_message_id=candidate.origin_message_id,
                    source_activity_id=candidate.source_activity_id,
                    expected_activity_revision=candidate.expected_activity_revision,
                )
                for candidate in deliveries
            ]
        finally:
            db.close()

        recovered = skipped = failed = exhausted = ambiguous = deferred = 0
        for request in requests:
            try:
                result = await follow_up_confirmation_delivery_workflow.run(request)
            except Exception:
                failed += 1
                logger.exception("Follow-up confirmation delivery recovery failed: %s", request.delivery_public_id)
                continue
            status = result.get("status")
            execution_status = result.get("execution_status")
            if status == FollowUpTaskConfirmationPromptStatus.SENT:
                recovered += 1
            elif status == FollowUpTaskConfirmationPromptStatus.SKIPPED:
                skipped += 1
            elif status == FollowUpTaskConfirmationPromptStatus.EXHAUSTED:
                exhausted += 1
            elif status == FollowUpTaskConfirmationPromptStatus.AMBIGUOUS:
                ambiguous += 1
            elif execution_status in {"BUSY", "DEFERRED", "NOT_CLAIMED", "LEASE_LOST"}:
                deferred += 1
            else:
                failed += 1
        return {
            "scanned": len(requests),
            "recovered": recovered,
            "skipped": skipped,
            "failed": failed,
            "exhausted": exhausted,
            "ambiguous": ambiguous,
            "deferred": deferred,
        }

    async def _run_scheduler(self) -> None:
        settings = get_settings()
        interval = max(10, settings.FOLLOW_UP_CONFIRMATION_DELIVERY_RECOVERY_INTERVAL_SECONDS)
        while self._running:
            try:
                result = await self.recover_once()
                if result["scanned"]:
                    logger.info("Follow-up confirmation delivery recovery scan completed: %s", result)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Follow-up confirmation delivery recovery scheduler failed")
            await asyncio.sleep(interval)

    def start(self) -> None:
        settings = get_settings()
        if not settings.FOLLOW_UP_CONFIRMATION_DELIVERY_RECOVERY_ENABLED:
            logger.info("Follow-up confirmation delivery recovery scheduler disabled")
            return
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("Follow-up confirmation delivery recovery scheduler started")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
        logger.info("Follow-up confirmation delivery recovery scheduler stopped")


follow_up_confirmation_delivery_recovery_scheduler = FollowUpConfirmationDeliveryRecoveryScheduler()


def start_follow_up_confirmation_delivery_recovery_scheduler() -> None:
    follow_up_confirmation_delivery_recovery_scheduler.start()


def stop_follow_up_confirmation_delivery_recovery_scheduler() -> None:
    follow_up_confirmation_delivery_recovery_scheduler.stop()

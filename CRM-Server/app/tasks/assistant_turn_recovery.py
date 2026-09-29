"""Recover interrupted Agent 2.0 turns with fresh, lease-fenced database sessions."""

from __future__ import annotations

import asyncio
import logging

from app.services.assistant.turns import recover_turns

logger = logging.getLogger(__name__)
_runner: asyncio.Task[None] | None = None


async def _loop() -> None:
    while True:
        try:
            await recover_turns()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("assistant turn recovery scan failed")
        await asyncio.sleep(15)


def start_assistant_turn_recovery() -> None:
    global _runner
    if _runner is None or _runner.done():
        _runner = asyncio.create_task(_loop())


def stop_assistant_turn_recovery() -> None:
    global _runner
    if _runner is not None:
        _runner.cancel()
        _runner = None

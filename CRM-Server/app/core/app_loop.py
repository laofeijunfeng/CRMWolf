"""Low-latency background kicks always start on the app's event loop.

An Assistant turn runs on its own short-lived loop in a worker thread
(``assistant.turns.schedule_turn``). A task created there would bind shared asyncio
primitives such as ``ai_generation_semaphore`` to that loop and be cancelled when it
closes, so kicks hand only their ``create_task`` to the loop the app started on.
Kicks stay best-effort: durable recovery remains authoritative.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

_app_loop: asyncio.AbstractEventLoop | None = None


def bind_app_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    global _app_loop
    _app_loop = loop


def _run_guarded(work: Callable[[], object], label: str) -> None:
    try:
        work()
    except Exception:
        logger.exception("assistant post-commit work failed: %s", label)


def run_on_app_loop(work: Callable[[], object], label: str) -> None:
    """Run ``work`` where any task it starts is owned by the app loop.

    ``work`` must not touch the caller's DB session: it may run on another thread.
    """
    loop = _app_loop
    try:
        current: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        current = None
    if loop is None or current is loop:
        _run_guarded(work, label)
        return
    try:
        loop.call_soon_threadsafe(_run_guarded, work, label)
    except RuntimeError:
        logger.warning("app loop closed; post-commit work left to recovery: %s", label)

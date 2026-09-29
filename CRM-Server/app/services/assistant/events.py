"""SSE turn events for the streaming submit endpoint.

Transport-only layer: the state machine, action log, and idempotency are
untouched. Reporting failures are swallowed — progress must never break the
business flow (TRD §3.2).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Literal, Protocol

from app.utils.sse_encoder import SSEJsonEncoder

logger = logging.getLogger(__name__)

StageName = Literal["classify", "structure", "quality_gate", "write"]

_STAGE_NAMES: frozenset[str] = frozenset({"classify", "structure", "quality_gate", "write"})


@dataclass(frozen=True)
class TurnStage:
    name: StageName


def stage(name: str) -> TurnStage:
    if name not in _STAGE_NAMES:
        raise ValueError(f"unknown stage name: {name!r}")
    return TurnStage(name=name)  # type: ignore[arg-type]


def encode_sse(event: str, data: dict[str, object]) -> str:
    """One SSE frame: named event + single-line JSON payload."""

    payload = json.dumps(data, ensure_ascii=False, cls=SSEJsonEncoder)
    return f"event: {event}\ndata: {payload}\n\n"


class ProgressReporter(Protocol):
    def stage_start(self, stage: TurnStage) -> None: ...

    def stage_done(self, stage: TurnStage, *, ms: int, score: int | None = None) -> None: ...


class NullProgressReporter:
    """Drop events; default for unit tests and in-process callers."""

    def stage_start(self, stage: TurnStage) -> None:
        _ = stage

    def stage_done(self, stage: TurnStage, *, ms: int, score: int | None = None) -> None:
        _ = stage, ms, score


class SSEProgressReporter:
    """Queue stage events for the streaming endpoint to drain.

    All methods swallow exceptions: progress reporting must not affect the
    business flow. ``ms`` is measured with ``time.monotonic`` deltas.
    """

    def __init__(self) -> None:
        import asyncio

        self._queue: asyncio.Queue[tuple[str, dict[str, object]] | None] = asyncio.Queue()
        self._started_at: dict[str, float] = {}

    def stage_start(self, stage: TurnStage) -> None:
        try:
            self._started_at[stage.name] = time.monotonic()
            self._queue.put_nowait(
                ("stage", {"stage": stage.name, "phase": "start"})
            )
        except Exception:
            logger.exception("stage_start reporting failed for %s", stage.name)

    def stage_done(self, stage: TurnStage, *, ms: int, score: int | None = None) -> None:
        try:
            self._started_at.pop(stage.name, None)
            payload: dict[str, object] = {"stage": stage.name, "phase": "done", "ms": ms}
            if score is not None:
                payload["score"] = score
            self._queue.put_nowait(("stage", payload))
        except Exception:
            logger.exception("stage_done reporting failed for %s", stage.name)

    def mark_done(self) -> None:
        """Signal the business flow finished; unblocks the drain loop."""

        try:
            self._queue.put_nowait(None)
        except Exception:
            logger.exception("mark_done reporting failed")

    def drain(self) -> list[tuple[str, dict[str, object]]]:
        """Non-blocking drain of all queued events (excluding the sentinel)."""

        items: list[tuple[str, dict[str, object]]] = []
        while True:
            try:
                item = self._queue.get_nowait()
            except Exception:
                break
            if item is None:
                self._finished = True
                break
            items.append(item)
        return items

    @property
    def finished(self) -> bool:
        return getattr(self, "_finished", False)


class DomainErrorCode:
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    QUALITY_NOT_PASSED = "QUALITY_NOT_PASSED"
    CUSTOMER_NOT_FOUND = "CUSTOMER_NOT_FOUND"
    CRM_WRITE_REJECTED = "CRM_WRITE_REJECTED"
    UNKNOWN_ACTION = "UNKNOWN_ACTION_NOMINATED"


class AssistantDomainError(Exception):
    """Typed domain failure carried on the SSE stream as an error event."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable

    def as_event_data(self) -> dict[str, object]:
        return {"code": self.code, "retryable": self.retryable, "message": self.message}

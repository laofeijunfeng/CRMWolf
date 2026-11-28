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
from datetime import UTC, datetime
from typing import Literal, Protocol, get_args

from app.utils.sse_encoder import SSEJsonEncoder

logger = logging.getLogger(__name__)

StageName = Literal[
    "route",
    "locate",
    "context",
    "judge",
    "propose",
    "classify",
    "structure",
    "quality_gate",
    "write",
]

_STAGE_NAMES: frozenset[str] = frozenset(get_args(StageName))


def is_stage_name(name: str) -> bool:
    return name in _STAGE_NAMES


@dataclass(frozen=True)
class TurnStage:
    name: StageName
    # What the stage works on (e.g. 部署信息), so the process line names the real object.
    subject: str | None = None

    def payload(self, phase: Literal["start", "done", "failed"]) -> dict[str, object]:
        data: dict[str, object] = {"stage": self.name, "phase": phase}
        if self.subject:
            data["subject"] = self.subject
        return data


def stage(name: str, subject: str | None = None) -> TurnStage | None:
    """Typed stage handle; an unknown name logs a warning and yields ``None``.

    Progress reporting must never break a turn, so callers treat ``None`` as
    "emit nothing" instead of raising.
    """

    if not is_stage_name(name):
        logger.warning("unknown assistant stage name skipped: %r", name)
        return None
    return TurnStage(name=name, subject=subject)  # type: ignore[arg-type]


Segment = tuple[int, int]
"""(1-based index, total) of one segment of a stage that runs in segments."""


def stage_payload(
    stage: TurnStage,
    phase: Literal["start", "done", "failed"],
    *,
    ms: int | None = None,
    score: int | None = None,
    segment: Segment | None = None,
    step_started_at: str | None = None,
) -> dict[str, object]:
    # ``TurnStage.payload`` carries the stage's subject; this only adds the measured fields.
    payload: dict[str, object] = stage.payload(phase)
    if phase == "start":
        payload["step_started_at"] = (
            step_started_at
            if step_started_at is not None
            else datetime.now(UTC).isoformat().replace("+00:00", "Z")
        )
    elif step_started_at is not None:
        payload["step_started_at"] = step_started_at
    if ms is not None:
        payload["ms"] = ms
    if score is not None:
        payload["score"] = score
    if segment is not None:
        payload["segment"] = {"index": segment[0], "total": segment[1]}
    return payload


def text_delta_payload(
    *,
    turn_id: str,
    seq: int,
    delta: str,
    message_id: str | None = None,
) -> dict[str, object]:
    """Structured payload for incremental assistant text_delta SSE events."""

    payload: dict[str, object] = {
        "turn_id": turn_id,
        "seq": seq,
        "delta": delta,
    }
    if message_id is not None:
        payload["message_id"] = message_id
    return payload


def encode_sse(event: str, data: dict[str, object]) -> str:
    """One SSE frame: named event + single-line JSON payload."""

    payload = json.dumps(data, ensure_ascii=False, cls=SSEJsonEncoder)
    return f"event: {event}\ndata: {payload}\n\n"


class ProgressReporter(Protocol):
    """Stage sink; every implementation emits nothing for a ``None`` stage."""

    def stage_start(self, stage: TurnStage | None, *, segment: Segment | None = None) -> None: ...

    def stage_done(
        self, stage: TurnStage | None, *, ms: int, score: int | None = None, segment: Segment | None = None
    ) -> None: ...

    def stage_failed(self, stage: TurnStage | None, *, segment: Segment | None = None) -> None: ...

    def emit_text_delta(self, delta: str, *, message_id: str | None = None) -> None: ...


class NullProgressReporter:
    """Drop events; default for unit tests and in-process callers."""

    def stage_start(self, stage: TurnStage | None, *, segment: Segment | None = None) -> None:
        _ = stage, segment

    def stage_done(
        self, stage: TurnStage | None, *, ms: int, score: int | None = None, segment: Segment | None = None
    ) -> None:
        _ = stage, ms, score, segment

    def stage_failed(self, stage: TurnStage | None, *, segment: Segment | None = None) -> None:
        _ = stage, segment

    def emit_text_delta(self, delta: str, *, message_id: str | None = None) -> None:
        _ = delta, message_id


class SSEProgressReporter:
    """Queue stage events for the streaming endpoint to drain.

    All methods swallow exceptions: progress reporting must not affect the
    business flow. ``ms`` is measured with ``time.monotonic`` deltas.
    """

    def __init__(self, *, turn_id: str = "") -> None:
        import asyncio

        self._queue: asyncio.Queue[tuple[str, dict[str, object]] | None] = asyncio.Queue()
        self._started_at: dict[str, float] = {}
        self._turn_id = turn_id
        self._delta_seq = 0

    def stage_start(self, stage: TurnStage | None, *, segment: Segment | None = None) -> None:
        if stage is None:
            return
        try:
            self._started_at[stage.name] = time.monotonic()
            self._queue.put_nowait(("stage", stage_payload(stage, "start", segment=segment)))
        except Exception:
            logger.exception("stage_start reporting failed for %s", stage.name)

    def stage_done(
        self, stage: TurnStage | None, *, ms: int, score: int | None = None, segment: Segment | None = None
    ) -> None:
        if stage is None:
            return
        try:
            self._started_at.pop(stage.name, None)
            self._queue.put_nowait(("stage", stage_payload(stage, "done", ms=ms, score=score, segment=segment)))
        except Exception:
            logger.exception("stage_done reporting failed for %s", stage.name)

    def stage_failed(self, stage: TurnStage | None, *, segment: Segment | None = None) -> None:
        if stage is None:
            return
        try:
            self._started_at.pop(stage.name, None)
            self._queue.put_nowait(("stage", stage_payload(stage, "failed", segment=segment)))
        except Exception:
            logger.exception("stage_failed reporting failed for %s", stage.name)

    def emit_text_delta(self, delta: str, *, message_id: str | None = None) -> None:
        if not delta:
            return
        try:
            self._delta_seq += 1
            self._queue.put_nowait(
                (
                    "text_delta",
                    text_delta_payload(
                        turn_id=self._turn_id,
                        seq=self._delta_seq,
                        delta=delta,
                        message_id=message_id,
                    ),
                )
            )
        except Exception:
            logger.exception("emit_text_delta reporting failed")

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

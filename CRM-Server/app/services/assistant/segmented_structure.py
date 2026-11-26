"""Organize a transcript over 20k characters in segments and merge the parts (CRM-167).

Each segment is one model call whose result is logged on the task before the next
call, so a recovered or reprocessed attempt resumes at the first missing segment.
"""

from __future__ import annotations

import hashlib
import time
from datetime import timedelta
from typing import TYPE_CHECKING, TypeVar

from app.models.assistant import AssistantAction
from app.services.assistant.failure_contract import (
    ATTEMPT_DEADLINE_SECONDS,
    AssistantFailureCode,
    bind_absolute_attempt_deadline,
    capture_attempt_deadline,
)
from app.services.assistant.llm_contracts import StructureDraftResult
from app.services.assistant.model_transport import AssistantLLMError
from app.services.assistant.task_state import TaskUpdate, apply_task_update
from app.services.customer_activity_ai.schemas import FollowUpContent, MeetingContent, MeetingParticipants
from app.utils.time import business_now

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.orm import Session

    from app.models.assistant import AssistantTask
    from app.services.assistant.events import ProgressReporter, TurnStage
    from app.services.assistant.intake import KindStructurer

# One model call reads at most this much user text; longer input is organized in segments.
SINGLE_CALL_LIMIT = 20_000
SEGMENT_SIZE = 6_000
# Paragraph, line, then sentence ends; a speaker turn in a transcript starts on a new line.
_BOUNDARIES = ("\n\n", "\n", "。", "\uff01", "\uff1f", ". ")
_SEGMENT_ACTION = "structure_segment"

T = TypeVar("T")


def split_transcript(text: str, size: int = SEGMENT_SIZE) -> list[tuple[int, str]]:
    """(offset, chunk) pairs that concatenate back to ``text`` exactly.

    A chunk ends at the last boundary in the second half of its window, or is cut hard.
    """

    if len(text) <= SINGLE_CALL_LIMIT:
        return [(0, text)]
    chunks: list[tuple[int, str]] = []
    start = 0
    while len(text) - start > size:
        window = text[start : start + size]
        cut = size
        for mark in _BOUNDARIES:
            at = window.rfind(mark)
            if at >= size // 2:
                cut = at + len(mark)
                break
        chunks.append((start, window[:cut]))
        start += cut
    chunks.append((start, text[start:]))
    return chunks


def _union(groups: Iterable[list[T]]) -> list[T]:
    merged: list[T] = []
    for items in groups:
        merged.extend(item for item in items if item not in merged)
    return merged


def _first(values: Iterable[str]) -> str:
    return next((value for value in values if value.strip()), "")


def _last(values: Iterable[str]) -> str:
    return _first(reversed(list(values)))


def _meeting(part: StructureDraftResult) -> MeetingContent:
    if part.content_json is not None:
        return MeetingContent.model_validate(part.content_json)
    return MeetingContent(
        meeting_subject=part.meeting_subject,
        key_minutes=[part.content] if part.content else [],
        next_step_summary=part.next_action,
    )


def _follow_up(part: StructureDraftResult) -> FollowUpContent:
    if part.content_json is not None:
        return FollowUpContent.model_validate(part.content_json)
    return FollowUpContent.model_validate(
        {"content": part.content, "next_action": part.next_action, "next_follow_time_text": part.next_follow_time_text}
    )


def merge_structured(kind: str, parts: list[tuple[int, StructureDraftResult]]) -> StructureDraftResult:
    """Deterministic merge: facts accumulate in order, the last next step wins, quotes move to full-text offsets."""

    results = [part for _, part in parts]
    if kind == "FOLLOW_UP":
        follow_ups = [_follow_up(part) for part in results]
        next_action = _last(item.next_action for item in follow_ups)
        follow_up = FollowUpContent(
            content="\n".join(item.content for item in follow_ups if item.content.strip()),
            customer_feedback="\n".join(
                item.customer_feedback for item in follow_ups if item.customer_feedback.strip()
            ),
            current_progress="\n".join(item.current_progress for item in follow_ups if item.current_progress.strip()),
            risks=_union(item.risks for item in follow_ups),
            next_action=next_action,
            next_action_absence_reason="" if next_action else _last(
                item.next_action_absence_reason for item in follow_ups
            ),
            next_follow_time_text=_last(item.next_follow_time_text for item in follow_ups),
        )
        content = follow_up.content
        content_json = follow_up.model_dump(mode="json")
    else:
        meetings = [_meeting(part) for part in results]
        next_step = _last(item.next_step_summary for item in meetings)
        meeting = MeetingContent(
            meeting_subject=_first(item.meeting_subject for item in meetings),
            meeting_background=_first(item.meeting_background for item in meetings),
            communication_context=_first(item.communication_context for item in meetings),
            participants=MeetingParticipants(
                internal=_union(item.participants.internal for item in meetings),
                customer=_union(item.participants.customer for item in meetings),
            ),
            key_minutes=_union(item.key_minutes for item in meetings),
            qa_items=_union(item.qa_items for item in meetings),
            requirements=_union(item.requirements for item in meetings),
            concerns_or_objections=_union(item.concerns_or_objections for item in meetings),
            risks=_union(item.risks for item in meetings),
            decisions_or_commitments=_union(item.decisions_or_commitments for item in meetings),
            action_items=_union(item.action_items for item in meetings),
            next_step_summary=next_step,
            next_action_absence_reason="" if next_step else _last(
                item.next_action_absence_reason for item in meetings
            ),
        )
        content = "\n".join(meeting.key_minutes)
        content_json = meeting.model_dump(mode="json")
    return StructureDraftResult(
        kind_confirmed=results[0].kind_confirmed,
        content=content,
        customer_name=_first(part.customer_name for part in results),
        next_action=_last(part.next_action for part in results),
        next_follow_time_text=_last(part.next_follow_time_text for part in results),
        meeting_subject=_first(part.meeting_subject for part in results),
        participants="\u3001".join(_union([part.participants] for part in results if part.participants.strip())),
        content_json=content_json,
        # Action refs are only unique inside one call.
        temporal_mentions=[
            mention.model_copy(update={
                "quote_start": mention.quote_start + offset,
                "quote_end": mention.quote_end + offset,
                "action_ref": f"s{index}-{mention.action_ref}"[:64] if mention.action_ref else "",
            })
            for index, (offset, part) in enumerate(parts, start=1)
            for mention in part.temporal_mentions
        ],
        actions=[
            action.model_copy(update={
                "quote_start": action.quote_start + offset,
                "quote_end": action.quote_end + offset,
                "action_ref": f"s{index}-{action.action_ref}"[:64],
            })
            for index, (offset, part) in enumerate(parts, start=1)
            for action in part.actions
        ],
        structuring_model=_first(part.structuring_model for part in results),
    )


def _saved_parts(db: Session, task: AssistantTask, key: str) -> dict[int, StructureDraftResult]:
    """Parts logged for this exact input since the last organize that was applied to the draft."""

    rows = (
        db.query(AssistantAction)
        .filter(
            AssistantAction.task_id == task.id,
            AssistantAction.team_id == task.team_id,
            AssistantAction.action.in_((_SEGMENT_ACTION, "structure_draft")),
        )
        .order_by(AssistantAction.id)
        .all()
    )
    parts: dict[int, StructureDraftResult] = {}
    for row in rows:
        if row.action == "structure_draft":
            if row.result_json.get("accepted") is True:
                parts = {}
        elif row.input_json.get("key") == key and isinstance(index := row.input_json.get("index"), int):
            parts[index] = StructureDraftResult.model_validate(row.result_json)
    return parts


def _extend_attempt_deadline() -> None:
    """Give the next model call a full attempt window; execute_turn's reset restores the turn deadline."""

    deadline = capture_attempt_deadline()
    if deadline is not None:
        bind_absolute_attempt_deadline(max(deadline, business_now() + timedelta(seconds=ATTEMPT_DEADLINE_SECONDS)))


async def _structure_segment(
    db: Session, task: AssistantTask, structurer: KindStructurer, *, kind: str, chunk: str
) -> StructureDraftResult:
    """Read one segment; a timeout gets one more full window, since a slow reply is not a wrong one."""

    _extend_attempt_deadline()
    try:
        return await structurer.structure(db, team_id=task.team_id, kind=kind, user_text=chunk)
    except AssistantLLMError as exc:
        if exc.code is not AssistantFailureCode.UPSTREAM_TIMEOUT:
            raise
    _extend_attempt_deadline()
    return await structurer.structure(db, team_id=task.team_id, kind=kind, user_text=chunk)


async def structure_in_segments(
    db: Session,
    task: AssistantTask,
    structurer: KindStructurer,
    *,
    kind: str,
    text: str,
    reporter: ProgressReporter,
    stage: TurnStage | None,
) -> StructureDraftResult:
    """Organize each segment once and merge. Commits each part; the caller owns failure handling."""

    chunks = split_transcript(text)
    key = hashlib.sha256(f"{kind}\n{text}".encode()).hexdigest()
    saved = _saved_parts(db, task, key)
    total = len(chunks)
    parts: list[tuple[int, StructureDraftResult]] = []
    for index, (offset, chunk) in enumerate(chunks, start=1):
        part = saved.get(index)
        if part is None:
            segment = (index, total)
            reporter.stage_start(stage, segment=segment)
            started = time.monotonic()
            try:
                part = await _structure_segment(db, task, structurer, kind=kind, chunk=chunk)
            except Exception:
                reporter.stage_failed(stage, segment=segment)
                raise
            reporter.stage_done(stage, ms=int((time.monotonic() - started) * 1000), segment=segment)
            apply_task_update(
                db,
                task,
                TaskUpdate(
                    action_actor="SYSTEM",
                    action_name=_SEGMENT_ACTION,
                    action_input={"key": key, "index": index, "total": total},
                    action_result=part.model_dump(mode="json"),
                ),
            )
            db.commit()
        parts.append((offset, part))
    # Quality scoring after the last segment gets its own window too.
    _extend_attempt_deadline()
    return merge_structured(kind, parts)

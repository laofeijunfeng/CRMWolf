"""Checkpoint-safe capability for retrying a validated PendingTask resume.

A Root-owned interrupt may be resumed successfully while the authoritative
child checkpoint is temporarily unavailable.  The user's already-validated
resume payload must survive that infrastructure failure so recovery can retry
without asking the user to confirm the same action again.
"""

from __future__ import annotations

from typing import TypedDict

from app.services.agent.interrupts import (
    AgentInterruptPayload,
    AgentResumePayload,
    interrupt_payload_from_json,
    validate_resume_payload,
)
from app.services.agent.pending_continuation import (
    PendingTaskContinuationRef,
    pending_task_continuation_from_json,
)
from app.services.agent.types import coerce_json_dict

PENDING_TASK_DEFERRED_RESUME_SCHEMA_VERSION = "agent.pending-task.deferred-resume.v1"


class PendingTaskDeferredResume(TypedDict):
    """One authenticated resume capability bound to one exact child interrupt."""

    schema_version: str
    continuation: PendingTaskContinuationRef
    interrupt: AgentInterruptPayload
    resume_payload: AgentResumePayload


def build_pending_task_deferred_resume(
    *,
    continuation: PendingTaskContinuationRef,
    interrupt: AgentInterruptPayload,
    resume_payload: AgentResumePayload,
) -> PendingTaskDeferredResume:
    """Build a durable retry capability after the Root accepted user input."""

    authenticated_continuation = pending_task_continuation_from_json(
        continuation,
        expected_team_id=continuation["team_id"],
        expected_user_id=continuation["user_id"],
        expected_session_id=continuation["session_id"],
        expected_thread_id=continuation["thread_id"],
    )
    interrupt_continuation = pending_task_continuation_from_json(
        interrupt.get("checkpoint_ref"),
        expected_team_id=continuation["team_id"],
        expected_user_id=continuation["user_id"],
        expected_session_id=continuation["session_id"],
        expected_thread_id=continuation["thread_id"],
    )
    if authenticated_continuation is None or interrupt_continuation != authenticated_continuation:
        raise ValueError("deferred resume continuation does not own interrupt")
    validate_resume_payload(resume_payload, current_interrupt=interrupt)
    return {
        "schema_version": PENDING_TASK_DEFERRED_RESUME_SCHEMA_VERSION,
        "continuation": authenticated_continuation,
        "interrupt": interrupt,
        "resume_payload": resume_payload,
    }


def pending_task_deferred_resume_from_json(
    value: object,
    *,
    expected_team_id: int,
    expected_user_id: int,
    expected_session_id: int,
    expected_thread_id: str,
    expected_interrupt: AgentInterruptPayload | None = None,
) -> PendingTaskDeferredResume | None:
    """Parse and authenticate a deferred resume against the owning Root thread."""

    payload = coerce_json_dict(value)
    if payload.get("schema_version") != PENDING_TASK_DEFERRED_RESUME_SCHEMA_VERSION:
        return None
    continuation = pending_task_continuation_from_json(
        payload.get("continuation"),
        expected_team_id=expected_team_id,
        expected_user_id=expected_user_id,
        expected_session_id=expected_session_id,
        expected_thread_id=expected_thread_id,
    )
    interrupt = interrupt_payload_from_json(payload.get("interrupt"))
    resume_payload = coerce_json_dict(payload.get("resume_payload"))
    if continuation is None or interrupt is None or not resume_payload:
        return None
    interrupt_continuation = pending_task_continuation_from_json(
        interrupt.get("checkpoint_ref"),
        expected_team_id=expected_team_id,
        expected_user_id=expected_user_id,
        expected_session_id=expected_session_id,
        expected_thread_id=expected_thread_id,
    )
    if interrupt_continuation != continuation:
        return None
    if expected_interrupt is not None:
        normalized_expected = interrupt_payload_from_json(expected_interrupt)
        if normalized_expected is None or coerce_json_dict(interrupt) != coerce_json_dict(normalized_expected):
            return None
    try:
        validate_resume_payload(resume_payload, current_interrupt=interrupt)
    except ValueError:
        return None
    return {
        "schema_version": PENDING_TASK_DEFERRED_RESUME_SCHEMA_VERSION,
        "continuation": continuation,
        "interrupt": interrupt,
        "resume_payload": resume_payload,
    }

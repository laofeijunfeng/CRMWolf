"""Tests for exact, checkpoint-owned PendingTask deferred resume capabilities."""

from __future__ import annotations

import pytest

from app.services.agent.pending_continuation import new_pending_task_continuation
from app.services.agent.pending_resume import (
    build_pending_task_deferred_resume,
    pending_task_deferred_resume_from_json,
)


def _continuation():
    return new_pending_task_continuation(
        team_id=1,
        user_id=2,
        session_id=3,
        task_id=101,
        root_thread_id="crm_agent:1:2:3:session-key",
        checkpoint_ns="pending_task_subgraph:child-1",
    )


def _interrupt(continuation=None):
    return {
        "schema_version": "agent.interrupt.v1",
        "type": "confirm",
        "reason": "write_confirmation",
        "business_action": "confirm_action",
        "allowed_resume_actions": ["approve", "edit", "reject", "cancel"],
        "task_projection_id": 101,
        "task_projection_key": "task-101",
        "interaction": {
            "schema_version": "agent.interaction.v1",
            "type": "confirm",
            "business_action": "confirm_action",
            "prompt": "确认记录跟进？",
        },
        "checkpoint_ref": continuation or _continuation(),
    }


def _resume_payload():
    return {
        "action": "approve",
        "content": "确认",
        "source": "web",
        "metadata": {},
        "task_projection_id": 101,
        "task_projection_key": "task-101",
        "interrupt_reason": "write_confirmation",
        "business_action": "confirm_action",
    }


def _parse(value, *, expected_interrupt=None, **overrides):
    expected = {
        "expected_team_id": 1,
        "expected_user_id": 2,
        "expected_session_id": 3,
        "expected_thread_id": "crm_agent:1:2:3:session-key",
        "expected_interrupt": expected_interrupt,
    }
    expected.update(overrides)
    return pending_task_deferred_resume_from_json(value, **expected)


def test_deferred_resume_round_trips_as_exact_root_owned_capability():
    continuation = _continuation()
    interrupt = _interrupt(continuation)
    resume_payload = _resume_payload()

    capability = build_pending_task_deferred_resume(
        continuation=continuation,
        interrupt=interrupt,
        resume_payload=resume_payload,
    )

    assert _parse(capability, expected_interrupt=interrupt) == capability


@pytest.mark.parametrize(
    ("expected_field", "unexpected_value"),
    [
        ("expected_team_id", 99),
        ("expected_user_id", 99),
        ("expected_session_id", 99),
        ("expected_thread_id", "crm_agent:1:2:3:other"),
    ],
)
def test_deferred_resume_rejects_non_owning_root_identity(expected_field, unexpected_value):
    continuation = _continuation()
    capability = build_pending_task_deferred_resume(
        continuation=continuation,
        interrupt=_interrupt(continuation),
        resume_payload=_resume_payload(),
    )

    assert _parse(capability, **{expected_field: unexpected_value}) is None


def test_deferred_resume_rejects_interrupt_owned_by_another_child_checkpoint():
    continuation = _continuation()
    other_continuation = new_pending_task_continuation(
        team_id=1,
        user_id=2,
        session_id=3,
        task_id=101,
        root_thread_id="crm_agent:1:2:3:session-key",
        checkpoint_ns="pending_task_subgraph:child-2",
    )

    with pytest.raises(ValueError, match="does not own interrupt"):
        build_pending_task_deferred_resume(
            continuation=continuation,
            interrupt=_interrupt(other_continuation),
            resume_payload=_resume_payload(),
        )


def test_deferred_resume_rejects_payload_not_allowed_by_owning_interrupt():
    continuation = _continuation()
    capability = {
        "schema_version": "agent.pending-task.deferred-resume.v1",
        "continuation": continuation,
        "interrupt": _interrupt(continuation),
        "resume_payload": {**_resume_payload(), "action": "submit_text"},
    }

    assert _parse(capability) is None


def test_deferred_resume_rejects_different_current_root_interrupt():
    continuation = _continuation()
    interrupt = _interrupt(continuation)
    capability = build_pending_task_deferred_resume(
        continuation=continuation,
        interrupt=interrupt,
        resume_payload=_resume_payload(),
    )
    different_interrupt = {
        **interrupt,
        "interaction": {
            **interrupt["interaction"],
            "prompt": "另一个等待用户确认的问题",
        },
    }

    assert _parse(capability, expected_interrupt=different_interrupt) is None

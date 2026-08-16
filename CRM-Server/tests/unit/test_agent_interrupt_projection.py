"""Contract tests for routing checkpoint-visible interrupts to their owner."""

from app.services.agent.interrupt_projection import classify_interrupt_projection
from app.services.agent.pending_continuation import (
    bind_pending_task_namespace,
    new_pending_task_continuation,
)


def _continuation():
    return bind_pending_task_namespace(
        new_pending_task_continuation(
            team_id=7,
            user_id=11,
            session_id=13,
            task_id=17,
            continuation_id="turn-1",
        ),
        "pending_task_subgraph:child-1",
    )


def _interrupt(checkpoint_ref=None):
    payload = {
        "reason": "write_confirmation",
        "source_event": "confirmation_required",
        "interaction": {"interaction_id": "int-1"},
    }
    if checkpoint_ref is not None:
        payload["checkpoint_ref"] = checkpoint_ref
    return payload


def test_interrupt_without_child_continuation_is_root_owned():
    result = classify_interrupt_projection(
        _interrupt(),
        team_id=7,
        user_id=11,
        session_id=13,
    )

    assert result.owner == "root"
    assert result.continuation is None
    assert result.failure_reason is None


def test_interrupt_with_authenticated_continuation_is_pending_task_owned():
    continuation = _continuation()

    result = classify_interrupt_projection(
        _interrupt(continuation),
        team_id=7,
        user_id=11,
        session_id=13,
    )

    assert result.owner == "pending_task"
    assert result.continuation == continuation


def test_cross_owner_child_continuation_fails_closed():
    continuation = _continuation()

    for expected_scope in (
        {"team_id": 8, "user_id": 11, "session_id": 13},
        {"team_id": 7, "user_id": 12, "session_id": 13},
        {"team_id": 7, "user_id": 11, "session_id": 14},
    ):
        result = classify_interrupt_projection(_interrupt(continuation), **expected_scope)
        assert result.owner == "invalid_pending_task"
        assert result.failure_reason == "invalid_continuation"


def test_tampered_thread_or_namespace_cannot_fall_back_to_root():
    continuation = _continuation()
    tampered_refs = [
        {**continuation, "thread_id": "crm_agent_pending:7:11:13:999:turn-1"},
        {**continuation, "checkpoint_ns": "other_graph:child-1"},
        {**continuation, "runtime": "crm_agent_root"},
    ]

    for checkpoint_ref in tampered_refs:
        result = classify_interrupt_projection(
            _interrupt(checkpoint_ref),
            team_id=7,
            user_id=11,
            session_id=13,
        )
        assert result.owner == "invalid_pending_task"
        assert result.continuation is None
        assert result.failure_reason == "invalid_continuation"

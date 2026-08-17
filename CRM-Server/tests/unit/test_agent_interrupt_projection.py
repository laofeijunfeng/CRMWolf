"""Contract tests for routing checkpoint-visible interrupts to their owner."""

from app.services.agent.interrupt_projection import classify_interrupt_projection
from app.services.agent.pending_continuation import new_pending_task_continuation

ROOT_THREAD_ID = "crm_agent:7:11:13:session-a"
CHILD_NAMESPACE = "pending_task_subgraph:child-1"


def _continuation():
    return new_pending_task_continuation(
        team_id=7,
        user_id=11,
        session_id=13,
        task_id=17,
        root_thread_id=ROOT_THREAD_ID,
        checkpoint_ns=CHILD_NAMESPACE,
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
        thread_id=ROOT_THREAD_ID,
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
        thread_id=ROOT_THREAD_ID,
    )

    assert result.owner == "pending_task"
    assert result.continuation == continuation


def test_root_owned_continuation_must_match_current_root_thread():
    continuation = _continuation()

    accepted = classify_interrupt_projection(
        _interrupt(continuation),
        team_id=7,
        user_id=11,
        session_id=13,
        thread_id=ROOT_THREAD_ID,
    )
    rejected = classify_interrupt_projection(
        _interrupt(continuation),
        team_id=7,
        user_id=11,
        session_id=13,
        thread_id="crm_agent:7:11:13:session-b",
    )

    assert accepted.owner == "pending_task"
    assert rejected.owner == "invalid_pending_task"
    assert rejected.failure_reason == "invalid_continuation"


def test_cross_owner_child_continuation_fails_closed():
    continuation = _continuation()

    for expected_scope in (
        {"team_id": 8, "user_id": 11, "session_id": 13},
        {"team_id": 7, "user_id": 12, "session_id": 13},
        {"team_id": 7, "user_id": 11, "session_id": 14},
    ):
        result = classify_interrupt_projection(
            _interrupt(continuation),
            **expected_scope,
            thread_id=ROOT_THREAD_ID,
        )
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
            thread_id=ROOT_THREAD_ID,
        )
        assert result.owner == "invalid_pending_task"
        assert result.continuation is None
        assert result.failure_reason == "invalid_continuation"


def test_deserialized_legacy_child_claim_fails_closed_instead_of_becoming_root_owned():
    from app.services.agent.interrupts import interrupt_payload_from_json

    interrupt = interrupt_payload_from_json({
        "schema_version": "agent.interrupt.v1",
        "type": "confirm",
        "reason": "write_confirmation",
        "business_action": "create_opportunity",
        "checkpoint_ref": {
            "runtime": "crm_agent_pending_task",
            "thread_id": "crm_agent_pending:7:11:13:17",
            "checkpoint_ns": CHILD_NAMESPACE,
            "team_id": 7,
            "user_id": 11,
            "session_id": 13,
            "task_id": 17,
        },
    })

    assert interrupt is not None
    result = classify_interrupt_projection(
        interrupt,
        team_id=7,
        user_id=11,
        session_id=13,
        thread_id=ROOT_THREAD_ID,
    )

    assert result.owner == "invalid_pending_task"
    assert result.failure_reason == "invalid_continuation"

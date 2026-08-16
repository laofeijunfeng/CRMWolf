"""Tests for the pending-task durable continuation identity module."""

from app.services.agent.pending_continuation import (
    PENDING_TASK_RUNTIME,
    bind_pending_task_namespace,
    new_pending_task_continuation,
    pending_task_checkpoint_config,
    pending_task_continuation_from_json,
    pending_task_thread_id,
)


def test_new_continuation_has_unique_canonical_thread_identity():
    first = new_pending_task_continuation(team_id=1, user_id=2, session_id=3, task_id=101)
    second = new_pending_task_continuation(team_id=1, user_id=2, session_id=3, task_id=101)

    assert first["runtime"] == PENDING_TASK_RUNTIME
    assert first["continuation_id"]
    assert first["thread_id"] == pending_task_thread_id(
        team_id=1,
        user_id=2,
        session_id=3,
        task_id=101,
        continuation_id=first["continuation_id"],
    )
    assert first["thread_id"] != second["thread_id"]


def test_continuation_round_trips_and_projects_checkpoint_config():
    continuation = new_pending_task_continuation(
        team_id=1,
        user_id=2,
        session_id=3,
        task_id=101,
        continuation_id="turn-1",
    )
    continuation = bind_pending_task_namespace(
        continuation,
        "pending_task_subgraph:child-1",
    )

    parsed = pending_task_continuation_from_json(
        continuation,
        expected_team_id=1,
        expected_user_id=2,
        expected_session_id=3,
    )

    assert parsed == continuation
    assert pending_task_checkpoint_config(parsed) == {
        "configurable": {
            "thread_id": "crm_agent_pending:1:2:3:101:turn-1",
            "checkpoint_ns": "pending_task_subgraph:child-1",
        },
        "metadata": {
            "team_id": 1,
            "user_id": 2,
            "session_id": 3,
            "task_id": 101,
            "runtime": PENDING_TASK_RUNTIME,
            "runtime_namespace": PENDING_TASK_RUNTIME,
            "continuation_id": "turn-1",
        },
    }


def test_continuation_rejects_scope_or_locator_tampering():
    continuation = new_pending_task_continuation(
        team_id=1,
        user_id=2,
        session_id=3,
        task_id=101,
        continuation_id="turn-1",
    )

    assert pending_task_continuation_from_json(continuation, expected_team_id=9) is None
    assert pending_task_continuation_from_json(continuation, expected_user_id=9) is None
    assert pending_task_continuation_from_json(continuation, expected_session_id=9) is None
    assert (
        pending_task_continuation_from_json(
            {
                **continuation,
                "thread_id": "crm_agent_pending:9:2:3:101:turn-1",
            }
        )
        is None
    )
    assert (
        pending_task_continuation_from_json(
            {
                **continuation,
                "checkpoint_ns": "foreign_graph:child-1",
            }
        )
        is None
    )


def test_legacy_continuation_without_invocation_id_remains_readable():
    legacy = {
        "runtime": PENDING_TASK_RUNTIME,
        "thread_id": "crm_agent_pending:1:2:3:101",
        "checkpoint_ns": "pending_task_subgraph:legacy-child",
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "task_id": 101,
    }

    assert pending_task_continuation_from_json(legacy) == legacy

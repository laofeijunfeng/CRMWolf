"""Tests for the V2 root-owned pending-task continuation contract."""

from app.services.agent.pending_continuation import (
    PENDING_TASK_CONTINUATION_SCHEMA_VERSION,
    PENDING_TASK_RUNTIME,
    new_pending_task_continuation,
    pending_task_checkpoint_config,
    pending_task_continuation_from_json,
    pending_task_continuation_shape_from_json,
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


def test_v2_continuation_is_root_owned_and_projects_exact_checkpoint_config():
    continuation = _continuation()

    assert continuation["schema_version"] == PENDING_TASK_CONTINUATION_SCHEMA_VERSION
    assert continuation["runtime"] == PENDING_TASK_RUNTIME
    assert continuation["persistence_scope"] == "root"
    assert continuation["thread_id"] == "crm_agent:1:2:3:session-key"
    assert continuation["checkpoint_ns"] == "pending_task_subgraph:child-1"
    checkpoint_config = pending_task_checkpoint_config(continuation)
    assert checkpoint_config["configurable"] == {
        "thread_id": "crm_agent:1:2:3:session-key",
        "checkpoint_ns": "pending_task_subgraph:child-1",
    }
    assert checkpoint_config["metadata"]["continuation_thread_id"] == continuation["thread_id"]
    assert (
        checkpoint_config["metadata"]["continuation_checkpoint_ns"]
        == continuation["checkpoint_ns"]
    )


def test_v2_continuation_identity_is_stable_for_same_root_invocation():
    assert _continuation()["continuation_id"] == _continuation()["continuation_id"]


def test_v2_continuation_requires_authenticated_root_thread():
    continuation = _continuation()

    assert pending_task_continuation_from_json(
        continuation,
        expected_team_id=1,
        expected_user_id=2,
        expected_session_id=3,
        expected_thread_id="crm_agent:1:2:3:session-key",
    ) == continuation
    assert pending_task_continuation_from_json(continuation) is None
    assert pending_task_continuation_from_json(
        continuation,
        expected_thread_id="crm_agent:1:2:3:other",
    ) is None


def test_legacy_child_continuation_is_rejected_at_cutover():
    legacy = {
        "runtime": PENDING_TASK_RUNTIME,
        "thread_id": "crm_agent_pending:1:2:3:101:old",
        "checkpoint_ns": "pending_task_subgraph:legacy-child",
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "task_id": 101,
    }

    assert pending_task_continuation_shape_from_json(legacy) is None
    assert pending_task_continuation_from_json(
        legacy,
        expected_thread_id="crm_agent:1:2:3:session-key",
    ) is None


def test_tampered_namespace_or_identity_is_rejected():
    continuation = _continuation()

    assert pending_task_continuation_shape_from_json(
        {**continuation, "checkpoint_ns": "pending_task_subgraph:other"}
    ) is None
    assert pending_task_continuation_shape_from_json(
        {**continuation, "thread_id": "crm_agent:1:2:3:other"}
    ) is None

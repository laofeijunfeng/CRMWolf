from types import SimpleNamespace

import pytest
from langgraph.types import Interrupt

from app.services.agent.pending_checkpoint import PendingTaskCheckpointStore
from app.services.agent.pending_continuation import new_pending_task_continuation


class FakeCheckpointReader:
    def __init__(self, tuples):
        self.tuples = tuples
        self.get_calls = []
        self.list_calls = []

    async def aget_tuple(self, config):
        self.get_calls.append(config)
        return self.tuples[0] if self.tuples else None

    async def alist(self, config, *, filter=None, before=None, limit=None):
        self.list_calls.append({"config": config, "limit": limit})
        for item in self.tuples:
            yield item


class FailingCheckpointReader:
    async def aget_tuple(self, config):
        raise RuntimeError("checkpoint backend unavailable")


def _ref():
    return new_pending_task_continuation(
        team_id=2,
        user_id=3,
        session_id=4,
        task_id=101,
        root_thread_id="crm_agent:2:3:4:session-key",
        checkpoint_ns="pending_task_subgraph:expected",
    )


def _tuple(interrupt_payload):
    return SimpleNamespace(
        config={"configurable": {"thread_id": _ref()["thread_id"], "checkpoint_ns": _ref()["checkpoint_ns"]}},
        checkpoint={"channel_values": {"task_projection": {"id": 101}}},
        pending_writes=[("task-1", "__interrupt__", [Interrupt(value=interrupt_payload, id="interrupt-1")])],
    )


@pytest.mark.asyncio
async def test_checkpoint_store_loads_only_exact_root_owned_locator():
    interrupt_payload = {
        "source_event": "confirmation_required",
        "business_action": "create_opportunity",
        "interaction": {"interaction_id": "int_pending_1"},
    }
    reader = FakeCheckpointReader([_tuple(interrupt_payload)])

    result = await PendingTaskCheckpointStore(reader).load_result(_ref(), expected_interrupt=interrupt_payload)

    assert result.snapshot is not None
    assert result.snapshot.values["task_projection"] == {"id": 101}
    assert reader.get_calls == [{"configurable": {"thread_id": _ref()["thread_id"], "checkpoint_ns": _ref()["checkpoint_ns"]}}]
    assert reader.list_calls == []


@pytest.mark.asyncio
async def test_checkpoint_store_distinguishes_missing_locator():
    result = await PendingTaskCheckpointStore(FakeCheckpointReader([])).load_result(_ref())

    assert result.snapshot is None
    assert result.failure_reason == "checkpoint_locator_not_found"


@pytest.mark.asyncio
async def test_checkpoint_store_classifies_reader_exception_as_retryable_recovery_failure():
    result = await PendingTaskCheckpointStore(FailingCheckpointReader()).load_result(_ref())

    assert result.snapshot is None
    assert result.failure_reason == "checkpoint_recovery_exception"


@pytest.mark.asyncio
async def test_checkpoint_store_reports_corrupt_exact_locator():
    corrupt_tuple = SimpleNamespace(
        config={
            "configurable": {
                "thread_id": _ref()["thread_id"],
                "checkpoint_ns": _ref()["checkpoint_ns"],
            }
        },
        checkpoint={"channel_values": None},
        pending_writes=(),
    )

    result = await PendingTaskCheckpointStore(
        FakeCheckpointReader([corrupt_tuple])
    ).load_result(_ref())

    assert result.snapshot is None
    assert result.failure_reason == "checkpoint_corrupt"


@pytest.mark.asyncio
async def test_checkpoint_store_rejects_tuple_from_a_different_exact_locator():
    mismatched_tuple = SimpleNamespace(
        config={
            "configurable": {
                "thread_id": "crm_agent:other-thread",
                "checkpoint_ns": "pending_task_subgraph:other-namespace",
            }
        },
        checkpoint={"channel_values": {"task_projection": {"id": 101}}},
        pending_writes=(),
    )

    result = await PendingTaskCheckpointStore(
        FakeCheckpointReader([mismatched_tuple])
    ).load_result(_ref())

    assert result.snapshot is None
    assert result.failure_reason == "checkpoint_corrupt"


@pytest.mark.asyncio
async def test_checkpoint_store_distinguishes_interrupt_identity_mismatch():
    stored = {"interaction": {"interaction_id": "stored"}}
    expected = {"interaction": {"interaction_id": "expected"}}

    result = await PendingTaskCheckpointStore(FakeCheckpointReader([_tuple(stored)])).load_result(
        _ref(), expected_interrupt=expected
    )

    assert result.snapshot is None
    assert result.failure_reason == "checkpoint_interrupt_not_found"


@pytest.mark.asyncio
async def test_checkpoint_store_never_revives_matching_interrupt_from_history():
    current = {"interaction": {"interaction_id": "current"}}
    historical = {"interaction": {"interaction_id": "expected"}}
    reader = FakeCheckpointReader([_tuple(current), _tuple(historical)])

    result = await PendingTaskCheckpointStore(reader).load_result(
        _ref(),
        expected_interrupt=historical,
    )

    assert result.snapshot is None
    assert result.failure_reason == "checkpoint_interrupt_not_found"
    assert reader.list_calls == []

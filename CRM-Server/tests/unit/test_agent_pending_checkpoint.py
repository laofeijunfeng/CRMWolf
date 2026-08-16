"""Tests for the pending-task durable checkpoint adapter."""

from types import SimpleNamespace

import pytest
from langgraph.types import Interrupt

from app.services.agent.pending_checkpoint import PendingTaskCheckpointStore


class FakeCheckpointReader:
    def __init__(self, tuples):
        self.tuples = tuples
        self.get_calls = []
        self.list_calls = []

    async def aget_tuple(self, config):
        self.get_calls.append(config)
        return None

    async def alist(self, config, *, filter=None, before=None, limit=None):
        self.list_calls.append(
            {
                "config": config,
                "filter": filter,
                "before": before,
                "limit": limit,
            }
        )
        requested = (config or {}).get("configurable", {})
        requested_thread_id = requested.get("thread_id")
        requested_checkpoint_ns = requested.get("checkpoint_ns")
        for checkpoint_tuple in self.tuples:
            actual = checkpoint_tuple.config.get("configurable", {})
            if actual.get("thread_id") != requested_thread_id:
                continue
            if requested_checkpoint_ns is not None and actual.get("checkpoint_ns") != requested_checkpoint_ns:
                continue
            yield checkpoint_tuple


@pytest.mark.asyncio
async def test_checkpoint_store_recovers_dynamic_child_namespace_from_thread_history():
    interrupt_payload = {
        "source_event": "confirmation_required",
        "business_action": "create_opportunity",
        "interaction": {"interaction_id": "int_pending_1"},
    }
    reader = FakeCheckpointReader(
        [
            SimpleNamespace(
                config={
                    "configurable": {
                        "thread_id": "crm_agent_pending:2:3:4:101",
                        "checkpoint_ns": "pending_task_subgraph:dynamic-1",
                    }
                },
                checkpoint={
                    "channel_values": {
                        "handled": True,
                        "task_projection": {"id": 101},
                        "assistant_content": "商机信息齐了。要创建商机吗？",  # noqa: RUF001
                    }
                },
                pending_writes=[
                    (
                        "task-1",
                        "__interrupt__",
                        [Interrupt(value=interrupt_payload, id="interrupt-1")],
                    )
                ],
            )
        ]
    )
    store = PendingTaskCheckpointStore(reader)

    snapshot = await store.load(
        {
            "thread_id": "crm_agent_pending:2:3:4:101",
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "task_id": 101,
        },
        expected_interrupt=interrupt_payload,
    )

    assert snapshot is not None
    assert snapshot.ref["checkpoint_ns"] == "pending_task_subgraph:dynamic-1"
    assert snapshot.values["task_projection"] == {"id": 101}
    assert snapshot.interrupts[0].value == interrupt_payload
    assert reader.get_calls == []
    assert reader.list_calls[0]["config"] == {"configurable": {"thread_id": "crm_agent_pending:2:3:4:101"}}


@pytest.mark.asyncio
async def test_checkpoint_store_does_not_cross_explicit_child_namespace():
    interrupt_payload = {
        "source_event": "confirmation_required",
        "business_action": "create_opportunity",
        "interaction": {"interaction_id": "int_pending_1"},
    }
    reader = FakeCheckpointReader(
        [
            SimpleNamespace(
                config={
                    "configurable": {
                        "thread_id": "crm_agent_pending:2:3:4:101",
                        "checkpoint_ns": "pending_task_subgraph:other",
                    }
                },
                checkpoint={"channel_values": {"task_projection": {"id": 999}}},
                pending_writes=[
                    (
                        "task-other",
                        "__interrupt__",
                        [Interrupt(value=interrupt_payload, id="interrupt-other")],
                    )
                ],
            )
        ]
    )
    store = PendingTaskCheckpointStore(reader)

    snapshot = await store.load(
        {
            "thread_id": "crm_agent_pending:2:3:4:101",
            "checkpoint_ns": "pending_task_subgraph:expected",
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "task_id": 101,
        },
        expected_interrupt=interrupt_payload,
    )

    assert snapshot is None
    assert reader.get_calls == [
        {
            "configurable": {
                "thread_id": "crm_agent_pending:2:3:4:101",
                "checkpoint_ns": "pending_task_subgraph:expected",
            }
        }
    ]
    assert reader.list_calls[0]["config"] == reader.get_calls[0]

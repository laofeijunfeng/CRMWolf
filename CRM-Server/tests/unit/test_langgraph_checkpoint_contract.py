"""Persistence-contract tests for the shared LangGraph SQL checkpointer."""

from types import SimpleNamespace

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services.agent.input import AgentTurnInput
from app.services.agent.pending_graph import PendingTaskGraphService
from app.services.agent.root_runtime import AgentRootRuntime
from app.services.agent.state import AgentRootRuntimeSideEffects, AgentRuntimeContext
from app.services.customer_activity_ai.checkpointer import SQLAlchemyCheckpointSaver
from tests.unit.test_agent_root_runtime import (
    FakeConfirmedTaskWithNextGraphService,
    FakeConfirmingPendingGraphService,
    FakeNativeInterruptInteractionGraphService,
    FakeNativeInterruptPreflightGraphService,
    FakePendingTaskSideEffectHandler,
    waiting_task_stub,
)

PENDING_RUNTIME = "crm_agent_pending_task"
PENDING_NAMESPACE = "pending_task_subgraph:continuation-33e9abedad0a30b6222ecb859eec012b"


def _create_checkpoint_tables(engine) -> None:
    statements = (
        """
        CREATE TABLE crm_langgraph_checkpoints (
            thread_id VARCHAR(191) NOT NULL,
            checkpoint_ns VARCHAR(191) NOT NULL DEFAULT '',
            checkpoint_id VARCHAR(191) NOT NULL,
            parent_checkpoint_id VARCHAR(191),
            checkpoint_type VARCHAR(100) NOT NULL,
            checkpoint_blob BLOB NOT NULL,
            metadata_type VARCHAR(100) NOT NULL,
            metadata_blob BLOB NOT NULL,
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
        )
        """,
        """
        CREATE TABLE crm_langgraph_checkpoint_blobs (
            thread_id VARCHAR(191) NOT NULL,
            checkpoint_ns VARCHAR(191) NOT NULL DEFAULT '',
            channel VARCHAR(191) NOT NULL,
            version VARCHAR(191) NOT NULL,
            serde_type VARCHAR(100) NOT NULL,
            `blob` BLOB NOT NULL,
            PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
        )
        """,
        """
        CREATE TABLE crm_langgraph_checkpoint_writes (
            thread_id VARCHAR(191) NOT NULL,
            checkpoint_ns VARCHAR(191) NOT NULL DEFAULT '',
            checkpoint_id VARCHAR(191) NOT NULL,
            task_id VARCHAR(191) NOT NULL,
            write_idx INTEGER NOT NULL,
            task_path VARCHAR(255) NOT NULL DEFAULT '',
            channel VARCHAR(191) NOT NULL,
            serde_type VARCHAR(100) NOT NULL,
            `blob` BLOB NOT NULL,
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx)
        )
        """,
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


@pytest.fixture
def checkpoint_store():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _create_checkpoint_tables(engine)
    try:
        yield engine, SQLAlchemyCheckpointSaver(engine)
    finally:
        engine.dispose()


def _pending_config(*, checkpoint_ns: str | None):
    configurable = {
        "thread_id": "crm_agent:1:1:8:im_feishu_e5585bac9852b520f06ae40dbb7db969",
    }
    if checkpoint_ns is not None:
        configurable["checkpoint_ns"] = checkpoint_ns
    return {
        "configurable": configurable,
        "metadata": {
            "runtime": PENDING_RUNTIME,
            "runtime_namespace": PENDING_RUNTIME,
            "task_id": 109,
            "continuation_id": "33e9abedad0a30b6222ecb859eec012b",
            "continuation_thread_id": configurable["thread_id"],
            "continuation_checkpoint_ns": checkpoint_ns,
        },
    }


def test_pending_checkpoint_rejects_root_namespace_before_writing(checkpoint_store):
    engine, saver = checkpoint_store

    with pytest.raises(ValueError, match="pending-task checkpoint namespace"):
        saver.put(
            _pending_config(checkpoint_ns=None),
            empty_checkpoint(),
            {},
            {},
        )

    with engine.begin() as connection:
        checkpoint_count = connection.execute(
            text("SELECT COUNT(*) FROM crm_langgraph_checkpoints")
        ).scalar_one()

    assert checkpoint_count == 0


def test_pending_checkpoint_writes_reject_root_namespace_before_writing(checkpoint_store):
    engine, saver = checkpoint_store
    config = _pending_config(checkpoint_ns=None)
    config["configurable"]["checkpoint_id"] = "checkpoint-1"

    with pytest.raises(ValueError, match="pending-task checkpoint namespace"):
        saver.put_writes(
            config,
            [("__resume__", {"action": "approve"})],
            task_id="task-109",
        )

    with engine.begin() as connection:
        write_count = connection.execute(
            text("SELECT COUNT(*) FROM crm_langgraph_checkpoint_writes")
        ).scalar_one()

    assert write_count == 0


def test_pending_checkpoint_persists_in_exact_child_namespace(checkpoint_store):
    engine, saver = checkpoint_store

    saver.put(
        _pending_config(checkpoint_ns=PENDING_NAMESPACE),
        empty_checkpoint(),
        {},
        {},
    )

    with engine.begin() as connection:
        namespaces = connection.execute(
            text("SELECT DISTINCT checkpoint_ns FROM crm_langgraph_checkpoints")
        ).scalars().all()

    assert namespaces == [PENDING_NAMESPACE]


def test_pending_checkpoint_rejects_locator_metadata_mismatch(checkpoint_store):
    engine, saver = checkpoint_store
    config = _pending_config(checkpoint_ns=PENDING_NAMESPACE)
    config["metadata"]["continuation_checkpoint_ns"] = "pending_task_subgraph:other"

    with pytest.raises(ValueError, match="continuation locator"):
        saver.put(config, empty_checkpoint(), {}, {})

    with engine.begin() as connection:
        checkpoint_count = connection.execute(
            text("SELECT COUNT(*) FROM crm_langgraph_checkpoints")
        ).scalar_one()

    assert checkpoint_count == 0


@pytest.mark.asyncio
async def test_root_owned_pending_card_survives_sql_runtime_restart(checkpoint_store):
    engine, saver = checkpoint_store
    first_pending_runtime = PendingTaskGraphService(
        preflight_graph_service=FakeNativeInterruptPreflightGraphService(),
        interaction_graph_service=FakeNativeInterruptInteractionGraphService(),
        checkpointer=saver,
    )
    first_root_runtime = AgentRootRuntime(
        checkpointer=saver,
        pending_graph_service=first_pending_runtime,
        pending_task_side_effect_handler=FakePendingTaskSideEffectHandler(),
    )
    task = waiting_task_stub()
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=task,
        turn_input=AgentTurnInput.text("补充金额 10 万"),
        content="补充金额 10 万",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )

    waiting_state = await first_root_runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "sql-pending-contract",
            "channel": "web",
            "content": context.content,
            "turn_kind": "text",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )
    interrupt = waiting_state["current_interrupt"]
    continuation = interrupt["checkpoint_ref"]

    with engine.begin() as connection:
        child_checkpoint_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM crm_langgraph_checkpoints
                WHERE thread_id = :thread_id
                  AND checkpoint_ns = :checkpoint_ns
                """
            ),
            {
                "thread_id": continuation["thread_id"],
                "checkpoint_ns": continuation["checkpoint_ns"],
            },
        ).scalar_one()

    pending_checkpoints = list(
        saver.list(
            {"configurable": {"thread_id": continuation["thread_id"]}},
            filter={"runtime": PENDING_RUNTIME},
        )
    )

    assert child_checkpoint_count > 0
    assert pending_checkpoints
    assert {
        item.config["configurable"]["checkpoint_ns"]
        for item in pending_checkpoints
    } == {continuation["checkpoint_ns"]}

    restarted_pending_runtime = PendingTaskGraphService(
        preflight_graph_service=FakeNativeInterruptPreflightGraphService(),
        interaction_graph_service=FakeNativeInterruptInteractionGraphService(),
        checkpointer=saver,
    )
    restarted_root_runtime = AgentRootRuntime(
        checkpointer=saver,
        pending_graph_service=restarted_pending_runtime,
        pending_task_side_effect_handler=FakePendingTaskSideEffectHandler(),
    )

    resumed_state = await restarted_root_runtime.resume_interrupt(
        resume_payload={
            "action": "approve",
            "content": "确认",
            "source": "web",
            "metadata": {},
            "business_action": interrupt["business_action"],
            "interrupt_reason": interrupt["reason"],
        },
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="sql-pending-contract",
        current_interrupt=interrupt,
        context=context,
    )

    assert resumed_state.get("pending_task_resume_error") is None
    assert resumed_state.get("runtime_status") != "checkpoint_recovery_failed"
    assert resumed_state["application_action"] == "execute_confirmed_task"


class _FirstConfirmationThenDurablePendingRuntime:
    """Use a confirmed first task, then route the Root-owned next card to the real graph."""

    def __init__(self, durable_runtime: PendingTaskGraphService) -> None:
        self._first_runtime = FakeConfirmingPendingGraphService()
        self._durable_runtime = durable_runtime
        self._call_count = 0

    async def run_with_trace(self, state, *, side_effects=None):
        self._call_count += 1
        if self._call_count == 1:
            return await self._first_runtime.run_with_trace(state, side_effects=side_effects)
        return await self._durable_runtime.run_with_trace(state, side_effects=side_effects)

    async def load_checkpointed_outcome(self, *args, **kwargs):
        return await self._durable_runtime.load_checkpointed_outcome(*args, **kwargs)


@pytest.mark.asyncio
async def test_root_owned_next_task_creates_child_checkpoint_on_first_user_response(
    checkpoint_store,
):
    _engine, saver = checkpoint_store
    durable_pending_runtime = PendingTaskGraphService(
        preflight_graph_service=FakeNativeInterruptPreflightGraphService(),
        interaction_graph_service=FakeNativeInterruptInteractionGraphService(),
        checkpointer=saver,
    )
    pending_runtime = _FirstConfirmationThenDurablePendingRuntime(durable_pending_runtime)
    root_runtime = AgentRootRuntime(
        checkpointer=saver,
        pending_graph_service=pending_runtime,
        confirmed_task_graph_service=FakeConfirmedTaskWithNextGraphService(),
        pending_task_side_effect_handler=FakePendingTaskSideEffectHandler(),
    )
    context = AgentRuntimeContext(
        db=object(),
        session=SimpleNamespace(id=4, context_json={}),
        task=SimpleNamespace(
            id=101,
            task_key="task-101",
            team_id=2,
            user_id=3,
            session_id=4,
            status="WAITING_USER",
            state_json={"action": "create_customer_activity"},
        ),
        turn_input=AgentTurnInput.confirm(source="web"),
        content="确认",
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        side_effects=AgentRootRuntimeSideEffects(),
    )

    waiting_next_state = await root_runtime.checkpoint_turn_start(
        {
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "session_key": "sql-root-owned-next-task",
            "channel": "web",
            "content": "确认",
            "turn_kind": "confirm",
            "pending_task_requested": True,
            "task_projection": {"id": 101, "task_key": "task-101"},
        },
        context=context,
    )
    next_interrupt = waiting_next_state["current_interrupt"]

    assert next_interrupt["task_projection_id"] == 102
    assert "checkpoint_ref" not in next_interrupt

    context.side_effects = AgentRootRuntimeSideEffects()
    context.task = SimpleNamespace(
        id=102,
        task_key="task-102",
        team_id=2,
        user_id=3,
        session_id=4,
        status="WAITING_USER",
        intent="CREATE_OPPORTUNITY",
        target_type="customer",
        target_id=17,
        summary="等待补充商机信息",
        state_json={
            "action": "collect_opportunity_fields",
            "customer": {"id": 17, "account_name": "广州睿狐科技有限公司"},
            "payload": {"customer_id": 17, "missing_fields": ["total_amount"]},
        },
    )

    resumed_state = await root_runtime.resume_interrupt(
        resume_payload={
            "action": "submit_fields",
            "content": "确认",
            "source": "web",
            "metadata": {"fields": {"total_amount": 100000}},
            "business_action": next_interrupt["business_action"],
            "interrupt_reason": next_interrupt["reason"],
            "task_projection_id": 102,
            "task_projection_key": "task-102",
        },
        team_id=2,
        user_id=3,
        session_id=4,
        session_key="sql-root-owned-next-task",
        current_interrupt=next_interrupt,
        context=context,
    )

    pending_checkpoints = list(
        saver.list(
            {
                "configurable": {
                    "thread_id": "crm_agent:2:3:4:sql-root-owned-next-task",
                }
            },
            filter={"runtime": PENDING_RUNTIME},
        )
    )

    assert resumed_state.get("pending_task_resume_error") is None
    assert resumed_state.get("runtime_status") != "checkpoint_recovery_failed"
    assert pending_checkpoints
    assert all(
        item.config["configurable"]["checkpoint_ns"].startswith(
            "pending_task_subgraph:"
        )
        for item in pending_checkpoints
    )

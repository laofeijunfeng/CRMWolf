"""Behavioral contract for durable PendingTask interrupt projection."""

from datetime import timedelta

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.crud.agent_pending_interrupt_projection import agent_pending_interrupt_projection_crud
from app.models.agent import AgentSession, AgentTask, AgentTaskStatus
from app.models.agent_pending_interrupt_projection import (
    AgentPendingInterruptDeliveryStatus,
    AgentPendingInterruptProjection,
    AgentPendingInterruptProjectionStatus,
)
from app.services.agent.pending_continuation import (
    bind_pending_task_namespace,
    new_pending_task_continuation,
)
from app.services.agent.pending_effects import PendingTaskSideEffectResult
from app.services.agent.pending_interrupt_projection import (
    PendingInterruptProjectionRequest,
    PendingInterruptProjector,
    pending_interrupt_projection_key,
)
from app.utils.time import business_now


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AgentSession.__table__,
            AgentTask.__table__,
            AgentPendingInterruptProjection.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    session_row = AgentSession(
        id=13,
        session_key="agent_projection_test",
        team_id=7,
        user_id=11,
        title="Projection test",
        context_json={},
    )
    task_row = AgentTask(
        id=17,
        task_key="task_projection_test",
        team_id=7,
        user_id=11,
        session_id=13,
        status="waiting_user",
        state_json={},
    )
    session.add_all([session_row, task_row])
    session.commit()
    yield session
    session.close()
    engine.dispose()


class RecordingSideEffectHandler:
    def __init__(self, *, fail: bool = False):
        self.calls = 0
        self.fail = fail

    def apply(self, graph_state, context):
        self.calls += 1
        context.session.summary = f"projected-{self.calls}"
        context.db.add(context.session)
        context.db.flush()
        if self.fail:
            raise RuntimeError("side effect failed")
        return PendingTaskSideEffectResult(
            task=context.task,
            events=[{"event": "confirmation_required", "content": "请确认"}],
            assistant_content="请确认",
            current_interrupt=graph_state["current_interrupt"],
        )


class SuspendingSideEffectHandler:
    def __init__(self):
        self.calls = 0

    def apply(self, graph_state, context):
        self.calls += 1
        context.task.status = AgentTaskStatus.SUSPENDED
        context.db.add(context.task)
        context.db.flush()
        return PendingTaskSideEffectResult(
            task=None,
            suspended_task=context.task,
            events=[{"event": "task_cancelled", "task_id": context.task.id}],
            assistant_content="已先放一边。",
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


def _interrupt(continuation=None, *, prompt="请确认"):
    continuation = continuation or _continuation()
    return {
        "reason": "write_confirmation",
        "source_event": "confirmation_required",
        "business_action": "create_opportunity",
        "interaction": {
            "interaction_id": "int-projection-1",
            "type": "choice",
            "prompt": prompt,
        },
        "checkpoint_ref": dict(continuation),
    }


def _request(db_session, *, event_sink=None, continuation=None, interrupt=None, task=True):
    continuation = continuation or _continuation()
    interrupt = interrupt or _interrupt(continuation)
    return PendingInterruptProjectionRequest(
        db=db_session,
        session=db_session.get(AgentSession, 13),
        team_id=7,
        user_id=11,
        session_id=13,
        continuation=continuation,
        interrupt=interrupt,
        outcome={
            "handled": True,
            "has_active_task": True,
            "task_projection": {"id": 17},
            "assistant_content": "请确认",
            "current_interrupt": interrupt,
            "events": [{"event": "confirmation_required", "content": "请确认"}],
        },
        task=db_session.get(AgentTask, 17) if task else None,
        event_sink=event_sink,
    )


@pytest.mark.asyncio
async def test_projector_applies_business_projection_once_and_replays_durable_result(db_session):
    handler = RecordingSideEffectHandler()
    delivered = []

    async def sink(event):
        delivered.append(event)

    projector = PendingInterruptProjector(side_effect_handler=handler)
    first = await projector.project(_request(db_session, event_sink=sink))
    db_session.expire_all()
    replay = await projector.project(_request(db_session, event_sink=sink, task=False))

    assert first.status == "PROJECTED"
    assert first.replayed is False
    assert replay.status == "PROJECTED"
    assert replay.replayed is True
    assert replay.task.id == 17
    assert handler.calls == 1
    assert len(delivered) == 1
    assert first.events[0]["projection_event_id"] == replay.events[0]["projection_event_id"]
    assert first.events[0]["projection_key"] == first.projection_key
    record = agent_pending_interrupt_projection_crud.get_by_key(
        db_session,
        team_id=7,
        user_id=11,
        projection_key=first.projection_key,
    )
    assert record.status == AgentPendingInterruptProjectionStatus.PROJECTED
    assert record.delivery_status == AgentPendingInterruptDeliveryStatus.DELIVERED
    assert record.result_json["task_id"] == 17
    assert db_session.get(AgentSession, 13).summary == "projected-1"


@pytest.mark.asyncio
async def test_projector_replay_preserves_active_and_suspended_task_ownership(db_session):
    handler = SuspendingSideEffectHandler()
    projector = PendingInterruptProjector(side_effect_handler=handler)

    first = await projector.project(_request(db_session))
    db_session.expire_all()
    replay = await projector.project(_request(db_session, task=False))

    assert first.task is None
    assert first.suspended_task.id == 17
    assert replay.task is None
    assert replay.suspended_task.id == 17
    assert replay.suspended_task.status == AgentTaskStatus.SUSPENDED
    assert handler.calls == 1


@pytest.mark.asyncio
async def test_delivery_failure_is_retryable_without_reapplying_business_side_effects(db_session):
    handler = RecordingSideEffectHandler()
    attempts = []

    async def failing_sink(event):
        attempts.append(("failed", event["projection_event_id"]))
        raise RuntimeError("transport unavailable")

    projector = PendingInterruptProjector(side_effect_handler=handler)
    first = await projector.project(_request(db_session, event_sink=failing_sink))

    delivered = []

    async def healthy_sink(event):
        delivered.append(event["projection_event_id"])

    replay = await projector.project(_request(db_session, event_sink=healthy_sink, task=False))

    assert first.status == "PROJECTED"
    assert first.delivery_status == AgentPendingInterruptDeliveryStatus.FAILED
    assert replay.replayed is True
    assert replay.delivery_status == AgentPendingInterruptDeliveryStatus.DELIVERED
    assert handler.calls == 1
    assert delivered == [attempts[0][1]]


@pytest.mark.asyncio
async def test_no_transport_is_recorded_as_inline_visible_not_silent_skip(db_session):
    handler = RecordingSideEffectHandler()
    result = await PendingInterruptProjector(side_effect_handler=handler).project(_request(db_session))

    assert result.status == "PROJECTED"
    assert result.delivery_status == AgentPendingInterruptDeliveryStatus.INLINE_VISIBLE
    record = agent_pending_interrupt_projection_crud.get_by_key(
        db_session,
        team_id=7,
        user_id=11,
        projection_key=result.projection_key,
    )
    assert record.delivery_status == AgentPendingInterruptDeliveryStatus.INLINE_VISIBLE
    assert record.delivery_reason_code == "RETURNED_IN_RUNTIME_OUTCOME"


@pytest.mark.asyncio
async def test_delivery_lease_loss_does_not_report_inline_visibility(db_session, monkeypatch):
    monkeypatch.setattr(
        agent_pending_interrupt_projection_crud,
        "finish_delivery_if_lease_owner",
        lambda *args, **kwargs: None,
    )

    result = await PendingInterruptProjector(side_effect_handler=RecordingSideEffectHandler()).project(
        _request(db_session)
    )

    assert result.status == "PROJECTED"
    assert result.delivery_status == AgentPendingInterruptDeliveryStatus.DELIVERING
    assert result.delivery_status != AgentPendingInterruptDeliveryStatus.INLINE_VISIBLE


@pytest.mark.asyncio
async def test_transport_acceptance_with_lost_lease_does_not_report_delivered(db_session, monkeypatch):
    accepted = []

    async def sink(event):
        accepted.append(event)

    monkeypatch.setattr(
        agent_pending_interrupt_projection_crud,
        "finish_delivery_if_lease_owner",
        lambda *args, **kwargs: None,
    )

    result = await PendingInterruptProjector(side_effect_handler=RecordingSideEffectHandler()).project(
        _request(db_session, event_sink=sink)
    )

    assert accepted
    assert result.status == "PROJECTED"
    assert result.delivery_status == AgentPendingInterruptDeliveryStatus.DELIVERING
    assert result.delivery_status != AgentPendingInterruptDeliveryStatus.DELIVERED


@pytest.mark.asyncio
async def test_live_projection_lease_fails_closed_as_retryable_busy(db_session):
    continuation = _continuation()
    interrupt = _interrupt(continuation)
    projection_key = pending_interrupt_projection_key(continuation, interrupt)
    agent_pending_interrupt_projection_crud.ensure(
        db_session,
        team_id=7,
        user_id=11,
        session_id=13,
        task_id=17,
        projection_key=projection_key,
        continuation_json=dict(continuation),
        interrupt_json=interrupt,
    )
    agent_pending_interrupt_projection_crud.claim_projection(
        db_session,
        team_id=7,
        user_id=11,
        projection_key=projection_key,
        lease_token="other-worker",
        lease_expires_at=business_now() + timedelta(minutes=5),
    )

    result = await PendingInterruptProjector(side_effect_handler=RecordingSideEffectHandler()).project(
        _request(db_session, continuation=continuation, interrupt=interrupt)
    )

    assert result.status == "IN_PROGRESS"
    assert result.busy is True
    assert result.retryable is True
    assert result.failure_reason == "projection_in_progress"


@pytest.mark.asyncio
async def test_expired_projection_lease_can_be_reclaimed(db_session):
    continuation = _continuation()
    interrupt = _interrupt(continuation)
    projection_key = pending_interrupt_projection_key(continuation, interrupt)
    agent_pending_interrupt_projection_crud.ensure(
        db_session,
        team_id=7,
        user_id=11,
        session_id=13,
        task_id=17,
        projection_key=projection_key,
        continuation_json=dict(continuation),
        interrupt_json=interrupt,
    )
    agent_pending_interrupt_projection_crud.claim_projection(
        db_session,
        team_id=7,
        user_id=11,
        projection_key=projection_key,
        lease_token="dead-worker",
        lease_expires_at=business_now() - timedelta(seconds=1),
    )
    handler = RecordingSideEffectHandler()

    result = await PendingInterruptProjector(side_effect_handler=handler).project(
        _request(db_session, continuation=continuation, interrupt=interrupt)
    )

    assert result.status == "PROJECTED"
    assert handler.calls == 1


@pytest.mark.asyncio
async def test_projection_rolls_back_business_mutation_and_can_retry_after_failure(db_session):
    failed_handler = RecordingSideEffectHandler(fail=True)
    first = await PendingInterruptProjector(side_effect_handler=failed_handler).project(_request(db_session))

    db_session.expire_all()
    assert first.status == "FAILED"
    assert db_session.get(AgentSession, 13).summary is None

    successful_handler = RecordingSideEffectHandler()
    retry = await PendingInterruptProjector(side_effect_handler=successful_handler).project(_request(db_session))

    assert retry.status == "PROJECTED"
    assert successful_handler.calls == 1
    assert db_session.get(AgentSession, 13).summary == "projected-1"


@pytest.mark.asyncio
async def test_projector_rejects_tampered_or_cross_scope_continuations(db_session):
    valid = _continuation()
    invalid_requests = [
        _request(db_session, continuation={**valid, "team_id": 99}),
        _request(db_session, continuation={**valid, "thread_id": "crm_agent_pending:7:11:13:99:turn-1"}),
        _request(db_session, continuation={**valid, "checkpoint_ns": "other:child"}),
        _request(db_session, continuation=valid, interrupt=_interrupt({**valid, "user_id": 99})),
    ]
    handler = RecordingSideEffectHandler()
    projector = PendingInterruptProjector(side_effect_handler=handler)

    results = [await projector.project(request) for request in invalid_requests]

    assert all(result.status == "FAILED" for result in results)
    assert handler.calls == 0
    assert db_session.query(AgentPendingInterruptProjection).count() == 0


def test_projection_key_hashes_full_identity_without_length_truncation_collisions():
    continuation = _continuation()
    prefix = "x" * 500
    first_interrupt = _interrupt(continuation, prompt="A")
    second_interrupt = _interrupt(continuation, prompt="B")
    first_interrupt["interaction"]["interaction_id"] = f"{prefix}A"
    second_interrupt["interaction"]["interaction_id"] = f"{prefix}B"
    first = pending_interrupt_projection_key(continuation, first_interrupt)
    second = pending_interrupt_projection_key(continuation, second_interrupt)

    assert first.startswith("pending_interrupt_projection:v1:")
    assert len(first) < 255
    assert first != second

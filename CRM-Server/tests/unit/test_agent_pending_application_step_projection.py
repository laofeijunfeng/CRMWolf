"""Behavioral contract for durable internal PendingTask application steps."""

from datetime import timedelta

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.agent import AgentSession, AgentTask
from app.models.agent_pending_application_step import (
    AgentPendingApplicationStep,
    AgentPendingApplicationStepStatus,
)
from app.schemas.agent import AgentTaskUpdate
from app.services.agent.pending_application_step_contracts import (
    build_pending_application_step_request,
    pending_application_step_id,
)
from app.services.agent.pending_application_step_projection import (
    PendingApplicationStepProjectionRequest,
    PendingApplicationStepProjector,
)
from app.services.agent.pending_application_steps import DefaultPendingApplicationStepExecutor
from app.services.agent.pending_continuation import (
    new_pending_task_continuation,
)
from app.services.agent.state import PendingTaskTurnResult
from app.services.agent.task_projection import agent_task_snapshot, update_agent_task
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
            AgentPendingApplicationStep.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    session.add(AgentSession(
        id=13,
        session_key="agent_application_step_test",
        team_id=7,
        user_id=11,
        title="Application step test",
        context_json={},
    ))
    session.add(AgentTask(
        id=17,
        task_key="task_application_step_test",
        team_id=7,
        user_id=11,
        session_id=13,
        status="waiting_user",
        state_json={"action": "collect_deployment_info_fields"},
        input_json={"payload": {}},
    ))
    session.commit()
    yield session
    session.close()
    engine.dispose()


def _continuation():
    return new_pending_task_continuation(
        team_id=7, user_id=11, session_id=13, task_id=17,
        root_thread_id="crm_agent:7:11:13:13",
        checkpoint_ns="pending_task_subgraph:child-1",
    )


def _continuation_without_task():
    return new_pending_task_continuation(
        team_id=7, user_id=11, session_id=13, task_id=None,
        root_thread_id="crm_agent:7:11:13:13",
        checkpoint_ns="pending_task_subgraph:child-no-task",
    )


def _step(db_session, *, content="补充部署信息", step_type="preflight"):
    task = db_session.get(AgentTask, 17)
    return build_pending_application_step_request(
        step_type=step_type,
        continuation=_continuation(),
        task_snapshot=agent_task_snapshot(task),
        content=content,
        turn_input={"type": "text", "content": content, "metadata": {}},
        interaction_metadata={},
    )


def _request(db_session, *, step=None):
    return PendingApplicationStepProjectionRequest(
        db=db_session,
        session=db_session.get(AgentSession, 13),
        team_id=7,
        user_id=11,
        session_id=13,
        root_thread_id="crm_agent:7:11:13:13",
        step=step or _step(db_session),
        task=db_session.get(AgentTask, 17),
        authorization="Bearer test",
    )


def test_application_step_id_is_stable_and_sensitive_to_semantic_input(db_session):
    first = _step(db_session)
    replay = _step(db_session)
    changed = _step(db_session, content="另一条输入")

    assert first["step_id"] == replay["step_id"]
    assert first["step_id"] == pending_application_step_id(first)
    assert changed["step_id"] != first["step_id"]
    assert first["internal"] is True
    assert first["reason"] == "pending_task_application_step"
    assert first["checkpoint_ref"]["checkpoint_ns"] == "pending_task_subgraph:child-1"


class RecordingExecutor:
    def __init__(self):
        self.calls = 0

    async def execute(self, request):
        self.calls += 1
        request.task.summary = f"application-step-{self.calls}"
        request.db.add(request.task)
        request.db.flush()
        return {
            "step_type": request.step["step_type"],
            "task_snapshot": agent_task_snapshot(request.task),
            "result": {
                "handled": False,
                "events": [{"event": "pending_preflight_started"}],
            },
        }


@pytest.mark.asyncio
async def test_projector_executes_once_and_replays_the_durable_json_result(db_session):
    executor = RecordingExecutor()
    projector = PendingApplicationStepProjector(executor=executor)

    step = _step(db_session)
    first = await projector.project(_request(db_session, step=step))
    db_session.expire_all()
    replay = await projector.project(_request(db_session, step=step))

    assert first.status == "COMPLETED"
    assert first.replayed is False
    assert replay.status == "COMPLETED"
    assert replay.replayed is True
    assert replay.result == first.result
    assert executor.calls == 1
    assert db_session.get(AgentTask, 17).summary == "application-step-1"
    record = db_session.query(AgentPendingApplicationStep).one()
    assert record.status == AgentPendingApplicationStepStatus.COMPLETED
    assert record.result_json == first.result


class MutatingInteractionModule:
    def __init__(self):
        self.calls = 0

    async def execute(self, request):
        self.calls += 1
        update_agent_task(
            request.db,
            request.task,
            AgentTaskUpdate(summary="已收集部署信息"),
        )
        return PendingTaskTurnResult(
            handled=True,
            assistant_content="请确认部署信息。",
            remember_pending_task=True,
            events=[{"event": "deployment_info_fields_required"}],
        )


@pytest.mark.asyncio
async def test_interaction_task_mutation_rolls_back_when_step_ledger_cannot_complete(
    db_session,
    monkeypatch,
):
    module = MutatingInteractionModule()
    executor = DefaultPendingApplicationStepExecutor(interaction_module=module)
    projector = PendingApplicationStepProjector(executor=executor)
    step = _step(db_session, step_type="interaction")
    monkeypatch.setattr(
        projector.crud,
        "complete_if_lease_owner",
        lambda *args, **kwargs: None,
    )

    result = await projector.project(_request(db_session, step=step))

    db_session.expire_all()
    assert result.status == "IN_PROGRESS"
    assert result.failure_reason == "application_step_lease_lost"
    assert module.calls == 1
    assert db_session.get(AgentTask, 17).summary is None


@pytest.mark.asyncio
async def test_interaction_task_mutation_commits_atomically_and_replays_without_reexecution(
    db_session,
):
    module = MutatingInteractionModule()
    executor = DefaultPendingApplicationStepExecutor(interaction_module=module)
    projector = PendingApplicationStepProjector(executor=executor)
    step = _step(db_session, step_type="interaction")

    first = await projector.project(_request(db_session, step=step))
    db_session.expire_all()
    replay = await projector.project(_request(db_session, step=step))

    assert first.status == "COMPLETED"
    assert replay.status == "COMPLETED"
    assert replay.replayed is True
    assert replay.result == first.result
    assert module.calls == 1
    assert db_session.get(AgentTask, 17).summary == "已收集部署信息"
    record = db_session.query(AgentPendingApplicationStep).one()
    assert record.status == AgentPendingApplicationStepStatus.COMPLETED
    assert record.result_json["task_snapshot"]["summary"] == "已收集部署信息"


@pytest.mark.asyncio
async def test_task_transition_rolls_back_when_step_ledger_cannot_complete(
    db_session,
    monkeypatch,
):
    task = db_session.get(AgentTask, 17)
    step = build_pending_application_step_request(
        step_type="task_transition",
        continuation=_continuation(),
        task_snapshot=agent_task_snapshot(task),
        content="先暂停当前任务",
        turn_input={"type": "text", "content": "先暂停当前任务", "metadata": {}},
        interaction_metadata={},
        effect_intents=[{
            "intent_id": "project_pending_task_state:17:suspend",
            "intent_type": "project_pending_task_state",
            "task_id": 17,
            "expected_task": {"status": "waiting_user"},
            "task_update": {"status": "suspended"},
        }],
    )
    projector = PendingApplicationStepProjector(
        executor=DefaultPendingApplicationStepExecutor()
    )
    monkeypatch.setattr(
        projector.crud,
        "complete_if_lease_owner",
        lambda *args, **kwargs: None,
    )

    result = await projector.project(_request(db_session, step=step))

    db_session.expire_all()
    assert result.status == "IN_PROGRESS"
    assert result.failure_reason == "application_step_lease_lost"
    assert db_session.get(AgentTask, 17).status == "waiting_user"


@pytest.mark.asyncio
async def test_projector_reports_busy_without_reexecuting_an_owned_unexpired_lease(db_session):
    step = _step(db_session)
    db_session.add(AgentPendingApplicationStep(
        team_id=7,
        user_id=11,
        session_id=13,
        task_id=17,
        step_id=step["step_id"],
        step_type="preflight",
        continuation_json=step["checkpoint_ref"],
        request_json=step,
        status=AgentPendingApplicationStepStatus.RUNNING,
        attempt_count=1,
        lease_token="other-worker",
        lease_expires_at=business_now() + timedelta(minutes=1),
    ))
    db_session.commit()
    executor = RecordingExecutor()

    result = await PendingApplicationStepProjector(executor=executor).project(
        _request(db_session, step=step)
    )

    assert result.status == "IN_PROGRESS"
    assert result.busy is True
    assert result.retryable is True
    assert executor.calls == 0


@pytest.mark.asyncio
async def test_projector_rejects_cross_owner_continuation_before_execution(db_session):
    step = dict(_step(db_session))
    step["checkpoint_ref"] = {**step["checkpoint_ref"], "user_id": 99}
    step["step_id"] = pending_application_step_id(step)
    executor = RecordingExecutor()

    result = await PendingApplicationStepProjector(executor=executor).project(
        _request(db_session, step=step)
    )

    assert result.status == "FAILED"
    assert result.retryable is False
    assert result.failure_reason == "invalid_continuation"
    assert executor.calls == 0


@pytest.mark.asyncio
async def test_projector_accepts_explicit_step_task_after_checkpointed_task_ownership_transfer(
    db_session,
):
    task = db_session.get(AgentTask, 17)
    step = build_pending_application_step_request(
        step_type="task_transition",
        continuation=_continuation_without_task(),
        task_snapshot=agent_task_snapshot(task),
        content="继续这个草稿",
        turn_input={"type": "text", "content": "继续这个草稿", "metadata": {}},
        interaction_metadata={},
        effect_intents=[{
            "intent_id": "project_pending_task_state:17:resume",
            "intent_type": "project_pending_task_state",
            "task_id": 17,
            "expected_task": {"status": "suspended"},
            "task_update": {"status": "waiting_user"},
        }],
    )
    executor = RecordingExecutor()

    result = await PendingApplicationStepProjector(executor=executor).project(
        _request(db_session, step=step)
    )

    assert result.status == "COMPLETED"
    assert executor.calls == 1
    record = db_session.query(AgentPendingApplicationStep).one()
    assert record.task_id == 17
    assert record.continuation_json["task_id"] is None


@pytest.mark.asyncio
async def test_projector_rejects_step_task_that_conflicts_with_continuation_task(db_session):
    step = dict(_step(db_session))
    step["task_snapshot"] = {**step["task_snapshot"], "id": 999}
    step["step_id"] = pending_application_step_id(step)
    executor = RecordingExecutor()

    result = await PendingApplicationStepProjector(executor=executor).project(
        _request(db_session, step=step)
    )

    assert result.status == "FAILED"
    assert result.failure_reason == "task_continuation_mismatch"
    assert executor.calls == 0

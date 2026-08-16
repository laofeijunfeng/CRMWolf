"""Behavioral contract for durable confirmed-task application projection."""


import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.agent import AgentSession, AgentTask, AgentTaskStatus
from app.models.agent_confirmed_application_step import (
    AgentConfirmedApplicationStep,
    AgentConfirmedApplicationStepStatus,
)
from app.services.agent.confirmed_application_step_contracts import (
    build_confirmed_application_step_request,
)
from app.services.agent.confirmed_application_step_projection import (
    ConfirmedApplicationStepProjectionRequest,
    ConfirmedApplicationStepProjector,
)
from app.services.agent.task_projection import agent_task_snapshot


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
            AgentConfirmedApplicationStep.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    session.add(AgentSession(
        id=13,
        session_key="confirmed_application_step_test",
        team_id=7,
        user_id=11,
        title="Confirmed application step test",
        context_json={},
    ))
    session.add(AgentTask(
        id=17,
        task_key="task_confirmed_application_step_test",
        team_id=7,
        user_id=11,
        session_id=13,
        status=AgentTaskStatus.WAITING_USER,
        state_json={"action": "create_deployment_info", "payload": {"customer_id": 101}},
        input_json={"customer_id": 101},
    ))
    session.commit()
    yield session
    session.close()
    engine.dispose()


def _step(db_session):
    return build_confirmed_application_step_request(
        task_snapshot=agent_task_snapshot(db_session.get(AgentTask, 17)),
        action="create_deployment_info",
    )


def _request(db_session, *, step=None, user_id=11, task=None):
    return ConfirmedApplicationStepProjectionRequest(
        db=db_session,
        session=db_session.get(AgentSession, 13),
        task=task if task is not None else db_session.get(AgentTask, 17),
        team_id=7,
        user_id=user_id,
        session_id=13,
        authorization="Bearer test",
        channel="web",
        provider=None,
        step=step or _step(db_session),
    )


class RecordingExecutor:
    def __init__(self):
        self.calls = 0

    async def execute(self, request):
        self.calls += 1
        request.task.status = AgentTaskStatus.COMPLETED
        request.task.result_json = {"deployment_id": 9001}
        request.db.add(request.task)
        request.db.commit()
        return {
            "execution_status": "completed",
            "tool_result": {
                "event": "tool_result",
                "tool_name": "create_deployment_info",
                "success": True,
                "data": {"deployment_id": 9001},
            },
            "task_event": {
                "event": "task_completed",
                "task_id": request.task.id,
                "content": "部署信息已创建。",
            },
            "assistant_content": "部署信息已创建。",
            "output_events": [
                {
                    "event": "tool_result",
                    "tool_name": "create_deployment_info",
                    "success": True,
                    "data": {"deployment_id": 9001},
                },
                {"event": "task_completed", "task_id": 17, "content": "部署信息已创建。"},
                {"event": "final", "content": "部署信息已创建。"},
            ],
            "executed_task_snapshot": agent_task_snapshot(request.task),
            "active_task_snapshot": {},
            "progress_events": [],
        }


@pytest.mark.asyncio
async def test_confirmed_application_projection_executes_once_and_replays_durable_result(db_session):
    executor = RecordingExecutor()
    projector = ConfirmedApplicationStepProjector(executor=executor)
    step = _step(db_session)

    first = await projector.project(_request(db_session, step=step))
    replay = await projector.project(_request(db_session, step=step))

    assert first.status == "COMPLETED"
    assert first.replayed is False
    assert replay.status == "COMPLETED"
    assert replay.replayed is True
    assert replay.result == first.result
    assert executor.calls == 1
    record = db_session.query(AgentConfirmedApplicationStep).one()
    assert record.status == AgentConfirmedApplicationStepStatus.COMPLETED
    assert record.attempt_count == 1
    assert record.result_json == first.result


@pytest.mark.asyncio
async def test_confirmed_application_projection_rejects_cross_owner_task_before_execution(db_session):
    executor = RecordingExecutor()
    projector = ConfirmedApplicationStepProjector(executor=executor)

    result = await projector.project(_request(db_session, user_id=99))

    assert result.status == "REJECTED"
    assert result.failure_reason == "task_owner_mismatch"
    assert result.retryable is False
    assert executor.calls == 0
    assert db_session.query(AgentConfirmedApplicationStep).count() == 0


@pytest.mark.asyncio
async def test_confirmed_application_projection_rejects_request_snapshot_mismatch(db_session):
    executor = RecordingExecutor()
    projector = ConfirmedApplicationStepProjector(executor=executor)
    step = _step(db_session)
    step["task_snapshot"] = {**step["task_snapshot"], "task_key": "other-task"}

    result = await projector.project(_request(db_session, step=step))

    assert result.status == "REJECTED"
    assert result.failure_reason == "invalid_application_step_request"
    assert executor.calls == 0


@pytest.mark.asyncio
async def test_confirmed_application_projection_reports_active_lease_as_retryable(db_session):
    executor = RecordingExecutor()
    projector = ConfirmedApplicationStepProjector(executor=executor)
    step = _step(db_session)
    projector.crud.ensure(
        db_session,
        team_id=7,
        user_id=11,
        session_id=13,
        task_id=17,
        step_id=step["step_id"],
        step_type=step["step_type"],
        request_json=step,
    )
    projector.crud.claim(
        db_session,
        team_id=7,
        user_id=11,
        step_id=step["step_id"],
        lease_token="held-by-another-worker",
        lease_seconds=60,
    )

    result = await projector.project(_request(db_session, step=step))

    assert result.status == "IN_PROGRESS"
    assert result.busy is True
    assert result.retryable is True
    assert result.failure_reason == "application_step_lease_busy"
    assert executor.calls == 0


@pytest.mark.asyncio
async def test_confirmed_application_projection_claims_waiting_task_before_executor(db_session):
    observed_statuses = []

    class ClaimAwareExecutor(RecordingExecutor):
        async def execute(self, request):
            observed_statuses.append(request.task.status)
            return await super().execute(request)

    result = await ConfirmedApplicationStepProjector(executor=ClaimAwareExecutor()).project(_request(db_session))

    assert result.status == "COMPLETED"
    assert observed_statuses == [AgentTaskStatus.RUNNING]


@pytest.mark.asyncio
async def test_confirmed_application_projection_rejects_new_intent_for_already_claimed_task(db_session):
    executor = RecordingExecutor()
    projector = ConfirmedApplicationStepProjector(executor=executor)
    first_step = _step(db_session)
    first = await projector.project(_request(db_session, step=first_step))
    assert first.status == "COMPLETED"

    task = db_session.get(AgentTask, 17)
    task.status = AgentTaskStatus.WAITING_USER
    task.state_json = {"action": "create_contact", "payload": {"customer_id": 101}}
    db_session.add(task)
    db_session.commit()
    second_step = build_confirmed_application_step_request(
        task_snapshot=agent_task_snapshot(task),
        action="create_contact",
    )

    second = await projector.project(_request(db_session, step=second_step, task=task))

    assert second.status == "REJECTED"
    assert second.failure_reason == "application_step_task_already_claimed"
    assert executor.calls == 1
    assert db_session.query(AgentConfirmedApplicationStep).count() == 1


@pytest.mark.asyncio
async def test_confirmed_application_projection_rejects_unclaimed_non_waiting_task(db_session):
    task = db_session.get(AgentTask, 17)
    task.status = AgentTaskStatus.RUNNING
    db_session.add(task)
    db_session.commit()
    step = build_confirmed_application_step_request(
        task_snapshot=agent_task_snapshot(task),
        action="create_deployment_info",
    )
    executor = RecordingExecutor()

    result = await ConfirmedApplicationStepProjector(executor=executor).project(
        _request(db_session, step=step, task=task)
    )

    assert result.status == "REJECTED"
    assert result.failure_reason == "task_not_waiting_confirmation"
    assert executor.calls == 0
    assert db_session.query(AgentConfirmedApplicationStep).count() == 0

"""Behavioral contract for replay-safe next waiting-task projection."""

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.agent import AgentSession, AgentTask, AgentTaskStatus, AgentWorkflowAction
from app.services.agent import action_workflow
from app.services.agent.next_waiting_task_projection import (
    NextWaitingTaskProjectionConflict,
    NextWaitingTaskProjectionRequest,
    NextWaitingTaskProjector,
    NextWaitingTaskSpec,
)


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
            AgentWorkflowAction.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    parent_workflow = action_workflow.required_write_contract(action="create_payment_plan")
    session.add(AgentSession(
        id=13,
        session_key="next_waiting_task_projection_test",
        team_id=7,
        user_id=11,
        title="Next task projection test",
        context_json={},
    ))
    session.add(AgentTask(
        id=17,
        task_key="task_parent_payment_plan",
        team_id=7,
        user_id=11,
        session_id=13,
        status=AgentTaskStatus.COMPLETED,
        state_json={
            "action": "create_payment_plan",
            "workflow": parent_workflow,
            "payload": {"customer_id": 101},
        },
        input_json={"customer_id": 101},
    ))
    session.commit()
    yield session
    session.close()
    engine.dispose()


def _request(db_session, *, payload=None, action="create_payment_record", user_id=11):
    return NextWaitingTaskProjectionRequest(
        db=db_session,
        parent_task=db_session.get(AgentTask, 17),
        team_id=7,
        user_id=user_id,
        session_id=13,
        spec=NextWaitingTaskSpec(
            slot="payment_record_after_plan",
            action=action,
            intent="PAYMENT_RECORD",
            target_type="customer",
            target_id=101,
            summary="登记本次回款",
            payload=payload or {
                "payment_plan_id": 9001,
                "actual_amount": 1000,
                "payment_date": "2026-08-14",
            },
            state_context={"customer": {"id": 101, "account_name": "示例客户"}},
            required_tools=("create_payment_record",),
            confirmation_summary="登记本次回款",
        ),
    )


def test_next_waiting_task_projection_replays_one_stable_task_and_action(db_session):
    projector = NextWaitingTaskProjector()

    first = projector.project(_request(db_session))
    replay = projector.project(_request(db_session))

    assert first.task.id == replay.task.id
    assert first.task.task_key == replay.task.task_key
    assert first.workflow == replay.workflow
    assert first.replayed is False
    assert replay.replayed is True
    assert db_session.query(AgentTask).filter(AgentTask.id != 17).count() == 1
    action = db_session.query(AgentWorkflowAction).one()
    assert action.task_id == first.task.id
    assert action.action_id == first.workflow["action_id"]
    assert action.parent_action_id == first.workflow["parent_action_id"]
    assert first.task.state_json["workflow"] == first.workflow


def test_next_waiting_task_projection_fails_closed_when_same_slot_changes_contract(db_session):
    projector = NextWaitingTaskProjector()
    projector.project(_request(db_session))

    with pytest.raises(NextWaitingTaskProjectionConflict, match="next_task_contract_mismatch"):
        projector.project(_request(
            db_session,
            payload={
                "payment_plan_id": 9002,
                "actual_amount": 500,
                "payment_date": "2026-08-15",
            },
        ))

    assert db_session.query(AgentTask).filter(AgentTask.id != 17).count() == 1
    assert db_session.query(AgentWorkflowAction).count() == 1


def test_next_waiting_task_projection_rejects_cross_owner_before_create(db_session):
    projector = NextWaitingTaskProjector()

    with pytest.raises(NextWaitingTaskProjectionConflict, match="parent_task_owner_mismatch"):
        projector.project(_request(db_session, user_id=99))

    assert db_session.query(AgentTask).filter(AgentTask.id != 17).count() == 0
    assert db_session.query(AgentWorkflowAction).count() == 0

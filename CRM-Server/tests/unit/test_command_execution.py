from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import operations
from app.core.database import Base
from app.models.command_execution import CommandExecution, CommandExecutionStatus
from app.schemas.command import CommandEffect, CommandNextAction, CommandResource
from app.services.command_execution_service import (
    CommandAlreadyInProgress,
    CommandIdempotencyConflict,
    command_execution_service,
    request_fingerprint,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[CommandExecution.__table__])
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(operations.router)
    app.dependency_overrides[operations.get_db] = lambda: db_session
    app.dependency_overrides[operations.get_current_user_team] = lambda: 1
    app.dependency_overrides[operations.get_current_active_user] = lambda: SimpleNamespace(id=7)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_begin_succeed_and_terminal_replay_are_idempotent(db_session):
    fingerprint = request_fingerprint({"task": "task_1", "action": "complete"})
    execution, replay = command_execution_service.begin(
        db_session,
        team_id=1,
        actor_id="7",
        command_type="FOLLOW_UP_TASK_TRANSITION",
        resource_type="FOLLOW_UP_TASK",
        resource_public_id="task_1",
        idempotency_key="idem_1",
        fingerprint=fingerprint,
    )
    assert replay is False
    assert execution.status == CommandExecutionStatus.PENDING
    db_session.commit()

    with pytest.raises(CommandAlreadyInProgress) as pending_error:
        command_execution_service.begin(
            db_session,
            team_id=1,
            actor_id="7",
            command_type="FOLLOW_UP_TASK_TRANSITION",
            resource_type="FOLLOW_UP_TASK",
            resource_public_id="task_1",
            idempotency_key="idem_1",
            fingerprint=fingerprint,
        )
    assert str(pending_error.value) == execution.operation_id

    command_execution_service.succeed(
        db_session,
        execution,
        data={"task": {"public_id": "task_1", "status": "COMPLETED"}},
        resource=CommandResource(type="FOLLOW_UP_TASK", public_id="task_1"),
        effects=[CommandEffect(type="FOLLOW_UP_TASK", public_id="task_1", status="SYNCED")],
        next_actions=[CommandNextAction(id="view-task", label="查看追踪详情", kind="view-detail")],
    )
    db_session.commit()

    replayed, replay = command_execution_service.begin(
        db_session,
        team_id=1,
        actor_id="7",
        command_type="FOLLOW_UP_TASK_TRANSITION",
        resource_type="FOLLOW_UP_TASK",
        resource_public_id="task_1",
        idempotency_key="idem_1",
        fingerprint=fingerprint,
    )
    assert replay is True
    assert replayed.operation_id == execution.operation_id
    assert command_execution_service.to_response_payload(replayed)["status"] == CommandExecutionStatus.SUCCEEDED


def test_reusing_idempotency_key_with_different_request_is_conflict(db_session):
    command_execution_service.begin(
        db_session,
        team_id=1,
        actor_id="7",
        command_type="FOLLOW_UP_TASK_TRANSITION",
        resource_type="FOLLOW_UP_TASK",
        resource_public_id="task_1",
        idempotency_key="idem_1",
        fingerprint="fingerprint_a",
    )
    db_session.commit()

    with pytest.raises(CommandIdempotencyConflict):
        command_execution_service.begin(
            db_session,
            team_id=1,
            actor_id="7",
            command_type="FOLLOW_UP_TASK_TRANSITION",
            resource_type="FOLLOW_UP_TASK",
            resource_public_id="task_1",
            idempotency_key="idem_1",
            fingerprint="fingerprint_b",
        )


def test_operation_endpoint_is_team_and_actor_scoped(db_session, client):
    execution, _ = command_execution_service.begin(
        db_session,
        team_id=1,
        actor_id="7",
        command_type="FOLLOW_UP_TASK_TRANSITION",
        operation_id="op_visible",
        fingerprint="fingerprint",
    )
    command_execution_service.fail(
        db_session,
        execution,
        error_code="TASK_OWNER_MISMATCH",
        error_message="没有权限操作这条任务",
    )
    db_session.commit()

    response = client.get("/v1/operations/op_visible")
    assert response.status_code == 200
    assert response.json()["status"] == "FAILED"
    assert response.json()["error"] == {
        "code": "TASK_OWNER_MISMATCH",
        "message": "没有权限操作这条任务",
        "field_path": None,
    }

    db_session.query(CommandExecution).filter(CommandExecution.operation_id == "op_visible").update({"actor_id": "8"})
    db_session.commit()
    forbidden = client.get("/v1/operations/op_visible")
    assert forbidden.status_code == 403


def test_fail_does_not_overwrite_a_committed_terminal_outcome(db_session):
    execution, replay = command_execution_service.begin(
        db_session,
        team_id=1,
        actor_id="7",
        command_type="CUSTOMER_ASSIGN",
        operation_id="op_committed",
        fingerprint="fingerprint",
    )
    assert replay is False
    command_execution_service.succeed(
        db_session,
        execution,
        data={"customer": {"public_id": "cus_1"}},
        resource=CommandResource(type="CUSTOMER", public_id="cus_1", version=2),
    )
    db_session.commit()

    # Simulate a recovery path that runs after a post-commit cleanup error.
    recovered = command_execution_service.fail(
        db_session,
        execution,
        status=CommandExecutionStatus.UNKNOWN,
        error_code="CUSTOMER_ASSIGN_UNKNOWN",
        error_message="移交结果暂未确认，请查询操作结果",
        retryable=True,
    )
    db_session.commit()

    assert recovered.status == CommandExecutionStatus.SUCCEEDED
    assert recovered.error_code is None
    assert command_execution_service.to_response_payload(recovered)["status"] == CommandExecutionStatus.SUCCEEDED

"""Stop-generation and Durable Async operation list for /v1/assistant (CRM-182 Modules B and C)."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, get_args

import pytest

from app.core.database import Base
from app.main import app
from app.models.agent import AgentSession
from app.models.agent_async_operation import (
    AgentAsyncOperation,
    AgentAsyncOperationEvent,
    AgentAsyncOperationStatus,
)
from app.models.assistant import AssistantTask, AssistantTaskStatus
from app.models.assistant_turn import AssistantTurn, AssistantTurnEvent
from app.schemas.assistant import AssistantAsyncOperationStatusLiteral
from app.services.assistant import turns
from app.utils.time import business_now
from tests.unit.test_assistant_api import client as client
from tests.unit.test_assistant_api import db_session as db_session
from tests.unit.test_assistant_api import override_auth as override_auth

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _accept(db: Session, task: AssistantTask, key: str) -> AssistantTurn:
    turn, accepted = turns.accept_submit(
        db,
        task=task,
        key=key,
        input_data={"kind": "text", "text": "今天跟客户确认服务器准备情况", "choice": None},
        action_id=None,
        expected_version=None,
    )
    assert accepted
    return turn


@pytest.fixture
def running_turn(client: TestClient, db_session: Session) -> tuple[AssistantTask, AssistantTurn]:
    created = client.post(
        "/api/v1/assistant/tasks",
        json={"goal": "停止本次生成", "client_request_id": "create-stop-turn"},
    )
    task = db_session.query(AssistantTask).filter_by(public_id=created.json()["public_id"]).one()
    turn = _accept(db_session, task, "stop-turn-input")
    turn.status = "RUNNING"
    turn.lease_owner = "live-worker"
    turn.lease_version = 1
    turn.lease_expires_at = business_now() + timedelta(seconds=300)
    db_session.commit()
    return task, turn


def _add_stage(db: Session, turn: AssistantTurn, stage: str, phase: str) -> None:
    turns.add_event(db, turn, "stage", {"stage": stage, "phase": phase})
    db.commit()


def _stop_url(task: AssistantTask, turn: AssistantTurn) -> str:
    return f"/api/v1/assistant/tasks/{task.public_id}/turns/{turn.public_id}/stop"


def _done_events(db: Session, turn: AssistantTurn) -> list[AssistantTurnEvent]:
    return db.query(AssistantTurnEvent).filter_by(turn_id=turn.id, event="done").all()


def test_stop_before_write_cancels_only_the_turn_and_keeps_the_task_usable(
    client: TestClient,
    db_session: Session,
    running_turn: tuple[AssistantTask, AssistantTurn],
) -> None:
    task, turn = running_turn
    _add_stage(db_session, turn, "locate", "start")

    response = client.post(_stop_url(task, turn))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stopped"] is True
    assert body["reason"] == "STOPPED"
    assert body["task"]["status"] == "ACTIVE"
    assert body["task"]["processing_turn_id"] is None
    db_session.expire_all()
    stopped = db_session.get(AssistantTurn, turn.id)
    assert stopped.status == "CANCELLED"
    assert stopped.lease_owner is None
    done = _done_events(db_session, turn)
    assert len(done) == 1
    assert done[0].data_json["stopped"] is True
    latest_task = db_session.get(AssistantTask, task.id)
    assert latest_task.status == AssistantTaskStatus.ACTIVE
    assert latest_task.active_turn_id is None
    follow_up = _accept(db_session, latest_task, "stop-turn-follow-up")
    assert follow_up.task_id == task.id
    assert follow_up.status == "PENDING"


@pytest.mark.parametrize("phase", ["start", "done"])
def test_stop_after_write_started_refuses_without_forging_cancellation(
    client: TestClient,
    db_session: Session,
    running_turn: tuple[AssistantTask, AssistantTurn],
    phase: str,
) -> None:
    task, turn = running_turn
    _add_stage(db_session, turn, "write", "start")
    if phase == "done":
        _add_stage(db_session, turn, "write", "done")

    response = client.post(_stop_url(task, turn))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stopped"] is False
    assert body["reason"] == "WRITE_IN_PROGRESS"
    assert body["task"]["status"] == "ACTIVE"
    assert body["task"]["processing_turn_id"] == turn.public_id
    db_session.expire_all()
    latest = db_session.get(AssistantTurn, turn.id)
    assert latest.status == "RUNNING"
    assert latest.lease_owner == "live-worker"
    assert db_session.get(AssistantTask, task.id).active_turn_id == turn.id
    assert _done_events(db_session, turn) == []


@pytest.mark.parametrize("terminal_status", ["SUCCEEDED", "FAILED"])
def test_stop_on_terminal_turn_reports_already_terminal_and_changes_nothing(
    client: TestClient,
    db_session: Session,
    running_turn: tuple[AssistantTask, AssistantTurn],
    terminal_status: str,
) -> None:
    task, turn = running_turn
    turn.status = terminal_status
    turn.lease_owner = None
    task.active_turn_id = None
    db_session.commit()

    response = client.post(_stop_url(task, turn))

    assert response.status_code == 200, response.text
    assert response.json()["stopped"] is False
    assert response.json()["reason"] == "ALREADY_TERMINAL"
    db_session.expire_all()
    assert db_session.get(AssistantTurn, turn.id).status == terminal_status
    assert _done_events(db_session, turn) == []


def test_repeated_stop_is_idempotent(
    client: TestClient,
    db_session: Session,
    running_turn: tuple[AssistantTask, AssistantTurn],
) -> None:
    task, turn = running_turn

    first = client.post(_stop_url(task, turn))
    second = client.post(_stop_url(task, turn))

    assert first.json()["reason"] == "STOPPED"
    assert second.status_code == 200, second.text
    assert second.json()["stopped"] is False
    assert second.json()["reason"] == "ALREADY_TERMINAL"
    assert second.json()["task"] == first.json()["task"]
    db_session.expire_all()
    assert db_session.get(AssistantTurn, turn.id).status == "CANCELLED"
    assert len(_done_events(db_session, turn)) == 1


@pytest.mark.parametrize(("other_team", "other_user"), [(1, 99), (99, 2)])
def test_stop_is_owner_and_team_scoped(
    client: TestClient,
    db_session: Session,
    running_turn: tuple[AssistantTask, AssistantTurn],
    other_team: int,
    other_user: int,
) -> None:
    from app.core import deps

    task, turn = running_turn
    app.dependency_overrides[deps.get_current_active_user] = lambda: SimpleNamespace(id=other_user, team_id=other_team)
    app.dependency_overrides[deps.get_current_user_team] = lambda: other_team

    response = client.post(_stop_url(task, turn))

    assert response.status_code == 404
    db_session.expire_all()
    assert db_session.get(AssistantTurn, turn.id).status == "RUNNING"
    assert db_session.get(AssistantTask, task.id).active_turn_id == turn.id
    assert _done_events(db_session, turn) == []


def test_stop_cannot_reach_a_turn_through_another_task(
    client: TestClient,
    db_session: Session,
    running_turn: tuple[AssistantTask, AssistantTurn],
) -> None:
    task, turn = running_turn
    other = client.post(
        "/api/v1/assistant/tasks",
        json={"goal": "另一条任务", "client_request_id": "create-stop-other-task"},
    ).json()

    crossed = client.post(f"/api/v1/assistant/tasks/{other['public_id']}/turns/{turn.public_id}/stop")
    unknown = client.post(f"/api/v1/assistant/tasks/{task.public_id}/turns/turn_missing/stop")

    assert crossed.status_code == 404
    assert unknown.status_code == 404
    db_session.expire_all()
    assert db_session.get(AssistantTurn, turn.id).status == "RUNNING"
    assert _done_events(db_session, turn) == []


@pytest.fixture
def operation_tables(db_session: Session) -> Session:
    Base.metadata.create_all(
        db_session.get_bind(),
        tables=[AgentSession.__table__, AgentAsyncOperation.__table__, AgentAsyncOperationEvent.__table__],
    )
    return db_session


def _seed_operation(db: Session, *, key: str, team_id: int, user_id: int, status: str) -> AgentAsyncOperation:
    operation = AgentAsyncOperation(
        public_id=f"aop_{key}",
        operation_key=f"assistant-ops:{key}",
        request_id=f"req-{key}",
        team_id=team_id,
        user_id=user_id,
        operation_type="customer_enrichment",
        resource_type="customer",
        resource_public_id=f"cus_{key}",
        status=status,
        summary=f"后台任务 {key}",
    )
    db.add(operation)
    return operation


def test_operations_are_scoped_to_current_user_and_team_with_isolated_statuses(
    client: TestClient,
    operation_tables: Session,
) -> None:
    db = operation_tables
    raw_statuses = [
        value for name, value in vars(AgentAsyncOperationStatus).items() if not name.startswith("_")
    ]
    for status in raw_statuses:
        _seed_operation(db, key=f"mine-{status.lower()}", team_id=1, user_id=2, status=status)
    _seed_operation(db, key="other-user", team_id=1, user_id=99, status="RUNNING")
    _seed_operation(db, key="other-team", team_id=99, user_id=2, status="RUNNING")
    db.commit()

    response = client.get("/api/v1/assistant/operations")

    assert response.status_code == 200, response.text
    body = response.json()
    returned = {item["public_id"]: item["status"] for item in body}
    assert set(returned) == {f"aop_mine-{status.lower()}" for status in raw_statuses}
    allowed = set(get_args(AssistantAsyncOperationStatusLiteral))
    assert allowed == {"QUEUED", "RUNNING", "DEGRADED", "SUCCEEDED", "FAILED"}
    assert set(returned.values()) <= allowed
    for status in allowed:
        assert returned[f"aop_mine-{status.lower()}"] == status

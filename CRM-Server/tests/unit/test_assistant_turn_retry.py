"""Explicit retry of one durable accepted turn, without replaying user input."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.orm import sessionmaker

from app.api import assistant as api
from app.main import app
from app.models.assistant import AssistantTask
from app.models.assistant_turn import AssistantRequest, AssistantTurn, AssistantTurnEvent
from app.services.assistant import turns
from app.utils.time import business_now
from tests.unit.test_assistant_api import client as client
from tests.unit.test_assistant_api import db_session as db_session
from tests.unit.test_assistant_api import override_auth as override_auth

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

@pytest.fixture
def retryable_turn(client: TestClient, db_session: Session) -> tuple[AssistantTask, AssistantTurn]:

    created = client.post(
        "/api/v1/assistant/tasks",
        json={"goal": "重试同一条跟进", "client_request_id": "create-retry-same-turn"},
    )
    task = db_session.query(AssistantTask).filter_by(public_id=created.json()["public_id"]).one()
    turn, _ = turns.accept_submit(
        db_session,
        task=task,
        key="retry-same-turn-input",
        input_data={"kind": "text", "text": "今天跟客户确认服务器准备情况", "choice": None},
        action_id=None,
        expected_version=None,
    )
    return task, turn


@pytest.mark.parametrize("initial_status", ["PENDING", "RUNNING", "EXPIRED"])
def test_retry_restarts_only_an_expired_turn(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch,
    retryable_turn: tuple[AssistantTask, AssistantTurn], initial_status: str,
) -> None:
    task, turn = retryable_turn
    if initial_status != "PENDING":
        turn.status = "RUNNING"
        turn.lease_owner = "old-worker"
        turn.lease_version = 3
        turn.lease_expires_at = business_now() + timedelta(seconds=-1 if initial_status == "EXPIRED" else 300)
        db_session.commit()
    observed_version = turn.lease_version
    observed_attempts = turn.attempts
    scheduled = []
    monkeypatch.setattr(api, "schedule_turn", lambda turn_id, **kwargs: scheduled.append(turn_id))
    url = f"/api/v1/assistant/tasks/{task.public_id}/turns/{turn.public_id}"
    before = client.get(url)
    assert before.status_code == 200
    assert before.json()["reprocess_allowed"] is (initial_status == "EXPIRED")
    assert scheduled == []  # GET remains read-only.
    response = client.post(url + "/retry", json={"expected_lease_version": observed_version, "after_seq": 0})
    assert response.status_code == 200
    body = response.json()
    db_session.expire_all()
    latest = db_session.get(AssistantTurn, turn.id)
    assert db_session.query(AssistantTurn).count() == 1
    assert db_session.query(AssistantRequest).filter(AssistantRequest.turn_id.is_not(None)).count() == 1
    if initial_status != "EXPIRED":
        assert body["status"] == initial_status
        assert body["lease_version"] == observed_version
        assert latest.attempts == observed_attempts
        assert scheduled == []
        return
    assert body["turn_id"] == turn.public_id
    assert body["status"] == "PENDING"
    assert body["task"]["processing_turn_id"] == turn.public_id
    assert body["reprocess_allowed"] is False
    assert latest.lease_version > observed_version
    assert latest.lease_owner is None
    assert latest.lease_expires_at is None
    assert latest.attempts == observed_attempts
    assert scheduled == [turn.id]


def test_retry_with_stale_observed_version_cannot_reclaim_the_new_worker(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch,
    retryable_turn: tuple[AssistantTask, AssistantTurn],
) -> None:
    task, turn = retryable_turn
    turn.status = "RUNNING"
    turn.lease_owner = "expired-worker"
    turn.lease_expires_at = business_now() + timedelta(seconds=-1)
    db_session.commit()
    scheduled = []
    monkeypatch.setattr(api, "schedule_turn", lambda turn_id, **kwargs: scheduled.append(turn_id))
    url = f"/api/v1/assistant/tasks/{task.public_id}/turns/{turn.public_id}/retry"
    request = {"expected_lease_version": turn.lease_version}
    assert client.post(url, json=request).status_code == 200
    new_version = turns.claim(db_session, turn_id=turn.id, owner="new-worker")
    assert new_version is not None
    replay = client.post(url, json=request)
    assert replay.status_code == 200
    assert replay.json()["status"] == "RUNNING"
    assert replay.json()["lease_version"] == new_version
    db_session.expire_all()
    assert db_session.get(AssistantTurn, turn.id).lease_owner == "new-worker"
    assert scheduled == [turn.id]


@pytest.mark.parametrize("terminal_status", ["SUCCEEDED", "FAILED"])
def test_retry_never_replays_a_terminal_turn(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch,
    retryable_turn: tuple[AssistantTask, AssistantTurn], terminal_status: str,
) -> None:

    task, turn = retryable_turn
    turn.status = terminal_status
    task.active_turn_id = None
    db_session.commit()
    scheduled = []
    monkeypatch.setattr(api, "schedule_turn", lambda turn_id, **kwargs: scheduled.append(turn_id))
    response = client.post(
        f"/api/v1/assistant/tasks/{task.public_id}/turns/{turn.public_id}/retry",
        json={"expected_lease_version": 0},
    )
    assert response.status_code == 200
    assert response.json()["status"] == terminal_status
    assert scheduled == []
    assert db_session.query(AssistantTurn).count() == 1


@pytest.mark.parametrize("other_team,other_user", [(1, 99), (99, 2)])
def test_retry_turn_is_owner_and_team_scoped(
    client: TestClient, db_session: Session, retryable_turn: tuple[AssistantTask, AssistantTurn],
    other_team: int, other_user: int,
) -> None:
    from app.core import deps

    task, turn = retryable_turn
    app.dependency_overrides[deps.get_current_active_user] = lambda: SimpleNamespace(id=other_user, team_id=other_team)
    app.dependency_overrides[deps.get_current_user_team] = lambda: other_team
    response = client.post(
        f"/api/v1/assistant/tasks/{task.public_id}/turns/{turn.public_id}/retry",
        json={"expected_lease_version": 0},
    )
    assert response.status_code == 404
    db_session.expire_all()
    assert db_session.get(AssistantTurn, turn.id).lease_version == 0


def test_live_retry_does_not_cancel_the_running_worker(
    db_session: Session, retryable_turn: tuple[AssistantTask, AssistantTurn], monkeypatch: pytest.MonkeyPatch,
) -> None:
    task, turn = retryable_turn
    started = asyncio.Event()
    old_released = asyncio.Event()
    calls = []

    async def handle_task(
        _db: Session, task: AssistantTask, _user_input: object, reporter: object
    ) -> SimpleNamespace:
        del reporter
        calls.append("started")
        started.set()
        await old_released.wait()
        calls.append("old-side-effect")
        return SimpleNamespace(task=task, reply=SimpleNamespace(message="原来的下一步"))

    monkeypatch.setattr("app.api.assistant._coordinator", SimpleNamespace(handle_task=handle_task))
    factory = sessionmaker(bind=db_session.get_bind(), autoflush=False)

    async def scenario() -> None:
        old = asyncio.create_task(turns.execute_turn(turn.id, factory=factory))
        await asyncio.wait_for(started.wait(), timeout=5)
        with factory() as db:
            observed = db.get(AssistantTurn, turn.id)
            version = observed.lease_version
            attempts = observed.attempts
            result = turns.retry_owned_turn(
                db, team_id=1, user_id=2, task_public_id=task.public_id,
                turn_public_id=turn.public_id, expected_lease_version=version,
            )
            assert result is not None and result[2] is False
            assert result[1].lease_version == version
            assert result[1].attempts == attempts
        old_released.set()
        await asyncio.wait_for(old, timeout=5)

    asyncio.run(scenario())
    db_session.expire_all()
    latest = db_session.get(AssistantTurn, turn.id)
    assert latest.status == "SUCCEEDED"
    assert latest.attempts == 1
    assert calls == ["started", "old-side-effect"]
    assert db_session.query(AssistantTurnEvent).filter_by(turn_id=turn.id, event="waiting").count() == 1


def test_failed_retryable_turn_restarts_without_a_second_request(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch,
    retryable_turn: tuple[AssistantTask, AssistantTurn],
) -> None:
    task, turn = retryable_turn
    turn.status = "FAILED"
    task.active_turn_id = None
    turns.add_event(
        db_session,
        turn,
        "error",
        {"code": "RETRYABLE_DEPENDENCY_FAILURE", "retryable": True, "message": "处理未完成请重试"},
    )
    db_session.commit()
    scheduled = []
    monkeypatch.setattr(api, "schedule_turn", lambda turn_id, **kwargs: scheduled.append(turn_id))
    response = client.post(
        f"/api/v1/assistant/tasks/{task.public_id}/turns/{turn.public_id}/retry",
        json={"expected_lease_version": turn.lease_version, "after_seq": 0},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING"
    assert response.json()["task"]["processing_turn_id"] == turn.public_id
    assert scheduled == [turn.id]
    assert db_session.query(AssistantTurn).count() == 1


def test_activity_receipt_blocks_reprocess(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch,
    retryable_turn: tuple[AssistantTask, AssistantTurn],
) -> None:
    task, turn = retryable_turn
    turn.status = "FAILED"
    task.active_turn_id = None
    task.committed_json = [{"kind": "customer_activity", "public_id": "act_existing"}]
    turns.add_event(
        db_session,
        turn,
        "error",
        {"code": "RETRYABLE_DEPENDENCY_FAILURE", "retryable": True, "message": "处理未完成请重试"},
    )
    db_session.commit()
    scheduled = []
    monkeypatch.setattr(api, "schedule_turn", lambda turn_id, **kwargs: scheduled.append(turn_id))
    response = client.post(
        f"/api/v1/assistant/tasks/{task.public_id}/turns/{turn.public_id}/retry",
        json={"expected_lease_version": turn.lease_version},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "FAILED"
    assert response.json()["reprocess_allowed"] is False
    assert scheduled == []

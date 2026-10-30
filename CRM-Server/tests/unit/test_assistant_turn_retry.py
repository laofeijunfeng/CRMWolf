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


def test_organize_stage_failure_is_failed_and_reprocessed_without_a_new_request(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch,
    retryable_turn: tuple[AssistantTask, AssistantTurn],
) -> None:
    from app.models.assistant_conversation import AssistantConversationEntry
    from app.services.assistant.failure_contract import (
        ORGANIZE_FAILURE_MESSAGE,
        AssistantFailureCode,
        AssistantStageFailure,
    )

    task, turn = retryable_turn
    requests_before = db_session.query(AssistantRequest).count()
    entries_before = db_session.query(AssistantConversationEntry).count()
    from app.services.assistant.contracts import TaskDraft

    source = "今天跟客户确认服务器准备情况"

    async def handle_task(db: Session, current: AssistantTask, _user_input: object, reporter: object = None) -> None:
        current.draft_json = TaskDraft(source_segments=[source]).model_dump(mode="json")
        current.last_error_code = "UPSTREAM_TIMEOUT"
        current.committed_json = []
        db.flush()
        raise AssistantStageFailure(
            code=AssistantFailureCode.UPSTREAM_TIMEOUT,
            stage="structure",
            retryable=True,
            user_message=ORGANIZE_FAILURE_MESSAGE,
            task_public_id=current.public_id,
        )

    monkeypatch.setattr("app.api.assistant._coordinator", SimpleNamespace(handle_task=handle_task))
    factory = sessionmaker(bind=db_session.get_bind(), autoflush=False)
    asyncio.run(turns.execute_turn(turn.id, factory=factory))
    db_session.expire_all()
    latest_turn = db_session.get(AssistantTurn, turn.id)
    latest_task = db_session.get(AssistantTask, task.id)
    assert latest_turn is not None and latest_task is not None
    assert latest_turn.status == "FAILED"
    assert latest_turn.last_error_code == "UPSTREAM_TIMEOUT"
    assert latest_task.status == "ACTIVE"
    assert latest_task.active_turn_id is None
    assert latest_task.last_error_code == "UPSTREAM_TIMEOUT"
    assert latest_task.draft_json["source_segments"] == [source]
    assert latest_task.committed_json == []
    events = db_session.query(AssistantTurnEvent).filter_by(turn_id=turn.id).all()
    errors = [event for event in events if event.event == "error"]
    assert len(errors) == 1
    assert errors[0].data_json["code"] == "UPSTREAM_TIMEOUT"
    assert errors[0].data_json["stage"] == "structure"
    assert errors[0].data_json["retryable"] is True
    assert errors[0].data_json["task_public_id"] == task.public_id
    assert errors[0].data_json["message"] == ORGANIZE_FAILURE_MESSAGE
    assert not any(event.event == "waiting" for event in events)
    assert db_session.query(AssistantRequest).count() == requests_before
    assert db_session.query(AssistantConversationEntry).count() == entries_before

    scheduled: list[int] = []
    monkeypatch.setattr(api, "schedule_turn", lambda turn_id, **kwargs: scheduled.append(turn_id))
    response = client.post(
        f"/api/v1/assistant/tasks/{task.public_id}/turns/{turn.public_id}/retry",
        json={"expected_lease_version": latest_turn.lease_version, "after_seq": 0},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING"
    assert response.json()["reprocess_allowed"] is False
    assert scheduled == [turn.id]
    db_session.expire_all()
    assert db_session.query(AssistantTurn).count() == 1
    assert db_session.query(AssistantRequest).count() == requests_before
    assert db_session.query(AssistantConversationEntry).count() == entries_before


def test_unexpected_turn_exception_rolls_back_uncommitted_task_edits(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch,
    retryable_turn: tuple[AssistantTask, AssistantTurn],
) -> None:
    task, turn = retryable_turn
    original_goal = task.goal

    async def handle_task(db: Session, current: AssistantTask, _user_input: object, reporter: object = None) -> None:
        current.goal = "不应提交的目标"
        db.flush()
        raise RuntimeError("boom")

    monkeypatch.setattr("app.api.assistant._coordinator", SimpleNamespace(handle_task=handle_task))
    factory = sessionmaker(bind=db_session.get_bind(), autoflush=False)
    asyncio.run(turns.execute_turn(turn.id, factory=factory))
    db_session.expire_all()
    latest_turn = db_session.get(AssistantTurn, turn.id)
    latest_task = db_session.get(AssistantTask, task.id)
    assert latest_turn is not None and latest_task is not None
    assert latest_turn.status == "FAILED"
    assert latest_task.goal == original_goal
    assert latest_task.status == "ACTIVE"


def test_recover_pending_turn_does_not_create_entry_or_request(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch,
    retryable_turn: tuple[AssistantTask, AssistantTurn],
) -> None:
    from app.models.assistant_conversation import AssistantConversationEntry

    _task, turn = retryable_turn
    requests_before = db_session.query(AssistantRequest).count()
    entries_before = db_session.query(AssistantConversationEntry).count()
    scheduled: list[int] = []
    monkeypatch.setattr(turns, "schedule_turn", lambda turn_id, **kwargs: scheduled.append(turn_id))
    recovered = asyncio.run(turns.recover_turns())
    assert turn.id in scheduled
    assert recovered >= 1
    db_session.expire_all()
    assert db_session.query(AssistantRequest).count() == requests_before
    assert db_session.query(AssistantConversationEntry).count() == entries_before
    assert db_session.get(AssistantTurn, turn.id).status == "PENDING"


def test_overdue_attempt_fails_closed_without_a_live_worker(
    db_session: Session, retryable_turn: tuple[AssistantTask, AssistantTurn]
) -> None:
    task, turn = retryable_turn
    turn.status = "RUNNING"
    turn.lease_owner = "dead-worker"
    turn.lease_version = 4
    turn.lease_expires_at = business_now() + timedelta(seconds=200)
    db_session.commit()
    turns.add_event(
        db_session,
        turn,
        "attempt",
        {"started_at": (business_now() - timedelta(seconds=181)).isoformat(), "attempt": 1},
    )
    db_session.commit()
    assert turns.close_overdue_turn(db_session, task, turn) is True
    db_session.refresh(turn)
    db_session.refresh(task)
    assert turn.status == "FAILED"
    assert turn.last_error_code == "UPSTREAM_TIMEOUT"
    assert task.active_turn_id is None
    error = (
        db_session.query(AssistantTurnEvent)
        .filter_by(turn_id=turn.id, event="error")
        .one()
    )
    assert error.data_json["retryable"] is True
    assert error.data_json["activity_written"] is False
    assert "尚未写入客户活动" in error.data_json["message"]

"""/v1/assistant endpoint contracts: ownership and view projection."""
# ruff: noqa: RUF001

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.main import app
from app.models.assistant import (
    AssistantAction,
    AssistantTask,
    AssistantTaskStatus,
)
from app.models.assistant_turn import AssistantRequest, AssistantTurn, AssistantTurnEvent
from app.services.assistant.contracts import TaskDraft


def _make_user(team_id: int, user_id: int):
    from types import SimpleNamespace

    return SimpleNamespace(id=user_id, team_id=team_id)


@pytest.fixture
def override_auth():
    from app.core import deps
    from app.main import app

    user = _make_user(team_id=1, user_id=2)
    app.dependency_overrides[deps.get_current_active_user] = lambda: user
    app.dependency_overrides[deps.get_current_user_team] = lambda: 1
    yield user
    app.dependency_overrides.pop(deps.get_current_active_user, None)

    app.dependency_overrides.pop(deps.get_current_user_team, None)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def client(db_session, override_auth, monkeypatch):
    from app.core.database import get_db
    from app.services.assistant import turns

    def _get_db_override():
        yield db_session

    monkeypatch.setattr(turns, "SessionLocal", sessionmaker(bind=db_session.get_bind(), autoflush=False))
    app.dependency_overrides[get_db] = _get_db_override
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


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
            AssistantTask.__table__,
            AssistantAction.__table__,
            AssistantRequest.__table__,
            AssistantTurn.__table__,
            AssistantTurnEvent.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_create_task_returns_active_view(client):
    response = client.post(
        "/api/v1/assistant/tasks", json={"goal": "记录睿狐科技的会议", "client_request_id": "create-meeting-001"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ACTIVE"
    assert body["draft"]["customer"]["status"] == "MISSING"
    assert body["waiting"] is None


def test_submit_stream_survives_expired_request_user(client):
    from sqlalchemy.orm.exc import DetachedInstanceError

    created = client.post("/api/v1/assistant/tasks", json={"goal": "流测试", "client_request_id": "create-stream-user"})

    class ExpiredUser:
        def __init__(self):
            self.reads = 0

        @property
        def id(self):
            self.reads += 1
            if self.reads > 1:
                raise DetachedInstanceError("expired")
            return 2

    from app.core import deps
    from app.main import app

    app.dependency_overrides[deps.get_current_active_user] = lambda: ExpiredUser()
    with client.stream(
        "POST",
        f"/api/v1/assistant/tasks/{created.json()['public_id']}/submit",
        json={"kind": "cancel", "client_request_id": "submit-stream-user"},
    ) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert "event: accepted" in body
    assert "event: waiting" in body


def test_create_request_replay_returns_same_task_and_conflict_on_different_goal(client, db_session):
    request = {"goal": "记录今天与甲客户的会议", "client_request_id": "create-0123456789"}
    first = client.post("/api/v1/assistant/tasks", json=request)
    replay = client.post("/api/v1/assistant/tasks", json=request)
    conflict = client.post(
        "/api/v1/assistant/tasks",
        json={**request, "goal": "记录完全不同的跟进"},
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert first.json()["public_id"] == replay.json()["public_id"]
    assert conflict.status_code == 409
    assert db_session.query(AssistantTask).count() == 1


def test_get_task_rejects_other_owner(client, db_session):
    created = client.post("/api/v1/assistant/tasks", json={"goal": "记录跟进", "client_request_id": "create-get-001"})
    public_id = created.json()["public_id"]

    other = AssistantTask(
        team_id=999,
        user_id=999,
        status=AssistantTaskStatus.ACTIVE,
        goal="别人的任务",
        draft_json=TaskDraft().model_dump(mode="json"),
        authority_json={},
        committed_json=[],
    )
    db_session.add(other)
    db_session.commit()

    response = client.get(f"/api/v1/assistant/tasks/{other.public_id}")
    assert response.status_code == 404

    owned = client.get(f"/api/v1/assistant/tasks/{public_id}")
    assert owned.status_code == 200


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    import json as _json

    events: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        name = ""
        data = "{}"
        for line in lines:
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = line[len("data: ") :]
        if name:
            events.append((name, _json.loads(data)))
    return events


def test_submit_cancel_closes_task_via_sse(client):
    created = client.post(
        "/api/v1/assistant/tasks", json={"goal": "记录跟进", "client_request_id": "create-cancel-001"}
    )
    public_id = created.json()["public_id"]

    response = client.post(
        f"/api/v1/assistant/tasks/{public_id}/submit",
        json={"kind": "cancel", "client_request_id": "cancel-turn-001"},
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "accepted"
    assert names[-1] == "waiting"
    final = events[-1][1]
    assert final["task"]["status"] == "CANCELLED"
    assert "已取消" in final["message"]


def test_submit_replay_returns_original_turn_after_task_changes(client, db_session):
    task_id = client.post(
        "/api/v1/assistant/tasks",
        json={
            "goal": "取消旧任务",
            "client_request_id": "create-replay-001",
        },
    ).json()["public_id"]
    request = {"kind": "cancel", "client_request_id": "cancel-replay-001"}
    first = client.post(f"/api/v1/assistant/tasks/{task_id}/submit", json=request)
    replay = client.post(f"/api/v1/assistant/tasks/{task_id}/submit", json=request)
    conflict = client.post(
        f"/api/v1/assistant/tasks/{task_id}/submit",
        json={
            **request,
            "text": "different payload",
        },
    )

    assert first.status_code == replay.status_code == 200
    first_events, replay_events = _parse_sse(first.text), _parse_sse(replay.text)
    assert first_events == replay_events
    turn_id = first_events[0][1]["turn_id"]
    recovered = client.get(f"/api/v1/assistant/tasks/{task_id}/turns/{turn_id}?after_seq=1")
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "SUCCEEDED"
    assert recovered.json()["events"][-1]["data"]["task"]["status"] == "CANCELLED"
    assert conflict.status_code == 409
    assert db_session.query(AssistantTurn).count() == 1


def test_stage_is_replayable_while_worker_is_still_running(db_session, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from app.services.assistant.events import stage
    from app.services.assistant.turns import accept_submit, execute_turn

    task = AssistantTask(
        team_id=1,
        user_id=2,
        status=AssistantTaskStatus.ACTIVE,
        goal="记录活动",
        draft_json=TaskDraft().model_dump(mode="json"),
        authority_json={},
        committed_json=[],
    )
    db_session.add(task)
    db_session.commit()
    turn, _ = accept_submit(
        db_session,
        task=task,
        key="stage-before-finish",
        input_data={"kind": "text", "text": "客户反馈", "choice": None},
        action_id=None,
        expected_version=None,
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def handle_task(db, task, user_input, reporter):
        reporter.stage_start(stage("structure"))
        started.set()
        await release.wait()
        reporter.stage_done(stage("structure"), ms=1)
        return SimpleNamespace(task=task, reply=SimpleNamespace(message="已整理"))

    monkeypatch.setattr("app.api.assistant._coordinator", SimpleNamespace(handle_task=handle_task))

    async def scenario():
        runner = asyncio.create_task(execute_turn(turn.id, factory=sessionmaker(bind=db_session.get_bind())))
        try:
            await asyncio.wait_for(started.wait(), timeout=5)
            db_session.expire_all()
            running = db_session.get(AssistantTurn, turn.id)
            events = (
                db_session.query(AssistantTurnEvent).filter_by(turn_id=turn.id).order_by(AssistantTurnEvent.seq).all()
            )
            assert running.status == "RUNNING"
            assert [(event.event, event.data_json.get("phase")) for event in events] == [
                ("accepted", None),
                ("stage", "start"),
            ]
        finally:
            release.set()
            await asyncio.wait_for(runner, timeout=5)

    asyncio.run(scenario())


def test_slow_turn_renews_lease_and_cannot_be_reclaimed(db_session, monkeypatch):
    import asyncio
    from datetime import timedelta
    from types import SimpleNamespace

    from app.services.assistant import turns
    from app.utils.time import business_now

    task = AssistantTask(
        team_id=1,
        user_id=2,
        status=AssistantTaskStatus.ACTIVE,
        goal="慢模型",
        draft_json=TaskDraft().model_dump(mode="json"),
        authority_json={},
        committed_json=[],
    )
    db_session.add(task)
    db_session.commit()
    turn, _ = turns.accept_submit(
        db_session,
        task=task,
        key="slow-lease",
        input_data={"kind": "text", "text": "继续", "choice": None},
        action_id=None,
        expected_version=None,
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def handle_task(db, task, user_input, reporter):
        started.set()
        await release.wait()
        return SimpleNamespace(task=task, reply=SimpleNamespace(message="处理完成"))

    monkeypatch.setattr("app.api.assistant._coordinator", SimpleNamespace(handle_task=handle_task))
    monkeypatch.setattr(turns, "LEASE_SECONDS", 1)

    async def scenario():
        runner = asyncio.create_task(turns.execute_turn(turn.id, factory=sessionmaker(bind=db_session.get_bind())))
        try:
            await asyncio.wait_for(started.wait(), timeout=5)
            await asyncio.sleep(1.3)
            db_session.rollback()
            db_session.expire_all()
            running = db_session.get(AssistantTurn, turn.id)
            assert running.status == "RUNNING"
            assert running.lease_expires_at > business_now() + timedelta(milliseconds=200)
            db_session.rollback()
            with sessionmaker(bind=db_session.get_bind())() as rival:
                assert turns.claim(rival, turn_id=turn.id, owner="rival") is None
        finally:
            release.set()
            await asyncio.wait_for(runner, timeout=5)

    asyncio.run(scenario())
    db_session.expire_all()
    assert db_session.get(AssistantTurn, turn.id).status == "SUCCEEDED"


def test_reclaimed_turn_cancels_old_worker_without_committing_its_side_effect(db_session, monkeypatch):
    import asyncio
    from datetime import timedelta
    from types import SimpleNamespace

    from sqlalchemy import update

    from app.services.assistant import turns
    from app.utils.time import business_now

    task = AssistantTask(
        team_id=1,
        user_id=2,
        status=AssistantTaskStatus.ACTIVE,
        goal="记录活动",
        draft_json=TaskDraft().model_dump(mode="json"),
        authority_json={},
        committed_json=[],
    )
    db_session.add(task)
    db_session.commit()
    turn, _ = turns.accept_submit(
        db_session,
        task=task,
        key="lease-takeover-001",
        input_data={"kind": "text", "text": "继续", "choice": None},
        action_id=None,
        expected_version=None,
    )
    started = asyncio.Event()
    side_effects = []

    async def handle_task(db, task, user_input, reporter):
        started.set()
        await asyncio.sleep(10)
        side_effects.append(task.id)
        return SimpleNamespace(task=task, reply=SimpleNamespace(message="成功"))

    monkeypatch.setattr("app.api.assistant._coordinator", SimpleNamespace(handle_task=handle_task))
    monkeypatch.setattr(turns, "LEASE_SECONDS", 1)

    async def scenario():
        worker = asyncio.create_task(turns.execute_turn(turn.id, factory=sessionmaker(bind=db_session.get_bind())))
        await asyncio.wait_for(started.wait(), timeout=5)
        db_session.rollback()
        with sessionmaker(bind=db_session.get_bind())() as rival:
            rival.execute(
                update(AssistantTurn)
                .where(AssistantTurn.id == turn.id)
                .values(
                    lease_owner="rival",
                    lease_version=AssistantTurn.lease_version + 1,
                    lease_expires_at=business_now() + timedelta(seconds=5),
                )
            )
            rival.commit()
        await asyncio.wait_for(worker, timeout=5)

    asyncio.run(scenario())
    db_session.expire_all()
    assert side_effects == []
    assert db_session.get(AssistantTurn, turn.id).status == "RUNNING"
    assert db_session.get(AssistantTurn, turn.id).lease_owner == "rival"
    assert db_session.get(AssistantTask, task.id).active_turn_id == turn.id


def test_crm_command_lease_guard_rejects_takeover_before_side_effect(db_session, monkeypatch):
    import asyncio
    from datetime import timedelta
    from types import SimpleNamespace

    from sqlalchemy import update

    from app.services.assistant import turns
    from app.utils.time import business_now

    task = AssistantTask(
        team_id=1,
        user_id=2,
        status=AssistantTaskStatus.ACTIVE,
        goal="记录活动",
        draft_json=TaskDraft().model_dump(mode="json"),
        authority_json={},
        committed_json=[],
    )
    db_session.add(task)
    db_session.commit()
    turn, _ = turns.accept_submit(
        db_session,
        task=task,
        key="crm-guard-001",
        input_data={"kind": "text", "text": "继续", "choice": None},
        action_id=None,
        expected_version=None,
    )
    side_effects = []
    lease_guard_checked = []

    async def handle_task(db, task, user_input, reporter):
        with sessionmaker(bind=db_session.get_bind())() as rival:
            rival.execute(
                update(AssistantTurn)
                .where(AssistantTurn.id == turn.id)
                .values(
                    lease_owner="rival",
                    lease_version=AssistantTurn.lease_version + 1,
                    lease_expires_at=business_now() + timedelta(seconds=5),
                )
            )
            rival.commit()
        lease_guard_checked.append(True)
        turns.assert_owned_execution_lease(db, task)
        side_effects.append(task.id)
        return SimpleNamespace(task=task, reply=SimpleNamespace(message="成功"))

    monkeypatch.setattr("app.api.assistant._coordinator", SimpleNamespace(handle_task=handle_task))
    asyncio.run(turns.execute_turn(turn.id, factory=sessionmaker(bind=db_session.get_bind())))

    db_session.expire_all()
    assert lease_guard_checked == [True]
    assert side_effects == []
    assert db_session.get(AssistantTurn, turn.id).status == "RUNNING"
    assert db_session.get(AssistantTurn, turn.id).lease_owner == "rival"


def test_orphaned_task_turn_fails_with_replayable_error(db_session):
    import asyncio

    from app.services.assistant.turns import accept_submit, execute_turn

    task = AssistantTask(
        team_id=1,
        user_id=2,
        status=AssistantTaskStatus.ACTIVE,
        goal="记录活动",
        draft_json=TaskDraft().model_dump(mode="json"),
        authority_json={},
        committed_json=[],
    )
    db_session.add(task)
    db_session.commit()
    turn, _ = accept_submit(
        db_session,
        task=task,
        key="submit-orphan-001",
        input_data={"kind": "cancel", "text": None, "choice": None},
        action_id=None,
        expected_version=None,
    )
    db_session.delete(task)
    db_session.commit()

    asyncio.run(execute_turn(turn.id, factory=sessionmaker(bind=db_session.get_bind())))
    db_session.expire_all()
    assert db_session.get(AssistantTurn, turn.id).status == "FAILED"
    events = db_session.query(AssistantTurnEvent).filter_by(turn_id=turn.id).order_by(AssistantTurnEvent.seq).all()
    assert [event.event for event in events] == ["accepted", "error"]


def test_submit_after_terminal_is_rejected(client):
    created = client.post(
        "/api/v1/assistant/tasks", json={"goal": "记录跟进", "client_request_id": "create-terminal-001"}
    )
    public_id = created.json()["public_id"]
    client.post(
        f"/api/v1/assistant/tasks/{public_id}/submit",
        json={"kind": "cancel", "client_request_id": "cancel-terminal-001"},
    )

    response = client.post(
        f"/api/v1/assistant/tasks/{public_id}/submit",
        json={"kind": "text", "text": "再记一条", "client_request_id": "after-terminal-001"},
    )

    assert response.status_code == 409


def test_sse_text_turn_emits_accepted_stages_waiting(client):
    """LLM seam is unavailable in tests; expect error event AI_UNAVAILABLE."""

    created = client.post("/api/v1/assistant/tasks", json={"goal": "记录跟进", "client_request_id": "create-text-001"})
    public_id = created.json()["public_id"]

    response = client.post(
        f"/api/v1/assistant/tasks/{public_id}/submit",
        json={"kind": "text", "text": "今天聊了 POC", "client_request_id": "submit-text-001"},
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "accepted"
    assert names[-1] in {"waiting", "error"}


def test_sse_stage_events_carry_payload(client):
    """Cancel turn emits no stages; accepted carries turn_id."""

    created = client.post("/api/v1/assistant/tasks", json={"goal": "取消场景", "client_request_id": "create-stage-001"})
    public_id = created.json()["public_id"]

    response = client.post(
        f"/api/v1/assistant/tasks/{public_id}/submit",
        json={"kind": "cancel", "client_request_id": "cancel-stage-001"},
    )

    events = _parse_sse(response.text)
    accepted = events[0][1]
    assert accepted["turn_id"].startswith("atn_")
    stage_events = [data for name, data in events if name == "stage"]
    assert stage_events == []


def test_change_kind_resets_slots_and_clears_waiting(client, db_session):
    created = client.post(
        "/api/v1/assistant/tasks", json={"goal": "改类型测试", "client_request_id": "create-kind-001"}
    )
    public_id = created.json()["public_id"]

    response = client.post(
        f"/api/v1/assistant/tasks/{public_id}/change-kind",
        json={"kind": "ONLINE_MEETING"},
    )

    assert response.status_code == 200
    body = response.json()
    # Kind stays as the user's hint (TRD G6); slots and waiting are reset.
    assert body["activity_kind"] == "ONLINE_MEETING"
    assert body["draft"]["content"]["status"] == "MISSING"
    assert body["waiting"] is None


def test_change_kind_rejects_unknown_kind(client):
    created = client.post(
        "/api/v1/assistant/tasks", json={"goal": "非法类型", "client_request_id": "create-unknown-kind-001"}
    )
    public_id = created.json()["public_id"]

    response = client.post(
        f"/api/v1/assistant/tasks/{public_id}/change-kind",
        json={"kind": "VIDEO_CALL"},
    )
    assert response.status_code == 422


def test_list_tasks_carries_last_modified_time(client):
    created = client.post(
        "/api/v1/assistant/tasks", json={"goal": "时间戳测试", "client_request_id": "create-list-001"}
    )
    public_id = created.json()["public_id"]

    listed = client.get("/api/v1/assistant/tasks")
    row = next(t for t in listed.json() if t["public_id"] == public_id)
    assert row["last_modified_time"] is not None
    assert "T" in row["last_modified_time"]


def _issue_waiting(db_session, task, *, type, field=None, candidates=None):
    from app.services.assistant.contracts import TaskWaiting
    from app.services.assistant.task_state import TaskUpdate, apply_task_update, load_waiting

    confirmation_payload = None
    if type == "CONFIRMATION":
        confirmation_payload = {
            "kind": "activity_write",
            "preview": {
                "customer_name": "虚构星河科技",
                "activity_kind": "OTHER_FOLLOW_UP",
                "content_json": {},
                "source_content": "沟通原文",
                "score": 82,
                "score_reason": "要素完整",
            },
        }
    waiting = TaskWaiting(
        type=type,
        field=field,
        question_id=f"question-{task.version}",
        prompt="请选择",
        candidates=candidates or [],
        fingerprint="f" * 64,
        confirmation_payload=confirmation_payload,
    )
    apply_task_update(
        db_session,
        task,
        TaskUpdate(
            waiting=waiting,
            action_actor="SYSTEM",
            action_name="offer_option",
        ),
    )
    db_session.commit()
    return load_waiting(task)


def test_submit_rejects_internal_followup_kind(client, db_session):
    task_id = client.post(
        "/api/v1/assistant/tasks",
        json={
            "goal": "记录活动",
            "client_request_id": "create-internal-denial",
        },
    ).json()["public_id"]
    response = client.post(
        f"/api/v1/assistant/tasks/{task_id}/submit",
        json={
            "kind": "continue_proposals",
            "client_request_id": "external-followup-denial",
        },
    )
    assert response.status_code == 422
    assert db_session.query(AssistantTurn).count() == 0


def test_waiting_rejects_stale_identity_wrong_kind_and_unsigned_choices(client, db_session):
    task_id = client.post(
        "/api/v1/assistant/tasks",
        json={
            "goal": "选择客户",
            "client_request_id": "create-strict-wait",
        },
    ).json()["public_id"]
    task = db_session.query(AssistantTask).filter_by(public_id=task_id).one()
    waiting = _issue_waiting(
        db_session,
        task,
        type="OBJECT_SELECTION",
        field="customer",
        candidates=[
            {"id": "cust-1", "name": "同名客户"},
            {"id": "cust-2", "name": "同名客户"},
        ],
    )
    url = f"/api/v1/assistant/tasks/{task_id}/submit"
    signed = {
        "kind": "submit_field",
        "client_request_id": "selection-001",
        "action_id": waiting.action_id,
        "expected_version": waiting.expected_version,
    }
    cases = [
        {**signed, "action_id": "old-card", "choice": "cust-1"},
        {**signed, "expected_version": waiting.expected_version - 1, "choice": "cust-1"},
        {**signed, "choice": "cust-unknown"},
        {**signed, "choice": "同名客户"},
        {**signed, "choice": "cust-1", "text": "cust-2"},
        {**signed, "kind": "text", "choice": "cust-1"},
    ]
    for index, payload in enumerate(cases):
        response = client.post(url, json={**payload, "client_request_id": f"invalid-choice-{index}"})
        assert response.status_code == 409
        assert response.json()["detail"]["task"]["waiting"]["action_id"] == waiting.action_id
    assert db_session.query(AssistantTurn).count() == 0
    assert db_session.query(AssistantRequest).count() == 1


def test_waiting_kind_field_and_confirmation_are_closed_choices(client, db_session):
    task_id = client.post(
        "/api/v1/assistant/tasks",
        json={
            "goal": "验证动作",
            "client_request_id": "create-closed-choice",
        },
    ).json()["public_id"]
    task = db_session.query(AssistantTask).filter_by(public_id=task_id).one()
    url = f"/api/v1/assistant/tasks/{task_id}/submit"
    for type, field, invalid in [
        ("ACTIVITY_KIND", None, {"choice": "VIDEO_CALL"}),
        ("FIELD", "content", {"choice": "EXPLICITLY_NONE", "text": "这条没有"}),
        ("FIELD", "next_action", {"choice": "EXPLICITLY_NONE"}),
        ("CONFIRMATION", "activity_write", {"choice": "maybe"}),
    ]:
        waiting = _issue_waiting(db_session, task, type=type, field=field)
        response = client.post(
            url,
            json={
                "kind": "confirm" if type == "CONFIRMATION" else "submit_field",
                "action_id": waiting.action_id,
                "expected_version": waiting.expected_version,
                "client_request_id": f"invalid-{type}-{field}",
                **invalid,
            },
        )
        assert response.status_code == 409
        assert response.json()["detail"]["task"]["waiting"]["action_id"] == waiting.action_id
    assert db_session.query(AssistantTurn).count() == 0


def test_old_confirmation_card_cannot_authorize_next_card_but_same_key_replays(client, db_session, monkeypatch):
    from types import SimpleNamespace

    from app.services.assistant.contracts import TaskWaiting
    from app.services.assistant.task_state import TaskUpdate, apply_task_update

    task_id = client.post(
        "/api/v1/assistant/tasks",
        json={
            "goal": "逐张确认",
            "client_request_id": "create-sequential-cards",
        },
    ).json()["public_id"]
    task = db_session.query(AssistantTask).filter_by(public_id=task_id).one()
    first = _issue_waiting(db_session, task, type="CONFIRMATION", field="activity_write")

    async def handle_task(db, current, user_input, reporter):
        assert user_input.choice == "confirm"
        apply_task_update(
            db,
            current,
            TaskUpdate(
                waiting=TaskWaiting(
                    type="CONFIRMATION",
                    field="proposal:customer_fact",
                    question_id="next-card",
                    prompt="记录事实？",
                    confirmation_payload={
                        "kind": "proposal",
                        "proposal_kind": "customer_fact",
                        "candidate": {
                            "kind": "customer_fact",
                            "key": "fictional-fact-key",
                            "payload": {"content": "采用虚构系统"},
                            "evidence_quote": "采用虚构系统",
                            "activity_id": 1,
                            "customer_id": 42,
                            "source_revision": 1,
                        },
                    },
                ),
                action_actor="SYSTEM",
                action_name="offer_next_card",
            ),
        )
        return SimpleNamespace(task=current, reply=SimpleNamespace(message="上一张卡已确认"))

    monkeypatch.setattr("app.api.assistant._coordinator", SimpleNamespace(handle_task=handle_task))
    url = f"/api/v1/assistant/tasks/{task_id}/submit"
    request = {
        "kind": "confirm",
        "choice": "confirm",
        "client_request_id": "confirm-first-card",
        "action_id": first.action_id,
        "expected_version": first.expected_version,
    }
    first_result = client.post(url, json=request)
    assert first_result.status_code == 200
    replay = client.post(url, json=request)
    assert _parse_sse(replay.text) == _parse_sse(first_result.text)
    stale = client.post(url, json={**request, "client_request_id": "confirm-second-card"})
    assert stale.status_code == 409
    assert stale.json()["detail"]["task"]["waiting"]["action_id"] != first.action_id
    assert db_session.query(AssistantTurn).count() == 1


def test_change_kind_resets_typed_content_preserves_sources_and_denies_committed_or_active(client, db_session):
    from app.services.assistant.contracts import DraftField, TaskDraft

    task_id = client.post(
        "/api/v1/assistant/tasks",
        json={
            "goal": "变更会议类型",
            "client_request_id": "create-kind-reset",
        },
    ).json()["public_id"]
    task = db_session.query(AssistantTask).filter_by(public_id=task_id).one()
    draft = TaskDraft(
        customer=DraftField(status="ACCEPTED", value="客户甲"),
        content=DraftField(status="ACCEPTED", value="会议结论"),
        source_segments=["原始客户反馈", "补充的行动项"],
        content_json={"meeting_subject": "旧主题"},
        score_reason="旧评分",
        score_detail={"dimensions": [80]},
        quality_score=DraftField(status="ACCEPTED", value="80"),
    )
    task.draft_json = draft.model_dump(mode="json")
    task.authority_json = {"customer_public_id": "cust-1", "frozen_activity_command": {"submission_id": "old"}}
    db_session.commit()
    waiting = _issue_waiting(db_session, task, type="CONFIRMATION", field="activity_write")
    url = f"/api/v1/assistant/tasks/{task_id}/change-kind"
    switched = client.post(url, json={"kind": "FOLLOW_UP"})
    assert switched.status_code == 200
    assert switched.json()["waiting"] is None
    assert switched.json()["draft"]["source_segments"] == draft.source_segments
    assert switched.json()["draft"]["customer"] == draft.customer.model_dump(mode="json")
    assert switched.json()["draft"]["content_json"] == {}
    assert switched.json()["draft"]["score_reason"] is None
    assert switched.json()["draft"]["score_detail"] == {}
    db_session.refresh(task)
    assert task.authority_json["customer_public_id"] == "cust-1"
    assert task.authority_json.get("frozen_activity_command") is None
    stale = client.post(
        f"/api/v1/assistant/tasks/{task_id}/submit",
        json={
            "kind": "confirm",
            "choice": "confirm",
            "action_id": waiting.action_id,
            "expected_version": waiting.expected_version,
            "client_request_id": "old-kind-confirm",
        },
    )
    assert stale.status_code == 409
    from app.services.assistant.turns import accept_submit

    turn, _ = accept_submit(
        db_session,
        task=task,
        key="active-kind-turn",
        input_data={"kind": "text", "text": "新的会议内容"},
        action_id=None,
        expected_version=None,
    )
    db_session.refresh(task)
    assert task.active_turn_id == turn.id
    assert client.post(url, json={"kind": "ONLINE_MEETING"}).status_code == 409
    task.active_turn_id = None
    task.committed_json = [{"kind": "customer_activity", "public_id": "act-1"}]
    db_session.commit()
    denied = client.post(url, json={"kind": "ONLINE_MEETING"})
    assert denied.status_code == 409
    assert denied.json()["detail"]["task"]["activity_kind"] == "FOLLOW_UP"


def test_successful_confirmation_queues_atomic_separate_followup_and_recovery(db_session, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from app.services.assistant import turns
    from app.services.assistant.task_state import TaskUpdate, apply_task_update

    task = AssistantTask(
        team_id=1,
        user_id=2,
        status=AssistantTaskStatus.ACTIVE,
        goal="记录客户活动",
        draft_json=TaskDraft().model_dump(mode="json"),
        authority_json={},
        committed_json=[],
    )
    db_session.add(task)
    db_session.commit()
    waiting = _issue_waiting(db_session, task, type="CONFIRMATION", field="activity_write")
    first, _ = turns.accept_submit(
        db_session,
        task=task,
        key="confirm-with-followup",
        input_data={
            "kind": "confirm",
            "text": None,
            "choice": "confirm",
        },
        action_id=waiting.action_id,
        expected_version=waiting.expected_version,
    )
    seen = []

    async def handle_task(db, current, user_input, reporter):
        seen.append(user_input.kind)
        if user_input.kind == "confirm":
            apply_task_update(
                db,
                current,
                TaskUpdate(
                    clear_waiting=True,
                    append_committed=[{"kind": "customer_activity", "public_id": "act-confirmed", "customer_id": 42}],
                    action_actor="USER",
                    action_name="confirm_write",
                ),
            )
            return SimpleNamespace(task=current, reply=SimpleNamespace(message="活动已记录"), start_followup=True)
        assert user_input.kind == "continue_proposals"
        assert current.committed_json[0]["public_id"] == "act-confirmed"
        apply_task_update(
            db, current, TaskUpdate(status="COMPLETED", action_actor="SYSTEM", action_name="no_proposals")
        )
        return SimpleNamespace(task=current, reply=SimpleNamespace(message="已完成"))

    monkeypatch.setattr("app.api.assistant._coordinator", SimpleNamespace(handle_task=handle_task))
    factory = sessionmaker(bind=db_session.get_bind(), autoflush=False)
    scheduled = []

    def assert_schedule_after_commit(turn_id, *, factory=None):
        with sessionmaker(bind=db_session.get_bind())() as check:
            current = check.get(AssistantTask, task.id)
            next_turn = check.get(AssistantTurn, turn_id)
            assert current.committed_json[0]["public_id"] == "act-confirmed"
            assert current.active_turn_id == next_turn.id
            assert next_turn.status == "PENDING"
            assert check.query(AssistantTurnEvent).filter_by(turn_id=next_turn.id, event="accepted").count() == 1
            assert check.get(AssistantTurn, first.id).status == "SUCCEEDED"
        scheduled.append(turn_id)

    monkeypatch.setattr(turns, "schedule_turn", assert_schedule_after_commit)
    asyncio.run(turns.execute_turn(first.id, factory=factory))
    assert seen == ["confirm"]
    assert len(scheduled) == 1
    db_session.expire_all()
    current = db_session.get(AssistantTask, task.id)
    assert current.waiting_type is None
    assert current.active_turn_id == scheduled[0]
    old_events = db_session.query(AssistantTurnEvent).filter_by(turn_id=first.id).order_by(AssistantTurnEvent.seq).all()
    assert old_events[-1].data_json["next_turn_id"] == db_session.get(AssistantTurn, scheduled[0]).public_id
    assert old_events[-1].data_json["task"]["committed"][0]["public_id"] == "act-confirmed"
    assert old_events[-1].data_json["task"]["waiting"] is None
    assert (
        old_events[-1].data_json["task"]["processing_turn_id"] == db_session.get(AssistantTurn, scheduled[0]).public_id
    )
    assert old_events[-1].data_json["task"]["processing_turn_status"] == "PENDING"
    monkeypatch.setattr(turns, "SessionLocal", factory)
    assert asyncio.run(turns.recover_turns()) == 1
    assert scheduled == [current.active_turn_id, current.active_turn_id]
    asyncio.run(turns.execute_turn(scheduled[0], factory=factory))
    db_session.expire_all()
    assert seen == ["confirm", "continue_proposals"]
    assert db_session.get(AssistantTask, task.id).status == "COMPLETED"
    assert db_session.get(AssistantTurn, scheduled[0]).status == "SUCCEEDED"


def test_concurrent_create_same_key_returns_winner_instead_of_integrity_error(db_session, monkeypatch):
    """A1: create colliding on the request unique key must replay the winner."""

    from app.services.assistant import turns

    won = turns.accept_create(db_session, team_id=1, user_id=2, key="race-create-001", goal="并发创建同一任务")
    db_session.expire_all()

    real_request = turns._request
    misses = {"count": 0}

    def stale_read(db, *, team_id, user_id, key):
        misses["count"] += 1
        if misses["count"] == 1:
            return None
        return real_request(db, team_id=team_id, user_id=user_id, key=key)

    monkeypatch.setattr(turns, "_request", stale_read)
    replayed = turns.accept_create(db_session, team_id=1, user_id=2, key="race-create-001", goal="并发创建同一任务")
    assert replayed.id == won.id
    assert db_session.query(AssistantTask).count() == 1

    misses["count"] = 0
    with pytest.raises(turns.AssistantRequestConflict):
        turns.accept_create(db_session, team_id=1, user_id=2, key="race-create-001", goal="完全不同的目标")


def test_concurrent_submit_same_key_returns_winner_turn_instead_of_integrity_error(db_session, monkeypatch):
    """A1: submit colliding on the request unique key must replay the winner turn."""

    from app.services.assistant import turns

    task = AssistantTask(
        team_id=1,
        user_id=2,
        status=AssistantTaskStatus.ACTIVE,
        goal="记录活动",
        draft_json=TaskDraft().model_dump(mode="json"),
        authority_json={},
        committed_json=[],
    )
    db_session.add(task)
    db_session.commit()
    payload = {"kind": "text", "text": "并发提交", "choice": None}
    won_turn, _ = turns.accept_submit(
        db_session, task=task, key="race-submit-001", input_data=payload, action_id=None, expected_version=None
    )
    won_turn.status = "SUCCEEDED"
    task.active_turn_id = None
    db_session.commit()
    db_session.expire_all()

    real_request = turns._request
    misses = {"count": 0}

    def stale_read(db, *, team_id, user_id, key):
        misses["count"] += 1
        if misses["count"] == 1:
            return None
        return real_request(db, team_id=team_id, user_id=user_id, key=key)

    monkeypatch.setattr(turns, "_request", stale_read)
    replayed, created = turns.accept_submit(
        db_session, task=task, key="race-submit-001", input_data=payload, action_id=None, expected_version=None
    )
    assert created is False
    assert replayed.id == won_turn.id
    assert db_session.query(AssistantTurn).count() == 1

    misses["count"] = 0
    with pytest.raises(turns.AssistantRequestConflict):
        turns.accept_submit(
            db_session,
            task=task,
            key="race-submit-001",
            input_data={"kind": "text", "text": "不同载荷", "choice": None},
            action_id=None,
            expected_version=None,
        )


def test_expired_worker_error_cannot_fail_a_reclaimable_turn(db_session, monkeypatch):
    """A2: an expired lease must keep the turn recoverable, not terminally FAILED."""

    import asyncio
    from datetime import timedelta
    from types import SimpleNamespace

    from sqlalchemy import update

    from app.services.assistant import turns
    from app.utils.time import business_now

    task = AssistantTask(
        team_id=1,
        user_id=2,
        status=AssistantTaskStatus.ACTIVE,
        goal="记录活动",
        draft_json=TaskDraft().model_dump(mode="json"),
        authority_json={},
        committed_json=[],
    )
    db_session.add(task)
    db_session.commit()
    turn, _ = turns.accept_submit(
        db_session,
        task=task,
        key="expired-fence-001",
        input_data={"kind": "text", "text": "继续", "choice": None},
        action_id=None,
        expected_version=None,
    )

    async def handle_task(db, current, user_input, reporter):
        with sessionmaker(bind=db_session.get_bind())() as rival:
            rival.execute(
                update(AssistantTurn)
                .where(AssistantTurn.id == turn.id)
                .values(
                    lease_expires_at=business_now() - timedelta(seconds=10),
                )
            )
            rival.commit()
        raise RuntimeError("worker exploded after lease expiry")

    monkeypatch.setattr("app.api.assistant._coordinator", SimpleNamespace(handle_task=handle_task))
    asyncio.run(turns.execute_turn(turn.id, factory=sessionmaker(bind=db_session.get_bind())))

    db_session.expire_all()
    final = db_session.get(AssistantTurn, turn.id)
    assert final.status == "RUNNING"
    assert final.lease_expires_at < business_now()
    assert db_session.get(AssistantTask, task.id).active_turn_id == turn.id
    events = db_session.query(AssistantTurnEvent).filter_by(turn_id=turn.id).order_by(AssistantTurnEvent.seq).all()
    assert [event.event for event in events] == ["accepted"]


def test_task_waiting_validates_command_discriminators_without_changing_proposal_identity():
    from pydantic import ValidationError

    from app.services.assistant.contracts import TaskWaiting

    candidate = {
        "kind": "customer_fact",
        "key": "fictional-fact-key",
        "payload": {"content": "采用虚构系统"},
        "evidence_quote": "采用虚构系统",
        "activity_id": 1,
        "customer_id": 42,
        "source_revision": 1,
        "prior_fact_version": None,
        "action_id": "fictional-action",
    }
    payload = {"kind": "proposal", "proposal_kind": "customer_fact", "candidate": candidate}
    values = {
        "type": "CONFIRMATION",
        "field": "proposal:customer_fact",
        "question_id": "q-fact",
        "prompt": "写入事实？",
        "confirmation_payload": payload,
    }
    waiting = TaskWaiting.model_validate(values)
    assert waiting.model_dump(mode="json")["confirmation_payload"] == payload
    for changed in [
        {**values, "field": "activity_write"},
        {**values, "confirmation_payload": {**payload, "proposal_kind": "opportunity_create"}},
        {**values, "confirmation_payload": {**payload, "kind": "arbitrary_command"}},
        {**values, "confirmation_payload": {**payload, "candidate": {**candidate, "untrusted_authority": True}}},
    ]:
        with pytest.raises(ValidationError):
            TaskWaiting.model_validate(changed)


def test_refresh_projects_and_reads_same_internal_turn_without_another_submission(client, db_session):
    from app.services.assistant.turns import accept_submit

    public_id = client.post(
        "/api/v1/assistant/tasks",
        json={
            "goal": "虚构星河科技后续提议",
            "client_request_id": "create-internal-recovery",
        },
    ).json()["public_id"]
    task = db_session.query(AssistantTask).filter_by(public_id=public_id).one()
    turn, _ = accept_submit(
        db_session,
        task=task,
        key="fictional-internal-turn",
        input_data={
            "kind": "text",
            "text": "虚构沟通原文",
            "choice": None,
        },
        action_id=None,
        expected_version=None,
    )
    turn.input_json = {"kind": "continue_proposals", "text": None, "choice": None}
    db_session.commit()
    projected = client.get(f"/api/v1/assistant/tasks/{public_id}").json()
    assert projected["processing_turn_id"] == turn.public_id
    assert projected["processing_turn_status"] == "PENDING"
    resumed = client.get(f"/api/v1/assistant/tasks/{public_id}/turns/{turn.public_id}").json()
    assert resumed["turn_id"] == turn.public_id
    assert resumed["task"]["processing_turn_id"] == turn.public_id
    assert db_session.query(AssistantTurn).count() == 1
    task.user_id = 99
    db_session.commit()
    assert client.get(f"/api/v1/assistant/tasks/{public_id}/turns/{turn.public_id}").status_code == 404


def test_task_list_isolates_unreadable_row_without_exposing_stored_authority(client, db_session):
    valid_id = client.post(
        "/api/v1/assistant/tasks",
        json={
            "goal": "虚构星河跟进",
            "client_request_id": "create-list-readable",
        },
    ).json()["public_id"]
    broken = AssistantTask(
        team_id=1,
        user_id=2,
        status="ACTIVE",
        goal="虚构云杉跟进",
        draft_json={"private_unvalidated_value": "must-not-escape"},
        waiting_json={"private_waiting_value": "must-not-escape"},
        authority_json={"customer_id": 42, "private_authority": "must-not-escape"},
        committed_json=[],
    )
    db_session.add(broken)
    db_session.commit()
    response = client.get("/api/v1/assistant/tasks")
    assert response.status_code == 200
    rows = {row["public_id"]: row for row in response.json()}
    assert set(rows) == {valid_id, broken.public_id}
    assert rows[valid_id]["draft"]["customer"]["status"] == "MISSING"
    assert rows[broken.public_id]["draft"] is None
    assert set(rows[broken.public_id]) == set(rows[valid_id])
    assert "must-not-escape" not in response.text
    assert not {"team_id", "user_id", "authority", "authority_json"} & set(rows[broken.public_id])


def test_task_view_keeps_historical_receipt_omissions_and_rejects_partial_processing_pointer():
    from pydantic import ValidationError

    from app.api.assistant import AssistantTaskView

    values = {
        "public_id": "ast_fictional",
        "status": "ACTIVE",
        "goal": "虚构客户跟进",
        "activity_kind": "FOLLOW_UP",
        "draft": TaskDraft(),
        "waiting": None,
        "committed": [{"kind": "customer_activity", "public_id": "act_fictional"}],
        "budget_steps": 0,
        "budget_max_steps": 50,
        "version": 1,
    }
    assert AssistantTaskView.model_validate(values).model_dump(mode="json")["committed"] == values["committed"]
    with pytest.raises(ValidationError):
        AssistantTaskView.model_validate({**values, "processing_turn_id": "atn_fictional"})
    with pytest.raises(ValidationError):
        AssistantTaskView.model_validate({**values, "processing_turn_status": "RUNNING"})
    with pytest.raises(ValidationError):
        AssistantTaskView.model_validate(
            {**values, "processing_turn_id": "atn_fictional", "processing_turn_status": "UNKNOWN"}
        )


def test_activity_preview_accepts_only_canonical_crm_kinds():
    from pydantic import ValidationError

    from app.services.assistant.contracts import ActivityPreview
    from app.services.customer_activity_kinds import ACTIVITY_KIND_META

    preview = {
        "customer_name": "虚构星河科技",
        "content_json": {},
        "source_content": "沟通原文",
        "score": 82,
        "score_reason": "要素完整",
    }
    for kind in ACTIVITY_KIND_META:
        assert ActivityPreview.model_validate({**preview, "activity_kind": kind}).activity_kind == kind
    for unsupported in ("FOLLOW_UP", "PHONE_CALL", "VIDEO_CALL", "arbitrary_kind"):
        with pytest.raises(ValidationError):
            ActivityPreview.model_validate({**preview, "activity_kind": unsupported})

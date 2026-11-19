"""Open follow-up tasks are listed and settled one at a time after a follow-up write."""
# ruff: noqa: RUF001

from copy import deepcopy
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.assistant import AssistantAction, AssistantTask, AssistantTaskStatus
from app.models.assistant_turn import AssistantTurn
from app.models.customer_activity import CustomerActivity
from app.models.sales_commitment import FollowUpTask, FollowUpTaskStatus
from app.services.assistant.open_follow_up_disposition import (
    advance_open_follow_up,
    public_disposition,
    relate_title,
    settle_open_follow_up,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX") or statement.startswith("CREATE UNIQUE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(
        engine,
        tables=[
            AssistantTask.__table__,
            AssistantAction.__table__,
            AssistantTurn.__table__,
            CustomerActivity.__table__,
            FollowUpTask.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _activity(
    db,
    *,
    kind="PHONE_FOLLOW_UP",
    content="已和林女士核对采购安排，客户预计下周反馈。",
    team_id=1,
    activity_id=1,
):
    activity = CustomerActivity(
        id=activity_id,
        team_id=team_id,
        customer_id=7,
        activity_kind=kind,
        activity_revision=3,
        source_content=content,
        content_json='{"summary":"整理稿里才有安全测评报告"}',
        creator_id="2",
        owner_id="2",
        submission_source="AGENT",
    )
    db.add(activity)
    return activity


def _task(db, activity):
    task = AssistantTask(
        team_id=activity.team_id,
        user_id=2,
        status=AssistantTaskStatus.ACTIVE,
        goal="记录跟进",
        draft_json={"content": {"status": "ACCEPTED", "value": "已整理"}},
        authority_json={"activity_public_id": str(activity.id)},
        committed_json=[{"kind": "customer_activity", "public_id": str(activity.id), "customer_id": 7}],
        version=0,
    )
    db.add(task)
    db.commit()
    return task


def _follow_up(
    db,
    *,
    public_id,
    title,
    owner="2",
    status=FollowUpTaskStatus.OPEN,
    team_id=1,
    customer_id=7,
    source_activity_id=None,
    due=None,
):
    row = FollowUpTask(
        public_id=public_id,
        team_id=team_id,
        customer_id=customer_id,
        owner_id=owner,
        creator_id=owner,
        title=title,
        status=status,
        due_at=due or datetime(2026, 10, 28, 9, 0, 0),
        due_at_granularity="DATE",
        due_at_timezone="Asia/Shanghai",
        source_type="CUSTOMER_ACTIVITY",
        source_key=f"test:{public_id}",
        source_activity_id=source_activity_id,
        task_hash=public_id,
        confidence=1,
    )
    db.add(row)
    db.commit()
    return row


def test_relation_uses_source_text_not_a_generic_fragment():
    assert relate_title("联系客户确认采购安排", "已和林女士核对采购安排，并确认采购安排")[0] == "确认采购安排"
    assert relate_title("跟进客户", "请继续跟进客户") is None
    assert relate_title("补充安全测评报告", "已和林女士核对采购安排") is None


@pytest.mark.asyncio
async def test_follow_up_write_lists_operable_open_tasks_without_a_model(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.assistant.open_follow_up_disposition._permission_codes",
        lambda db, task: set(),
    )
    activity = _activity(db_session)
    _follow_up(db_session, public_id="fut_related", title="联系客户确认采购安排", due=datetime(2026, 10, 28, 9, 0, 0))
    _follow_up(db_session, public_id="fut_plain", title="补充安全测评报告", due=datetime(2026, 11, 2, 9, 0, 0))
    _follow_up(db_session, public_id="fut_other_team", title="联系客户确认采购安排", team_id=9)
    _follow_up(db_session, public_id="fut_other_owner", title="别人的采购安排", owner="9")
    _follow_up(db_session, public_id="fut_closed", title="联系客户确认采购安排", status=FollowUpTaskStatus.COMPLETED)
    _follow_up(db_session, public_id="fut_created_here", title="本次新建任务", source_activity_id=1)
    task = _task(db_session, activity)

    outcome = await advance_open_follow_up(db_session, task)

    assert outcome is not None and outcome.start_followup is False
    items = outcome.task.authority_json["open_follow_up_batch"]["items"]
    assert [item["task_public_id"] for item in items] == ["fut_related", "fut_plain"]
    assert items[0]["related"] is True
    assert items[0]["evidence_quote"] in activity.source_content
    assert items[1]["related"] is False
    assert outcome.task.waiting_type == "FOLLOW_UP_DISPOSITION"
    assert outcome.task.waiting_json["payload"]["candidates"][0]["id"] == "i1:complete"
    from app.schemas.assistant_conversation import ConversationMessage
    from app.services.assistant.presentation import task_view
    from app.services.assistant.ui_projection import project_assistant_message

    view = task_view(outcome.task, db_session)
    message = ConversationMessage(
        id="m1",
        role="assistant",
        text=outcome.message,
        at="2026-10-29T00:00:00",
        task=view,
        outcome="follow_up_disposition",
    )
    envelope = project_assistant_message(message, active_waiting=True, active_boundary=False)
    interaction = next(block for block in envelope.blocks if block.type == "interaction")
    assert interaction.presentation == "OPEN_FOLLOW_UP_DISPOSITION"
    assert interaction.disposition_items[0].related is True
    assert interaction.disposition_items[1].related is False
    assert [option.label for option in interaction.options] == ["已完成", "先放着", "不管了"]


@pytest.mark.asyncio
async def test_meeting_write_does_not_open_the_historical_card(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.assistant.open_follow_up_disposition._permission_codes",
        lambda db, task: set(),
    )
    activity = _activity(db_session, kind="ONLINE_MEETING")
    _follow_up(db_session, public_id="fut_related", title="联系客户确认采购安排")
    task = _task(db_session, activity)

    assert await advance_open_follow_up(db_session, task) is None
    assert "open_follow_up_batch" not in (task.authority_json or {})


@pytest.mark.asyncio
async def test_choices_are_independent_and_only_complete_writes(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.assistant.open_follow_up_disposition._permission_codes",
        lambda db, task: set(),
    )
    calls = []

    def fake_execute(db, *, team_id, action, plan, actor_id, expected_owner_id, commit):
        calls.append(action.task_public_id)
        row = db.query(FollowUpTask).filter_by(team_id=team_id, public_id=action.task_public_id).one()
        row.status = FollowUpTaskStatus.COMPLETED
        return type("Result", (), {"status": "EXECUTED", "skip_reason": None})()

    monkeypatch.setattr(
        "app.services.follow_up_task_transition_execution_service.follow_up_task_transition_execution_service.execute_action",
        fake_execute,
    )
    activity = _activity(db_session)
    _follow_up(db_session, public_id="fut_related", title="联系客户确认采购安排", due=datetime(2026, 10, 28, 9, 0, 0))
    _follow_up(db_session, public_id="fut_plain", title="补充安全测评报告", due=datetime(2026, 11, 2, 9, 0, 0))
    task = _task(db_session, activity)
    offered = await advance_open_follow_up(db_session, task)

    completed = await settle_open_follow_up(db_session, offered.task, "i1:complete")
    held = await settle_open_follow_up(db_session, completed.task, "i2:hold")

    assert calls == ["fut_related"]
    related = db_session.query(FollowUpTask).filter_by(public_id="fut_related").one()
    assert related.status == FollowUpTaskStatus.COMPLETED
    plain = db_session.query(FollowUpTask).filter_by(public_id="fut_plain").one()
    assert plain.status == FollowUpTaskStatus.OPEN
    assert held.start_followup is True
    assert held.task.waiting_type is None
    assert held.task.authority_json["open_follow_up_batch"]["status"] == "DONE"
    assert held.task.committed_json[-1]["proposal_key"].endswith(":i1:complete")
    again = await advance_open_follow_up(db_session, held.task)
    assert again is None


@pytest.mark.asyncio
async def test_skip_does_not_record_unrelated_and_failure_stays_on_one_item(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.assistant.open_follow_up_disposition._permission_codes",
        lambda db, task: set(),
    )
    activity = _activity(db_session)
    first = _follow_up(db_session, public_id="fut_related", title="联系客户确认采购安排")
    _follow_up(db_session, public_id="fut_plain", title="补充安全测评报告", due=datetime(2026, 11, 2, 9, 0, 0))
    task = _task(db_session, activity)
    offered = await advance_open_follow_up(db_session, task)
    first.status = FollowUpTaskStatus.CANCELLED
    db_session.commit()

    failed = await settle_open_follow_up(db_session, offered.task, "i1:complete")
    skipped = await settle_open_follow_up(db_session, failed.task, "i2:skip")

    first_item = failed.task.authority_json["open_follow_up_batch"]["items"][0]
    assert first_item["disposition"] == "failed"
    assert first_item["failure_code"] == "ALREADY_HANDLED"
    assert first_item["related"] is True
    second = skipped.task.authority_json["open_follow_up_batch"]["items"][1]
    assert second["disposition"] == "skip"
    assert "unrelated" not in second
    assert "failure_code" not in second
    assert db_session.query(FollowUpTask).filter_by(public_id="fut_plain").one().status == FollowUpTaskStatus.OPEN
    assert db_session.query(CustomerActivity).one().id == activity.id


@pytest.mark.asyncio
async def test_stale_evidence_and_overflow_do_not_offer_a_partial_list(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.assistant.open_follow_up_disposition._permission_codes",
        lambda db, task: {"follow_up_task:operate:all"},
    )
    activity = _activity(db_session)
    _follow_up(db_session, public_id="fut_related", title="联系客户确认采购安排", owner="8")
    task = _task(db_session, activity)
    offered = await advance_open_follow_up(db_session, task)
    assert offered.task.authority_json["open_follow_up_batch"]["items"][0]["related"] is True
    activity.source_content = "这次只谈了别的话题"
    db_session.commit()

    failed = await settle_open_follow_up(db_session, offered.task, "i1:complete")
    stale = failed.task.authority_json["open_follow_up_batch"]["items"][0]
    assert stale["failure_code"] == "RELATION_STALE"
    assert stale["related"] is False
    assert db_session.query(FollowUpTask).one().status == FollowUpTaskStatus.OPEN

    for index in range(101):
        _follow_up(
            db_session,
            public_id=f"fut_many_{index}",
            title=f"独立任务{index:03d}",
            due=datetime(2026, 12, 1, 9, 0, index % 60),
        )
    fresh = _task(db_session, _activity(db_session, activity_id=2, content="另一条跟进"))
    # The helper commits the first activity; attach the second activity id on this task.
    fresh.authority_json = {"activity_public_id": "2"}
    fresh.committed_json = [{"kind": "customer_activity", "public_id": "2", "customer_id": 7}]
    db_session.commit()
    overflow = await advance_open_follow_up(db_session, fresh)
    assert overflow is not None and overflow.start_followup is True
    assert overflow.task.authority_json["open_follow_up_batch"]["status"] == "OVERFLOW"
    assert overflow.task.authority_json["open_follow_up_batch"]["items"] == []


@pytest.mark.asyncio
async def test_batch_identity_survives_restore_settlement_and_reload(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.assistant.open_follow_up_disposition._permission_codes",
        lambda db, task: set(),
    )
    activity = _activity(db_session)
    _follow_up(db_session, public_id="fut_first", title="联系客户确认采购安排")
    _follow_up(db_session, public_id="fut_second", title="补充安全测评报告")
    task = _task(db_session, activity)
    task_id = task.id

    offered = await advance_open_follow_up(db_session, task)
    batch_id = offered.task.authority_json["open_follow_up_batch"]["disposition_batch_id"]
    assert batch_id.startswith("afb_")
    assert len(batch_id) == 36
    restored = await advance_open_follow_up(db_session, offered.task)
    assert restored.task.authority_json["open_follow_up_batch"]["disposition_batch_id"] == batch_id
    held = await settle_open_follow_up(db_session, restored.task, "i1:hold")
    assert public_disposition(held.task)["batch_id"] == batch_id
    await settle_open_follow_up(db_session, held.task, "i2:skip")
    db_session.expire_all()
    reloaded = db_session.get(AssistantTask, task_id)
    card = public_disposition(reloaded)
    assert reloaded.authority_json["open_follow_up_batch"]["disposition_batch_id"] == batch_id
    assert card["batch_id"] == batch_id
    assert card["activity_public_id"] == str(activity.id)
    assert card["status"] == "DONE"
    assert [(item["item_id"], item["task_public_id"], item["state"]) for item in card["items"]] == [
        ("i1", "fut_first", "hold"),
        ("i2", "fut_second", "skip"),
    ]
    assert all("owner_id" not in item and "idempotency_key" not in item for item in card["items"])
    assert all(row.status == FollowUpTaskStatus.OPEN for row in db_session.query(FollowUpTask).all())

    another_round = _task(db_session, activity)
    reopened = await advance_open_follow_up(db_session, another_round)
    assert public_disposition(reopened.task)["batch_id"] != batch_id


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["DONE", "OVERFLOW", "QUERY_FAILED"])
async def test_terminal_batch_identity_is_persisted_once(db_session, monkeypatch, status):
    monkeypatch.setattr(
        "app.services.assistant.open_follow_up_disposition._permission_codes",
        lambda db, task: set(),
    )
    if status == "OVERFLOW":
        monkeypatch.setattr(
            "app.services.assistant.open_follow_up_disposition._build_batch", lambda db, task, activity: None,
        )
    elif status == "QUERY_FAILED":
        def fail_query(db, task, activity):
            raise PermissionError("cannot query")

        monkeypatch.setattr("app.services.assistant.open_follow_up_disposition._build_batch", fail_query)
    task = _task(db_session, _activity(db_session))
    task_id = task.id
    await advance_open_follow_up(db_session, task)
    db_session.expire_all()
    reloaded = db_session.get(AssistantTask, task_id)
    card = public_disposition(reloaded)
    assert card["status"] == status
    assert card["items"] == []
    batch_id = reloaded.authority_json["open_follow_up_batch"]["disposition_batch_id"]
    assert batch_id.startswith("afb_") and len(batch_id) == 36
    assert card["batch_id"] == batch_id
    assert card["activity_public_id"] == "1"
    version = reloaded.version
    assert await advance_open_follow_up(db_session, reloaded) is None
    assert reloaded.version == version
    assert public_disposition(reloaded)["batch_id"] == batch_id


@pytest.fixture
def legacy_disposition_task():
    return AssistantTask(
        public_id="ast_legacy",
        authority_json={
            "activity_public_id": "1",
            "open_follow_up_batch": {
                "status": "ACTIVE",
                "activity_id": 1,
                "activity_revision": 3,
                "source_sha256": "a" * 64,
                "items": [{"item_id": "i1", "task_public_id": "fut_legacy", "owner_id": "private"}],
            },
        },
        committed_json=[{"kind": "customer_activity", "public_id": "1"}],
    )


def test_legacy_batch_identity_is_read_only_stable_and_round_specific(legacy_disposition_task):
    task = legacy_disposition_task
    before = deepcopy(task.authority_json)
    original = public_disposition(task)
    assert original["batch_id"] is not None
    assert public_disposition(task)["batch_id"] == original["batch_id"]
    assert task.authority_json == before
    item = task.authority_json["open_follow_up_batch"]["items"][0]
    item.update({"title": "changed display text", "disposition": "hold", "result_title": "先放着"})
    task.authority_json["open_follow_up_batch"]["status"] = "DONE"
    assert public_disposition(task)["batch_id"] == original["batch_id"]
    task.authority_json["open_follow_up_batch"]["activity_revision"] = 4
    assert public_disposition(task)["batch_id"] != original["batch_id"]
    task.authority_json = before
    task.public_id = "ast_another"
    assert public_disposition(task)["batch_id"] != original["batch_id"]


@pytest.mark.parametrize("unsafe", [
    "no_receipt", "mismatched_receipt", "mismatched_authority", "no_revision", "invalid_hash",
    "no_task_identity", "duplicate_item_identity", "empty_batch",
])
def test_legacy_batch_identity_is_null_without_proven_round(legacy_disposition_task, unsafe):
    task = legacy_disposition_task
    batch = task.authority_json["open_follow_up_batch"]
    if unsafe == "no_receipt":
        task.committed_json = []
    elif unsafe == "mismatched_receipt":
        task.committed_json = [{"kind": "customer_activity", "public_id": "2"}]
    elif unsafe == "mismatched_authority":
        task.authority_json["activity_public_id"] = "2"
    elif unsafe == "no_revision":
        batch.pop("activity_revision")
    elif unsafe == "invalid_hash":
        batch["source_sha256"] = "invalid"
    elif unsafe == "no_task_identity":
        batch["items"][0].pop("task_public_id")
    elif unsafe == "duplicate_item_identity":
        batch["items"].append(deepcopy(batch["items"][0]))
    else:
        batch["items"] = []
    before = deepcopy(task.authority_json)
    card = public_disposition(task)
    assert card["batch_id"] is None
    assert task.authority_json == before
    if unsafe in {"no_receipt", "mismatched_receipt", "mismatched_authority"}:
        assert card["activity_public_id"] is None
    if unsafe == "no_task_identity":
        assert card["items"][0]["task_public_id"] is None

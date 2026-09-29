"""Transition-function contracts for the assistant task state."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.assistant import (
    AssistantAction,
    AssistantTask,
    AssistantTaskStatus,
    AssistantWaitingType,
)
from app.services.assistant.contracts import DraftField, TaskDraft, TaskWaiting
from app.services.assistant.task_state import (
    InvalidTaskTransitionError,
    TaskStateConflictError,
    TaskUpdate,
    apply_task_update,
    load_draft,
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
        tables=[AssistantTask.__table__, AssistantAction.__table__],
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _make_task(session, **overrides):
    values = {
        "team_id": 1,
        "user_id": 2,
        "status": AssistantTaskStatus.ACTIVE,
        "goal": "记录一条客户跟进",
        "draft_json": TaskDraft().model_dump(mode="json"),
        "authority_json": {},
        "committed_json": [],
        "version": 0,
    }
    values.update(overrides)
    task = AssistantTask(**values)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def test_apply_update_bumps_version_and_appends_action(db_session):
    task = _make_task(db_session)

    result = apply_task_update(
        db_session,
        task,
        TaskUpdate(
            draft=TaskDraft(customer=DraftField(status="ACCEPTED", value="睿狐科技")),
            action_actor="SYSTEM",
            action_name="bind_customer",
            action_result={"customer": "睿狐科技"},
        ),
    )

    assert result.task.version == 1
    assert result.action.task_id == task.id
    assert result.action.action == "bind_customer"
    assert load_draft(result.task).customer.value == "睿狐科技"


def test_stale_version_raises_conflict(db_session):
    task = _make_task(db_session)

    fresh = apply_task_update(
        db_session,
        task,
        TaskUpdate(action_actor="SYSTEM", action_name="first"),
    )
    assert fresh.task.version == 1

    # Build a stale snapshot: version 0 while the row is at version 1.
    stale = AssistantTask(
        id=task.id,
        team_id=task.team_id,
        user_id=task.user_id,
        status=task.status,
        goal=task.goal,
        version=0,
    )
    with pytest.raises(TaskStateConflictError):
        apply_task_update(
            db_session,
            stale,
            TaskUpdate(action_actor="SYSTEM", action_name="second"),
        )



def test_stale_session_cannot_overwrite_committed_transition(db_session):
    task = _make_task(db_session)
    Session = sessionmaker(bind=db_session.get_bind())
    stale_session = Session()
    fresh_session = Session()
    try:
        stale = stale_session.get(AssistantTask, task.id)
        fresh = fresh_session.get(AssistantTask, task.id)
        assert stale is not None and fresh is not None
        apply_task_update(
            fresh_session,
            fresh,
            TaskUpdate(action_actor="USER", action_name="first"),
        )
        fresh_session.commit()

        with pytest.raises(TaskStateConflictError):
            apply_task_update(
                stale_session,
                stale,
                TaskUpdate(action_actor="USER", action_name="late_second"),
            )
        stale_session.rollback()
        db_session.expire_all()
        assert db_session.get(AssistantTask, task.id).version == 1
        assert db_session.query(AssistantAction).filter_by(task_id=task.id).count() == 1
    finally:
        stale_session.close()
        fresh_session.close()


def test_change_kind_rejects_turn_claim_between_read_and_update(tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.api.assistant import ChangeKindRequest, change_kind
    from app.models.assistant_turn import AssistantRequest, AssistantTurn, AssistantTurnEvent
    from app.services.assistant import task_state, turns

    engine = create_engine(f"sqlite:///{tmp_path / 'change-kind-race.db'}")
    Base.metadata.create_all(engine, tables=[
        AssistantTask.__table__, AssistantAction.__table__, AssistantRequest.__table__,
        AssistantTurn.__table__, AssistantTurnEvent.__table__,
    ])
    Session = sessionmaker(bind=engine)
    original_draft = TaskDraft(content=DraftField(status="ACCEPTED", value="已拟定的跟进内容"))
    original_authority = {"frozen_activity_command": {"submission_id": "existing-command"}}
    with Session() as setup:
        task = _make_task(setup, activity_kind="FOLLOW_UP",
                          draft_json=original_draft.model_dump(mode="json"), authority_json=original_authority)
        task_id, public_id = task.id, task.public_id

    original_apply = task_state.apply_task_update
    claimed_turn_id = None

    def claim_before_update(db, task, update):
        nonlocal claimed_turn_id
        with Session() as claimant:
            fresh = claimant.get(AssistantTask, task_id)
            turn, created = turns.accept_submit(
                claimant, task=fresh, key="submit-before-kind-switch",
                input_data={"kind": "text", "text": "新的一轮输入"}, action_id=None, expected_version=None,
            )
            assert created
            claimed_turn_id = turn.id
        return original_apply(db, task, update)

    monkeypatch.setattr(task_state, "apply_task_update", claim_before_update)
    with Session() as stale:
        with pytest.raises(HTTPException) as conflict:
            asyncio.run(change_kind(
                public_id=public_id, request=ChangeKindRequest(kind="ONLINE_MEETING"),
                team_id=1, current_user=SimpleNamespace(id=2), db=stale,
            ))
        assert conflict.value.status_code == 409
        assert conflict.value.detail["code"] == "STATE_CONFLICT"

    with Session() as check:
        current = check.get(AssistantTask, task_id)
        assert current.active_turn_id == claimed_turn_id
        assert current.version == 0  # Turn ownership alone does not advance task.version.
        assert current.activity_kind == "FOLLOW_UP"
        assert current.draft_json == original_draft.model_dump(mode="json")
        assert current.authority_json == original_authority
        assert check.query(AssistantAction).filter_by(task_id=task_id).count() == 0
        assert check.get(AssistantTurn, claimed_turn_id).status == "PENDING"

        # A worker holding the claimed turn can still record an ordinary transition.
        result = original_apply(check, current, TaskUpdate(action_actor="SYSTEM", action_name="turn_progress"))
        check.commit()
        assert result.task.version == 1
        assert result.task.active_turn_id == claimed_turn_id


def test_terminal_task_rejects_any_transition(db_session):
    task = _make_task(db_session, status=AssistantTaskStatus.COMPLETED)

    with pytest.raises(InvalidTaskTransitionError):
        apply_task_update(
            db_session,
            task,
            TaskUpdate(action_actor="USER", action_name="late_update"),
        )


def test_transition_without_action_audit_is_rejected(db_session):
    task = _make_task(db_session)

    with pytest.raises(InvalidTaskTransitionError):
        apply_task_update(db_session, task, TaskUpdate())


def test_set_and_clear_waiting_in_one_transition_is_rejected(db_session):
    task = _make_task(db_session)

    with pytest.raises(InvalidTaskTransitionError):
        apply_task_update(
            db_session,
            task,
            TaskUpdate(
                waiting=TaskWaiting(
                    type=AssistantWaitingType.FIELD,
                    field="next_action",
                    question_id="q1",
                    prompt="下一步是谁在什么时间做什么？",  # noqa: RUF001
                ),
                clear_waiting=True,
                action_actor="SYSTEM",
                action_name="ask_field",
            ),
        )


def test_clear_waiting_resets_pause_point(db_session):
    task = _make_task(
        db_session,
        waiting_type=AssistantWaitingType.FIELD,
        waiting_field="next_action",
    )

    result = apply_task_update(
        db_session,
        task,
        TaskUpdate(
            clear_waiting=True,
            draft=TaskDraft(next_action=DraftField(status="ACCEPTED", value="下周三确认批复")),
            action_actor="USER",
            action_name="submit_field",
            action_input={"field": "next_action"},
        ),
    )

    assert result.task.waiting_type is None
    assert result.task.waiting_field is None
    assert load_draft(result.task).next_action.value == "下周三确认批复"


def test_committed_list_only_grows(db_session):
    task = _make_task(db_session, committed_json=[{"kind": "activity", "id": "act_1"}])

    result = apply_task_update(
        db_session,
        task,
        TaskUpdate(
            append_committed=[{"kind": "task_transition", "id": "fut_1"}],
            action_actor="USER",
            action_name="confirm_follow_up_task",
        ),
    )

    assert [item["id"] for item in result.task.committed_json] == ["act_1", "fut_1"]



def test_committed_activity_cannot_be_retyped_or_redrafted(db_session):
    task = _make_task(db_session, activity_kind="FOLLOW_UP", committed_json=[
        {"kind": "customer_activity", "public_id": "123"},
    ])
    with pytest.raises(InvalidTaskTransitionError):
        apply_task_update(db_session, task, TaskUpdate(
            activity_kind="ONLINE_MEETING", action_actor="USER", action_name="change_kind",
        ))
    with pytest.raises(InvalidTaskTransitionError):
        apply_task_update(db_session, task, TaskUpdate(
            draft=TaskDraft(content=DraftField(status="ACCEPTED", value="重写")),
            action_actor="USER", action_name="submit_field",
        ))


def test_chooser_budget_counts_only_nominations_not_other_model_actions(db_session):
    task = _make_task(db_session, budget_max_steps=1)
    apply_task_update(db_session, task, TaskUpdate(
        action_actor="MODEL", action_name="record_model_observation",
    ))
    assert task.budget_steps == 0
    apply_task_update(db_session, task, TaskUpdate(
        action_actor="SYSTEM", action_name="chooser_nomination",
    ))
    assert task.budget_steps == 1
    with pytest.raises(InvalidTaskTransitionError, match="budget"):
        apply_task_update(db_session, task, TaskUpdate(
            action_actor="SYSTEM", action_name="chooser_nomination",
        ))


def test_change_kind_clears_only_frozen_command_with_cas(db_session):
    task = _make_task(db_session, authority_json={
        "customer_public_id": "cus_1",
        "frozen_activity_command": {"submission_id": "sub_old"},
    })

    apply_task_update(db_session, task, TaskUpdate(
        clear_frozen_activity_command=True,
        action_actor="USER", action_name="change_kind",
    ))

    assert task.authority_json == {"customer_public_id": "cus_1"}
    assert task.version == 1

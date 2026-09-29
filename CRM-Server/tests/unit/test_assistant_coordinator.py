"""Waiting-state routing and cancel contracts for the assistant coordinator."""

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
from app.services.assistant.coordinator import (
    AssistantCoordinator,
    AssistantInput,
    NextActionDecision,
)
from app.services.assistant.task_state import TaskUpdate, apply_task_update

# ruff: noqa: RUF001


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


class StubChooser:
    """Deterministic fake for the Agent-LLM seam."""

    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = 0

    async def choose(self, task):
        self.calls += 1
        if not self.decisions:
            return NextActionDecision(action="end", parameters={})
        return self.decisions.pop(0)


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
        "goal": "记录睿狐科技的会议",
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


async def test_waiting_reply_merges_source_without_chooser(db_session):
    from app.services.assistant.llm_contracts import StructureDraftResult
    from app.services.assistant.quality_gate import QualityGateOutcome

    task = _make_task(db_session, activity_kind="FOLLOW_UP", draft_json=TaskDraft(
        content=DraftField(status="CANDIDATE", value="客户已完成演示"),
        content_json={"content": "客户已完成演示"}, source_segments=["客户已完成演示"],
    ).model_dump(mode="json"))
    task = apply_task_update(db_session, task, TaskUpdate(
        waiting=TaskWaiting(type="FIELD", field="next_action", question_id="q1", prompt="下一步？"),
        action_actor="SYSTEM", action_name="ask_quality_gap",
    )).task

    class Structurer:
        async def structure(self, db, *, team_id, kind, user_text):
            return StructureDraftResult(kind_confirmed=kind, content="", next_action=user_text)

    class Gate:
        async def evaluate(self, db, **kwargs):
            return QualityGateOutcome(False, 35, "缺少客户反馈", "content", "请补充客户反馈", {})

    chooser = StubChooser([])
    outcome = await AssistantCoordinator(chooser, structurer=Structurer(), quality_gate=Gate()).handle_task(
        db_session, task, AssistantInput(kind="submit_field", text="下周三与王总确认批复"),
    )
    assert chooser.calls == 0
    assert outcome.task.status == AssistantTaskStatus.ACTIVE
    assert outcome.reply.waiting and outcome.reply.waiting.field == "content"
    draft = TaskDraft.model_validate(outcome.task.draft_json)
    assert draft.next_action.value == "下周三与王总确认批复"
    assert draft.source_segments == ["客户已完成演示", "下周三与王总确认批复"]

async def test_cancel_closes_task_and_clears_waiting(db_session):
    task = _make_task(
        db_session,
        waiting_type=AssistantWaitingType.FIELD,
        waiting_field="next_action",
    )
    coordinator = AssistantCoordinator(StubChooser([]))

    outcome = await coordinator.handle_task(db_session, task, AssistantInput(kind="cancel"))

    assert outcome.task.status == AssistantTaskStatus.CANCELLED
    assert outcome.task.waiting_type is None
    assert "已取消" in outcome.reply.message


async def test_blank_field_answer_reasks_same_question(db_session):
    task = _make_task(db_session)
    apply_task_update(
        db_session,
        task,
        TaskUpdate(
            waiting=TaskWaiting(
                type=AssistantWaitingType.FIELD,
                field="next_action",
                question_id="q1",
                prompt="下一步是谁在什么时间做什么？",
            ),
            action_actor="MODEL",
            action_name="ask_field",
        ),
    )

    chooser = StubChooser([])
    coordinator = AssistantCoordinator(chooser)

    outcome = await coordinator.handle_task(
        db_session,
        task,
        AssistantInput(kind="submit_field", text="   "),
    )

    assert chooser.calls == 0  # blank answer must not reach the model
    assert outcome.reply.waiting is not None
    assert outcome.reply.waiting.field == "next_action"


async def test_activity_kind_accepts_only_closed_enum(db_session):
    task = _make_task(
        db_session,
        waiting_type=AssistantWaitingType.ACTIVITY_KIND,
    )
    chooser = StubChooser([])
    coordinator = AssistantCoordinator(chooser)

    outcome = await coordinator.handle_task(
        db_session,
        task,
        AssistantInput(kind="submit_field", choice="VIDEO_CALL"),
    )
    assert outcome.task.activity_kind is None  # rejected, still waiting

    outcome = await coordinator.handle_task(
        db_session,
        task,
        AssistantInput(kind="submit_field", choice="ONLINE_MEETING"),
    )
    assert outcome.task.activity_kind == "ONLINE_MEETING"


async def test_unknown_nomination_fails_closed(db_session):
    task = _make_task(db_session)
    coordinator = AssistantCoordinator(StubChooser([NextActionDecision(action="delete_customer", parameters={})]))

    outcome = await coordinator.handle_task(db_session, task, AssistantInput(kind="text", text="记一下"))

    assert outcome.task.status == AssistantTaskStatus.ACTIVE
    assert outcome.task.last_error_code == "UNKNOWN_ACTION_NOMINATED"
    assert outcome.task.waiting_type is None


async def test_drafted_field_survives_later_transitions(db_session):
    task = _make_task(db_session)
    apply_task_update(
        db_session,
        task,
        TaskUpdate(
            draft=TaskDraft(customer=DraftField(status="ACCEPTED", value="睿狐科技")),
            action_actor="SYSTEM",
            action_name="bind_customer",
        ),
    )

    coordinator = AssistantCoordinator(StubChooser([]))
    outcome = await coordinator.handle_task(db_session, task, AssistantInput(kind="text", text="继续"))

    # End nomination must not touch the accepted customer slot.
    draft = TaskDraft.model_validate(outcome.task.draft_json)
    assert draft.customer.value == "睿狐科技"
    assert draft.customer.status == "ACCEPTED"


async def test_chooser_reserves_budget_before_model_and_cannot_end_uncommitted_task(db_session):
    task = _make_task(db_session, budget_max_steps=1)

    class ObservingChooser:
        calls = 0

        async def choose(self, current):
            self.calls += 1
            assert current.budget_steps == 1
            return NextActionDecision(action="end", parameters={})

    chooser = ObservingChooser()
    coordinator = AssistantCoordinator(chooser)
    first = await coordinator.handle_task(db_session, task, AssistantInput(kind="text", text="还没写活动"))
    assert first.task.status == AssistantTaskStatus.ACTIVE
    assert first.task.budget_steps == 1
    assert first.task.last_error_code == "END_NOT_ALLOWED"
    assert db_session.query(AssistantAction).filter_by(task_id=task.id, action="chooser_nomination").count() == 1

    second = await coordinator.handle_task(db_session, first.task, AssistantInput(kind="text", text="重试"))
    assert chooser.calls == 1
    assert second.task.status == AssistantTaskStatus.ACTIVE
    assert second.task.last_error_code == "CHOOSER_BUDGET_EXHAUSTED"
    assert db_session.query(AssistantAction).filter_by(task_id=task.id, action="chooser_nomination").count() == 1

async def test_chooser_asks_only_an_editable_missing_field(db_session):
    task = _make_task(db_session)
    chooser = StubChooser([NextActionDecision(action="ask_field", parameters={
        "field": "next_action", "prompt": "下一步是谁负责？",
    })])
    outcome = await AssistantCoordinator(chooser).handle_task(
        db_session, task, AssistantInput(kind="text", text="请补充"),
    )
    assert outcome.reply.waiting and outcome.reply.waiting.type == "FIELD"
    assert outcome.reply.waiting.field == "next_action"
    assert outcome.task.budget_steps == 1


async def test_chooser_cannot_request_server_computed_score(db_session):
    task = _make_task(db_session)
    chooser = StubChooser([NextActionDecision(action="ask_field", parameters={
        "field": "quality_score", "prompt": "请输入评分",
    })])
    outcome = await AssistantCoordinator(chooser).handle_task(
        db_session, task, AssistantInput(kind="text", text="请补充"),
    )
    assert outcome.task.waiting_type is None
    assert outcome.task.status == AssistantTaskStatus.ACTIVE
    assert outcome.task.last_error_code == "UNKNOWN_ACTION_NOMINATED"

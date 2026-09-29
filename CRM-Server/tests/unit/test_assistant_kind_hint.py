"""G6 kind-hint behavior: change-kind directs the next classify round."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.assistant import AssistantAction, AssistantTask, AssistantTaskStatus
from app.services.assistant.contracts import TaskDraft
from app.services.assistant.intake_flow import intake_step
from app.services.assistant.llm_contracts import KindDecision, StructureDraftResult

# ruff: noqa: RUF001


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


class RecordingStructurer:
    """Classify would mislead if called; structure records the kind it got."""

    def __init__(self) -> None:
        self.classify_calls = 0
        self.structured_kinds: list[str] = []

    async def classify(self, db, *, team_id, user_text):
        self.classify_calls += 1
        return KindDecision(kind="FOLLOW_UP", reason="classifier would mislead")

    async def structure(self, db, *, team_id, kind, user_text):
        self.structured_kinds.append(kind)
        return StructureDraftResult(
            kind_confirmed=kind,
            content="客户确认 POC 可行。",
            customer_name="广州睿狐科技有限公司",
            next_action="下周三确认批复",
        )


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[AssistantTask.__table__, AssistantAction.__table__])
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _task(session, **overrides):
    values = {
        "team_id": 1,
        "user_id": 2,
        "status": AssistantTaskStatus.ACTIVE,
        "goal": "记录会议",
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


async def test_change_kind_hint_short_circuits_classifier(db_session):
    """A kind set by change-kind wins over the model on the next text turn."""

    task = _task(db_session, activity_kind="OFFLINE_MEETING")
    structurer = RecordingStructurer()

    updated, _message, waiting, _failed = await intake_step(
        db_session, task, "今天下午和客户开了个会", structurer
    )

    assert structurer.classify_calls == 0
    assert structurer.structured_kinds == ["OFFLINE_MEETING"]
    assert updated.activity_kind == "OFFLINE_MEETING"
    assert waiting is None


async def test_no_hint_still_classifies(db_session):
    """Without a stored kind the classifier runs as before."""

    task = _task(db_session)
    structurer = RecordingStructurer()

    await intake_step(db_session, task, "今天聊了两句", structurer)

    assert structurer.classify_calls == 1


async def test_open_kind_question_still_classifies_on_answer_flow(db_session):
    """A pending ACTIVITY_KIND wait must not be treated as a hint; the kind
    question flow routes through _answer_activity_kind, and intake only sees
    the task after the wait cleared — but guard: hinted intake must not fire
    while the wait exists."""

    task = _task(
        db_session,
        activity_kind=None,
        waiting_type="ACTIVITY_KIND",
        waiting_field="activity_kind",
        waiting_json={"payload": {"question_id": "q1", "prompt": "哪种活动？"}},
    )
    structurer = RecordingStructurer()

    _updated, _message, _waiting, _failed = await intake_step(
        db_session, task, "今天聊了两句", structurer
    )

    # With no stored kind, classification runs even if a stray kind wait
    # remains; the structuring proceeds on the classified kind.
    assert structurer.classify_calls == 1

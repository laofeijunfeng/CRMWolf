"""Quality intake scores the draft and requests missing facts without writing."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.assistant import AssistantAction, AssistantTask, AssistantTaskStatus, AssistantWaitingType
from app.services.assistant.contracts import TaskDraft
from app.services.assistant.intake_flow import intake_step
from app.services.assistant.llm_contracts import KindDecision, StructureDraftResult
from app.services.assistant.quality_gate import QualityGateOutcome

# ruff: noqa: RUF001


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


class PassGate:
    async def evaluate(self, db, *, team_id, user_text, content, next_action, kind="FOLLOW_UP", content_json=None):
        return QualityGateOutcome(passed=True, score=82, reason="ok", gap_field=None, question=None)


class FailGate:
    def __init__(self, gap="next_action"):
        self.gap = gap

    async def evaluate(self, db, *, team_id, user_text, content, next_action, kind="FOLLOW_UP", content_json=None):
        return QualityGateOutcome(
            passed=False, score=40, reason="缺关键信息", gap_field=self.gap, question="下一步是什么？"
        )


class GoodStructurer:
    async def classify(self, db, *, team_id, user_text):
        return KindDecision(kind="FOLLOW_UP")

    async def structure(self, db, *, team_id, kind, user_text):
        return StructureDraftResult(
            kind_confirmed="FOLLOW_UP",
            content="客户反馈 POC 可行。",
            customer_name="睿狐科技",
            next_action="下周三确认批复",
        )


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[AssistantTask.__table__, AssistantAction.__table__])
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
        "goal": "记录跟进",
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

async def test_failed_gate_asks_single_gap_not_confirmation(db_session):
    task = _make_task(db_session)

    updated, message, waiting, failed = await intake_step(
        db_session, task, "聊了一下", GoodStructurer(), FailGate()
    )

    assert failed is False
    assert waiting is not None and waiting.type == AssistantWaitingType.FIELD
    assert waiting.field == "next_action"
    assert updated.waiting_type == AssistantWaitingType.FIELD
    assert TaskDraft.model_validate(updated.draft_json).quality_score.status == "MISSING"
    assert updated.authority_json.get("frozen_activity_command") is None
    assert updated.committed_json == []
    assert "下一步" in message


async def test_passed_gate_scores_draft_without_freezing_confirmation(db_session):
    task = _make_task(db_session)

    updated, _message, waiting, failed = await intake_step(
        db_session, task, "聊得很好", GoodStructurer(), PassGate()
    )

    draft = TaskDraft.model_validate(updated.draft_json)
    assert failed is False
    assert waiting is None
    assert updated.waiting_type is None
    assert updated.authority_json.get("frozen_activity_command") is None
    assert draft.content.value == "客户反馈 POC 可行。"
    assert draft.quality_score.value == "82"
    assert updated.committed_json == []



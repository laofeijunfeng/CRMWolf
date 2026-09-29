"""Stage-event sequences per turn type (TRD §2.3 matrix)."""

from types import SimpleNamespace

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
from app.models.customer import Customer, CustomerMember, CustomerProduct
from app.services.assistant.confirmation import WriteActivityResult
from app.services.assistant.contracts import DraftField, TaskDraft
from app.services.assistant.coordinator import AssistantCoordinator, AssistantInput, NextActionDecision
from app.services.assistant.events import SSEProgressReporter
from app.services.assistant.llm_contracts import KindDecision, StructureDraftResult
from app.services.assistant.quality_gate import QualityGateOutcome

# ruff: noqa: RUF001


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


class Structurer:
    async def classify(self, db, *, team_id, user_text):
        return KindDecision(kind="FOLLOW_UP")

    async def structure(self, db, *, team_id, kind, user_text):
        return StructureDraftResult(
            kind_confirmed=kind,
            content="客户确认 POC 可行。",
            customer_name="广州睿狐科技有限公司",
            next_action="下周三确认批复",
        )


class PassGate:
    async def evaluate(self, db, **kw):
        return QualityGateOutcome(passed=True, score=88, reason="ok", gap_field=None, question=None)


class NoModel:
    async def classify(self, db, **kw):
        raise AssertionError("confirmation must not classify")

    async def structure(self, db, **kw):
        raise AssertionError("confirmation must not restructure")


class NoGate:
    async def evaluate(self, db, **kw):
        raise AssertionError("confirmation must not rescore")


class Writer:
    async def write_activity(self, db, **kw):
        return WriteActivityResult(success=True, activity_public_id="9", error_code=None)


class Chooser:
    async def choose(self, task):
        return NextActionDecision(action="end", parameters={})


@pytest.fixture
def db_session(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AssistantTask.__table__,
            AssistantAction.__table__,
            Customer.__table__,
            CustomerProduct.__table__,
            CustomerMember.__table__,
        ],
    )
    monkeypatch.setattr(
        "app.services.assistant.customer_resolution.permission_crud.get_user_permissions",
        lambda *args: [SimpleNamespace(code="customer:activity:create")],
    )
    session = sessionmaker(bind=engine)()
    session.add(Customer(
        team_id=1, account_name="广州睿狐科技有限公司", public_id="cus_st_1",
        city="广州", creator_id="2", owner_id="2",
    ))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _task(session, **overrides):
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


def stages_of(reporter):
    return [(item[1]["stage"], item[1]["phase"]) for item in reporter.drain()]


async def test_text_turn_emits_classify_structure_gate(db_session):
    task = _task(db_session)
    reporter = SSEProgressReporter()
    coordinator = AssistantCoordinator(Chooser(), structurer=Structurer(), quality_gate=PassGate())

    await coordinator.handle_task(db_session, task, AssistantInput(kind="text", text="聊了 POC"), reporter=reporter)

    stages = stages_of(reporter)
    assert ("classify", "start") in stages
    assert ("classify", "done") in stages
    assert ("structure", "start") in stages
    assert ("structure", "done") in stages
    assert ("quality_gate", "done") in stages
    # Order: classify before structure before gate
    assert stages.index(("classify", "start")) < stages.index(("structure", "start"))
    assert stages.index(("structure", "done")) < stages.index(("quality_gate", "start"))


async def test_gate_done_carries_score(db_session):
    task = _task(db_session)
    reporter = SSEProgressReporter()
    coordinator = AssistantCoordinator(Chooser(), structurer=Structurer(), quality_gate=PassGate())

    await coordinator.handle_task(db_session, task, AssistantInput(kind="text", text="聊了"), reporter=reporter)

    done = [
        item[1] for item in reporter.drain()
        if item[1]["phase"] == "done" and item[1]["stage"] == "quality_gate"
    ]
    assert [stage["score"] for stage in done] == [88]


async def test_field_answer_structures_and_scores_without_classifying(db_session):
    task = _task(
        db_session,
        activity_kind="FOLLOW_UP",
        draft_json=TaskDraft(
            customer=DraftField(status="ACCEPTED", value="广州睿狐科技有限公司"),
            content=DraftField(status="CANDIDATE", value="客户确认 POC 可行。"),
        ).model_dump(mode="json"),
        waiting_type=AssistantWaitingType.FIELD,
        waiting_field="next_action",
        waiting_json={"payload": {"question_id": "q1", "prompt": "下一步？"}},
    )
    reporter = SSEProgressReporter()
    coordinator = AssistantCoordinator(Chooser(), structurer=Structurer(), quality_gate=PassGate())

    await coordinator.handle_task(
        db_session, task, AssistantInput(kind="submit_field", text="下周三确认批复"), reporter=reporter
    )

    stages = stages_of(reporter)
    assert ("classify", "start") not in stages
    assert ("structure", "start") in stages
    assert ("structure", "done") in stages
    assert ("quality_gate", "start") in stages
    assert stages.index(("structure", "done")) < stages.index(("quality_gate", "start"))


async def test_confirm_turn_writes_frozen_activity_without_model_or_gate(db_session):
    task = _task(
        db_session,
        activity_kind="FOLLOW_UP",
        draft_json=TaskDraft(
            customer=DraftField(status="CANDIDATE", value="广州睿狐科技有限公司"),
            content=DraftField(status="CANDIDATE", value="客户确认 POC 可行。"),
            next_action=DraftField(status="CANDIDATE", value="下周三确认批复"),
            content_json={"content": "客户确认 POC 可行。", "next_action": "下周三确认批复"},
            source_segments=["客户确认 POC 可行，下周三确认批复"],
            quality_score=DraftField(status="CANDIDATE", value="88"),
            score_reason="事实与行动明确",
        ).model_dump(mode="json"),
    )
    writer = Writer()
    coordinator = AssistantCoordinator(Chooser(), writer=writer)
    prepared = await coordinator.handle_task(db_session, task, AssistantInput(kind="text"))
    assert prepared.reply.waiting is not None
    assert prepared.reply.waiting.type == AssistantWaitingType.CONFIRMATION
    assert prepared.reply.waiting.fingerprint == prepared.task.authority_json["frozen_activity_command"]["fingerprint"]
    reporter = SSEProgressReporter()
    coordinator = AssistantCoordinator(Chooser(), structurer=NoModel(), writer=writer, quality_gate=NoGate())

    confirmed = await coordinator.handle_task(
        db_session, prepared.task, AssistantInput(kind="confirm", choice="confirm"), reporter=reporter
    )

    stages = stages_of(reporter)
    assert stages == [("write", "start"), ("write", "done")]
    assert confirmed.start_followup is True
    assert confirmed.task.committed_json[0]["public_id"] == "9"


async def test_cancel_emits_no_stages(db_session):
    task = _task(db_session)
    reporter = SSEProgressReporter()
    coordinator = AssistantCoordinator(Chooser(), structurer=Structurer(), quality_gate=PassGate())

    await coordinator.handle_task(db_session, task, AssistantInput(kind="cancel"), reporter=reporter)

    assert stages_of(reporter) == []

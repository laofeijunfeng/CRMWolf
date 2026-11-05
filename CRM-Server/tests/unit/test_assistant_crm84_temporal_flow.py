"""CRM-84: persisted action-scoped answers cannot become unbound scalar writes."""

from datetime import datetime

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.assistant import AssistantAction, AssistantTask
from app.services.assistant.action_evidence import SourceSegment
from app.services.assistant.contracts import DraftField, TaskDraft
from app.services.assistant.coordinator import AssistantCoordinator, AssistantInput
from app.services.assistant.task_state import load_draft, load_waiting
from app.services.assistant.temporal_evidence import attach_model_evidence, resolved_sales_follow_up


@compiles(BigInteger, "sqlite")
def _bigint_sqlite(element, compiler, **kwargs):
    return "INTEGER"


class NoChooser:
    async def choose(self, task):
        raise AssertionError("an already-scored temporal answer must not replan the activity")


@pytest.fixture
def factory(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'crm84.sqlite'}")
    Base.metadata.create_all(engine, tables=[AssistantTask.__table__, AssistantAction.__table__])
    monkeypatch.setattr("app.utils.time.business_now", lambda: datetime(2026, 11, 5, 10))
    yield sessionmaker(bind=engine)
    engine.dispose()


def _draft(text):
    draft = TaskDraft(
        content=DraftField(status="CANDIDATE", value=text),
        content_json={"content": text},
        source_segments=[text],
        source_records=[SourceSegment(segment_id="original", text=text, recorded_at=datetime(2026, 11, 5, 9))],
        quality_score=DraftField(status="CANDIDATE", value="85"),
    )
    attach_model_evidence(
        draft, segment_id="original", segment_text=text, anchor=datetime(2026, 11, 5, 9), mentions=[], actions=[]
    )
    return draft


async def _start(factory, text):
    coordinator = AssistantCoordinator(NoChooser())
    with factory() as db:
        draft = _draft(text)
        task = AssistantTask(
            team_id=1,
            user_id=2,
            status="ACTIVE",
            goal="记录沟通",
            activity_kind="FOLLOW_UP",
            draft_json=draft.model_dump(mode="json"),
            authority_json={},
            committed_json=[],
        )
        db.add(task)
        db.commit()
        output = await coordinator.handle_task(db, task, AssistantInput(kind="text"))
        db.commit()
        return task.id, output.reply.waiting


async def test_date_answer_survives_reload_and_retires_old_question(factory):
    task_id, waiting = await _start(factory, "我大概明年联系客户")
    assert waiting.temporal_target.business_action_id
    old_action = waiting.action_id
    with factory() as db:
        task = db.get(AssistantTask, task_id)
        await AssistantCoordinator(NoChooser()).handle_task(
            db, task, AssistantInput(kind="submit_field", text="12 月 5 号")
        )
        db.commit()
    with factory() as db:
        task = db.get(AssistantTask, task_id)
        draft = load_draft(task)
        assert resolved_sales_follow_up(draft) == (datetime(2026, 12, 5), "DATE")
        assert load_waiting(task).field == "customer"
        assert load_waiting(task).action_id != old_action
        assert draft.source_records[-1].text == "12 月 5 号"
        assert draft.customer.status == "MISSING"
        assert task.committed_json == []


async def test_role_answer_keeps_date_then_only_resolves_remaining_ownership(factory):
    task_id, initial = await _start(factory, "月底付款")
    assert initial.temporal_target.reason == "ROLE"
    with factory() as db:
        task = db.get(AssistantTask, task_id)
        await AssistantCoordinator(NoChooser()).handle_task(
            db, task, AssistantInput(kind="submit_field", text="12月5号")
        )
        db.commit()
    with factory() as db:
        task = db.get(AssistantTask, task_id)
        waiting = load_waiting(task)
        assert waiting.temporal_target.reason == "ROLE"
        assert waiting.temporal_target.business_action_id == initial.temporal_target.business_action_id
        choice = next(item["id"] for item in waiting.candidates if item["id"].endswith(":sales"))
        await AssistantCoordinator(NoChooser()).handle_task(
            db, task, AssistantInput(kind="submit_field", choice=choice)
        )
        db.commit()
    with factory() as db:
        task = db.get(AssistantTask, task_id)
        assert resolved_sales_follow_up(load_draft(task)) == (datetime(2026, 12, 5), "DATE")
        assert load_waiting(task).field == "customer"


async def test_legacy_wait_without_target_reissues_before_accepting_answer(factory):
    task_id, _ = await _start(factory, "我大概明年联系客户")
    with factory() as db:
        task = db.get(AssistantTask, task_id)
        legacy = dict(task.waiting_json)
        legacy["payload"] = {key: value for key, value in legacy["payload"].items() if key != "temporal_target"}
        task.waiting_json = legacy
        db.commit()
    with factory() as db:
        task = db.get(AssistantTask, task_id)
        await AssistantCoordinator(NoChooser()).handle_task(
            db, task, AssistantInput(kind="submit_field", text="12月5号")
        )
        db.commit()
    with factory() as db:
        task = db.get(AssistantTask, task_id)
        assert load_waiting(task).temporal_target.reason == "DATE"
        assert resolved_sales_follow_up(load_draft(task)) == (None, "UNKNOWN")
        assert [record.text for record in load_draft(task).source_records] == ["我大概明年联系客户"]

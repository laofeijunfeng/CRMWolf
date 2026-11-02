# ruff: noqa: RUF001
"""CRM-73: one flat choice of the seven concrete activity kinds."""

from __future__ import annotations

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
from app.services.assistant.activity_channel import (
    ACTIVITY_KIND_CHOICES,
    CANONICAL_KINDS,
    FOLLOW_UP_KINDS,
    MEETING_KINDS,
    kind_choice_candidates,
    kind_hint,
    selected_kind,
)
from app.services.assistant.contracts import TaskDraft, TaskWaiting
from app.services.assistant.coordinator import (
    AssistantCoordinator,
    AssistantInput,
    NextActionDecision,
)
from app.services.assistant.llm_contracts import StructureDraftResult
from app.services.assistant.task_state import TaskUpdate, apply_task_update, load_draft


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


class StubChooser:
    """Deterministic fake for the Agent-LLM seam."""

    def __init__(self) -> None:
        self.calls = 0

    async def choose(self, task):
        self.calls += 1
        return NextActionDecision(action="end", parameters={})


class RecordingStructurer:
    """Classify must never run once the user picked a concrete kind."""

    def __init__(self) -> None:
        self.classify_calls = 0
        self.structured_kinds: list[str] = []

    async def classify(self, db, *, team_id, user_text):
        self.classify_calls += 1
        raise AssertionError("a chosen kind must not be re-classified")

    async def structure(self, db, *, team_id, kind, user_text):
        self.structured_kinds.append(kind)
        return StructureDraftResult(
            kind_confirmed=kind,
            content="客户确认 POC 可行。",
            customer_name="睿狐科技",
            next_action="下周三确认批复",
            next_follow_time_text="下周三",
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
        "goal": "今天微信上和客户聊了 POC 部署",
        "draft_json": TaskDraft(source_segments=["今天微信上和客户聊了 POC 部署"]).model_dump(mode="json"),
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


def _kind_task(session, **overrides):
    task = _task(session, **overrides)
    return apply_task_update(
        session,
        task,
        TaskUpdate(
            waiting=TaskWaiting(
                type=AssistantWaitingType.ACTIVITY_KIND,
                field="activity_kind",
                question_id="q_kind",
                prompt="这次沟通属于哪种活动？",
                candidates=kind_choice_candidates(),
                hint="原文提到：微信",
            ),
            action_actor="SYSTEM",
            action_name="ask_activity_kind",
        ),
    ).task


def test_kind_choices_are_the_seven_concrete_kinds() -> None:
    assert [(choice.kind, choice.group, choice.description) for choice in ACTIVITY_KIND_CHOICES] == [
        ("ONLINE_MEETING", "会议", "远程会议"),
        ("OFFLINE_MEETING", "会议", "当面开会"),
        ("PHONE_FOLLOW_UP", "跟进", "电话沟通"),
        ("WECHAT_FOLLOW_UP", "跟进", "微信 / 企业微信"),
        ("EMAIL_FOLLOW_UP", "跟进", "邮件往来"),
        ("VISIT_FOLLOW_UP", "跟进", "上门拜访、面谈"),
        ("OTHER_FOLLOW_UP", "跟进", "以上都不是"),
    ]
    assert [candidate["id"] for candidate in kind_choice_candidates()] == [
        choice.kind for choice in ACTIVITY_KIND_CHOICES
    ]
    assert [candidate["group"] for candidate in kind_choice_candidates()] == [
        "会议",
        "会议",
        "跟进",
        "跟进",
        "跟进",
        "跟进",
        "跟进",
    ]
    # The coarse family is not a selectable type any more.
    assert frozenset(FOLLOW_UP_KINDS + MEETING_KINDS) == CANONICAL_KINDS
    assert "FOLLOW_UP" not in CANONICAL_KINDS


def test_kind_hint_names_the_channels_the_text_mentioned() -> None:
    assert kind_hint("今天微信沟通完，下午又开了线上会议") == "原文提到：微信、线上会议"
    assert kind_hint("打了电话，也在企业微信上聊了，还发邮件确认") == "原文提到：电话、微信、邮件"
    assert kind_hint("今天和客户聊了很多") is None
    assert kind_hint("") is None


def test_selected_kind_keeps_same_family_options() -> None:
    follow_up = selected_kind("WECHAT_FOLLOW_UP")
    assert follow_up.kind == "WECHAT_FOLLOW_UP"
    assert follow_up.family == "FOLLOW_UP"
    assert follow_up.source == "user"
    assert follow_up.status_label == "已选择"
    assert follow_up.source_text == "你选择：微信跟进"
    assert follow_up.options == FOLLOW_UP_KINDS

    meeting = selected_kind("OFFLINE_MEETING")
    assert meeting.family == "OFFLINE_MEETING"
    assert meeting.source_text == "你选择：线下会议"
    assert meeting.options == MEETING_KINDS

    with pytest.raises(ValueError):
        selected_kind("FOLLOW_UP")


async def test_out_of_range_kind_keeps_the_card_with_the_seven_choices(db_session) -> None:
    task = _kind_task(db_session)
    coordinator = AssistantCoordinator(StubChooser())

    current = task
    for rejected in ("FOLLOW_UP", "VIDEO_CALL"):
        outcome = await coordinator.handle_task(
            db_session, current, AssistantInput(kind="submit_field", choice=rejected)
        )
        waiting = outcome.reply.waiting
        assert outcome.task.activity_kind is None
        assert waiting is not None and waiting.type == AssistantWaitingType.ACTIVITY_KIND
        assert outcome.reply.message == "请从卡片给出的活动类型中选择。"
        assert [candidate["id"] for candidate in waiting.candidates] == [
            choice.kind for choice in ACTIVITY_KIND_CHOICES
        ]
        current = outcome.task


async def test_offline_meeting_choice_structures_with_the_meeting_schema(db_session) -> None:
    task = _kind_task(db_session)
    structurer = RecordingStructurer()
    coordinator = AssistantCoordinator(StubChooser(), structurer=structurer)

    outcome = await coordinator.handle_task(
        db_session, task, AssistantInput(kind="submit_field", choice="OFFLINE_MEETING")
    )

    assert outcome.task.activity_kind == "OFFLINE_MEETING"
    draft = load_draft(outcome.task)
    assert draft.channel_kind == "OFFLINE_MEETING"
    assert draft.channel_status_label == "已选择"
    assert structurer.classify_calls == 0
    assert structurer.structured_kinds == ["OFFLINE_MEETING"]
    assert outcome.reply.waiting is None or outcome.reply.waiting.type != AssistantWaitingType.ACTIVITY_KIND

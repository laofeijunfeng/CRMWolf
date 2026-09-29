"""Chooser contracts: closed action set, invalid output never guesses."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.ai_config import AIConfig
from app.models.assistant import (
    AssistantAction,
    AssistantTask,
    AssistantTaskStatus,
)
from app.services.assistant.chooser import ActionNomination, AgentLLMChooser
from app.services.assistant.contracts import DraftField, TaskDraft

# ruff: noqa: RUF001


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


class FakeRuntime:
    def __init__(self, nomination):
        self.nomination = nomination
        self.prompts: list[str] = []

    async def ainvoke_structured(self, *, user_prompt, **kwargs):
        self.prompts.append(user_prompt)
        return self.nomination


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[AssistantTask.__table__, AssistantAction.__table__, AIConfig.__table__],
    )
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


def _config(session):
    session.add(
        AIConfig(
            team_id=1,
            api_host="https://example.internal/v1",
            api_key_encrypted=AIConfig.encrypt_api_key("sk-test"),
            model_name="test-model",
            temperature=0,
            max_tokens=1024,
        )
    )
    session.commit()


async def test_asks_missing_field_with_prompt(db_session):
    _config(db_session)
    task = _task(db_session)
    runtime = FakeRuntime(
        ActionNomination(action="ask_field", field="next_action", prompt="下一步是什么？", reason="缺下一步")
    )
    chooser = AgentLLMChooser(runtime=runtime)

    decision = await chooser.choose(task)

    assert decision.action == "ask_field"
    assert decision.parameters["field"] == "next_action"
    assert decision.parameters["prompt"] == "下一步是什么？"
    # Snapshot prompt must carry draft state, not raw conversation.
    assert "next_action（下一步行动）：MISSING" in runtime.prompts[0]


async def test_end_when_goal_reached(db_session):
    _config(db_session)
    task = _task(
        db_session,
        draft_json=TaskDraft(content=DraftField(status="ACCEPTED", value="done")).model_dump(mode="json"),
        committed_json=[
            {"kind": "customer_activity"},
            {"kind": "refused:opportunity"},
            {"kind": "refused:follow_up_task"},
        ],
    )
    runtime = FakeRuntime(ActionNomination(action="end", reason="goal_reached"))
    chooser = AgentLLMChooser(runtime=runtime)

    decision = await chooser.choose(task)

    assert decision.action == "end"
    assert "refused:opportunity" in runtime.prompts[0]


async def test_missing_config_raises_technical_error(db_session):
    from app.services.assistant.llm import AssistantLLMError

    task = _task(db_session)  # no AIConfig row
    chooser = AgentLLMChooser(runtime=FakeRuntime(ActionNomination(action="end")))

    with pytest.raises(AssistantLLMError, match="配置"):
        await chooser.choose(task)


async def test_closed_enum_rejects_unknown_action(db_session):
    """ActionNomination itself must refuse unknown action names."""

    import pydantic

    with pytest.raises(pydantic.ValidationError):
        ActionNomination(action="delete_customer")


async def test_snapshot_excludes_accepted_slot_from_asking(db_session):
    """Prompt builder marks ACCEPTED slots so the model won't re-ask them."""

    _config(db_session)
    task = _task(
        db_session,
        draft_json=TaskDraft(customer=DraftField(status="ACCEPTED", value="睿狐科技")).model_dump(mode="json"),
    )
    runtime = FakeRuntime(ActionNomination(action="end"))
    await AgentLLMChooser(runtime=runtime).choose(task)

    assert "customer（客户名称）：ACCEPTED「睿狐科技」" in runtime.prompts[0]


async def test_missing_chooser_action_is_technical_failure(db_session):
    from app.services.assistant.llm import AssistantLLMError

    _config(db_session)
    task = _task(db_session)
    with pytest.raises(AssistantLLMError):
        await AgentLLMChooser(runtime=FakeRuntime({})).choose(task)


async def test_ask_field_requires_valid_field_and_prompt(db_session):
    from app.services.assistant.llm import AssistantLLMError

    _config(db_session)
    task = _task(db_session)
    with pytest.raises(AssistantLLMError):
        await AgentLLMChooser(runtime=FakeRuntime({"action": "ask_field", "field": "unknown", "prompt": "why?"})).choose(task)

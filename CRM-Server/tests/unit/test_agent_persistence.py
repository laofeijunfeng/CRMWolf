"""Persistence contracts for the CRM Agent query architecture."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.agent import AgentMessage, AgentMessageRole, AgentSession
from app.models.agent_persistence import AgentQueryResultSet, AgentUIAction
from app.schemas.agent_persistence import AgentQueryResultSetCreate, AgentResultPage
from app.services.agent.query.result_sets import (
    AgentQueryResultSetRepository,
    ResultSetExpiredError,
    ResultSetNotFoundError,
    ResultSetOwnershipError,
)
from app.services.agent.query.schemas import CRMFilter, CRMQuerySpec, EntityRef


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
        tables=[
            AgentSession.__table__,
            AgentMessage.__table__,
            AgentQueryResultSet.__table__,
            AgentUIAction.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_message(db_session) -> AgentMessage:
    session = AgentSession(session_key="agent-session-1", team_id=1, user_id=2)
    db_session.add(session)
    db_session.flush()
    message = AgentMessage(
        team_id=1,
        user_id=2,
        session_id=session.id,
        role=AgentMessageRole.ASSISTANT,
        content="上海客户列表",
    )
    db_session.add(message)
    db_session.commit()
    return message


def _result_set_create(message: AgentMessage) -> AgentQueryResultSetCreate:
    return AgentQueryResultSetCreate(
        public_id="rs_test_snapshot",
        team_id=1,
        user_id=2,
        session_id=message.session_id,
        source_message_id=message.id,
        resource="customer",
        query=CRMQuerySpec(
            resource="customer",
            projection=["public_id", "account_name", "city"],
            filters=[CRMFilter(field="city", operator="eq", value="上海")],
        ),
        ordered_entity_refs=[
            EntityRef(
                ref_id="ref_customer_1",
                resource="customer",
                public_id="cus_11111111111111111111111111111111",
                display_name="甲客户",
            ),
            EntityRef(
                ref_id="ref_customer_2",
                resource="customer",
                public_id="cus_22222222222222222222222222222222",
                display_name="乙客户",
            ),
        ],
        page=AgentResultPage(page_size=20, range_start=1, range_end=2, total=2),
    )


def test_result_set_repository_creates_immutable_owned_snapshot(db_session) -> None:
    message = _seed_message(db_session)
    now = datetime(2026, 8, 21, 10, 0, 0)
    repository = AgentQueryResultSetRepository()

    created = repository.create(db_session, _result_set_create(message), now=now)
    db_session.commit()

    assert created.public_id == "rs_test_snapshot"
    assert created.row_count == 2
    assert created.expires_at == now + timedelta(hours=24)
    assert [ref.result_set_id for ref in created.ordered_entity_refs] == [created.public_id, created.public_id]

    loaded = repository.get_active(
        db_session,
        public_id=created.public_id,
        team_id=1,
        user_id=2,
        session_id=message.session_id,
        now=now + timedelta(hours=1),
    )
    assert loaded == created

    with pytest.raises(ResultSetNotFoundError):
        repository.get_active(
            db_session,
            public_id=created.public_id,
            team_id=1,
            user_id=999,
            session_id=message.session_id,
            now=now + timedelta(hours=1),
        )


def test_result_set_repository_rejects_non_assistant_source_message(db_session) -> None:
    assistant_message = _seed_message(db_session)
    user_message = AgentMessage(
        team_id=assistant_message.team_id,
        user_id=assistant_message.user_id,
        session_id=assistant_message.session_id,
        role=AgentMessageRole.USER,
        content="我在上海有哪些客户",
    )
    db_session.add(user_message)
    db_session.commit()

    request = _result_set_create(assistant_message).model_copy(update={"source_message_id": user_message.id})

    with pytest.raises(ResultSetOwnershipError, match="assistant message"):
        AgentQueryResultSetRepository().create(db_session, request)


def test_result_set_repository_fails_closed_for_cross_tenant_parent(db_session) -> None:
    owner_message = _seed_message(db_session)
    foreign_session = AgentSession(session_key="agent-session-foreign", team_id=2, user_id=3)
    db_session.add(foreign_session)
    db_session.flush()
    foreign_message = AgentMessage(
        team_id=2,
        user_id=3,
        session_id=foreign_session.id,
        role=AgentMessageRole.ASSISTANT,
        content="其他团队客户列表",
    )
    db_session.add(foreign_message)
    db_session.commit()

    repository = AgentQueryResultSetRepository()
    owner_result = repository.create(db_session, _result_set_create(owner_message))
    foreign_request = _result_set_create(foreign_message).model_copy(
        update={"public_id": "rs_foreign_snapshot", "team_id": 2, "user_id": 3}
    )
    foreign_result = repository.create(db_session, foreign_request)
    db_session.commit()

    owner_row = db_session.query(AgentQueryResultSet).filter_by(public_id=owner_result.public_id).one()
    foreign_row = db_session.query(AgentQueryResultSet).filter_by(public_id=foreign_result.public_id).one()
    owner_row.parent_result_set_id = foreign_row.id
    db_session.commit()
    db_session.expire_all()

    with pytest.raises(ResultSetOwnershipError, match="parent result set"):
        repository.get_active(
            db_session,
            public_id=owner_result.public_id,
            team_id=1,
            user_id=2,
            session_id=owner_message.session_id,
        )


def test_result_set_repository_distinguishes_expiry_and_purges_after_retention(db_session) -> None:
    message = _seed_message(db_session)
    foreign_session = AgentSession(session_key="agent-session-foreign", team_id=2, user_id=3)
    db_session.add(foreign_session)
    db_session.flush()
    foreign_message = AgentMessage(
        team_id=2,
        user_id=3,
        session_id=foreign_session.id,
        role=AgentMessageRole.ASSISTANT,
        content="外部团队客户列表",
    )
    db_session.add(foreign_message)
    db_session.flush()
    now = datetime(2026, 8, 21, 10, 0, 0)
    repository = AgentQueryResultSetRepository()
    created = repository.create(
        db_session,
        _result_set_create(message).model_copy(update={"expires_at": now - timedelta(days=8)}),
        now=now,
    )
    foreign_created = repository.create(
        db_session,
        _result_set_create(foreign_message).model_copy(
            update={
                "public_id": "rs_foreign_expired_snapshot",
                "team_id": 2,
                "user_id": 3,
                "expires_at": now - timedelta(days=8),
            }
        ),
        now=now,
    )
    db_session.commit()

    with pytest.raises(ResultSetExpiredError):
        repository.get_active(
            db_session,
            public_id=created.public_id,
            team_id=1,
            user_id=2,
            session_id=message.session_id,
            now=now,
        )

    assert repository.purge_expired(db_session, team_id=1, now=now) == 1
    db_session.commit()
    remaining = db_session.query(AgentQueryResultSet).one()
    assert str(remaining.public_id) == foreign_created.public_id
    assert remaining.team_id == 2


def test_ui_action_repository_atomically_claims_and_replays_one_shot_action(db_session) -> None:
    from app.schemas.agent_persistence import AgentUIActionRegistration
    from app.services.agent.ui.actions import (
        ActionAlreadyConsumedError,
        AgentUIActionRepository,
    )

    message = _seed_message(db_session)
    result_message = AgentMessage(
        team_id=1,
        user_id=2,
        session_id=message.session_id,
        role=AgentMessageRole.ASSISTANT,
        content="工作流已启动",
    )
    db_session.add(result_message)
    db_session.flush()
    now = datetime(2026, 8, 21, 10, 0, 0)
    repository = AgentUIActionRepository()
    action = repository.register(
        db_session,
        AgentUIActionRegistration(
            public_id="act_start_workflow_1",
            team_id=1,
            user_id=2,
            session_id=message.session_id,
            message_id=message.id,
            action_type="start_workflow",
            root_context_role="PROJECTION_ONLY",
            target={"entity_ref": "ref_customer_1", "workflow": "assign_owner"},
            consumption_mode="ONE_SHOT",
        ),
        now=now,
    )
    db_session.commit()

    acquired = repository.begin_consumption(
        db_session,
        public_id=action.public_id,
        team_id=1,
        user_id=2,
        session_id=message.session_id,
        client_request_id="6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be",
        now=now,
    )
    assert acquired.outcome == "ACQUIRED"
    assert acquired.action.status == "CONSUMING"

    replay_while_running = repository.begin_consumption(
        db_session,
        public_id=action.public_id,
        team_id=1,
        user_id=2,
        session_id=message.session_id,
        client_request_id="6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be",
        now=now,
    )
    assert replay_while_running.outcome == "REPLAY"
    assert replay_while_running.action.result_message_id is None

    with pytest.raises(ActionAlreadyConsumedError):
        repository.begin_consumption(
            db_session,
            public_id=action.public_id,
            team_id=1,
            user_id=2,
            session_id=message.session_id,
            client_request_id="7fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be",
            now=now,
        )

    completed = repository.complete_consumption(
        db_session,
        public_id=action.public_id,
        team_id=1,
        user_id=2,
        session_id=message.session_id,
        client_request_id="6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be",
        result_message_id=result_message.id,
        submitted_values={"text": "已与河南双汇技术经理沟通 POC 部署。"},
        now=now + timedelta(seconds=1),
    )
    db_session.commit()
    assert completed.status == "CONSUMED"
    assert completed.result_message_id == result_message.id

    replay_after_completion = repository.begin_consumption(
        db_session,
        public_id=action.public_id,
        team_id=1,
        user_id=2,
        session_id=message.session_id,
        client_request_id="6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be",
        now=now + timedelta(seconds=2),
    )
    assert replay_after_completion.outcome == "REPLAY"
    assert replay_after_completion.action.result_message_id == result_message.id
    assert replay_after_completion.action.submitted_values == {
        "text": "已与河南双汇技术经理沟通 POC 部署。",
    }
    assert db_session.query(AgentUIAction).count() == 1


def test_ui_action_repository_leaves_reusable_action_active_and_expires_stale_action(db_session) -> None:
    from app.schemas.agent_persistence import AgentUIActionRegistration
    from app.services.agent.ui.actions import ActionExpiredError, AgentUIActionRepository

    message = _seed_message(db_session)
    now = datetime(2026, 8, 21, 10, 0, 0)
    repository = AgentUIActionRepository()
    reusable = repository.register(
        db_session,
        AgentUIActionRegistration(
            public_id="act_open_entity_1",
            team_id=1,
            user_id=2,
            session_id=message.session_id,
            message_id=message.id,
            action_type="open_entity",
            root_context_role="PROJECTION_ONLY",
            target={"entity_ref": "ref_customer_1"},
            consumption_mode="REUSABLE",
        ),
        now=now,
    )
    expired = repository.register(
        db_session,
        AgentUIActionRegistration(
            public_id="act_retry_1",
            team_id=1,
            user_id=2,
            session_id=message.session_id,
            message_id=message.id,
            action_type="retry",
            root_context_role="PROJECTION_ONLY",
            target={"turn_id": "turn_1"},
            consumption_mode="ONE_SHOT",
            expires_at=now - timedelta(seconds=1),
        ),
        now=now,
    )
    db_session.commit()

    first = repository.begin_consumption(
        db_session,
        public_id=reusable.public_id,
        team_id=1,
        user_id=2,
        session_id=message.session_id,
        client_request_id="6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be",
        now=now,
    )
    second = repository.begin_consumption(
        db_session,
        public_id=reusable.public_id,
        team_id=1,
        user_id=2,
        session_id=message.session_id,
        client_request_id="7fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be",
        now=now,
    )
    assert first.outcome == second.outcome == "REUSABLE"
    assert first.action.status == second.action.status == "ACTIVE"

    with pytest.raises(ActionExpiredError):
        repository.begin_consumption(
            db_session,
            public_id=expired.public_id,
            team_id=1,
            user_id=2,
            session_id=message.session_id,
            client_request_id="8fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be",
            now=now,
        )

    other_session = AgentSession(session_key="agent-session-team-2", team_id=2, user_id=3)
    db_session.add(other_session)
    db_session.flush()
    other_message = AgentMessage(
        team_id=2,
        user_id=3,
        session_id=other_session.id,
        role=AgentMessageRole.ASSISTANT,
        content="其他团队消息",
    )
    db_session.add(other_message)
    db_session.flush()
    other_action = repository.register(
        db_session,
        AgentUIActionRegistration(
            public_id="act_retry_team_2",
            team_id=2,
            user_id=3,
            session_id=other_session.id,
            message_id=other_message.id,
            action_type="retry",
            root_context_role="PROJECTION_ONLY",
            target={"turn_id": "turn_team_2"},
            consumption_mode="ONE_SHOT",
            expires_at=now - timedelta(seconds=1),
        ),
        now=now,
    )
    with pytest.raises(ActionExpiredError):
        repository.begin_consumption(
            db_session,
            public_id=other_action.public_id,
            team_id=2,
            user_id=3,
            session_id=other_session.id,
            client_request_id="9fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be",
            now=now,
        )

    assert repository.purge_terminal(db_session, team_id=1, now=now + timedelta(days=31)) == 1
    assert db_session.query(AgentUIAction).filter(AgentUIAction.team_id == 2).count() == 1


def test_ui_action_repository_revokes_only_actions_for_confirmation_case(db_session) -> None:
    from app.schemas.agent_persistence import AgentUIActionRegistration
    from app.services.agent.ui.actions import AgentUIActionRepository

    message = _seed_message(db_session)
    repository = AgentUIActionRepository()
    now = datetime(2026, 8, 21, 10, 0, 0)
    case_action = repository.register(
        db_session,
        AgentUIActionRegistration(
            public_id="act_case_projection_1",
            team_id=1,
            user_id=2,
            session_id=message.session_id,
            message_id=message.id,
            action_type="submit_interaction",
            root_context_role="PENDING_CASE",
            target={"follow_up_confirmation_case_public_id": "fuc_target"},
            consumption_mode="ONE_SHOT",
        ),
        now=now,
    )
    unrelated_action = repository.register(
        db_session,
        AgentUIActionRegistration(
            public_id="act_case_projection_2",
            team_id=1,
            user_id=2,
            session_id=message.session_id,
            message_id=message.id,
            action_type="submit_interaction",
            root_context_role="PENDING_CASE",
            target={"follow_up_confirmation_case_public_id": "fuc_other"},
            consumption_mode="ONE_SHOT",
        ),
        now=now,
    )
    db_session.commit()

    assert (
        repository.revoke_for_follow_up_confirmation_case(
            db_session,
            team_id=1,
            case_public_id="fuc_target",
            reason="SOURCE_ACTIVITY_REVISION_SUPERSEDED",
            now=now,
        )
        == 1
    )
    db_session.commit()

    assert db_session.query(AgentUIAction).filter_by(public_id=case_action.public_id).one().status == "REVOKED"
    assert db_session.query(AgentUIAction).filter_by(public_id=unrelated_action.public_id).one().status == "ACTIVE"


def test_result_set_contract_uses_one_based_inclusive_ranges() -> None:
    from pydantic import ValidationError

    message = type("MessageRef", (), {"session_id": 1, "id": 1})()
    request = _result_set_create(message)

    assert request.page.range_start == 1
    assert request.page.range_end == 2

    with pytest.raises(ValidationError, match="one-based inclusive range"):
        request.model_copy(
            update={"page": AgentResultPage(page_size=20, range_start=1, range_end=1, total=2)}
        ).model_validate(
            request.model_copy(
                update={"page": AgentResultPage(page_size=20, range_start=1, range_end=1, total=2)}
            ).model_dump()
        )


def _message_body(text: str):
    from app.schemas.agent_persistence import AgentUIMessageBody

    return AgentUIMessageBody(
        state="final",
        blocks=[{"id": "b_text", "type": "text", "format": "plain", "text": text}],
        metadata={},
    )


def test_turn_repository_replays_request_and_rejects_changed_input(db_session) -> None:
    from app.schemas.agent_persistence import AgentTurnStart
    from app.services.agent.turns import AgentTurnIdempotencyConflictError, AgentTurnRepository

    message = _seed_message(db_session)
    repository = AgentTurnRepository()
    request = AgentTurnStart(
        team_id=1,
        user_id=2,
        session_id=message.session_id,
        client_request_id="6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be",
        input_fingerprint="a" * 64,
        content="我在上海有哪些客户",
        ui=_message_body("我在上海有哪些客户"),
    )

    created = repository.begin(db_session, request)
    db_session.commit()
    replayed = repository.begin(db_session, request)

    assert created.outcome == "CREATED"
    assert replayed.outcome == "IN_PROGRESS"
    assert replayed.user_message == created.user_message
    assert created.user_message.turn_id.startswith("turn_")
    assert created.user_message.ui.message_id == created.user_message.id

    with pytest.raises(AgentTurnIdempotencyConflictError):
        repository.begin(
            db_session,
            request.model_copy(
                update={
                    "content": "我在北京有哪些客户",
                    "ui": _message_body("我在北京有哪些客户"),
                }
            ),
        )

    with pytest.raises(AgentTurnIdempotencyConflictError):
        repository.begin(
            db_session,
            request.model_copy(update={"input_fingerprint": "b" * 64}),
        )


def test_turn_repository_completes_once_and_returns_final_on_request_replay(db_session) -> None:
    from app.schemas.agent_persistence import AgentAssistantMessageCreate, AgentTurnStart
    from app.services.agent.turns import AgentTurnIdempotencyConflictError, AgentTurnRepository

    message = _seed_message(db_session)
    repository = AgentTurnRepository()
    started = repository.begin(
        db_session,
        AgentTurnStart(
            team_id=1,
            user_id=2,
            session_id=message.session_id,
            client_request_id="6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be",
            input_fingerprint="a" * 64,
            content="我在上海有哪些客户",
            ui=_message_body("我在上海有哪些客户"),
        ),
    )
    db_session.commit()
    completion = AgentAssistantMessageCreate(
        team_id=1,
        user_id=2,
        session_id=message.session_id,
        turn_id=started.user_message.turn_id,
        content="共找到 2 个客户",
        ui=_message_body("共找到 2 个客户"),
        diagnostics={"route": "QUERY"},
    )

    created = repository.complete(db_session, completion)
    db_session.commit()
    replayed = repository.complete(db_session, completion)
    resumed = repository.begin(
        db_session,
        AgentTurnStart(
            team_id=1,
            user_id=2,
            session_id=message.session_id,
            client_request_id="6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be",
            input_fingerprint="a" * 64,
            content="我在上海有哪些客户",
            ui=_message_body("我在上海有哪些客户"),
        ),
    )

    assert created.outcome == "CREATED"
    assert replayed.outcome == "REPLAY"
    assert replayed.message == created.message
    assert resumed.outcome == "COMPLETED"
    assert resumed.assistant_message == created.message

    with pytest.raises(AgentTurnIdempotencyConflictError):
        repository.complete(
            db_session,
            completion.model_copy(update={"content": "不同输出", "ui": _message_body("不同输出")}),
        )


def test_result_set_repository_loads_only_latest_active_owned_snapshot(db_session) -> None:
    message = _seed_message(db_session)
    now = datetime(2026, 8, 23, 10, 0, 0)
    repository = AgentQueryResultSetRepository()
    expired = repository.create(
        db_session,
        _result_set_create(message).model_copy(
            update={
                "public_id": "rs_expired_latest_candidate",
                "expires_at": now - timedelta(seconds=1),
            }
        ),
        now=now - timedelta(minutes=2),
    )
    active = repository.create(
        db_session,
        _result_set_create(message).model_copy(
            update={"public_id": "rs_latest_active"}
        ),
        now=now - timedelta(minutes=1),
    )
    foreign_session = AgentSession(session_key="agent-session-foreign-latest", team_id=1, user_id=99)
    db_session.add(foreign_session)
    db_session.flush()
    foreign_message = AgentMessage(
        team_id=1,
        user_id=99,
        session_id=foreign_session.id,
        role=AgentMessageRole.ASSISTANT,
        content="其他用户客户列表",
    )
    db_session.add(foreign_message)
    db_session.flush()
    repository.create(
        db_session,
        _result_set_create(foreign_message).model_copy(
            update={
                "public_id": "rs_foreign_newer",
                "user_id": 99,
                "session_id": foreign_session.id,
                "source_message_id": foreign_message.id,
            }
        ),
        now=now,
    )
    db_session.commit()

    loaded = repository.get_latest_active(
        db_session,
        team_id=1,
        user_id=2,
        session_id=message.session_id,
        now=now,
    )

    assert loaded == active
    assert loaded != expired
    assert (
        repository.get_latest_active(
            db_session,
            team_id=1,
            user_id=2,
            session_id=999,
            now=now,
        )
        is None
    )


def test_visible_history_normalizes_legacy_follow_up_confirmation_prompt_without_rewriting_storage(db_session) -> None:
    from app.schemas.agent_persistence import AgentUIMessageBody
    from app.services.agent.turns import AgentTurnRepository
    from app.services.agent.ui.schemas import AgentUIMetadata, InteractionBlock, InteractionOption

    session = AgentSession(session_key="legacy-confirmation-history", team_id=1, user_id=2)
    db_session.add(session)
    db_session.flush()
    old_prompt = "9 月 9 号待办的「确认技术评估结论」现在完成了吗?"
    envelope = AgentUIMessageBody(
        state="final",
        blocks=[
            InteractionBlock(
                id="b_legacy_confirmation",
                type="interaction",
                interaction_id="int_legacy_confirmation",
                interaction_type="choice",
                presentation="COMPACT_TASK_COMPLETION",
                state="ACTIVE",
                prompt=old_prompt,
                options=[InteractionOption(value="已完成", label="标记完成")],
                selection_mode="single",
                min_selections=1,
                max_selections=1,
                submit_on_select=True,
                submit_action_id="act_legacy_confirmation",
            )
        ],
        suggested_actions=[],
        metadata=AgentUIMetadata(route="WORKFLOW"),
    )
    message = AgentMessage(
        team_id=1,
        user_id=2,
        session_id=session.id,
        role=AgentMessageRole.ASSISTANT,
        content=old_prompt,
        turn_id="turn_legacy_confirmation",
        ui_json={
            "schema_version": "crm.agent.ui.v1",
            "message_id": 1,
            "turn_id": "turn_legacy_confirmation",
            "role": "assistant",
            **envelope.model_dump(mode="json"),
        },
        created_time=datetime(2026, 9, 3, 10),
        last_modified_time=datetime(2026, 9, 3, 10),
    )
    db_session.add(message)
    db_session.commit()

    records, total = AgentTurnRepository().list_visible_by_session(
        db_session,
        session_id=session.id,
        team_id=1,
        user_id=2,
    )

    assert total == 1
    assert records[0].ui.blocks[0].prompt == old_prompt
    db_session.refresh(message)
    assert message.ui_json["blocks"][0]["prompt"] == old_prompt

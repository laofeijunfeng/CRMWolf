"""Deterministic historical-message migration for the one-version Agent cutover."""

import hashlib
import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.agent import AgentMessage, AgentMessageRole, AgentSession
from app.services.agent.message_migration import AgentMessageMigrationError, AgentMessageMigrationService
from app.services.agent.ui.schemas import AgentUIEnvelope


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def migration_db():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[AgentSession.__table__, AgentMessage.__table__])
    session_factory = sessionmaker(bind=engine)
    try:
        yield engine, session_factory
    finally:
        engine.dispose()


def test_message_migration_backfills_plain_text_turn_and_diagnostics(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 9, 30, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-1", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="我在上海有哪些客户",
            payload_json=None,
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        assistant_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.ASSISTANT,
            event_type="assistant_message",
            content="找到 2 个客户",
            payload_json={
                "source": "root_runtime",
                "for_user_message_id": user_message.id,
                "trace_events": [{"event": "tool_result", "tool_name": "list_customers"}],
                "content_format": "text",
                "turn_observability": {"schema_version": "agent.turn_observability.v1"},
            },
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(assistant_message)

    result = AgentMessageMigrationService(engine).migrate_batch(after_id=0, batch_size=1000)

    assert result.source_row_count == 2
    assert result.target_row_count == 2
    assert result.schema_validated_count == 2
    assert result.migrated_row_count == 2
    assert result.last_id == 2
    assert result.has_more is False
    assert len(result.source_payload_checksum) == 64
    assert len(result.target_ui_checksum) == 64

    with session_factory() as db:
        rows = db.query(AgentMessage).order_by(AgentMessage.id).all()
        user_row, assistant_row = rows
        assert user_row.turn_id == "turn_legacy_1"
        assert assistant_row.turn_id == user_row.turn_id
        assert user_row.content == "我在上海有哪些客户"
        assert assistant_row.content == "找到 2 个客户"
        assert user_row.diagnostics_json is None
        assert assistant_row.diagnostics_json == {
            "migration_source": "root_runtime",
            "runtime_events": [{"event": "tool_result", "tool_name": "list_customers"}],
            "turn_observability": {"schema_version": "agent.turn_observability.v1"},
        }

        user_ui = AgentUIEnvelope.model_validate(user_row.ui_json)
        assistant_ui = AgentUIEnvelope.model_validate(assistant_row.ui_json)
        assert user_ui.turn_id == user_row.turn_id
        assert user_ui.role == "user"
        assert user_ui.state == "final"
        assert user_ui.blocks[0].model_dump() == {
            "id": "b_text_1",
            "type": "text",
            "format": "plain",
            "text": "我在上海有哪些客户",
        }
        assert assistant_ui.turn_id == user_row.turn_id
        assert assistant_ui.role == "assistant"
        assert assistant_ui.blocks[0].model_dump() == {
            "id": "b_text_1",
            "type": "text",
            "format": "plain",
            "text": "找到 2 个客户",
        }


def test_message_migration_projects_markdown_content_without_changing_the_ui_block(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 10, 0, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-markdown", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="列出客户",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="**上海客户**\n- [甲公司](https://crm.example/customers/1)\n- `乙公司`",
                payload_json={
                    "source": "root_runtime",
                    "for_user_message_id": user_message.id,
                    "trace_events": [],
                    "content_format": "markdown",
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        assistant = db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).one()
        assert assistant.content == "上海客户\n甲公司\n乙公司"
        envelope = AgentUIEnvelope.model_validate(assistant.ui_json)
        assert envelope.metadata.accessibility_label == assistant.content
        assert envelope.blocks[0].model_dump() == {
            "id": "b_text_1",
            "type": "text",
            "format": "markdown",
            "text": "**上海客户**\n- [甲公司](https://crm.example/customers/1)\n- `乙公司`",
        }


def test_message_migration_is_idempotent_for_already_migrated_markdown(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 11, 0, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-idempotent", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="列出客户",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="**上海客户**",
                payload_json={
                    "source": "root_runtime",
                    "for_user_message_id": user_message.id,
                    "trace_events": [],
                    "content_format": "markdown",
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    first = AgentMessageMigrationService(engine).migrate_batch()
    with session_factory() as db:
        first_snapshot = [
            (row.turn_id, row.content, row.ui_json, row.diagnostics_json)
            for row in db.query(AgentMessage).order_by(AgentMessage.id)
        ]

    second = AgentMessageMigrationService(engine).migrate_batch()
    with session_factory() as db:
        second_snapshot = [
            (row.turn_id, row.content, row.ui_json, row.diagnostics_json)
            for row in db.query(AgentMessage).order_by(AgentMessage.id)
        ]

    assert first.migrated_row_count == 2
    assert second.migrated_row_count == 0
    assert second.source_payload_checksum == first.source_payload_checksum
    assert second.target_ui_checksum == first.target_ui_checksum
    assert second_snapshot == first_snapshot


def test_message_migration_rolls_back_the_entire_batch_for_unknown_payload(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 12, 0, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-invalid", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="查询客户",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="不能迁移",
                payload_json={"unknown_private_key": "sensitive"},
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    with pytest.raises(RuntimeError, match="unknown payload shape"):
        AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        rows = db.query(AgentMessage).order_by(AgentMessage.id).all()
        assert all(row.turn_id is None for row in rows)
        assert all(row.ui_json is None for row in rows)
        assert all(row.diagnostics_json is None for row in rows)
        assert rows[0].content == "查询客户"


def test_message_migration_pairs_source_only_assistant_with_the_nearest_prior_user(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 13, 0, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-source-only", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="查询客户",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        assistant_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.ASSISTANT,
            event_type="assistant_message",
            content="查询完成",
            payload_json={"source": "legacy_root"},
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(assistant_message)

    AgentMessageMigrationService(engine).migrate_batch(after_id=0, batch_size=1)
    second_batch = AgentMessageMigrationService(engine).migrate_batch(after_id=1, batch_size=1)

    assert second_batch.source_row_count == 1
    with session_factory() as db:
        user_row, assistant_row = db.query(AgentMessage).order_by(AgentMessage.id).all()
        assert assistant_row.turn_id == user_row.turn_id == "turn_legacy_1"


def test_message_migration_normalizes_legacy_markdown_outside_the_target_dialect(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 14, 0, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-wide-markdown", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="总结客户",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="### 上海客户\n> 重点名单\n<script>ignored()</script>\n- [x] 已联系",
                payload_json={
                    "source": "legacy_read_presenter",
                    "for_user_message_id": user_message.id,
                    "trace_events": [],
                    "content_format": "markdown",
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        assistant = db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).one()
        assert assistant.content == "上海客户\n重点名单\nignored()\n已联系"
        envelope = AgentUIEnvelope.model_validate(assistant.ui_json)
        assert envelope.blocks[0].format == "markdown"
        assert envelope.blocks[0].text == assistant.content


@pytest.mark.parametrize(
    ("role", "event_type"),
    [
        (AgentMessageRole.USER, "assistant_message"),
        (AgentMessageRole.ASSISTANT, "user_message"),
    ],
)
def test_message_migration_rejects_role_event_type_mismatch_atomically(
    migration_db,
    role: str,
    event_type: str,
) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 15, 0, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key=f"legacy-session-mismatch-{role}", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=role,
                event_type=event_type,
                content="不应迁移",
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    with pytest.raises(RuntimeError, match="event type does not match role"):
        AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        row = db.query(AgentMessage).one()
        assert row.turn_id is None
        assert row.ui_json is None


def test_message_migration_rejects_message_owner_mismatched_with_session(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 15, 15, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-owner-mismatch", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add(
            AgentMessage(
                team_id=9,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.USER,
                event_type="user_message",
                content="不应跨团队迁移",
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    with pytest.raises(RuntimeError, match="owner does not match its session"):
        AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        row = db.query(AgentMessage).one()
        assert row.turn_id is None
        assert row.ui_json is None


def test_message_migration_rejects_assistant_lineage_to_a_later_user_message(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 15, 30, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-future-lineage", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        assistant = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.ASSISTANT,
            event_type="assistant_message",
            content="不应绑定未来消息",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(assistant)
        db.flush()
        future_user = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="未来用户消息",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(future_user)
        db.flush()
        assistant.payload_json = {
            "source": "legacy_root",
            "for_user_message_id": future_user.id,
            "trace_events": [],
            "content_format": "text",
        }

    with pytest.raises(RuntimeError, match="invalid user-message lineage"):
        AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        rows = db.query(AgentMessage).order_by(AgentMessage.id).all()
        assert all(row.turn_id is None for row in rows)
        assert all(row.ui_json is None for row in rows)


def test_message_migration_rejects_source_only_assistant_without_a_prior_user(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 16, 0, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-orphan", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="孤立回复",
                payload_json={"source": "legacy_root"},
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    with pytest.raises(RuntimeError, match="missing its user-message lineage"):
        AgentMessageMigrationService(engine).migrate_batch()


def test_message_migration_rejects_two_source_only_assistants_for_one_user_turn(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 16, 30, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-ambiguous", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.USER,
                event_type="user_message",
                content="执行操作",
                created_time=created_at,
                last_modified_time=created_at,
            )
        )
        db.add_all(
            [
                AgentMessage(
                    team_id=1,
                    user_id=2,
                    session_id=session.id,
                    role=AgentMessageRole.ASSISTANT,
                    event_type="assistant_message",
                    content=content,
                    payload_json={"source": "legacy_root"},
                    created_time=created_at,
                    last_modified_time=created_at,
                )
                for content in ("第一条回复", "第二条回复")
            ]
        )

    with pytest.raises(RuntimeError, match="ambiguous user-message lineage"):
        AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        rows = db.query(AgentMessage).order_by(AgentMessage.id).all()
        assert all(row.turn_id is None for row in rows)
        assert all(row.ui_json is None for row in rows)


def test_message_migration_reports_resume_cursor_and_empty_batch(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 17, 0, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-batches", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add_all(
            [
                AgentMessage(
                    team_id=1,
                    user_id=2,
                    session_id=session.id,
                    role=AgentMessageRole.USER,
                    event_type="user_message",
                    content=content,
                    created_time=created_at,
                    last_modified_time=created_at,
                )
                for content in ("第一轮", "第二轮")
            ]
        )

    first = AgentMessageMigrationService(engine).migrate_batch(batch_size=1)
    second = AgentMessageMigrationService(engine).migrate_batch(after_id=first.last_id or 0, batch_size=1)
    empty = AgentMessageMigrationService(engine).migrate_batch(after_id=second.last_id or 0, batch_size=1)

    assert first.last_id == 1
    assert first.has_more is True
    assert second.last_id == 2
    assert second.has_more is False
    assert empty.after_id == 2
    assert empty.last_id is None
    assert empty.source_row_count == 0
    assert empty.target_row_count == 0
    assert empty.migrated_row_count == 0
    assert empty.schema_validated_count == 0
    assert empty.has_more is False


def test_message_migration_preserves_recovery_diagnostics_without_exposing_them_in_ui(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 18, 0, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-recovery", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="恢复任务",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="任务已恢复",
                payload_json={
                    "source": "runtime_recovery",
                    "recovered_for_user_message_id": user_message.id,
                    "trace_events": [],
                    "content_format": "text",
                    "reason": "recovered",
                    "recovery_status": "completed",
                    "related_task_id": 2,
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        assistant = db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).one()
        assert assistant.diagnostics_json == {
            "migration_source": "runtime_recovery",
            "runtime_events": [],
            "recovery": {
                "reason": "recovered",
                "recovery_status": "completed",
                "related_task_id": 2,
            },
        }
        envelope = AgentUIEnvelope.model_validate(assistant.ui_json)
        assert envelope.blocks[0].text == "任务已恢复"
        assert "recovery" not in envelope.model_dump_json()


def test_message_migration_projects_historical_choice_interaction_as_read_only(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 19, 0, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-choice-interaction", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="选择客户",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="请选择客户。",
                payload_json={
                    "source": "legacy_root",
                    "for_user_message_id": user_message.id,
                    "trace_events": [
                        {
                            "event": "customer_selection_required",
                            "interaction": {
                                "schema_version": "agent.interaction.v1",
                                "interaction_id": "int_customer_legacy_1",
                                "type": "choice",
                                "status": "waiting_user_input",
                                "prompt": "请选择客户。",
                                "selection_mode": "single",
                                "min_selections": 1,
                                "max_selections": 1,
                                "choices": [
                                    {
                                        "value": "cus_1",
                                        "label": "上海睿狐",
                                        "description": "上海客户",
                                    }
                                ],
                            },
                        }
                    ],
                    "content_format": "text",
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        assistant = db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).one()
        assert assistant.content == "请选择客户。\n历史交互状态: 等待用户输入"
        envelope = AgentUIEnvelope.model_validate(assistant.ui_json)
        assert [block.type for block in envelope.blocks] == ["text", "interaction"]
        interaction = envelope.blocks[1]
        assert interaction.type == "interaction"
        assert interaction.interaction_id == "int_customer_legacy_1"
        assert interaction.interaction_type == "choice"
        assert interaction.state == "READ_ONLY"
        assert interaction.submit_action_id is None
        assert interaction.options[0].model_dump() == {
            "value": "cus_1",
            "label": "上海睿狐",
            "description": "上海客户",
            "disabled": False,
        }
        assert envelope.suggested_actions == []


def test_message_migration_defaults_legacy_choice_card_to_single_selection(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 19, 30, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-choice-defaults", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="确认执行",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="确认后执行。",
                payload_json={
                    "source": "legacy_root",
                    "for_user_message_id": user_message.id,
                    "trace_events": [
                        {
                            "event": "confirmation_required",
                            "interaction": {
                                "schema_version": "agent.interaction.v1",
                                "interaction_id": "int_legacy_confirmation",
                                "type": "choice",
                                "status": "waiting_confirmation",
                                "prompt": "确认后执行。",
                                "choices": [
                                    {"value": "是", "label": "是"},
                                    {"value": "否", "label": "否"},
                                ],
                            },
                        }
                    ],
                    "content_format": "text",
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        assistant = db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).one()
        envelope = AgentUIEnvelope.model_validate(assistant.ui_json)
        interaction = envelope.blocks[1]
        assert interaction.selection_mode == "single"
        assert interaction.min_selections == 1
        assert interaction.max_selections == 1


def test_message_migration_disambiguates_duplicate_legacy_choice_values_with_task_evidence(
    migration_db,
) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 19, 45, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-duplicate-choice-values", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="继续草稿",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="请选择草稿。",
                payload_json={
                    "source": "legacy_root",
                    "for_user_message_id": user_message.id,
                    "trace_events": [
                        {
                            "event": "suspended_task_selection_required",
                            "interaction": {
                                "schema_version": "agent.interaction.v1",
                                "interaction_id": "int_legacy_duplicate_choices",
                                "type": "choice",
                                "status": "waiting_user_input",
                                "prompt": "请选择草稿。",
                                "choices": [
                                    {
                                        "value": "继续草稿",
                                        "label": "商机草稿",
                                        "metadata": {"selected_task_id": 47},
                                    },
                                    {
                                        "value": "继续草稿",
                                        "label": "商机草稿",
                                        "metadata": {"selected_task_id": 45},
                                    },
                                ],
                            },
                        }
                    ],
                    "content_format": "text",
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        assistant = db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).one()
        envelope = AgentUIEnvelope.model_validate(assistant.ui_json)
        interaction = envelope.blocks[1]
        assert [option.value for option in interaction.options] == [
            "legacy_task_47",
            "legacy_task_45",
        ]
        assert [option.description for option in interaction.options] == [
            "历史任务 ID: 47",
            "历史任务 ID: 45",
        ]


def test_message_migration_projects_historical_task_result_as_action_result(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 20, 0, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-action-result", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="创建部署信息",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="操作已处理。",
                payload_json={
                    "source": "legacy_root",
                    "for_user_message_id": user_message.id,
                    "trace_events": [
                        {
                            "event": "tool_result",
                            "tool_name": "create_deployment_info",
                            "success": True,
                            "data": {"deployment_id": 9001},
                        },
                        {"event": "task_completed", "task_id": 17, "content": "部署信息已创建。"},
                    ],
                    "content_format": "text",
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        assistant = db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).one()
        assert assistant.content == "操作已处理。\n部署信息已创建。"
        envelope = AgentUIEnvelope.model_validate(assistant.ui_json)
        assert [block.type for block in envelope.blocks] == ["text", "action_result"]
        result = envelope.blocks[1]
        assert result.type == "action_result"
        assert result.action_id == f"legacy_action_{assistant.id}"
        assert result.status == "SUCCESS"
        assert result.title == "操作已完成"
        assert result.message == "部署信息已创建。"
        assert "deployment_id" not in envelope.model_dump_json()


def test_message_migration_projects_historical_form_interaction_as_read_only(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 20, 30, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-form-interaction", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="创建商机",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="请补充商机信息。",
                payload_json={
                    "source": "legacy_root",
                    "for_user_message_id": user_message.id,
                    "trace_events": [
                        {
                            "event": "opportunity_fields_required",
                            "interaction": {
                                "schema_version": "agent.interaction.v1",
                                "interaction_id": "int_opportunity_legacy_1",
                                "type": "form",
                                "status": "waiting_user_input",
                                "prompt": "请补充商机信息。",
                                "fields": [
                                    {
                                        "key": "total_amount",
                                        "label": "预计金额",
                                        "type": "number",
                                        "required": True,
                                    }
                                ],
                            },
                        }
                    ],
                    "content_format": "text",
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        assistant = db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).one()
        envelope = AgentUIEnvelope.model_validate(assistant.ui_json)
        interaction = envelope.blocks[1]
        assert interaction.type == "interaction"
        assert interaction.interaction_type == "form"
        assert interaction.state == "READ_ONLY"
        assert interaction.submit_action_id is None
        assert interaction.fields[0].key == "total_amount"
        assert interaction.fields[0].field_type == "number"
        assert interaction.fields[0].minimum == -1_000_000_000
        assert interaction.fields[0].maximum == 1_000_000_000


def test_message_migration_projects_historical_text_interaction_as_read_only(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 21, 0, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-text-interaction", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="记录跟进",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="请补充跟进背景。",
                payload_json={
                    "source": "legacy_root",
                    "for_user_message_id": user_message.id,
                    "trace_events": [
                        {
                            "event": "follow_up_quality_required",
                            "interaction": {
                                "schema_version": "agent.interaction.v1",
                                "interaction_id": "int_follow_up_legacy_1",
                                "type": "text",
                                "status": "waiting_user_input",
                                "prompt": "请补充跟进背景。",
                                "placeholder": "补充下一步动作",
                                "allow_free_text": False,
                            },
                        }
                    ],
                    "content_format": "text",
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        assistant = db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).one()
        envelope = AgentUIEnvelope.model_validate(assistant.ui_json)
        interaction = envelope.blocks[1]
        assert interaction.type == "interaction"
        assert interaction.interaction_type == "text_input"
        assert interaction.state == "READ_ONLY"
        assert interaction.submit_action_id is None
        assert interaction.allow_blank is False
        assert interaction.fields[0].required is True
        assert interaction.fields[0].min_length == 1
        assert interaction.fields[0].placeholder == "补充下一步动作"


@pytest.mark.parametrize(
    ("event", "expected_status", "expected_title", "expected_message"),
    [
        (
            {"event": "action_completed", "action_id": "act_legacy_1", "action_type": "create_customer"},
            "SUCCESS",
            "操作已完成",
            "客户已创建。",
        ),
        (
            {
                "event": "action_failed",
                "action_id": "act_legacy_2",
                "action_type": "create_customer",
                "reason": "database password leaked only to diagnostics",
            },
            "FAILED",
            "操作未完成",
            "客户创建失败，请稍后重试。",  # noqa: RUF001
        ),
        (
            {"event": "task_failed", "task_id": 18, "content": "跟进记录创建失败。", "reason": "internal"},
            "FAILED",
            "操作未完成",
            "跟进记录创建失败。",
        ),
        (
            {"event": "task_cancelled", "task_id": 19, "content": "已取消创建跟进记录。"},
            "CANCELLED",
            "操作已取消",
            "已取消创建跟进记录。",
        ),
    ],
)
def test_message_migration_projects_all_historical_action_outcomes_without_exposing_internal_data(
    migration_db,
    event: dict[str, object],
    expected_status: str,
    expected_title: str,
    expected_message: str,
) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 21, 30, 0)
    assistant_content = {
        "action_completed": "客户已创建。",
        "action_failed": "客户创建失败，请稍后重试。",  # noqa: RUF001
        "task_failed": "操作未完成。",
        "task_cancelled": "操作已取消。",
    }[str(event["event"])]
    with session_factory.begin() as db:
        session = AgentSession(
            session_key=f"legacy-session-{event['event']}",
            team_id=1,
            user_id=2,
        )
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="执行操作",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content=assistant_content,
                payload_json={
                    "source": "legacy_root",
                    "for_user_message_id": user_message.id,
                    "trace_events": [
                        {
                            "event": "tool_result",
                            "success": expected_status == "SUCCESS",
                            "data": {"secret": "must-not-enter-agent-ui"},
                        },
                        event,
                    ],
                    "content_format": "text",
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        assistant = db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).one()
        envelope = AgentUIEnvelope.model_validate(assistant.ui_json)
        result = envelope.blocks[1]
        assert result.type == "action_result"
        assert result.status == expected_status
        assert result.title == expected_title
        assert result.message == expected_message
        assert "must-not-enter-agent-ui" not in envelope.model_dump_json()
        assert "database password" not in envelope.model_dump_json()


def test_message_migration_rejects_oversized_action_result_instead_of_truncating(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 21, 1, 50, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-action-result-too-long", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="执行任务",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="任务已完成",
                payload_json={
                    "source": "legacy_root",
                    "for_user_message_id": user_message.id,
                    "trace_events": [{"event": "task_completed", "content": "长" * 10001}],
                    "content_format": "text",
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    with pytest.raises(AgentMessageMigrationError, match="action result exceeds target limits"):
        AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        rows = db.query(AgentMessage).order_by(AgentMessage.id).all()
        assert all(row.ui_json is None for row in rows)


def test_message_migration_preserves_unknown_non_string_trace_event_only_in_diagnostics(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 22, 0, 0)
    unknown_event = {"event": {"kind": "future_event"}, "data": ["internal"]}
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-unknown-event", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="查询状态",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="当前没有可展示的操作结果。",
                payload_json={
                    "source": "legacy_root",
                    "for_user_message_id": user_message.id,
                    "trace_events": [unknown_event],
                    "content_format": "text",
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        assistant = db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).one()
        envelope = AgentUIEnvelope.model_validate(assistant.ui_json)
        assert [block.type for block in envelope.blocks] == ["text"]
        assert assistant.diagnostics_json == {
            "migration_source": "legacy_root",
            "runtime_events": [unknown_event],
        }


def test_message_migration_rejects_falsy_explicit_user_lineage_instead_of_inferring_it(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 20, 23, 30, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-falsy-lineage", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.USER,
                event_type="user_message",
                content="执行操作",
                created_time=created_at,
                last_modified_time=created_at,
            )
        )
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="不应自动绑定",
                payload_json={
                    "source": "legacy_root",
                    "for_user_message_id": 0,
                    "trace_events": [],
                    "content_format": "text",
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    with pytest.raises(RuntimeError, match="invalid user-message lineage"):
        AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        rows = db.query(AgentMessage).order_by(AgentMessage.id).all()
        assert all(row.ui_json is None for row in rows)


def test_message_migration_rejects_existing_target_diagnostics_that_do_not_match_an_empty_payload(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 21, 0, 0, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-target-diagnostics", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.USER,
                event_type="user_message",
                content="查询客户",
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    AgentMessageMigrationService(engine).migrate_batch()
    with session_factory.begin() as db:
        row = db.query(AgentMessage).one()
        row.diagnostics_json = {"unexpected": "must fail closed"}

    with pytest.raises(RuntimeError, match="target diagnostics do not match"):
        AgentMessageMigrationService(engine).migrate_batch()


def test_message_migration_rejects_existing_target_content_that_disagrees_with_accessibility(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 21, 0, 15, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-target-content", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.USER,
                event_type="user_message",
                content="查询客户",
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    AgentMessageMigrationService(engine).migrate_batch()
    with session_factory.begin() as db:
        row = db.query(AgentMessage).one()
        row.content = "被篡改的搜索投影"

    with pytest.raises(RuntimeError, match="target content does not match accessibility"):
        AgentMessageMigrationService(engine).migrate_batch()


def test_message_migration_rejects_existing_target_with_extra_user_visible_blocks(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 21, 0, 20, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-target-extra-block", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.USER,
                event_type="user_message",
                content="查询客户",
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    AgentMessageMigrationService(engine).migrate_batch()
    with session_factory.begin() as db:
        row = db.query(AgentMessage).one()
        tampered_ui = dict(row.ui_json)
        tampered_ui["blocks"] = [
            *tampered_ui["blocks"],
            {"id": "b_injected", "type": "text", "format": "plain", "text": "额外内容"},
        ]
        row.ui_json = tampered_ui

    with pytest.raises(RuntimeError, match="target blocks do not match deterministic projection"):
        AgentMessageMigrationService(engine).migrate_batch()


def test_message_migration_rejects_existing_target_with_coordinated_turn_id_tampering(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 21, 0, 25, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-target-turn-tamper", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.USER,
                event_type="user_message",
                content="查询客户",
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    AgentMessageMigrationService(engine).migrate_batch()
    with session_factory.begin() as db:
        row = db.query(AgentMessage).one()
        tampered_ui = dict(row.ui_json)
        tampered_ui["turn_id"] = "turn_tampered"
        row.turn_id = "turn_tampered"
        row.ui_json = tampered_ui

    with pytest.raises(RuntimeError, match="target identity does not match"):
        AgentMessageMigrationService(engine).migrate_batch()


def test_message_migration_rejects_structured_assistant_without_explicit_lineage(
    migration_db,
) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 21, 0, 30, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-structured-no-lineage", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.USER,
                event_type="user_message",
                content="查询客户",
                created_time=created_at,
                last_modified_time=created_at,
            )
        )
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="查询完成",
                payload_json={
                    "source": "legacy_root",
                    "trace_events": [],
                    "content_format": "text",
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    with pytest.raises(RuntimeError, match="missing explicit user-message lineage"):
        AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        rows = db.query(AgentMessage).order_by(AgentMessage.id).all()
        assert all(row.turn_id is None for row in rows)
        assert all(row.ui_json is None for row in rows)


def test_message_migration_rejects_overlapping_legacy_requests_without_lineage(
    migration_db,
) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 21, 0, 31, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-overlapping-requests", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add_all(
            [
                AgentMessage(
                    team_id=1,
                    user_id=2,
                    session_id=session.id,
                    role=role,
                    event_type="user_message" if role == AgentMessageRole.USER else "assistant_message",
                    content=content,
                    payload_json=None if role == AgentMessageRole.USER else {"source": "legacy_root"},
                    created_time=created_at,
                    last_modified_time=created_at,
                )
                for role, content in (
                    (AgentMessageRole.USER, "第一次请求"),
                    (AgentMessageRole.USER, "第二次请求"),
                    (AgentMessageRole.ASSISTANT, "第一次回复"),
                    (AgentMessageRole.ASSISTANT, "第二次回复"),
                )
            ]
        )

    with pytest.raises(RuntimeError, match="ambiguous user-message lineage"):
        AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        rows = db.query(AgentMessage).order_by(AgentMessage.id).all()
        assert all(row.turn_id is None for row in rows)
        assert all(row.ui_json is None for row in rows)


def test_message_migration_uses_historical_interaction_prompt_for_search_content(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 21, 1, 0, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-interaction-prompt", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="选择客户",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="请选择一个选项。",
                payload_json={
                    "source": "legacy_root",
                    "for_user_message_id": user_message.id,
                    "trace_events": [
                        {
                            "event": "customer_selection_required",
                            "interaction": {
                                "schema_version": "agent.interaction.v1",
                                "interaction_id": "int_prompt_projection",
                                "type": "choice",
                                "status": "waiting_user_input",
                                "prompt": "请选择需要继续跟进的客户。",
                                "selection_mode": "single",
                                "min_selections": 1,
                                "max_selections": 1,
                                "choices": [{"value": "cus_1", "label": "上海睿狐"}],
                            },
                        }
                    ],
                    "content_format": "text",
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        assistant = db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).one()
        assert assistant.content == "请选择需要继续跟进的客户。\n历史交互状态: 等待用户输入"
        envelope = AgentUIEnvelope.model_validate(assistant.ui_json)
        assert envelope.blocks[0].text == "请选择一个选项。"
        assert envelope.metadata.accessibility_label == assistant.content


@pytest.mark.parametrize(
    "trace_events",
    [
        {"event": "not-a-list"},
        [
            {
                "event": "customer_selection_required",
                "interaction": {
                    "schema_version": "agent.interaction.v1",
                    "interaction_id": "int_unknown_status",
                    "type": "choice",
                    "status": "future_unknown_status",
                    "prompt": "请选择客户。",
                    "selection_mode": "single",
                    "min_selections": 1,
                    "max_selections": 1,
                    "choices": [{"value": "cus_1", "label": "上海睿狐"}],
                },
            }
        ],
        [
            {
                "event": "customer_selection_required",
                "interaction": {
                    "schema_version": "agent.interaction.v1",
                    "interaction_id": "int_invalid_disabled",
                    "type": "choice",
                    "status": "waiting_user_input",
                    "prompt": "请选择客户。",
                    "selection_mode": "single",
                    "min_selections": 1,
                    "max_selections": 1,
                    "choices": [{"value": "cus_1", "label": "上海睿狐", "disabled": "no"}],
                },
            }
        ],
        [
            {
                "event": "customer_selection_required",
                "interaction": {
                    "schema_version": "agent.interaction.v1",
                    "interaction_id": "int_oversized_choice",
                    "type": "choice",
                    "status": "waiting_user_input",
                    "prompt": "请选择客户。",
                    "selection_mode": "single",
                    "min_selections": 1,
                    "max_selections": 1,
                    "choices": [{"value": "cus_1", "label": "客" * 201}],
                },
            }
        ],
        [
            {
                "event": "opportunity_fields_required",
                "interaction": {
                    "schema_version": "agent.interaction.v1",
                    "interaction_id": "int_invalid_required",
                    "type": "form",
                    "status": "waiting_user_input",
                    "prompt": "请补充商机信息。",
                    "fields": [{"key": "name", "label": "商机名称", "type": "text", "required": "yes"}],
                },
            }
        ],
    ],
)
def test_message_migration_rejects_lossy_or_ambiguous_historical_interactions(
    migration_db,
    trace_events: object,
) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 21, 1, 30, 0)
    with session_factory.begin() as db:
        session = AgentSession(
            session_key=f"legacy-session-invalid-interaction-{id(trace_events)}",
            team_id=1,
            user_id=2,
        )
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="执行操作",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="请继续。",
                payload_json={
                    "source": "legacy_root",
                    "for_user_message_id": user_message.id,
                    "trace_events": trace_events,
                    "content_format": "text",
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    with pytest.raises(RuntimeError, match=r"invalid (payload|historical interaction)"):
        AgentMessageMigrationService(engine).migrate_batch()


def test_message_migration_rejects_an_update_that_did_not_write_exactly_one_row(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 21, 3, 0, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-ignored-update", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.USER,
                event_type="user_message",
                content="必须实际写入",
                created_time=created_at,
                last_modified_time=created_at,
            )
        )
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TRIGGER ignore_agent_message_update
                BEFORE UPDATE ON crm_agent_messages
                BEGIN
                    SELECT RAISE(IGNORE);
                END
                """
            )
        )

    with pytest.raises(AgentMessageMigrationError, match="did not update exactly one row"):
        AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        row = db.query(AgentMessage).one()
        assert row.turn_id is None
        assert row.ui_json is None


def test_message_migration_checksum_is_based_on_the_persisted_target_rows(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 21, 3, 30, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-readback-checksum", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.USER,
                event_type="user_message",
                content="校验持久化结果",
                created_time=created_at,
                last_modified_time=created_at,
            )
        )
    result = AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        row = db.query(AgentMessage).one()
        persisted_targets = [{"id": row.id, "ui_json": row.ui_json}]
    canonical = json.dumps(
        persisted_targets,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    expected_checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert result.target_ui_checksum == expected_checksum


def test_message_migration_rejects_persisted_state_that_differs_from_the_deterministic_target(
    migration_db,
) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 21, 3, 40, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-readback-state", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.USER,
                event_type="user_message",
                content="校验状态",
                created_time=created_at,
                last_modified_time=created_at,
            )
        )
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TRIGGER rewrite_agent_message_state
                AFTER UPDATE ON crm_agent_messages
                BEGIN
                    UPDATE crm_agent_messages
                    SET ui_json = json_set(NEW.ui_json, '$.state', 'failed')
                    WHERE id = NEW.id;
                END
                """
            )
        )

    with pytest.raises(AgentMessageMigrationError, match="target identity does not match"):
        AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        row = db.query(AgentMessage).one()
        assert row.ui_json is None


@pytest.mark.parametrize("underline", ["=", "===", "-", "--"])
def test_message_migration_normalizes_historical_setext_heading(migration_db, underline: str) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 21, 2, 10, 0)
    with session_factory.begin() as db:
        session = AgentSession(
            session_key=f"legacy-session-markdown-setext-{ord(underline[0])}-{len(underline)}",
            team_id=1,
            user_id=2,
        )
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="查看概览",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content=f"客户概览\n{underline}\n甲公司",
                payload_json={
                    "source": "legacy_root",
                    "for_user_message_id": user_message.id,
                    "trace_events": [],
                    "content_format": "markdown",
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        assistant = db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).one()
        assert assistant.content == "客户概览\n甲公司"
        envelope = AgentUIEnvelope.model_validate(assistant.ui_json)
        assert envelope.blocks[0].text == "客户概览\n甲公司"


def test_message_migration_normalizes_historical_markdown_table_without_losing_cells(migration_db) -> None:
    engine, session_factory = migration_db
    created_at = datetime(2026, 8, 21, 2, 0, 0)
    with session_factory.begin() as db:
        session = AgentSession(session_key="legacy-session-markdown-table", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        user_message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            event_type="user_message",
            content="列出客户",
            created_time=created_at,
            last_modified_time=created_at,
        )
        db.add(user_message)
        db.flush()
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                event_type="assistant_message",
                content="| 客户 | 城市 |\n| --- | --- |\n| 甲公司 | 上海 |",
                payload_json={
                    "source": "legacy_root",
                    "for_user_message_id": user_message.id,
                    "trace_events": [],
                    "content_format": "markdown",
                },
                created_time=created_at,
                last_modified_time=created_at,
            )
        )

    AgentMessageMigrationService(engine).migrate_batch()

    with session_factory() as db:
        assistant = db.query(AgentMessage).filter_by(role=AgentMessageRole.ASSISTANT).one()
        assert assistant.content == "客户\t城市\n甲公司\t上海"
        envelope = AgentUIEnvelope.model_validate(assistant.ui_json)
        assert envelope.blocks[0].format == "markdown"
        assert envelope.blocks[0].text == assistant.content

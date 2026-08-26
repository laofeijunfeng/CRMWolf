"""Behavior tests for the single-version Agent checkpoint cutover seam."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import ClassVar

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from pydantic import BaseModel
from sqlalchemy import JSON, Column, DateTime, Integer, LargeBinary, MetaData, String, Table, create_engine, text
from sqlalchemy.pool import StaticPool

from app.services.agent.checkpoint_cutover import (
    AgentCheckpointCutoverError,
    AgentCheckpointCutoverService,
)
from app.services.customer_activity_ai.checkpointer import SQLAlchemyCheckpointSaver

AS_OF = datetime(2026, 8, 23, 23, 59, 59)
ROOT_STATE_KEYS = {
    "turn",
    "context_snapshot",
    "decision",
    "query_input",
    "resolved_action",
    "workflow_input",
    "workflow_result",
    "dispatch_result",
}


class _LegacyConstructorProbe(BaseModel):
    construction_count: ClassVar[int] = 0

    value: str

    def model_post_init(self, _context: object) -> None:
        type(self).construction_count += 1


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata = MetaData()
    Table(
        "crm_langgraph_checkpoints",
        metadata,
        Column("thread_id", String(191), primary_key=True),
        Column("checkpoint_ns", String(512), primary_key=True, default=""),
        Column("checkpoint_id", String(191), primary_key=True),
        Column("parent_checkpoint_id", String(191)),
        Column("checkpoint_type", String(100), nullable=False),
        Column("checkpoint_blob", LargeBinary, nullable=False),
        Column("metadata_type", String(100), nullable=False),
        Column("metadata_blob", LargeBinary, nullable=False),
        Column("created_time", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    Table(
        "crm_langgraph_checkpoint_blobs",
        metadata,
        Column("thread_id", String(191), primary_key=True),
        Column("checkpoint_ns", String(512), primary_key=True),
        Column("channel", String(191), primary_key=True),
        Column("version", String(191), primary_key=True),
        Column("serde_type", String(100), nullable=False),
        Column("blob", LargeBinary, nullable=False),
        Column("created_time", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    Table(
        "crm_langgraph_checkpoint_writes",
        metadata,
        Column("thread_id", String(191), primary_key=True),
        Column("checkpoint_ns", String(512), primary_key=True),
        Column("checkpoint_id", String(191), primary_key=True),
        Column("task_id", String(191), primary_key=True),
        Column("write_idx", Integer, primary_key=True),
        Column("task_path", String(255), nullable=False, default=""),
        Column("channel", String(191), nullable=False),
        Column("serde_type", String(100), nullable=False),
        Column("blob", LargeBinary, nullable=False),
        Column("created_time", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    Table(
        "crm_agent_sessions",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("session_key", String(64), nullable=False),
        Column("team_id", Integer, nullable=False),
        Column("user_id", Integer, nullable=False),
        Column("status", String(20), nullable=False),
        Column("created_time", DateTime, nullable=False, default=AS_OF),
        Column("last_modified_time", DateTime, nullable=False, default=AS_OF),
    )
    Table(
        "crm_agent_tasks",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("team_id", Integer, nullable=False),
        Column("user_id", Integer, nullable=False),
        Column("session_id", Integer, nullable=False),
        Column("status", String(20), nullable=False),
        Column("created_time", DateTime, nullable=False, default=AS_OF),
        Column("last_modified_time", DateTime, nullable=False, default=AS_OF),
    )
    Table(
        "crm_agent_ui_actions",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("public_id", String(64), nullable=False),
        Column("team_id", Integer, nullable=False),
        Column("user_id", Integer, nullable=False),
        Column("session_id", Integer, nullable=False),
        Column("action_type", String(40), nullable=False),
        Column("target_json", JSON, nullable=False),
        Column("status", String(20), nullable=False),
        Column("expires_at", DateTime, nullable=False),
    )
    Table(
        "crm_customer_intelligence_runs",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("event_key", String(120), nullable=False),
        Column("event_json", JSON, nullable=False),
        Column("tenant_id", Integer, nullable=False),
        Column("team_id", Integer, nullable=False),
        Column("customer_id", Integer, nullable=False),
        Column("status", String(20), nullable=False),
        Column("attempt_count", Integer, nullable=False),
        Column("max_attempts", Integer, nullable=False),
        Column("lease_token", String(64)),
        Column("lease_expires_at", DateTime),
    )
    Table(
        "crm_agent_checkpoint_migration_journal",
        metadata,
        Column("migration_key", String(100), primary_key=True),
        Column("schema_version", String(100), nullable=False),
        Column("evidence_sha256", String(64), nullable=False),
        Column("created_time", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    metadata.create_all(engine)
    return engine


def _put_session(engine, *, session_id: int = 3, team_id: int = 1, user_id: int = 2, session_key: str = "web") -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO crm_agent_sessions "
                "(id, session_key, team_id, user_id, status, created_time, last_modified_time) "
                "VALUES (:session_id, :session_key, :team_id, :user_id, 'ACTIVE', :as_of, :as_of)"
            ),
            {
                "session_id": session_id,
                "session_key": session_key,
                "team_id": team_id,
                "user_id": user_id,
                "as_of": AS_OF,
            },
        )


def _put_checkpoint(
    saver: SQLAlchemyCheckpointSaver,
    *,
    thread_id: str,
    checkpoint_ns: str,
    checkpoint_id: str,
    runtime: str,
    runtime_namespace: str,
    state: dict[str, object] | None = None,
    metadata_extra: dict[str, object] | None = None,
) -> None:
    checkpoint = empty_checkpoint()
    checkpoint["id"] = checkpoint_id
    checkpoint["channel_values"] = state or {}
    checkpoint["channel_versions"] = dict.fromkeys(checkpoint["channel_values"], "1")
    metadata = {
        "source": "loop",
        "step": 1,
        "parents": {},
        "runtime": runtime,
        "runtime_namespace": runtime_namespace,
        **(metadata_extra or {}),
    }
    saver.put(
        {"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns}},
        checkpoint,
        metadata,
        checkpoint["channel_versions"],
    )


def test_cutover_deletes_quiescent_legacy_agent_checkpoints_without_creating_five_segment_targets() -> None:
    engine = _engine()
    _put_session(engine)
    saver = SQLAlchemyCheckpointSaver(engine)
    _put_checkpoint(
        saver,
        thread_id="crm_agent:1:2:3:web",
        checkpoint_ns="",
        checkpoint_id="legacy-root",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
        state={"team_id": 1, "user_id": 2, "session_id": 3},
    )
    _put_checkpoint(
        saver,
        thread_id="crm_agent:1:2:3:web",
        checkpoint_ns="query_agent:old",
        checkpoint_id="legacy-query",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
        state={"messages": []},
    )
    _put_checkpoint(
        saver,
        thread_id="crm_agent:1:2:3",
        checkpoint_ns="",
        checkpoint_id="target-root",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
        state={"turn": {"type": "text"}, "dispatch_result": None},
    )
    _put_checkpoint(
        saver,
        thread_id="customer_activity:9",
        checkpoint_ns="",
        checkpoint_id="adjacent",
        runtime="customer_activity",
        runtime_namespace="customer_activity",
        state={"activity_id": 9},
    )

    with engine.begin() as connection:
        result = AgentCheckpointCutoverService(connection).run(as_of=AS_OF)

    assert result.deleted_legacy_checkpoint_count == 2
    assert result.target_root_checkpoint_count == 1
    assert result.target_workflow_checkpoint_count == 0
    with engine.connect() as connection:
        identities = connection.execute(
            text("SELECT thread_id, checkpoint_ns FROM crm_langgraph_checkpoints ORDER BY thread_id, checkpoint_ns")
        ).all()
        assert identities == [
            ("crm_agent:1:2:3", ""),
            ("customer_activity:9", ""),
        ]
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM crm_langgraph_checkpoints WHERE thread_id = 'crm_agent:1:2:3:web'")
            ).scalar_one()
            == 0
        )


def test_cutover_inspects_legacy_custom_values_without_running_their_constructors() -> None:
    engine = _engine()
    _put_session(engine)
    saver = SQLAlchemyCheckpointSaver(engine)
    _put_checkpoint(
        saver,
        thread_id="crm_agent:1:2:3:web",
        checkpoint_ns="",
        checkpoint_id="legacy-root",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
        metadata_extra={"legacy_custom_value": _LegacyConstructorProbe(value="must-stay-inert")},
    )
    _LegacyConstructorProbe.construction_count = 0

    with engine.begin() as connection:
        result = AgentCheckpointCutoverService(connection).run(as_of=AS_OF)

    assert result.deleted_legacy_checkpoint_count == 1
    assert _LegacyConstructorProbe.construction_count == 0


def test_cutover_rejects_custom_constructors_in_target_state_blobs() -> None:
    engine = _engine()
    _put_session(engine)
    saver = SQLAlchemyCheckpointSaver(engine)
    _put_checkpoint(
        saver,
        thread_id="crm_agent:1:2:3",
        checkpoint_ns="",
        checkpoint_id="target-root",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
        state={"turn": _LegacyConstructorProbe(value="must-be-json-safe")},
    )
    _LegacyConstructorProbe.construction_count = 0

    with (
        pytest.raises(AgentCheckpointCutoverError, match="target_root:custom_serde"),
        engine.begin() as connection,
    ):
        AgentCheckpointCutoverService(connection).run(as_of=AS_OF)

    assert _LegacyConstructorProbe.construction_count == 0


def test_cutover_fails_closed_and_rolls_back_when_a_legacy_task_is_still_active() -> None:
    engine = _engine()
    _put_session(engine)
    saver = SQLAlchemyCheckpointSaver(engine)
    _put_checkpoint(
        saver,
        thread_id="crm_agent:1:2:3:web",
        checkpoint_ns="",
        checkpoint_id="legacy-root",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO crm_agent_tasks "
                "(id, team_id, user_id, session_id, status, created_time, last_modified_time) "
                "VALUES (1, 1, 2, 3, 'WAITING_USER', :as_of, :as_of)"
            ),
            {"as_of": AS_OF},
        )

    with pytest.raises(AgentCheckpointCutoverError, match="legacy_task:active"), engine.begin() as connection:
        AgentCheckpointCutoverService(connection).run(as_of=AS_OF)

    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM crm_langgraph_checkpoints")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM crm_agent_checkpoint_migration_journal")).scalar_one() == 0


def test_cutover_rejects_target_root_state_outside_the_eight_field_contract() -> None:
    engine = _engine()
    _put_session(engine)
    saver = SQLAlchemyCheckpointSaver(engine)
    _put_checkpoint(
        saver,
        thread_id="crm_agent:1:2:3",
        checkpoint_ns="",
        checkpoint_id="target-root",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
        state={"turn": {}, "legacy_selected_customer": {"id": 8}},
    )

    with pytest.raises(AgentCheckpointCutoverError, match="target_root:unknown_state"), engine.begin() as connection:
        AgentCheckpointCutoverService(connection).run(as_of=AS_OF)


def test_cutover_treats_langgraph_join_channels_as_control_state() -> None:
    engine = _engine()
    _put_session(engine)
    saver = SQLAlchemyCheckpointSaver(engine)
    _put_checkpoint(
        saver,
        thread_id="crm_agent:1:2:3",
        checkpoint_ns="",
        checkpoint_id="target-root",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
        state=dict.fromkeys(ROOT_STATE_KEYS),
    )
    _put_checkpoint(
        saver,
        thread_id="crm_agent:1:2:3",
        checkpoint_ns="workflow_subgraph:flow-1",
        checkpoint_id="target-workflow",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
        state={"workflow_id": "flow-1", "join:workflow_complete": False},
    )

    with engine.begin() as connection:
        result = AgentCheckpointCutoverService(connection).run(as_of=AS_OF)

    assert result.target_workflow_checkpoint_count == 1


def test_cutover_is_idempotent_only_when_the_committed_post_state_matches_the_journal() -> None:
    engine = _engine()
    _put_session(engine)
    saver = SQLAlchemyCheckpointSaver(engine)
    _put_checkpoint(
        saver,
        thread_id="crm_agent:1:2:3",
        checkpoint_ns="",
        checkpoint_id="target-root",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
        state=dict.fromkeys(ROOT_STATE_KEYS),
    )

    with engine.begin() as connection:
        first = AgentCheckpointCutoverService(connection).run(as_of=AS_OF)
    with engine.begin() as connection:
        second = AgentCheckpointCutoverService(connection).run(as_of=AS_OF + timedelta(seconds=1))

    assert second.evidence_sha256 == first.evidence_sha256
    assert second.already_completed is True
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE crm_agent_checkpoint_migration_journal SET evidence_sha256 = :digest"),
            {"digest": "0" * 64},
        )
    with pytest.raises(AgentCheckpointCutoverError, match="journal"), engine.begin() as connection:
        AgentCheckpointCutoverService(connection).run(as_of=AS_OF)


def _put_interrupt(
    saver: SQLAlchemyCheckpointSaver,
    *,
    thread_id: str,
    checkpoint_ns: str,
    checkpoint_id: str,
) -> None:
    saver.put_writes(
        {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        },
        [("__interrupt__", [{"id": "interrupt-1"}])],
        task_id="workflow-task",
    )


def _put_workflow_action(
    engine,
    *,
    action_id: int = 1,
    parent_checkpoint_id: str = "root-parent",
    subgraph_checkpoint_ns: str = "workflow_subgraph:flow-1",
    subgraph_checkpoint_id: str = "workflow-waiting",
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO crm_agent_ui_actions "
                "(id, public_id, team_id, user_id, session_id, action_type, target_json, status, expires_at) "
                "VALUES (:id, :public_id, 1, 2, 3, 'submit_interaction', :target_json, 'ACTIVE', :expires_at)"
            ),
            {
                "id": action_id,
                "public_id": f"act-{action_id}",
                "target_json": json.dumps(
                    {
                        "workflow_continuation": {
                            "workflow_ref": {"workflow_id": "flow-1", "interrupt_id": "interrupt-1"},
                            "parent_checkpoint_id": parent_checkpoint_id,
                            "subgraph_checkpoint_ns": subgraph_checkpoint_ns,
                            "subgraph_checkpoint_id": subgraph_checkpoint_id,
                        }
                    }
                ),
                "expires_at": AS_OF + timedelta(hours=1),
            },
        )


def _put_waiting_target_workflow(engine) -> SQLAlchemyCheckpointSaver:
    _put_session(engine)
    saver = SQLAlchemyCheckpointSaver(engine)
    _put_checkpoint(
        saver,
        thread_id="crm_agent:1:2:3",
        checkpoint_ns="",
        checkpoint_id="root-parent",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
        state=dict.fromkeys(ROOT_STATE_KEYS),
    )
    _put_checkpoint(
        saver,
        thread_id="crm_agent:1:2:3",
        checkpoint_ns="workflow_subgraph:flow-1",
        checkpoint_id="workflow-waiting",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
        state={"workflow_id": "flow-1", "workflow_interaction": {"type": "choice"}},
    )
    _put_interrupt(
        saver,
        thread_id="crm_agent:1:2:3",
        checkpoint_ns="workflow_subgraph:flow-1",
        checkpoint_id="workflow-waiting",
    )
    return saver


def test_cutover_rejects_a_waiting_target_workflow_without_an_exact_action_continuation() -> None:
    engine = _engine()
    _put_waiting_target_workflow(engine)

    with (
        pytest.raises(AgentCheckpointCutoverError, match="target_workflow:continuation_missing"),
        engine.begin() as connection,
    ):
        AgentCheckpointCutoverService(connection).run(as_of=AS_OF)


def test_cutover_accepts_one_exact_action_for_a_waiting_target_workflow() -> None:
    engine = _engine()
    _put_waiting_target_workflow(engine)
    _put_workflow_action(engine)

    with engine.begin() as connection:
        result = AgentCheckpointCutoverService(connection).run(as_of=AS_OF)

    assert result.target_root_checkpoint_count == 1
    assert result.target_workflow_checkpoint_count == 1


def test_cutover_does_not_treat_a_consumed_empty_legacy_branch_as_active_work() -> None:
    engine = _engine()
    _put_session(engine)
    saver = SQLAlchemyCheckpointSaver(engine)
    _put_checkpoint(
        saver,
        thread_id="crm_agent:1:2:3:web",
        checkpoint_ns="",
        checkpoint_id="legacy-root",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
        state={"branch:to:new_flow_graph": []},
    )

    with engine.begin() as connection:
        result = AgentCheckpointCutoverService(connection).run(as_of=AS_OF)

    assert result.deleted_legacy_checkpoint_count == 1


def test_cutover_rejects_an_action_that_points_to_a_missing_workflow_checkpoint() -> None:
    engine = _engine()
    _put_waiting_target_workflow(engine)
    _put_workflow_action(engine, subgraph_checkpoint_id="missing-checkpoint")

    with (
        pytest.raises(AgentCheckpointCutoverError, match="target_workflow:continuation_orphaned"),
        engine.begin() as connection,
    ):
        AgentCheckpointCutoverService(connection).run(as_of=AS_OF)


def test_cutover_rejects_duplicate_actions_for_one_waiting_workflow_checkpoint() -> None:
    engine = _engine()
    _put_waiting_target_workflow(engine)
    _put_workflow_action(engine, action_id=1)
    _put_workflow_action(engine, action_id=2)

    with (
        pytest.raises(AgentCheckpointCutoverError, match="target_workflow:continuation_ambiguous"),
        engine.begin() as connection,
    ):
        AgentCheckpointCutoverService(connection).run(as_of=AS_OF)


def test_cutover_rejects_an_action_for_a_workflow_checkpoint_that_is_not_waiting() -> None:
    engine = _engine()
    _put_session(engine)
    saver = SQLAlchemyCheckpointSaver(engine)
    _put_checkpoint(
        saver,
        thread_id="crm_agent:1:2:3",
        checkpoint_ns="",
        checkpoint_id="root-parent",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
        state=dict.fromkeys(ROOT_STATE_KEYS),
    )
    _put_checkpoint(
        saver,
        thread_id="crm_agent:1:2:3",
        checkpoint_ns="workflow_subgraph:flow-1",
        checkpoint_id="workflow-waiting",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
        state={"workflow_id": "flow-1"},
    )
    _put_workflow_action(engine)

    with (
        pytest.raises(AgentCheckpointCutoverError, match="target_workflow:continuation_not_waiting"),
        engine.begin() as connection,
    ):
        AgentCheckpointCutoverService(connection).run(as_of=AS_OF)


def test_cutover_rolls_back_if_an_adjacent_workflow_row_changes_during_legacy_deletion() -> None:
    engine = _engine()
    _put_session(engine)
    saver = SQLAlchemyCheckpointSaver(engine)
    _put_checkpoint(
        saver,
        thread_id="crm_agent:1:2:3:web",
        checkpoint_ns="",
        checkpoint_id="legacy-root",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
    )
    _put_checkpoint(
        saver,
        thread_id="customer_activity:9",
        checkpoint_ns="",
        checkpoint_id="adjacent",
        runtime="customer_activity",
        runtime_namespace="customer_activity",
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """CREATE TRIGGER mutate_adjacent_after_legacy_delete
                   AFTER DELETE ON crm_langgraph_checkpoints
                   WHEN OLD.thread_id = 'crm_agent:1:2:3:web'
                   BEGIN
                     UPDATE crm_langgraph_checkpoints
                     SET parent_checkpoint_id = 'mutated'
                     WHERE thread_id = 'customer_activity:9';
                   END"""
            )
        )

    with (
        pytest.raises(AgentCheckpointCutoverError, match="cutover:protected_rows_changed"),
        engine.begin() as connection,
    ):
        AgentCheckpointCutoverService(connection).run(as_of=AS_OF)

    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT parent_checkpoint_id FROM crm_langgraph_checkpoints WHERE thread_id = 'customer_activity:9'"
                )
            ).scalar_one()
            is None
        )
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM crm_langgraph_checkpoints WHERE thread_id = 'crm_agent:1:2:3:web'")
            ).scalar_one()
            == 1
        )


def test_cutover_rejects_an_active_customer_intelligence_run_without_its_checkpoint() -> None:
    engine = _engine()
    with engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO crm_customer_intelligence_runs
                   (id, event_key, event_json, tenant_id, team_id, customer_id, status,
                    attempt_count, max_attempts, lease_token, lease_expires_at)
                   VALUES (1, 'event-1', :event_json, 1, 1, 9, 'RETRY_PENDING', 1, 3, NULL, NULL)"""
            ),
            {"event_json": json.dumps({"event_key": "event-1", "tenant_id": 1, "team_id": 1, "customer_id": 9})},
        )

    with (
        pytest.raises(AgentCheckpointCutoverError, match="customer_intelligence:active_ownership_invalid"),
        engine.begin() as connection,
    ):
        AgentCheckpointCutoverService(connection).run(as_of=AS_OF)


def test_cutover_rejects_an_active_customer_intelligence_checkpoint_with_mismatched_event_state() -> None:
    engine = _engine()
    saver = SQLAlchemyCheckpointSaver(engine)
    _put_checkpoint(
        saver,
        thread_id="crm_agent_customer_intelligence:1:event-1",
        checkpoint_ns="",
        checkpoint_id="ci-latest",
        runtime="crm_agent_customer_intelligence",
        runtime_namespace="crm_agent_customer_intelligence",
        state={
            "team_id": 1,
            "event": {"event_key": "other-event", "tenant_id": 1, "team_id": 1, "customer_id": 9},
        },
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO crm_customer_intelligence_runs
                   (id, event_key, event_json, tenant_id, team_id, customer_id, status,
                    attempt_count, max_attempts, lease_token, lease_expires_at)
                   VALUES (1, 'event-1', :event_json, 1, 1, 9, 'RETRY_PENDING', 1, 3, NULL, NULL)"""
            ),
            {"event_json": json.dumps({"event_key": "event-1", "tenant_id": 1, "team_id": 1, "customer_id": 9})},
        )

    with (
        pytest.raises(AgentCheckpointCutoverError, match="customer_intelligence:active_ownership_invalid"),
        engine.begin() as connection,
    ):
        AgentCheckpointCutoverService(connection).run(as_of=AS_OF)


def _put_customer_intelligence_run(
    engine,
    *,
    status: str = "RETRY_PENDING",
    lease_token: str | None = None,
    lease_expires_at: datetime | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO crm_customer_intelligence_runs
                   (id, event_key, event_json, tenant_id, team_id, customer_id, status,
                    attempt_count, max_attempts, lease_token, lease_expires_at)
                   VALUES (1, 'event-1', :event_json, 1, 1, 9, :status, 1, 3,
                           :lease_token, :lease_expires_at)"""
            ),
            {
                "event_json": json.dumps(
                    {"event_key": "event-1", "tenant_id": 1, "team_id": 1, "customer_id": 9}
                ),
                "status": status,
                "lease_token": lease_token,
                "lease_expires_at": lease_expires_at,
            },
        )


def _put_customer_intelligence_checkpoint(engine) -> None:
    saver = SQLAlchemyCheckpointSaver(engine)
    _put_checkpoint(
        saver,
        thread_id="crm_agent_customer_intelligence:1:event-1",
        checkpoint_ns="",
        checkpoint_id="ci-latest",
        runtime="crm_agent_customer_intelligence",
        runtime_namespace="crm_agent_customer_intelligence",
        state={
            "team_id": 1,
            "user_id": 2,
            "session_id": 3,
            "event": {"event_key": "event-1", "tenant_id": 1, "team_id": 1, "customer_id": 9},
            "branch:to:normalize_event": "normalize_event",
        },
        metadata_extra={"team_id": 1, "event_key": "event-1"},
    )


def test_cutover_retains_a_valid_retry_pending_customer_intelligence_checkpoint() -> None:
    engine = _engine()
    _put_customer_intelligence_checkpoint(engine)
    _put_customer_intelligence_run(engine)

    with engine.begin() as connection:
        result = AgentCheckpointCutoverService(connection).run(as_of=AS_OF)

    assert result.retained_customer_intelligence_checkpoint_count == 1


def test_cutover_rejects_a_customer_intelligence_run_with_a_live_executor_lease() -> None:
    engine = _engine()
    _put_customer_intelligence_checkpoint(engine)
    _put_customer_intelligence_run(
        engine,
        status="RUNNING",
        lease_token="lease-1",
        lease_expires_at=AS_OF + timedelta(minutes=5),
    )

    with (
        pytest.raises(AgentCheckpointCutoverError, match="customer_intelligence:live_lease"),
        engine.begin() as connection,
    ):
        AgentCheckpointCutoverService(connection).run(as_of=AS_OF)


def test_cutover_rejects_an_incomplete_customer_intelligence_checkpoint_chain() -> None:
    engine = _engine()
    _put_customer_intelligence_checkpoint(engine)
    _put_customer_intelligence_run(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                """UPDATE crm_langgraph_checkpoints
                   SET parent_checkpoint_id = 'missing-parent'
                   WHERE thread_id = 'crm_agent_customer_intelligence:1:event-1'"""
            )
        )

    with (
        pytest.raises(AgentCheckpointCutoverError, match="customer_intelligence:physical_ownership_invalid"),
        engine.begin() as connection,
    ):
        AgentCheckpointCutoverService(connection).run(as_of=AS_OF)


def test_cutover_rejects_orphan_customer_intelligence_writes() -> None:
    engine = _engine()
    _put_customer_intelligence_checkpoint(engine)
    _put_customer_intelligence_run(engine)
    SQLAlchemyCheckpointSaver(engine).put_writes(
        {
            "configurable": {
                "thread_id": "crm_agent_customer_intelligence:1:event-1",
                "checkpoint_ns": "",
                "checkpoint_id": "missing-checkpoint",
            }
        },
        [("__error__", {"code": "failed"})],
        task_id="orphan-task",
    )

    with (
        pytest.raises(AgentCheckpointCutoverError, match="customer_intelligence:physical_ownership_invalid"),
        engine.begin() as connection,
    ):
        AgentCheckpointCutoverService(connection).run(as_of=AS_OF)


def test_cutover_rejects_orphan_customer_intelligence_blobs() -> None:
    engine = _engine()
    _put_customer_intelligence_checkpoint(engine)
    _put_customer_intelligence_run(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO crm_langgraph_checkpoint_blobs
                   (thread_id, checkpoint_ns, channel, version, serde_type, `blob`)
                   VALUES ('crm_agent_customer_intelligence:1:event-1', '',
                           'orphan-channel', 'orphan-version', 'empty', :blob)"""
            ),
            {"blob": b""},
        )

    with (
        pytest.raises(AgentCheckpointCutoverError, match="customer_intelligence:physical_ownership_invalid"),
        engine.begin() as connection,
    ):
        AgentCheckpointCutoverService(connection).run(as_of=AS_OF)

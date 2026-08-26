"""Behavior tests for the single-version Agent cutover inventory."""

from __future__ import annotations

from datetime import datetime

from langgraph.checkpoint.base import empty_checkpoint
from sqlalchemy import JSON, Column, DateTime, Integer, LargeBinary, MetaData, String, Table, create_engine, text
from sqlalchemy.pool import StaticPool

from app.services.agent.migration_inventory import AgentMigrationInventory
from app.services.customer_activity_ai.checkpointer import SQLAlchemyCheckpointSaver

AS_OF = datetime(2026, 8, 23, 23, 59, 59)


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata = MetaData()
    Table(
        "crm_agent_sessions",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("session_key", String(64), nullable=False),
        Column("team_id", Integer, nullable=False),
        Column("user_id", Integer, nullable=False),
        Column("status", String(20), nullable=False),
        Column("created_time", DateTime, nullable=False),
        Column("last_modified_time", DateTime, nullable=False),
    )
    Table(
        "crm_agent_tasks",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("team_id", Integer, nullable=False),
        Column("user_id", Integer, nullable=False),
        Column("session_id", Integer, nullable=False),
        Column("status", String(20), nullable=False),
        Column("created_time", DateTime, nullable=False),
        Column("last_modified_time", DateTime, nullable=False),
    )
    Table(
        "crm_agent_messages",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("role", String(20), nullable=False),
        Column("event_type", String(40)),
        Column("content", String(500), nullable=False),
        Column("payload_json", JSON),
        Column("created_time", DateTime, nullable=False),
    )
    Table(
        "crm_agent_ui_actions",
        metadata,
        Column("id", Integer, primary_key=True),
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
    metadata.create_all(engine)
    return engine


def _put_checkpoint(
    engine,
    *,
    thread_id: str,
    checkpoint_ns: str,
    checkpoint_id: str,
    runtime: str,
    runtime_namespace: str,
    state: dict[str, object] | None = None,
) -> None:
    checkpoint = empty_checkpoint()
    checkpoint["id"] = checkpoint_id
    checkpoint["channel_values"] = state or {}
    checkpoint["channel_versions"] = dict.fromkeys(checkpoint["channel_values"], "1")
    SQLAlchemyCheckpointSaver(engine).put(
        {"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns}},
        checkpoint,
        {
            "source": "loop",
            "step": 1,
            "parents": {},
            "runtime": runtime,
            "runtime_namespace": runtime_namespace,
        },
        checkpoint["channel_versions"],
    )


def _put_session(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO crm_agent_sessions
                   (id, session_key, team_id, user_id, status, created_time, last_modified_time)
                   VALUES (3, 'web', 1, 2, 'ACTIVE', :as_of, :as_of)"""
            ),
            {"as_of": AS_OF},
        )


def test_inventory_reports_the_single_version_checkpoint_matrix_without_business_content() -> None:
    engine = _engine()
    _put_session(engine)
    _put_checkpoint(
        engine,
        thread_id="crm_agent:1:2:3:web",
        checkpoint_ns="",
        checkpoint_id="legacy-root",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
    )
    _put_checkpoint(
        engine,
        thread_id="crm_agent:1:2:3:web",
        checkpoint_ns="query_agent:old",
        checkpoint_id="legacy-query",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
    )
    _put_checkpoint(
        engine,
        thread_id="crm_agent:1:2:3",
        checkpoint_ns="",
        checkpoint_id="target-root",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
        state={"turn": {"type": "text"}},
    )
    _put_checkpoint(
        engine,
        thread_id="customer_activity:9",
        checkpoint_ns="",
        checkpoint_id="adjacent",
        runtime="customer_activity",
        runtime_namespace="customer_activity",
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO crm_agent_messages
                   (id, role, event_type, content, payload_json, created_time)
                   VALUES (1, 'USER', 'user_message', 'sensitive customer request', NULL, :as_of)"""
            ),
            {"as_of": AS_OF},
        )

    report = AgentMigrationInventory(engine, as_of=AS_OF).collect()
    dumped = report.model_dump(mode="json")

    assert dumped["schema_version"] == "crm.agent.migration-inventory.v2"
    assert dumped["as_of"] == "2026-08-23T23:59:59"
    assert dumped["checkpoints"]["categories"]["legacy_root"]["checkpoint_row_count"] == 1
    assert dumped["checkpoints"]["categories"]["legacy_query"]["checkpoint_row_count"] == 1
    assert dumped["checkpoints"]["categories"]["target_root"]["checkpoint_row_count"] == 1
    assert dumped["checkpoints"]["categories"]["adjacent_workflow"]["checkpoint_row_count"] == 1
    assert dumped["blocking_unknowns"] == []
    assert "sensitive customer request" not in str(dumped)


def test_inventory_uses_the_cutover_matrix_blockers_as_the_release_gate() -> None:
    engine = _engine()
    _put_session(engine)
    _put_checkpoint(
        engine,
        thread_id="crm_agent:1:2:3:web",
        checkpoint_ns="",
        checkpoint_id="legacy-root",
        runtime="crm_agent_root",
        runtime_namespace="crm_agent",
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO crm_agent_tasks
                   (id, team_id, user_id, session_id, status, created_time, last_modified_time)
                   VALUES (1, 1, 2, 3, 'WAITING_USER', :as_of, :as_of)"""
            ),
            {"as_of": AS_OF},
        )

    report = AgentMigrationInventory(engine, as_of=AS_OF).collect()

    assert report.blocking_unknowns == ["legacy_task:active"]
    assert report.active_state.active_legacy_task_count == 1

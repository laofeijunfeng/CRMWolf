"""Customer activity AI workflow orchestration tests."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services.customer_activity_ai.checkpointer import SQLAlchemyCheckpointSaver
from app.services.customer_activity_ai.workflow import CustomerActivityAIWorkflow


class FakeStructuringAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def structure(self, db, *, team_id: int, context: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"team_id": team_id, "context": context})
        return {
            "title": "整理后的会议",
            "summary": "客户关注预算和交付周期。",
            "next_action": "下周三提供方案",
            "content_json": {
                "meeting_subject": "方案沟通会",
                "key_minutes": ["客户关注预算和交付周期。"],
            },
        }


class FakeEvaluationAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def evaluate(self, db, *, team_id: int, context: dict[str, Any], rubric) -> dict[str, Any]:
        self.calls.append({"team_id": team_id, "context": context, "rubric": rubric})
        return {
            "score": 80,
            "is_valid": True,
            "reason": "信息完整且有明确下一步。",
            "principle_scores": {},
        }


class WorkflowHarness(CustomerActivityAIWorkflow):
    def __init__(self, *, structuring_agent, evaluation_agent, checkpointer=None) -> None:
        self.persisted_structures: list[dict[str, Any]] = []
        self.persisted_evaluations: list[dict[str, Any]] = []
        self.context = {
            "current_activity": {
                "id": 1,
                "activity_kind": "ONLINE_MEETING",
                "activity_category": "MEETING",
                "activity_label": "线上会议",
                "score_rule": "meeting",
                "source_content": "今天和客户开方案会，客户关注预算和交付周期，下周三提供方案。",
                "content_json": None,
                "next_action": None,
                "occurred_at": "2026-07-30T10:00:00",
            },
            "customer": {"id": 10, "account_name": "睿狐科技"},
            "contacts": [],
            "opportunities": [],
            "previous_activities": [],
        }
        super().__init__(
            structuring_agent=structuring_agent,
            evaluation_agent=evaluation_agent,
            checkpointer=checkpointer or InMemorySaver(),
        )

    def _load_context(self, state):
        return {"context": self.context, "events": [{"event": "activity_context_loaded"}]}

    def _persist_structured_content(self, state):
        self.persisted_structures.append(state["structure_result"])
        self.context = {
            **self.context,
            "current_activity": {
                **self.context["current_activity"],
                "title": state["structure_result"]["title"],
                "content_json": state["structure_result"]["content_json"],
                "summary": state["structure_result"]["summary"],
                "next_action": state["structure_result"]["next_action"],
            },
        }
        return {"context": self.context, "events": [{"event": "structured_content_persisted"}]}

    def _persist_evaluation_result(self, state):
        self.persisted_evaluations.append(state["evaluation_result"])
        return {"events": [{"event": "evaluation_result_persisted"}]}


@pytest.mark.asyncio
async def test_process_mode_structures_then_evaluates_meeting_with_meeting_rubric():
    structuring_agent = FakeStructuringAgent()
    evaluation_agent = FakeEvaluationAgent()
    workflow = WorkflowHarness(structuring_agent=structuring_agent, evaluation_agent=evaluation_agent)

    state = await workflow.run(activity_id=1, team_id=2, mode="process", run_id="test-process")

    assert len(structuring_agent.calls) == 1
    assert len(evaluation_agent.calls) == 1
    assert evaluation_agent.calls[0]["rubric"].score_rule == "meeting"
    assert workflow.persisted_structures[0]["content_json"]["meeting_subject"] == "方案沟通会"
    assert workflow.persisted_evaluations[0]["score"] == 80
    assert state["evaluation_result"]["is_valid"] is True


@pytest.mark.asyncio
async def test_evaluate_mode_skips_structuring_and_uses_existing_context():
    structuring_agent = FakeStructuringAgent()
    evaluation_agent = FakeEvaluationAgent()
    workflow = WorkflowHarness(structuring_agent=structuring_agent, evaluation_agent=evaluation_agent)

    state = await workflow.run(activity_id=1, team_id=2, mode="evaluate", run_id="test-evaluate")

    assert structuring_agent.calls == []
    assert len(evaluation_agent.calls) == 1
    assert workflow.persisted_structures == []
    assert workflow.persisted_evaluations[0]["score"] == 80
    assert state["evaluation_result"]["score"] == 80


def test_ai_structured_next_follow_time_overrides_ui_default_only():
    workflow = WorkflowHarness(
        structuring_agent=FakeStructuringAgent(),
        evaluation_agent=FakeEvaluationAgent(),
    )
    result = {
        "content_json": {
            "content": "客户反馈项目还在立项评估阶段，先持续跟进。",
            "next_follow_time_text": "下周三",
        }
    }
    activity = SimpleNamespace(
        next_follow_time=datetime(2026, 8, 2, 0, 0, 0),
        next_follow_time_source="UI_DEFAULT",
        occurred_at=datetime(2026, 7, 30, 10, 0, 0),
    )

    resolved = workflow._resolve_structured_next_follow_time(result, activity)

    assert resolved == datetime(2026, 8, 5, 10, 0, 0)


def test_ai_structured_next_follow_time_does_not_override_user_time():
    workflow = WorkflowHarness(
        structuring_agent=FakeStructuringAgent(),
        evaluation_agent=FakeEvaluationAgent(),
    )
    result = {"content_json": {"next_follow_time_text": "下周三"}}
    activity = SimpleNamespace(
        next_follow_time=datetime(2026, 8, 6, 9, 0, 0),
        next_follow_time_source="USER",
        occurred_at=datetime(2026, 7, 30, 10, 0, 0),
    )

    assert workflow._resolve_structured_next_follow_time(result, activity) is None


def _create_checkpoint_tables(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE crm_langgraph_checkpoints (
                thread_id VARCHAR(191) NOT NULL,
                checkpoint_ns VARCHAR(191) NOT NULL DEFAULT '',
                checkpoint_id VARCHAR(191) NOT NULL,
                parent_checkpoint_id VARCHAR(191),
                checkpoint_type VARCHAR(100) NOT NULL,
                checkpoint_blob BLOB NOT NULL,
                metadata_type VARCHAR(100) NOT NULL,
                metadata_blob BLOB NOT NULL,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE crm_langgraph_checkpoint_blobs (
                thread_id VARCHAR(191) NOT NULL,
                checkpoint_ns VARCHAR(191) NOT NULL DEFAULT '',
                channel VARCHAR(191) NOT NULL,
                version VARCHAR(191) NOT NULL,
                serde_type VARCHAR(100) NOT NULL,
                `blob` BLOB NOT NULL,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
            )
        """))
        conn.execute(text("""
            CREATE TABLE crm_langgraph_checkpoint_writes (
                thread_id VARCHAR(191) NOT NULL,
                checkpoint_ns VARCHAR(191) NOT NULL DEFAULT '',
                checkpoint_id VARCHAR(191) NOT NULL,
                task_id VARCHAR(191) NOT NULL,
                write_idx INTEGER NOT NULL,
                task_path VARCHAR(255) NOT NULL DEFAULT '',
                channel VARCHAR(191) NOT NULL,
                serde_type VARCHAR(100) NOT NULL,
                `blob` BLOB NOT NULL,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx)
            )
        """))


@pytest.mark.asyncio
async def test_workflow_persists_langgraph_checkpoints_with_sqlalchemy_saver():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _create_checkpoint_tables(engine)
    checkpointer = SQLAlchemyCheckpointSaver(engine)
    workflow = WorkflowHarness(
        structuring_agent=FakeStructuringAgent(),
        evaluation_agent=FakeEvaluationAgent(),
        checkpointer=checkpointer,
    )

    await workflow.run(activity_id=1, team_id=2, mode="process", run_id="sql-checkpoint")

    thread_id = "customer_activity:1:process:sql-checkpoint"
    with engine.begin() as conn:
        checkpoint_count = conn.execute(
            text("SELECT COUNT(*) FROM crm_langgraph_checkpoints WHERE thread_id = :thread_id"),
            {"thread_id": thread_id},
        ).scalar_one()
        blob_count = conn.execute(
            text("SELECT COUNT(*) FROM crm_langgraph_checkpoint_blobs WHERE thread_id = :thread_id"),
            {"thread_id": thread_id},
        ).scalar_one()

    assert checkpoint_count > 0
    assert blob_count > 0
    assert checkpointer.get_tuple({"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}})

"""Behavior tests for the one-time follow-up confirmation question migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import sqlalchemy as sa

if TYPE_CHECKING:
    from types import ModuleType


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/127_canonicalize_follow_up_confirmation_questions.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("follow_up_confirmation_question_127", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schema() -> sa.MetaData:
    metadata = sa.MetaData()
    sa.Table(
        "crm_follow_up_task_confirmation_cases",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("question_text", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
    )
    sa.Table(
        "crm_follow_up_task_confirmation_prompt_deliveries",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("payload_json", sa.JSON, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
    )
    sa.Table(
        "crm_agent_messages",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ui_json", sa.JSON, nullable=True),
        sa.Column("role", sa.String(20), nullable=False),
    )
    return metadata


def test_migration_rewrites_persisted_questions_once_without_changing_business_rows():
    migration = _load_migration()
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = _schema()
    metadata.create_all(engine)
    cases = metadata.tables["crm_follow_up_task_confirmation_cases"]
    deliveries = metadata.tables["crm_follow_up_task_confirmation_prompt_deliveries"]
    messages = metadata.tables["crm_agent_messages"]

    with engine.begin() as connection:
        connection.execute(
            cases.insert(),
            [
                {"id": 1, "question_text": "9 月 9 号待办的「确认预算」需要延期吗?", "status": "PENDING"},
                {"id": 2, "question_text": "9 月 10 号待办的「发送报价」不需要继续跟进了吗？", "status": "RESOLVED"},
                {"id": 3, "question_text": "9 月 11 号待办的「安排会议」现在完成了吗?", "status": "PENDING"},
            ],
        )
        connection.execute(
            deliveries.insert(),
            {
                "id": 10,
                "payload_json": {
                    "question_text": "9 月 9 号待办的「确认预算」需要延期吗?",
                    "choices": ["已完成", "先放着", "不管了"],
                },
                "status": "SENT",
            },
        )
        connection.execute(
            messages.insert(),
            {
                "id": 20,
                "ui_json": {
                    "blocks": [
                        {
                            "type": "interaction",
                            "presentation": "COMPACT_TASK_COMPLETION",
                            "prompt": "9 月 9 号待办的「确认预算」需要延期吗?",
                        },
                        {"type": "markdown", "content": "保留其他内容"},
                    ]
                },
                "role": "ASSISTANT",
            },
        )

        changed = migration.migrate_confirmation_question_data(connection)
        assert changed == {"cases": 2, "deliveries": 1, "messages": 1}

        first_run = {
            "cases": connection.execute(sa.select(cases).order_by(cases.c.id)).mappings().all(),
            "deliveries": connection.execute(sa.select(deliveries)).mappings().all(),
            "messages": connection.execute(sa.select(messages)).mappings().all(),
        }
        assert first_run["cases"][0]["question_text"].endswith("现在完成了吗?")
        assert first_run["cases"][1]["question_text"].endswith("现在完成了吗?")
        assert first_run["cases"][2]["question_text"] == "9 月 11 号待办的「安排会议」现在完成了吗?"
        assert first_run["cases"][0]["status"] == "PENDING"
        assert first_run["cases"][1]["status"] == "RESOLVED"
        assert first_run["deliveries"][0]["payload_json"]["question_text"].endswith("现在完成了吗?")
        assert first_run["messages"][0]["ui_json"]["blocks"][0]["prompt"].endswith("现在完成了吗?")
        assert first_run["messages"][0]["ui_json"]["blocks"][1]["content"] == "保留其他内容"

        assert migration.migrate_confirmation_question_data(connection) == {
            "cases": 0,
            "deliveries": 0,
            "messages": 0,
        }

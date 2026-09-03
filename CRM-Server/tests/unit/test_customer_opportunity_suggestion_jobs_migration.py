"""Structural contract tests for migration 121."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType


class _RecordingOperations:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name: str):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))

        return record


def _load_migration() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2] / "migrations" / "versions" / "121_customer_opportunity_suggestion_jobs.py"
    )
    spec = importlib.util.spec_from_file_location("customer_opportunity_suggestion_jobs_121", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_121_creates_agent_only_revision_scoped_job_table():
    migration = _load_migration()
    operations = _RecordingOperations()
    migration.op = operations

    migration.upgrade()

    assert migration.revision == "121_customer_opportunity_suggestion_jobs"
    assert migration.down_revision == "120_customer_activity_post_commit_job_evidence"
    create_table = next(call for call in operations.calls if call[0] == "create_table")
    assert create_table[1][0] == "crm_customer_opportunity_suggestion_jobs"
    table_items = create_table[1][1:]
    column_names = {item.name for item in table_items if hasattr(item, "name")}
    assert {
        "team_id",
        "activity_id",
        "activity_revision",
        "submission_source",
        "status",
        "attempt_count",
        "lease_token",
        "lease_expires_at",
        "run_id",
        "graph_thread_id",
        "result_json",
        "error_message",
        "started_at",
        "finished_at",
    } <= column_names
    constraint_names = {item.name for item in table_items if getattr(item, "name", None)}
    assert "uq_customer_opportunity_suggestion_job_activity_revision" in constraint_names
    assert "ck_customer_opportunity_suggestion_job_status" in constraint_names
    assert "ck_customer_opportunity_suggestion_job_submission_source" in constraint_names

    create_fks = [call for call in operations.calls if call[0] == "create_foreign_key"]
    assert create_fks == []

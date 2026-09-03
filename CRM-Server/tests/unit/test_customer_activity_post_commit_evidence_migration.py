"""Structural contract tests for migration 120."""

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
            if name == "get_bind":
                return object()

        return record


def _load_migration() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "120_customer_activity_post_commit_job_evidence.py"
    )
    spec = importlib.util.spec_from_file_location("customer_activity_post_commit_evidence_120", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_120_replaces_cascade_with_evidence_foreign_key():
    migration = _load_migration()
    operations = _RecordingOperations()
    migration.op = operations

    migration.upgrade()

    drops = [call for call in operations.calls if call[0] == "drop_constraint"]
    creates = [call for call in operations.calls if call[0] == "create_foreign_key"]
    assert drops == [
        (
            "drop_constraint",
            ("crm_customer_activity_post_commit_jobs_ibfk_1", "crm_customer_activity_post_commit_jobs"),
            {"type_": "foreignkey"},
        )
    ]
    assert creates[0][1] == (
        "fk_customer_activity_post_commit_jobs_activity",
        "crm_customer_activity_post_commit_jobs",
        "crm_customer_activities",
        ["activity_id"],
        ["id"],
    )
    assert creates[0][2] == {"ondelete": None}

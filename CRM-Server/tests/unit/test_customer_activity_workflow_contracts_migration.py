"""Structural contract tests for migration 118."""

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
        Path(__file__).resolve().parents[2] / "migrations" / "versions" / "118_customer_activity_workflow_contracts.py"
    )
    spec = importlib.util.spec_from_file_location("customer_activity_workflow_contracts_118", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_118_has_expected_revision_chain_and_contract_operations():
    migration = _load_migration()
    operations = _RecordingOperations()
    migration.op = operations

    migration.upgrade()

    assert migration.revision == "118_customer_activity_workflow_contracts"
    assert migration.down_revision == "117_remove_legacy_customer_profile_fields"

    alter_calls = [call for call in operations.calls if call[0] == "alter_column"]
    assert alter_calls[0][1][:2] == ("crm_customer_activities", "post_commit_revision")
    assert alter_calls[0][2]["new_column_name"] == "activity_revision"

    added_columns = {
        call[1][1].name
        for call in operations.calls
        if call[0] == "add_column" and call[1][0] == "crm_customer_activities"
    }
    assert added_columns == {"submission_source", "submission_id"}

    unique_constraints = {
        call[1][0]: (call[1][1], tuple(call[1][2]))
        for call in operations.calls
        if call[0] == "create_unique_constraint"
    }
    assert unique_constraints["uq_customer_activity_submission"] == (
        "crm_customer_activities",
        ("team_id", "submission_id"),
    )

    check_names = {call[1][0] for call in operations.calls if call[0] == "create_check_constraint"}
    assert check_names == {
        "ck_customer_activity_submission_source",
        "ck_customer_activity_processing_status",
        "ck_customer_activity_effectiveness_status",
        "ck_customer_activity_post_commit_job_status",
    }

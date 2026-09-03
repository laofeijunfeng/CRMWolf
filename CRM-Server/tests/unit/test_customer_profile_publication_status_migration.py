"""Structural contract for the publication-status compatibility migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_migration() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "126_expand_customer_profile_publication_status.py"
    )
    spec = importlib.util.spec_from_file_location("expand_customer_profile_publication_status_126", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RecordingOperations:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name: str):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))

        return record


def test_publication_status_migration_can_store_canonical_warning_status() -> None:
    migration = _load_migration()
    operations = _RecordingOperations()
    migration.op = operations

    migration.upgrade()

    assert migration.revision == "126_expand_customer_profile_publication_status"
    assert migration.down_revision == "125_merge_activity_and_payment_heads"
    alter = next(call for call in operations.calls if call[0] == "alter_column")
    assert alter[1][:2] == ("crm_customer_profile_projection_versions", "publication_status")
    assert alter[2]["type_"].length >= len("PUBLISHED_WITH_WARNINGS")
    assert alter[2]["existing_type"].length == 20

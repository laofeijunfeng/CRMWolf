from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType


def _load_migration() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "137_datatable_export_permissions.py"
    )
    spec = importlib.util.spec_from_file_location("datatable_export_permissions_137", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_revisions_merge_both_heads() -> None:
    migration = _load_migration()
    assert migration.revision == "137_datatable_export_permissions"
    assert migration.down_revision == (
        "136_business_journey_saved_views",
        "136_customer_initial_enrichment",
    )


def test_migration_declares_nine_export_permissions_for_admin_only() -> None:
    migration = _load_migration()
    codes = {code for _name, code, _resource, _action, _scope in migration.EXPORT_PERMISSIONS}
    assert codes == {
        "customer:export",
        "follow_up_task:export",
        "lead:export",
        "opportunity:export",
        "contract:export",
        "payment:plan:export",
        "payment:record:export",
        "invoice:export",
        "approval:export",
    }
    for role_code, permission_codes in migration.ROLE_PERMISSION_CODES.items():
        assert role_code == "TEAM_ADMIN"
        assert set(permission_codes) == codes

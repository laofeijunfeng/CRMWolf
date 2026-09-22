from pathlib import Path

from app.core.list_export.catalogs import LIST_EXPORT_CATALOGS
from app.core.list_export.manifest import build_list_export_manifest, write_list_export_manifest

CLIENT_MANIFEST = (
    Path(__file__).resolve().parents[4]
    / "CRM-Client"
    / "src"
    / "components"
    / "crmwolf"
    / "listExportCatalogManifest.json"
)


def test_all_core_datatables_have_export_catalogs_without_internal_id() -> None:
    assert set(LIST_EXPORT_CATALOGS) == {
        "approvals",
        "contracts",
        "customers",
        "follow_up_tasks",
        "invoices",
        "leads",
        "opportunities",
        "payment_plans",
        "payment_records",
    }
    for catalog in LIST_EXPORT_CATALOGS.values():
        assert "id" not in {export_field.key for export_field in catalog.fields}


def test_manifest_contains_user_facing_contract() -> None:
    manifest = build_list_export_manifest(LIST_EXPORT_CATALOGS)
    assert manifest["customers"]["public_id"] == {"label": "业务 ID", "type": "text"}
    assert manifest["payment_records"]["actual_amount"] == {"label": "回款金额", "type": "currency"}


def test_committed_export_manifest_matches_backend(tmp_path: Path) -> None:
    generated = tmp_path / "listExportCatalogManifest.json"
    write_list_export_manifest(generated, LIST_EXPORT_CATALOGS)
    assert CLIENT_MANIFEST.read_text(encoding="utf-8") == generated.read_text(encoding="utf-8")

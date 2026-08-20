import json
from pathlib import Path

from app.core.list_query.catalogs import LIST_QUERY_CATALOGS
from app.core.list_query.manifest import build_list_query_manifest, write_list_query_manifest

CLIENT_MANIFEST = (
    Path(__file__).resolve().parents[4]
    / "CRM-Client"
    / "src"
    / "components"
    / "crmwolf"
    / "listQueryCatalogManifest.json"
)


def test_build_list_query_manifest_exposes_each_catalog_field_type():
    manifest = build_list_query_manifest(LIST_QUERY_CATALOGS)

    assert manifest["customers"]["license_status"] == {
        "type": "enum",
        "filterable": True,
        "sortable": True,
        "ops": ["contains", "eq", "in", "is_empty", "is_not_empty", "neq", "not_contains", "not_in"],
    }
    assert manifest["customers"]["license_expiry_date"]["type"] == "date"
    assert manifest["payment_plans"]["planned_amount"]["type"] == "number"
    assert manifest["approvals"]["overdue_hours"]["sortable"] is True
    assert manifest["payment_records"]["approval_status"]["sortable"] is True


def test_committed_client_manifest_matches_backend_catalogs(tmp_path):
    generated_path = tmp_path / "listQueryCatalogManifest.json"
    write_list_query_manifest(generated_path, LIST_QUERY_CATALOGS)

    assert CLIENT_MANIFEST.exists()
    assert json.loads(CLIENT_MANIFEST.read_text(encoding="utf-8")) == json.loads(
        generated_path.read_text(encoding="utf-8")
    )

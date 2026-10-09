"""Customer license authorized-user response and catalog contracts."""

from datetime import datetime

from app.core.list_export.catalogs import LIST_EXPORT_CATALOGS
from app.core.list_query.catalogs.customers import CUSTOMERS_LIST_QUERY_CATALOG
from app.schemas.customer import CustomerDetailResponse, CustomerResponse, CustomerListResponse
from app.api.customers import _customer_export_row


def _valid_customer_payload(*, license_authorized_users: int | None = None) -> dict:
    return {
        "id": "cus_contract",
        "public_id": "cus_contract",
        "account_name": "契约客户",
        "city": "上海",
        "status": 0,
        "creator_id": "tester",
        "created_time": datetime(2026, 1, 1, 9, 0, 0),
        "last_modified_time": datetime(2026, 1, 1, 9, 0, 0),
        "version": 1,
        "license_expiry_date": None,
        "license_authorized_users": license_authorized_users,
        "license_type": None,
    }


def test_customer_response_and_detail_response_accept_nullable_authorized_users():
    payload = _valid_customer_payload(license_authorized_users=32)

    assert CustomerResponse.model_validate(payload).license_authorized_users == 32
    assert CustomerDetailResponse.model_validate({**payload, "contacts": []}).license_authorized_users == 32
    assert CustomerResponse.model_validate(_valid_customer_payload()).license_authorized_users is None


def test_customer_query_catalog_exposes_numeric_authorized_users_between_license_fields():
    keys = [field.key for field in CUSTOMERS_LIST_QUERY_CATALOG.fields]
    assert keys[keys.index("license_status") : keys.index("license_expiry_date") + 1] == [
        "license_status",
        "license_authorized_users",
        "license_expiry_date",
    ]

    field = CUSTOMERS_LIST_QUERY_CATALOG.require("license_authorized_users")
    assert field.type == "number"
    assert field.supports_filtering() and field.supports_sorting()


def test_customer_export_exposes_authorized_users_between_license_fields():
    fields = LIST_EXPORT_CATALOGS["customers"].fields
    selected = [
        field
        for field in fields
        if field.key in {"license_status", "license_authorized_users", "license_expiry_date"}
    ]

    assert [(field.key, field.label, field.cell_type) for field in selected] == [
        ("license_status", "授权状态", "text"),
        ("license_authorized_users", "授权人数", "number"),
        ("license_expiry_date", "授权到期", "date"),
    ]


def test_customer_export_row_projects_authorized_users():
    item = CustomerListResponse.model_validate(_valid_customer_payload(license_authorized_users=32))

    assert _customer_export_row(item)["license_authorized_users"] == 32
    assert item.license_authorized_users == 32

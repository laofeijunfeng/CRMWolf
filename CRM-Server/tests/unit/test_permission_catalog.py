from app.constants.permissions import (
    ALL_PERMISSIONS,
    DEPRECATED_PERMISSION_CODES,
    ROLE_PERMISSIONS_MAPPING,
)


def test_deprecated_api_permissions_are_not_assignable_system_permissions() -> None:
    active_codes = {permission["code"] for permission in ALL_PERMISSIONS}

    assert DEPRECATED_PERMISSION_CODES.isdisjoint(active_codes)
    assert all(
        permission["resource"] not in {"api", "apikey"}
        for permission in ALL_PERMISSIONS
    )


EXPORT_PERMISSION_CODES = {
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


def test_datatable_export_permissions_are_assignable_and_admin_only_by_default() -> None:
    active = {item["code"] for item in ALL_PERMISSIONS}
    assert active >= EXPORT_PERMISSION_CODES
    assert ROLE_PERMISSIONS_MAPPING["TEAM_ADMIN"] == "all"
    for role_code in ("SALES_DIRECTOR", "SALES_MEMBER", "FINANCE"):
        assert EXPORT_PERMISSION_CODES.isdisjoint(ROLE_PERMISSIONS_MAPPING[role_code])

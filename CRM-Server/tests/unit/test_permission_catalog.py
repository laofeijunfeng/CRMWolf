from app.constants.permissions import ALL_PERMISSIONS, DEPRECATED_PERMISSION_CODES


def test_deprecated_api_permissions_are_not_assignable_system_permissions() -> None:
    active_codes = {permission["code"] for permission in ALL_PERMISSIONS}

    assert DEPRECATED_PERMISSION_CODES.isdisjoint(active_codes)
    assert all(
        permission["resource"] not in {"api", "apikey"}
        for permission in ALL_PERMISSIONS
    )

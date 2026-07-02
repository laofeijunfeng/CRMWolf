from app.constants.permissions import ALL_PERMISSIONS, ROLE_PERMISSIONS_MAPPING


def test_payment_approve_codes_exist():
    codes = {p["code"] for p in ALL_PERMISSIONS}
    assert "payment:submit" in codes
    assert "payment:approve" in codes
    assert "payment:approve:own" in codes
    assert "payment:approve:all" in codes


def test_invoice_approve_own_all_exist():
    codes = {p["code"] for p in ALL_PERMISSIONS}
    assert "invoice:approve:own" in codes
    assert "invoice:approve:all" in codes


def test_finance_has_payment_approve():
    finance_perms = ROLE_PERMISSIONS_MAPPING["FINANCE"]
    assert "payment:approve" in finance_perms or "payment:approve:all" in finance_perms
    assert "payment:submit" in finance_perms


def test_sales_director_has_own_approvals():
    sd_perms = ROLE_PERMISSIONS_MAPPING["SALES_DIRECTOR"]
    assert "payment:approve:own" in sd_perms
    assert "invoice:approve:own" in sd_perms


def test_new_permission_codes_have_consistent_fields():
    """新增权限码 dict 字段格式须与既有一致（resource/action 必须，own/all 含 scope）。"""
    by_code = {p["code"]: p for p in ALL_PERMISSIONS}
    expected = {
        "payment:submit": ("payment", "submit", None),
        "payment:withdraw": ("payment", "withdraw", None),
        "payment:approve": ("payment", "approve", None),
        "payment:approve:own": ("payment", "approve", "own"),
        "payment:approve:all": ("payment", "approve", "all"),
        "invoice:approve:own": ("invoice", "approve", "own"),
        "invoice:approve:all": ("invoice", "approve", "all"),
    }
    for code, (resource, action, scope) in expected.items():
        assert code in by_code, f"missing code {code}"
        p = by_code[code]
        assert p["name"], f"{code} missing name"
        assert p["resource"] == resource, f"{code} resource mismatch"
        assert p["action"] == action, f"{code} action mismatch"
        if scope is None:
            assert "scope" not in p, f"{code} should not have scope"
        else:
            assert p.get("scope") == scope, f"{code} scope mismatch"


def test_existing_invoice_approve_preserved():
    """不删既有 flat invoice:approve 以保持兼容。"""
    codes = {p["code"] for p in ALL_PERMISSIONS}
    assert "invoice:approve" in codes
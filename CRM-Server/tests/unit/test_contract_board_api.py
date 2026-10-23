"""Contract board aggregation uses the complete authorized population."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

from app.api import contracts as contracts_api
from app.core import database, deps
from app.models.approval import Approval, ApprovalFlow, ApprovalNode, ApprovalStatus
from app.models.contract import Contract
from app.models.customer import Customer, CustomerProduct
from app.models.product import Product
from app.models.license_application import LicenseApplication
from app.models.opportunity import Opportunity
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User, UserStatus
from app.models.user_role import UserRole


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


COLUMN_KEYS = (
    "DRAFT",
    "PENDING_REVIEW",
    "SIGNED",
    "EFFECTIVE",
    "EXPIRED",
    "TERMINATED",
    "UNCLASSIFIED",
)
COLUMN_LABELS = {
    "DRAFT": "草稿",
    "PENDING_REVIEW": "待审核",
    "SIGNED": "已签署",
    "EFFECTIVE": "已生效",
    "EXPIRED": "已到期",
    "TERMINATED": "已终止",
    "UNCLASSIFIED": "未分类",
}
COLUMN_TONES = {
    "DRAFT": "neutral",
    "PENDING_REVIEW": "warning",
    "SIGNED": "success",
    "EFFECTIVE": "success",
    "EXPIRED": "muted",
    "TERMINATED": "danger",
    "UNCLASSIFIED": "muted",
}
SUMMARY_KEYS = ("total_count", "pending_review_count", "total_amount", "signed_effective_amount")
SUMMARY_LABELS = {
    "total_count": "合同",
    "pending_review_count": "待审",
    "total_amount": "合同金额",
    "signed_effective_amount": "生效金额",
}


def _customer(customer_id: int, *, name: str, owner_id: str = "7") -> Customer:
    return Customer(
        id=customer_id,
        public_id=f"cus_{customer_id}",
        team_id=1,
        account_name=name,
        city="上海",
        status=0,
        owner_id=owner_id,
        creator_id=owner_id,
        created_time=datetime(2026, 4, 1),
        last_modified_time=datetime(2026, 4, 1),
    )


def _opportunity(
    opportunity_id: int,
    *,
    name: str,
    customer_id: int,
    purchase_type: str = "NEW",
    owner_id: str = "7",
) -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        public_id=f"opp_{opportunity_id:02d}",
        team_id=1,
        opportunity_number=f"OPP-{opportunity_id:04d}",
        opportunity_name=name,
        customer_id=customer_id,
        total_amount=Decimal("100.00"),
        user_count=10,
        unit_price=Decimal("10.00"),
        license_type="SUBSCRIPTION",
        subscription_years=1,
        purchase_type=purchase_type,
        expected_closing_date=date(2026, 9, 1),
        win_probability=50,
        owner_id=owner_id,
        creator_id=owner_id,
        status=0,
        approval_phase="approved",
        created_time=datetime(2026, 4, 1),
        last_modified_time=datetime(2026, 4, 1),
    )


def _contract(
    contract_id: int,
    *,
    name: str,
    status: str = "DRAFT",
    total_amount: str = "100.00",
    customer_id: int = 1,
    opportunity_id: int = 1,
    owner_id: str = "7",
    creator_id: str | None = None,
    signing_date: date | None = date(2026, 5, 1),
    effective_date: date | None = date(2026, 5, 2),
    expiry_date: date | None = date(2027, 5, 1),
    user_count: int = 10,
    team_id: int = 1,
    deleted_at: datetime | None = None,
    approval_phase: str = "draft",
    license_type: str = "SUBSCRIPTION",
    subscription_years: int | None = 1,
    standard_unit_price: str = "10.00",
    contract_number: str | None = None,
) -> Contract:
    return Contract(
        id=contract_id,
        team_id=team_id,
        contract_number=contract_number or f"CT-{contract_id:04d}",
        contract_name=name,
        customer_id=customer_id,
        opportunity_id=opportunity_id,
        user_count=user_count,
        total_amount=Decimal(total_amount),
        license_type=license_type,
        subscription_years=subscription_years,
        standard_unit_price=Decimal(standard_unit_price),
        status=status,
        approval_phase=approval_phase,
        signing_date=signing_date,
        effective_date=effective_date,
        expiry_date=expiry_date,
        owner_id=owner_id,
        creator_id=creator_id or owner_id,
        created_time=datetime(2026, 4, contract_id if contract_id <= 28 else 28),
        last_modified_time=datetime(2026, 4, 1),
        deleted_at=deleted_at,
    )


def _license(
    license_id: int,
    *,
    contract_id: int,
    authorized_users: int,
    expiry_date: date,
    modified: datetime,
    license_type: str = "OFFICIAL",
    status: str = "ISSUED",
    team_id: int = 1,
) -> LicenseApplication:
    return LicenseApplication(
        id=license_id,
        team_id=team_id,
        application_number=f"LA-{license_id:04d}",
        customer_id=1,
        contract_id=contract_id,
        expiry_date=expiry_date,
        license_type=license_type,
        authorized_users=authorized_users,
        status=status,
        applicant_id="7",
        created_time=modified,
        last_modified_time=modified,
    )


@pytest.fixture
def api_env():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        User.__table__,
        Role.__table__,
        Permission.__table__,
        RolePermission.__table__,
        UserRole.__table__,
        Customer.__table__,
        Product.__table__,
        CustomerProduct.__table__,
        Opportunity.__table__,
        Contract.__table__,
        LicenseApplication.__table__,
        ApprovalFlow.__table__,
        ApprovalNode.__table__,
        Approval.__table__,
    ]
    with engine.begin() as connection:
        for table in tables:
            connection.execute(CreateTable(table))
    session = sessionmaker(bind=engine)()
    current_user = SimpleNamespace(id=7, name="销售张", status="active")
    session.add(User(id=7, email="owner@example.com", name="销售张", avatar_url="https://cdn.example/ada.png", status=UserStatus.ACTIVE))
    session.add(User(id=8, email="other@example.com", name="销售李", status=UserStatus.ACTIVE))
    session.add(_customer(1, name="甲客户"))
    session.add(_customer(2, name="乙客户", owner_id="8"))
    session.add(_opportunity(1, name="甲商机", customer_id=1, purchase_type="RENEWAL"))
    session.add(_opportunity(2, name="乙商机", customer_id=2, purchase_type="NEW", owner_id="8"))
    session.commit()

    app = FastAPI()
    app.include_router(contracts_api.router)
    app.dependency_overrides[database.get_db] = lambda: session
    app.dependency_overrides[deps.get_db] = lambda: session
    app.dependency_overrides[contracts_api.get_db] = lambda: session
    app.dependency_overrides[deps.get_current_user_team] = lambda: 1
    app.dependency_overrides[contracts_api.get_current_user_team] = lambda: 1
    app.dependency_overrides[deps.get_current_active_user] = lambda: current_user
    app.dependency_overrides[contracts_api.get_current_active_user] = lambda: current_user

    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=session, current_user=current_user, app=app)

    session.close()
    engine.dispose()


def _grant(db, user_id: int, *codes: str, role_code: str | None = None) -> None:
    role = Role(
        name=f"角色{user_id}-{'-'.join(codes)}",
        code=role_code or f"role-{user_id}-{len(codes)}-{codes[0]}",
    )
    db.add(role)
    db.flush()
    for code in codes:
        permission = db.query(Permission).filter(Permission.code == code).one_or_none()
        if permission is None:
            parts = code.split(":")
            permission = Permission(
                name=code,
                code=code,
                resource=parts[0],
                action=parts[1],
            )
            db.add(permission)
            db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db.add(UserRole(user_id=user_id, role_id=role.id, team_id=1))
    db.commit()


def _board(client: TestClient, **params):
    return client.get("/v1/contracts/board", params=params)


def _columns(body: dict) -> dict[str, dict]:
    return {column["key"]: column for column in body["columns"]}


def _metric(body: dict, key: str) -> dict:
    return next(metric for metric in body["summary"] if metric["key"] == key)


def _pending_approval(db, contract_id: int, *, approve_role: str = "SALES_DIRECTOR") -> None:
    flow = ApprovalFlow(id=contract_id, team_id=1, flow_name="合同审批", flow_code=f"contract-{contract_id}", business_type="CONTRACT")
    node = ApprovalNode(
        id=contract_id,
        team_id=1,
        flow_id=contract_id,
        node_name="销售总监",
        node_code=f"director-{contract_id}",
        node_order=1,
        approve_role=approve_role,
    )
    approval = Approval(
        id=contract_id,
        team_id=1,
        contract_id=contract_id,
        business_type="CONTRACT",
        business_id=contract_id,
        flow_id=contract_id,
        current_node_id=contract_id,
        status=ApprovalStatus.PENDING,
        submitter_id="7",
    )
    db.add_all([flow, node, approval])


def test_board_route_precedes_dynamic_contract_route() -> None:
    board_route = next(route for route in contracts_api.router.routes if getattr(route, "path", None) == "/v1/contracts/board")
    detail_route = next(route for route in contracts_api.router.routes if getattr(route, "path", None) == "/v1/contracts/{contract_id}")
    assert contracts_api.router.routes.index(board_route) < contracts_api.router.routes.index(detail_route)
    query_names = set(board_route.dependant.query_params)
    assert {"skip", "limit", "page", "page_size", "include_deleted", "user_id"}.isdisjoint(query_names)


def test_board_groups_fixed_lifecycle_columns_and_unknown_status(api_env, monkeypatch) -> None:
    class _FrozenDate(date):
        @classmethod
        def today(cls) -> date:
            return date(2026, 10, 12)

    monkeypatch.setattr(contracts_api, "date", _FrozenDate)
    api_env.db.add_all([
        _contract(1, name="草稿甲", status="DRAFT", total_amount="10.10", signing_date=date(2026, 5, 2), user_count=8),
        _contract(2, name="待审甲", status="PENDING_REVIEW", total_amount="20.00", signing_date=date(2026, 6, 3), approval_phase="pending_review"),
        _contract(3, name="已签署甲", status="SIGNED", total_amount="30.25", signing_date=date(2026, 7, 4)),
        _contract(4, name="已生效甲", status="EFFECTIVE", total_amount="40.00", signing_date=date(2026, 8, 5)),
        _contract(5, name="已到期甲", status="EXPIRED", total_amount="50.00", signing_date=date(2026, 4, 6)),
        _contract(6, name="已终止甲", status="TERMINATED", total_amount="60.00", signing_date=date(2026, 9, 7)),
        _contract(7, name="未知状态", status="ARCHIVED", total_amount="70.00", signing_date=date(2026, 9, 8)),
        _contract(8, name="其他团队", status="SIGNED", total_amount="1000.00", team_id=2, signing_date=date(2026, 8, 1)),
        _contract(9, name="已删除", status="SIGNED", total_amount="500.00", deleted_at=datetime(2026, 8, 1), signing_date=date(2026, 8, 1)),
        _license(1, contract_id=1, authorized_users=3, expiry_date=date(2026, 1, 1), modified=datetime(2026, 1, 1)),
        _license(2, contract_id=1, authorized_users=25, expiry_date=date(2027, 8, 1), modified=datetime(2026, 6, 1)),
        _license(3, contract_id=1, authorized_users=99, expiry_date=date(2028, 1, 1), modified=datetime(2026, 7, 1), license_type="TRIAL"),
        _license(4, contract_id=1, authorized_users=12, expiry_date=date(2026, 12, 1), modified=datetime(2026, 8, 1), status="DRAFT"),
    ])
    _pending_approval(api_env.db, 2)
    api_env.db.commit()
    _grant(
        api_env.db,
        7,
        "contract:view:all",
        "contract:edit:own",
        "contract:delete:own",
        "contract:submit",
        "contract:approve:all",
        "contract:approve:own",
        role_code="SALES_DIRECTOR",
    )

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    body = response.json()
    columns = _columns(body)
    assert list(columns) == list(COLUMN_KEYS)
    assert {key: columns[key]["label"] for key in COLUMN_KEYS} == COLUMN_LABELS
    assert {key: columns[key]["tone"] for key in COLUMN_KEYS} == COLUMN_TONES
    assert columns["DRAFT"]["count"] == 1
    assert columns["DRAFT"]["amount"] == "10.10"
    assert columns["PENDING_REVIEW"]["count"] == 1
    assert columns["SIGNED"]["amount"] == "30.25"
    assert columns["EFFECTIVE"]["amount"] == "40.00"
    assert columns["EXPIRED"]["count"] == 1
    assert columns["TERMINATED"]["count"] == 1
    assert columns["UNCLASSIFIED"]["count"] == 1
    assert columns["UNCLASSIFIED"]["amount"] == "70.00"
    assert columns["UNCLASSIFIED"]["items"][0]["status"] == "UNCLASSIFIED"
    assert all(item["id"] not in {8, 9} for column in columns.values() for item in column["items"])

    draft = columns["DRAFT"]["items"][0]
    assert draft["id"] == 1
    assert draft["title"] == "草稿甲"
    assert draft["subtitle"] == "CT-0001"
    assert draft["amount"] == "10.10"
    assert draft["date"] == "2026-05-02"
    assert draft["owner"] == {"id": "7", "name": "销售张", "avatar_url": "https://cdn.example/ada.png"}
    assert draft["metadata"] == {
        "customer_name": "甲客户",
        "opportunity_name": "甲商机",
        "license_type": "SUBSCRIPTION",
        "purchase_type": "RENEWAL",
        "signing_date": "2026-05-02",
        "effective_date": "2026-05-02",
        "expiry_date": "2027-05-01",
        "license_expiry_date": "2027-08-01",
        "authorized_users": 25,
    }
    assert draft["action_state"] == {
        "can_edit": True,
        "can_delete": True,
        "can_submit_approval": True,
        "can_approve": False,
        "can_reject": False,
    }
    pending = columns["PENDING_REVIEW"]["items"][0]
    assert pending["action_state"]["can_edit"] is False
    assert pending["action_state"]["can_delete"] is False
    assert pending["action_state"]["can_submit_approval"] is False
    assert pending["action_state"]["can_approve"] is True
    assert pending["action_state"]["can_reject"] is True

    assert [metric["key"] for metric in body["summary"]] == list(SUMMARY_KEYS)
    assert [metric["label"] for metric in body["summary"]] == [SUMMARY_LABELS[key] for key in SUMMARY_KEYS]
    assert _metric(body, "total_count")["value"] == 7
    assert _metric(body, "pending_review_count")["value"] == 1
    assert _metric(body, "total_amount")["value"] == "280.35"
    assert _metric(body, "signed_effective_amount")["value"] == "70.25"
    assert {point["date"]: (point["count"], point["amount"]) for point in body["trends"]} == {
        "2026-04": (1, "50.00"),
        "2026-05": (1, "10.10"),
        "2026-06": (1, "20.00"),
        "2026-07": (1, "30.25"),
        "2026-08": (1, "40.00"),
        "2026-09": (2, "130.00"),
    }


def test_board_preview_keeps_full_column_totals_and_empty_columns(api_env) -> None:
    rows = []
    for index in range(1, 8):
        rows.append(_contract(
            index,
            name=f"草稿{index:02d}",
            status="DRAFT",
            total_amount=f"{index}.00",
            signing_date=date(2026, 5, index),
            effective_date=date(2026, 6, index),
        ))
    api_env.db.add_all(rows)
    api_env.db.commit()
    _grant(api_env.db, 7, "contract:view:all")

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    body = response.json()
    columns = _columns(body)
    column = columns["DRAFT"]
    assert column["count"] == 7
    assert [item["id"] for item in column["items"]] == [7, 6, 5, 4, 3, 2, 1]
    assert column["has_more"] is False
    assert column["remaining_count"] == 0
    assert column["amount"] == "28.00"
    assert _metric(body, "total_count")["value"] == 7
    assert _metric(body, "total_amount")["value"] == "28.00"
    assert _metric(body, "signed_effective_amount")["value"] == "0.00"
    for key in COLUMN_KEYS:
        if key == "DRAFT":
            continue
        assert columns[key]["count"] == 0
        assert columns[key]["items"] == []
        assert columns[key]["has_more"] is False
        assert columns[key]["remaining_count"] == 0
        assert columns[key]["amount"] == "0.00"


def test_empty_authorized_population_returns_columns_and_zero_summary(api_env) -> None:
    api_env.db.add(_contract(1, name="其他团队", team_id=2))
    api_env.db.commit()
    _grant(api_env.db, 7, "contract:view:all")

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    body = response.json()
    columns = _columns(body)
    assert list(columns) == list(COLUMN_KEYS)
    assert all(column["count"] == 0 and column["items"] == [] and column["amount"] == "0.00" for column in columns.values())
    assert _metric(body, "total_count")["value"] == 0
    assert _metric(body, "pending_review_count")["value"] == 0
    assert _metric(body, "total_amount")["value"] == "0.00"
    assert _metric(body, "signed_effective_amount")["value"] == "0.00"
    assert body["trends"] == []


def test_latest_license_falls_back_to_contract_user_count(api_env) -> None:
    api_env.db.add_all([
        _contract(1, name="无正式许可", status="SIGNED", user_count=18, total_amount="11.00"),
        _contract(2, name="仅试用许可", status="SIGNED", user_count=4, total_amount="12.00"),
        _license(1, contract_id=2, authorized_users=80, expiry_date=date(2028, 1, 1), modified=datetime(2026, 8, 1), license_type="TRIAL"),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "contract:view:all")

    response = _board(api_env.client, license_authorized_users=18)

    assert response.status_code == 200, response.text
    items = _columns(response.json())["SIGNED"]["items"]
    assert [item["id"] for item in items] == [1]
    assert items[0]["metadata"]["authorized_users"] == 18
    assert items[0]["metadata"]["license_expiry_date"] is None


def test_signing_date_bounds_and_complete_population_totals(api_env, monkeypatch) -> None:
    class _FrozenDate(date):
        @classmethod
        def today(cls) -> date:
            return date(2026, 10, 12)

    monkeypatch.setattr(contracts_api, "date", _FrozenDate)
    api_env.db.add_all([
        _contract(1, name="窗口内甲", status="SIGNED", total_amount="10.00", signing_date=date(2026, 6, 15)),
        _contract(2, name="窗口内乙", status="EFFECTIVE", total_amount="20.50", signing_date=date(2026, 6, 20)),
        _contract(3, name="窗口外", status="SIGNED", total_amount="99.00", signing_date=date(2026, 8, 15)),
        _contract(4, name="无签署日", status="DRAFT", total_amount="5.00", signing_date=None),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "contract:view:all")

    response = _board(
        api_env.client,
        signing_date_start="2026-06-01",
        signing_date_end="2026-06-30",
        search="窗口",
    )

    assert response.status_code == 200, response.text
    body = response.json()
    columns = _columns(body)
    assert columns["SIGNED"]["count"] == 1
    assert columns["EFFECTIVE"]["count"] == 1
    assert columns["DRAFT"]["count"] == 0
    assert _metric(body, "total_count")["value"] == 2
    assert _metric(body, "total_amount")["value"] == "30.50"
    assert _metric(body, "signed_effective_amount")["value"] == "30.50"
    assert body["trends"] == [{"date": "2026-06", "count": 2, "amount": "30.50"}]


def test_unified_signing_bounds_ignore_legacy_dates(api_env, monkeypatch) -> None:
    class _FrozenDate(date):
        @classmethod
        def today(cls) -> date:
            return date(2026, 10, 12)

    monkeypatch.setattr(contracts_api, "date", _FrozenDate)
    api_env.db.add_all([
        _contract(1, name="窗口内", status="SIGNED", total_amount="10.00", signing_date=date(2026, 6, 15)),
        _contract(2, name="窗口外", status="SIGNED", total_amount="20.00", signing_date=date(2026, 8, 15)),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "contract:view:all")

    response = _board(
        api_env.client,
        signing_date_start="2026-08-01",
        signing_date_end="2026-08-31",
        filters='[{"field":"signing_date","op":"after","value":"2026-06-01"},{"field":"signing_date","op":"before","value":"2026-06-30"}]',
        sorts="[]",
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert _columns(body)["SIGNED"]["count"] == 1
    assert _columns(body)["SIGNED"]["items"][0]["id"] == 1
    assert _metric(body, "total_amount")["value"] == "10.00"
    assert body["trends"] == [{"date": "2026-06", "count": 1, "amount": "10.00"}]


def test_sorting_changes_preview_order_only(api_env, monkeypatch) -> None:
    class _FrozenDate(date):
        @classmethod
        def today(cls) -> date:
            return date(2026, 10, 12)

    monkeypatch.setattr(contracts_api, "date", _FrozenDate)
    signings = [
        date(2026, 6, 3),
        date(2026, 6, 1),
        date(2026, 6, 1),
        date(2026, 6, 9),
        date(2026, 6, 2),
        date(2026, 6, 4),
        date(2026, 6, 5),
    ]
    effectives = [
        date(2026, 7, 1),
        date(2026, 7, 3),
        date(2026, 7, 1),
        date(2026, 7, 1),
        date(2026, 7, 1),
        date(2026, 7, 1),
        date(2026, 7, 1),
    ]
    amounts = ["10.00", "30.00", "40.00", "99.00", "20.00", "5.00", "4.00"]
    rows = []
    for index, (signing, effective, amount) in enumerate(zip(signings, effectives, amounts, strict=True), start=1):
        rows.append(_contract(
            index,
            name=f"合同{index}",
            status="SIGNED",
            total_amount=amount,
            signing_date=signing,
            effective_date=effective,
        ))
    api_env.db.add_all(rows)
    api_env.db.commit()
    _grant(api_env.db, 7, "contract:view:all")

    default_response = _board(api_env.client)
    sorted_response = _board(api_env.client, order_by="contract_name", order_dir="desc")

    assert default_response.status_code == 200, default_response.text
    assert sorted_response.status_code == 200, sorted_response.text
    default_body = default_response.json()
    sorted_body = sorted_response.json()
    assert [item["id"] for item in _columns(default_body)["SIGNED"]["items"]] == [4, 7, 6, 1, 5, 2, 3]
    assert [item["id"] for item in _columns(sorted_body)["SIGNED"]["items"]] == [7, 6, 5, 4, 3, 2, 1]
    assert [metric["value"] for metric in default_body["summary"]] == [
        metric["value"] for metric in sorted_body["summary"]
    ]
    assert default_body["trends"] == sorted_body["trends"]
    assert _columns(default_body)["SIGNED"]["count"] == 7
    assert _columns(default_body)["SIGNED"]["amount"] == _columns(sorted_body)["SIGNED"]["amount"]
    assert _metric(default_body, "total_amount")["value"] == "208.00"
    assert _metric(default_body, "signed_effective_amount")["value"] == "208.00"


def test_owner_permission_uses_contract_view_scope(api_env) -> None:
    api_env.db.add_all([
        _contract(1, name="自己的合同", owner_id="7"),
        _contract(2, name="别人的合同", customer_id=2, opportunity_id=2, owner_id="8"),
    ])
    api_env.db.commit()

    forbidden = _board(api_env.client, owner_id="8")
    own = _board(api_env.client)

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "只能查看自己负责的合同，或需要 contract:view:all 权限查看他人数据"
    assert own.status_code == 200, own.text
    assert _columns(own.json())["DRAFT"]["count"] == 1
    assert _columns(own.json())["DRAFT"]["items"][0]["id"] == 1


def test_own_scope_customer_filter_excludes_another_owners_contracts(api_env) -> None:
    api_env.db.add_all([
        _contract(1, name="自己的合同", customer_id=2, opportunity_id=2, owner_id="7"),
        _contract(2, name="别人的合同", customer_id=2, opportunity_id=2, owner_id="8", status="SIGNED", total_amount="250.00"),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "contract:view:own", "customer:view:all")

    response = _board(api_env.client, customer_id="cus_2")

    assert response.status_code == 200, response.text
    body = response.json()
    columns = _columns(body)
    assert columns["DRAFT"]["count"] == 1
    assert columns["DRAFT"]["items"][0]["id"] == 1
    assert columns["SIGNED"]["count"] == 0
    assert columns["SIGNED"]["items"] == []
    assert all(item["id"] != 2 for column in columns.values() for item in column["items"])
    assert _metric(body, "total_count")["value"] == 1
    assert _metric(body, "total_amount")["value"] == "100.00"


def test_customer_filter_resolves_public_id_before_population_query(api_env) -> None:
    api_env.db.add_all([
        _contract(1, name="甲的合同", customer_id=1, opportunity_id=1, owner_id="7"),
        _contract(2, name="乙的合同", customer_id=2, opportunity_id=2, owner_id="8", status="SIGNED"),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "contract:view:all", "customer:view:all")

    response = _board(api_env.client, customer_id="cus_2")

    assert response.status_code == 200, response.text
    column = _columns(response.json())["SIGNED"]
    assert column["count"] == 1
    assert column["items"][0]["id"] == 2
    assert column["items"][0]["metadata"]["customer_name"] == "乙客户"
    assert column["items"][0]["action_state"]["can_edit"] is False


def test_node_role_user_can_approve_another_users_contract_without_approve_all(api_env) -> None:
    api_env.db.add(_contract(
        1,
        name="他人待审",
        status="PENDING_REVIEW",
        approval_phase="pending_review",
        creator_id="8",
        owner_id="8",
    ))
    _pending_approval(api_env.db, 1, approve_role="SALES_DIRECTOR")
    api_env.db.commit()
    _grant(api_env.db, 7, "contract:view:all", role_code="SALES_DIRECTOR")

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    actions = _columns(response.json())["PENDING_REVIEW"]["items"][0]["action_state"]
    assert actions["can_approve"] is True
    assert actions["can_reject"] is True


def test_wrong_node_role_cannot_approve_even_with_approve_all(api_env) -> None:
    api_env.db.add(_contract(
        1,
        name="自建待审",
        status="PENDING_REVIEW",
        approval_phase="pending_review",
        creator_id="7",
        owner_id="7",
    ))
    _pending_approval(api_env.db, 1, approve_role="SALES_DIRECTOR")
    api_env.db.commit()
    _grant(api_env.db, 7, "contract:view:all", "contract:approve:all", "contract:approve:own", role_code="FINANCE")

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    actions = _columns(response.json())["PENDING_REVIEW"]["items"][0]["action_state"]
    assert actions["can_approve"] is False
    assert actions["can_reject"] is False




def test_approve_own_is_required_only_for_contracts_created_by_current_user(api_env) -> None:
    api_env.db.add_all([
        _contract(
            1,
            name="自己创建的待审",
            status="PENDING_REVIEW",
            approval_phase="pending_review",
            creator_id="7",
            owner_id="8",
        ),
        _contract(
            2,
            name="他人创建的待审",
            status="PENDING_REVIEW",
            approval_phase="pending_review",
            creator_id="8",
            owner_id="7",
        ),
    ])
    _pending_approval(api_env.db, 1, approve_role="SALES_DIRECTOR")
    _pending_approval(api_env.db, 2, approve_role="SALES_DIRECTOR")
    api_env.db.commit()
    _grant(api_env.db, 7, "contract:view:all", role_code="SALES_DIRECTOR")

    denied = _board(api_env.client)

    assert denied.status_code == 200, denied.text
    denied_items = {item["id"]: item for item in _columns(denied.json())["PENDING_REVIEW"]["items"]}
    assert denied_items[1]["action_state"]["can_approve"] is False
    assert denied_items[1]["action_state"]["can_reject"] is False
    assert denied_items[2]["action_state"]["can_approve"] is True
    assert denied_items[2]["action_state"]["can_reject"] is True

    _grant(api_env.db, 7, "contract:view:all", "contract:approve:own", role_code="SALES_DIRECTOR")
    allowed = _board(api_env.client)

    assert allowed.status_code == 200, allowed.text
    allowed_items = {item["id"]: item for item in _columns(allowed.json())["PENDING_REVIEW"]["items"]}
    assert allowed_items[1]["action_state"]["can_approve"] is True
    assert allowed_items[1]["action_state"]["can_reject"] is True
    assert allowed_items[2]["action_state"]["can_approve"] is True
    assert allowed_items[2]["action_state"]["can_reject"] is True

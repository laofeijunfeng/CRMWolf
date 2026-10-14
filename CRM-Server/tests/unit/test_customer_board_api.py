"""Customer board aggregation is computed from the complete authorized population."""

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

from app.api import customers as customers_api
from app.core import database, deps
from app.models.acquisition_source import AcquisitionSource
from app.models.contract import Contract
from app.models.customer import Customer, CustomerMember, CustomerProduct
from app.models.customer_identity_term import CustomerIdentityTerm
from app.models.deal_journey import CustomerDealJourney, DealJourneyStatus
from app.models.invoice import InvoiceApplication
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan, PaymentRecord
from app.models.permission import Permission
from app.models.product import Product
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User, UserStatus
from app.models.user_role import UserRole


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


COLUMN_KEYS = ("not_started", "following", "repurchasing", "won", "lost")
COLUMN_LABELS = {
    "not_started": "未启动",
    "following": "跟进中",
    "repurchasing": "复购中",
    "won": "已成交",
    "lost": "已流失",
}
COLUMN_TONES = {
    "not_started": "neutral",
    "following": "info",
    "repurchasing": "warning",
    "won": "success",
    "lost": "danger",
}
COUNT_LABELS = {
    "total_count": "客户",
    "following_count": "跟进",
    "repurchasing_count": "复购",
    "won_count": "成交",
    "recent_new_count": "新增",
}
PERCENTAGE_LABELS = {
    "not_started_percentage": "未开始占比",
    "following_percentage": "跟进占比",
    "repurchasing_percentage": "复购占比",
    "won_percentage": "成交占比",
    "lost_percentage": "流失占比",
}


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
        AcquisitionSource.__table__,
        Customer.__table__,
        CustomerMember.__table__,
        CustomerIdentityTerm.__table__,
        Product.__table__,
        CustomerProduct.__table__,
        Opportunity.__table__,
        CustomerDealJourney.__table__,
        Contract.__table__,
        PaymentPlan.__table__,
        PaymentRecord.__table__,
        InvoiceApplication.__table__,
    ]
    with engine.begin() as connection:
        for table in tables:
            connection.execute(CreateTable(table))
    session = sessionmaker(bind=engine)()
    current_user = SimpleNamespace(id=7, name="销售张", status="active")
    session.add(User(id=7, email="owner@example.com", name="销售张", avatar_url="https://cdn.example/ada.png", status=UserStatus.ACTIVE))
    session.add(User(id=8, email="other@example.com", name="销售李", status=UserStatus.ACTIVE))
    session.commit()

    app = FastAPI()
    app.include_router(customers_api.router)
    app.dependency_overrides[database.get_db] = lambda: session
    app.dependency_overrides[deps.get_db] = lambda: session
    app.dependency_overrides[customers_api.get_db] = lambda: session
    app.dependency_overrides[deps.get_current_user_team] = lambda: 1
    app.dependency_overrides[customers_api.get_current_user_team] = lambda: 1
    app.dependency_overrides[deps.get_current_active_user] = lambda: current_user
    app.dependency_overrides[customers_api.get_current_active_user] = lambda: current_user

    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=session, current_user=current_user, app=app)

    session.close()
    engine.dispose()


def _customer(
    customer_id: int,
    *,
    name: str,
    owner_id: str | None,
    created_time: datetime,
    status: int = 0,
    team_id: int = 1,
    **extra,
) -> Customer:
    return Customer(
        id=customer_id,
        public_id=extra.pop("public_id", f"cus_{customer_id}"),
        team_id=team_id,
        account_name=name,
        city=extra.pop("city", "上海"),
        status=status,
        owner_id=owner_id,
        creator_id=owner_id or "7",
        created_time=created_time,
        last_modified_time=extra.pop("last_modified_time", created_time),
        **extra,
    )


def _journey(
    journey_id: int,
    *,
    customer_id: int,
    status: str,
    opportunity_id: int | None = None,
) -> CustomerDealJourney:
    return CustomerDealJourney(
        id=journey_id,
        public_id=f"djy_{journey_id}",
        team_id=1,
        customer_id=customer_id,
        primary_opportunity_id=opportunity_id,
        name=f"旅程{journey_id}",
        status=status,
        started_at=datetime(2026, 4, 1),
        last_event_at=datetime(2026, 4, 1),
    )


def _opportunity(opportunity_id: int, *, customer_id: int, purchase_type: str) -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        public_id=f"opp_{opportunity_id}",
        team_id=1,
        opportunity_number=f"OPP-{opportunity_id}",
        opportunity_name=f"商机{opportunity_id}",
        customer_id=customer_id,
        total_amount=Decimal("1000.00"),
        user_count=10,
        unit_price=Decimal("100.00"),
        license_type="SUBSCRIPTION",
        subscription_years=1,
        purchase_type=purchase_type,
        expected_closing_date=date(2026, 9, 1),
        owner_id="7",
        creator_id="7",
        win_probability=60,
        created_time=datetime(2026, 4, 1),
    )


def _grant(db, user_id: int, *codes: str) -> None:
    role = Role(name=f"角色{user_id}-{'-'.join(codes)}", code=f"role-{user_id}-{len(codes)}-{codes[0]}")
    db.add(role)
    db.flush()
    for index, code in enumerate(codes, start=1):
        permission = db.query(Permission).filter(Permission.code == code).one_or_none()
        if permission is None:
            permission = Permission(
                name=code,
                code=code,
                resource=code.split(":")[0],
                action=code.split(":")[1],
            )
            db.add(permission)
            db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=permission.id))
        del index
    db.add(UserRole(user_id=user_id, role_id=role.id, team_id=1))
    db.commit()


def _board(client: TestClient, **params):
    return client.get("/v1/customers/board", params=params)


def _columns(body: dict) -> dict[str, dict]:
    return {column["key"]: column for column in body["columns"]}


def _counts(body: dict) -> dict[str, int]:
    return {
        metric["key"]: metric["value"]
        for metric in body["summary"]
        if metric["value_type"] == "count"
    }


def _percentages(body: dict) -> dict[str, float | None]:
    return {
        metric["key"]: metric["value"]
        for metric in body["summary"]
        if metric["value_type"] == "percentage"
    }


def test_board_route_precedes_dynamic_customer_route() -> None:
    board_route = next(route for route in customers_api.router.routes if getattr(route, "path", None) == "/v1/customers/board")
    detail_route = next(route for route in customers_api.router.routes if getattr(route, "path", None) == "/v1/customers/{customer_id}")
    assert customers_api.router.routes.index(board_route) < customers_api.router.routes.index(detail_route)

    app = FastAPI()
    app.include_router(customers_api.router)
    matched = [route for route in app.router.routes if "/v1/customers/board" in getattr(route, "path", "")]
    assert any(getattr(route, "path", None) == "/v1/customers/board" for route in matched)


def test_board_public_id_named_board_uses_static_route(api_env) -> None:
    api_env.db.add(_customer(1, name="名字像路由", owner_id="7", created_time=datetime(2026, 5, 2), public_id="board"))
    api_env.db.commit()
    _grant(api_env.db, 7, "customer:view:all")

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert _columns(body)["not_started"]["items"][0]["id"] == "board"


def test_board_groups_derived_lifecycle_and_excludes_public_pool(api_env) -> None:
    db = api_env.db
    db.add_all([
        _customer(1, name="未启动客户", owner_id="7", created_time=datetime(2026, 5, 2), industry="software", city="上海", company_scale="100-499"),
        _customer(2, name="跟进客户", owner_id="7", created_time=datetime(2026, 6, 3)),
        _customer(
            3,
            name="复购客户",
            owner_id="7",
            created_time=datetime(2026, 7, 4),
            license_type="OFFICIAL",
            license_expiry_date=date(2027, 1, 31),
        ),
        _customer(4, name="成交客户", owner_id="7", created_time=datetime(2026, 8, 5), license_type="TRIAL", license_expiry_date=date(2026, 12, 1)),
        _customer(5, name="流失客户", owner_id="7", created_time=datetime(2026, 3, 6), status=2),
        _customer(6, name="公海客户", owner_id=None, created_time=datetime(2026, 8, 7), status=3),
        _customer(7, name="其他团队", owner_id="7", created_time=datetime(2026, 8, 8), team_id=2),
        _opportunity(21, customer_id=2, purchase_type="NEW"),
        _opportunity(31, customer_id=3, purchase_type="EXPANSION"),
        _opportunity(41, customer_id=4, purchase_type="NEW"),
        _journey(201, customer_id=2, status=DealJourneyStatus.ACTIVE, opportunity_id=21),
        _journey(301, customer_id=3, status=DealJourneyStatus.ACTIVE, opportunity_id=31),
        _journey(302, customer_id=3, status=DealJourneyStatus.COMPLETED),
        _journey(401, customer_id=4, status=DealJourneyStatus.COMPLETED, opportunity_id=41),
        _journey(601, customer_id=6, status=DealJourneyStatus.ACTIVE),
    ])
    db.commit()
    _grant(db, 7, "customer:view:all", "customer:edit:own", "customer:delete:own", "customer:assign", "opportunity:create")

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    body = response.json()
    columns = _columns(body)
    assert list(columns) == list(COLUMN_KEYS)
    assert {key: column["label"] for key, column in columns.items()} == COLUMN_LABELS
    assert {key: column["tone"] for key, column in columns.items()} == COLUMN_TONES
    assert {key: column["count"] for key, column in columns.items()} == {
        "not_started": 1,
        "following": 1,
        "repurchasing": 1,
        "won": 1,
        "lost": 1,
    }
    assert all(column["amount"] is None for column in columns.values())
    assert all(item["id"] != "cus_6" for column in columns.values() for item in column["items"])
    assert "cus_7" not in {item["id"] for column in columns.values() for item in column["items"]}

    repurchasing = columns["repurchasing"]["items"][0]
    assert repurchasing["id"] == "cus_3"
    assert repurchasing["title"] == "复购客户"
    assert repurchasing["subtitle"] == "增购 · 持续推进"
    assert repurchasing["amount"] is None
    assert repurchasing["date"] == "2026-07-04"
    assert repurchasing["owner"] == {"id": "7", "name": "销售张", "avatar_url": "https://cdn.example/ada.png"}
    assert repurchasing["status"] == "repurchasing"
    assert repurchasing["metadata"] == {
        "stage_hint": "增购 · 持续推进",
        "industry": None,
        "city": "上海",
        "company_scale": None,
        "license_type": "OFFICIAL",
        "license_expiry_date": "2027-01-31",
    }
    assert repurchasing["action_state"] == {
        "can_edit": True,
        "can_delete": True,
        "can_assign": True,
        "can_create_opportunity": True,
    }
    assert columns["won"]["items"][0]["metadata"]["license_type"] == "TRIAL"
    assert columns["not_started"]["items"][0]["subtitle"] is None
    assert columns["not_started"]["items"][0]["metadata"]["stage_hint"] is None

    assert _counts(body) == {
        "total_count": 5,
        "following_count": 1,
        "repurchasing_count": 1,
        "won_count": 1,
        "recent_new_count": 4,
    }
    assert body["summary"][-1]["key"] == "lost_percentage"
    assert [metric["label"] for metric in body["summary"][:5]] == list(COUNT_LABELS.values())
    assert _percentages(body) == {
        "not_started_percentage": 20.0,
        "following_percentage": 20.0,
        "repurchasing_percentage": 20.0,
        "won_percentage": 20.0,
        "lost_percentage": 20.0,
    }
    assert [point["date"] for point in body["trends"]] == [
        "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09",
    ]
    assert {point["date"]: point["count"] for point in body["trends"]} == {
        "2026-04": 0,
        "2026-05": 1,
        "2026-06": 1,
        "2026-07": 1,
        "2026-08": 1,
        "2026-09": 0,
    }
    assert all("amount" not in point for point in body["trends"])
    recent = next(metric for metric in body["summary"] if metric["key"] == "recent_new_count")
    assert recent["secondary_label"] == "上月"
    assert recent["secondary_value"] == 1


def test_board_preview_uses_full_column_totals(api_env) -> None:
    rows = [
        _customer(index, name=f"客户{index:02d}", owner_id="7", created_time=datetime(2026, 5, index), public_id=f"cus_{index:02d}")
        for index in range(1, 8)
    ]
    api_env.db.add_all(rows)
    api_env.db.commit()
    _grant(api_env.db, 7, "customer:view:all")

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    column = _columns(response.json())["not_started"]
    assert column["count"] == 7
    assert [item["id"] for item in column["items"]] == ["cus_07", "cus_06", "cus_05", "cus_04", "cus_03"]
    assert column["has_more"] is True
    assert column["remaining_count"] == 2
    assert _counts(response.json())["total_count"] == 7
    assert all(other["count"] == 0 and other["items"] == [] for key, other in _columns(response.json()).items() if key != "not_started")


def test_empty_authorized_population_returns_complete_zero_board(api_env) -> None:
    api_env.db.add(_customer(1, name="其他团队", owner_id="7", created_time=datetime(2026, 8, 1), team_id=2))
    api_env.db.commit()
    _grant(api_env.db, 7, "customer:view:all")

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    body = response.json()
    columns = _columns(body)
    assert list(columns) == list(COLUMN_KEYS)
    assert all(column["count"] == 0 and column["items"] == [] and column["has_more"] is False for column in columns.values())
    assert _counts(body) == {key: 0 for key in COUNT_LABELS}
    assert _percentages(body) == {key: None for key in PERCENTAGE_LABELS}
    assert body["trends"] == []
    recent = next(metric for metric in body["summary"] if metric["key"] == "recent_new_count")
    assert recent["secondary_label"] is None
    assert recent["secondary_value"] is None


def test_search_legacy_filters_and_source_resolution_narrow_complete_population(api_env) -> None:
    db = api_env.db
    db.add(AcquisitionSource(id=11, public_id="acq_expo", team_id=1, code="EXPO", name="展会", sort_order=1, created_by="7"))
    db.add_all([
        _customer(1, name="Alpha 上海", owner_id="7", created_time=datetime(2026, 5, 1), city="上海", industry="software", source_id=11),
        _customer(2, name="Alpha 北京", owner_id="7", created_time=datetime(2026, 5, 2), city="北京", industry="software", source_id=11),
        _customer(3, name="Beta 上海", owner_id="7", created_time=datetime(2026, 5, 3), city="上海", industry="finance", source_id=11),
    ])
    db.commit()
    _grant(db, 7, "customer:view:all")

    response = _board(
        api_env.client,
        search="Alpha",
        city="上海",
        industry="software",
        source_public_id="acq_expo",
    )

    assert response.status_code == 200, response.text
    column = _columns(response.json())["not_started"]
    assert column["count"] == 1
    assert column["items"][0]["id"] == "cus_1"
    assert _counts(response.json())["total_count"] == 1


def test_unified_filter_uses_derived_status_and_ignores_legacy_dates(api_env) -> None:
    db = api_env.db
    db.add_all([
        _customer(1, name="早期成交", owner_id="7", created_time=datetime(2026, 1, 15)),
        _customer(2, name="窗口成交", owner_id="7", created_time=datetime(2026, 6, 15)),
        _customer(3, name="窗口跟进", owner_id="7", created_time=datetime(2026, 6, 20)),
        _opportunity(21, customer_id=1, purchase_type="NEW"),
        _opportunity(22, customer_id=2, purchase_type="NEW"),
        _opportunity(23, customer_id=3, purchase_type="NEW"),
        _journey(11, customer_id=1, status=DealJourneyStatus.COMPLETED, opportunity_id=21),
        _journey(12, customer_id=2, status=DealJourneyStatus.COMPLETED, opportunity_id=22),
        _journey(13, customer_id=3, status=DealJourneyStatus.ACTIVE, opportunity_id=23),
    ])
    db.commit()
    _grant(db, 7, "customer:view:all")

    response = _board(
        api_env.client,
        status="1",
        created_time_start="2026-08-01",
        created_time_end="2026-08-31",
        filters='[{"field":"status","op":"eq","value":"won"},{"field":"created_time","op":"after","value":"2026-06-01"},{"field":"created_time","op":"before","value":"2026-06-30"}]',
        sorts="[]",
    )

    assert response.status_code == 200, response.text
    body = response.json()
    columns = _columns(body)
    assert columns["won"]["count"] == 1
    assert columns["won"]["items"][0]["id"] == "cus_2"
    assert columns["following"]["count"] == 0
    assert _counts(body)["total_count"] == 1
    assert [point["date"] for point in body["trends"]] == ["2026-06"]
    assert body["trends"][0]["count"] == 1


def test_sorting_changes_preview_order_only(api_env) -> None:
    api_env.db.add_all([
        _customer(1, name="甲", owner_id="7", created_time=datetime(2026, 5, 1), public_id="cus_b", last_modified_time=datetime(2026, 8, 2)),
        _customer(2, name="乙", owner_id="7", created_time=datetime(2026, 5, 1), public_id="cus_a", last_modified_time=datetime(2026, 8, 1)),
        _customer(3, name="丙", owner_id="7", created_time=datetime(2026, 6, 1), public_id="cus_c"),
        _customer(4, name="丁", owner_id="7", created_time=datetime(2026, 4, 1), public_id="cus_d"),
        _customer(5, name="戊", owner_id="7", created_time=datetime(2026, 7, 1), public_id="cus_e"),
        _customer(6, name="己", owner_id="7", created_time=datetime(2026, 3, 1), public_id="cus_f"),
        _customer(7, name="庚", owner_id="7", created_time=datetime(2026, 2, 1), public_id="cus_g"),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "customer:view:all")

    default_response = _board(api_env.client)
    sorted_response = _board(api_env.client, order_by="account_name", order_dir="asc")

    assert default_response.status_code == 200, default_response.text
    assert sorted_response.status_code == 200, sorted_response.text
    default_body = default_response.json()
    sorted_body = sorted_response.json()
    assert [item["id"] for item in _columns(default_body)["not_started"]["items"]] == [
        "cus_e", "cus_c", "cus_b", "cus_a", "cus_d",
    ]
    assert [item["title"] for item in _columns(sorted_body)["not_started"]["items"]] == ["丁", "丙", "乙", "己", "庚"]
    assert _counts(default_body) == _counts(sorted_body)
    assert _percentages(default_body) == _percentages(sorted_body)
    assert default_body["trends"] == sorted_body["trends"]
    assert _columns(default_body)["not_started"]["count"] == _columns(sorted_body)["not_started"]["count"] == 7


def test_invalid_scope_and_owner_permission_are_rejected(api_env) -> None:
    api_env.db.add_all([
        _customer(1, name="自己的客户", owner_id="7", created_time=datetime(2026, 5, 1)),
        _customer(2, name="别人的客户", owner_id="8", created_time=datetime(2026, 5, 2)),
    ])
    api_env.db.commit()

    public_scope = _board(api_env.client, scope="public")
    unknown_scope = _board(api_env.client, scope="team")
    forbidden = _board(api_env.client, owner_id="8")

    assert public_scope.status_code == 400
    assert public_scope.json()["detail"] == "scope 仅支持 collaborated/accessible"
    assert unknown_scope.status_code == 400
    assert unknown_scope.json()["detail"] == "scope 仅支持 collaborated/accessible"
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "只能查看自己负责的客户，或需要 customer:view:all 权限查看他人数据"


def test_own_scope_excludes_other_owners_without_view_all(api_env) -> None:
    api_env.db.add_all([
        _customer(1, name="自己的客户", owner_id="7", created_time=datetime(2026, 5, 1)),
        _customer(2, name="别人的客户", owner_id="8", created_time=datetime(2026, 5, 2)),
        _customer(3, name="其他团队自己的客户", owner_id="7", created_time=datetime(2026, 5, 3), team_id=2),
    ])
    api_env.db.commit()

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert _columns(body)["not_started"]["count"] == 1
    assert _columns(body)["not_started"]["items"][0]["id"] == "cus_1"
    assert _counts(body)["total_count"] == 1


def test_collaborated_scope_uses_membership_not_owner_permission(api_env) -> None:
    api_env.db.add_all([
        _customer(1, name="自己负责", owner_id="7", created_time=datetime(2026, 5, 1)),
        _customer(2, name="协作客户", owner_id="8", created_time=datetime(2026, 6, 1)),
        _customer(3, name="无关系客户", owner_id="8", created_time=datetime(2026, 7, 1)),
        CustomerMember(id=1, team_id=1, customer_id=2, user_id="7", access_level="EDIT", is_active=True, created_by="7"),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "customer:edit:own", "opportunity:create")

    response = _board(api_env.client, scope="collaborated")

    assert response.status_code == 200, response.text
    body = response.json()
    assert _columns(body)["not_started"]["count"] == 1
    assert _columns(body)["not_started"]["items"][0]["id"] == "cus_2"
    assert _columns(body)["not_started"]["items"][0]["action_state"] == {
        "can_edit": True,
        "can_delete": False,
        "can_assign": False,
        "can_create_opportunity": True,
    }
    assert _counts(body)["total_count"] == 1


def test_recent_new_count_uses_approved_six_complete_month_window(api_env, monkeypatch) -> None:
    class _FrozenDate(date):
        @classmethod
        def today(cls) -> date:
            return date(2026, 10, 12)

    monkeypatch.setattr(customers_api, "date", _FrozenDate)
    api_env.db.add_all([
        _customer(1, name="窗口前", owner_id="7", created_time=datetime(2026, 3, 31), public_id="cus_before"),
        _customer(2, name="窗口首月", owner_id="7", created_time=datetime(2026, 4, 1), public_id="cus_april"),
        _customer(3, name="上月", owner_id="7", created_time=datetime(2026, 8, 15), public_id="cus_august"),
        _customer(4, name="窗口末月", owner_id="7", created_time=datetime(2026, 9, 30, 23, 59), public_id="cus_september"),
        _customer(5, name="当前未完成月", owner_id="7", created_time=datetime(2026, 10, 2), public_id="cus_october"),
        _customer(6, name="公海新增", owner_id=None, created_time=datetime(2026, 9, 2), public_id="cus_public", status=3),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "customer:view:all")

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    body = response.json()
    recent = next(metric for metric in body["summary"] if metric["key"] == "recent_new_count")
    assert recent["value"] == 3
    assert recent["secondary_label"] == "上月"
    assert recent["secondary_value"] == 1
    assert {point["date"]: point["count"] for point in body["trends"]} == {
        "2026-04": 1,
        "2026-05": 0,
        "2026-06": 0,
        "2026-07": 0,
        "2026-08": 1,
        "2026-09": 1,
    }


def test_recent_new_comparison_is_omitted_when_previous_month_is_outside_window(api_env) -> None:
    api_env.db.add_all([
        _customer(1, name="窗口内", owner_id="7", created_time=datetime(2026, 9, 12), public_id="cus_inside"),
        _customer(2, name="窗口外上月", owner_id="7", created_time=datetime(2026, 8, 12), public_id="cus_outside"),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "customer:view:all")

    response = _board(api_env.client, created_time_start="2026-09-01", created_time_end="2026-09-30")

    assert response.status_code == 200, response.text
    body = response.json()
    recent = next(metric for metric in body["summary"] if metric["key"] == "recent_new_count")
    assert recent["value"] == 1
    assert recent["secondary_label"] is None
    assert recent["secondary_value"] is None
    assert [point["date"] for point in body["trends"]] == ["2026-09"]


def test_status_exclude_filters_legacy_population(api_env) -> None:
    api_env.db.add_all([
        _customer(1, name="跟进中", owner_id="7", created_time=datetime(2026, 5, 1), status=0, public_id="cus_following"),
        _customer(2, name="已赢单", owner_id="7", created_time=datetime(2026, 6, 1), status=1, public_id="cus_won"),
        _customer(3, name="已输单", owner_id="7", created_time=datetime(2026, 7, 1), status=2, public_id="cus_lost"),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "customer:view:all")

    response = _board(api_env.client, status_exclude="1,2")

    assert response.status_code == 200, response.text
    body = response.json()
    assert _counts(body)["total_count"] == 1
    assert _columns(body)["not_started"]["items"][0]["id"] == "cus_following"
    assert _columns(body)["lost"]["count"] == 0


def test_explicit_source_sort_uses_source_name_then_public_id(api_env) -> None:
    api_env.db.add_all([
        _customer(1, name="甲", owner_id="7", created_time=datetime(2026, 5, 1), source="expo", source_id=30, public_id="cus_z"),
        _customer(2, name="乙", owner_id="7", created_time=datetime(2026, 5, 2), source="web", source_id=10, public_id="cus_b"),
        _customer(3, name="丙", owner_id="7", created_time=datetime(2026, 5, 3), source="web", source_id=20, public_id="cus_a"),
        _customer(4, name="丁", owner_id="7", created_time=datetime(2026, 5, 4), source="referral", source_id=5, public_id="cus_d"),
        _customer(5, name="戊", owner_id="7", created_time=datetime(2026, 5, 5), source="phone", source_id=40, public_id="cus_e"),
        _customer(6, name="己", owner_id="7", created_time=datetime(2026, 5, 6), source="ad", source_id=50, public_id="cus_f"),
        _customer(7, name="庚", owner_id="7", created_time=datetime(2026, 5, 7), source="partner", source_id=60, public_id="cus_g"),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "customer:view:all")

    response = _board(api_env.client, order_by="source", order_dir="asc")

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["id"] for item in _columns(body)["not_started"]["items"]] == [
        "cus_f", "cus_z", "cus_g", "cus_e", "cus_d",
    ]
    assert _counts(body)["total_count"] == 7

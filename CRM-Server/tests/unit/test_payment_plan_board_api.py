"""Payment-plan board aggregation uses the complete authorized population."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, event, inspect
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

from app.api import payments as payments_api
from app.constants.business_types import BusinessType
from app.core import database, deps
from app.models.approval import Approval, ApprovalStatus
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.customer_identity_term import CustomerIdentityTerm
from app.models.opportunity import Opportunity
from app.models.payment import PaymentConfirmationStatus, PaymentPlan, PaymentRecord
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User, UserStatus
from app.models.user_role import UserRole


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


COLUMN_KEYS = ("PENDING", "OVERDUE", "PARTIAL", "COMPLETED", "UNCLASSIFIED")
COLUMN_LABELS = {
    "PENDING": "待登记",
    "OVERDUE": "已逾期",
    "PARTIAL": "部分回款",
    "COMPLETED": "已登记",
    "UNCLASSIFIED": "未分类",
}
COLUMN_TONES = {
    "PENDING": "neutral",
    "OVERDUE": "danger",
    "PARTIAL": "warning",
    "COMPLETED": "success",
    "UNCLASSIFIED": "muted",
}
SUMMARY_KEYS = (
    "overdue_count",
    "planned_amount",
    "paid_amount",
    "remaining_amount",
    "overdue_remaining_amount",
)
SUMMARY_LABELS = {
    "overdue_count": "逾期",
    "planned_amount": "计划金额",
    "paid_amount": "已回款",
    "remaining_amount": "待回款",
    "overdue_remaining_amount": "逾期待回款",
}
ZERO_AMOUNTS = {
    "amount": "0.00",
    "planned_amount": "0.00",
    "paid_amount": "0.00",
    "remaining_amount": "0.00",
    "overdue_remaining_amount": "0.00",
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


def _opportunity(opportunity_id: int, *, name: str, customer_id: int, owner_id: str = "7") -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        public_id=f"opp_{opportunity_id:02d}",
        team_id=1,
        opportunity_number=f"OPP-{opportunity_id:04d}",
        opportunity_name=name,
        customer_id=customer_id,
        total_amount=Decimal("1000.00"),
        user_count=10,
        unit_price=Decimal("100.00"),
        license_type="SUBSCRIPTION",
        subscription_years=1,
        purchase_type="NEW",
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
    customer_id: int = 1,
    opportunity_id: int = 1,
    owner_id: str = "7",
    creator_id: str | None = None,
    team_id: int = 1,
) -> Contract:
    return Contract(
        id=contract_id,
        team_id=team_id,
        contract_number=f"CT-{contract_id:04d}",
        contract_name=name,
        customer_id=customer_id,
        opportunity_id=opportunity_id,
        user_count=10,
        total_amount=Decimal("1000.00"),
        license_type="SUBSCRIPTION",
        subscription_years=1,
        standard_unit_price=Decimal("100.00"),
        status="EFFECTIVE",
        approval_phase="approved",
        owner_id=owner_id,
        creator_id=creator_id or owner_id,
        created_time=datetime(2026, 4, 1),
        last_modified_time=datetime(2026, 4, 1),
    )


def _plan(
    plan_id: int,
    *,
    contract_id: int,
    name: str,
    amount: str,
    status: str = "PENDING",
    due_date: date | None = date(2026, 6, 1),
    team_id: int = 1,
) -> PaymentPlan:
    return PaymentPlan(
        id=plan_id,
        team_id=team_id,
        contract_id=contract_id,
        plan_number=f"PP-{plan_id:04d}",
        stage_name=name,
        planned_amount=Decimal(amount),
        due_date=due_date,
        status=status,
        created_time=datetime(2026, 4, 1),
        last_modified_time=datetime(2026, 4, 1),
    )


def _record(
    record_id: int,
    *,
    plan_id: int,
    amount: str,
    payment_date: date,
    approval_phase: str = "draft",
    confirmation_status: str = PaymentConfirmationStatus.PENDING,
    approval_id: int | None = None,
    team_id: int = 1,
) -> PaymentRecord:
    return PaymentRecord(
        id=record_id,
        team_id=team_id,
        record_number=f"PR-{record_id:04d}",
        payment_plan_id=plan_id,
        actual_amount=Decimal(amount),
        payment_date=payment_date,
        creator_id="7",
        creator_name="销售张",
        confirmation_status=confirmation_status,
        approval_phase=approval_phase,
        approval_id=approval_id,
        created_time=datetime(2026, 8, min(record_id, 28)),
        updated_time=datetime(2026, 8, min(record_id, 28)),
    )


def _approval(approval_id: int, *, record_id: int, status: str, team_id: int = 1) -> Approval:
    return Approval(
        id=approval_id,
        team_id=team_id,
        business_type=BusinessType.PAYMENT,
        business_id=record_id,
        status=status,
        submitter_id="7",
    )


@pytest.fixture
def api_env():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    def _reject_property_fallback(statement, *_args, **_kwargs):
        sql = str(statement).lower()
        if "exception" in sql or "try" in sql:
            raise AssertionError("approved paid-to-date must not catch property exceptions")

    event.listen(engine, "before_cursor_execute", _reject_property_fallback)
    tables = [
        User.__table__,
        Role.__table__,
        Permission.__table__,
        RolePermission.__table__,
        UserRole.__table__,
        Customer.__table__,
        Opportunity.__table__,
        Contract.__table__,
        CustomerIdentityTerm.__table__,
        PaymentPlan.__table__,
        Approval.__table__,
        PaymentRecord.__table__,
    ]
    with engine.begin() as connection:
        for table in tables:
            connection.execute(CreateTable(table))
    session = sessionmaker(bind=engine)()
    current_user = SimpleNamespace(id=7, name="销售张", status="active")
    session.add(User(
        id=7,
        email="owner@example.com",
        name="销售张",
        avatar_url="https://cdn.example/ada.png",
        status=UserStatus.ACTIVE,
    ))
    session.add(User(id=8, email="other@example.com", name="销售李", status=UserStatus.ACTIVE))
    session.add(_customer(1, name="甲客户"))
    session.add(_customer(2, name="乙客户", owner_id="8"))
    session.add(_opportunity(1, name="甲商机", customer_id=1))
    session.add(_opportunity(2, name="乙商机", customer_id=2, owner_id="8"))
    session.commit()

    app = FastAPI()
    app.include_router(payments_api.router)
    app.dependency_overrides[database.get_db] = lambda: session
    app.dependency_overrides[deps.get_db] = lambda: session
    app.dependency_overrides[payments_api.get_db] = lambda: session
    app.dependency_overrides[deps.get_current_user_team] = lambda: 1
    app.dependency_overrides[payments_api.get_current_user_team] = lambda: 1
    app.dependency_overrides[deps.get_current_active_user] = lambda: current_user
    app.dependency_overrides[payments_api.get_current_active_user] = lambda: current_user

    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=session, current_user=current_user, app=app)

    session.close()
    engine.dispose()


def _grant(db, user_id: int, *codes: str) -> None:
    role = Role(name=f"角色{user_id}-{'-'.join(codes)}", code=f"role-{user_id}-{len(codes)}-{codes[0]}")
    db.add(role)
    db.flush()
    for code in codes:
        permission = db.query(Permission).filter(Permission.code == code).one_or_none()
        if permission is None:
            parts = code.split(":")
            permission = Permission(name=code, code=code, resource=parts[0], action=parts[1])
            db.add(permission)
            db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db.add(UserRole(user_id=user_id, role_id=role.id, team_id=1))
    db.commit()


def _board(client: TestClient, **params):
    return client.get("/v1/payments/payment-plans/board", params=params)


def _columns(body: dict) -> dict[str, dict]:
    return {column["key"]: column for column in body["columns"]}


def _metric(body: dict, key: str) -> dict:
    return next(metric for metric in body["summary"] if metric["key"] == key)


def _freeze(monkeypatch, frozen: date) -> None:
    class _FrozenDate(date):
        @classmethod
        def today(cls) -> date:
            return frozen

    monkeypatch.setattr(payments_api, "date", _FrozenDate)


def test_board_route_precedes_dynamic_plan_route() -> None:
    board_route = next(
        route for route in payments_api.router.routes
        if getattr(route, "path", None) == "/v1/payments/payment-plans/board"
    )
    detail_route = next(
        route for route in payments_api.router.routes
        if getattr(route, "path", None) == "/v1/payments/payment-plans/{plan_id}"
    )
    assert payments_api.router.routes.index(board_route) < payments_api.router.routes.index(detail_route)
    query_names = {field.alias or field.name for field in board_route.dependant.query_params}
    assert {"skip", "limit", "page", "page_size", "user_id"}.isdisjoint(query_names)
    assert {"status", "me", "filters", "sorts", "due_date_start", "due_date_end"} <= query_names


def test_missing_permission_is_forbidden_before_aggregation(api_env) -> None:
    api_env.db.add_all([
        _contract(1, name="甲合同"),
        _plan(1, contract_id=1, name="首付款", amount="10.00"),
    ])
    api_env.db.commit()

    response = _board(api_env.client)

    assert response.status_code == 403
    assert response.json()["detail"] == "没有查看回款计划的权限"
    assert inspect(api_env.db.bind).has_table("crm_contract_payment_plans")


def test_me_with_view_all_limits_scope_to_contract_owner(api_env, monkeypatch) -> None:
    _freeze(monkeypatch, date(2026, 10, 12))
    api_env.db.add_all([
        _contract(1, name="甲合同", owner_id="7"),
        _contract(2, name="乙合同", customer_id=2, opportunity_id=2, owner_id="8"),
        _plan(1, contract_id=1, name="本人计划", amount="10.00", due_date=date(2026, 6, 2)),
        _plan(2, contract_id=2, name="他人计划", amount="90.00", due_date=date(2026, 6, 2)),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "payment:view:all")

    response = _board(api_env.client, me=True)

    assert response.status_code == 200, response.text
    body = response.json()
    assert _columns(body)["PENDING"]["count"] == 1
    assert _columns(body)["PENDING"]["items"][0]["id"] == 1
    assert _metric(body, "planned_amount")["value"] == "10.00"
    assert {point["date"]: point for point in body["trends"]}["2026-06"] == {
        "date": "2026-06",
        "count": 1,
        "planned_amount": "10.00",
        "paid_amount": "0.00",
        "remaining_amount": "10.00",
    }
    assert [point["date"] for point in body["trends"]] == [
        "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09",
    ]


def test_own_only_excludes_other_owner_from_every_aggregate(api_env, monkeypatch) -> None:
    _freeze(monkeypatch, date(2026, 10, 12))
    api_env.db.add_all([
        _contract(1, name="甲合同", owner_id="7", creator_id="8"),
        _contract(2, name="乙合同", customer_id=2, opportunity_id=2, owner_id="8", creator_id="7"),
        _plan(1, contract_id=1, name="本人计划", amount="12.50", status="OVERDUE", due_date=date(2026, 6, 3)),
        _plan(2, contract_id=2, name="他人计划", amount="80.00", status="OVERDUE", due_date=date(2026, 6, 3)),
        _record(1, plan_id=1, amount="2.50", payment_date=date(2026, 5, 1), approval_phase="approved"),
        _record(2, plan_id=2, amount="40.00", payment_date=date(2026, 5, 1), approval_phase="approved"),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "payment:view:own")

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    body = response.json()
    columns = _columns(body)
    assert columns["OVERDUE"]["count"] == 1
    assert columns["OVERDUE"]["items"][0]["id"] == 1
    assert _metric(body, "overdue_count")["value"] == 1
    assert _metric(body, "planned_amount")["value"] == "12.50"
    assert _metric(body, "paid_amount")["value"] == "2.50"
    assert _metric(body, "remaining_amount")["value"] == "10.00"
    assert _metric(body, "overdue_remaining_amount")["value"] == "10.00"
    assert all(item["id"] != 2 for column in columns.values() for item in column["items"])
    assert {point["date"]: point for point in body["trends"]}["2026-06"] == {
        "date": "2026-06",
        "count": 1,
        "planned_amount": "12.50",
        "paid_amount": "2.50",
        "remaining_amount": "10.00",
    }


def test_board_groups_columns_and_uses_canonical_decimal_paid_to_date(api_env, monkeypatch) -> None:
    _freeze(monkeypatch, date(2026, 10, 12))
    api_env.db.add_all([
        _contract(1, name="甲合同"),
        _plan(1, contract_id=1, name="待登记", amount="10.10", status="PENDING", due_date=date(2026, 5, 2)),
        _plan(2, contract_id=1, name="已逾期", amount="20.00", status="OVERDUE", due_date=date(2026, 6, 3)),
        _plan(3, contract_id=1, name="部分回款", amount="30.25", status="PARTIAL", due_date=date(2026, 7, 4)),
        _plan(4, contract_id=1, name="已登记", amount="40.00", status="COMPLETED", due_date=date(2026, 8, 5)),
        _plan(5, contract_id=1, name="未知状态", amount="70.00", status="ARCHIVED", due_date=date(2026, 9, 8)),
        _plan(6, contract_id=1, name="超额回款", amount="10.00", status="OVERDUE", due_date=date(2026, 4, 15)),
        _plan(7, contract_id=1, name="其他团队", amount="1000.00", status="PENDING", due_date=date(2026, 6, 1), team_id=2),
        _record(1, plan_id=2, amount="5.00", payment_date=date(2026, 3, 1), approval_phase="approved"),
        _record(2, plan_id=2, amount="1.25", payment_date=date(2026, 3, 2), approval_phase="approved", confirmation_status=PaymentConfirmationStatus.CONFIRMED),
        _record(3, plan_id=2, amount="9.00", payment_date=date(2026, 3, 3), approval_phase="pending_review", confirmation_status=PaymentConfirmationStatus.CONFIRMED),
        _record(4, plan_id=3, amount="10.10", payment_date=date(2026, 3, 4), approval_phase="draft"),
        _approval(20, record_id=4, status=ApprovalStatus.APPROVED),
        _record(5, plan_id=6, amount="12.50", payment_date=date(2026, 3, 5), approval_phase="withdrawn"),
        _approval(21, record_id=5, status=ApprovalStatus.APPROVED),
        _record(6, plan_id=7, amount="500.00", payment_date=date(2026, 3, 6), approval_phase="approved", team_id=2),
    ])
    api_env.db.flush()
    api_env.db.query(PaymentRecord).filter(PaymentRecord.id == 4).one().approval_id = 20
    api_env.db.query(PaymentRecord).filter(PaymentRecord.id == 5).one().approval_id = 21
    api_env.db.commit()
    _grant(api_env.db, 7, "payment:view:all", "payment:plan:edit", "payment:plan:delete")

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    body = response.json()
    columns = _columns(body)
    assert list(columns) == list(COLUMN_KEYS)
    assert {key: columns[key]["label"] for key in COLUMN_KEYS} == COLUMN_LABELS
    assert {key: columns[key]["tone"] for key in COLUMN_KEYS} == COLUMN_TONES
    assert columns["PENDING"]["count"] == 1
    assert columns["PENDING"]["planned_amount"] == "10.10"
    assert columns["OVERDUE"]["count"] == 2
    assert columns["OVERDUE"]["planned_amount"] == "30.00"
    assert columns["OVERDUE"]["paid_amount"] == "18.75"
    assert columns["OVERDUE"]["remaining_amount"] == "11.25"
    assert columns["OVERDUE"]["overdue_remaining_amount"] == "11.25"
    assert columns["PARTIAL"]["paid_amount"] == "10.10"
    assert columns["PARTIAL"]["remaining_amount"] == "20.15"
    assert columns["COMPLETED"]["planned_amount"] == "40.00"
    assert columns["UNCLASSIFIED"]["count"] == 1
    assert columns["UNCLASSIFIED"]["items"][0]["status"] == "UNCLASSIFIED"
    assert all(item["id"] != 7 for column in columns.values() for item in column["items"])

    pending = columns["PENDING"]["items"][0]
    assert pending["title"] == "PP-0001"
    assert pending["subtitle"] == "待登记"
    assert pending["amount"] == "10.10"
    assert pending["date"] == "2026-05-02"
    assert pending["owner"] == {"id": "7", "name": "销售张", "avatar_url": "https://cdn.example/ada.png"}
    assert pending["metadata"] == {
        "customer_name": "甲客户",
        "contract_name": "甲合同",
        "opportunity_name": "甲商机",
        "paid_amount": "0.00",
        "remaining_amount": "10.10",
    }
    assert pending["action_state"] == {"can_edit": True, "can_delete": True, "can_view_detail": True}
    overdue_items = {item["id"]: item for item in columns["OVERDUE"]["items"]}
    assert overdue_items[6]["paid_amount"] == "12.50"
    assert overdue_items[6]["remaining_amount"] == "-2.50"
    assert overdue_items[6]["metadata"]["remaining_amount"] == "-2.50"

    assert [metric["key"] for metric in body["summary"]] == list(SUMMARY_KEYS)
    assert [metric["label"] for metric in body["summary"]] == [SUMMARY_LABELS[key] for key in SUMMARY_KEYS]
    assert _metric(body, "overdue_count") == {
        "key": "overdue_count",
        "label": "逾期",
        "value_type": "count",
        "value": 2,
        "secondary_label": None,
        "secondary_value": None,
    }
    assert _metric(body, "planned_amount")["value"] == "180.35"
    assert _metric(body, "paid_amount")["value"] == "28.85"
    assert _metric(body, "remaining_amount")["value"] == "151.50"
    assert _metric(body, "overdue_remaining_amount")["value"] == "11.25"
    assert {point["date"]: point for point in body["trends"]}["2026-04"] == {
        "date": "2026-04",
        "count": 1,
        "planned_amount": "10.00",
        "paid_amount": "12.50",
        "remaining_amount": "-2.50",
    }
    assert {point["date"]: point["count"] for point in body["trends"]} == {
        "2026-04": 1,
        "2026-05": 1,
        "2026-06": 1,
        "2026-07": 1,
        "2026-08": 1,
        "2026-09": 1,
    }


def test_confirmed_without_approval_evidence_is_not_paid(api_env) -> None:
    api_env.db.add_all([
        _contract(1, name="甲合同"),
        _plan(1, contract_id=1, name="仅确认", amount="15.00", status="PARTIAL", due_date=date(2026, 6, 1)),
        _record(
            1,
            plan_id=1,
            amount="15.00",
            payment_date=date(2026, 5, 1),
            approval_phase="draft",
            confirmation_status=PaymentConfirmationStatus.CONFIRMED,
        ),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "payment:view:all")

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    column = _columns(response.json())["PARTIAL"]
    assert column["paid_amount"] == "0.00"
    assert column["remaining_amount"] == "15.00"
    assert column["items"][0]["paid_amount"] == "0.00"


def test_due_month_trends_follow_active_date_branch(api_env, monkeypatch) -> None:
    _freeze(monkeypatch, date(2026, 10, 12))
    api_env.db.add_all([
        _contract(1, name="甲合同"),
        _plan(1, contract_id=1, name="窗口内", amount="10.00", due_date=date(2026, 6, 15)),
        _plan(2, contract_id=1, name="窗口外", amount="20.00", due_date=date(2026, 8, 15)),
        _record(1, plan_id=1, amount="4.00", payment_date=date(2026, 8, 1), approval_phase="approved"),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "payment:view:all")

    legacy = _board(api_env.client, due_date_start="2026-06-01", due_date_end="2026-06-30")
    unified = _board(
        api_env.client,
        due_date_start="2026-08-01",
        due_date_end="2026-08-31",
        filters='[{"field":"due_date","op":"after","value":"2026-06-01"},{"field":"due_date","op":"before","value":"2026-06-30"}]',
    )

    assert legacy.status_code == 200, legacy.text
    assert unified.status_code == 200, unified.text
    assert legacy.json()["trends"] == [{
        "date": "2026-06",
        "count": 1,
        "planned_amount": "10.00",
        "paid_amount": "4.00",
        "remaining_amount": "6.00",
    }]
    assert unified.json()["trends"] == [{
        "date": "2026-06",
        "count": 1,
        "planned_amount": "10.00",
        "paid_amount": "4.00",
        "remaining_amount": "6.00",
    }]
    assert _metric(legacy.json(), "planned_amount")["value"] == "10.00"


def test_search_and_date_filters_limit_complete_population(api_env) -> None:
    api_env.db.add_all([
        _contract(1, name="甲合同"),
        _plan(1, contract_id=1, name="首付款", amount="10.00", due_date=date(2026, 6, 1)),
        _plan(2, contract_id=1, name="尾款", amount="30.00", due_date=date(2026, 8, 1)),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "payment:view:all")

    response = _board(api_env.client, search="PP-0001", due_date_start="2026-06-01", due_date_end="2026-06-30")

    assert response.status_code == 200, response.text
    body = response.json()
    assert _columns(body)["PENDING"]["count"] == 1
    assert _columns(body)["PENDING"]["items"][0]["id"] == 1
    assert _metric(body, "planned_amount")["value"] == "10.00"


def test_empty_population_returns_ordered_zero_columns(api_env) -> None:
    api_env.db.add_all([
        _contract(1, name="其他团队合同", team_id=2),
        _plan(1, contract_id=1, name="其他团队", amount="50.00", team_id=2),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "payment:view:all")

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    body = response.json()
    columns = _columns(body)
    assert list(columns) == list(COLUMN_KEYS)
    for column in columns.values():
        assert column["count"] == 0
        assert column["items"] == []
        assert column["has_more"] is False
        assert column["remaining_count"] == 0
        assert {key: column[key] for key in ZERO_AMOUNTS} == ZERO_AMOUNTS
    assert _metric(body, "overdue_count")["value"] == 0
    assert _metric(body, "planned_amount")["value"] == "0.00"
    assert _metric(body, "paid_amount")["value"] == "0.00"
    assert _metric(body, "remaining_amount")["value"] == "0.00"
    assert _metric(body, "overdue_remaining_amount")["value"] == "0.00"
    assert body["trends"] == []


def test_preview_limit_keeps_full_totals_and_sort_changes_order_only(api_env, monkeypatch) -> None:
    _freeze(monkeypatch, date(2026, 10, 12))
    rows = [
        _contract(1, name="甲合同"),
        *[
            _plan(
                index,
                contract_id=1,
                name=f"计划{index:02d}",
                amount=f"{index}.00",
                due_date=date(2026, 6, index),
            )
            for index in range(1, 8)
        ],
    ]
    api_env.db.add_all(rows)
    api_env.db.commit()
    _grant(api_env.db, 7, "payment:view:all")

    default_response = _board(api_env.client)
    sorted_response = _board(api_env.client, order_by="planned_amount", order_dir="desc")

    assert default_response.status_code == 200, default_response.text
    assert sorted_response.status_code == 200, sorted_response.text
    default_body = default_response.json()
    sorted_body = sorted_response.json()
    default_column = _columns(default_body)["PENDING"]
    sorted_column = _columns(sorted_body)["PENDING"]
    assert default_column["count"] == 7
    assert [item["id"] for item in default_column["items"]] == [1, 2, 3, 4, 5]
    assert default_column["has_more"] is True
    assert default_column["remaining_count"] == 2
    assert default_column["planned_amount"] == "28.00"
    assert [item["id"] for item in sorted_column["items"]] == [7, 6, 5, 4, 3]
    assert sorted_column["count"] == default_column["count"]
    assert sorted_column["planned_amount"] == default_column["planned_amount"]
    assert sorted_column["paid_amount"] == default_column["paid_amount"]
    assert sorted_column["remaining_amount"] == default_column["remaining_amount"]
    assert _metric(sorted_body, "planned_amount")["value"] == _metric(default_body, "planned_amount")["value"]
    assert sorted_body["trends"] == default_body["trends"]
    for key in COLUMN_KEYS:
        if key == "PENDING":
            continue
        assert _columns(default_body)[key]["count"] == 0
        assert {name: _columns(default_body)[key][name] for name in ZERO_AMOUNTS} == ZERO_AMOUNTS

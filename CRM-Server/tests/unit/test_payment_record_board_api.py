"""Payment-record board aggregation uses the complete authorized population."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, inspect
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
from app.models.invoice import InvoiceApplication
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


COLUMN_KEYS = (
    "pending_submit",
    "pending_approval",
    "rejected",
    "approved",
    "unclassified",
)
COLUMN_LABELS = {
    "pending_submit": "待提交",
    "pending_approval": "审批中",
    "rejected": "已驳回",
    "approved": "已通过",
    "unclassified": "未分类",
}
COLUMN_TONES = {
    "pending_submit": "neutral",
    "pending_approval": "info",
    "rejected": "danger",
    "approved": "success",
    "unclassified": "muted",
}
SUMMARY_KEYS = (
    "total_count",
    "rejected_count",
    "actual_total",
    "confirmed_amount",
    "unconfirmed_amount",
)
SUMMARY_LABELS = {
    "total_count": "回款笔数",
    "rejected_count": "已驳回",
    "actual_total": "回款金额",
    "confirmed_amount": "已确认",
    "unconfirmed_amount": "未确认",
}
ZERO_AMOUNTS = {
    "amount": "0.00",
    "actual_amount": "0.00",
    "confirmed_amount": "0.00",
    "unconfirmed_amount": "0.00",
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
    name: str = "首付款",
    team_id: int = 1,
) -> PaymentPlan:
    return PaymentPlan(
        id=plan_id,
        team_id=team_id,
        contract_id=contract_id,
        plan_number=f"PP-{plan_id:04d}",
        stage_name=name,
        planned_amount=Decimal("1000.00"),
        due_date=date(2026, 6, 1),
        status="PENDING",
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
    confirmation_status: str | None = PaymentConfirmationStatus.PENDING,
    approval_id: int | None = None,
    creator_id: str = "7",
    creator_name: str = "销售张",
    payer: str | None = None,
    commission_member_name: str | None = None,
    team_id: int = 1,
) -> PaymentRecord:
    return PaymentRecord(
        id=record_id,
        team_id=team_id,
        record_number=f"PR-{record_id:04d}",
        payment_plan_id=plan_id,
        actual_amount=Decimal(amount),
        actual_payer_name=payer,
        payment_date=payment_date,
        creator_id=creator_id,
        creator_name=creator_name,
        commission_member_name=commission_member_name,
        confirmation_status=confirmation_status,
        approval_phase=approval_phase,
        approval_id=approval_id,
        created_time=datetime(2026, 8, min(record_id, 28)),
        updated_time=datetime(2026, 8, min(record_id, 28)),
    )


def _approval(
    approval_id: int,
    *,
    record_id: int,
    status: str,
    team_id: int = 1,
    business_type: str = BusinessType.PAYMENT,
) -> Approval:
    return Approval(
        id=approval_id,
        team_id=team_id,
        business_type=business_type,
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
        InvoiceApplication.__table__,
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
    return client.get("/v1/payments/payment-records/board", params=params)


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


def _link(db, record_id: int, approval_id: int) -> None:
    db.query(PaymentRecord).filter(PaymentRecord.id == record_id).one().approval_id = approval_id


def test_board_route_precedes_dynamic_record_route() -> None:
    board_route = next(
        route for route in payments_api.router.routes
        if getattr(route, "path", None) == "/v1/payments/payment-records/board"
    )
    detail_route = next(
        route for route in payments_api.router.routes
        if getattr(route, "path", None) == "/v1/payments/payment-records/{record_id}"
    )
    assert payments_api.router.routes.index(board_route) < payments_api.router.routes.index(detail_route)
    query_names = {field.alias or field.name for field in board_route.dependant.query_params}
    assert {"skip", "limit", "page", "page_size"}.isdisjoint(query_names)
    assert {
        "contract_id",
        "payment_plan_id",
        "payment_date_start",
        "payment_date_end",
        "min_amount",
        "actual_amount",
        "creator_id",
        "keyword",
        "search",
        "confirmation_status",
        "me",
        "approval_status",
        "filters",
        "sorts",
    } <= query_names


def test_missing_permission_is_forbidden_before_aggregation(api_env) -> None:
    api_env.db.add_all([
        _contract(1, name="甲合同"),
        _plan(1, contract_id=1),
        _record(1, plan_id=1, amount="10.00", payment_date=date(2026, 6, 1)),
    ])
    api_env.db.commit()

    response = _board(api_env.client)

    assert response.status_code == 403
    assert response.json()["detail"] == "没有查看回款记录的权限"
    assert inspect(api_env.db.bind).has_table("crm_payment_records")


def test_me_with_view_all_limits_scope_to_contract_creator(api_env, monkeypatch) -> None:
    _freeze(monkeypatch, date(2026, 10, 12))
    api_env.db.add_all([
        _contract(1, name="甲合同", owner_id="8", creator_id="7"),
        _contract(2, name="乙合同", customer_id=2, opportunity_id=2, owner_id="7", creator_id="8"),
        _plan(1, contract_id=1),
        _plan(2, contract_id=2),
        _record(1, plan_id=1, amount="10.00", payment_date=date(2026, 6, 2), creator_id="8"),
        _record(2, plan_id=2, amount="90.00", payment_date=date(2026, 6, 2), creator_id="7"),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "payment:view:all")

    response = _board(api_env.client, me=True)

    assert response.status_code == 200, response.text
    body = response.json()
    assert _columns(body)["pending_submit"]["count"] == 1
    assert _columns(body)["pending_submit"]["items"][0]["id"] == 1
    assert _metric(body, "actual_total")["value"] == "10.00"
    assert {point["date"]: point for point in body["trends"]}["2026-06"] == {
        "date": "2026-06",
        "count": 1,
        "actual_amount": "10.00",
        "confirmed_amount": "0.00",
        "unconfirmed_amount": "10.00",
    }


def test_own_only_excludes_other_creator_from_every_aggregate(api_env, monkeypatch) -> None:
    _freeze(monkeypatch, date(2026, 10, 12))
    api_env.db.add_all([
        _contract(1, name="甲合同", owner_id="8", creator_id="7"),
        _contract(2, name="乙合同", customer_id=2, opportunity_id=2, owner_id="7", creator_id="8"),
        _plan(1, contract_id=1),
        _plan(2, contract_id=2),
        _record(
            1,
            plan_id=1,
            amount="12.50",
            payment_date=date(2026, 6, 3),
            approval_phase="rejected",
            confirmation_status=PaymentConfirmationStatus.CONFIRMED,
            creator_id="8",
        ),
        _record(
            2,
            plan_id=2,
            amount="80.00",
            payment_date=date(2026, 6, 3),
            approval_phase="rejected",
            confirmation_status=PaymentConfirmationStatus.CONFIRMED,
            creator_id="7",
        ),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "payment:view:own")

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    body = response.json()
    columns = _columns(body)
    assert columns["rejected"]["count"] == 1
    assert columns["rejected"]["items"][0]["id"] == 1
    assert _metric(body, "total_count")["value"] == 1
    assert _metric(body, "rejected_count")["value"] == 1
    assert _metric(body, "actual_total")["value"] == "12.50"
    assert _metric(body, "confirmed_amount")["value"] == "12.50"
    assert _metric(body, "unconfirmed_amount")["value"] == "0.00"
    assert all(item["id"] != 2 for column in columns.values() for item in column["items"])
    assert {point["date"]: point for point in body["trends"]}["2026-06"]["count"] == 1
    assert {point["date"]: point for point in body["trends"]}["2026-06"]["actual_amount"] == "12.50"


def test_board_groups_canonical_columns_and_keeps_confirmation_independent(api_env, monkeypatch) -> None:
    _freeze(monkeypatch, date(2026, 10, 12))
    api_env.db.add_all([
        _contract(1, name="甲合同"),
        _plan(1, contract_id=1),
        _record(1, plan_id=1, amount="10.10", payment_date=date(2026, 5, 2), approval_phase="draft", payer="甲付款方", commission_member_name="协作王"),
        _record(2, plan_id=1, amount="20.00", payment_date=date(2026, 6, 3), approval_phase="draft", confirmation_status=PaymentConfirmationStatus.CONFIRMED),
        _approval(20, record_id=2, status=ApprovalStatus.PENDING),
        _record(3, plan_id=1, amount="30.25", payment_date=date(2026, 7, 4), approval_phase="approved", confirmation_status=PaymentConfirmationStatus.DISPUTED),
        _approval(21, record_id=3, status=ApprovalStatus.REJECTED),
        _record(4, plan_id=1, amount="40.00", payment_date=date(2026, 8, 5), approval_phase="draft", confirmation_status=PaymentConfirmationStatus.CONFIRMED),
        _approval(22, record_id=4, status=ApprovalStatus.APPROVED),
        _record(5, plan_id=1, amount="50.40", payment_date=date(2026, 9, 6), approval_phase="withdrawn", confirmation_status="UNKNOWN"),
        _record(6, plan_id=1, amount="1000.00", payment_date=date(2026, 6, 1), approval_phase="approved", team_id=2),
        _record(7, plan_id=1, amount="8.00", payment_date=date(2026, 6, 7), approval_phase="approved"),
        _approval(23, record_id=7, status=ApprovalStatus.APPROVED, team_id=2),
        _record(8, plan_id=1, amount="9.00", payment_date=date(2026, 6, 8), approval_phase="approved"),
        _approval(24, record_id=8, status=ApprovalStatus.APPROVED, business_type=BusinessType.CONTRACT),
    ])
    api_env.db.flush()
    _link(api_env.db, 2, 20)
    _link(api_env.db, 3, 21)
    _link(api_env.db, 4, 22)
    _link(api_env.db, 7, 23)
    _link(api_env.db, 8, 24)
    api_env.db.commit()
    loaded_unknown = api_env.db.query(PaymentRecord).filter(PaymentRecord.id == 5).one()
    api_env.db.refresh(loaded_unknown)
    assert loaded_unknown.confirmation_status == "UNKNOWN"
    _grant(
        api_env.db,
        7,
        "payment:view:all",
        "payment:record:edit",
        "payment:record:delete",
        "payment:submit",
    )

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    body = response.json()
    columns = _columns(body)
    assert list(columns) == list(COLUMN_KEYS)
    assert {key: columns[key]["label"] for key in COLUMN_KEYS} == COLUMN_LABELS
    assert {key: columns[key]["tone"] for key in COLUMN_KEYS} == COLUMN_TONES
    assert {key: columns[key]["count"] for key in COLUMN_KEYS} == {
        "pending_submit": 1,
        "pending_approval": 1,
        "rejected": 1,
        "approved": 3,
        "unclassified": 1,
    }
    assert columns["pending_submit"]["actual_amount"] == "10.10"
    assert columns["pending_submit"]["confirmed_amount"] == "0.00"
    assert columns["pending_approval"]["confirmed_amount"] == "20.00"
    assert columns["pending_approval"]["unconfirmed_amount"] == "0.00"
    assert columns["rejected"]["confirmed_amount"] == "0.00"
    assert columns["rejected"]["unconfirmed_amount"] == "30.25"
    assert columns["approved"]["actual_amount"] == "57.00"
    assert columns["approved"]["confirmed_amount"] == "40.00"
    assert columns["approved"]["unconfirmed_amount"] == "17.00"
    assert columns["unclassified"]["actual_amount"] == "50.40"
    assert columns["unclassified"]["unconfirmed_amount"] == "50.40"
    assert all(item["id"] != 6 for column in columns.values() for item in column["items"])

    pending = columns["pending_submit"]["items"][0]
    assert isinstance(pending["id"], int)
    assert pending["id"] == 1
    assert pending["title"] == "PR-0001"
    assert pending["subtitle"] == "甲客户"
    assert pending["amount"] == "10.10"
    assert pending["actual_amount"] == "10.10"
    assert pending["date"] == "2026-05-02"
    assert pending["owner"] == {"id": "7", "name": "销售张", "avatar_url": "https://cdn.example/ada.png"}
    assert pending["status"] == "pending_submit"
    assert pending["metadata"] == {
        "customer_name": "甲客户",
        "contract_name": "甲合同",
        "actual_payer_name": "甲付款方",
        "creator_name": "销售张",
        "owner_name": "销售张",
        "commission_member_name": "协作王",
        "approval_phase": "draft",
        "approval_id": None,
        "confirmation_status": "PENDING",
    }
    assert pending["action_state"] == {"can_edit": True, "can_delete": True, "can_resubmit": False}

    by_id = {item["id"]: item for column in columns.values() for item in column["items"]}
    assert by_id[2]["status"] == "pending_approval"
    assert by_id[2]["metadata"]["confirmation_status"] == "CONFIRMED"
    assert by_id[2]["metadata"]["approval_phase"] == "draft"
    assert by_id[2]["metadata"]["approval_id"] == 20
    assert by_id[2]["action_state"] == {"can_edit": False, "can_delete": False, "can_resubmit": False}
    assert by_id[3]["status"] == "rejected"
    assert by_id[3]["metadata"]["confirmation_status"] == "DISPUTED"
    assert by_id[3]["action_state"]["can_resubmit"] is True
    assert by_id[4]["status"] == "approved"
    assert by_id[4]["metadata"]["confirmation_status"] == "CONFIRMED"
    assert by_id[4]["action_state"] == {"can_edit": False, "can_delete": False, "can_resubmit": False}
    assert by_id[5]["status"] == "unclassified"
    assert by_id[5]["metadata"]["confirmation_status"] is None
    assert by_id[7]["status"] == "approved"
    assert by_id[8]["status"] == "approved"

    assert [metric["key"] for metric in body["summary"]] == list(SUMMARY_KEYS)
    assert [metric["label"] for metric in body["summary"]] == [SUMMARY_LABELS[key] for key in SUMMARY_KEYS]
    assert _metric(body, "total_count")["value"] == 7
    assert _metric(body, "rejected_count")["value"] == 1
    assert _metric(body, "actual_total")["value"] == "167.75"
    assert _metric(body, "confirmed_amount")["value"] == "60.00"
    assert _metric(body, "unconfirmed_amount")["value"] == "107.75"
    assert {point["date"]: point["count"] for point in body["trends"]} == {
        "2026-04": 0,
        "2026-05": 1,
        "2026-06": 3,
        "2026-07": 1,
        "2026-08": 1,
        "2026-09": 1,
    }
    june = {point["date"]: point for point in body["trends"]}["2026-06"]
    assert june["actual_amount"] == "37.00"
    assert june["confirmed_amount"] == "20.00"
    assert june["unconfirmed_amount"] == "17.00"


def test_confirmed_without_approval_evidence_stays_pending_submit(api_env) -> None:
    api_env.db.add_all([
        _contract(1, name="甲合同"),
        _plan(1, contract_id=1),
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
    body = response.json()
    column = _columns(body)["pending_submit"]
    assert column["count"] == 1
    assert column["confirmed_amount"] == "15.00"
    assert column["items"][0]["status"] == "pending_submit"
    assert column["items"][0]["metadata"]["confirmation_status"] == "CONFIRMED"
    assert _columns(body)["approved"]["count"] == 0
    assert _metric(body, "confirmed_amount")["value"] == "15.00"


def test_payment_date_bounds_follow_active_query_branch(api_env, monkeypatch) -> None:
    _freeze(monkeypatch, date(2026, 10, 12))
    api_env.db.add_all([
        _contract(1, name="甲合同"),
        _plan(1, contract_id=1),
        _record(1, plan_id=1, amount="10.00", payment_date=date(2026, 6, 15), confirmation_status=PaymentConfirmationStatus.CONFIRMED),
        _record(2, plan_id=1, amount="20.00", payment_date=date(2026, 8, 15)),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "payment:view:all")

    legacy = _board(api_env.client, payment_date_start="2026-06-01", payment_date_end="2026-06-30")
    unified = _board(
        api_env.client,
        payment_date_start="2026-08-01",
        payment_date_end="2026-08-31",
        filters='[{"field":"payment_date","op":"after","value":"2026-06-01"},{"field":"payment_date","op":"before","value":"2026-06-30"}]',
    )

    assert legacy.status_code == 200, legacy.text
    assert unified.status_code == 200, unified.text
    assert legacy.json()["trends"] == [{
        "date": "2026-06",
        "count": 1,
        "actual_amount": "10.00",
        "confirmed_amount": "10.00",
        "unconfirmed_amount": "0.00",
    }]
    assert unified.json()["trends"] == legacy.json()["trends"]
    assert _metric(legacy.json(), "actual_total")["value"] == "10.00"
    assert _metric(unified.json(), "actual_total")["value"] == "10.00"


def test_search_and_text_filters_limit_complete_population(api_env) -> None:
    api_env.db.add_all([
        _contract(1, name="甲合同"),
        _plan(1, contract_id=1),
        _record(1, plan_id=1, amount="10.00", payment_date=date(2026, 6, 1), payer="甲付款方"),
        _record(2, plan_id=1, amount="30.00", payment_date=date(2026, 6, 2), payer="乙付款方"),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "payment:view:all")

    response = _board(
        api_env.client,
        search="PR-0001",
        customer_name="甲客户",
        actual_payer_name="甲付款",
        contract_name="甲合同",
        min_amount=10,
        actual_amount=10,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert _columns(body)["pending_submit"]["count"] == 1
    assert _columns(body)["pending_submit"]["items"][0]["id"] == 1
    assert _metric(body, "actual_total")["value"] == "10.00"


def test_external_confirmed_tab_is_not_canonical_approval(api_env) -> None:
    api_env.db.add_all([
        _contract(1, name="甲合同"),
        _plan(1, contract_id=1),
        _record(1, plan_id=1, amount="10.00", payment_date=date(2026, 6, 1), approval_phase="approved"),
        _record(
            2,
            plan_id=1,
            amount="20.00",
            payment_date=date(2026, 6, 2),
            approval_phase="draft",
            confirmation_status=PaymentConfirmationStatus.CONFIRMED,
        ),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "payment:view:all")

    confirmed_tab = _board(api_env.client, approval_status="confirmed")
    approved_tab = _board(api_env.client, approval_status="approved")

    assert confirmed_tab.status_code == 400
    assert "approved" in confirmed_tab.json()["detail"]
    assert approved_tab.status_code == 200, approved_tab.text
    assert _columns(approved_tab.json())["approved"]["count"] == 1
    assert _columns(approved_tab.json())["approved"]["items"][0]["id"] == 1
    assert _columns(approved_tab.json())["pending_submit"]["count"] == 0


def test_empty_population_returns_ordered_zero_columns(api_env) -> None:
    api_env.db.add_all([
        _contract(1, name="其他团队合同", team_id=2),
        _plan(1, contract_id=1, team_id=2),
        _record(1, plan_id=1, amount="50.00", payment_date=date(2026, 6, 1), team_id=2),
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
    assert _metric(body, "total_count")["value"] == 0
    assert _metric(body, "rejected_count")["value"] == 0
    assert _metric(body, "actual_total")["value"] == "0.00"
    assert _metric(body, "confirmed_amount")["value"] == "0.00"
    assert _metric(body, "unconfirmed_amount")["value"] == "0.00"
    assert body["trends"] == []


def test_preview_limit_keeps_full_totals_and_sort_changes_order_only(api_env, monkeypatch) -> None:
    _freeze(monkeypatch, date(2026, 10, 12))
    api_env.db.add_all([
        _contract(1, name="甲合同"),
        _plan(1, contract_id=1),
        *[
            _record(
                index,
                plan_id=1,
                amount=f"{10 - index}.00",
                payment_date=date(2026, 6, index),
                confirmation_status=PaymentConfirmationStatus.CONFIRMED if index == 1 else PaymentConfirmationStatus.PENDING,
            )
            for index in range(1, 8)
        ],
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "payment:view:all")

    default_response = _board(api_env.client)
    sorted_response = _board(api_env.client, order_by="actual_amount", order_dir="desc")

    assert default_response.status_code == 200, default_response.text
    assert sorted_response.status_code == 200, sorted_response.text
    default_body = default_response.json()
    sorted_body = sorted_response.json()
    default_column = _columns(default_body)["pending_submit"]
    sorted_column = _columns(sorted_body)["pending_submit"]
    assert default_column["count"] == 7
    assert [item["id"] for item in default_column["items"]] == [7, 6, 5, 4, 3]
    assert all(isinstance(item["id"], int) for item in default_column["items"])
    assert default_column["has_more"] is True
    assert default_column["remaining_count"] == 2
    assert default_column["actual_amount"] == "42.00"
    assert default_column["confirmed_amount"] == "9.00"
    assert [item["id"] for item in sorted_column["items"]] == [1, 2, 3, 4, 5]
    assert sorted_column["count"] == default_column["count"]
    assert sorted_column["actual_amount"] == default_column["actual_amount"]
    assert sorted_column["confirmed_amount"] == default_column["confirmed_amount"]
    assert sorted_column["unconfirmed_amount"] == default_column["unconfirmed_amount"]
    assert _metric(sorted_body, "actual_total")["value"] == _metric(default_body, "actual_total")["value"]
    assert sorted_body["trends"] == default_body["trends"]
    for key in COLUMN_KEYS:
        if key == "pending_submit":
            continue
        assert _columns(default_body)[key]["count"] == 0
        assert {name: _columns(default_body)[key][name] for name in ZERO_AMOUNTS} == ZERO_AMOUNTS


def test_approval_exclude_removes_approved_from_counts_amounts_and_trends(api_env, monkeypatch) -> None:
    _freeze(monkeypatch, date(2026, 10, 12))
    api_env.db.add_all([
        _contract(1, name="甲合同"),
        _plan(1, contract_id=1),
        _record(
            1,
            plan_id=1,
            amount="40.00",
            payment_date=date(2026, 6, 5),
            approval_phase="draft",
            confirmation_status=PaymentConfirmationStatus.CONFIRMED,
        ),
        _approval(22, record_id=1, status=ApprovalStatus.APPROVED),
        _record(2, plan_id=1, amount="15.25", payment_date=date(2026, 6, 6), approval_phase="rejected"),
        _approval(23, record_id=2, status=ApprovalStatus.REJECTED),
    ])
    api_env.db.flush()
    _link(api_env.db, 1, 22)
    _link(api_env.db, 2, 23)
    api_env.db.commit()
    _grant(api_env.db, 7, "payment:view:all")

    response = _board(api_env.client, approval_status_exclude="approved")

    assert response.status_code == 200, response.text
    body = response.json()
    columns = _columns(body)
    assert columns["approved"]["count"] == 0
    assert columns["approved"]["items"] == []
    assert columns["rejected"]["count"] == 1
    assert columns["rejected"]["items"][0]["id"] == 2
    assert all(item["id"] != 1 for column in columns.values() for item in column["items"])
    assert _metric(body, "total_count")["value"] == 1
    assert _metric(body, "actual_total")["value"] == "15.25"
    assert _metric(body, "confirmed_amount")["value"] == "0.00"
    assert _metric(body, "unconfirmed_amount")["value"] == "15.25"
    june = {point["date"]: point for point in body["trends"]}["2026-06"]
    assert june["count"] == 1
    assert june["actual_amount"] == "15.25"
    assert june["confirmed_amount"] == "0.00"
    assert june["unconfirmed_amount"] == "15.25"

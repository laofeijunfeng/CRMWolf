"""Payment plan and payment record export API tests (Task 8)."""

import io
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable
from sqlalchemy.types import BigInteger

from app.api.payments import router as payments_router
from app.core import deps
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.invoice import InvoiceApplication, InvoiceApplicationStatus, InvoiceType
from app.models.opportunity import Opportunity
from app.models.payment import PaymentConfirmationStatus, PaymentPlan, PaymentPlanStatus, PaymentRecord
from app.models.user import User


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        User.__table__,
        Customer.__table__,
        Opportunity.__table__,
        Contract.__table__,
        PaymentPlan.__table__,
        PaymentRecord.__table__,
        InvoiceApplication.__table__,
    ]
    with engine.begin() as connection:
        for table in tables:
            connection.execute(CreateTable(table))
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def client(db_session, monkeypatch):
    import app.api.payments as payments_module

    test_session_factory = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(payments_module, "SessionLocal", test_session_factory, raising=False)

    app = FastAPI()
    app.include_router(payments_router)
    app.dependency_overrides[deps.get_db] = lambda: db_session
    app.dependency_overrides[deps.get_current_user_team] = lambda: 1
    app.dependency_overrides[deps.get_current_active_user] = lambda: SimpleNamespace(
        id=1,
        name="销售张",
        status="active",
    )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def _grant(monkeypatch, *codes: str) -> None:
    from app.crud.permission import permission_crud

    monkeypatch.setattr(
        permission_crud,
        "get_user_permissions",
        lambda *args, **kwargs: [SimpleNamespace(code=code) for code in codes],
    )


def _workbook_rows(response) -> list[tuple]:
    workbook = load_workbook(io.BytesIO(response.content), read_only=True)
    return list(workbook.active.values)


def _seed_user(db_session, user_id: int = 1, name: str = "销售张") -> None:
    if db_session.query(User).filter_by(id=user_id).first() is None:
        db_session.add(User(id=user_id, email=f"user{user_id}@example.com", name=name))


def _seed_customer(db_session, customer_id: int = 1, account_name: str = "客户A") -> None:
    if db_session.query(Customer).filter_by(id=customer_id).first() is None:
        db_session.add(Customer(
            id=customer_id,
            team_id=1,
            public_id=f"cus_{customer_id:032d}",
            account_name=account_name,
            city="上海",
            creator_id=str(customer_id),
        ))


def _seed_opportunity(
    db_session,
    *,
    opportunity_id: int = 1,
    customer_id: int = 1,
    owner_id: str = "1",
) -> None:
    if db_session.query(Opportunity).filter_by(id=opportunity_id).first() is None:
        db_session.add(Opportunity(
            id=opportunity_id,
            public_id=f"opp_{opportunity_id:032d}",
            team_id=1,
            opportunity_number=f"OPP-{opportunity_id:03d}",
            opportunity_name=f"商机{opportunity_id}",
            customer_id=customer_id,
            total_amount=Decimal("1000"),
            user_count=10,
            unit_price=Decimal("100"),
            license_type="SUBSCRIPTION",
            purchase_type="NEW",
            expected_closing_date=date(2026, 12, 31),
            owner_id=owner_id,
            creator_id=owner_id,
        ))


def _seed_contract(
    db_session,
    *,
    contract_id: int = 1,
    customer_id: int = 1,
    opportunity_id: int = 1,
    owner_id: str = "1",
    creator_id: str = "1",
    contract_name: str = "合同A",
) -> None:
    if db_session.query(Contract).filter_by(id=contract_id).first() is None:
        db_session.add(Contract(
            id=contract_id,
            team_id=1,
            contract_number=f"CT-{contract_id:03d}",
            contract_name=contract_name,
            customer_id=customer_id,
            opportunity_id=opportunity_id,
            user_count=10,
            total_amount=Decimal("1000"),
            license_type="SUBSCRIPTION",
            standard_unit_price=Decimal("100"),
            owner_id=owner_id,
            creator_id=creator_id,
        ))


def _seed_plan(db_session, **overrides) -> PaymentPlan:
    defaults = {
        "team_id": 1,
        "contract_id": 1,
        "plan_number": "PP-001",
        "stage_name": "首付款",
        "planned_amount": Decimal("1000.00"),
        "due_date": date(2026, 9, 10),
        "status": PaymentPlanStatus.PENDING,
    }
    defaults.update(overrides)
    plan = PaymentPlan(**defaults)
    db_session.add(plan)
    return plan


def _seed_record(db_session, **overrides) -> PaymentRecord:
    defaults = {
        "team_id": 1,
        "record_number": "PR-001",
        "payment_plan_id": 1,
        "actual_amount": Decimal("800.00"),
        "actual_payer_name": "付款方A",
        "payment_date": date(2026, 8, 10),
        "creator_id": "1",
        "creator_name": "销售张",
        "confirmation_status": PaymentConfirmationStatus.PENDING,
        "commission_member_name": "协作李",
        "created_time": datetime(2026, 8, 10, 9, 30, 0),
        "updated_time": datetime(2026, 8, 10, 9, 30, 0),
    }
    defaults.update(overrides)
    record = PaymentRecord(**defaults)
    db_session.add(record)
    return record


def _seed_owned_graph(db_session, *, owner_id: str, contract_id: int) -> None:
    user_id = int(owner_id)
    _seed_user(db_session, user_id=user_id, name=f"负责人{owner_id}")
    _seed_customer(db_session, customer_id=contract_id, account_name=f"客户{owner_id}")
    _seed_opportunity(
        db_session,
        opportunity_id=contract_id,
        customer_id=contract_id,
        owner_id=owner_id,
    )
    _seed_contract(
        db_session,
        contract_id=contract_id,
        customer_id=contract_id,
        opportunity_id=contract_id,
        owner_id=owner_id,
        creator_id=owner_id,
        contract_name=f"合同{owner_id}",
    )


def test_payment_plan_export_requires_permission_and_preserves_view_own_scope(
    client,
    db_session,
    monkeypatch,
):
    _grant(monkeypatch, "payment:view:own")
    _seed_owned_graph(db_session, owner_id="1", contract_id=1)
    _seed_owned_graph(db_session, owner_id="2", contract_id=2)
    _seed_plan(db_session, contract_id=1, plan_number="PP-MINE")
    _seed_plan(db_session, contract_id=2, plan_number="PP-OTHER")
    db_session.commit()

    denied = client.post("/v1/payments/payment-plans/export", json={
        "fields": ["plan_number"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })
    assert denied.status_code == 403

    _grant(monkeypatch, "payment:plan:export", "payment:view:own")
    allowed = client.post("/v1/payments/payment-plans/export", json={
        "fields": ["plan_number"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })
    assert allowed.status_code == 200
    rows = _workbook_rows(allowed)
    assert rows[0] == ("计划编号",)
    assert [row[0] for row in rows[1:]] == ["PP-MINE"]


def test_payment_plan_export_maps_pending_tab_and_exports_all_rows(
    client,
    db_session,
    monkeypatch,
):
    _grant(monkeypatch, "payment:plan:export", "payment:view:all")
    _seed_owned_graph(db_session, owner_id="1", contract_id=1)
    _seed_plan(
        db_session,
        plan_number="PP-DONE",
        status=PaymentPlanStatus.COMPLETED,
        due_date=date(2026, 1, 1),
    )
    for index in range(76):
        _seed_plan(
            db_session,
            plan_number=f"PP-{index:02d}",
            status=PaymentPlanStatus.PENDING,
            due_date=date(2026, 2, 1) + timedelta(days=index),
        )
    db_session.commit()

    response = client.post("/v1/payments/payment-plans/export", json={
        "fields": ["plan_number", "status", "plan_amount", "due_date"],
        "tab": "pending",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 200
    rows = _workbook_rows(response)
    assert rows[0] == ("计划编号", "状态", "计划金额", "计划日期")
    assert len(rows) == 77
    assert "PP-DONE" not in [row[0] for row in rows[1:]]
    assert rows[1][0] == "PP-00"
    assert rows[76][0] == "PP-75"
    assert rows[1][1] == "待登记"
    assert rows[1][2] == 1000
    due_date = rows[1][3]
    assert datetime(due_date.year, due_date.month, due_date.day) == datetime(2026, 2, 1)


def test_payment_record_export_maps_confirmed_tab_to_approved(
    client,
    db_session,
    monkeypatch,
):
    _grant(monkeypatch, "payment:record:export", "payment:view:all")
    _seed_owned_graph(db_session, owner_id="1", contract_id=1)
    _seed_plan(db_session, plan_number="PP-001")
    _seed_record(
        db_session,
        record_number="PR-PENDING",
        confirmation_status=PaymentConfirmationStatus.PENDING,
        payment_date=date(2026, 8, 9),
    )
    _seed_record(
        db_session,
        record_number="PR-CONFIRMED",
        confirmation_status=PaymentConfirmationStatus.CONFIRMED,
        payment_date=date(2026, 8, 11),
    )
    db_session.commit()

    response = client.post("/v1/payments/payment-records/export", json={
        "fields": ["record_number", "confirmation_status"],
        "tab": "confirmed",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 200
    rows = _workbook_rows(response)
    assert rows[0] == ("回款编号", "状态")
    assert [row[0] for row in rows[1:]] == ["PR-CONFIRMED"]
    assert rows[1][1] == "已确认"


def test_payment_record_export_projects_latest_invoice_title_and_owner_name(
    client,
    db_session,
    monkeypatch,
):
    _grant(monkeypatch, "payment:record:export", "payment:view:all")
    _seed_user(db_session, user_id=1, name="销售张")
    _seed_user(db_session, user_id=2, name="合同李")
    _seed_customer(db_session, customer_id=1, account_name="客户A")
    _seed_opportunity(db_session, opportunity_id=1, customer_id=1, owner_id="1")
    _seed_contract(
        db_session,
        contract_id=1,
        customer_id=1,
        opportunity_id=1,
        owner_id="2",
        creator_id="2",
        contract_name="合同A",
    )
    _seed_plan(db_session, plan_number="PP-001")
    _seed_record(db_session, record_number="PR-001", actual_payer_name="付款方A")
    db_session.add(InvoiceApplication(
        team_id=1,
        application_number="INV-PLAN",
        customer_id=1,
        contract_id=1,
        opportunity_id=1,
        payment_plan_id=1,
        payment_record_id=None,
        invoice_amount=Decimal("800"),
        invoice_type=InvoiceType.VAT_NORMAL,
        status=InvoiceApplicationStatus.ISSUED,
        applicant_id="1",
        invoice_title_type="COMPANY",
        invoice_title_text="计划级抬头",
        invoice_taxpayer_id="TAX-PLAN",
        created_time=datetime(2026, 8, 12, 10, 0, 0),
    ))
    db_session.add(InvoiceApplication(
        team_id=1,
        application_number="INV-RECORD",
        customer_id=1,
        contract_id=1,
        opportunity_id=1,
        payment_plan_id=1,
        payment_record_id=1,
        invoice_amount=Decimal("800"),
        invoice_type=InvoiceType.VAT_NORMAL,
        status=InvoiceApplicationStatus.ISSUED,
        applicant_id="1",
        invoice_title_type="COMPANY",
        invoice_title_text="记录级抬头",
        invoice_taxpayer_id="TAX-RECORD",
        created_time=datetime(2026, 8, 11, 10, 0, 0),
    ))
    db_session.commit()

    response = client.post("/v1/payments/payment-records/export", json={
        "fields": [
            "record_number",
            "customer_name",
            "invoice_title_text",
            "contract_name",
            "owner_name",
            "commission_member_name",
        ],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 200
    rows = _workbook_rows(response)
    assert rows[0] == ("回款编号", "客户名称", "发票抬头", "合同名称", "负责人", "团队成员")
    assert rows[1] == ("PR-001", "客户A", "记录级抬头", "合同A", "销售张", "协作李")


def test_payment_exports_leave_missing_business_numbers_blank(
    client,
    db_session,
    monkeypatch,
):
    _grant(
        monkeypatch,
        "payment:plan:export",
        "payment:record:export",
        "payment:view:all",
    )
    _seed_owned_graph(db_session, owner_id="1", contract_id=1)
    _seed_plan(db_session, plan_number="")
    _seed_record(db_session, record_number="")
    db_session.commit()

    plan_response = client.post("/v1/payments/payment-plans/export", json={
        "fields": ["plan_number", "stage_name"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })
    record_response = client.post("/v1/payments/payment-records/export", json={
        "fields": ["record_number", "actual_payer_name"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })

    assert plan_response.status_code == 200
    assert record_response.status_code == 200
    plan_rows = _workbook_rows(plan_response)
    record_rows = _workbook_rows(record_response)
    assert plan_rows[1][0] is None
    assert plan_rows[1][1] == "首付款"
    assert record_rows[1][0] is None
    assert record_rows[1][1] == "付款方A"

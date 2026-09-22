"""Opportunity and contract export API tests (Task 7)."""

import io
import itertools
from datetime import date, datetime, timedelta
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.api.contracts import router as contracts_router
from app.api.opportunities import router as opportunities_router
from app.core import deps
from app.core.database import Base
from app.models.contract import Contract
from app.models.customer import Customer, CustomerProduct, CustomerStatus
from app.models.lead import Lead, LeadProduct
from app.models.license_application import LicenseApplication
from app.models.approval import Approval, ApprovalFlow, ApprovalNode, ApprovalRecord
from app.models.opportunity import Opportunity, OpportunityProductModule
from app.models.product import Product, ProductModule
from app.models.user import User, UserStatus


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
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
        Product.__table__,
        ProductModule.__table__,
        Customer.__table__,
        CustomerProduct.__table__,
        Lead.__table__,
        LeadProduct.__table__,
        Opportunity.__table__,
        OpportunityProductModule.__table__,
        Contract.__table__,
        LicenseApplication.__table__,
        ApprovalFlow.__table__,
        ApprovalNode.__table__,
        Approval.__table__,
        ApprovalRecord.__table__,
    ]
    renamed_indexes = []
    for table in tables:
        for index in table.indexes:
            if index.name:
                renamed_indexes.append((index, index.name))
                index.name = f"{table.name}_{index.name}"
    try:
        Base.metadata.create_all(engine, tables=tables)
    finally:
        for index, original_name in renamed_indexes:
            index.name = original_name
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def client(db_session, monkeypatch):
    import app.api.contracts as contracts_module
    import app.api.opportunities as opportunities_module
    from sqlalchemy.orm import sessionmaker

    test_session_factory = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(opportunities_module, "SessionLocal", test_session_factory)
    monkeypatch.setattr(contracts_module, "SessionLocal", test_session_factory)

    app = FastAPI()
    app.include_router(opportunities_router)
    app.include_router(contracts_router)
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


_opportunity_number_seq = itertools.count(1001)


def _seed_opportunity(db_session, **overrides) -> None:
    if db_session.query(Customer).filter_by(id=1).first() is None:
        _seed_customer(db_session)
    defaults: dict = {
        "team_id": 1,
        "public_id": f"opp_{overrides.get('opportunity_name', '商机')}",
        "opportunity_number": next(_opportunity_number_seq),
        "opportunity_name": "商机A",
        "customer_id": 1,
        "total_amount": 50000.0,
        "unit_price": 500.0,
        "user_count": 10,
        "license_type": "SUBSCRIPTION",
        "purchase_type": "NEW",
        "expected_closing_date": date(2026, 12, 31),
        "owner_id": "1",
        "status": 0,
        "creator_id": "1",
    }
    defaults.update(overrides)
    db_session.add(Opportunity(**defaults))


def _seed_contract(db_session, **overrides) -> None:
    defaults: dict = {
        "team_id": 1,
        "contract_number": "HT-2026-001",
        "contract_name": "测试合同",
        "customer_id": 1,
        "opportunity_id": 1,
        "owner_id": "1",
        "signing_contact_id": 1,
        "user_count": 10,
        "total_amount": 50000.0,
        "license_type": "SUBSCRIPTION",
        "standard_unit_price": 500.0,
        "status": "DRAFT",
        "creator_id": "1",
    }
    defaults.update(overrides)
    db_session.add(Contract(**defaults))


def _seed_customer(db_session) -> None:
    db_session.add(Customer(
        team_id=1,
        public_id="cus_seed",
        account_name="客户A",
        city="上海",
        status=CustomerStatus.FOLLOWING.value,
        creator_id="1",
    ))


def test_opportunity_export_requires_export_permission(client, db_session, monkeypatch):
    _grant(monkeypatch)
    db_session.add(User(id=1, email="sales@example.com", name="销售张", status=UserStatus.ACTIVE))
    db_session.commit()

    response = client.post("/v1/opportunities/export", json={
        "fields": ["opportunity_name"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 403


def test_opportunity_export_keeps_owner_scope(client, db_session, monkeypatch):
    _grant(monkeypatch, "opportunity:export", "opportunity:view:own")
    db_session.add(User(id=1, email="sales@example.com", name="销售张", status=UserStatus.ACTIVE))
    _seed_opportunity(db_session, opportunity_name="我的商机", owner_id="1")
    _seed_opportunity(db_session, opportunity_name="他人商机", owner_id="2")
    db_session.commit()

    response = client.post("/v1/opportunities/export", json={
        "fields": ["opportunity_name"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 200
    rows = _workbook_rows(response)
    assert [row[0] for row in rows[1:]] == ["我的商机"]


def test_opportunity_export_won_tab_only_won_rows(client, db_session, monkeypatch):
    _grant(monkeypatch, "opportunity:export", "opportunity:view:own")
    db_session.add(User(id=1, email="sales@example.com", name="销售张", status=UserStatus.ACTIVE))
    _seed_opportunity(db_session, opportunity_name="跟进中商机", owner_id="1", status=0)
    _seed_opportunity(db_session, opportunity_name="已赢单商机", owner_id="1", status=1)
    db_session.commit()

    response = client.post("/v1/opportunities/export", json={
        "fields": ["opportunity_name"],
        "tab": "won",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 200
    rows = _workbook_rows(response)
    assert [row[0] for row in rows[1:]] == ["已赢单商机"]


def test_opportunity_export_writes_all_76_filtered_rows(client, db_session, monkeypatch):
    _grant(monkeypatch, "opportunity:export", "opportunity:view:own")
    db_session.add(User(id=1, email="sales@example.com", name="销售张", status=UserStatus.ACTIVE))
    base_time = datetime(2026, 9, 1, 9, 0, 0)
    for index in range(76):
        _seed_opportunity(
            db_session,
            opportunity_name=f"商机{index:02d}",
            owner_id="1",
            public_id=f"opp_{index:02d}",
            created_time=base_time + timedelta(minutes=index),
        )
    db_session.commit()

    response = client.post("/v1/opportunities/export", json={
        "fields": ["opportunity_name"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 200
    rows = _workbook_rows(response)
    assert len(rows) == 77
    assert rows[1][0] == "商机75"
    assert rows[76][0] == "商机00"


def test_opportunity_export_status_and_money_types(client, db_session, monkeypatch):
    _grant(monkeypatch, "opportunity:export", "opportunity:view:all")
    db_session.add(User(id=1, email="sales@example.com", name="销售张", status=UserStatus.ACTIVE))
    _seed_opportunity(
        db_session,
        opportunity_name="金额商机",
        owner_id="1",
        status=0,
        total_amount=12345.67,
        user_count=42,
        expected_closing_date=date(2026, 12, 31),
    )
    db_session.commit()

    response = client.post("/v1/opportunities/export", json={
        "fields": ["opportunity_name", "status", "total_amount", "user_count", "expected_closing_date"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 200
    rows = _workbook_rows(response)
    assert rows[0] == ("商机名称", "状态", "预计金额", "用户数", "预计成交日期")
    name, status_text, amount, user_count, closing = rows[1]
    assert name == "金额商机"
    assert status_text == "跟进中"
    assert amount == 12345.67
    assert user_count == 42
    assert datetime(closing.year, closing.month, closing.day) == datetime(2026, 12, 31)


def test_contract_export_rejects_owner_id_field(client, db_session, monkeypatch):
    _grant(monkeypatch, "contract:export")

    response = client.post("/v1/contracts/export", json={
        "fields": ["owner_id"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })
    assert response.status_code == 422


def test_contract_export_blank_contract_number_stays_blank(client, db_session, monkeypatch):
    _grant(monkeypatch, "contract:export", "contract:view:all")
    db_session.add(User(id=1, email="sales@example.com", name="销售张", status=UserStatus.ACTIVE))
    _seed_customer(db_session)
    _seed_opportunity(db_session, opportunity_name="合同商机", owner_id="1")
    _seed_contract(db_session, contract_number="HT-2026-001", owner_id="1", opportunity_id=1)
    db_session.commit()

    response = client.post("/v1/contracts/export", json={
        "fields": ["contract_number", "owner"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 200
    rows = _workbook_rows(response)
    assert rows[0] == ("合同编号", "负责人")
    assert rows[1][0] == "HT-2026-001"
    assert rows[1][1] == "销售张"


def test_opportunity_export_loads_product_off_the_stream_session(client, db_session, monkeypatch):
    from sqlalchemy import event

    _grant(monkeypatch, "opportunity:export", "opportunity:view:all")
    db_session.add(User(id=1, email="sales@example.com", name="销售张", status=UserStatus.ACTIVE))
    db_session.add(Product(
        id=1,
        public_id="prd_crm",
        team_id=1,
        code="CRM",
        name="CRM产品",
        created_by="1",
    ))
    _seed_opportunity(
        db_session,
        opportunity_name="带产品商机",
        owner_id="1",
        product_id=1,
    )
    db_session.commit()

    stream_product_sql: list[str] = []

    @event.listens_for(db_session, "do_orm_execute")
    def _capture_stream_product_sql(execute_state):
        statement = str(execute_state.statement)
        if "crm_products" in statement or "crm_opportunity_product_modules" in statement:
            stream_product_sql.append(statement)

    response = client.post("/v1/opportunities/export", json={
        "fields": ["opportunity_name", "product_name"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 200, response.text
    rows = _workbook_rows(response)
    assert rows[0] == ("商机名称", "产品")
    assert rows[1] == ("带产品商机", "CRM产品")
    assert stream_product_sql == []


def test_opportunity_and_contract_export_unknown_filter_returns_400(client, db_session, monkeypatch):
    _grant(monkeypatch, "opportunity:export", "opportunity:view:all", "contract:export", "contract:view:all")
    unknown_filter = [{"field": "missing", "op": "eq", "value": "x"}]

    opportunity_response = client.post("/v1/opportunities/export", json={
        "fields": ["opportunity_name"],
        "tab": "all",
        "filters": unknown_filter,
        "sorts": [],
    })
    contract_response = client.post("/v1/contracts/export", json={
        "fields": ["contract_name"],
        "tab": "all",
        "filters": unknown_filter,
        "sorts": [],
    })

    assert opportunity_response.status_code == 400, opportunity_response.text
    assert "未知筛选字段" in opportunity_response.text
    assert contract_response.status_code == 400, contract_response.text
    assert "未知筛选字段" in contract_response.text


def test_contract_export_reuses_batch_loaded_customer_and_opportunity(client, db_session, monkeypatch):
    import app.api.contracts as contracts_module

    _grant(monkeypatch, "contract:export", "contract:view:all")
    db_session.add(User(id=1, email="sales@example.com", name="销售张", status=UserStatus.ACTIVE))
    _seed_customer(db_session)
    _seed_opportunity(db_session, opportunity_name="合同商机", owner_id="1")
    _seed_contract(db_session, contract_number="HT-2026-001", owner_id="1", opportunity_id=1)
    _seed_contract(db_session, contract_number="HT-2026-002", owner_id="1", opportunity_id=1)
    db_session.commit()

    customer_lookups: list[int] = []
    opportunity_lookups: list[int] = []
    original_customer = contracts_module._get_customer_basic_info
    original_opportunity = contracts_module._get_opportunity_list_info

    def _spy_customer(db, customer_id):
        if customer_id is not None:
            customer_lookups.append(customer_id)
        return original_customer(db, customer_id)

    def _spy_opportunity(db, opportunity_id):
        if opportunity_id is not None:
            opportunity_lookups.append(opportunity_id)
        return original_opportunity(db, opportunity_id)

    monkeypatch.setattr(contracts_module, "_get_customer_basic_info", _spy_customer)
    monkeypatch.setattr(contracts_module, "_get_opportunity_list_info", _spy_opportunity)

    response = client.post("/v1/contracts/export", json={
        "fields": ["contract_number", "customer_name", "opportunity_name"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 200, response.text
    rows = _workbook_rows(response)
    assert rows[0] == ("合同编号", "客户名称", "商机名称")
    assert {row[0] for row in rows[1:]} == {"HT-2026-001", "HT-2026-002"}
    assert {row[1] for row in rows[1:]} == {"客户A"}
    assert {row[2] for row in rows[1:]} == {"合同商机"}
    assert customer_lookups == []
    assert opportunity_lookups == []

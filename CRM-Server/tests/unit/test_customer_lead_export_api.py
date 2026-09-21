"""Customer and lead export API tests (Task 6)."""

import io
from datetime import datetime, timedelta
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

from app.api.customers import router as customers_router
from app.api.leads import router as leads_router
from app.core import deps
from app.core.database import Base
from app.models.customer import Customer, CustomerMember, CustomerProduct, CustomerStatus
from app.models.lead import Lead, LeadProduct, LeadSource, LeadStatus
from app.models.product import Product
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
        Customer.__table__,
        CustomerMember.__table__,
        CustomerProduct.__table__,
        Lead.__table__,
        LeadProduct.__table__,
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
    import app.api.customers as customers_module
    import app.api.leads as leads_module

    test_session_factory = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(customers_module, "SessionLocal", test_session_factory)
    monkeypatch.setattr(leads_module, "SessionLocal", test_session_factory, raising=False)

    app = FastAPI()
    app.include_router(customers_router)
    app.include_router(leads_router)
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


def _seed_customer(db_session, **overrides) -> None:
    defaults: dict = {
        "team_id": 1,
        "public_id": f"cus_{overrides.get('public_id', overrides.get('account_name', '客户'))}",
        "account_name": "客户A",
        "city": "上海",
        "status": CustomerStatus.FOLLOWING.value,
        "creator_id": "1",
    }
    defaults.update(overrides)
    db_session.add(Customer(**defaults))


def _seed_lead(db_session, **overrides) -> None:
    defaults: dict = {
        "team_id": 1,
        "public_id": f"lead_{overrides.get('lead_name', '线索')}",
        "lead_name": "线索A",
        "source": LeadSource.WEBSITE_INQUIRY.value,
        "city": "上海",
        "contact_name": "王五",
        "contact_phone": "13800138000",
        "creator_id": "1",
        "status": LeadStatus.NEW.value,
    }
    defaults.update(overrides)
    db_session.add(Lead(**defaults))

def test_customer_export_requires_export_permission(client, db_session, monkeypatch):
    _grant(monkeypatch)
    db_session.add(User(id=1, email="sales@example.com", name="销售张", status=UserStatus.ACTIVE))
    _seed_customer(db_session)
    db_session.commit()

    response = client.post("/v1/customers/export", json={
        "fields": ["account_name"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 403


def test_customer_export_keeps_view_scope(client, db_session, monkeypatch):
    _grant(monkeypatch, "customer:export", "customer:view:own")
    db_session.add(User(id=1, email="sales@example.com", name="销售张", status=UserStatus.ACTIVE))
    _seed_customer(db_session, account_name="我的客户", owner_id="1")
    _seed_customer(db_session, account_name="他人客户", owner_id="2")
    db_session.commit()

    response = client.post("/v1/customers/export", json={
        "fields": ["account_name"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 200
    rows = _workbook_rows(response)
    assert rows[0] == ("客户名称",)
    assert [row[0] for row in rows[1:]] == ["我的客户"]


def test_customer_export_public_tab_uses_public_pool_query(client, db_session, monkeypatch):
    _grant(monkeypatch, "customer:export", "customer:view:own")
    _seed_customer(db_session, account_name="有主客户", owner_id="1")
    _seed_customer(db_session, account_name="公海客户", owner_id=None)
    db_session.commit()

    response = client.post("/v1/customers/export", json={
        "fields": ["account_name"],
        "tab": "public",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 200
    rows = _workbook_rows(response)
    assert [row[0] for row in rows[1:]] == ["公海客户"]

def test_customer_export_writes_all_76_filtered_rows(client, db_session, monkeypatch):
    _grant(monkeypatch, "customer:export", "customer:view:own")
    base_time = datetime(2026, 9, 1, 9, 0, 0)
    for index in range(76):
        _seed_customer(
            db_session,
            account_name=f"客户{index:02d}",
            owner_id="1",
            public_id=f"cus_{index:02d}",
            created_time=base_time + timedelta(minutes=index),
        )
    db_session.commit()

    response = client.post("/v1/customers/export", json={
        "fields": ["account_name", "city"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 200
    rows = _workbook_rows(response)
    assert len(rows) == 77
    assert rows[0] == ("客户名称", "城市")
    # Default business sort is created_time desc, matching the list view.
    assert rows[1][0] == "客户75"
    assert rows[76][0] == "客户00"


def test_lead_export_public_tab_uses_user_readable_values(client, db_session, monkeypatch):
    _grant(monkeypatch, "lead:export")
    db_session.add(User(id=1, email="sales@example.com", name="销售张", status=UserStatus.ACTIVE))
    _seed_lead(
        db_session,
        lead_name="公海线索",
        owner_id=None,
        status=LeadStatus.FOLLOWING,
        public_id="lead_pub_01",
    )
    db_session.commit()

    response = client.post("/v1/leads/export", json={
        "fields": ["public_id", "lead_name", "status", "city", "contact_name", "contact_phone"],
        "tab": "public",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 200
    rows = _workbook_rows(response)
    assert rows[0] == ("业务 ID", "线索名称", "状态", "城市", "联系人", "联系电话")
    assert rows[1] == ("lead_pub_01", "公海线索", "跟进中", "上海", "王五", "13800138000")


def test_customer_and_lead_export_reject_unsafe_fields(client, monkeypatch):
    _grant(monkeypatch, "customer:export", "lead:export")

    response = client.post("/v1/customers/export", json={
        "fields": ["id"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })
    assert response.status_code == 422

    response = client.post("/v1/customers/export", json={
        "fields": ["missing"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })
    assert response.status_code == 400

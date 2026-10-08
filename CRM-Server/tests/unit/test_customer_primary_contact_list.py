"""Customer list primary-contact projection and query tests."""

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.api.customers import _build_customer_list_responses, _customer_export_row
from app.core.database import Base
from app.core.list_export.catalogs import LIST_EXPORT_CATALOGS
from app.core.list_query.catalogs.customers import CUSTOMERS_LIST_QUERY_CATALOG
from app.core.list_query.engine import apply_filters, apply_sorts
from app.models.customer import Contact, Customer, CustomerMember, CustomerProduct, CustomerStatus
from app.models.deal_journey import CustomerDealJourney
from app.models.product import Product
from app.models.user import User
from app.schemas.customer import CustomerListResponse


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


@pytest.fixture
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'customer-primary-contact.db'}")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    tables = [User.__table__, Product.__table__, Customer.__table__, CustomerProduct.__table__, CustomerMember.__table__, Contact.__table__, CustomerDealJourney.__table__]
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

    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _customer(customer_id: int, name: str) -> Customer:
    now = datetime(2026, 9, 1, 9, 0, 0)
    return Customer(
        id=customer_id,
        team_id=1,
        public_id=f"cus_{customer_id}",
        account_name=name,
        city="上海",
        status=CustomerStatus.FOLLOWING.value,
        creator_id="1",
        created_time=now,
        last_modified_time=now,
        version=1,
    )


def _contact(contact_id: int, customer_id: int, name: str, mobile: str, *, is_primary: int) -> Contact:
    return Contact(
        id=contact_id,
        team_id=1,
        customer_id=customer_id,
        name=name,
        mobile=mobile,
        is_primary=is_primary,
        is_decision_maker=0,
        created_time=datetime(2026, 9, 1, 10, contact_id, 0),
    )


def _seed(db) -> None:
    db.add_all([
        _customer(1, "有主联系人"),
        _customer(2, "只有普通联系人"),
        _customer(3, "没有联系人"),
        _contact(11, 1, "王总", "13800000001", is_primary=1),
        _contact(12, 1, "李助理", "13800000002", is_primary=0),
        _contact(21, 2, "赵经理", "13900000001", is_primary=0),
    ])
    db.commit()


def test_customer_list_projects_only_primary_contact(db):
    _seed(db)
    customers = db.query(Customer).order_by(Customer.id.asc()).all()

    responses = _build_customer_list_responses(db, customers, 1)
    by_name = {item.account_name: item for item in responses}

    assert by_name["有主联系人"].primary_contact_name == "王总"
    assert by_name["有主联系人"].primary_contact_mobile == "13800000001"
    assert by_name["只有普通联系人"].primary_contact_name is None
    assert by_name["只有普通联系人"].primary_contact_mobile is None
    assert by_name["没有联系人"].primary_contact_name is None
    assert by_name["没有联系人"].primary_contact_mobile is None


def test_public_customer_response_projects_primary_contact(db):
    _seed(db)
    customers = db.query(Customer).order_by(Customer.id.asc()).all()

    items = _build_customer_list_responses(db, customers, 1)
    by_name = {item.account_name: item for item in items}

    assert by_name["有主联系人"].primary_contact_name == "王总"
    assert by_name["有主联系人"].primary_contact_mobile == "13800000001"
    assert by_name["只有普通联系人"].primary_contact_name is None
    assert by_name["没有联系人"].primary_contact_mobile is None


def test_customer_export_uses_primary_contact_columns(db):
    _seed(db)
    customer = db.query(Customer).filter(Customer.id == 1).one()
    item = _build_customer_list_responses(db, [customer], 1)[0]

    row = _customer_export_row(item)

    assert row["primary_contact_name"] == "王总"
    assert row["primary_contact_mobile"] == "13800000001"
    catalog = LIST_EXPORT_CATALOGS["customers"]
    labels = {field.key: field.label for field in catalog.fields}
    assert labels["primary_contact_name"] == "联系人"
    assert labels["primary_contact_mobile"] == "联系电话"


def test_customer_query_filters_and_sorts_primary_contact_only(db):
    _seed(db)
    name_field = CUSTOMERS_LIST_QUERY_CATALOG.require("primary_contact_name")
    mobile_field = CUSTOMERS_LIST_QUERY_CATALOG.require("primary_contact_mobile")
    assert name_field.type == "text"
    assert mobile_field.type == "text"
    assert name_field.supports_filtering() and name_field.supports_sorting()
    assert mobile_field.supports_filtering() and mobile_field.supports_sorting()

    query = db.query(Customer).filter(Customer.team_id == 1)
    matched = apply_filters(
        query,
        CUSTOMERS_LIST_QUERY_CATALOG,
        [{"field": "primary_contact_name", "op": "contains", "value": "王"}],
    ).all()
    assert [customer.account_name for customer in matched] == ["有主联系人"]

    ignored = apply_filters(
        query,
        CUSTOMERS_LIST_QUERY_CATALOG,
        [{"field": "primary_contact_mobile", "op": "eq", "value": "13900000001"}],
    ).all()
    assert ignored == []

    ordered = apply_sorts(
        query,
        CUSTOMERS_LIST_QUERY_CATALOG,
        [{"field": "primary_contact_name", "dir": "asc"}],
    ).all()
    assert [customer.account_name for customer in ordered] == ["只有普通联系人", "没有联系人", "有主联系人"]


def test_list_schema_keeps_primary_contact_optional():
    payload = {
        "id": "cus_1",
        "public_id": "cus_1",
        "account_name": "没有联系人",
        "city": "上海",
        "status": 0,
        "creator_id": "1",
        "created_time": datetime(2026, 9, 1, 9, 0, 0),
        "last_modified_time": datetime(2026, 9, 1, 9, 0, 0),
        "version": 1,
    }

    item = CustomerListResponse(**payload)

    assert item.primary_contact_name is None
    assert item.primary_contact_mobile is None

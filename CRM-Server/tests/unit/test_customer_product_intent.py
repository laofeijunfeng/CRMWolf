from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import BigInteger, create_engine, event, text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud.customer import customer_crud
from app.crud.lead import lead_crud
from app.crud.opportunity import opportunity_crud
from app.crud.product import product_crud
from app.crud.product_intent import (
    EMPTY_CATALOG_MESSAGE,
    ProductNotFoundError,
    product_intent_payload,
)
from app.models.acquisition_source import AcquisitionSource
from app.models.customer import Contact, Customer, CustomerProduct
from app.models.lead import Lead, LeadFollowUp, LeadProduct
from app.models.operation_log import OperationLog
from app.models.opportunity import Opportunity, OpportunityProductModule
from app.models.product import Product, ProductModule
from app.schemas.customer import ConvertLeadToCustomer, CustomerCreate, CustomerUpdate
from app.schemas.lead import LeadConvertRequest, LeadCreate
from app.schemas.product import ProductCreate


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


@pytest.fixture
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'customer-product-intent.db'}")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS crm_customer_deal_journeys (id INTEGER PRIMARY KEY)"))

    tables = [
        AcquisitionSource.__table__,
        Product.__table__,
        ProductModule.__table__,
        Lead.__table__,
        LeadProduct.__table__,
        LeadFollowUp.__table__,
        Customer.__table__,
        CustomerProduct.__table__,
        Contact.__table__,
        Opportunity.__table__,
        OpportunityProductModule.__table__,
        OperationLog.__table__,
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
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        session.add(
            AcquisitionSource(
                team_id=1,
                code="ONLINE_REGISTER",
                name="线上注册",
                is_system=1,
                is_active=1,
                sort_order=10,
                created_by="u1",
            )
        )
        session.commit()
        yield session
    finally:
        session.close()


def _customer_in(*, product_public_id: str) -> CustomerCreate:
    return CustomerCreate(
        account_name="客户A",
        city="上海",
        product_public_id=product_public_id,
    )


def _lead_in(*, product_public_id: str) -> LeadCreate:
    return LeadCreate(
        lead_name="线索A",
        city="上海",
        contact_name="王",
        contact_phone="13800138000",
        source="线上注册",
        product_public_id=product_public_id,
    )


def _lead_row(db, *, team_id: int) -> Lead:
    source = (
        db.query(AcquisitionSource)
        .filter(AcquisitionSource.team_id == team_id)
        .first()
    )
    lead = Lead(
        id=1,
        team_id=team_id,
        lead_name="历史线索",
        source=source.name,
        source_id=source.id,
        city="上海",
        contact_name="王",
        contact_phone="13800138000",
        creator_id="u1",
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def _opportunity(db, *, customer_id: int, team_id: int = 1) -> Opportunity:
    opportunity = Opportunity(
        team_id=team_id,
        opportunity_number="OPP202601010001",
        opportunity_name="测试商机",
        customer_id=customer_id,
        total_amount=10000,
        user_count=10,
        unit_price=200,
        license_type="SUBSCRIPTION",
        subscription_years=1,
        purchase_type="NEW",
        expected_closing_date=date(2026, 8, 30),
        owner_id="u1",
        creator_id="u1",
    )
    db.add(opportunity)
    db.flush()
    return opportunity


def test_create_customer_requires_product():
    with pytest.raises(ValidationError, match="缺少产品"):
        CustomerCreate(account_name="客户A", city="上海")


def test_create_customer_writes_single_product_link(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    customer = customer_crud.create(db, _customer_in(product_public_id=crm.public_id), "u1", 1)
    links = db.query(CustomerProduct).filter(CustomerProduct.customer_id == customer.id).all()
    assert [link.product_id for link in links] == [crm.id]


def test_create_customer_rejects_cross_team_product(db):
    product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    other = product_crud.create(db, 2, ProductCreate(name="OA"), "u1")
    with pytest.raises(ProductNotFoundError, match="产品不存在"):
        customer_crud.create(db, _customer_in(product_public_id=other.public_id), "u1", 1)


def test_create_customer_rejects_inactive_product(db):
    product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    inactive = product_crud.create(db, 1, ProductCreate(name="停用"), "u1")
    inactive.is_active = False
    db.commit()
    with pytest.raises(ValueError, match="请选择启用中的产品"):
        customer_crud.create(db, _customer_in(product_public_id=inactive.public_id), "u1", 1)


def test_create_customer_empty_catalog_uses_admin_copy(db):
    with pytest.raises(ValueError, match="还没有可用产品"):
        customer_crud.create(db, _customer_in(product_public_id="prd_junk"), "u1", 1)


def test_update_customer_replaces_intent_and_does_not_touch_opportunity(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    customer = customer_crud.create(db, _customer_in(product_public_id=crm.public_id), "u1", 1)
    opportunity = _opportunity(db, customer_id=customer.id, team_id=1)
    opportunity_crud.assign_product(
        db,
        opportunity,
        team_id=1,
        product_public_id=crm.public_id,
        module_public_ids=[crm.modules[0].public_id],
    )
    customer_crud.update(db, customer, CustomerUpdate(product_public_id=oa.public_id))
    db.refresh(opportunity)
    assert [link.product_id for link in customer.product_links] == [oa.id]
    assert opportunity.product_id == crm.id
    assert [module.public_id for module in opportunity.selected_modules] == [crm.modules[0].public_id]


def test_update_customer_without_product_keeps_existing_link(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    customer = customer_crud.create(db, _customer_in(product_public_id=crm.public_id), "u1", 1)
    customer_crud.update(db, customer, CustomerUpdate(city="杭州"))
    links = db.query(CustomerProduct).filter(CustomerProduct.customer_id == customer.id).all()
    assert [link.product_id for link in links] == [crm.id]


def test_convert_copies_lead_product(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    lead = lead_crud.create(db, _lead_in(product_public_id=crm.public_id), "u1", 1)
    customer, _contact = customer_crud.convert_from_lead(
        db,
        lead_id=lead.id,
        account_name=lead.lead_name,
        address=None,
        creator_id="u1",
        team_id=1,
    )
    assert [link.product_id for link in customer.product_links] == [crm.id]


def test_convert_request_product_overrides_lead_product(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    lead = lead_crud.create(db, _lead_in(product_public_id=crm.public_id), "u1", 1)
    customer, _contact = customer_crud.convert_from_lead(
        db,
        lead_id=lead.id,
        account_name=lead.lead_name,
        address=None,
        creator_id="u1",
        team_id=1,
        product_public_id=oa.public_id,
    )
    assert [link.product_id for link in customer.product_links] == [oa.id]
    assert [link.product_id for link in lead.product_links] == [crm.id]


def test_convert_historical_lead_without_product_requires_request_id(db):
    lead = _lead_row(db, team_id=1)
    with pytest.raises(ValueError, match="请选择产品"):
        customer_crud.convert_from_lead(
            db,
            lead_id=lead.id,
            account_name=lead.lead_name,
            address=None,
            creator_id="u1",
            team_id=1,
        )


def test_customers_catalog_exposes_product_name():
    from app.core.list_query.catalogs.customers import CUSTOMERS_LIST_QUERY_CATALOG

    field = CUSTOMERS_LIST_QUERY_CATALOG.require("product_name")
    assert field.type == "text"
    assert field.supports_sorting()


def test_customers_catalog_product_name_uses_fresh_subquery():
    from app.core.list_query.catalogs.customers import (
        CUSTOMERS_LIST_QUERY_CATALOG,
        _customer_product_name_expression,
    )

    field = CUSTOMERS_LIST_QUERY_CATALOG.require("product_name")
    assert field.expression is not _customer_product_name_expression()


def test_customer_response_includes_product_public_id(db):
    from app.api.customers import _customer_response

    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    customer = customer_crud.create(db, _customer_in(product_public_id=crm.public_id), "u1", 1)
    response = _customer_response(db, customer)
    assert response.product_public_id == crm.public_id
    assert response.product_name == "CRM"
    assert [(item.public_id, item.name) for item in response.products] == [(crm.public_id, "CRM")]


def test_convert_and_lead_convert_schemas_accept_optional_product():
    convert = ConvertLeadToCustomer(lead_id="lead_1", product_public_id="prd_oa")
    assert convert.product_public_id == "prd_oa"
    convert_blank = ConvertLeadToCustomer(lead_id="lead_1")
    assert convert_blank.product_public_id is None

    request = LeadConvertRequest(
        customer_name="客户A",
        customer_contact_name="王",
        customer_contact_phone="13800138000",
        product_public_id="prd_oa",
    )
    assert request.product_public_id == "prd_oa"


def test_historical_customer_without_product_reads_empty_payload(db):
    customer = Customer(
        id=1,
        team_id=1,
        account_name="历史客户",
        city="上海",
        creator_id="u1",
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    assert product_intent_payload(customer.product_links) == {
        "product_public_id": None,
        "product_name": None,
        "products": [],
    }

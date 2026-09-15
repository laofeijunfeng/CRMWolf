from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import status
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.api.products import _domain_error
from app.core.database import Base
from app.crud.product import product_crud
from app.crud.product_intent import (
    ProductNotFoundError,
    PRODUCT_IN_USE_MESSAGE,
    base_module_public_id,
    first_active_product,
    product_intent_payload,
    replace_product_links,
    resolve_writable_product,
)
from app.models.customer import Customer, CustomerProduct
from app.models.lead import Lead, LeadProduct
from app.models.opportunity import Opportunity
from app.models.product import Product, ProductModule, ProductModuleRole
from app.schemas.product import ProductCreate, ProductIntentRef


@pytest.fixture
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'product-intent.db'}")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS crm_customer_deal_journeys (id INTEGER PRIMARY KEY)"))
    tables = [
        Product.__table__,
        ProductModule.__table__,
        Lead.__table__,
        LeadProduct.__table__,
        Customer.__table__,
        CustomerProduct.__table__,
        Opportunity.__table__,
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
        yield session
    finally:
        session.close()


def _lead(db, *, team_id: int = 1, lead_id: int = 1) -> Lead:
    lead = Lead(
        id=lead_id,
        team_id=team_id,
        lead_name="线索A",
        source="线上注册",
        city="上海",
        contact_name="王",
        contact_phone="13800138000",
        creator_id="u1",
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def _customer(db, *, team_id: int = 1, customer_id: int = 1) -> Customer:
    customer = Customer(
        id=customer_id,
        team_id=team_id,
        account_name="客户A",
        city="上海",
        creator_id="u1",
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def _opportunity(db, *, team_id: int, customer_id: int, product_id: int, opportunity_id: int = 1) -> Opportunity:
    opportunity = Opportunity(
        id=opportunity_id,
        team_id=team_id,
        opportunity_number="OPP202601010001",
        opportunity_name="测试商机",
        customer_id=customer_id,
        product_id=product_id,
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
    db.commit()
    db.refresh(opportunity)
    return opportunity


def test_replace_product_links_replaces_instead_of_appending(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    lead = _lead(db, team_id=1)
    replace_product_links(db, team_id=1, link_cls=LeadProduct, owner_id=lead.id, owner_fk="lead_id", product=crm)
    replace_product_links(db, team_id=1, link_cls=LeadProduct, owner_id=lead.id, owner_fk="lead_id", product=oa)
    links = db.query(LeadProduct).filter(LeadProduct.lead_id == lead.id).all()
    assert [link.product_id for link in links] == [oa.id]


def test_replace_product_links_uses_product_team_not_caller_guess(db):
    product = product_crud.create(db, 2, ProductCreate(name="CRM"), "u1")
    lead = _lead(db, team_id=2)
    replace_product_links(
        db,
        team_id=1,
        link_cls=LeadProduct,
        owner_id=lead.id,
        owner_fk="lead_id",
        product=product,
    )
    link = db.query(LeadProduct).filter(LeadProduct.lead_id == lead.id).one()
    assert link.team_id == product.team_id


def test_resolve_writable_product_rejects_cross_team_as_not_found(db):
    product = product_crud.create(db, 2, ProductCreate(name="CRM"), "u1")
    with pytest.raises(ProductNotFoundError, match="产品不存在"):
        resolve_writable_product(db, team_id=1, product_public_id=product.public_id)
    assert issubclass(ProductNotFoundError, ValueError)


def test_resolve_writable_product_rejects_inactive(db):
    product = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    product.is_active = False
    db.commit()
    with pytest.raises(ValueError, match="请选择启用中的产品"):
        resolve_writable_product(db, team_id=1, product_public_id=product.public_id)


def test_resolve_writable_product_empty_catalog_message(db):
    with pytest.raises(ValueError, match="还没有可用产品"):
        resolve_writable_product(db, team_id=1, product_public_id=None)


def test_resolve_writable_product_missing_product_when_catalog_exists(db):
    product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    with pytest.raises(ValueError, match="请选择产品"):
        resolve_writable_product(db, team_id=1, product_public_id=None)


def test_product_intent_payload_empty_and_single(db):
    assert product_intent_payload([]) == {
        "product_public_id": None,
        "product_name": None,
        "products": [],
    }
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    payload = product_intent_payload([SimpleNamespace(product=crm)])
    assert payload["product_public_id"] == crm.public_id
    assert payload["product_name"] == "CRM"
    assert payload["products"] == [{"public_id": crm.public_id, "name": "CRM"}]


def test_product_intent_payload_takes_lowest_product_id(db):
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    payload = product_intent_payload(
        [
            SimpleNamespace(product_id=oa.id, product=oa),
            SimpleNamespace(product_id=crm.id, product=crm),
        ]
    )
    first = crm if crm.id < oa.id else oa
    assert payload["product_public_id"] == first.public_id
    assert payload["products"] == [{"public_id": first.public_id, "name": first.name}]


def test_delete_product_referenced_by_lead_is_rejected(db):
    product = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    lead = _lead(db, team_id=1)
    replace_product_links(db, team_id=1, link_cls=LeadProduct, owner_id=lead.id, owner_fk="lead_id", product=product)
    with pytest.raises(ValueError, match="引用"):
        product_crud.delete(db, product)


def test_delete_product_referenced_by_customer_is_rejected(db):
    product = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    customer = _customer(db, team_id=1)
    replace_product_links(
        db,
        team_id=1,
        link_cls=CustomerProduct,
        owner_id=customer.id,
        owner_fk="customer_id",
        product=product,
    )
    with pytest.raises(ValueError, match="引用"):
        product_crud.delete(db, product)


def test_delete_product_referenced_by_opportunity_is_rejected(db):
    product = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    customer = _customer(db, team_id=1)
    _opportunity(db, team_id=1, customer_id=customer.id, product_id=product.id)
    with pytest.raises(ValueError, match="引用"):
        product_crud.delete(db, product)


def test_first_active_product_returns_lowest_id(db):
    assert first_active_product(db, 1) is None
    first = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    assert first_active_product(db, 1).id == first.id
    first.is_active = False
    db.commit()
    remaining = first_active_product(db, 1)
    assert remaining is not None
    assert remaining.id != first.id


def test_base_module_public_id_prefers_active_base(db):
    product = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    base = next(module for module in product.modules if module.module_role == ProductModuleRole.BASE.value)
    assert base_module_public_id(product) == base.public_id
    base.is_active = False
    addon = ProductModule(
        team_id=product.team_id,
        product_id=product.id,
        code="ADDON",
        name="增强",
        module_role=ProductModuleRole.ADD_ON.value,
        is_active=True,
        sort_order=1,
        created_by="u1",
    )
    db.add(addon)
    db.commit()
    db.refresh(product)
    assert base_module_public_id(product) == addon.public_id


def test_product_intent_ref_schema_forbids_extra_fields():
    ref = ProductIntentRef(public_id="prd_1", name="CRM")
    assert ref.public_id == "prd_1"
    with pytest.raises(ValueError):
        ProductIntentRef(public_id="prd_1", name="CRM", extra="nope")


def test_domain_error_maps_in_use_and_duplicate_code_to_conflict():
    in_use = _domain_error(ValueError(PRODUCT_IN_USE_MESSAGE))
    assert in_use.status_code == status.HTTP_409_CONFLICT
    duplicate = _domain_error(ValueError("产品编码已存在"))
    assert duplicate.status_code == status.HTTP_409_CONFLICT
    other = _domain_error(ValueError("请选择产品"))
    assert other.status_code == status.HTTP_400_BAD_REQUEST

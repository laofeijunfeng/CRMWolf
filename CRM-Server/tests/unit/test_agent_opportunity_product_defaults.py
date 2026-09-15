"""Opportunity create defaults from customer intent product."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud.product import product_crud
from app.models.opportunity import Opportunity, OpportunityProductModule
from app.models.product import Product, ProductModule
from app.schemas.product import ProductCreate
from app.services.agent.business_rules import (
    customer_opportunity_product_defaults,
    opportunity_field_defaults,
    opportunity_next_task_from_suggestions,
)


@pytest.fixture
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'opportunity-product-defaults.db'}")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=OFF")

    Base.metadata.create_all(
        engine,
        tables=[
            Product.__table__,
            ProductModule.__table__,
            Opportunity.__table__,
            OpportunityProductModule.__table__,
        ],
    )
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


def test_opportunity_field_defaults_use_customer_product_and_base():
    customer = {"id": "cus_1", "product_public_id": "prd_crm", "products": [{"public_id": "prd_crm", "name": "CRM"}]}
    defaults = opportunity_field_defaults(customer)
    assert defaults["product_public_id"] == "prd_crm"


def test_opportunity_field_defaults_keep_procurement_and_existing_module_ids():
    customer = {
        "id": "cus_1",
        "product_public_id": "prd_crm",
        "product_module_public_ids": ["prm_pro"],
        "default_procurement_method_id": 8,
    }
    defaults = opportunity_field_defaults(customer)
    assert defaults["product_public_id"] == "prd_crm"
    assert defaults["product_module_public_ids"] == ["prm_pro"]
    assert defaults["procurement_method_id"] == 8


def test_opportunity_field_defaults_without_product_keep_procurement_only():
    defaults = opportunity_field_defaults({"id": "cus_1", "default_procurement_method_id": 3})
    assert defaults == {"procurement_method_id": 3}


def test_customer_opportunity_product_defaults_use_customer_product_and_base(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    defaults = customer_opportunity_product_defaults(
        db,
        1,
        {"product_public_id": oa.public_id},
    )
    assert defaults["product_public_id"] == oa.public_id
    assert defaults["product_module_public_ids"] == [oa.modules[0].public_id]
    assert defaults["product_public_id"] != crm.public_id


def test_customer_opportunity_product_defaults_fall_back_when_intent_inactive(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    oa.is_active = False
    db.commit()
    defaults = customer_opportunity_product_defaults(
        db,
        1,
        {"product_public_id": oa.public_id},
    )
    assert defaults["product_public_id"] == crm.public_id
    assert defaults["product_module_public_ids"] == [crm.modules[0].public_id]


def test_customer_opportunity_product_defaults_fall_back_when_intent_missing(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    defaults = customer_opportunity_product_defaults(
        db,
        1,
        {"product_public_id": "prd_gone"},
    )
    assert defaults["product_public_id"] == crm.public_id
    assert defaults["product_module_public_ids"] == [crm.modules[0].public_id]


def test_customer_opportunity_product_defaults_empty_catalog_returns_empty(db):
    assert customer_opportunity_product_defaults(db, 1, {"product_public_id": "prd_crm"}) == {}
    assert customer_opportunity_product_defaults(db, 1, {}) == {}


def test_opportunity_field_defaults_merge_db_helper_when_team_available(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    defaults = opportunity_field_defaults(
        {"id": "cus_1", "default_procurement_method_id": 3},
        db=db,
        team_id=1,
    )
    assert defaults["product_public_id"] == crm.public_id
    assert defaults["product_module_public_ids"] == [crm.modules[0].public_id]
    assert defaults["procurement_method_id"] == 3


def test_opportunity_field_defaults_keep_customer_modules_when_db_fills_base(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    defaults = opportunity_field_defaults(
        {
            "id": "cus_1",
            "product_public_id": crm.public_id,
            "product_module_public_ids": ["prm_keep"],
        },
        db=db,
        team_id=1,
    )
    assert defaults["product_public_id"] == crm.public_id
    assert defaults["product_module_public_ids"] == ["prm_keep"]


def test_opportunity_next_task_copies_customer_product_into_payload():
    suggestion = SimpleNamespace(action="CREATE_OPPORTUNITY", confidence=0.9, title="创建商机")
    next_task = opportunity_next_task_from_suggestions(
        [suggestion],
        {
            "opportunity": {
                "total_amount": 100000,
                "user_count": 20,
                "license_type": "PERPETUAL",
                "purchase_type": "NEW",
                "expected_closing_date": "2026-09-01",
            }
        },
        {
            "id": "cus_1",
            "product_public_id": "prd_crm",
            "product_module_public_ids": ["prm_base"],
        },
    )
    assert next_task is not None
    opportunity = next_task["payload"]["opportunity"]
    assert opportunity["product_public_id"] == "prd_crm"
    assert opportunity["product_module_public_ids"] == ["prm_base"]
    assert next_task["payload"]["field_defaults"]["product_public_id"] == "prd_crm"


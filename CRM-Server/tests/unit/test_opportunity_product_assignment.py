"""Opportunity product assignment contract tests."""
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud.opportunity import opportunity_crud
from app.crud.product import product_crud
from app.models.opportunity import Opportunity, OpportunityProductModule
from app.models.product import Product, ProductModule
from app.schemas.product import ProductCreate, ProductModuleCreate


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


@pytest.fixture
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'opportunity-products.db'}")

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


def _opportunity(db, *, team_id: int = 1) -> Opportunity:
    opportunity = Opportunity(
        team_id=team_id,
        opportunity_number="OPP202601010001",
        opportunity_name="测试商机",
        customer_id=1,
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


def test_assign_product_binds_selected_modules_and_rejects_foreign_modules(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    addon = product_crud.create_module(db, crm, ProductModuleCreate(name="专业版"), "u1")
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    oa_base = oa.modules[0]
    opportunity = _opportunity(db)

    opportunity_crud.assign_product(
        db,
        opportunity,
        team_id=1,
        product_public_id=crm.public_id,
        module_public_ids=[addon.public_id],
    )

    assert opportunity.product_id == crm.id
    assert [module.public_id for module in opportunity.selected_modules] == [addon.public_id]

    with pytest.raises(ValueError, match="不属于所选产品"):
        opportunity_crud.assign_product(
            db,
            opportunity,
            team_id=1,
            product_public_id=crm.public_id,
            module_public_ids=[oa_base.public_id],
        )


def test_assign_product_replaces_previous_modules_when_product_changes(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    addon = product_crud.create_module(db, crm, ProductModuleCreate(name="专业版"), "u1")
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    opportunity = _opportunity(db)

    opportunity_crud.assign_product(
        db,
        opportunity,
        team_id=1,
        product_public_id=crm.public_id,
        module_public_ids=[addon.public_id],
    )
    opportunity_crud.assign_product(
        db,
        opportunity,
        team_id=1,
        product_public_id=oa.public_id,
        module_public_ids=[oa.modules[0].public_id],
    )

    assert opportunity.product_id == oa.id
    assert [module.public_id for module in opportunity.selected_modules] == [oa.modules[0].public_id]


def test_assign_product_blank_id_with_empty_catalog_uses_admin_copy(db):
    opportunity = _opportunity(db)
    with pytest.raises(ValueError, match="还没有可用产品"):
        opportunity_crud.assign_product(db, opportunity, team_id=1, product_public_id="", module_public_ids=[])


def test_assign_product_blank_id_with_catalog_still_requires_product(db):
    product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    opportunity = _opportunity(db)
    with pytest.raises(ValueError, match="请选择产品"):
        opportunity_crud.assign_product(db, opportunity, team_id=1, product_public_id="", module_public_ids=[])


def test_assign_product_missing_product_with_catalog_is_not_found(db):
    product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    opportunity = _opportunity(db)
    with pytest.raises(ValueError, match="产品不存在"):
        opportunity_crud.assign_product(
            db,
            opportunity,
            team_id=1,
            product_public_id="prd_missing",
            module_public_ids=["prm_x"],
        )


def test_assign_product_inactive_product_with_catalog_is_not_found(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    crm.is_active = False
    db.commit()
    opportunity = _opportunity(db)
    with pytest.raises(ValueError, match="产品不存在"):
        opportunity_crud.assign_product(
            db,
            opportunity,
            team_id=1,
            product_public_id=crm.public_id,
            module_public_ids=[crm.modules[0].public_id],
        )

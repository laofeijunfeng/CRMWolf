from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud.product import product_crud
from app.models.product import Product, ProductModule, ProductModuleRole
from app.schemas.product import ProductCreate, ProductModuleCreate, ProductModuleUpdate


@pytest.fixture
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'products.db'}")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine, tables=[Product.__table__, ProductModule.__table__])
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


def product_payload(name: str = "CRM") -> ProductCreate:
    return ProductCreate(name=name, description="desc")


def module_payload(name: str = "增强模块") -> ProductModuleCreate:
    return ProductModuleCreate(name=name, description="module")


def test_product_rejects_second_base_module_at_database_boundary(db):
    product = product_crud.create(db, 1, product_payload(), "u1")

    db.add(
        ProductModule(
            team_id=product.team_id,
            product_id=product.id,
            code="SECOND_BASE",
            name="重复基础版",
            module_role=ProductModuleRole.BASE.value,
            base_key="BASE",
            created_by="u2",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_product_module_cannot_cross_team_product_boundary(db):
    product = product_crud.create(db, 1, product_payload(), "u1")

    db.add(
        ProductModule(
            team_id=2,
            product_id=product.id,
            code="CROSS_TEAM",
            name="越权模块",
            module_role=ProductModuleRole.ADD_ON.value,
            created_by="u2",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()

def test_create_product_creates_exactly_one_base_module(db):
    product = product_crud.create(db, team_id=1, obj_in=product_payload(), creator_id="u1")

    assert product.team_id == 1
    assert product.public_id.startswith("prd_")
    assert len(product.public_id) == 36
    assert product.code.startswith("PRD_")
    assert product.code != product.public_id
    assert len(product.modules) == 1
    base = product.modules[0]
    assert base.public_id.startswith("prm_")
    assert base.code == "BASE"
    assert base.name == "基础版"
    assert base.module_role == ProductModuleRole.BASE.value
    assert base.is_active is True


def test_create_product_generates_unique_internal_codes_per_team(db):
    first = product_crud.create(db, 1, product_payload(), "u1")
    second = product_crud.create(db, 1, product_payload(name="另一个"), "u2")
    other_team = product_crud.create(db, 2, product_payload(), "u3")

    assert first.public_id != second.public_id
    assert first.code != second.code
    assert other_team.team_id == 2
    assert other_team.public_id != first.public_id


def test_create_add_on_module_generates_internal_code(db):
    product = product_crud.create(db, 1, product_payload(), "u1")
    first = product_crud.create_module(db, product, module_payload(), "u1")
    second = product_crud.create_module(db, product, module_payload(name="重复名称"), "u2")

    assert first.public_id.startswith("prm_")
    assert first.code.startswith("PRM_")
    assert first.code != "BASE"
    assert second.code != first.code
    assert second.name == "重复名称"


def test_base_module_cannot_be_deleted_or_deactivated(db):
    product = product_crud.create(db, 1, product_payload(), "u1")
    base = product.modules[0]

    with pytest.raises(ValueError, match="基础模块不可删除"):
        product_crud.delete_module(db, base)

    with pytest.raises(ValueError, match="基础模块不可停用"):
        product_crud.update_module(db, base, ProductModuleUpdate(is_active=False), "u2")


def test_product_and_module_lookup_cannot_cross_team_boundaries(db):
    product = product_crud.create(db, 1, product_payload(), "u1")
    base = product.modules[0]

    assert product_crud.get_by_public_id(db, product.public_id, 2) is None
    assert product_crud.get_module_by_public_id(db, base.public_id, 2) is None


def test_product_delete_rejects_add_on_modules(db):
    product = product_crud.create(db, 1, product_payload(), "u1")
    product_crud.create_module(db, product, module_payload(), "u1")

    with pytest.raises(ValueError, match="包含增强模块"):
        product_crud.delete(db, product)

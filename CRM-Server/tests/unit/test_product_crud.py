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


def product_payload(code: str = "CRM", name: str = "CRM") -> ProductCreate:
    return ProductCreate(code=code, name=name, description="desc")


def module_payload(code: str = "ADDON", name: str = "增强模块") -> ProductModuleCreate:
    return ProductModuleCreate(code=code, name=name, description="module")


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
    assert len(product.modules) == 1
    base = product.modules[0]
    assert base.code == "BASE"
    assert base.name == "基础版"
    assert base.module_role == ProductModuleRole.BASE.value
    assert base.is_active is True


def test_duplicate_product_code_in_same_team_is_rejected(db):
    product_crud.create(db, 1, product_payload(), "u1")

    with pytest.raises(ValueError, match="产品编码已存在"):
        product_crud.create(db, 1, product_payload(name="另一个"), "u2")


def test_same_product_code_in_another_team_is_allowed(db):
    first = product_crud.create(db, 1, product_payload(), "u1")
    second = product_crud.create(db, 2, product_payload(), "u2")

    assert first.public_id != second.public_id
    assert second.team_id == 2


def test_duplicate_module_code_in_one_product_is_rejected(db):
    product = product_crud.create(db, 1, product_payload(), "u1")
    product_crud.create_module(db, product, module_payload(), "u1")

    with pytest.raises(ValueError, match="模块编码已存在"):
        product_crud.create_module(db, product, module_payload(name="重复"), "u2")


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

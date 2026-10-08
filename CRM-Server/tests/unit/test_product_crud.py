from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.customer import Customer
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.crud.product import product_crud
from app.models.product import Product, ProductModule, ProductModuleRole
from app.models.team import Team
from app.models.user import User
from app.schemas.product import ProductCreate, ProductModuleCreate, ProductModuleUpdate, ProductUpdate


@pytest.fixture
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'products.db'}")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine, tables=[
        User.__table__, Team.__table__, Customer.__table__, CustomerLegacySourceProgress.__table__,
        Product.__table__, ProductModule.__table__,
    ])
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    session.add(User(id=1, email="owner@example.com", name="Owner"))
    session.flush()
    session.add_all([
        Team(id=1, name="One", code="TEAM_ONE", owner_id=1),
        Team(id=2, name="Two", code="TEAM_TWO", owner_id=1),
    ])
    session.commit()
    try:
        yield session
    finally:
        session.close()

def test_product_create_requires_existing_team(db):
    with pytest.raises(ValueError, match="产品团队信息无效"):
        product_crud.create(db, 3, product_payload(), "u1")
    assert db.query(Product).count() == 0


def test_product_update_rejects_forged_team_without_modifying_real_product(db):
    product = product_crud.create(db, 1, product_payload(), "u1")
    forged = Product(id=product.id, team_id=2)

    with pytest.raises(ValueError, match="产品团队信息无效"):
        product_crud.update(db, forged, ProductUpdate(name="越权更新"), "u2")

    db.expire(product)
    assert product.name == "CRM"


def test_product_noop_update_does_not_change_audit_columns(db):
    product = product_crud.create(db, 1, product_payload(), "u1")
    original_updated_time = product.updated_time

    product_crud.update(db, product, ProductUpdate(name=product.name), "u2")

    assert product.updated_by is None
    assert product.updated_time == original_updated_time


def test_product_delete_rejects_forged_team_without_deleting_real_product(db):
    product = product_crud.create(db, 1, product_payload(), "u1")
    forged = Product(id=product.id, team_id=2)

    with pytest.raises(ValueError, match="产品团队信息无效"):
        product_crud.delete(db, forged)

    assert db.get(Product, product.id) is product


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


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_stale_module_cannot_modify_another_team_after_reassignment(db, operation):
    first = product_crud.create(db, 1, product_payload(), "u1")
    second = product_crud.create(db, 2, product_payload(), "u1")
    module = product_crud.create_module(db, first, module_payload(), "u1")
    db.commit()
    sessions = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    with sessions() as stale, sessions() as concurrent:
        loaded = stale.get(ProductModule, module.id)
        assert loaded.product.id == first.id  # Cache the old relationship before reassignment.
        reassigned = concurrent.get(ProductModule, module.id)
        reassigned.team_id = second.team_id
        reassigned.product_id = second.id
        concurrent.commit()

        with pytest.raises(ValueError, match="产品模块团队不一致"):
            if operation == "update":
                product_crud.update_module(stale, loaded, ProductModuleUpdate(name="越权修改"), "u2")
            else:
                product_crud.delete_module(stale, loaded)
        stale.rollback()

    db.expire_all()
    current = db.get(ProductModule, module.id)
    assert current.team_id == second.team_id
    assert current.product_id == second.id
    assert current.name == "增强模块"


def test_stale_module_update_reloads_current_values_before_applying_changes(db):
    product = product_crud.create(db, 1, product_payload(), "u1")
    module = product_crud.create_module(db, product, module_payload(), "u1")
    db.commit()
    sessions = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    with sessions() as stale, sessions() as concurrent:
        loaded = stale.get(ProductModule, module.id)
        assert loaded.name == "增强模块"
        fresh = concurrent.get(ProductModule, module.id)
        fresh.name = "最新名称"
        concurrent.commit()

        updated = product_crud.update_module(stale, loaded, ProductModuleUpdate(is_active=False), "u2")
        assert updated.name == "最新名称"
        assert updated.is_active is False


def test_create_module_rejects_product_deleted_after_it_was_loaded(db):
    product = product_crud.create(db, 1, product_payload(), "u1")
    product_id = product.id
    db.commit()
    sessions = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    with sessions() as stale, sessions() as concurrent:
        loaded = stale.get(Product, product.id)
        assert loaded.team_id == 1
        concurrent.query(Product).filter(Product.id == product.id).delete()
        concurrent.commit()

        with pytest.raises(ValueError, match="产品团队信息无效"):
            product_crud.create_module(stale, loaded, module_payload(), "u2")
        stale.rollback()

    db.expire_all()
    assert db.get(Product, product_id) is None
    assert db.query(ProductModule).filter(ProductModule.product_id == product_id).count() == 0


@pytest.mark.parametrize("operation", ["deactivate", "delete"])
def test_stale_module_cannot_change_module_promoted_to_base(db, operation):
    product = product_crud.create(db, 1, product_payload(), "u1")
    module = product_crud.create_module(db, product, module_payload(), "u1")
    db.commit()
    sessions = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    with sessions() as stale, sessions() as concurrent:
        loaded = stale.get(ProductModule, module.id)
        assert loaded.module_role == ProductModuleRole.ADD_ON.value
        current = concurrent.get(ProductModule, module.id)
        base = concurrent.query(ProductModule).filter_by(product_id=product.id, base_key="BASE").one()
        concurrent.delete(base)
        concurrent.flush()
        current.module_role = ProductModuleRole.BASE.value
        current.base_key = "BASE"
        concurrent.commit()

        with pytest.raises(ValueError, match="基础模块不可停用|基础模块不可删除"):
            if operation == "deactivate":
                product_crud.update_module(stale, loaded, ProductModuleUpdate(is_active=False), "u2")
            else:
                product_crud.delete_module(stale, loaded)
        stale.rollback()

    db.expire_all()
    actual = db.get(ProductModule, module.id)
    assert actual.module_role == ProductModuleRole.BASE.value
    assert actual.is_active is True

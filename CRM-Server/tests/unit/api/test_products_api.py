"""Focused product API authorization and team-isolation contract tests."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import products as products_api
from app.core import database, deps
from app.core.database import Base
from app.crud.product import product_crud
from app.models.product import Product, ProductModule
from app.schemas.product import ProductCreate


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


@pytest.fixture()
def api_env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine, tables=[Product.__table__, ProductModule.__table__])
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    current_user = SimpleNamespace(id=7, status="active", name="销售成员")
    team_state = {"id": 1}
    permissions = {"product:view", "product:create", "product:edit", "product:delete"}

    def _permission_stub(_db, _user_id, team_id=None):
        assert team_id == team_state["id"]
        return [SimpleNamespace(code=code) for code in permissions]

    monkeypatch.setattr(deps.permission_crud, "get_user_permissions", _permission_stub)
    app = FastAPI()
    app.include_router(products_api.router)

    def _get_db():
        yield db

    def _current_team():
        return team_state["id"]

    app.dependency_overrides[database.get_db] = _get_db
    app.dependency_overrides[deps.get_db] = _get_db
    app.dependency_overrides[products_api.get_db] = _get_db
    app.dependency_overrides[deps.get_current_user_team] = _current_team
    app.dependency_overrides[products_api.get_current_user_team] = _current_team
    app.dependency_overrides[deps.get_current_active_user] = lambda: current_user
    app.dependency_overrides[products_api.get_current_active_user] = lambda: current_user

    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            db=db,
            permissions=permissions,
            team_state=team_state,
            current_user=current_user,
        )

    db.close()
    engine.dispose()


def _create_product(api_env, *, team_id: int = 1, code: str = "CRM", name: str = "CRM"):
    return product_crud.create(api_env.db, team_id, ProductCreate(code=code, name=name), "7")


def test_view_permission_lists_and_gets_product_detail(api_env):
    product = _create_product(api_env)

    listed = api_env.client.get("/v1/products/")
    detail = api_env.client.get(f"/v1/products/{product.public_id}")

    assert listed.status_code == 200
    assert listed.json()[0]["public_id"] == product.public_id
    assert listed.json()[0]["modules"][0]["module_role"] == "BASE"
    assert detail.status_code == 200
    assert detail.json()["public_id"] == product.public_id


def test_missing_view_permission_returns_forbidden(api_env):
    api_env.permissions.clear()

    response = api_env.client.get("/v1/products/")

    assert response.status_code == 403


def test_create_requires_explicit_permission_even_for_team_admin_role(api_env):
    api_env.permissions.difference_update({"product:create"})

    response = api_env.client.post("/v1/products/", json={"code": "CRM", "name": "CRM"})

    assert response.status_code == 403


def test_create_returns_mandatory_base_module(api_env):
    response = api_env.client.post("/v1/products/", json={"code": "CRM", "name": "CRM"})

    assert response.status_code == 201
    assert len(response.json()["modules"]) == 1
    assert response.json()["modules"][0]["module_role"] == "BASE"
    assert response.json()["modules"][0]["code"] == "BASE"


def test_edit_updates_product_and_add_on_module(api_env):
    product = _create_product(api_env)
    module = product_crud.create_module(
        api_env.db,
        product,
        {"code": "PRO", "name": "专业版"},
        "7",
    )

    product_response = api_env.client.put(
        f"/v1/products/{product.public_id}",
        json={"name": "更新产品", "description": "新的描述"},
    )
    module_response = api_env.client.put(
        f"/v1/products/{product.public_id}/modules/{module.public_id}",
        json={"name": "更新模块", "sort_order": 2},
    )

    assert product_response.status_code == 200
    assert product_response.json()["name"] == "更新产品"
    assert module_response.status_code == 200
    assert module_response.json()["name"] == "更新模块"
    assert module_response.json()["sort_order"] == 2


def test_delete_safe_product(api_env):
    product = _create_product(api_env)

    response = api_env.client.delete(f"/v1/products/{product.public_id}")

    assert response.status_code == 204
    assert product_crud.get_by_public_id(api_env.db, product.public_id, 1) is None


def test_module_delete_requires_product_edit_permission(api_env):
    product = _create_product(api_env)
    module = product_crud.create_module(api_env.db, product, {"code": "PRO", "name": "专业版"}, "7")
    api_env.permissions.discard("product:edit")

    response = api_env.client.delete(f"/v1/products/{product.public_id}/modules/{module.public_id}")

    assert response.status_code == 403


def test_base_module_delete_and_deactivation_return_bad_request(api_env):
    product = _create_product(api_env)
    base = product.modules[0]

    delete_response = api_env.client.delete(f"/v1/products/{product.public_id}/modules/{base.public_id}")
    deactivate_response = api_env.client.put(
        f"/v1/products/{product.public_id}/modules/{base.public_id}",
        json={"is_active": False},
    )

    assert delete_response.status_code == 400
    assert deactivate_response.status_code == 400


def test_foreign_product_public_id_is_not_found_and_cannot_be_mutated(api_env):
    foreign = _create_product(api_env, team_id=2, code="FOREIGN", name="Foreign")

    detail = api_env.client.get(f"/v1/products/{foreign.public_id}")
    update = api_env.client.put(f"/v1/products/{foreign.public_id}", json={"name": "侵入"})
    delete = api_env.client.delete(f"/v1/products/{foreign.public_id}")

    assert detail.status_code == 404
    assert update.status_code == 404
    assert delete.status_code == 404


def test_foreign_module_public_id_is_not_found_under_local_product(api_env):
    local = _create_product(api_env, team_id=1, code="LOCAL", name="Local")
    foreign = _create_product(api_env, team_id=2, code="FOREIGN", name="Foreign")
    foreign_module = product_crud.create_module(
        api_env.db,
        foreign,
        {"code": "PRO", "name": "专业版"},
        "7",
    )

    response = api_env.client.put(
        f"/v1/products/{local.public_id}/modules/{foreign_module.public_id}",
        json={"name": "侵入"},
    )

    assert response.status_code == 404

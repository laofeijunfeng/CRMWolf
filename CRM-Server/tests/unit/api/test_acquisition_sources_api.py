"""Acquisition source API seams from TRD 9.1 API-01 to API-06."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import acquisition_sources as acquisition_sources_api
from app.api import teams as teams_api
from app.core import database, deps
from app.core.database import Base
from app.models.acquisition_source import AcquisitionSource
from app.models.customer import Customer
from app.models.lead import Lead
from app.models.role import Role
from app.models.team import Team, UserTeam
from app.models.user import User, UserStatus
from app.models.user_role import UserRole


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


EXPECTED_NAMES = (
    "线上注册",
    "市场活动",
    "客户推荐",
    "电话营销",
    "网站咨询",
    "展会",
    "其他",
)


@pytest.fixture()
def api_env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        User.__table__,
        Team.__table__,
        UserTeam.__table__,
        Role.__table__,
        UserRole.__table__,
        AcquisitionSource.__table__,
        Lead.__table__,
        Customer.__table__,
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
    db = Session()
    current_user = User(id=1, email="admin@example.com", name="管理员", status=UserStatus.ACTIVE)
    db.add(current_user)
    db.add(Role(id=1, name="团队管理员", code="TEAM_ADMIN"))
    db.commit()

    permissions = {
        "acquisition_source:view",
        "acquisition_source:create",
        "acquisition_source:update",
    }

    def _permission_stub(_db, user_id, team_id=None):
        return [SimpleNamespace(code=code) for code in permissions]

    monkeypatch.setattr("app.core.deps.permission_crud.get_user_permissions", _permission_stub)

    app = FastAPI()
    app.include_router(teams_api.router)
    app.include_router(acquisition_sources_api.router)

    team_state = {"id": None}

    def _get_db():
        yield db

    def _current_team():
        if team_state["id"] is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="未选择团队")
        return team_state["id"]

    for module in (database, deps, teams_api, acquisition_sources_api):
        if hasattr(module, "get_db"):
            app.dependency_overrides[module.get_db] = _get_db
        if hasattr(module, "get_current_user_team"):
            app.dependency_overrides[module.get_current_user_team] = _current_team
        if hasattr(module, "get_current_active_user"):
            app.dependency_overrides[module.get_current_active_user] = lambda: current_user

    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            db=db,
            current_user=current_user,
            team_state=team_state,
            permissions=permissions,
        )

    db.close()
    engine.dispose()


def _create_team(api_env, name: str = "测试团队") -> int:
    response = api_env.client.post("/v1/teams/", json={"name": name})
    assert response.status_code == 200, response.text
    team_id = response.json()["id"]
    api_env.team_state["id"] = team_id
    return team_id


def test_create_team_seeds_seven_default_options(api_env):
    _create_team(api_env)

    response = api_env.client.get("/v1/acquisition-sources/options")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["name"] for item in payload] == list(EXPECTED_NAMES)
    assert all(item["public_id"].startswith("acq_") for item in payload)
    assert all("id" not in item for item in payload)
    assert all(item["is_system"] is True and item["is_active"] is True for item in payload)


def test_deactivate_hides_from_default_options_but_keeps_inactive_filter(api_env):
    _create_team(api_env)
    options = api_env.client.get("/v1/acquisition-sources/options").json()
    exhibition = next(item for item in options if item["code"] == "EXHIBITION")

    update = api_env.client.put(
        f"/v1/acquisition-sources/{exhibition['public_id']}",
        json={"is_active": 0},
    )
    assert update.status_code == 200, update.text
    assert update.json()["is_active"] is False

    active = api_env.client.get("/v1/acquisition-sources/options").json()
    assert exhibition["public_id"] not in {item["public_id"] for item in active}

    all_items = api_env.client.get(
        "/v1/acquisition-sources/options",
        params={"include_inactive": True},
    ).json()
    assert exhibition["public_id"] in {item["public_id"] for item in all_items}


def test_delete_is_not_allowed_and_row_remains(api_env):
    _create_team(api_env)
    options = api_env.client.get("/v1/acquisition-sources/options").json()
    target = options[0]

    response = api_env.client.delete(f"/v1/acquisition-sources/{target['public_id']}")
    assert response.status_code == 405

    remaining = (
        api_env.db.query(AcquisitionSource)
        .filter(AcquisitionSource.public_id == target["public_id"])
        .one()
    )
    assert remaining.public_id == target["public_id"]


def test_custom_item_can_be_renamed_then_deactivated(api_env):
    _create_team(api_env)
    created = api_env.client.post("/v1/acquisition-sources/", json={"name": "误建项", "sort_order": 80})
    assert created.status_code == 201, created.text
    public_id = created.json()["public_id"]
    assert created.json()["code"].startswith("CUSTOM_")
    assert created.json()["is_system"] is False

    renamed = api_env.client.put(
        f"/v1/acquisition-sources/{public_id}",
        json={"name": "废弃误建项", "is_active": 0},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "废弃误建项"
    assert renamed.json()["is_active"] is False

    active = api_env.client.get("/v1/acquisition-sources/options").json()
    assert public_id not in {item["public_id"] for item in active}
    row = (
        api_env.db.query(AcquisitionSource)
        .filter(AcquisitionSource.public_id == public_id)
        .one()
    )
    assert row.is_active == 0


def test_forbidden_name_lead_conversion_is_rejected(api_env):
    _create_team(api_env)
    response = api_env.client.post("/v1/acquisition-sources/", json={"name": "线索转化"})
    assert response.status_code == 400
    assert response.json()["detail"] == "不能使用该名称"


def test_foreign_team_public_id_is_not_found(api_env):
    first_team_id = _create_team(api_env, "团队甲")
    first_options = api_env.client.get("/v1/acquisition-sources/options").json()
    foreign_id = first_options[0]["public_id"]

    second_team_id = _create_team(api_env, "团队乙")
    assert second_team_id != first_team_id

    response = api_env.client.put(
        f"/v1/acquisition-sources/{foreign_id}",
        json={"name": "偷改"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "获客来源不存在"

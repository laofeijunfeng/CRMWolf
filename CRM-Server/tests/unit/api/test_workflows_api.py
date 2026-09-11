"""Workflows API seams: CRUD, team isolation, optimistic locking, status transitions, permissions."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import workflows as workflows_api
from app.core import database, deps
from app.core.database import Base
from app.models.role import Role
from app.models.team import Team, UserTeam
from app.models.user import User, UserStatus
from app.models.user_role import UserRole
from app.models.workflow import Workflow


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


VALID_DSL = {
    "schema_version": 1,
    "nodes": [
        {
            "id": "n1",
            "type": "trigger.opportunity_stage_changed",
            "position": {"x": 0, "y": 0},
            "config": {"to_stage": "QUOTE"},
        },
        {
            "id": "n2",
            "type": "action.create_follow_up_task",
            "position": {"x": 200, "y": 0},
            "config": {"title": "跟进"},
        },
    ],
    "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
}


def _payload(name: str = "商机阶段工作流", dsl: dict | None = None) -> dict:
    return {"name": name, "description": "测试工作流", "dsl": dsl if dsl is not None else VALID_DSL}


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
        Workflow.__table__,
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
    db.add(Team(id=101, name="团队A", code="TEAM_A", owner_id=1))
    db.add(Team(id=202, name="团队B", code="TEAM_B", owner_id=1))
    db.add(UserTeam(user_id=1, team_id=101, current_team=True))
    db.add(Role(id=1, name="团队管理员", code="TEAM_ADMIN"))
    db.commit()

    permissions = {
        "automation:read",
        "automation:create",
        "automation:edit",
        "automation:publish",
    }

    def _permission_stub(_db, user_id, team_id=None):
        return [SimpleNamespace(code=code) for code in permissions]

    monkeypatch.setattr("app.core.deps.permission_crud.get_user_permissions", _permission_stub)

    app = FastAPI()
    app.include_router(workflows_api.router)

    team_state = {"id": None}

    def _get_db():
        yield db

    def _current_team():
        if team_state["id"] is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail="未选择团队")
        return team_state["id"]

    for module in (database, deps, workflows_api):
        if hasattr(module, "get_db"):
            app.dependency_overrides[module.get_db] = _get_db
        if hasattr(module, "get_current_user_team"):
            app.dependency_overrides[module.get_current_user_team] = _current_team
        if hasattr(module, "get_current_active_user"):
            app.dependency_overrides[module.get_current_active_user] = lambda: current_user
    app.dependency_overrides[deps.get_db] = _get_db
    app.dependency_overrides[deps.get_current_user_team] = _current_team
    app.dependency_overrides[deps.get_current_active_user] = lambda: current_user

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


def _use_team(api_env, team_id: int) -> None:
    api_env.team_state["id"] = team_id


def _create_workflow(api_env, name: str = "商机阶段工作流") -> dict:
    response = api_env.client.post("/v1/workflows", json=_payload(name))
    assert response.status_code == 201, response.text
    return response.json()


def test_create_workflow_returns_201_with_dsl(api_env):
    _use_team(api_env, 101)
    body = _create_workflow(api_env)
    assert body["name"] == "商机阶段工作流"
    assert body["status"] == "draft"
    assert body["node_count"] == 2
    assert body["dsl"] == VALID_DSL
    assert body["created_by"] == 1


def test_create_workflow_with_invalid_dsl_returns_422(api_env):
    _use_team(api_env, 101)
    bad_dsl = {
        "schema_version": 2,
        "nodes": [
            {"id": "n1", "type": "action.unknown", "position": {"x": 0, "y": 0}, "config": {}},
        ],
    }
    response = api_env.client.post("/v1/workflows", json=_payload(dsl=bad_dsl))
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, dict) and "errors" in detail


def test_list_workflows_only_returns_current_team(api_env):
    _use_team(api_env, 101)
    _create_workflow(api_env, "团队A工作流")
    _use_team(api_env, 202)
    _create_workflow(api_env, "团队B工作流1")
    _create_workflow(api_env, "团队B工作流2")

    _use_team(api_env, 101)
    listing = api_env.client.get("/v1/workflows")
    assert listing.status_code == 200
    items = listing.json()
    assert [item["name"] for item in items] == ["团队A工作流"]
    assert all("dsl" not in item for item in items)

    _use_team(api_env, 202)
    items = api_env.client.get("/v1/workflows").json()
    assert len(items) == 2


def test_list_workflows_supports_trailing_slash(api_env):
    _use_team(api_env, 101)
    _create_workflow(api_env)

    response = api_env.client.get("/v1/workflows/")

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1


def test_malformed_dsl_types_return_422_instead_of_unhandled_type_error(api_env):
    _use_team(api_env, 101)
    malformed_dsl = {
        **VALID_DSL,
        "nodes": [{**VALID_DSL["nodes"][0], "type": ["trigger.opportunity_stage_changed"]}],
    }

    response = api_env.client.post("/v1/workflows", json=_payload(dsl=malformed_dsl))

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["errors"]


def test_get_workflow_detail_cross_team_404(api_env):
    _use_team(api_env, 101)
    created = _create_workflow(api_env)

    _use_team(api_env, 202)
    response = api_env.client.get(f"/v1/workflows/{created['id']}")
    assert response.status_code == 404


def test_update_workflow_optimistic_lock_conflict_409(api_env):
    _use_team(api_env, 101)
    created = _create_workflow(api_env)

    stale_time = "2020-01-01T00:00:00"
    response = api_env.client.put(
        f"/v1/workflows/{created['id']}",
        json={**_payload("改名"), "expected_last_modified_time": stale_time},
    )
    assert response.status_code == 409, response.text


def test_update_workflow_with_fresh_timestamp_succeeds(api_env):
    _use_team(api_env, 101)
    created = _create_workflow(api_env)

    response = api_env.client.put(
        f"/v1/workflows/{created['id']}",
        json={**_payload("改名"), "expected_last_modified_time": created["last_modified_time"]},
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["name"] == "改名"
    assert updated["dsl"] == VALID_DSL


def test_delete_non_draft_workflow_409(api_env):
    _use_team(api_env, 101)
    created = _create_workflow(api_env)
    publish = api_env.client.put(f"/v1/workflows/{created['id']}/status", json={"status": "published"})
    assert publish.status_code == 200, publish.text

    response = api_env.client.delete(f"/v1/workflows/{created['id']}")
    assert response.status_code == 409, response.text


def test_delete_draft_workflow_204(api_env):
    _use_team(api_env, 101)
    created = _create_workflow(api_env)

    response = api_env.client.delete(f"/v1/workflows/{created['id']}")
    assert response.status_code == 204, response.text
    assert api_env.client.get(f"/v1/workflows/{created['id']}").status_code == 404


def test_status_transition_draft_to_published_200(api_env):
    _use_team(api_env, 101)
    created = _create_workflow(api_env)

    response = api_env.client.put(f"/v1/workflows/{created['id']}/status", json={"status": "published"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "published"


def test_status_transition_published_to_draft_422(api_env):
    _use_team(api_env, 101)
    created = _create_workflow(api_env)
    publish = api_env.client.put(f"/v1/workflows/{created['id']}/status", json={"status": "published"})
    assert publish.status_code == 200, publish.text

    response = api_env.client.put(f"/v1/workflows/{created['id']}/status", json={"status": "draft"})
    assert response.status_code == 422, response.text


def test_create_workflow_without_permission_403(api_env, monkeypatch):
    _use_team(api_env, 101)
    api_env.permissions.clear()

    response = api_env.client.post("/v1/workflows", json=_payload())
    assert response.status_code == 403, response.text

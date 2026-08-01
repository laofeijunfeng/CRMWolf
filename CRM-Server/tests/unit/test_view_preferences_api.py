from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import deps
from app.core.database import Base
from app.main import app
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.team import Team, UserTeam
from app.models.user import User
from app.models.user_role import UserRole
from app.models.view_preference import ViewPreference


TEST_TABLES = [
    User.__table__,
    Team.__table__,
    UserTeam.__table__,
    Role.__table__,
    Permission.__table__,
    RolePermission.__table__,
    UserRole.__table__,
    ViewPreference.__table__,
]


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=TEST_TABLES)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(User(id=1, email="user@example.com", name="普通成员", status="active"))
    db.add(User(id=2, email="admin@example.com", name="管理员", status="active"))
    db.add(Team(id=1, name="销售团队", code="TEAM001", owner_id=2))
    db.add(UserTeam(user_id=1, team_id=1, current_team=True))
    db.add(UserTeam(user_id=2, team_id=1, current_team=True))
    db.add(Role(id=1, name="团队管理员", code="TEAM_ADMIN"))
    db.add(UserRole(user_id=2, role_id=1, team_id=1))
    db.commit()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine, tables=TEST_TABLES)


@pytest.fixture
def client(db_session):
    app.dependency_overrides[deps.get_db] = lambda: db_session
    app.dependency_overrides[deps.get_current_user_team] = lambda: 1
    app.dependency_overrides[deps.get_current_active_user] = lambda: SimpleNamespace(id=1, status="active")
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()
    app.dependency_overrides.clear()


def test_saves_personal_preference_and_returns_it_as_effective(client):
    response = client.put(
        "/api/v1/view-preferences/customers.list",
        json={
            "scope": "personal",
            "config": {
                "version": 1,
                "columns": [
                    {"key": "owner", "order": 0, "visible": True},
                    {"key": "city", "order": 10, "visible": False},
                ],
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["personal"]["user_id"] == 1
    assert body["effective_scope"] == "personal"
    assert [column["key"] for column in body["effective_config"]["columns"]] == ["owner", "city"]


def test_personal_preference_overrides_team_preference(client, db_session):
    db_session.add(ViewPreference(
        team_id=1,
        user_id=0,
        view_key="customers.list",
        scope="team",
        config_json='{"version":1,"columns":[{"key":"team_only","order":0,"visible":true}],"sorts":[],"filters":[]}',
        created_by=2,
        updated_by=2,
    ))
    db_session.commit()

    client.put(
        "/api/v1/view-preferences/customers.list",
        json={
            "scope": "personal",
            "config": {"version": 1, "columns": [{"key": "personal_only", "order": 0, "visible": True}]},
        },
    )

    response = client.get("/api/v1/view-preferences/customers.list")

    assert response.status_code == 200
    assert response.json()["effective_scope"] == "personal"
    assert response.json()["effective_config"]["columns"][0]["key"] == "personal_only"


def test_rejects_team_preference_for_non_admin(client):
    response = client.put(
        "/api/v1/view-preferences/customers.list",
        json={
            "scope": "team",
            "config": {"version": 1, "columns": [{"key": "owner", "order": 0, "visible": True}]},
        },
    )

    assert response.status_code == 403


def test_team_admin_can_save_team_preference(client):
    app.dependency_overrides[deps.get_current_active_user] = lambda: SimpleNamespace(id=2, status="active")

    response = client.put(
        "/api/v1/view-preferences/customers.list",
        json={
            "scope": "team",
            "config": {"version": 1, "columns": [{"key": "owner", "order": 0, "visible": True}]},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["team"]["user_id"] == 0
    assert body["effective_scope"] == "team"
    assert body["effective_config"]["columns"][0]["key"] == "owner"


def test_deleting_personal_preference_falls_back_to_team(client, db_session):
    db_session.add(ViewPreference(
        team_id=1,
        user_id=0,
        view_key="customers.list",
        scope="team",
        config_json='{"version":1,"columns":[{"key":"team_owner","order":0,"visible":true}],"sorts":[],"filters":[]}',
        created_by=2,
        updated_by=2,
    ))
    db_session.add(ViewPreference(
        team_id=1,
        user_id=1,
        view_key="customers.list",
        scope="personal",
        config_json='{"version":1,"columns":[{"key":"personal_owner","order":0,"visible":true}],"sorts":[],"filters":[]}',
        created_by=1,
        updated_by=1,
    ))
    db_session.commit()

    response = client.delete("/api/v1/view-preferences/customers.list?scope=personal")

    assert response.status_code == 200
    body = response.json()
    assert body["personal"] is None
    assert body["team"] is not None
    assert body["effective_scope"] == "team"
    assert body["effective_config"]["columns"][0]["key"] == "team_owner"


def test_rejects_team_preference_reset_for_non_admin(client, db_session):
    db_session.add(ViewPreference(
        team_id=1,
        user_id=0,
        view_key="customers.list",
        scope="team",
        config_json='{"version":1,"columns":[{"key":"owner","order":0,"visible":true}],"sorts":[],"filters":[]}',
        created_by=2,
        updated_by=2,
    ))
    db_session.commit()

    response = client.delete("/api/v1/view-preferences/customers.list?scope=team")

    assert response.status_code == 403


def test_rejects_oversized_column_preference_payload(client):
    response = client.put(
        "/api/v1/view-preferences/customers.list",
        json={
            "scope": "personal",
            "config": {
                "version": 1,
                "columns": [
                    {"key": f"field_{index}", "order": index, "visible": True}
                    for index in range(101)
                ],
            },
        },
    )

    assert response.status_code == 422


def test_creates_personal_custom_filter_view_with_generated_name(client):
    response = client.post(
        "/api/v1/view-preferences/customers.list/custom-views",
        json={
            "config": {
                "version": 1,
                "columns": [],
                "filters": [{"field": "status", "op": "contains", "value": ["won"]}],
                "sorts": [],
            },
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "视图 1"
    assert body["scope"] == "personal"
    assert body["user_id"] == 1
    assert body["is_default"] is False
    assert body["sort_order"] is None
    assert body["config"]["filters"][0]["field"] == "status"


def test_custom_filter_view_name_uses_current_effective_count_plus_one(client):
    for _ in range(2):
        response = client.post(
            "/api/v1/view-preferences/customers.list/custom-views",
            json={"config": {"version": 1, "columns": [], "filters": [], "sorts": []}},
        )
        assert response.status_code == 201

    response = client.get("/api/v1/view-preferences/customers.list/custom-views")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()["items"]] == ["视图 1", "视图 2"]


def test_custom_filter_views_are_only_visible_to_creator(client, db_session):
    db_session.add(ViewPreference(
        team_id=1,
        user_id=2,
        view_key="customers.list",
        scope="personal",
        preference_key="custom:99",
        name="视图 1",
        is_default=0,
        config_json='{"version":1,"columns":[],"sorts":[],"filters":[{"field":"owner_id","op":"contains","value":["2"]}]}',
        created_by=2,
        updated_by=2,
    ))
    db_session.commit()

    response = client.get("/api/v1/view-preferences/customers.list/custom-views")

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_renames_and_deletes_owned_custom_filter_view(client):
    created = client.post(
        "/api/v1/view-preferences/customers.list/custom-views",
        json={"config": {"version": 1, "columns": [], "filters": [], "sorts": []}},
    ).json()

    rename_response = client.patch(
        f"/api/v1/view-preferences/customers.list/custom-views/{created['id']}",
        json={"name": "本周重点"},
    )

    assert rename_response.status_code == 200
    assert rename_response.json()["name"] == "本周重点"

    delete_response = client.delete(f"/api/v1/view-preferences/customers.list/custom-views/{created['id']}")
    assert delete_response.status_code == 204

    list_response = client.get("/api/v1/view-preferences/customers.list/custom-views")
    assert list_response.json()["items"] == []


def test_rejects_blank_custom_filter_view_name(client):
    created = client.post(
        "/api/v1/view-preferences/customers.list/custom-views",
        json={"config": {"version": 1, "columns": [], "filters": [], "sorts": []}},
    ).json()

    response = client.patch(
        f"/api/v1/view-preferences/customers.list/custom-views/{created['id']}",
        json={"name": "   "},
    )

    assert response.status_code == 422


def test_rejects_updating_other_users_custom_filter_view(client, db_session):
    db_session.add(ViewPreference(
        id=100,
        team_id=1,
        user_id=2,
        view_key="customers.list",
        scope="personal",
        preference_key="custom:100",
        name="别人的视图",
        is_default=0,
        config_json='{"version":1,"columns":[],"sorts":[],"filters":[]}',
        created_by=2,
        updated_by=2,
    ))
    db_session.commit()

    response = client.patch(
        "/api/v1/view-preferences/customers.list/custom-views/100",
        json={"name": "不能改"},
    )

    assert response.status_code == 404


def test_custom_filter_view_can_move_to_front(client):
    first = client.post(
        "/api/v1/view-preferences/customers.list/custom-views",
        json={"config": {"version": 1, "columns": [], "filters": [], "sorts": []}},
    ).json()
    second = client.post(
        "/api/v1/view-preferences/customers.list/custom-views",
        json={"config": {"version": 1, "columns": [], "filters": [], "sorts": []}},
    ).json()

    response = client.patch(
        f"/api/v1/view-preferences/customers.list/custom-views/{second['id']}",
        json={"sort_order": -1},
    )

    assert response.status_code == 200
    assert response.json()["sort_order"] == -1

    list_response = client.get("/api/v1/view-preferences/customers.list/custom-views")

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["items"]] == [second["id"], first["id"]]

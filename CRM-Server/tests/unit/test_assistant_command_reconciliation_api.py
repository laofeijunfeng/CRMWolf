"""T03: owner-scoped and operator-permitted unresolved command queries."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.security import create_access_token
from app.main import app
from app.models.assistant import AssistantAction, AssistantTask
from app.models.assistant_turn import AssistantRequest, AssistantTurn, AssistantTurnEvent
from app.models.team import UserTeam
from app.models.user import User


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    from app.models.permission import Permission
    from app.models.role import Role
    from app.models.role_permission import RolePermission
    from app.models.user_role import UserRole

    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            UserTeam.__table__,
            Role.__table__,
            Permission.__table__,
            RolePermission.__table__,
            UserRole.__table__,
            AssistantTask.__table__,
            AssistantAction.__table__,
            AssistantRequest.__table__,
            AssistantTurn.__table__,
            AssistantTurnEvent.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _seed_user(db, email: str, user_id: int, team_id: int = 1) -> None:
    db.add(User(id=user_id, email=email, name=email, status="ACTIVE"))
    db.add(UserTeam(user_id=user_id, team_id=team_id, current_team=True))
    db.commit()


def _seed_claim(db, *, task_public: str, status: str, user_id: int, team_id: int = 1) -> None:
    task = AssistantTask(
        public_id=task_public,
        team_id=team_id,
        user_id=user_id,
        goal="T03 fixture",
        status="ACTIVE",
        version=1,
    )
    db.add(task)
    db.flush()
    db.add(
        AssistantAction(
            task_id=task.id,
            team_id=team_id,
            public_id=f"aca_{task_public}",
            action="proposal_command_claim",
            actor="SYSTEM",
            input_json={"kind": "opportunity_create"},
            result_json={"proposal_key": f"pk-{task_public}", "kind": "opportunity_create", "status": status},
        )
    )
    db.commit()


def _auth(user_id: int, team_id: int = 1) -> dict[str, str]:
    from app.core import deps

    token = create_access_token({"sub": str(user_id)})
    original = deps.get_current_user_team
    app.dependency_overrides[deps.get_current_user_team] = lambda: team_id
    _auth._restore = original
    return {"Authorization": f"Bearer {token}"}


def _restore_team_override() -> None:
    from app.core import deps

    app.dependency_overrides.pop(deps.get_current_user_team, None)


def test_owner_sees_only_own_unresolved_claims(client, db_session):
    _seed_user(db_session, "a@x.com", 101)
    _seed_user(db_session, "b@x.com", 102)
    _seed_claim(db_session, task_public="t_own", status="UNKNOWN", user_id=101)
    _seed_claim(db_session, task_public="t_other", status="UNKNOWN", user_id=102)

    resp = client.get("/api/v1/assistant/unknown-commands", headers=_auth(101))
    _restore_team_override()

    assert resp.status_code == 200
    keys = {item["task_public_id"] for item in resp.json()}
    assert keys == {"t_own"}


def test_unauthorized_member_gets_forbidden(client, db_session):
    db_session.add(User(id=201, email="plain@x.com", name="plain", status="ACTIVE"))
    db_session.commit()  # 无团队归属：不属于团队 1，必须 403

    resp = client.get("/api/v1/assistant/unknown-commands", headers=_auth(201))
    _restore_team_override()

    assert resp.status_code == 403


def test_operator_sees_team_claims_including_claimed(client, db_session, monkeypatch):
    from app.crud.permission import permission_crud

    _seed_user(db_session, "op@x.com", 301)
    _seed_user(db_session, "peer@x.com", 302)
    _seed_claim(db_session, task_public="t_u", status="UNKNOWN", user_id=302)
    _seed_claim(db_session, task_public="t_c", status="CLAIMED", user_id=302)
    _seed_claim(db_session, task_public="t_s", status="RECONCILED", user_id=302)

    monkeypatch.setattr(
        permission_crud,
        "get_user_permissions",
        lambda db, uid, tid: [type("P", (), {"code": "assistant:commands:reconcile:team"})()],
    )
    resp = client.get("/api/v1/assistant/unknown-commands", headers=_auth(301))
    _restore_team_override()

    assert resp.status_code == 200
    items = {item["task_public_id"]: item["status"] for item in resp.json()}
    assert items.get("t_u") == "UNKNOWN"
    assert items.get("t_c") == "CLAIMED"
    assert "t_s" not in items


def test_operator_result_is_team_scoped(client, db_session, monkeypatch):
    from app.crud.permission import permission_crud

    _seed_user(db_session, "opt@x.com", 401, team_id=1)
    _seed_claim(db_session, task_public="t_foreign", status="UNKNOWN", user_id=999, team_id=2)

    monkeypatch.setattr(
        permission_crud,
        "get_user_permissions",
        lambda db, uid, tid: [type("P", (), {"code": "assistant:commands:reconcile:team"})()],
    )
    resp = client.get("/api/v1/assistant/unknown-commands", headers=_auth(401, team_id=1))
    _restore_team_override()

    assert resp.status_code == 200
    assert all(item["task_public_id"] != "t_foreign" for item in resp.json())

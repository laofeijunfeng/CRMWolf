"""Manual adjudication of assistant command claims (TRD §7.1, decision 3)."""

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
from app.models.assistant_crm_effect import AssistantCRMEffect
from app.models.assistant_turn import AssistantRequest, AssistantTurn, AssistantTurnEvent
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.team import Team, UserTeam
from app.models.user import User
from app.models.user_role import UserRole


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
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Team.__table__,
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
            AssistantCRMEffect.__table__,
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
    app.dependency_overrides.clear()


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"}


def _seed(db, *, operator: bool = False) -> int:
    """Create team 1, user 501 (operator if operator=True); returns user id."""
    db.add(User(id=501, email="judge@x.com", name="judge", status="ACTIVE"))
    db.add(Team(id=1, name="t", code="T", owner_id=501))
    db.add(UserTeam(user_id=501, team_id=1, current_team=True))
    if operator:
        db.add(Permission(id=91, name="核对", code="assistant:commands:reconcile:team", resource="assistant_command", action="reconcile", scope="team", is_active=True))
        db.add(Role(id=91, name="核对员", code="ASSISTANT_COMMAND_OPERATOR", description=""))
        db.add(RolePermission(role_id=91, permission_id=91))
        db.add(UserRole(user_id=501, role_id=91, team_id=1))
    db.commit()
    return 501


def _seed_claim(db, *, status: str, started: bool, command_id: str = "acm_1") -> str:
    task = AssistantTask(public_id="t_j", team_id=1, user_id=501, goal="g", status="ACTIVE", version=1)
    db.add(task)
    db.flush()
    result = {"proposal_key": "pk_j", "kind": "opportunity_create", "status": status, "command_id": command_id}
    if started:
        result["started"] = True
    db.add(
        AssistantAction(
            task_id=task.id,
            team_id=1,
            public_id="aca_j",
            action="proposal_command_claim",
            actor="SYSTEM",
            input_json={"kind": "opportunity_create"},
            result_json=result,
        )
    )
    db.commit()
    return "aca_j"


def _grant_operator(db, monkeypatch):
    from app.crud.permission import permission_crud

    monkeypatch.setattr(
        permission_crud,
        "get_user_permissions",
        lambda d, uid, tid: [type("P", (), {"code": "assistant:commands:reconcile:team"})()],
    )


def test_adjudication_requires_operator_permission(client, db_session):
    uid = _seed(db_session, operator=False)
    _seed_claim(db_session, status="UNKNOWN", started=True)

    resp = client.post(
        "/api/v1/assistant/unknown-commands/aca_j/adjudicate",
        headers=_auth(uid),
        json={"decision": "REJECTED", "reason": "测试"},
    )

    assert resp.status_code == 403


def test_reject_requires_not_started_proof(client, db_session, monkeypatch):
    uid = _seed(db_session)
    _seed_claim(db_session, status="UNKNOWN", started=True)  # STARTED：无无调用证明
    _grant_operator(db_session, monkeypatch)

    resp = client.post(
        "/api/v1/assistant/unknown-commands/aca_j/adjudicate",
        headers=_auth(uid),
        json={"decision": "REJECTED", "reason": "未见调用"},
    )

    assert resp.status_code == 409


def test_rejected_with_durable_not_started(client, db_session, monkeypatch):
    uid = _seed(db_session)
    _seed_claim(db_session, status="UNKNOWN", started=False)
    _grant_operator(db_session, monkeypatch)

    resp = client.post(
        "/api/v1/assistant/unknown-commands/aca_j/adjudicate",
        headers=_auth(uid),
        json={"decision": "REJECTED", "reason": "持久 NOT_STARTED，无调用"},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "REJECTED"


def test_succeeded_requires_exact_target_effect(client, db_session, monkeypatch):
    uid = _seed(db_session)
    _seed_claim(db_session, status="UNKNOWN", started=True)
    _grant_operator(db_session, monkeypatch)

    resp = client.post(
        "/api/v1/assistant/unknown-commands/aca_j/adjudicate",
        headers=_auth(uid),
        json={"decision": "SUCCEEDED", "reason": "看到了同名商机"},
    )

    # 无 (team,command_id,effect_kind) 精确回执 → 拒绝裁决成功
    assert resp.status_code == 409


def test_unknown_claim_not_found_for_foreign_action(client, db_session, monkeypatch):
    uid = _seed(db_session)
    _grant_operator(db_session, monkeypatch)

    resp = client.post(
        "/api/v1/assistant/unknown-commands/aca_missing/adjudicate",
        headers=_auth(uid),
        json={"decision": "REJECTED", "reason": "x"},
    )

    assert resp.status_code == 404

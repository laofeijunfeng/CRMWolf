from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


from app.api import sales_dashboard
from app.core.database import Base
from app.models.customer_activity import CustomerActivity
from app.models.user import User, UserStatus


@pytest.fixture(scope="function")
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
            CustomerActivity.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def permission_codes(monkeypatch):
    codes: list[str] = []

    def _fake_get_user_permissions(db, user_id, team_id=None):  # noqa: ARG001
        return [SimpleNamespace(code=code) for code in codes]

    monkeypatch.setattr(
        sales_dashboard.permission_crud,
        "get_user_permissions",
        _fake_get_user_permissions,
    )
    return codes


@pytest.fixture
def app(db_session):
    app_ = FastAPI()
    app_.include_router(sales_dashboard.router)
    app_.dependency_overrides[sales_dashboard.get_db] = lambda: db_session
    app_.dependency_overrides[sales_dashboard.get_current_active_user] = lambda: SimpleNamespace(
        id=1,
        name="Alex",
        status="active",
    )
    app_.dependency_overrides[sales_dashboard.get_current_user_team] = lambda: 1
    yield app_
    app_.dependency_overrides.clear()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def seed_follow_up_trend_data(db_session):
    db_session.add_all([
        User(id=1, email="alex@example.com", name="Alex", status=UserStatus.ACTIVE),
        User(id=2, email="eddie@example.com", name="Eddie", status=UserStatus.ACTIVE),
        User(id=3, email="other@example.com", name="Other Team", status=UserStatus.ACTIVE),
    ])
    db_session.add_all([
        CustomerActivity(
            id=1,
            team_id=1,
            source_content="alex valid",
            activity_kind="PHONE_FOLLOW_UP",
            creator_id="1",
            occurred_at=datetime(2026, 7, 1, 9, 0, 0),
            effectiveness_score=80,
            effectiveness_is_valid=True,
        ),
        CustomerActivity(
            id=2,
            team_id=1,
            source_content="alex invalid",
            activity_kind="WECHAT_FOLLOW_UP",
            creator_id="1",
            occurred_at=datetime(2026, 7, 1, 10, 0, 0),
            effectiveness_score=40,
            effectiveness_is_valid=False,
        ),
        CustomerActivity(
            id=3,
            team_id=1,
            source_content="eddie valid",
            activity_kind="VISIT_FOLLOW_UP",
            creator_id="2",
            occurred_at=datetime(2026, 7, 1, 11, 0, 0),
            effectiveness_score=90,
            effectiveness_is_valid=True,
        ),
        CustomerActivity(
            id=4,
            team_id=2,
            source_content="other team",
            activity_kind="PHONE_FOLLOW_UP",
            creator_id="3",
            occurred_at=datetime(2026, 7, 1, 12, 0, 0),
            effectiveness_score=100,
            effectiveness_is_valid=True,
        ),
    ])
    db_session.commit()


def test_follow_up_trend_own_scope_ignores_owner_filter_and_limits_to_current_user(
    client,
    permission_codes,
    seed_follow_up_trend_data,
):
    permission_codes[:] = ["sales_dashboard:view:own"]

    response = client.get(
        "/v1/sales-dashboard/follow-up-trend",
        params={
            "start_date": "2026-07-01",
            "end_date": "2026-07-01",
            "owner_id": "2",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "own"
    assert payload["data"] == [
        {
            "date": "2026-07-01",
            "total": 2,
            "valid": 1,
            "members": [
                {"user_id": "1", "name": "Alex", "total": 2, "valid": 1},
            ],
        },
    ]


def test_follow_up_trend_team_scope_applies_owner_filter_inside_current_team(
    client,
    permission_codes,
    seed_follow_up_trend_data,
):
    permission_codes[:] = ["sales_dashboard:view:team"]

    response = client.get(
        "/v1/sales-dashboard/follow-up-trend",
        params={
            "start_date": "2026-07-01",
            "end_date": "2026-07-01",
            "owner_id": "2",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "team"
    assert payload["data"] == [
        {
            "date": "2026-07-01",
            "total": 1,
            "valid": 1,
            "members": [
                {"user_id": "2", "name": "Eddie", "total": 1, "valid": 1},
            ],
        },
    ]


def test_follow_up_trend_all_scope_still_stays_in_current_team(
    client,
    permission_codes,
    seed_follow_up_trend_data,
):
    permission_codes[:] = ["sales_dashboard:view:all"]

    response = client.get(
        "/v1/sales-dashboard/follow-up-trend",
        params={
            "start_date": "2026-07-01",
            "end_date": "2026-07-01",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "all"
    assert payload["data"][0]["total"] == 3
    assert payload["data"][0]["valid"] == 2
    assert payload["data"][0]["members"] == [
        {"user_id": "1", "name": "Alex", "total": 2, "valid": 1},
        {"user_id": "2", "name": "Eddie", "total": 1, "valid": 1},
    ]


def test_follow_up_trend_requires_sales_dashboard_permission(
    client,
    permission_codes,
    seed_follow_up_trend_data,
):
    permission_codes[:] = []

    response = client.get(
        "/v1/sales-dashboard/follow-up-trend",
        params={
            "start_date": "2026-07-01",
            "end_date": "2026-07-01",
        },
    )

    assert response.status_code == 403

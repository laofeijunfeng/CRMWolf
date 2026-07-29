from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.api.leads import router as leads_router
from app.core import deps
from app.core.database import Base
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.user import User, UserStatus


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[User.__table__, Lead.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(leads_router)
    app.dependency_overrides[deps.get_db] = lambda: db_session
    app.dependency_overrides[deps.get_current_user_team] = lambda: 1
    app.dependency_overrides[deps.get_current_active_user] = lambda: SimpleNamespace(
        id=1,
        name="销售张",
        status="active",
    )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_my_leads_list_includes_owner_info(client, db_session):
    db_session.add(User(id=1, email="sales@example.com", name="销售张", status=UserStatus.ACTIVE))
    db_session.add(
        Lead(
            team_id=1,
            lead_name="测试线索",
            source=LeadSource.WEBSITE_INQUIRY,
            city="上海",
            contact_name="王五",
            contact_phone="13800138000",
            owner_id="1",
            creator_id="1",
            status=LeadStatus.FOLLOWING,
        )
    )
    db_session.commit()

    response = client.get("/v1/leads/my/list")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["owner_id"] == "1"
    assert item["owner_info"] == {
        "id": "1",
        "name": "销售张",
        "avatar_url": None,
    }

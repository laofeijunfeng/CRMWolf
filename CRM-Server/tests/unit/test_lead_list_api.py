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


def test_leads_list_owner_me_includes_owner_info(client, db_session, monkeypatch):
    from app.crud.permission import permission_crud

    monkeypatch.setattr(permission_crud, "get_user_permissions", lambda *args, **kwargs: [])

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

    response = client.get("/v1/leads/", params={"owner_id": "me"})

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["owner_id"] == "1"
    assert item["owner_info"] == {
        "id": "1",
        "name": "销售张",
        "avatar_url": None,
    }


def test_leads_sorts_only_uses_unified_protocol_instead_of_legacy_sort(
    client, db_session, monkeypatch,
):
    from app.crud.permission import permission_crud

    monkeypatch.setattr(permission_crud, "get_user_permissions", lambda *args, **kwargs: [])
    db_session.add_all(
        [
            Lead(
                team_id=1,
                lead_name="Zulu",
                source=LeadSource.WEBSITE_INQUIRY,
                city="上海",
                contact_name="甲",
                contact_phone="13800138011",
                owner_id="1",
                creator_id="1",
                status=LeadStatus.NEW,
            ),
            Lead(
                team_id=1,
                lead_name="Alpha",
                source=LeadSource.WEBSITE_INQUIRY,
                city="北京",
                contact_name="乙",
                contact_phone="13800138012",
                owner_id="1",
                creator_id="1",
                status=LeadStatus.FOLLOWING,
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        "/v1/leads/",
        params={
            "sorts": '[{"field":"lead_name","direction":"asc"}]',
            "order_by": "lead_name",
            "order_dir": "desc",
            "limit": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert [item["lead_name"] for item in payload["items"]] == ["Alpha"]


def test_public_leads_unified_query_filters_sorts_and_preserves_public_scope(client, db_session):
    db_session.add_all(
        [
            Lead(
                team_id=1,
                lead_name="公海 Alpha",
                source=LeadSource.WEBSITE_INQUIRY,
                city="上海",
                contact_name="甲",
                contact_phone="13800138001",
                owner_id=None,
                creator_id="1",
                status=LeadStatus.NEW,
            ),
            Lead(
                team_id=1,
                lead_name="公海 Beta",
                source=LeadSource.WEBSITE_INQUIRY,
                city="北京",
                contact_name="乙",
                contact_phone="13800138002",
                owner_id=None,
                creator_id="1",
                status=LeadStatus.FOLLOWING,
            ),
            Lead(
                team_id=1,
                lead_name="已转化公海",
                source=LeadSource.WEBSITE_INQUIRY,
                city="上海",
                contact_name="丙",
                contact_phone="13800138003",
                owner_id=None,
                creator_id="1",
                status=LeadStatus.CONVERTED,
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        "/v1/leads/public/list",
        params={
            "filters": '[{"field":"city","op":"contains","value":["上海","北京"]}]',
            "sorts": '[{"field":"lead_name","direction":"desc"}]',
            "limit": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert [item["lead_name"] for item in payload["items"]] == ["公海 Beta"]


def test_public_leads_empty_new_protocol_does_not_fall_back_to_legacy_filters(client, db_session):
    db_session.add(
        Lead(
            team_id=1,
            lead_name="公海线索",
            source=LeadSource.WEBSITE_INQUIRY,
            city="上海",
            contact_name="甲",
            contact_phone="13800138004",
            owner_id=None,
            creator_id="1",
            status=LeadStatus.NEW,
        )
    )
    db_session.commit()

    response = client.get(
        "/v1/leads/public/list",
        params={"filters": "[]", "sorts": "[]", "order_by": "missing_legacy_field"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_public_leads_rejects_unknown_unified_query_field(client):
    response = client.get(
        "/v1/leads/public/list",
        params={"filters": "[]", "sorts": '[{"field":"missing_field","direction":"asc"}]'},
    )

    assert response.status_code == 400
    assert "missing_field" in response.json()["detail"]

"""Acquisition source entity seams from TRD 9.1 API-02 / API-07 / API-08 / API-09 / API-10."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import acquisition_sources as acquisition_sources_api
from app.api import customers as customers_api
from app.api import teams as teams_api
from app.api.leads import analytics_router as leads_analytics_router
from app.api.leads import router as leads_router
from app.core import database, deps
from app.core.database import Base
from app.models.acquisition_source import AcquisitionSource
from app.models.customer import Contact, Customer, CustomerMember
from app.models.lead import Lead, LeadFollowUp, LeadStatus
from app.models.role import Role
from app.models.team import Team, UserTeam
from app.models.user import User, UserStatus
from app.models.user_role import UserRole


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


def _lead_payload(name: str, source_public_id: str, phone: str = "13800138001") -> dict[str, str]:
    return {
        "lead_name": name,
        "source_public_id": source_public_id,
        "city": "上海",
        "contact_name": "张三",
        "contact_phone": phone,
    }


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
        LeadFollowUp.__table__,
        Customer.__table__,
        Contact.__table__,
        CustomerMember.__table__,
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
        "lead:view:all",
        "customer:view:all",
        "customer:view:own",
        "customer:edit:all",
    }

    def _permission_stub(_db, user_id, team_id=None):
        return [SimpleNamespace(code=code) for code in permissions]

    monkeypatch.setattr("app.core.deps.permission_crud.get_user_permissions", _permission_stub)
    monkeypatch.setattr(
        "app.crud.customer_activity.customer_activity_crud.migrate_from_lead",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.operation_log_service.operation_log_service.log_lead_converted",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.operation_log_service.operation_log_service.log",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.crud.operation_log.operation_log_crud.migrate_lead_logs_to_customer",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.customer_intelligence_refresh_service.trigger_customer_created_refresh",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.customer_intelligence_refresh_service.has_customer_business_data",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        "app.services.feishu.feishu_service.notify_account_created",
        AsyncMock(return_value=None),
    )

    app = FastAPI()
    app.include_router(teams_api.router)
    app.include_router(acquisition_sources_api.router)
    app.include_router(leads_router)
    app.include_router(leads_analytics_router)
    app.include_router(customers_api.router)

    team_state = {"id": None}

    def _get_db():
        yield db

    def _current_team():
        if team_state["id"] is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail="未选择团队")
        return team_state["id"]

    for module in (database, deps, teams_api, acquisition_sources_api, leads_router, customers_api):
        target = module
        if hasattr(target, "get_db"):
            app.dependency_overrides[target.get_db] = _get_db
        if hasattr(target, "get_current_user_team"):
            app.dependency_overrides[target.get_current_user_team] = _current_team
        if hasattr(target, "get_current_active_user"):
            app.dependency_overrides[target.get_current_active_user] = lambda: current_user

    # leads router is an APIRouter, dependencies live on deps / leads module
    from app.api import leads as leads_api

    app.dependency_overrides[deps.get_db] = _get_db
    app.dependency_overrides[deps.get_current_user_team] = _current_team
    app.dependency_overrides[deps.get_current_active_user] = lambda: current_user
    app.dependency_overrides[leads_api.get_db] = _get_db
    app.dependency_overrides[leads_api.get_current_user_team] = _current_team
    app.dependency_overrides[leads_api.get_current_active_user] = lambda: current_user
    app.dependency_overrides[customers_api.get_db] = _get_db
    app.dependency_overrides[customers_api.get_current_user_team] = _current_team
    app.dependency_overrides[customers_api.get_current_active_user] = lambda: current_user

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


def _option_by_code(api_env, code: str) -> dict:
    options = api_env.client.get("/v1/acquisition-sources/options").json()
    return next(item for item in options if item["code"] == code)


def test_rename_follows_on_lead_and_customer_read_paths(api_env):
    _create_team(api_env)
    exhibition = _option_by_code(api_env, "EXHIBITION")

    lead_resp = api_env.client.post("/v1/leads/", json=_lead_payload("展会线索", exhibition["public_id"]))
    assert lead_resp.status_code == 201, lead_resp.text
    lead_id = lead_resp.json()["public_id"]

    customer_resp = api_env.client.post(
        "/v1/customers/",
        json={"account_name": "展会客户", "city": "上海", "source_public_id": exhibition["public_id"]},
    )
    assert customer_resp.status_code == 201, customer_resp.text
    customer_id = customer_resp.json()["public_id"]

    renamed = api_env.client.put(
        f"/v1/acquisition-sources/{exhibition['public_id']}",
        json={"name": "线下展会"},
    )
    assert renamed.status_code == 200, renamed.text

    lead_list = api_env.client.get("/v1/leads/").json()["items"]
    lead_item = next(item for item in lead_list if item["public_id"] == lead_id)
    assert lead_item["source"] == "线下展会"
    assert lead_item["source_info"]["public_id"] == exhibition["public_id"]
    assert lead_item["source_info"]["name"] == "线下展会"

    lead_detail = api_env.client.get(f"/v1/leads/{lead_id}").json()
    assert lead_detail["source"] == "线下展会"
    assert lead_detail["source_info"]["public_id"] == exhibition["public_id"]
    assert lead_detail["source_info"]["name"] == "线下展会"

    customer_list = api_env.client.get("/v1/customers/").json()["items"]
    customer_item = next(item for item in customer_list if item["public_id"] == customer_id)
    assert customer_item["source"] == "线下展会"
    assert customer_item["source_info"]["public_id"] == exhibition["public_id"]
    assert customer_item["source_info"]["name"] == "线下展会"

    customer_detail = api_env.client.get(f"/v1/customers/{customer_id}").json()
    assert customer_detail["source"] == "线下展会"
    assert customer_detail["source_info"]["public_id"] == exhibition["public_id"]
    assert customer_detail["source_info"]["name"] == "线下展会"


def test_convert_from_lead_inherits_source_and_rejects_missing_source(api_env):
    team_id = _create_team(api_env)
    exhibition = _option_by_code(api_env, "EXHIBITION")

    lead_resp = api_env.client.post("/v1/leads/", json=_lead_payload("待转化线索", exhibition["public_id"]))
    assert lead_resp.status_code == 201, lead_resp.text
    lead_public_id = lead_resp.json()["public_id"]
    lead = api_env.db.query(Lead).filter(Lead.public_id == lead_public_id).one()
    lead_source_id = lead.source_id
    assert lead_source_id is not None

    convert = api_env.client.post(
        "/v1/customers/convert-from-lead",
        json={"lead_id": lead_public_id, "account_name": "转化后的客户"},
    )
    assert convert.status_code == 201, convert.text
    assert set(convert.json()) == {"customer_id", "contact_id", "message"}

    customer = (
        api_env.db.query(Customer)
        .filter(Customer.account_name == "转化后的客户", Customer.team_id == team_id)
        .one()
    )
    assert customer.source_id == lead_source_id
    assert customer.source_lead_id == lead.id

    listed = api_env.client.get("/v1/customers/").json()["items"]
    converted_item = next(item for item in listed if item["public_id"] == customer.public_id)
    assert converted_item["source_lead_id"] == lead_public_id
    assert converted_item["source_info"]["public_id"] == exhibition["public_id"]

    orphan = Lead(
        team_id=team_id,
        lead_name="无来源线索",
        source="网站咨询",
        source_id=None,
        city="上海",
        contact_name="李四",
        contact_phone="13800138999",
        owner_id="1",
        creator_id="1",
        status=LeadStatus.FOLLOWING,
    )
    api_env.db.add(orphan)
    api_env.db.commit()

    rejected = api_env.client.post(
        "/v1/customers/convert-from-lead",
        json={"lead_id": orphan.public_id, "account_name": "不该出现的客户"},
    )
    assert rejected.status_code == 400
    assert "来源" in rejected.json()["detail"]
    assert api_env.db.query(Customer).filter(Customer.account_name == "不该出现的客户").first() is None


def test_import_unknown_or_forbidden_source_fails_that_row(api_env):
    _create_team(api_env)
    options = api_env.client.get("/v1/acquisition-sources/options").json()
    available_names = [item["name"] for item in options]

    response = api_env.client.post(
        "/v1/leads/batch-import",
        json={
            "leads": [
                {
                    "lead_name": "可导入线索",
                    "source": "网站咨询",
                    "city": "上海",
                    "contact_name": "王五",
                    "contact_phone": "13800138011",
                },
                {
                    "lead_name": "未知来源线索",
                    "source": "地推",
                    "city": "上海",
                    "contact_name": "赵六",
                    "contact_phone": "13800138012",
                },
                {
                    "lead_name": "线索转化导入",
                    "source": "线索转化",
                    "city": "上海",
                    "contact_name": "钱七",
                    "contact_phone": "13800138013",
                },
            ]
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] == 1
    assert payload["failed"] == 2

    failed_by_name = {item["lead_name"]: item["error"] for item in payload["failed_items"]}
    assert "未知来源线索" in failed_by_name
    assert "线索转化导入" in failed_by_name
    assert "地推" in failed_by_name["未知来源线索"] or "不存在" in failed_by_name["未知来源线索"]
    for name in available_names:
        assert name in failed_by_name["未知来源线索"]
    assert "线索转化" in failed_by_name["线索转化导入"] or "不能使用" in failed_by_name["线索转化导入"]

    saved = api_env.db.query(Lead).filter(Lead.lead_name == "可导入线索").one()
    assert saved.source_id is not None
    assert api_env.db.query(Lead).filter(Lead.lead_name == "未知来源线索").first() is None
    assert api_env.db.query(Lead).filter(Lead.lead_name == "线索转化导入").first() is None


def test_inactive_source_still_filters_historical_records(api_env):
    _create_team(api_env)
    exhibition = _option_by_code(api_env, "EXHIBITION")
    website = _option_by_code(api_env, "WEBSITE_INQUIRY")

    lead_resp = api_env.client.post("/v1/leads/", json=_lead_payload("历史展会线索", exhibition["public_id"]))
    assert lead_resp.status_code == 201, lead_resp.text
    other_lead = api_env.client.post(
        "/v1/leads/",
        json=_lead_payload("网站线索", website["public_id"], phone="13800138021"),
    )
    assert other_lead.status_code == 201, other_lead.text

    customer_resp = api_env.client.post(
        "/v1/customers/",
        json={"account_name": "历史展会客户", "city": "上海", "source_public_id": exhibition["public_id"]},
    )
    assert customer_resp.status_code == 201, customer_resp.text
    other_customer = api_env.client.post(
        "/v1/customers/",
        json={"account_name": "网站客户", "city": "上海", "source_public_id": website["public_id"]},
    )
    assert other_customer.status_code == 201, other_customer.text

    deactivated = api_env.client.put(
        f"/v1/acquisition-sources/{exhibition['public_id']}",
        json={"is_active": 0},
    )
    assert deactivated.status_code == 200, deactivated.text

    lead_query = api_env.client.get(
        "/v1/leads/",
        params={"source_public_id": exhibition["public_id"]},
    )
    assert lead_query.status_code == 200, lead_query.text
    assert [item["lead_name"] for item in lead_query.json()["items"]] == ["历史展会线索"]

    lead_filters = api_env.client.get(
        "/v1/leads/",
        params={
            "filters": json.dumps(
                {"filters": [{"field": "source", "op": "eq", "value": exhibition["public_id"]}]}
            )
        },
    )
    assert lead_filters.status_code == 200, lead_filters.text
    assert [item["lead_name"] for item in lead_filters.json()["items"]] == ["历史展会线索"]

    customer_query = api_env.client.get(
        "/v1/customers/",
        params={"source_public_id": exhibition["public_id"]},
    )
    assert customer_query.status_code == 200, customer_query.text
    assert [item["account_name"] for item in customer_query.json()["items"]] == ["历史展会客户"]


def test_conversion_analytics_keeps_same_public_id_after_rename(api_env):
    _create_team(api_env)
    exhibition = _option_by_code(api_env, "EXHIBITION")

    lead_resp = api_env.client.post("/v1/leads/", json=_lead_payload("分析线索", exhibition["public_id"]))
    assert lead_resp.status_code == 201, lead_resp.text
    convert = api_env.client.post(
        "/v1/customers/convert-from-lead",
        json={"lead_id": lead_resp.json()["public_id"], "account_name": "分析客户"},
    )
    assert convert.status_code == 201, convert.text

    before = api_env.client.get("/v1/analytics/leads/conversion")
    assert before.status_code == 200, before.text
    before_row = next(item for item in before.json() if item.get("source_public_id") == exhibition["public_id"])
    assert before_row["total"] == 1
    assert before_row["converted"] == 1
    assert before_row["source"] == "展会"

    renamed = api_env.client.put(
        f"/v1/acquisition-sources/{exhibition['public_id']}",
        json={"name": "城市展会"},
    )
    assert renamed.status_code == 200, renamed.text

    after = api_env.client.get("/v1/analytics/leads/conversion")
    assert after.status_code == 200, after.text
    matched = [item for item in after.json() if item.get("source_public_id") == exhibition["public_id"]]
    assert len(matched) == 1
    assert matched[0]["total"] == 1
    assert matched[0]["converted"] == 1
    assert matched[0]["source"] == "城市展会"
    assert matched[0]["source_name"] == "城市展会"

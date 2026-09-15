"""Command-path convert maps product intent errors to 404/400, not 409."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, event, text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import customers as customers_api
from app.core.database import Base
from app.crud.product import product_crud
from app.models.acquisition_source import AcquisitionSource
from app.models.command_execution import CommandExecution
from app.models.customer import Contact, Customer, CustomerProduct
from app.models.lead import Lead, LeadFollowUp, LeadProduct
from app.models.operation_log import OperationLog
from app.models.opportunity import Opportunity, OpportunityProductModule
from app.models.product import Product, ProductModule
from app.schemas.product import ProductCreate


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


@pytest.fixture
def convert_client(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS crm_customer_deal_journeys (id INTEGER PRIMARY KEY)"))

    tables = [
        AcquisitionSource.__table__,
        Product.__table__,
        ProductModule.__table__,
        Lead.__table__,
        LeadProduct.__table__,
        LeadFollowUp.__table__,
        Customer.__table__,
        CustomerProduct.__table__,
        Contact.__table__,
        Opportunity.__table__,
        OpportunityProductModule.__table__,
        OperationLog.__table__,
        CommandExecution.__table__,
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

    session = sessionmaker(bind=engine, expire_on_commit=False)()
    session.add(
        AcquisitionSource(
            team_id=1,
            code="ONLINE_REGISTER",
            name="线上注册",
            is_system=1,
            is_active=1,
            sort_order=10,
            created_by="u1",
        )
    )
    session.commit()

    monkeypatch.setattr(
        "app.crud.customer_activity.customer_activity_crud.migrate_from_lead",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.operation_log_service.operation_log_service.log_lead_converted",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.crud.operation_log.operation_log_crud.migrate_lead_logs_to_customer",
        lambda *args, **kwargs: None,
    )

    app = FastAPI()
    app.include_router(customers_api.router)
    current_user = SimpleNamespace(id="u1", name="销售", status="active")
    app.dependency_overrides[customers_api.get_db] = lambda: session
    app.dependency_overrides[customers_api.get_current_user_team] = lambda: 1
    app.dependency_overrides[customers_api.get_current_active_user] = lambda: current_user

    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=session)

    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def _source(db):
    return db.query(AcquisitionSource).filter(AcquisitionSource.team_id == 1).one()


def _lead(db, *, lead_name: str, product=None) -> Lead:
    source = _source(db)
    lead = Lead(
        team_id=1,
        lead_name=lead_name,
        source=source.name,
        source_id=source.id,
        city="上海",
        contact_name="王",
        contact_phone="13800138000",
        creator_id="u1",
    )
    db.add(lead)
    db.flush()
    if product is not None:
        db.add(LeadProduct(lead_id=lead.id, product_id=product.id, team_id=1))
    db.commit()
    db.refresh(lead)
    return lead


def _command_headers(suffix: str) -> dict[str, str]:
    token = uuid4().hex[:12]
    return {
        "X-Operation-Id": f"op_{suffix}_{token}",
        "Idempotency-Key": f"idem_{suffix}_{token}",
    }


def _convert(client, lead: Lead, headers: dict[str, str], **payload):
    body = {"lead_id": lead.public_id, "account_name": lead.lead_name, **payload}
    return client.post("/v1/customers/convert-from-lead", json=body, headers=headers)


def test_command_convert_other_team_product_is_404(convert_client):
    product_crud.create(convert_client.db, 1, ProductCreate(name="CRM"), "u1")
    other = product_crud.create(convert_client.db, 2, ProductCreate(name="OA"), "u1")
    lead = _lead(convert_client.db, lead_name="跨团队产品线索")
    headers = _command_headers("cross_team")

    response = _convert(convert_client.client, lead, headers, product_public_id=other.public_id)

    assert response.status_code == 404, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "PRODUCT_NOT_FOUND"
    assert detail["message"] == "产品不存在"
    assert detail["operation_id"] == headers["X-Operation-Id"]
    execution = convert_client.db.query(CommandExecution).one()
    assert execution.error_code == "PRODUCT_NOT_FOUND"
    assert execution.error_message == "产品不存在"


def test_command_convert_missing_product_is_400(convert_client):
    product_crud.create(convert_client.db, 1, ProductCreate(name="CRM"), "u1")
    lead = _lead(convert_client.db, lead_name="无产品历史线索")
    headers = _command_headers("missing")

    response = _convert(convert_client.client, lead, headers)

    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert detail["message"] == "请选择产品"
    assert detail["operation_id"] == headers["X-Operation-Id"]
    execution = convert_client.db.query(CommandExecution).one()
    assert execution.error_code == "PRODUCT_INTENT_REJECTED"
    assert execution.error_message == "请选择产品"


def test_command_convert_empty_catalog_with_product_id_is_400(convert_client):
    lead = _lead(convert_client.db, lead_name="空目录线索")
    headers = _command_headers("empty")

    response = _convert(convert_client.client, lead, headers, product_public_id="prd_junk")

    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "还没有可用产品" in detail["message"]
    assert detail["operation_id"] == headers["X-Operation-Id"]
    execution = convert_client.db.query(CommandExecution).one()
    assert execution.error_code == "PRODUCT_INTENT_REJECTED"
    assert "还没有可用产品" in execution.error_message

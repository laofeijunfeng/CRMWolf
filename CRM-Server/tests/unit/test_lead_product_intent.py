from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud.lead import lead_crud
from app.crud.product import product_crud
from app.crud.product_intent import (
    EMPTY_CATALOG_MESSAGE,
    ProductNotFoundError,
    product_intent_payload,
)
from app.models.acquisition_source import AcquisitionSource
from app.models.lead import Lead, LeadProduct
from app.models.product import Product, ProductModule
from app.schemas.lead import LeadCreate, LeadUpdate
from app.schemas.product import ProductCreate


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


@pytest.fixture
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'lead-product-intent.db'}")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    tables = [
        AcquisitionSource.__table__,
        Product.__table__,
        ProductModule.__table__,
        Lead.__table__,
        LeadProduct.__table__,
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
    try:
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
        yield session
    finally:
        session.close()


def _lead_in(*, product_public_id: str) -> LeadCreate:
    return LeadCreate(
        lead_name="线索A",
        city="上海",
        contact_name="王",
        contact_phone="13800138000",
        source="线上注册",
        product_public_id=product_public_id,
    )


def _lead_row(db, *, team_id: int) -> Lead:
    lead = Lead(
        id=1,
        team_id=team_id,
        lead_name="历史线索",
        source="线上注册",
        city="上海",
        contact_name="王",
        contact_phone="13800138000",
        creator_id="u1",
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def test_create_lead_requires_active_product(db):
    with pytest.raises(ValidationError, match="缺少产品"):
        LeadCreate(
            lead_name="线索A",
            city="上海",
            contact_name="王",
            contact_phone="13800138000",
            source="线上注册",
        )
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    other = product_crud.create(db, 2, ProductCreate(name="OA"), "u1")
    with pytest.raises(ProductNotFoundError, match="产品不存在"):
        lead_crud.create(db, _lead_in(product_public_id=other.public_id), "u1", 1)
    inactive = product_crud.create(db, 1, ProductCreate(name="停用"), "u1")
    inactive.is_active = False
    db.commit()
    with pytest.raises(ValueError, match="请选择启用中的产品"):
        lead_crud.create(db, _lead_in(product_public_id=inactive.public_id), "u1", 1)
    lead = lead_crud.create(db, _lead_in(product_public_id=crm.public_id), "u1", 1)
    payload = product_intent_payload(lead.product_links)
    assert payload["product_public_id"] == crm.public_id
    assert db.query(LeadProduct).filter(LeadProduct.lead_id == lead.id).count() == 1


def test_update_lead_replaces_product_link(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    lead = lead_crud.create(db, _lead_in(product_public_id=crm.public_id), "u1", 1)
    lead_crud.update(db, lead, LeadUpdate(product_public_id=oa.public_id))
    links = db.query(LeadProduct).filter(LeadProduct.lead_id == lead.id).all()
    assert [link.product_id for link in links] == [oa.id]


def test_update_lead_without_product_keeps_existing_link(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    lead = lead_crud.create(db, _lead_in(product_public_id=crm.public_id), "u1", 1)
    lead_crud.update(db, lead, LeadUpdate(city="杭州"))
    links = db.query(LeadProduct).filter(LeadProduct.lead_id == lead.id).all()
    assert [link.product_id for link in links] == [crm.id]


def test_historical_lead_without_product_reads_empty_payload(db):
    lead = _lead_row(db, team_id=1)
    assert product_intent_payload(lead.product_links) == {
        "product_public_id": None,
        "product_name": None,
        "products": [],
    }


def test_batch_import_missing_product_fails_that_row():
    with pytest.raises(ValidationError, match="缺少产品"):
        LeadCreate(
            lead_name="导入失败行",
            city="上海",
            contact_name="王",
            contact_phone="13800138000",
            source="线上注册",
            product_public_id=" ",
        )


def test_leads_catalog_exposes_product_name():
    from app.core.list_query.catalogs.leads import LEADS_LIST_QUERY_CATALOG

    field = LEADS_LIST_QUERY_CATALOG.require("product_name")
    assert field.type == "text"
    assert field.supports_sorting()


def test_create_lead_empty_catalog_uses_admin_copy(db):
    with pytest.raises(ValueError, match="还没有可用产品"):
        lead_crud.create(db, _lead_in(product_public_id="prd_junk"), "u1", 1)


def test_create_lead_only_inactive_products_uses_admin_copy(db):
    inactive = product_crud.create(db, 1, ProductCreate(name="停用"), "u1")
    inactive.is_active = False
    db.commit()
    with pytest.raises(ValueError, match=EMPTY_CATALOG_MESSAGE):
        lead_crud.create(db, _lead_in(product_public_id=inactive.public_id), "u1", 1)


def test_update_lead_empty_catalog_uses_admin_copy(db):
    lead = _lead_row(db, team_id=1)
    with pytest.raises(ValueError, match=EMPTY_CATALOG_MESSAGE):
        lead_crud.update(db, lead, LeadUpdate(product_public_id="prd_junk"))


def test_build_lead_response_includes_product_public_id(db):
    from app.api.leads import _build_lead_list_responses, _build_lead_response

    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    lead = lead_crud.create(db, _lead_in(product_public_id=crm.public_id), "u1", 1)
    response = _build_lead_response(db, lead)
    assert response.product_public_id == crm.public_id
    assert response.product_name == "CRM"
    assert [(item.public_id, item.name) for item in response.products] == [(crm.public_id, "CRM")]

    listed = _build_lead_list_responses(db, [lead])
    assert listed[0].product_public_id == crm.public_id
    assert listed[0].product_name == "CRM"


def test_lead_parser_create_entity_defaults_first_active_product(db):
    import asyncio

    from app.services.ai_parser.lead_parser import LeadAIParser

    db.add(
        AcquisitionSource(
            team_id=1,
            code="OTHER",
            name="其他",
            is_system=1,
            is_active=1,
            sort_order=99,
            created_by="u1",
        )
    )
    db.commit()
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    lead = asyncio.run(
        LeadAIParser().create_entity(
            db,
            {
                "lead_name": "解析线索",
                "source": "线上注册",
                "city": "上海",
                "contact_name": "王",
                "contact_phone": "13800138000",
            },
            "u1",
            1,
        )
    )
    assert product_intent_payload(lead.product_links)["product_public_id"] == crm.public_id


def test_lead_parser_create_entity_empty_catalog(db):
    import asyncio

    from app.services.ai_parser.lead_parser import LeadAIParser

    db.add(
        AcquisitionSource(
            team_id=1,
            code="OTHER",
            name="其他",
            is_system=1,
            is_active=1,
            sort_order=99,
            created_by="u1",
        )
    )
    db.commit()
    with pytest.raises(ValueError, match=EMPTY_CATALOG_MESSAGE):
        asyncio.run(
            LeadAIParser().create_entity(
                db,
                {
                    "lead_name": "解析线索",
                    "source": "线上注册",
                    "city": "上海",
                    "contact_name": "王",
                    "contact_phone": "13800138000",
                },
                "u1",
                1,
            )
        )


def test_leads_catalog_product_name_uses_fresh_subquery():
    from app.core.list_query.catalogs.leads import (
        LEADS_LIST_QUERY_CATALOG,
        _lead_product_name_expression,
    )

    field = LEADS_LIST_QUERY_CATALOG.require("product_name")
    assert field.expression is not _lead_product_name_expression()

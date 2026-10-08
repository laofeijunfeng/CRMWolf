"""AI 创建解析器把来源/产品名称解析成表单 public_id 的回归测试。"""
import asyncio
from pathlib import Path

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud.product import product_crud
from app.models.acquisition_source import AcquisitionSource
from app.models.product import Product, ProductModule
from app.schemas.product import ProductCreate
from app.services.ai_parser.customer_parser import CustomerAIParser
from app.services.ai_parser.lead_parser import LeadAIParser


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


@pytest.fixture
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'parse-catalog.db'}")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    tables = [AcquisitionSource.__table__, Product.__table__, ProductModule.__table__]
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
                code="OTHER",
                name="其他",
                is_system=1,
                is_active=1,
                sort_order=99,
                created_by="u1",
            )
        )
        session.commit()
        yield session
    finally:
        session.close()


def _raw_parse_result(product_name: str | None, source_name: str | None = "线上注册") -> dict:
    return {
        "lead_info": {
            "lead_name": "阿里巴巴",
            "source": source_name,
            "city": "杭州",
            "company_scale": "501-1000人",
            "product": product_name,
            "contact_name": "张三",
            "contact_phone": "13800138000",
            "missing_fields": [],
        },
        "follow_up_info": None,
        "thinking_process": "",
    }


def test_lead_parser_attaches_source_and_product_public_ids(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    result = _raw_parse_result("想做 CRM 的客户")

    LeadAIParser().attach_catalog_ids(result, db, 1)

    lead_info = result["lead_info"]
    assert lead_info["product"] == "CRM"
    assert lead_info["product_public_id"] == crm.public_id
    assert lead_info["source_public_id"] is not None


def test_lead_parser_unmatched_product_stays_null(db):
    product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    result = _raw_parse_result("完全无关的产品描述")

    LeadAIParser().attach_catalog_ids(result, db, 1)

    lead_info = result["lead_info"]
    assert lead_info["product"] is None
    assert lead_info["product_public_id"] is None


def test_customer_parser_attaches_product_public_id(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    result = {
        "customer_info": {
            "account_name": "阿里巴巴",
            "city": "杭州",
            "company_scale": None,
            "source": "其他",
            "product": "CRM",
            "industry_hint": None,
            "missing_fields": [],
        },
        "contact_info": {},
        "follow_up_info": None,
        "thinking_process": "",
    }

    CustomerAIParser().attach_catalog_ids(result, db, 1)

    customer_info = result["customer_info"]
    assert customer_info["product"] == "CRM"
    assert customer_info["product_public_id"] == crm.public_id
    assert customer_info["source_public_id"] is not None


def test_lead_parser_empty_source_keeps_null_public_id(db):
    product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    result = _raw_parse_result(None, source_name=None)

    LeadAIParser().attach_catalog_ids(result, db, 1)

    assert result["lead_info"]["source_public_id"] is None

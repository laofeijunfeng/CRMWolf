"""Regression: creating an opportunity must load the team customer."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import DropIndex

from app.crud.opportunity import opportunity_crud
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.procurement import OpportunityStageSnapshot
from app.models.team import Team
from app.schemas.opportunity import LicenseTypeEnum, OpportunityCreate, PurchaseTypeEnum


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _create_tables(engine) -> None:
    tables = [
        Customer.__table__,
        Team.__table__,
        Opportunity.__table__,
        OpportunityStageSnapshot.__table__,
    ]
    previous_indexes: dict[str, object] = {}
    for table in tables:
        with engine.begin() as connection:
            for index in table.indexes:
                previous = previous_indexes.get(index.name)
                if previous is not None:
                    connection.execute(DropIndex(previous))
            table.create(connection)
        previous_indexes.update((index.name, index) for index in table.indexes)


@pytest.fixture
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'opportunity-create.db'}")

    @event.listens_for(engine, "connect")
    def _sqlite_foreign_keys_off(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=OFF")

    _create_tables(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    session.add(Team(id=1, name="测试团队", code="OPP21", owner_id=1))
    session.add(
        Customer(
            id=1,
            team_id=1,
            account_name="浙商证券股份有限公司",
            city="杭州",
            creator_id="u1",
            default_procurement_method_id=9,
        )
    )
    session.add(
        Customer(
            id=2,
            team_id=2,
            account_name="其他团队客户",
            city="上海",
            creator_id="u2",
            default_procurement_method_id=4,
        )
    )
    session.add(
        Customer(
            id=3,
            team_id=1,
            account_name="没有默认采购方式",
            city="杭州",
            creator_id="u1",
            default_procurement_method_id=None,
        )
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _install_downstream(monkeypatch) -> None:
    from app.crud.procurement import procurement_stage_template_crud
    from app.services.deal_journey_service import deal_journey_service

    def get_default_stage(db, procurement_method_id, team_id=None):
        return SimpleNamespace(
            id=7,
            procurement_method_id=procurement_method_id,
            win_probability=20,
            stage_name="需求确认",
            sort_order=1,
            template_code="START",
            version=1,
        )

    monkeypatch.setattr(procurement_stage_template_crud, "get_default_stage", get_default_stage)
    monkeypatch.setattr(deal_journey_service, "record_opportunity_created", lambda *args, **kwargs: None)
    monkeypatch.setattr(deal_journey_service, "record_opportunity_stage_changed", lambda *args, **kwargs: None)

    def assign_product(db, opportunity, **kwargs):
        return opportunity

    monkeypatch.setattr(opportunity_crud, "assign_product", assign_product)


def _payload(**overrides) -> OpportunityCreate:
    data = {
        "customer_id": "cus_1",
        "total_amount": 160000,
        "user_count": 100,
        "license_type": LicenseTypeEnum.PERPETUAL,
        "purchase_type": PurchaseTypeEnum.EXPANSION,
        "expected_closing_date": date(2027, 9, 30),
        "procurement_method_id": 3,
        "product_public_id": "prd_apifox",
        "product_module_public_ids": ["prm_base"],
    }
    data.update(overrides)
    return OpportunityCreate(**data)


def test_explicit_procurement_uses_customer_name(db, monkeypatch):
    _install_downstream(monkeypatch)
    payload = _payload()
    payload.customer_id = 1

    created = opportunity_crud.create_without_commit(db, payload, "u1", 1)

    assert created.opportunity_name == "浙商证券股份有限公司-100人-买断"
    assert created.procurement_method_id == 3
    assert created.customer_id == 1
    assert created.team_id == 1


def test_missing_procurement_uses_customer_default(db, monkeypatch):
    _install_downstream(monkeypatch)
    payload = _payload(procurement_method_id=None)
    payload.customer_id = 1

    created = opportunity_crud.create_without_commit(db, payload, "u1", 1)

    assert created.procurement_method_id == 9
    assert created.opportunity_name == "浙商证券股份有限公司-100人-买断"


def test_other_team_customer_is_not_visible(db, monkeypatch):
    _install_downstream(monkeypatch)
    payload = _payload()
    payload.customer_id = 2

    with pytest.raises(ValueError, match="客户不存在"):
        opportunity_crud.create_without_commit(db, payload, "u1", 1)


def test_missing_customer_is_value_error(db, monkeypatch):
    _install_downstream(monkeypatch)
    payload = _payload()
    payload.customer_id = 999

    with pytest.raises(ValueError, match="客户不存在"):
        opportunity_crud.create_without_commit(db, payload, "u1", 1)


def test_no_procurement_and_no_default_keeps_business_error(db, monkeypatch):
    _install_downstream(monkeypatch)
    payload = _payload(procurement_method_id=None)
    payload.customer_id = 3

    with pytest.raises(ValueError, match="未指定采购方式"):
        opportunity_crud.create_without_commit(db, payload, "u1", 1)

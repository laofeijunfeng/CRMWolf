from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.core.list_query import FilterCondition
from app.crud.customer import customer_crud
from app.crud.lead import lead_crud
from app.models.customer import Customer, CustomerStatus
from app.models.lead import Lead, LeadSource, LeadStatus


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


def _session(*tables):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=list(tables))
    return engine, sessionmaker(bind=engine)()


def test_leads_unified_status_filter_wins_over_conflicting_legacy_status():
    engine, db = _session(Lead.__table__)
    try:
        db.add_all(
            [
                Lead(
                    team_id=1,
                    lead_name="旧协议命中",
                    source=LeadSource.WEBSITE_INQUIRY,
                    city="上海",
                    contact_name="甲",
                    contact_phone="13800138001",
                    owner_id="1",
                    creator_id="1",
                    status=LeadStatus.NEW,
                ),
                Lead(
                    team_id=1,
                    lead_name="统一协议命中",
                    source=LeadSource.WEBSITE_INQUIRY,
                    city="北京",
                    contact_name="乙",
                    contact_phone="13800138002",
                    owner_id="1",
                    creator_id="1",
                    status=LeadStatus.FOLLOWING,
                ),
            ]
        )
        db.commit()

        leads, total = lead_crud.get_multi(
            db,
            team_id=1,
            status=LeadStatus.NEW,
            filters=[FilterCondition(field="status", op="in", value=[LeadStatus.FOLLOWING.value])],
            sorts=[],
        )

        assert total == 1
        assert [lead.lead_name for lead in leads] == ["统一协议命中"]
    finally:
        db.close()
        engine.dispose()


def test_customers_unified_status_filter_wins_over_conflicting_legacy_status():
    engine, db = _session(Customer.__table__)
    try:
        db.add_all(
            [
                Customer(
                    team_id=1,
                    account_name="旧协议命中",
                    city="上海",
                    status=CustomerStatus.FOLLOWING.value,
                    owner_id="1",
                    creator_id="1",
                ),
                Customer(
                    team_id=1,
                    account_name="统一协议命中",
                    city="北京",
                    status=CustomerStatus.WON.value,
                    owner_id="1",
                    creator_id="1",
                ),
            ]
        )
        db.commit()

        customers, total = customer_crud.get_multi(
            db,
            team_id=1,
            status=str(CustomerStatus.FOLLOWING.value),
            filters=[FilterCondition(field="status", op="in", value=[CustomerStatus.WON.value])],
            sorts=[],
        )

        assert total == 1
        assert [customer.account_name for customer in customers] == ["统一协议命中"]
    finally:
        db.close()
        engine.dispose()


def test_public_customers_unified_status_filter_wins_over_conflicting_legacy_status():
    engine, db = _session(Customer.__table__)
    try:
        db.add_all(
            [
                Customer(
                    team_id=1,
                    account_name="旧协议命中",
                    city="上海",
                    status=CustomerStatus.FOLLOWING.value,
                    owner_id=None,
                    creator_id="1",
                ),
                Customer(
                    team_id=1,
                    account_name="统一协议命中",
                    city="北京",
                    status=CustomerStatus.WON.value,
                    owner_id=None,
                    creator_id="1",
                ),
            ]
        )
        db.commit()

        customers, total = customer_crud.get_public_customers(
            db,
            team_id=1,
            status=CustomerStatus.FOLLOWING.value,
            filters=[FilterCondition(field="status", op="in", value=[CustomerStatus.WON.value])],
            sorts=[],
        )

        assert total == 1
        assert [customer.account_name for customer in customers] == ["统一协议命中"]
    finally:
        db.close()
        engine.dispose()

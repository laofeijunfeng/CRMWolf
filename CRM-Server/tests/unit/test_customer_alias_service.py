"""Shared customer alias vocabulary used by Agent identity resolution."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.customer import Customer
from app.models.customer_fact import CustomerFact, CustomerFactStatus
from app.services.customer_alias_service import CustomerAliasService


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def test_list_aliases_for_customer_combines_generated_and_approved_facts() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[Customer.__table__, CustomerFact.__table__])
    db = sessionmaker(bind=engine)()
    try:
        customer = Customer(
            public_id="cus_11111111111111111111111111111111",
            team_id=1,
            account_name="广州凡亚信息科技有限公司",
            city="深圳",
            creator_id="2",
        )
        db.add(customer)
        db.flush()
        db.add(
            CustomerFact(
                fact_key="alias-test-1",
                tenant_id=1,
                team_id=1,
                customer_id=customer.id,
                fact_type="alias",
                subject="凡亚信息",
                content="凡亚",
                confidence=0.99,
                status=CustomerFactStatus.ACTIVE,
                occurred_at=datetime(2026, 8, 27, 10, 0),
                extracted_at=datetime(2026, 8, 27, 10, 0),
                created_time=datetime(2026, 8, 27, 10, 0),
                updated_time=datetime(2026, 8, 27, 10, 0),
            )
        )
        db.commit()

        aliases = CustomerAliasService().list_aliases_for_customer(
            db,
            team_id=1,
            customer_id=int(customer.id),
            account_name=customer.account_name,
        )

        assert "凡亚信息" in aliases
        assert "凡亚" in aliases
        assert "广州凡亚信息科技有限公司" in aliases
    finally:
        db.close()
        engine.dispose()

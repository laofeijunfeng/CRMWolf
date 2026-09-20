"""Customer deal-journey read API contract tests."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import customer_deal_journeys as journeys_api
from app.constants.approval_phase import ApprovalPhase
from app.core import database, deps
from app.core.database import Base
from app.models.contract import Contract
from app.models.customer import Contact, Customer
from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent, DealJourneyStatus
from app.models.invoice import InvoiceApplication, InvoiceTitle
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan, PaymentRecord
from app.models.product import Product
from app.models.user import User, UserStatus


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture()
def api_env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        User.__table__,
        Customer.__table__,
        Contact.__table__,
        Product.__table__,
        Opportunity.__table__,
        CustomerDealJourney.__table__,
        CustomerDealJourneyEvent.__table__,
        Contract.__table__,
        PaymentPlan.__table__,
        PaymentRecord.__table__,
        InvoiceTitle.__table__,
        InvoiceApplication.__table__,
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
    current_user = SimpleNamespace(id=1, name="销售张", status="active")
    db.add(User(id=1, email="sales@example.com", name="销售张", status=UserStatus.ACTIVE))
    customer = Customer(
        team_id=1,
        account_name="客户A",
        city="上海",
        owner_id="1",
        creator_id="1",
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    def _check_view(customer_id, team_id, current_user, db):
        found = db.query(Customer).filter(Customer.public_id == customer_id, Customer.team_id == team_id).first()
        if found is None:
            raise HTTPException(status_code=404, detail="客户不存在")
        return found

    monkeypatch.setattr(journeys_api, "check_customer_view_permission", _check_view)

    app = FastAPI()
    app.include_router(journeys_api.router)
    app.dependency_overrides[database.get_db] = lambda: db
    app.dependency_overrides[deps.get_db] = lambda: db
    app.dependency_overrides[journeys_api.get_db] = lambda: db
    app.dependency_overrides[deps.get_current_user_team] = lambda: 1
    app.dependency_overrides[journeys_api.get_current_user_team] = lambda: 1
    app.dependency_overrides[deps.get_current_active_user] = lambda: current_user
    app.dependency_overrides[journeys_api.get_current_active_user] = lambda: current_user

    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=db, customer=customer, current_user=current_user)

    db.close()
    engine.dispose()


def seed_customer(env, *, suffix: str) -> Customer:
    customer = Customer(
        team_id=1,
        account_name=f"客户{suffix}",
        city="上海",
        owner_id="1",
        creator_id="1",
    )
    env.db.add(customer)
    env.db.commit()
    env.db.refresh(customer)
    return customer


def seed_journey(
    env,
    customer: Customer,
    *,
    suffix: str,
    status: str = DealJourneyStatus.ACTIVE,
    approval_phase: str = ApprovalPhase.DRAFT.value,
    win_probability: int = 20,
    last_event_at: datetime | None = None,
    actual_amount: Decimal | None = None,
) -> CustomerDealJourney:
    created_time = datetime(2026, 3, 1, 10, 0, 0)
    opportunity = Opportunity(
        team_id=1,
        opportunity_number=f"OPP-{suffix}",
        opportunity_name=f"商机{suffix}",
        customer_id=customer.id,
        total_amount=Decimal("10000"),
        actual_amount=actual_amount,
        user_count=10,
        unit_price=Decimal("1000"),
        license_type="SUBSCRIPTION",
        subscription_years=1,
        purchase_type="NEW",
        expected_closing_date=date(2026, 6, 30),
        owner_id="1",
        creator_id="1",
        approval_phase=approval_phase,
        created_time=created_time,
        win_probability=win_probability,
    )
    env.db.add(opportunity)
    env.db.flush()

    journey = CustomerDealJourney(
        team_id=1,
        customer_id=customer.id,
        primary_opportunity_id=opportunity.id,
        name=f"旅程{suffix}",
        status=status,
        started_at=created_time,
        last_event_at=last_event_at or created_time,
    )
    env.db.add(journey)
    env.db.flush()
    opportunity.deal_journey_id = journey.id
    env.db.commit()
    env.db.refresh(journey)
    return journey


def test_list_includes_unapproved_opportunity_journey(api_env):
    journey = seed_journey(
        api_env,
        api_env.customer,
        suffix="draft",
        approval_phase=ApprovalPhase.DRAFT.value,
        win_probability=20,
    )

    response = api_env.client.get(f"/v1/customers/{api_env.customer.public_id}/deal-journeys")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"].startswith("djy_")
    assert body[0]["id"] == journey.public_id
    assert body[0]["public_id"] == journey.public_id
    assert body[0]["current_board_stage"] == "early_communication"
    assert body[0]["amount"] == 10000.0


def test_customer_journey_amount_preserves_total_amount_contract(api_env):
    seed_journey(
        api_env,
        api_env.customer,
        suffix="actual",
        actual_amount=Decimal("7500"),
    )

    response = api_env.client.get(f"/v1/customers/{api_env.customer.public_id}/deal-journeys")

    assert response.status_code == 200
    assert response.json()[0]["amount"] == 10000.0


def test_list_excludes_archived(api_env):
    active = seed_journey(api_env, api_env.customer, suffix="active")
    seed_journey(api_env, api_env.customer, suffix="archived", status=DealJourneyStatus.ARCHIVED)

    response = api_env.client.get(f"/v1/customers/{api_env.customer.public_id}/deal-journeys")

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert ids == {active.public_id}


def test_detail_404_for_internal_id_and_wrong_prefix(api_env):
    cus = api_env.customer.public_id
    response = api_env.client.get(f"/v1/customers/{cus}/deal-journeys/12")
    assert response.status_code == 404
    assert response.json()["detail"] == "业务旅程不存在"
    response = api_env.client.get(f"/v1/customers/{cus}/deal-journeys/opp_{'a' * 32}")
    assert response.status_code == 404
    assert response.json()["detail"] == "业务旅程不存在"


def test_detail_404_for_other_customer_journey(api_env):
    other = seed_customer(api_env, suffix="B")
    foreign = seed_journey(api_env, other, suffix="foreign")

    response = api_env.client.get(
        f"/v1/customers/{api_env.customer.public_id}/deal-journeys/{foreign.public_id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "业务旅程不存在"


def test_list_forbidden_without_view_permission(api_env, monkeypatch):
    def _forbid(*args, **kwargs):
        raise HTTPException(status_code=403, detail="缺少权限: customer:view:own 或 customer:view:all")

    monkeypatch.setattr(journeys_api, "check_customer_view_permission", _forbid)

    response = api_env.client.get(f"/v1/customers/{api_env.customer.public_id}/deal-journeys")

    assert response.status_code == 403

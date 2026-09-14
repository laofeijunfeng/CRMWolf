"""Business journey board opportunity date filter contract tests."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import business_journey_board as board_api
from app.constants.approval_phase import ApprovalPhase
from app.core import database, deps
from app.core.database import Base
from app.models.contract import Contract
from app.models.customer import Contact, Customer
from app.models.deal_journey import (
    CustomerDealJourney,
    CustomerDealJourneyEvent,
    DealJourneyEventType,
    DealJourneyStatus,
)
from app.models.invoice import InvoiceApplication, InvoiceTitle
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan, PaymentRecord
from app.models.user import User, UserStatus


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
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
    db.commit()

    monkeypatch.setattr(
        "app.api.business_journey_board.permission_crud.get_user_permissions",
        lambda _db, _user_id, team_id=None: [SimpleNamespace(code="sales_dashboard:view:all")],
    )

    app = FastAPI()
    app.include_router(board_api.router)
    app.dependency_overrides[database.get_db] = lambda: db
    app.dependency_overrides[deps.get_db] = lambda: db
    app.dependency_overrides[board_api.get_db] = lambda: db
    app.dependency_overrides[deps.get_current_user_team] = lambda: 1
    app.dependency_overrides[board_api.get_current_user_team] = lambda: 1
    app.dependency_overrides[deps.get_current_active_user] = lambda: current_user
    app.dependency_overrides[board_api.get_current_active_user] = lambda: current_user

    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=db)

    db.close()
    engine.dispose()


def _journey_ids(body: dict) -> set[int]:
    return {
        card["journey_id"]
        for column in body["columns"]
        for card in column["cards"]
    }


def seed_board_card(
    env,
    *,
    suffix: str,
    created_time: datetime,
    expected_closing_date: date,
    last_event_at: datetime,
) -> CustomerDealJourney:
    customer = Customer(
        team_id=1,
        account_name=f"客户{suffix}",
        city="上海",
        owner_id="1",
        creator_id="1",
    )
    env.db.add(customer)
    env.db.flush()

    opportunity = Opportunity(
        team_id=1,
        opportunity_number=f"OPP-{suffix}",
        opportunity_name=f"商机{suffix}",
        customer_id=customer.id,
        total_amount=Decimal("10000"),
        user_count=10,
        unit_price=Decimal("1000"),
        license_type="SUBSCRIPTION",
        subscription_years=1,
        purchase_type="NEW",
        expected_closing_date=expected_closing_date,
        owner_id="1",
        creator_id="1",
        approval_phase=ApprovalPhase.APPROVED.value,
        created_time=created_time,
        win_probability=20,
    )
    env.db.add(opportunity)
    env.db.flush()

    journey = CustomerDealJourney(
        team_id=1,
        customer_id=customer.id,
        primary_opportunity_id=opportunity.id,
        name=f"旅程{suffix}",
        status=DealJourneyStatus.ACTIVE,
        started_at=created_time,
        last_event_at=last_event_at,
    )
    env.db.add(journey)
    env.db.flush()

    opportunity.deal_journey_id = journey.id
    env.db.add(
        CustomerDealJourneyEvent(
            team_id=1,
            deal_journey_id=journey.id,
            customer_id=customer.id,
            event_type=DealJourneyEventType.OPPORTUNITY_APPROVED,
            event_time=last_event_at,
            source_type="opportunity",
            source_id=opportunity.id,
            actor_id="1",
            summary="商机审批通过",
        )
    )
    env.db.commit()
    return journey


def seed_three_cards(env):
    march = seed_board_card(
        env,
        suffix="A",
        created_time=datetime(2026, 3, 15, 10, 0, 0),
        expected_closing_date=date(2026, 9, 30),
        last_event_at=datetime(2026, 8, 1, 9, 0, 0),
    )
    april = seed_board_card(
        env,
        suffix="B",
        created_time=datetime(2026, 4, 15, 10, 0, 0),
        expected_closing_date=date(2026, 10, 15),
        last_event_at=datetime(2026, 8, 15, 9, 0, 0),
    )
    march_early_close = seed_board_card(
        env,
        suffix="C",
        created_time=datetime(2026, 3, 20, 10, 0, 0),
        expected_closing_date=date(2026, 9, 10),
        last_event_at=datetime(2026, 7, 1, 9, 0, 0),
    )
    return march, april, march_early_close


def test_created_time_range_includes_only_matching_opportunities(api_env):
    march, april, march_early_close = seed_three_cards(api_env)

    response = api_env.client.get(
        "/v1/business-journey-board/",
        params={"created_time_start": "2026-03-01", "created_time_end": "2026-03-31"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert _journey_ids(body) == {march.id, march_early_close.id}
    assert april.id not in _journey_ids(body)
    assert body["period_start"] is None
    assert body["period_end"] is None


def test_created_time_start_only_is_inclusive_lower_bound(api_env):
    march, april, march_early_close = seed_three_cards(api_env)

    response = api_env.client.get(
        "/v1/business-journey-board/",
        params={"created_time_start": "2026-04-01"},
    )

    assert response.status_code == 200, response.text
    assert _journey_ids(response.json()) == {april.id}
    assert march.id not in _journey_ids(response.json())
    assert march_early_close.id not in _journey_ids(response.json())


def test_expected_closing_date_range_is_inclusive_on_both_ends(api_env):
    march, april, march_early_close = seed_three_cards(api_env)

    response = api_env.client.get(
        "/v1/business-journey-board/",
        params={
            "expected_closing_date_start": "2026-09-10",
            "expected_closing_date_end": "2026-09-30",
        },
    )

    assert response.status_code == 200, response.text
    assert _journey_ids(response.json()) == {march.id, march_early_close.id}
    assert april.id not in _journey_ids(response.json())


def test_created_time_and_expected_closing_date_are_anded(api_env):
    march, april, march_early_close = seed_three_cards(api_env)

    response = api_env.client.get(
        "/v1/business-journey-board/",
        params={
            "created_time_start": "2026-03-01",
            "created_time_end": "2026-03-31",
            "expected_closing_date_start": "2026-09-20",
            "expected_closing_date_end": "2026-09-30",
        },
    )

    assert response.status_code == 200, response.text
    assert _journey_ids(response.json()) == {march.id}
    assert april.id not in _journey_ids(response.json())
    assert march_early_close.id not in _journey_ids(response.json())


def test_opportunity_dates_and_last_event_at_are_anded(api_env):
    march, april, march_early_close = seed_three_cards(api_env)

    response = api_env.client.get(
        "/v1/business-journey-board/",
        params={
            "created_time_start": "2026-03-01",
            "created_time_end": "2026-03-31",
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert _journey_ids(body) == {march.id}
    assert april.id not in _journey_ids(body)
    assert march_early_close.id not in _journey_ids(body)
    assert body["period_start"] == "2026-08-01"
    assert body["period_end"] == "2026-08-31"


def test_created_time_start_after_end_returns_400(api_env):
    response = api_env.client.get(
        "/v1/business-journey-board/",
        params={"created_time_start": "2026-04-01", "created_time_end": "2026-03-01"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "开始日期不能晚于结束日期"


def test_expected_closing_date_start_after_end_returns_400(api_env):
    response = api_env.client.get(
        "/v1/business-journey-board/",
        params={
            "expected_closing_date_start": "2026-10-01",
            "expected_closing_date_end": "2026-09-01",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "开始日期不能晚于结束日期"

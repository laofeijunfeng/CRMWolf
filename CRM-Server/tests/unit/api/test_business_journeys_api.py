"""Unified business-journey API contract tests."""
from __future__ import annotations

import json
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

from app import main as app_main
from app.constants.approval_phase import ApprovalPhase
from app.core import database, deps
from app.core.database import Base
from app.crud.permission import permission_crud
from app.models.contract import Contract
from app.models.customer import Contact, Customer, CustomerMember
from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent, DealJourneyStatus
from app.models.invoice import InvoiceApplication, InvoiceTitle
from app.models.opportunity import Opportunity, OpportunityProductModule
from app.models.payment import PaymentPlan, PaymentRecord
from app.models.product import Product, ProductModule
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
        CustomerMember.__table__,
        Product.__table__,
        Opportunity.__table__,
        ProductModule.__table__,
        OpportunityProductModule.__table__,
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
    db.add_all(
        [
            User(id=1, email="sales@example.com", name="销售张", status=UserStatus.ACTIVE),
            User(id=2, email="other@example.com", name="销售李", status=UserStatus.ACTIVE),
        ]
    )
    db.commit()

    env = SimpleNamespace(
        db=db,
        current_user=current_user,
        permissions=["customer:view:all"],
        seed_index=0,
    )

    def _permission_stub(_db, _user_id, team_id=None):  # noqa: ARG001
        return [SimpleNamespace(code=code) for code in env.permissions]

    monkeypatch.setattr(permission_crud, "get_user_permissions", _permission_stub)

    app = FastAPI()
    app.include_router(app_main.api_router)
    app.dependency_overrides[database.get_db] = lambda: db
    app.dependency_overrides[deps.get_db] = lambda: db
    app.dependency_overrides[deps.get_current_user_team] = lambda: 1
    app.dependency_overrides[deps.get_current_active_user] = lambda: current_user

    with TestClient(app) as client:
        env.client = client
        yield env

    db.close()
    engine.dispose()


def seed_journey(
    env,
    *,
    customer_owner: str = "1",
    opportunity_owner: str = "1",
    product_name: str | None = None,
    approval_phase: str = ApprovalPhase.APPROVED.value,
    status: str = DealJourneyStatus.ACTIVE,
    total_amount: str = "10000",
    actual_amount: str | None = None,
    win_probability: int = 20,
    created_time: datetime | None = None,
    expected_closing_date: date | None = None,
    last_event_at: datetime | None = None,
) -> CustomerDealJourney:
    env.seed_index += 1
    suffix = str(env.seed_index)
    customer = Customer(
        team_id=1,
        account_name=f"客户{suffix}",
        city="上海",
        owner_id=customer_owner,
        creator_id="1",
    )
    env.db.add(customer)
    env.db.flush()

    product = None
    if product_name is not None:
        product = Product(
            team_id=1,
            code=f"PRODUCT-{suffix}",
            name=product_name,
            created_by="1",
        )
        env.db.add(product)
        env.db.flush()

    created_time = created_time or datetime(2026, 3, env.seed_index, 10, 0, 0)
    opportunity = Opportunity(
        team_id=1,
        opportunity_number=f"OPP-{suffix}",
        opportunity_name=f"商机{suffix}",
        customer_id=customer.id,
        product_id=product.id if product is not None else None,
        total_amount=Decimal(total_amount),
        actual_amount=Decimal(actual_amount) if actual_amount is not None else None,
        user_count=10,
        unit_price=Decimal("1000"),
        license_type="SUBSCRIPTION",
        subscription_years=1,
        purchase_type="NEW",
        expected_closing_date=expected_closing_date or date(2026, 9, env.seed_index),
        owner_id=opportunity_owner,
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


def seed_customer_member(
    env,
    *,
    customer_id: int,
    user_id: str,
    access_level: str,
    is_active: bool = True,
) -> CustomerMember:
    member = CustomerMember(
        team_id=1,
        customer_id=customer_id,
        user_id=user_id,
        member_role="PRESALES",
        access_level=access_level,
        created_by="1",
        is_active=is_active,
    )
    env.db.add(member)
    env.db.commit()
    return member


def test_detail_returns_journey_and_full_primary_opportunity(api_env):
    journey = seed_journey(api_env, product_name="Hifox CRM")

    response = api_env.client.get(f"/v1/business-journeys/{journey.public_id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["journey"]["public_id"] == journey.public_id
    assert body["primary_opportunity"]["public_id"].startswith("opp_")
    assert body["primary_opportunity"]["deal_journey_id"] == journey.public_id
    assert body["primary_opportunity"]["customer_id"].startswith("cus_")
    assert body["primary_opportunity"]["customer_name"].startswith("客户")
    assert body["primary_opportunity"]["product_name"] == "Hifox CRM"


def test_detail_returns_null_primary_opportunity(api_env):
    journey = seed_journey(api_env)
    opportunity = api_env.db.query(Opportunity).filter(Opportunity.id == journey.primary_opportunity_id).one()
    opportunity.deal_journey_id = None
    journey.primary_opportunity_id = None
    api_env.db.commit()

    response = api_env.client.get(f"/v1/business-journeys/{journey.public_id}")

    assert response.status_code == 200, response.text
    assert response.json()["journey"]["public_id"] == journey.public_id
    assert response.json()["journey"]["primary_opportunity"] is None
    assert response.json()["primary_opportunity"] is None


def test_detail_requires_public_journey_id(api_env):
    journey = seed_journey(api_env)

    response = api_env.client.get(f"/v1/business-journeys/{journey.id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "业务旅程不存在"


def _journey_public_ids(body: dict) -> set[str]:
    return {
        card["public_id"]
        for column in body["columns"]
        for card in column["cards"]
    }


def test_unapproved_primary_opportunity_appears_in_list_and_board(api_env):
    journey = seed_journey(
        api_env,
        approval_phase=ApprovalPhase.DRAFT.value,
        win_probability=20,
    )

    list_response = api_env.client.get("/v1/business-journeys")
    board_response = api_env.client.get("/v1/business-journeys/board")

    assert list_response.status_code == 200, list_response.text
    assert board_response.status_code == 200, board_response.text
    assert list_response.json()["items"][0]["public_id"] == journey.public_id
    assert list_response.json()["items"][0]["current_board_stage"] == "early_communication"
    card = next(card for column in board_response.json()["columns"] for card in column["cards"])
    assert card["public_id"] == journey.public_id
    assert card["current_board_stage"] == "early_communication"


def test_board_and_list_share_filtered_ids(api_env):
    seed_journey(api_env, product_name="Hifox")
    seed_journey(api_env, product_name="Apifox")
    params = {"filters": json.dumps([{"field": "product_name", "op": "eq", "value": "Hifox"}])}

    list_response = api_env.client.get("/v1/business-journeys", params=params)
    board_response = api_env.client.get("/v1/business-journeys/board", params=params)

    assert list_response.status_code == 200, list_response.text
    assert board_response.status_code == 200, board_response.text
    list_body = list_response.json()
    board_body = board_response.json()
    assert _journey_public_ids(board_body) == {item["public_id"] for item in list_body["items"]}
    assert board_body["summary"]["total_count"] == list_body["total"]


def test_board_uses_public_ids_and_unified_opportunity_amount(api_env):
    journey = seed_journey(api_env, total_amount="10000", actual_amount="7500")

    list_body = api_env.client.get("/v1/business-journeys").json()
    board_body = api_env.client.get("/v1/business-journeys/board").json()
    card = next(card for column in board_body["columns"] for card in column["cards"])

    assert card["public_id"] == journey.public_id
    assert "journey_id" not in card
    assert card["customer_id"].startswith("cus_")
    assert card["primary_opportunity"]["public_id"].startswith("opp_")
    assert card["amount"] == 7500.0
    assert list_body["items"][0]["amount"] == 7500.0


def test_owner_options_contain_only_owners_present_in_visible_rows(api_env):
    seed_journey(api_env, customer_owner="1", opportunity_owner="1")
    seed_journey(api_env, customer_owner="2", opportunity_owner="2")
    api_env.permissions = ["customer:view:own", "opportunity:view:own"]

    response = api_env.client.get("/v1/business-journeys/owner-options")

    assert response.status_code == 200, response.text
    assert [owner["id"] for owner in response.json()["data"]] == ["1"]


def test_invalid_tab_returns_422(api_env):
    response = api_env.client.get("/v1/business-journeys", params={"tab": "unknown"})

    assert response.status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {"filters": json.dumps([{"field": "unknown", "op": "eq", "value": "x"}])},
        {"sorts": json.dumps([{"field": "unknown", "direction": "asc"}])},
    ],
)
def test_unknown_filter_or_sort_field_returns_400(api_env, params):
    response = api_env.client.get("/v1/business-journeys", params=params)

    assert response.status_code == 400


def test_list_pagination_uses_skip_based_page_formula(api_env):
    for _ in range(5):
        seed_journey(api_env)

    response = api_env.client.get("/v1/business-journeys", params={"skip": 2, "limit": 2})

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 5
    assert response.json()["page"] == 2
    assert response.json()["page_size"] == 2
    assert response.json()["total_pages"] == 3


def test_board_limit_reports_untruncated_total(api_env):
    for _ in range(3):
        seed_journey(api_env)

    response = api_env.client.get("/v1/business-journeys/board", params={"limit": 1})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["total_count"] == 3
    assert body["truncated"] is True
    assert sum(len(column["cards"]) for column in body["columns"]) == 1


def seed_three_date_cards(api_env):
    march = seed_journey(
        api_env,
        created_time=datetime(2026, 3, 15, 10, 0, 0),
        expected_closing_date=date(2026, 9, 30),
        last_event_at=datetime(2026, 8, 1, 9, 0, 0),
    )
    april = seed_journey(
        api_env,
        created_time=datetime(2026, 4, 15, 10, 0, 0),
        expected_closing_date=date(2026, 10, 15),
        last_event_at=datetime(2026, 8, 15, 9, 0, 0),
    )
    march_early_close = seed_journey(
        api_env,
        created_time=datetime(2026, 3, 20, 10, 0, 0),
        expected_closing_date=date(2026, 9, 10),
        last_event_at=datetime(2026, 7, 1, 9, 0, 0),
    )
    return march, april, march_early_close


def test_board_created_time_range_includes_both_boundary_days(api_env):
    march, april, march_early_close = seed_three_date_cards(api_env)
    params = {
        "filters": json.dumps(
            [
                {"field": "created_time", "op": "after", "value": "2026-03-01"},
                {"field": "created_time", "op": "before", "value": "2026-03-31"},
            ]
        )
    }

    response = api_env.client.get("/v1/business-journeys/board", params=params)

    assert response.status_code == 200, response.text
    assert _journey_public_ids(response.json()) == {march.public_id, march_early_close.public_id}
    assert april.public_id not in _journey_public_ids(response.json())


def test_board_expected_closing_date_range_is_inclusive(api_env):
    march, april, march_early_close = seed_three_date_cards(api_env)
    params = {
        "filters": json.dumps(
            [
                {"field": "expected_closing_date", "op": "after", "value": "2026-09-10"},
                {"field": "expected_closing_date", "op": "before", "value": "2026-09-30"},
            ]
        )
    }

    response = api_env.client.get("/v1/business-journeys/board", params=params)

    assert response.status_code == 200, response.text
    assert _journey_public_ids(response.json()) == {march.public_id, march_early_close.public_id}
    assert april.public_id not in _journey_public_ids(response.json())


def test_board_opportunity_dates_and_last_event_date_are_anded(api_env):
    march, april, march_early_close = seed_three_date_cards(api_env)
    params = {
        "filters": json.dumps(
            [
                {"field": "created_time", "op": "after", "value": "2026-03-01"},
                {"field": "created_time", "op": "before", "value": "2026-03-31"},
                {"field": "last_event_at", "op": "after", "value": "2026-08-01"},
                {"field": "last_event_at", "op": "before", "value": "2026-08-31"},
            ]
        )
    }

    response = api_env.client.get("/v1/business-journeys/board", params=params)

    assert response.status_code == 200, response.text
    assert _journey_public_ids(response.json()) == {march.public_id}
    assert april.public_id not in _journey_public_ids(response.json())
    assert march_early_close.public_id not in _journey_public_ids(response.json())

"""A failed payment-plan journey event must not expose any part of the source write."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal, engine
from app.crud.payment import payment_plan_crud
from app.models.contract import Contract, ContractStatus
from app.models.customer import Contact, Customer
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent
from app.models.operation_log import OperationLog
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan
from app.models.team import Team
from app.schemas.payment import PaymentPlanCreate
from app.services.deal_journey_service import deal_journey_service
from app.utils.time import business_now

pytestmark = pytest.mark.integration


def _isolated_mysql() -> bool:
    url = engine.url
    return (
        os.getenv("RUN_MYSQL_INTEGRATION") == "1"
        and url.drivername == "mysql+pymysql"
        and url.username == "root"
        and url.password == "assistant-test-only"
        and url.host == "127.0.0.1"
        and url.port == 3308
        and url.database == "crm_assistant_acceptance"
    )


@pytest.mark.skipif(not _isolated_mysql(), reason="requires isolated acceptance MySQL")
@pytest.mark.parametrize("batch", [False, True], ids=["single", "batch"])
def test_record_event_failure_rolls_back_payment_plans_progress_and_events(monkeypatch, batch: bool) -> None:
    suffix = uuid4().hex
    with SessionLocal() as seed:
        team = Team(name=f"PAYMENT_ATOMIC_{suffix[:12]}", code=suffix[:12], owner_id=990126011)
        seed.add(team)
        seed.flush()
        customer = Customer(
            team_id=team.id, account_name=f"Payment atomic {suffix}", city="深圳", creator_id="990126011",
        )
        seed.add(customer)
        seed.flush()
        journey = CustomerDealJourney(team_id=team.id, customer_id=customer.id, name=f"Journey {suffix}")
        seed.add(journey)
        seed.flush()
        opportunity = Opportunity(
            team_id=team.id, opportunity_number=f"OPP{suffix}", opportunity_name=f"Opportunity {suffix}",
            customer_id=customer.id, deal_journey_id=journey.id, total_amount=Decimal("300.00"),
            user_count=1, unit_price=Decimal("300.00"), license_type="PERPETUAL", purchase_type="NEW",
            expected_closing_date=date(2026, 12, 31), owner_id="990126011", creator_id="990126011",
        )
        seed.add(opportunity)
        seed.flush()
        signing_contact = Contact(
            team_id=team.id, customer_id=customer.id, name=f"Signing contact {suffix}", mobile="13800000000",
        )
        seed.add(signing_contact)
        seed.flush()
        contract = Contract(
            team_id=team.id, contract_number=f"CT{suffix}", contract_name=f"Contract {suffix}",
            customer_id=customer.id, opportunity_id=opportunity.id, deal_journey_id=journey.id,
            signing_contact_id=signing_contact.id,
            user_count=1, total_amount=Decimal("300.00"), license_type="PERPETUAL",
            standard_unit_price=Decimal("300.00"), status=ContractStatus.SIGNED,
            owner_id="990126011", creator_id="990126011",
        )
        seed.add(contract)
        seed.commit()
        team_id, customer_id, journey_id, contract_id = team.id, customer.id, journey.id, contract.id

    # Insert an actual event before raising. In a batch, the second event fails,
    # so the first event must roll back along with both plans and their progress.
    calls = 0
    failure_at = 2 if batch else 1

    def record_event_then_fail(db, **kwargs):
        nonlocal calls
        calls += 1
        db.add(CustomerDealJourneyEvent(
            team_id=kwargs["team_id"], customer_id=kwargs["customer_id"],
            deal_journey_id=kwargs["deal_journey_id"], event_type=kwargs["event_type"],
            source_type=kwargs["source_type"], source_id=kwargs["source_id"],
            event_time=business_now(),
        ))
        db.flush()
        if calls == failure_at:
            raise RuntimeError("injected journey event failure")

    monkeypatch.setattr(deal_journey_service, "record_event", record_event_then_fail)
    monkeypatch.setattr(
        "app.crud.payment.BusinessNumberGenerator.generate",
        lambda prefix, db: f"{prefix}{uuid4().hex}",
    )
    plans = [
        PaymentPlanCreate(stage_name=f"Stage {suffix}-{n}", planned_amount=100, due_date=date(2026, 12, 31))
        for n in range(failure_at)
    ]

    try:
        with SessionLocal() as writer:
            with pytest.raises(RuntimeError, match="injected journey event failure"):
                if batch:
                    payment_plan_crud.batch_create(writer, contract_id, plans, "990126011", team_id)
                else:
                    payment_plan_crud.create(writer, contract_id, plans[0], team_id)
            writer.rollback()  # The API dependency closes (rolls back) on failure.

        with SessionLocal() as reader:
            assert reader.query(PaymentPlan).filter_by(team_id=team_id, contract_id=contract_id).count() == 0
            assert reader.query(CustomerLegacySourceProgress).filter_by(
                team_id=team_id, customer_id=customer_id,
            ).count() == 0
            assert reader.query(CustomerDealJourneyEvent).filter_by(
                team_id=team_id, customer_id=customer_id, deal_journey_id=journey_id,
            ).count() == 0
            assert reader.query(OperationLog).filter_by(team_id=team_id).count() == 0
            assert calls == failure_at
    finally:
        # Delete only this test's uniquely named source chain; never touch shared acceptance fixtures.
        with SessionLocal() as cleanup:
            params = {"team": team_id, "customer": customer_id, "journey": journey_id, "contract": contract_id}
            cleanup.execute(text("DELETE FROM crm_operation_logs WHERE team_id=:team"), params)
            cleanup.execute(text("DELETE FROM crm_customer_deal_journey_events WHERE deal_journey_id=:journey AND team_id=:team"), params)
            cleanup.execute(text("DELETE FROM crm_customer_legacy_source_progress WHERE customer_id=:customer AND team_id=:team"), params)
            cleanup.execute(text("DELETE FROM crm_contract_payment_plans WHERE contract_id=:contract AND team_id=:team"), params)
            cleanup.execute(text("DELETE FROM crm_contracts WHERE id=:contract AND team_id=:team"), params)
            cleanup.execute(text("DELETE FROM crm_opportunities WHERE customer_id=:customer AND team_id=:team"), params)
            cleanup.execute(text("DELETE FROM crm_customer_deal_journeys WHERE id=:journey AND team_id=:team"), params)
            cleanup.execute(text("DELETE FROM crm_contacts WHERE customer_id=:customer AND team_id=:team"), params)
            cleanup.execute(text("DELETE FROM crm_customers WHERE id=:customer AND team_id=:team"), params)
            cleanup.execute(text("DELETE FROM teams WHERE id=:team"), params)
            cleanup.commit()

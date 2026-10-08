"""Customer-first locking and transaction boundaries of journey closure refresh."""

from datetime import datetime

from sqlalchemy import event

from app.models.contract import Contract, PaymentStatus
from app.models.customer import Customer
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.deal_journey import CustomerDealJourney, DealJourneyStatus
from app.models.payment import PaymentRecord
from app.services.deal_journey_service import deal_journey_service
from tests.unit.test_customer_intelligence_context_service import _seed_customer_context, _session


def test_direct_closure_refresh_locks_customer_first_without_advancing_aggregate_progress():
    engine, db = _session()
    try:
        _seed_customer_context(db)
        journey = CustomerDealJourney(
            id=994, team_id=2, customer_id=101, name="回款完成旅程", status=DealJourneyStatus.ACTIVE,
            primary_opportunity_id=301,
        )
        db.add(journey)
        db.flush()
        contract = db.query(Contract).filter_by(id=401).one()
        contract.deal_journey_id = journey.id
        contract.payment_status = PaymentStatus.COMPLETED
        confirmed = db.query(PaymentRecord).filter_by(id=601).one()
        confirmed.deal_journey_id = journey.id
        confirmed.confirmed_time = datetime(2026, 8, 20, 11)
        db.commit()
        progress = db.query(CustomerLegacySourceProgress).filter_by(team_id=2, customer_id=101).one()
        initial_revision = progress.eligible_revision
        locks = []

        @event.listens_for(db, "do_orm_execute")
        def record_locks(state):
            statement = state.statement
            if getattr(statement, "_for_update_arg", None) is not None:
                locks.append(str(statement))

        refreshed = deal_journey_service.refresh_closure_status(db, journey.id)
        assert len(locks) >= 2
        assert "crm_customers" in locks[0]
        assert "crm_customer_deal_journeys" in locks[1]
        assert refreshed.status == DealJourneyStatus.COMPLETED
        assert refreshed.closed_at == confirmed.confirmed_time
        db.flush()
        db.refresh(progress)
        assert progress.eligible_revision == initial_revision

        locks.clear()
        again = deal_journey_service.refresh_closure_status(db, journey.id)
        assert again.closed_at == confirmed.confirmed_time
        assert len(locks) >= 2
        assert "crm_customers" in locks[0]
        assert "crm_customer_deal_journeys" in locks[1]
        assert not db.is_modified(again)
        db.refresh(progress)
        assert progress.eligible_revision == initial_revision

        db.rollback()
        assert db.query(CustomerDealJourney).filter_by(id=journey.id).one().status == DealJourneyStatus.ACTIVE
        assert db.query(CustomerLegacySourceProgress).filter_by(team_id=2, customer_id=101).one().eligible_revision == initial_revision
    finally:
        db.close()
        engine.dispose()


def test_closure_refresh_ignores_another_customers_contract_on_same_journey():
    engine, db = _session()
    try:
        _seed_customer_context(db)
        db.add(Customer(id=102, team_id=2, account_name="其他客户", city="广州", creator_id="9"))
        journey = CustomerDealJourney(id=994, team_id=2, customer_id=101, name="独立旅程", status=DealJourneyStatus.ACTIVE)
        db.add(journey)
        db.flush()
        foreign_contract = db.query(Contract).filter_by(id=401).one()
        foreign_contract.customer_id = 102
        foreign_contract.deal_journey_id = journey.id
        foreign_contract.payment_status = PaymentStatus.COMPLETED
        db.commit()

        refreshed = deal_journey_service.refresh_closure_status(db, journey.id)
        assert refreshed.status == DealJourneyStatus.ACTIVE
        assert refreshed.closed_at is None
    finally:
        db.close()
        engine.dispose()

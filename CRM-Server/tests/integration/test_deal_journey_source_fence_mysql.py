"""Repeatable-read journey writes must use current rows under the customer fence."""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal, engine
from app.models.customer import Customer
from app.models.contract import Contract, PaymentStatus
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.customer_activity import CustomerActivity
from app.models.deal_journey import (
    CustomerDealJourney,
    CustomerDealJourneyEvent,
    DealJourneyEventType,
    DealJourneySourceType,
    DealJourneyStatus,
)
from app.models.opportunity import Opportunity
from app.models.team import Team
from app.services.deal_journey_service import deal_journey_service
from app.services.legacy_profile_source import advance_activity_progress, advance_eligible_progress, lock_source_customer

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


@pytest.fixture
def journey_case():
    if not _isolated_mysql():
        pytest.skip("requires isolated acceptance MySQL")
    suffix = uuid4().hex
    with SessionLocal() as seed:
        team = Team(name=f"JOURNEY_RR_{suffix[:12]}", code=suffix[:12], owner_id=990126011)
        seed.add(team)
        seed.flush()
        customer = Customer(team_id=team.id, account_name=f"Journey RR {suffix}", city="深圳", creator_id="990126011")
        seed.add(customer)
        seed.flush()
        first = CustomerDealJourney(team_id=team.id, customer_id=customer.id, name="First")
        second = CustomerDealJourney(team_id=team.id, customer_id=customer.id, name="Second")
        seed.add_all([first, second])
        seed.flush()
        opportunity = Opportunity(
            team_id=team.id, customer_id=customer.id, deal_journey_id=first.id,
            opportunity_number=f"OPP{suffix}", opportunity_name=f"Opportunity {suffix}",
            total_amount=Decimal("300.00"), user_count=1, unit_price=Decimal("300.00"),
            license_type="PERPETUAL", purchase_type="NEW", expected_closing_date=date(2026, 12, 31),
            owner_id="990126011", creator_id="990126011",
        )
        seed.add(opportunity)
        seed.flush()
        first.primary_opportunity_id = opportunity.id
        seed.commit()
        ids = (team.id, customer.id, first.id, second.id, opportunity.id)
    try:
        yield ids
    finally:
        team_id, customer_id, _, _, _ = ids
        with SessionLocal() as cleanup:
            params = {"team": team_id, "customer": customer_id}
            cleanup.execute(text("DELETE FROM crm_customer_intelligence_runs WHERE customer_id=:customer AND team_id=:team"), params)
            cleanup.execute(text("DELETE FROM crm_customer_vector_documents WHERE customer_id=:customer AND team_id=:team"), params)
            cleanup.execute(text("DELETE FROM crm_customer_deal_journey_events WHERE customer_id=:customer AND team_id=:team"), params)
            cleanup.execute(text("DELETE FROM crm_customer_legacy_source_progress WHERE customer_id=:customer AND team_id=:team"), params)
            cleanup.execute(text("DELETE FROM crm_contracts WHERE customer_id=:customer AND team_id=:team"), params)
            cleanup.execute(text("DELETE FROM crm_customer_activities WHERE customer_id=:customer AND team_id=:team"), params)
            cleanup.execute(text("DELETE FROM crm_opportunities WHERE customer_id=:customer AND team_id=:team"), params)
            cleanup.execute(text("DELETE FROM crm_customer_deal_journeys WHERE customer_id=:customer AND team_id=:team"), params)
            cleanup.execute(text("DELETE FROM crm_customers WHERE id=:customer AND team_id=:team"), params)
            cleanup.execute(text("DELETE FROM teams WHERE id=:team"), params)
            cleanup.commit()


def _progress(db, team_id: int, customer_id: int) -> int:
    row = db.query(CustomerLegacySourceProgress).filter_by(team_id=team_id, customer_id=customer_id).one_or_none()
    return int(row.eligible_revision) if row else 0


def test_stale_opportunity_and_journey_cannot_restore_old_association(journey_case) -> None:
    team_id, customer_id, first_id, second_id, opportunity_id = journey_case
    with SessionLocal() as stale, SessionLocal() as editor:
        assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
        old_opportunity = stale.query(Opportunity).filter_by(id=opportunity_id).one()
        stale.query(CustomerDealJourney).filter_by(id=first_id).one()
        current = editor.query(Opportunity).filter_by(id=opportunity_id).one()
        deal_journey_service.associate_opportunity(editor, current, deal_journey_id=second_id)
        editor.commit()
        current_revision = _progress(editor, team_id, customer_id)
        assert current_revision > 0
        assert old_opportunity.deal_journey_id == first_id

        resolved = deal_journey_service.ensure_for_opportunity(stale, old_opportunity)
        assert resolved.id == second_id
        assert old_opportunity.deal_journey_id == second_id
        stale.commit()
    with SessionLocal() as check:
        assert check.query(Opportunity).filter_by(id=opportunity_id).one().deal_journey_id == second_id
        assert _progress(check, team_id, customer_id) == current_revision
        assert check.query(CustomerDealJourneyEvent).filter_by(
            team_id=team_id, customer_id=customer_id, event_type=DealJourneyEventType.ASSOCIATION_CHANGED,
        ).count() == 2


def test_detach_uses_current_opportunity_association_after_snapshot(journey_case) -> None:
    team_id, customer_id, first_id, _, opportunity_id = journey_case
    with SessionLocal() as stale, SessionLocal() as editor:
        assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
        old_opportunity = stale.query(Opportunity).filter_by(id=opportunity_id).one()
        deal_journey_service.detach_opportunity(
            editor, editor.query(Opportunity).filter_by(id=opportunity_id).one(),
        )
        editor.commit()
        revision = _progress(editor, team_id, customer_id)
        assert revision > 0 and old_opportunity.deal_journey_id == first_id
        assert deal_journey_service.detach_opportunity(stale, old_opportunity) is None
        stale.commit()
    with SessionLocal() as check:
        assert check.query(Opportunity).filter_by(id=opportunity_id).one().deal_journey_id is None
        assert _progress(check, team_id, customer_id) == revision
        assert check.query(CustomerDealJourneyEvent).filter_by(
            team_id=team_id, customer_id=customer_id, event_type=DealJourneyEventType.ASSOCIATION_CHANGED,
        ).count() == 1


def test_stale_target_archived_after_snapshot_cannot_accept_association(journey_case) -> None:
    team_id, customer_id, first_id, second_id, opportunity_id = journey_case
    with SessionLocal() as stale, SessionLocal() as editor:
        assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
        opportunity = stale.query(Opportunity).filter_by(id=opportunity_id).one()
        target = stale.query(CustomerDealJourney).filter_by(id=second_id).one()
        assert target.status == DealJourneyStatus.ACTIVE
        lock_source_customer(editor, team_id=team_id, customer_id=customer_id)
        editor.query(CustomerDealJourney).filter_by(id=second_id).one().status = DealJourneyStatus.ARCHIVED
        advance_eligible_progress(editor, team_id=team_id, customer_id=customer_id)
        editor.commit()
        revision = _progress(editor, team_id, customer_id)

        with pytest.raises(ValueError, match="已归档"):
            deal_journey_service.associate_opportunity(stale, opportunity, deal_journey_id=second_id)
        stale.rollback()
    with SessionLocal() as check:
        assert check.query(Opportunity).filter_by(id=opportunity_id).one().deal_journey_id == first_id
        assert _progress(check, team_id, customer_id) == revision
        assert check.query(CustomerDealJourneyEvent).filter_by(team_id=team_id, customer_id=customer_id).count() == 0


def test_stale_event_snapshot_cannot_duplicate_another_committed_event(journey_case) -> None:
    team_id, customer_id, first_id, _, opportunity_id = journey_case
    event_time = datetime(2026, 9, 30, 11, 0)
    kwargs = dict(
        deal_journey_id=first_id, team_id=team_id, customer_id=customer_id,
        event_type=DealJourneyEventType.OPPORTUNITY_APPROVED,
        source_type=DealJourneySourceType.OPPORTUNITY, source_id=opportunity_id,
        event_time=event_time, summary="Original", enqueue_customer_intelligence=False,
    )
    with SessionLocal() as stale, SessionLocal() as editor:
        assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
        assert stale.query(CustomerDealJourneyEvent).filter_by(
            team_id=team_id, customer_id=customer_id,
        ).all() == []  # Starts the stale snapshot before the other writer commits.
        inserted = deal_journey_service.record_event(editor, **kwargs)
        assert inserted is not None
        editor.commit()
        revision = _progress(editor, team_id, customer_id)
        assert revision == 1
        reused = deal_journey_service.record_event(stale, **kwargs)
        assert reused is not None and reused.id == inserted.id
        stale.commit()
    with SessionLocal() as check:
        assert check.query(CustomerDealJourneyEvent).filter_by(
            team_id=team_id, customer_id=customer_id, event_type=DealJourneyEventType.OPPORTUNITY_APPROVED,
        ).count() == 1
        assert _progress(check, team_id, customer_id) == 1


def test_preloaded_event_is_reloaded_before_existing_evidence_is_reused(journey_case) -> None:
    team_id, customer_id, first_id, _, opportunity_id = journey_case
    kwargs = dict(
        deal_journey_id=first_id, team_id=team_id, customer_id=customer_id,
        event_type=DealJourneyEventType.OPPORTUNITY_APPROVED,
        source_type=DealJourneySourceType.OPPORTUNITY, source_id=opportunity_id,
        event_time=datetime(2026, 9, 30, 11, 0), summary="Original",
        enqueue_customer_intelligence=False,
    )
    with SessionLocal() as seed:
        original = deal_journey_service.record_event(seed, **kwargs)
        assert original is not None
        seed.commit()
        event_id = original.id
    with SessionLocal() as stale, SessionLocal() as editor:
        cached = stale.query(CustomerDealJourneyEvent).filter_by(id=event_id).one()
        assert cached.summary == "Original"
        lock_source_customer(editor, team_id=team_id, customer_id=customer_id)
        editor.query(CustomerDealJourneyEvent).filter_by(id=event_id).one().summary = "Corrected"
        advance_eligible_progress(editor, team_id=team_id, customer_id=customer_id)
        editor.commit()
        revision = _progress(editor, team_id, customer_id)
        reused = deal_journey_service.record_event(stale, **kwargs)
        assert reused is cached
        assert reused.summary == "Corrected"
        stale.commit()
    with SessionLocal() as check:
        assert check.query(CustomerDealJourneyEvent).filter_by(id=event_id).one().summary == "Corrected"
        assert _progress(check, team_id, customer_id) == revision
        assert check.query(CustomerDealJourneyEvent).filter_by(team_id=team_id, customer_id=customer_id).count() == 1


def test_preloaded_journey_cannot_roll_back_newer_event_time(journey_case) -> None:
    team_id, customer_id, first_id, _, opportunity_id = journey_case
    older = datetime(2026, 9, 28, 11, 0)
    newer = datetime(2026, 9, 30, 11, 0)
    with SessionLocal() as stale, SessionLocal() as editor:
        cached = stale.query(CustomerDealJourney).filter_by(id=first_id).one()
        assert cached.last_event_at is None
        deal_journey_service.record_event(
            editor, deal_journey_id=first_id, team_id=team_id, customer_id=customer_id,
            event_type=DealJourneyEventType.OPPORTUNITY_APPROVED,
            source_type=DealJourneySourceType.OPPORTUNITY, source_id=opportunity_id,
            event_time=newer, enqueue_customer_intelligence=False,
        )
        editor.commit()
        revision = _progress(editor, team_id, customer_id)
        deal_journey_service.record_event(
            stale, deal_journey_id=first_id, team_id=team_id, customer_id=customer_id,
            event_type=DealJourneyEventType.OPPORTUNITY_STAGE_CHANGED,
            source_type=DealJourneySourceType.OPPORTUNITY, source_id=opportunity_id,
            event_time=older, enqueue_customer_intelligence=False,
        )
        stale.commit()
    with SessionLocal() as check:
        assert check.query(CustomerDealJourney).filter_by(id=first_id).one().last_event_at == newer
        assert _progress(check, team_id, customer_id) == revision + 1


def test_preloaded_lost_opportunity_does_not_close_journey_after_recovery(journey_case) -> None:
    team_id, customer_id, first_id, _, opportunity_id = journey_case
    with SessionLocal() as setup:
        lock_source_customer(setup, team_id=team_id, customer_id=customer_id)
        setup.query(Opportunity).filter_by(id=opportunity_id).one().status = 2
        setup.commit()
    with SessionLocal() as stale, SessionLocal() as editor:
        cached = stale.query(Opportunity).filter_by(id=opportunity_id).one()
        assert cached.status == 2
        lock_source_customer(editor, team_id=team_id, customer_id=customer_id)
        editor.query(Opportunity).filter_by(id=opportunity_id).one().status = 0
        advance_eligible_progress(editor, team_id=team_id, customer_id=customer_id)
        editor.commit()
        revision = _progress(editor, team_id, customer_id)
        refreshed = deal_journey_service.refresh_closure_status(stale, first_id)
        assert refreshed is not None and refreshed.status == DealJourneyStatus.ACTIVE
        assert refreshed.closed_at is None
        stale.commit()
    with SessionLocal() as check:
        assert check.query(CustomerDealJourney).filter_by(id=first_id).one().status == DealJourneyStatus.ACTIVE
        assert _progress(check, team_id, customer_id) == revision


def test_assistant_two_event_does_not_advance_legacy_progress(journey_case) -> None:
    team_id, customer_id, first_id, _, _ = journey_case
    with SessionLocal() as writer:
        lock_source_customer(writer, team_id=team_id, customer_id=customer_id)
        activity = CustomerActivity(
            team_id=team_id, customer_id=customer_id, deal_journey_id=first_id,
            activity_kind="PHONE_CALL", source_content="Assistant-only material",
            submission_source="ASSISTANT_2", submission_id=f"journey-{uuid4().hex}",
            submission_fingerprint="a" * 64, creator_id="990126011", owner_id="990126011",
        )
        writer.add(activity)
        advance_activity_progress(writer, team_id=team_id, customer_id=customer_id, submission_source="ASSISTANT_2")
        writer.flush()
        event = deal_journey_service.record_event(
            writer, deal_journey_id=first_id, team_id=team_id, customer_id=customer_id,
            event_type=DealJourneyEventType.ACTIVITY_ADDED,
            source_type=DealJourneySourceType.CUSTOMER_ACTIVITY, source_id=activity.id,
            event_time=datetime(2026, 9, 30, 11, 0), enqueue_customer_intelligence=False,
        )
        assert event is not None
        event_id = event.id
        writer.commit()
    with SessionLocal() as check:
        assert check.query(CustomerDealJourneyEvent).filter_by(id=event_id).count() == 1
        assert _progress(check, team_id, customer_id) == 0


def test_preloaded_contract_does_not_close_journey_after_payment_reversal(journey_case) -> None:
    team_id, customer_id, first_id, _, opportunity_id = journey_case
    with SessionLocal() as setup:
        contract = Contract(
            team_id=team_id, customer_id=customer_id, opportunity_id=opportunity_id,
            deal_journey_id=first_id, contract_number=f"CT{uuid4().hex}",
            contract_name="Payment regression", user_count=1, total_amount=Decimal("300.00"),
            license_type="PERPETUAL", standard_unit_price=Decimal("300.00"),
            owner_id="990126011", creator_id="990126011", payment_status=PaymentStatus.COMPLETED,
        )
        setup.add(contract)
        setup.commit()
        contract_id = contract.id
    with SessionLocal() as stale, SessionLocal() as editor:
        cached = stale.query(Contract).filter_by(id=contract_id).one()
        assert cached.payment_status == PaymentStatus.COMPLETED
        lock_source_customer(editor, team_id=team_id, customer_id=customer_id)
        editor.query(Contract).filter_by(id=contract_id).one().payment_status = PaymentStatus.UNPAID
        advance_eligible_progress(editor, team_id=team_id, customer_id=customer_id)
        editor.commit()
        revision = _progress(editor, team_id, customer_id)
        refreshed = deal_journey_service.refresh_closure_status(stale, first_id)
        assert refreshed is not None and refreshed.status == DealJourneyStatus.ACTIVE
        stale.commit()
    with SessionLocal() as check:
        assert check.query(CustomerDealJourney).filter_by(id=first_id).one().status == DealJourneyStatus.ACTIVE
        assert _progress(check, team_id, customer_id) == revision


def test_inference_uses_current_journey_status_after_stale_snapshot(journey_case) -> None:
    team_id, customer_id, first_id, second_id, _ = journey_case
    with SessionLocal() as setup:
        lock_source_customer(setup, team_id=team_id, customer_id=customer_id)
        setup.query(CustomerDealJourney).filter_by(id=second_id).one().status = DealJourneyStatus.LOST
        setup.commit()
    with SessionLocal() as stale, SessionLocal() as editor:
        assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
        old = stale.query(CustomerDealJourney).filter_by(id=first_id).one()
        assert old.status == DealJourneyStatus.ACTIVE
        lock_source_customer(editor, team_id=team_id, customer_id=customer_id)
        editor.query(CustomerDealJourney).filter_by(id=first_id).one().status = DealJourneyStatus.COMPLETED
        editor.query(CustomerDealJourney).filter_by(id=second_id).one().status = DealJourneyStatus.ACTIVE
        advance_eligible_progress(editor, team_id=team_id, customer_id=customer_id)
        editor.commit()
        revision = _progress(editor, team_id, customer_id)
        inferred = deal_journey_service.infer_for_customer(stale, customer_id, team_id)
        assert inferred is not None and inferred.id == second_id
        assert inferred.status == DealJourneyStatus.ACTIVE
        stale.commit()
    with SessionLocal() as check:
        assert check.query(CustomerDealJourney).filter_by(id=first_id).one().status == DealJourneyStatus.COMPLETED
        assert _progress(check, team_id, customer_id) == revision


def test_event_for_activity_committed_after_rr_snapshot_advances_progress(journey_case) -> None:
    team_id, customer_id, first_id, _, _ = journey_case
    with SessionLocal() as stale, SessionLocal() as editor:
        assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
        assert stale.query(CustomerActivity).filter_by(team_id=team_id, customer_id=customer_id).all() == []
        lock_source_customer(editor, team_id=team_id, customer_id=customer_id)
        activity = CustomerActivity(
            team_id=team_id, customer_id=customer_id, deal_journey_id=first_id,
            activity_kind="PHONE_CALL", source_content="Post-snapshot eligible activity",
            submission_source="FORM", creator_id="990126011", owner_id="990126011",
        )
        editor.add(activity)
        advance_activity_progress(editor, team_id=team_id, customer_id=customer_id, submission_source="FORM")
        editor.commit()
        activity_id = activity.id
        assert _progress(editor, team_id, customer_id) == 1

        event = deal_journey_service.record_event(
            stale, deal_journey_id=first_id, team_id=team_id, customer_id=customer_id,
            event_type=DealJourneyEventType.ACTIVITY_ADDED,
            source_type=DealJourneySourceType.CUSTOMER_ACTIVITY, source_id=activity_id,
            event_time=datetime(2026, 9, 30, 11, 0), enqueue_customer_intelligence=False,
        )
        assert event is not None
        stale.commit()
    with SessionLocal() as check:
        assert check.query(CustomerDealJourneyEvent).filter_by(
            team_id=team_id, customer_id=customer_id, source_type=DealJourneySourceType.CUSTOMER_ACTIVITY,
            source_id=activity_id,
        ).count() == 1
        assert _progress(check, team_id, customer_id) == 2

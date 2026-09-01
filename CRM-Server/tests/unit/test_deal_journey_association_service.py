"""Business-journey association lifecycle tests."""

import json
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.customer import Customer
from app.models.deal_journey import (
    CustomerDealJourney,
    CustomerDealJourneyEvent,
    DealJourneyEventType,
    DealJourneyStatus,
)
from app.services.deal_journey_service import (
    OpportunityDealJourneyConflictError,
    deal_journey_service,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kwargs):
    return "INTEGER"


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[Customer.__table__, CustomerDealJourney.__table__, CustomerDealJourneyEvent.__table__],
    )
    return sessionmaker(bind=engine)()


def _opportunity(customer, journey):
    return SimpleNamespace(
        id=1001,
        team_id=customer.team_id,
        customer_id=customer.id,
        deal_journey_id=journey.id,
        version=7,
    )


def test_associate_opportunity_records_both_sides_without_rewriting_primary_history(monkeypatch):
    db = _session()
    customer = Customer(team_id=2, account_name="广州市粤港澳大湾区气象智能装备研究中心", city="广州", creator_id="9")
    db.add(customer)
    db.flush()
    previous = CustomerDealJourney(
        team_id=2,
        customer_id=customer.id,
        primary_opportunity_id=None,
        name="第一条业务旅程",
        status=DealJourneyStatus.ACTIVE,
        started_at=datetime(2026, 8, 1),
    )
    target = CustomerDealJourney(
        team_id=2,
        customer_id=customer.id,
        name="第二条业务旅程",
        status=DealJourneyStatus.ACTIVE,
        started_at=datetime(2026, 8, 10),
    )
    db.add_all([previous, target])
    db.flush()
    opportunity = _opportunity(customer, previous)
    previous.primary_opportunity_id = opportunity.id
    db.flush()

    recorded = []
    monkeypatch.setattr(
        deal_journey_service,
        "record_event",
        lambda db, **kwargs: recorded.append(kwargs),
    )

    result = deal_journey_service.associate_opportunity(
        db,
        opportunity,
        deal_journey_id=target.id,
        actor_id="9",
    )

    assert result.id == target.id
    assert opportunity.deal_journey_id == target.id
    assert previous.primary_opportunity_id is None
    assert target.primary_opportunity_id == opportunity.id
    assert opportunity.version == 8
    assert [item["deal_journey_id"] for item in recorded] == [previous.id, target.id]
    assert recorded[0]["metadata"]["transition_id"] == (
        f"journey-association:{opportunity.id}:{previous.id}:{target.id}:7"
    )
    assert all(item["event_type"] == DealJourneyEventType.ASSOCIATION_CHANGED for item in recorded)
    assert recorded[0]["metadata"]["journey_side"] == "previous"
    assert recorded[1]["metadata"]["journey_side"] == "new"
    assert recorded[0]["metadata"]["new_deal_journey_id"] == target.id


def test_detach_opportunity_clears_primary_and_records_negative_association(monkeypatch):
    db = _session()
    customer = Customer(team_id=2, account_name="测试客户", city="广州", creator_id="9")
    db.add(customer)
    db.flush()
    journey = CustomerDealJourney(
        team_id=2,
        customer_id=customer.id,
        name="待解除旅程",
        status=DealJourneyStatus.ACTIVE,
    )
    db.add(journey)
    db.flush()
    opportunity = _opportunity(customer, journey)
    journey.primary_opportunity_id = opportunity.id
    db.flush()

    recorded = []
    monkeypatch.setattr(
        deal_journey_service,
        "record_event",
        lambda db, **kwargs: recorded.append(kwargs),
    )

    result = deal_journey_service.detach_opportunity(db, opportunity, actor_id="9")

    assert result.id == journey.id
    assert opportunity.deal_journey_id is None
    assert opportunity.version == 8
    assert journey.primary_opportunity_id is None
    assert len(recorded) == 1
    assert recorded[0]["metadata"]["previous_deal_journey_id"] == journey.id
    assert recorded[0]["metadata"]["new_deal_journey_id"] is None


def test_associate_opportunity_rejects_cross_customer_journey():
    db = _session()
    customer = Customer(team_id=2, account_name="客户A", city="广州", creator_id="9")
    other_customer = Customer(team_id=2, account_name="客户B", city="广州", creator_id="9")
    db.add_all([customer, other_customer])
    db.flush()
    current = CustomerDealJourney(
        team_id=2, customer_id=customer.id, name="当前旅程", status=DealJourneyStatus.ACTIVE
    )
    foreign = CustomerDealJourney(
        team_id=2, customer_id=other_customer.id, name="其他旅程", status=DealJourneyStatus.ACTIVE
    )
    db.add_all([current, foreign])
    db.flush()
    opportunity = _opportunity(customer, current)

    try:
        deal_journey_service.associate_opportunity(db, opportunity, deal_journey_id=foreign.id)
    except ValueError as exc:
        assert str(exc) == "目标业务旅程不存在，或不属于当前客户"
    else:
        raise AssertionError("跨客户业务旅程关联应被拒绝")


def test_associate_opportunity_rejects_stale_version_without_mutating_state():
    db = _session()
    customer = Customer(team_id=2, account_name="并发客户", city="广州", creator_id="9")
    db.add(customer)
    db.flush()
    current = CustomerDealJourney(
        team_id=2, customer_id=customer.id, name="当前旅程", status=DealJourneyStatus.ACTIVE
    )
    target = CustomerDealJourney(
        team_id=2, customer_id=customer.id, name="目标旅程", status=DealJourneyStatus.ACTIVE
    )
    db.add_all([current, target])
    db.flush()
    opportunity = _opportunity(customer, current)

    try:
        deal_journey_service.associate_opportunity(
            db, opportunity, deal_journey_id=target.id, expected_version=6
        )
    except OpportunityDealJourneyConflictError as exc:
        assert exc.opportunity_id == opportunity.id
        assert exc.expected_version == 6
        assert exc.current_version == 7
    else:
        raise AssertionError("过期版本应拒绝业务旅程迁移")

    assert opportunity.deal_journey_id == current.id
    assert opportunity.version == 7
    assert current.primary_opportunity_id is None
    assert target.primary_opportunity_id is None


def test_repeating_same_association_is_idempotent_and_does_not_bump_version(monkeypatch):
    db = _session()
    customer = Customer(team_id=2, account_name="幂等客户", city="广州", creator_id="9")
    db.add(customer)
    db.flush()
    journey = CustomerDealJourney(
        team_id=2, customer_id=customer.id, name="已有旅程", status=DealJourneyStatus.ACTIVE
    )
    db.add(journey)
    db.flush()
    opportunity = _opportunity(customer, journey)
    recorded = []
    monkeypatch.setattr(
        deal_journey_service,
        "record_event",
        lambda db, **kwargs: recorded.append(kwargs),
    )

    result = deal_journey_service.associate_opportunity(
        db, opportunity, deal_journey_id=journey.id, expected_version=7
    )

    assert result is journey
    assert opportunity.version == 7
    assert recorded == []


def test_real_association_events_are_persisted_for_a_to_b_to_a_and_enqueue_failure_isolated(monkeypatch):
    db = _session()
    customer = Customer(
        team_id=2,
        account_name="广州市粤港澳大湾区气象智能装备研究中心",
        city="广州",
        creator_id="9",
    )
    db.add(customer)
    db.flush()
    journey_a = CustomerDealJourney(
        team_id=2, customer_id=customer.id, name="A：线上服务器", status=DealJourneyStatus.ACTIVE
    )
    journey_b = CustomerDealJourney(
        team_id=2, customer_id=customer.id, name="B：正式采购", status=DealJourneyStatus.ACTIVE
    )
    db.add_all([journey_a, journey_b])
    db.flush()
    opportunity = _opportunity(customer, journey_a)
    journey_a.primary_opportunity_id = opportunity.id
    db.flush()

    class FailingRefresh:
        def enqueue_committed_event_refresh(self, *args, **kwargs):
            raise RuntimeError("refresh outbox unavailable")

    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.customer_intelligence_refresh_service",
        FailingRefresh(),
    )

    deal_journey_service.associate_opportunity(
        db, opportunity, deal_journey_id=journey_b.id, actor_id="9", expected_version=7
    )
    db.commit()

    assert opportunity.deal_journey_id == journey_b.id
    assert journey_a.primary_opportunity_id is None
    assert journey_b.primary_opportunity_id == opportunity.id

    first_transition_events = (
        db.query(CustomerDealJourneyEvent)
        .filter(CustomerDealJourneyEvent.customer_id == customer.id)
        .order_by(CustomerDealJourneyEvent.id.asc())
        .all()
    )
    assert len(first_transition_events) == 2
    first_metadata = [json.loads(item.metadata_json) for item in first_transition_events]
    assert {item["journey_side"] for item in first_metadata} == {"previous", "new"}
    assert len({item["transition_id"] for item in first_metadata}) == 1

    # Move back: this must add a new pair rather than overwrite A's history.
    deal_journey_service.associate_opportunity(
        db, opportunity, deal_journey_id=journey_a.id, actor_id="9", expected_version=8
    )
    db.commit()

    all_events = (
        db.query(CustomerDealJourneyEvent)
        .filter(CustomerDealJourneyEvent.customer_id == customer.id)
        .order_by(CustomerDealJourneyEvent.id.asc())
        .all()
    )
    assert len(all_events) == 4
    transitions = [json.loads(item.metadata_json)["transition_id"] for item in all_events]
    assert len(set(transitions)) == 2
    assert opportunity.version == 9

    # Retrying the current association is a no-op and does not create events.
    deal_journey_service.associate_opportunity(
        db, opportunity, deal_journey_id=journey_a.id, actor_id="9", expected_version=9
    )
    db.commit()
    assert db.query(CustomerDealJourneyEvent).count() == 4

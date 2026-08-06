from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.customer import Contact, Customer
from app.models.deal_journey import (
    CustomerDealJourney,
    CustomerDealJourneyEvent,
    DealJourneyEventType,
    DealJourneySourceType,
)
from app.services.agent.customer_intelligence_trigger import (
    AgentCustomerIntelligenceTurn,
    CustomerIntelligenceTriggerPolicy,
)


class FakeEventService:
    def __init__(self):
        self.question_calls = []
        self.activity_calls = []
        self.contact_calls = []
        self.deal_journey_calls = []

    def agent_customer_question(self, **kwargs):
        self.question_calls.append(kwargs)
        return SimpleNamespace(event_key="question-event", customer_id=kwargs["customer_id"])

    def from_customer_activity(self, activity):
        self.activity_calls.append(activity)
        return SimpleNamespace(event_key="activity-event", customer_id=activity.customer_id)

    def from_contact(self, contact):
        self.contact_calls.append(contact)
        return SimpleNamespace(event_key="contact-event", customer_id=contact.customer_id)

    def from_deal_journey_event(self, event):
        self.deal_journey_calls.append(event)
        return SimpleNamespace(event_key="deal-journey-event", customer_id=event.customer_id)


def test_customer_intelligence_trigger_builds_agent_question_from_structured_new_flow_events():
    event_service = FakeEventService()
    policy = CustomerIntelligenceTriggerPolicy(event_service=event_service)

    event = policy.from_new_flow_events(
        [
            {"event": "intent", "intent": "CRM_READ_QUERY"},
            {"event": "business_context_loaded", "customer": {"id": 101, "account_name": "越秀金融"}},
        ],
        turn=AgentCustomerIntelligenceTurn(
            team_id=2,
            user_id=9,
            session_id=77,
            message_id=88,
            content="总结一下这个客户",
        ),
    )

    assert event.event_key == "question-event"
    assert event.customer_id == 101
    assert event_service.question_calls == [
        {
            "team_id": 2,
            "customer_id": 101,
            "actor_id": "9",
            "session_id": 77,
            "message_id": 88,
            "question": "总结一下这个客户",
        }
    ]


def test_customer_intelligence_trigger_uses_latest_loaded_customer_for_agent_question():
    event_service = FakeEventService()
    policy = CustomerIntelligenceTriggerPolicy(event_service=event_service)

    event = policy.from_new_flow_events(
        [
            {"event": "intent", "intent": "CRM_READ_QUERY"},
            {"event": "business_context_loaded", "customer": {"id": 101, "account_name": "旧客户"}},
            {"event": "business_context_loaded", "customer": {"id": 202, "account_name": "中国科学院信息工程研究所"}},
        ],
        turn=AgentCustomerIntelligenceTurn(
            team_id=2,
            user_id=9,
            session_id=77,
            message_id=88,
            content="中科院现在是什么情况",
        ),
    )

    assert event.event_key == "question-event"
    assert event.customer_id == 202
    assert event_service.question_calls[0]["customer_id"] == 202


def test_customer_intelligence_trigger_ignores_non_customer_query_new_flow_events():
    event_service = FakeEventService()
    policy = CustomerIntelligenceTriggerPolicy(event_service=event_service)

    event = policy.from_new_flow_events(
        [
            {"event": "intent", "intent": "CREATE_OPPORTUNITY"},
            {"event": "business_context_loaded", "customer_id": 101},
        ],
        turn=AgentCustomerIntelligenceTurn(
            team_id=2,
            user_id=9,
            session_id=77,
            message_id=88,
            content="给这个客户建一个商机",
        ),
    )

    assert event is None
    assert event_service.question_calls == []


def test_customer_intelligence_trigger_builds_activity_event_from_committed_tool_result(monkeypatch):
    event_service = FakeEventService()
    policy = CustomerIntelligenceTriggerPolicy(event_service=event_service)
    activity = SimpleNamespace(id=501, team_id=2, customer_id=101)
    lookup_calls = []

    def fake_get_by_id(db, activity_id, team_id):
        lookup_calls.append({"db": db, "activity_id": activity_id, "team_id": team_id})
        return activity

    monkeypatch.setattr(
        "app.services.agent.customer_intelligence_trigger.customer_activity_crud.get_by_id",
        fake_get_by_id,
    )

    event = policy.from_confirmed_tool_result(
        object(),
        {"tool_name": "create_customer_activity", "success": True, "data": {"id": 501}},
        team_id=2,
    )

    assert event.event_key == "activity-event"
    assert event.customer_id == 101
    assert lookup_calls[0]["activity_id"] == 501
    assert event_service.activity_calls == [activity]


def test_customer_intelligence_trigger_builds_deal_journey_event_from_committed_opportunity():
    engine, db = _deal_journey_db_session()
    event_service = FakeEventService()
    policy = CustomerIntelligenceTriggerPolicy(event_service=event_service)
    try:
        _seed_customer_deal_journey_event(
            db,
            source_type=DealJourneySourceType.OPPORTUNITY,
            event_id=1,
            source_id=7101,
            event_type=DealJourneyEventType.OPPORTUNITY_CREATED,
            summary="创建商机：越秀金融-订阅",
        )

        event = policy.from_confirmed_tool_result(
            db,
            {"tool_name": "create_opportunity", "success": True, "data": {"id": 7101}},
            team_id=2,
        )

        assert event.event_key == "deal-journey-event"
        assert event.customer_id == 101
        assert event_service.deal_journey_calls[0].source_type == DealJourneySourceType.OPPORTUNITY
    finally:
        db.close()
        engine.dispose()


def test_customer_intelligence_trigger_builds_contact_event_from_committed_contact():
    engine, db = _contact_db_session()
    event_service = FakeEventService()
    policy = CustomerIntelligenceTriggerPolicy(event_service=event_service)
    try:
        contact = Contact(
            id=601,
            team_id=2,
            customer_id=101,
            name="张总",
            mobile="13800138000",
            position="总经理",
            is_decision_maker=1,
        )
        db.add(contact)
        db.commit()

        event = policy.from_confirmed_tool_result(
            db,
            {"tool_name": "create_contact", "success": True, "data": {"id": 601}},
            team_id=2,
        )

        assert event.event_key == "contact-event"
        assert event.customer_id == 101
        assert event_service.contact_calls == [contact]
    finally:
        db.close()
        engine.dispose()


def test_customer_intelligence_trigger_builds_deal_journey_event_from_contract():
    engine, db = _deal_journey_db_session()
    event_service = FakeEventService()
    policy = CustomerIntelligenceTriggerPolicy(event_service=event_service)
    try:
        _seed_customer_deal_journey_event(
            db,
            source_type=DealJourneySourceType.CONTRACT,
            event_id=3,
            source_id=8101,
            event_type=DealJourneyEventType.CONTRACT_CREATED,
            summary="创建合同：越秀金融合同",
        )

        event = policy.from_confirmed_tool_result(
            db,
            {"tool_name": "create_contract", "success": True, "data": {"id": 8101}},
            team_id=2,
        )

        assert event.event_key == "deal-journey-event"
        assert event.customer_id == 101
        assert event_service.deal_journey_calls[0].source_type == DealJourneySourceType.CONTRACT
    finally:
        db.close()
        engine.dispose()


def test_customer_intelligence_trigger_finds_latest_stage_event_by_opportunity():
    engine, db = _deal_journey_db_session()
    event_service = FakeEventService()
    policy = CustomerIntelligenceTriggerPolicy(event_service=event_service)
    try:
        _seed_customer_deal_journey_event(
            db,
            source_type=DealJourneySourceType.OPPORTUNITY_STAGE_SNAPSHOT,
            event_id=1,
            source_id=9001,
            event_type=DealJourneyEventType.OPPORTUNITY_STAGE_CHANGED,
            summary="商机阶段推进到：方案交流",
            event_time=datetime(2026, 7, 1, 10, 0, 0),
        )
        latest = _seed_customer_deal_journey_event(
            db,
            source_type=DealJourneySourceType.OPPORTUNITY_STAGE_SNAPSHOT,
            event_id=2,
            source_id=9002,
            event_type=DealJourneyEventType.OPPORTUNITY_STAGE_CHANGED,
            summary="商机阶段推进到：POC",
            event_time=datetime(2026, 7, 2, 10, 0, 0),
        )

        event = policy.from_confirmed_tool_result(
            db,
            {"tool_name": "move_opportunity_stage", "success": True, "data": {"id": 7101}},
            team_id=2,
        )

        assert event.event_key == "deal-journey-event"
        assert event_service.deal_journey_calls == [latest]
    finally:
        db.close()
        engine.dispose()


def test_customer_intelligence_trigger_builds_deal_journey_event_from_invoice_application():
    engine, db = _deal_journey_db_session()
    event_service = FakeEventService()
    policy = CustomerIntelligenceTriggerPolicy(event_service=event_service)
    try:
        _seed_customer_deal_journey_event(
            db,
            source_type=DealJourneySourceType.INVOICE_APPLICATION,
            event_id=4,
            source_id=301,
            event_type=DealJourneyEventType.INVOICE_APPLIED,
            summary="申请开票：100000",
        )

        event = policy.from_confirmed_tool_result(
            db,
            {"tool_name": "create_invoice_application", "success": True, "data": {"id": 301}},
            team_id=2,
        )

        assert event.event_key == "deal-journey-event"
        assert event.customer_id == 101
        assert event_service.deal_journey_calls[0].event_type == DealJourneyEventType.INVOICE_APPLIED
    finally:
        db.close()
        engine.dispose()


def test_customer_intelligence_trigger_builds_deal_journey_event_from_payment_record():
    engine, db = _deal_journey_db_session()
    event_service = FakeEventService()
    policy = CustomerIntelligenceTriggerPolicy(event_service=event_service)
    try:
        _seed_customer_deal_journey_event(
            db,
            source_type=DealJourneySourceType.PAYMENT_RECORD,
            event_id=1,
            source_id=401,
            event_type=DealJourneyEventType.PAYMENT_RECEIVED,
            summary="登记回款：300000",
        )

        event = policy.from_confirmed_tool_result(
            db,
            {"tool_name": "create_payment_record", "success": True, "data": {"id": 401}},
            team_id=2,
        )

        assert event.event_key == "deal-journey-event"
        assert event.customer_id == 101
        assert event_service.deal_journey_calls[0].source_type == DealJourneySourceType.PAYMENT_RECORD
    finally:
        db.close()
        engine.dispose()


def _deal_journey_db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerDealJourney.__table__,
            CustomerDealJourneyEvent.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Customer(id=101, team_id=2, account_name="越秀金融", city="广州", creator_id="9"))
    session.add(
        CustomerDealJourney(
            id=301, team_id=2, customer_id=101, primary_opportunity_id=7101, name="越秀金融商机", status="ACTIVE"
        )
    )
    session.commit()
    return engine, session


def _contact_db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Contact.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    return engine, Session()


def _seed_customer_deal_journey_event(
    db,
    *,
    source_type: str,
    event_id: int,
    source_id: int,
    event_type: str,
    summary: str,
    event_time: datetime | None = None,
) -> CustomerDealJourneyEvent:
    event = CustomerDealJourneyEvent(
        id=event_id,
        team_id=2,
        deal_journey_id=301,
        customer_id=101,
        event_type=event_type,
        source_type=source_type,
        source_id=source_id,
        event_time=event_time or datetime(2026, 7, 1, 10, 0, 0),
        actor_id="9",
        summary=summary,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event

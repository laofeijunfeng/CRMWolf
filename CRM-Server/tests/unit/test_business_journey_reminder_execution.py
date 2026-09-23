from datetime import datetime, timedelta

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.customer import Customer, CustomerMember
from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent, DealJourneyEventType
from app.models.opportunity import Opportunity
from app.models.reminder_rule import ReminderRule
from app.models.reminder_rule_run import ReminderRuleRun
from app.models.user import User, UserStatus
from app.services.reminder_rule_execution import execute_due_reminder_rules


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


def _session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    tables = [
        User.__table__, Customer.__table__, CustomerMember.__table__, Opportunity.__table__,
        CustomerDealJourney.__table__, CustomerDealJourneyEvent.__table__, ReminderRule.__table__, ReminderRuleRun.__table__,
    ]
    renamed = []
    for table in tables:
        for index in table.indexes:
            if index.name:
                renamed.append((index, index.name))
                index.name = f"{table.name}_{index.name}"
    try:
        Base.metadata.create_all(engine, tables=tables)
    finally:
        for index, original in renamed:
            index.name = original
    return sessionmaker(bind=engine)()


def _seed(db):
    now = datetime(2026, 9, 23, 9, 0)
    db.add_all([
        User(id=7, email="owner@example.com", name="负责人", status=UserStatus.ACTIVE),
        User(id=8, email="selected@example.com", name="指定成员", status=UserStatus.ACTIVE),
        User(id=9, email="collaborator@example.com", name="协作成员", status=UserStatus.ACTIVE),
        Customer(id=1, team_id=101, account_name="华东电力", city="上海", owner_id="7", creator_id="7"),
        CustomerMember(id=10, team_id=101, customer_id=1, user_id="9", member_role="PRESALES", access_level="VIEW", created_by="7"),
        CustomerDealJourney(id=21, team_id=101, customer_id=1, primary_opportunity_id=11, name="华东电力扩容旅程", status="WON", started_at=now - timedelta(days=30), last_event_at=now - timedelta(days=1)),
        Opportunity(id=11, team_id=101, customer_id=1, opportunity_number="OPP-11", opportunity_name="华东电力扩容", owner_id="7", creator_id="7", status=1, current_stage_name="赢单", current_stage_entered_at=now - timedelta(days=20), total_amount=100, user_count=1, unit_price=100, license_type="SUBSCRIPTION", purchase_type="NEW", expected_closing_date=now.date(), deal_journey_id=21),
        CustomerDealJourneyEvent(id=31, team_id=101, deal_journey_id=21, customer_id=1, event_type=DealJourneyEventType.OPPORTUNITY_WON, event_time=now - timedelta(days=7), source_type="opportunity", source_id=11, summary="商机已赢单"),
        CustomerDealJourneyEvent(id=32, team_id=101, deal_journey_id=21, customer_id=1, event_type=DealJourneyEventType.ASSOCIATION_CHANGED, event_time=now - timedelta(days=1), source_type="opportunity", source_id=11, summary="关联调整"),
        ReminderRule(id=41, team_id=101, name="业务旅程无动态提醒", object_type="business_journey", trigger="schedule", enabled=True, created_by=7, rule={
            "name": "业务旅程无动态提醒", "object_type": "business_journey", "trigger": "schedule",
            "inactive_days": 7, "offset_days": 0, "trigger_time": "09:00",
            "conditions": [{"field": "status", "operator": "in", "value": ["ACTIVE", "WON"]}],
            "recipients": ["primary_opportunity_owner", "customer_owner", "customer_members", "user:8"],
            "message_title": "业务旅程已连续 {静默天数} 天无新动态",
            "message_template": "{客户名称} 的业务旅程「{业务旅程名称}」已连续 {静默天数} 天无新动态。最后动态：{最近动态摘要}",
            "channels": ["feishu"], "notify_once_per_window": True,
        }),
    ])
    db.commit()
    return now


def test_journey_reminder_uses_effective_event_time_and_sends_once_at_configured_time():
    import asyncio

    db = _session()
    now = _seed(db)
    sent = []

    def deliver(team_id, user_ids, title, content):
        sent.append({"team_id": team_id, "user_ids": sorted(user_ids), "title": title, "content": content})
        return {"sent": len(user_ids), "skipped": 0}

    before = asyncio.run(execute_due_reminder_rules(db, now=now - timedelta(minutes=1), deliver=deliver))
    first = asyncio.run(execute_due_reminder_rules(db, now=now, deliver=deliver))
    second = asyncio.run(execute_due_reminder_rules(db, now=now + timedelta(days=1), deliver=deliver))

    assert before.sent_count == 0
    assert first.sent_count == 1
    assert second.sent_count == 0
    assert sent == [{
        "team_id": 101,
        "user_ids": [7, 8, 9],
        "title": "业务旅程已连续 7 天无新动态",
        "content": "华东电力 的业务旅程「华东电力扩容旅程」已连续 7 天无新动态。最后动态：商机已赢单",
    }]


def test_journey_reminder_can_fire_one_day_before_the_inactivity_threshold():
    import asyncio

    db = _session()
    now = _seed(db)
    event = db.query(CustomerDealJourneyEvent).filter(CustomerDealJourneyEvent.id == 31).one()
    event.event_time = now - timedelta(days=6)
    rule = db.query(ReminderRule).filter(ReminderRule.id == 41).one()
    payload = dict(rule.rule)
    payload["offset_days"] = -1
    rule.rule = payload
    db.commit()
    sent = []

    def deliver(team_id, user_ids, title, content):
        sent.append({"team_id": team_id, "user_ids": sorted(user_ids), "title": title, "content": content})
        return {"sent": len(user_ids), "skipped": 0}

    result = asyncio.run(execute_due_reminder_rules(db, now=now, deliver=deliver))
    assert result.sent_count == 1
    assert len(sent) == 1


def test_journey_owner_not_empty_condition_suppresses_missing_owner():
    import asyncio

    db = _session()
    now = _seed(db)
    opportunity = db.query(Opportunity).filter(Opportunity.id == 11).one()
    opportunity.owner_id = ""
    rule = db.query(ReminderRule).filter(ReminderRule.id == 41).one()
    payload = dict(rule.rule)
    payload["conditions"] = [
        {"field": "status", "operator": "in", "value": ["ACTIVE", "WON"]},
        {"field": "primary_opportunity_owner", "operator": "not_empty", "value": True},
    ]
    rule.rule = payload
    db.commit()

    result = asyncio.run(execute_due_reminder_rules(
        db,
        now=now,
        deliver=lambda *_args: {"sent": 1, "skipped": 0},
    ))
    assert result.sent_count == 0

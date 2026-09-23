from datetime import datetime, timedelta

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.customer import Customer, CustomerMember
from app.models.customer_activity import CustomerActivity
from app.models.opportunity import Opportunity
from app.models.reminder_rule import ReminderRule
from app.models.reminder_rule_run import ReminderRuleRun
from app.models.role import Role
from app.models.sales_commitment import FollowUpTask
from app.models.team import UserTeam
from app.models.user import User, UserStatus
from app.models.user_role import UserRole
from app.services.reminder_rule_execution import execute_due_reminder_rules


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    tables = [
        User.__table__,
        UserTeam.__table__,
        Role.__table__,
        UserRole.__table__,
        Customer.__table__,
        CustomerMember.__table__,
        Opportunity.__table__,
        CustomerActivity.__table__,
        FollowUpTask.__table__,
        ReminderRule.__table__,
        ReminderRuleRun.__table__,
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


def _seed(db, *, activity_at: datetime | None):
    now = datetime(2026, 9, 23, 9, 30)
    db.add(User(id=7, email="owner@example.com", name="负责人", status=UserStatus.ACTIVE))
    db.add(User(id=8, email="director@example.com", name="销售总监", status=UserStatus.ACTIVE))
    db.add(UserTeam(user_id=7, team_id=101))
    db.add(UserTeam(user_id=8, team_id=101))
    db.add(Role(id=3, name="销售总监", code="SALES_DIRECTOR"))
    db.add(UserRole(user_id=8, role_id=3, team_id=101))
    db.add(Customer(id=1, team_id=101, account_name="华东电力", city="上海", owner_id="7", creator_id="7"))
    db.add(User(id=9, email="collaborator@example.com", name="协作成员", status=UserStatus.ACTIVE))
    db.add(UserTeam(user_id=9, team_id=101))
    db.add(
        CustomerMember(
            id=10, team_id=101, customer_id=1, user_id="9", member_role="PRESALES", access_level="VIEW", created_by="7"
        )
    )
    db.add(
        Opportunity(
            id=11,
            team_id=101,
            customer_id=1,
            opportunity_number="OPP-11",
            opportunity_name="华东电力扩容",
            owner_id="7",
            creator_id="7",
            status=0,
            current_stage_name="报价",
            current_stage_entered_at=now - timedelta(days=8),
            total_amount=100,
            user_count=1,
            unit_price=100,
            license_type="SUBSCRIPTION",
            purchase_type="NEW",
            expected_closing_date=now.date(),
        )
    )
    if activity_at is not None:
        db.add(
            CustomerActivity(
                id=21,
                team_id=101,
                customer_id=1,
                activity_kind="visit",
                source_content="已电话沟通",
                occurred_at=activity_at,
                creator_id="7",
                owner_id="7",
            )
        )
    db.add(
        ReminderRule(
            id=31,
            team_id=101,
            name="商机阶段停留提醒",
            object_type="opportunity",
            trigger="schedule",
            enabled=True,
            created_by=7,
            rule={
                "name": "商机阶段停留提醒",
                "object_type": "opportunity",
                "trigger": "schedule",
                "status": "FOLLOWING",
                "inactive_days": 7,
                "require_no_new_activity": True,
                "recipients": ["owner", "customer_members", "user:8"],
                "message_template": "{商机名称} 在{当前阶段}已停留 {天数} 天，期间没有新的客户活动。",  # noqa: RUF001
                "channels": ["in_app", "feishu"],
            },
        )
    )
    db.commit()
    return now


def test_stale_opportunity_notifies_owner_and_sales_director_once():
    import asyncio

    db = _session()
    now = _seed(db, activity_at=datetime(2026, 9, 1, 9, 0))
    sent: list[dict] = []

    def deliver(team_id, user_ids, message):
        sent.append({"team_id": team_id, "user_ids": sorted(user_ids), "message": message})
        return {"sent": len(user_ids), "skipped": 0}

    first = asyncio.run(execute_due_reminder_rules(db, now=now, deliver=deliver))
    second = asyncio.run(execute_due_reminder_rules(db, now=now, deliver=deliver))

    assert first.sent_count == 1
    assert second.sent_count == 0
    assert sent == [
        {
            "team_id": 101,
            "user_ids": [7, 8, 9],
            "message": "华东电力扩容 在报价已停留 8 天，期间没有新的客户活动。",  # noqa: RUF001
        }
    ]
    assert db.query(ReminderRuleRun).count() == 1


def test_recent_activity_suppresses_the_stage_silence_rule():
    import asyncio

    db = _session()
    now = _seed(db, activity_at=datetime(2026, 9, 22, 9, 0))
    result = asyncio.run(
        execute_due_reminder_rules(db, now=now, deliver=lambda *_args, **_kwargs: {"sent": 1, "skipped": 0})
    )
    assert result.sent_count == 0
    assert db.query(ReminderRuleRun).count() == 0


def test_due_follow_up_task_notifies_its_owner_once():
    import asyncio

    db = _session()
    now = datetime(2026, 9, 23, 9, 30)
    db.add(User(id=7, email="owner@example.com", name="负责人", status=UserStatus.ACTIVE))
    db.add(Customer(id=1, team_id=101, account_name="华东电力", city="上海", owner_id="7", creator_id="7"))
    db.add(
        FollowUpTask(
            id=41,
            team_id=101,
            customer_id=1,
            owner_id="7",
            creator_id="7",
            title="回访华东电力",
            status="OPEN",
            due_at=now - timedelta(hours=1),
            source_type="CUSTOMER_ACTIVITY",
            source_key="activity:1",
            task_hash="hash-1",
        )
    )
    db.add(
        ReminderRule(
            id=51,
            team_id=101,
            name="跟进任务到期",
            object_type="follow_up_task",
            trigger="date",
            enabled=True,
            rule={
                "name": "跟进任务到期",
                "object_type": "follow_up_task",
                "trigger": "date",
                "status": "OPEN",
                "date_field": "due_at",
                "offset_days": 0,
                "require_no_new_activity": False,
                "recipients": ["owner"],
                "message_template": "{任务标题} 今天到期，仍待处理。",  # noqa: RUF001
                "channels": ["feishu"],
            },
        )
    )
    db.commit()
    sent: list[dict] = []

    def deliver(team_id, user_ids, message):
        sent.append({"team_id": team_id, "user_ids": user_ids, "message": message})
        return {"sent": len(user_ids), "skipped": 0}

    first = asyncio.run(execute_due_reminder_rules(db, now=now, deliver=deliver))
    second = asyncio.run(execute_due_reminder_rules(db, now=now, deliver=deliver))
    assert first.sent_count == 1
    assert second.sent_count == 0
    assert sent == [{"team_id": 101, "user_ids": [7], "message": "回访华东电力 今天到期，仍待处理。"}]  # noqa: RUF001


def _v2_rule(db, object_type, conditions, recipients=None):
    from app.services.reminder_rule_dsl import validate_reminder_rule

    recipients = recipients or ["owner"]
    payload = {
        "version": 2,
        "name": "条件提醒",
        "object_type": object_type,
        "trigger": "schedule",
        "status": None,
        "inactive_days": None,
        "date_field": None,
        "offset_days": 0,
        "require_no_new_activity": False,
        "trigger_time": "09:30",
        "conditions": conditions,
        "recipients": recipients,
        "message_title": "提醒",
        "message_template": "条件已满足",
        "channels": ["feishu"],
        "notify_once_per_window": True,
    }
    assert validate_reminder_rule(payload) == []
    db.add(
        ReminderRule(
            id=99, team_id=101, name="条件提醒", object_type=object_type, trigger="schedule", enabled=True, rule=payload
        )
    )
    db.commit()
    return payload


def test_v2_partial_delivery_retries_only_unreached_recipients():
    import asyncio

    db = _session()
    now = datetime(2026, 9, 23, 9, 30)
    db.add(User(id=7, email="owner@example.com", name="负责人", status=UserStatus.ACTIVE))
    db.add(User(id=8, email="other@example.com", name="协作者", status=UserStatus.ACTIVE))
    db.add(UserTeam(user_id=7, team_id=101))
    db.add(UserTeam(user_id=8, team_id=101))
    db.add(Customer(id=1, team_id=101, account_name="客户", city="上海", owner_id="7", creator_id="7"))
    _v2_rule(db, "customer", [{"field": "status", "operator": "in", "value": ["FOLLOWING"]}], recipients=["user:7", "user:8"])
    calls = []

    def deliver(_team_id, user_ids, _title, _content):
        calls.append(user_ids)
        return {"sent": int(user_ids != [8] or calls.count([8]) > 1), "skipped": int(user_ids == [8] and calls.count([8]) == 1)}

    def run():
        return asyncio.run(execute_due_reminder_rules(db, now=now, deliver=deliver)).sent_count

    assert run() == 1
    ledger = db.query(ReminderRuleRun).one()
    assert ledger.recipient_ids == "7"
    assert ledger.sent_count == 1
    assert run() == 1
    assert db.query(ReminderRuleRun).count() == 1
    assert ledger.recipient_ids == "7,8"
    assert ledger.sent_count == 2
    assert run() == 0
    assert calls == [[7], [8], [8]]


def test_v2_retries_same_anchor_after_zero_successful_deliveries():
    import asyncio

    db = _session()
    now = datetime(2026, 9, 23, 9, 30)
    db.add(User(id=7, email="owner@example.com", name="负责人", status=UserStatus.ACTIVE))
    db.add(UserTeam(user_id=7, team_id=101))
    db.add(Customer(id=1, team_id=101, account_name="客户", city="上海", owner_id="7", creator_id="7"))
    _v2_rule(db, "customer", [{"field": "status", "operator": "in", "value": ["FOLLOWING"]}])
    attempts = []

    def deliver(_team_id, _user_ids, _title, _content):
        attempts.append(True)
        return {"sent": int(len(attempts) > 1), "skipped": int(len(attempts) == 1)}

    def run():
        return asyncio.run(execute_due_reminder_rules(db, now=now, deliver=deliver)).sent_count

    assert run() == 0
    assert db.query(ReminderRuleRun).count() == 0
    assert run() == 1
    assert db.query(ReminderRuleRun).one().sent_count == 1
    assert run() == 0
    assert len(attempts) == 2


def test_v2_deadline_at_earliest_date_handles_maximum_day_offset():
    import asyncio
    from datetime import date

    db = _session()
    now = datetime(2026, 9, 23, 9, 30)
    db.add(User(id=7, email="owner@example.com", name="负责人", status=UserStatus.ACTIVE))
    db.add(UserTeam(user_id=7, team_id=101))
    db.add(Customer(id=1, team_id=101, account_name="客户", city="上海", owner_id="7", creator_id="7", license_expiry_date=date.min))
    _v2_rule(db, "customer", [{"field": "license_expiry_date", "operator": "due_in_days", "value": 36500}])
    assert asyncio.run(execute_due_reminder_rules(db, now=now, deliver=lambda *_args: {"sent": 1, "skipped": 0})).sent_count == 1




def test_v2_rejects_overflowing_day_conditions_and_keeps_scanning():
    import asyncio

    from app.services.reminder_rule_dsl import validate_reminder_rule

    db = _session()
    now = datetime(2026, 9, 23, 9, 30)
    db.add(User(id=7, email="owner@example.com", name="负责人", status=UserStatus.ACTIVE))
    db.add(UserTeam(user_id=7, team_id=101))
    db.add(Customer(id=1, team_id=101, account_name="客户", city="上海", owner_id="7", creator_id="7"))
    valid = _v2_rule(db, "customer", [{"field": "status", "operator": "in", "value": ["FOLLOWING"]}])
    malformed = {**valid, "name": "错误天数", "conditions": [{"field": "license_expiry_date", "operator": "due_in_days", "value": 10**9}]}
    assert validate_reminder_rule(malformed)
    db.add(ReminderRule(id=100, team_id=101, name="错误天数", object_type="customer", trigger="schedule", enabled=True, rule=malformed))
    db.commit()
    calls = []

    def deliver(*_args):
        calls.append(True)
        return {"sent": 1, "skipped": 0}

    assert asyncio.run(execute_due_reminder_rules(db, now=now, deliver=deliver)).sent_count == 1
    assert len(calls) == 1


def test_v2_created_after_daily_slot_waits_until_next_day():
    import asyncio

    db = _session()
    now = datetime(2026, 9, 23, 16, 15)
    db.add(User(id=7, email="owner@example.com", name="负责人", status=UserStatus.ACTIVE))
    db.add(UserTeam(user_id=7, team_id=101))
    db.add(Customer(id=1, team_id=101, account_name="客户", city="上海", owner_id="7", creator_id="7"))
    payload = _v2_rule(db, "customer", [{"field": "status", "operator": "in", "value": ["FOLLOWING"]}])
    payload["trigger_time"] = "09:00"
    rule = db.query(ReminderRule).one()
    rule.rule = payload
    rule.created_time = datetime(2026, 9, 23, 16, 0)
    db.commit()
    deliveries = []

    def deliver(*_args):
        deliveries.append(True)
        return {"sent": 1, "skipped": 0}

    assert asyncio.run(execute_due_reminder_rules(db, now=now, deliver=deliver)).sent_count == 0
    assert db.query(ReminderRuleRun).count() == 0
    assert asyncio.run(execute_due_reminder_rules(db, now=datetime(2026, 9, 24, 9, 15), deliver=deliver)).sent_count == 1
    assert len(deliveries) == 1


def test_v2_opportunity_requires_every_condition_and_rearms_only_on_date_change():
    import asyncio

    db = _session()
    now = datetime(2026, 9, 23, 9, 30)
    db.add(UserTeam(user_id=7, team_id=101))
    db.add(User(id=7, email="owner@example.com", name="负责人", status=UserStatus.ACTIVE))
    db.add(Customer(id=1, team_id=101, account_name="客户", city="上海", owner_id="7", creator_id="7"))
    db.add(
        Opportunity(
            id=11,
            team_id=101,
            customer_id=1,
            opportunity_number="V2-11",
            opportunity_name="测试",
            owner_id="7",
            creator_id="7",
            status=1,
            current_stage_entered_at=now - timedelta(days=4),
            total_amount=100,
            user_count=1,
            unit_price=100,
            license_type="SUBSCRIPTION",
            purchase_type="NEW",
            expected_closing_date=now.date(),
        )
    )
    _v2_rule(
        db,
        "opportunity",
        [
            {"field": "status", "operator": "in", "value": ["FOLLOWING"]},
            {"field": "current_stage_entered_at", "operator": "older_than_days", "value": 4},
            {"field": "owner", "operator": "not_empty", "value": True},
        ],
    )
    sent = []

    def deliver(team_id, user_ids, title, content):
        sent.append((team_id, user_ids, content))
        return {"sent": len(user_ids), "skipped": 0}

    def run(at):
        return asyncio.run(execute_due_reminder_rules(db, now=at, deliver=deliver)).sent_count

    assert run(now - timedelta(minutes=1)) == 0
    assert run(now) == 0  # date matches, status does not
    opportunity = db.query(Opportunity).one()
    opportunity.status = 0
    db.commit()
    assert run(now) == 1
    assert run(now + timedelta(days=1)) == 0
    opportunity.current_stage_entered_at = now - timedelta(days=5)
    db.commit()
    assert run(now) == 1
    assert sent == [(101, [7], "条件已满足"), (101, [7], "条件已满足")]
    assert all(len(row.window_key) < 120 for row in db.query(ReminderRuleRun).all())


def test_v2_due_in_days_sends_before_deadline_and_status_only_once():
    import asyncio

    db = _session()
    now = datetime(2026, 9, 23, 9, 30)
    db.add(User(id=7, email="owner@example.com", name="负责人", status=UserStatus.ACTIVE))
    db.add(UserTeam(user_id=7, team_id=101))
    db.add(Customer(id=1, team_id=101, account_name="客户", city="上海", owner_id="7", creator_id="7"))
    task = FollowUpTask(
        id=41,
        team_id=101,
        customer_id=1,
        owner_id="7",
        creator_id="7",
        title="跟进",
        status="OPEN",
        due_at=now + timedelta(days=2),
        source_type="CUSTOMER_ACTIVITY",
        source_key="activity:41",
        task_hash="hash-41",
    )
    db.add(task)
    _v2_rule(
        db,
        "follow_up_task",
        [
            {"field": "due_at", "operator": "due_in_days", "value": 2},
            {"field": "status", "operator": "in", "value": ["OPEN"]},
        ],
    )
    deliveries = []

    def deliver(*_args):
        deliveries.append(True)
        return {"sent": 1, "skipped": 0}

    def run(at):
        return asyncio.run(execute_due_reminder_rules(db, now=at, deliver=deliver)).sent_count

    assert run(now) == 1
    assert run(now + timedelta(days=4)) == 0
    assert len(deliveries) == 1
    db.query(ReminderRule).delete()
    db.query(ReminderRuleRun).delete()
    db.add(
        ReminderRule(
            id=100,
            team_id=101,
            name="状态提醒",
            object_type="follow_up_task",
            trigger="schedule",
            enabled=True,
            rule={
                "version": 2,
                "object_type": "follow_up_task",
                "trigger": "schedule",
                "trigger_time": "09:30",
                "conditions": [{"field": "status", "operator": "in", "value": ["OPEN"]}],
                "recipients": ["owner"],
                "message_template": "状态提醒",
                "message_title": "状态提醒",
                "channels": ["feishu"],
            },
        )
    )
    db.commit()
    assert run(now) == 1
    task.due_at = now + timedelta(days=10)
    db.commit()
    assert run(now + timedelta(days=1)) == 0


def test_v2_missing_date_never_matches_and_due_window_starts_on_calendar_day():
    import asyncio

    db = _session()
    now = datetime(2026, 9, 23, 9, 30)
    db.add(User(id=7, email="owner@example.com", name="负责人", status=UserStatus.ACTIVE))
    db.add(UserTeam(user_id=7, team_id=101))
    db.add(Customer(id=1, team_id=101, account_name="客户", city="上海", owner_id="7", creator_id="7"))
    db.add(
        Opportunity(
            id=11,
            team_id=101,
            customer_id=1,
            opportunity_number="V2-11",
            opportunity_name="测试",
            owner_id="7",
            creator_id="7",
            status=0,
            current_stage_entered_at=None,
            total_amount=100,
            user_count=1,
            unit_price=100,
            license_type="SUBSCRIPTION",
            purchase_type="NEW",
            expected_closing_date=now.date() + timedelta(days=3),
        )
    )
    _v2_rule(
        db,
        "opportunity",
        [
            {"field": "current_stage_entered_at", "operator": "older_than_days", "value": 0},
            {"field": "expected_closing_date", "operator": "due_in_days", "value": 2},
        ],
    )
    sent = []

    def deliver(*_args):
        sent.append(True)
        return {"sent": 1, "skipped": 0}

    def run(at):
        return asyncio.run(execute_due_reminder_rules(db, now=at, deliver=deliver)).sent_count

    assert run(now + timedelta(days=1)) == 0  # missing stage date, despite deadline now in range
    opportunity = db.query(Opportunity).one()
    opportunity.current_stage_entered_at = now
    db.commit()
    assert run(now) == 0  # one day before the due_in_days threshold
    assert run(now + timedelta(days=1)) == 1
    assert run(now + timedelta(days=10)) == 0  # overdue, still the same date anchor
    assert sent == [True]


def test_v2_journey_uses_effective_event_not_latest_association():
    import asyncio

    from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent, DealJourneyEventType

    db = _session()
    CustomerDealJourney.__table__.create(db.bind)
    CustomerDealJourneyEvent.__table__.create(db.bind)
    now = datetime(2026, 9, 23, 9, 30)
    db.add(User(id=7, email="owner@example.com", name="负责人", status=UserStatus.ACTIVE))
    db.add(UserTeam(user_id=7, team_id=101))
    db.add(Customer(id=1, team_id=101, account_name="客户", city="上海", owner_id="7", creator_id="7"))
    db.add(
        CustomerDealJourney(
            id=21, team_id=101, customer_id=1, name="旅程", status="ACTIVE", last_event_at=now - timedelta(days=1)
        )
    )
    db.add(
        CustomerDealJourneyEvent(
            id=31,
            team_id=101,
            deal_journey_id=21,
            customer_id=1,
            event_type=DealJourneyEventType.OPPORTUNITY_WON,
            event_time=now - timedelta(days=7),
            source_type="opportunity",
        )
    )
    db.add(
        CustomerDealJourneyEvent(
            id=32,
            team_id=101,
            deal_journey_id=21,
            customer_id=1,
            event_type=DealJourneyEventType.ASSOCIATION_CHANGED,
            event_time=now - timedelta(days=1),
            source_type="opportunity",
        )
    )
    _v2_rule(
        db,
        "business_journey",
        [
            {"field": "last_effective_event_at", "operator": "older_than_days", "value": 7},
            {"field": "status", "operator": "in", "value": ["ACTIVE"]},
        ],
        recipients=["customer_owner"],
    )
    result = asyncio.run(execute_due_reminder_rules(db, now=now, deliver=lambda *_args: {"sent": 1, "skipped": 0}))
    assert result.sent_count == 1
    assert db.query(ReminderRuleRun).one().object_id == 21


def test_v2_journey_status_only_skips_cross_team_customer_with_explicit_recipient():
    import asyncio

    from app.models.deal_journey import CustomerDealJourney

    db = _session()
    CustomerDealJourney.__table__.create(db.bind)
    now = datetime(2026, 9, 23, 9, 30)
    db.add(User(id=7, email="owner@example.com", name="负责人", status=UserStatus.ACTIVE))
    db.add(UserTeam(user_id=7, team_id=101))
    db.add(Customer(id=1, team_id=202, account_name="其他团队客户", city="上海", owner_id="7", creator_id="7"))
    db.add(CustomerDealJourney(id=21, team_id=101, customer_id=1, name="错误关联旅程", status="ACTIVE"))
    _v2_rule(
        db, "business_journey", [{"field": "status", "operator": "in", "value": ["ACTIVE"]}], recipients=["user:7"]
    )
    deliveries = []
    assert (
        asyncio.run(
            execute_due_reminder_rules(
                db, now=now, deliver=lambda *_args: deliveries.append(True) or {"sent": 1, "skipped": 0}
            )
        ).sent_count
        == 0
    )
    assert deliveries == []


def test_v2_lead_enum_status_and_customer_activity_team_scope():
    import asyncio

    from app.models.lead import Lead, LeadStatus

    db = _session()
    Lead.__table__.create(db.bind)
    now = datetime(2026, 9, 23, 9, 30)
    db.add(User(id=7, email="owner@example.com", name="负责人", status=UserStatus.ACTIVE))
    db.add(UserTeam(user_id=7, team_id=101))
    db.add(
        Lead(
            id=61,
            team_id=101,
            lead_name="跟进线索",
            source="官网",
            city="上海",
            contact_name="联系人",
            contact_phone="123",
            owner_id="7",
            status=LeadStatus.FOLLOWING,
            creator_id="7",
            created_time=now - timedelta(days=1),
        )
    )
    _v2_rule(db, "lead", [{"field": "status", "operator": "in", "value": ["FOLLOWING"]}])
    assert (
        asyncio.run(
            execute_due_reminder_rules(db, now=now, deliver=lambda *_args: {"sent": 1, "skipped": 0})
        ).sent_count
        == 1
    )

    db.query(ReminderRule).delete()
    db.query(ReminderRuleRun).delete()
    db.add(Customer(id=1, team_id=101, account_name="客户", city="上海", owner_id="7", creator_id="7"))
    db.add(
        CustomerActivity(
            id=21,
            team_id=101,
            customer_id=1,
            activity_kind="visit",
            source_content="旧活动",
            occurred_at=now - timedelta(days=7),
            creator_id="7",
            owner_id="7",
        )
    )
    db.add(
        CustomerActivity(
            id=22,
            team_id=202,
            customer_id=1,
            activity_kind="visit",
            source_content="其他团队活动",
            occurred_at=now,
            creator_id="7",
            owner_id="7",
        )
    )
    _v2_rule(db, "customer", [{"field": "last_activity_at", "operator": "older_than_days", "value": 7}])
    assert (
        asyncio.run(
            execute_due_reminder_rules(db, now=now, deliver=lambda *_args: {"sent": 1, "skipped": 0})
        ).sent_count
        == 1
    )
    db.add(
        CustomerActivity(
            id=23,
            team_id=101,
            customer_id=1,
            activity_kind="visit",
            source_content="本团队活动",
            occurred_at=now,
            creator_id="7",
            owner_id="7",
        )
    )
    db.commit()
    assert (
        asyncio.run(
            execute_due_reminder_rules(
                db, now=now + timedelta(days=1), deliver=lambda *_args: {"sent": 1, "skipped": 0}
            )
        ).sent_count
        == 0
    )


def test_v2_approval_and_payment_select_team_and_resolve_related_owner():
    import asyncio

    from app.models.approval import Approval
    from app.models.contract import Contract
    from app.models.payment import PaymentPlan

    db = _session()
    Approval.__table__.create(db.bind)
    Contract.__table__.create(db.bind)
    PaymentPlan.__table__.create(db.bind)
    now = datetime(2026, 9, 23, 9, 30)
    db.add(User(id=7, email="owner@example.com", name="负责人", status=UserStatus.ACTIVE))
    db.add(UserTeam(user_id=7, team_id=101))
    db.add(Customer(id=1, team_id=101, account_name="客户", city="上海", owner_id="7", creator_id="7"))
    db.add(
        Approval(
            id=51,
            team_id=101,
            status="APPROVED",
            submitter_id="7",
            business_type="CONTRACT",
            created_time=now - timedelta(days=7),
        )
    )
    db.add(
        Approval(
            id=52,
            team_id=202,
            status="APPROVED",
            submitter_id="7",
            business_type="CONTRACT",
            created_time=now - timedelta(days=7),
        )
    )
    _v2_rule(
        db,
        "approval",
        [
            {"field": "status", "operator": "in", "value": ["APPROVED"]},
            {"field": "created_time", "operator": "older_than_days", "value": 7},
            {"field": "submitter", "operator": "not_empty", "value": True},
        ],
        recipients=["submitter"],
    )
    delivered = []

    def deliver(team_id, user_ids, title, content):
        delivered.append((team_id, user_ids))
        return {"sent": len(user_ids), "skipped": 0}

    assert asyncio.run(execute_due_reminder_rules(db, now=now, deliver=deliver)).sent_count == 1
    assert delivered == [(101, [7])]
    db.query(ReminderRuleRun).delete()
    db.query(ReminderRule).delete()
    db.add(
        Opportunity(
            id=11,
            team_id=101,
            customer_id=1,
            opportunity_number="V2-11",
            opportunity_name="测试",
            owner_id="7",
            creator_id="7",
            status=0,
            total_amount=100,
            user_count=1,
            unit_price=100,
            license_type="SUBSCRIPTION",
            purchase_type="NEW",
            expected_closing_date=now.date(),
        )
    )
    db.add(
        Contract(
            id=61,
            team_id=101,
            contract_number="C-61",
            contract_name="本团队合同",
            customer_id=1,
            opportunity_id=11,
            user_count=1,
            total_amount=100,
            license_type="SUBSCRIPTION",
            standard_unit_price=100,
            owner_id="7",
            creator_id="7",
        )
    )
    db.add(
        Contract(
            id=62,
            team_id=202,
            contract_number="C-62",
            contract_name="他团队合同",
            customer_id=1,
            opportunity_id=11,
            user_count=1,
            total_amount=100,
            license_type="SUBSCRIPTION",
            standard_unit_price=100,
            owner_id="7",
            creator_id="7",
        )
    )
    db.add(
        PaymentPlan(
            id=71,
            team_id=101,
            contract_id=61,
            plan_number="P-71",
            stage_name="首款",
            planned_amount=100,
            due_date=now.date() + timedelta(days=2),
            status="PENDING",
        )
    )
    db.add(
        PaymentPlan(
            id=72,
            team_id=101,
            contract_id=62,
            plan_number="P-72",
            stage_name="首款",
            planned_amount=100,
            due_date=now.date() + timedelta(days=2),
            status="PENDING",
        )
    )
    _v2_rule(
        db,
        "payment_plan",
        [
            {"field": "due_date", "operator": "due_in_days", "value": 2},
            {"field": "contract_owner", "operator": "not_empty", "value": True},
        ],
        recipients=["contract_owner"],
    )
    assert asyncio.run(execute_due_reminder_rules(db, now=now, deliver=deliver)).sent_count == 1
    assert db.query(ReminderRuleRun).one().object_id == 71
    assert delivered == [(101, [7]), (101, [7])]
    db.query(ReminderRuleRun).delete()
    db.query(ReminderRule).delete()
    db.add(User(id=8, email="other@example.com", name="他团队成员", status=UserStatus.ACTIVE))
    db.add(UserTeam(user_id=8, team_id=202))
    _v2_rule(
        db,
        "payment_plan",
        [{"field": "status", "operator": "in", "value": ["PENDING"]}],
        recipients=["user:7", "user:8"],
    )
    assert asyncio.run(execute_due_reminder_rules(db, now=now, deliver=deliver)).sent_count == 1
    assert db.query(ReminderRuleRun).one().object_id == 71
    assert delivered[-1] == (101, [7])
    assert len(delivered) == 3


def test_v2_invalid_stored_conditions_do_not_send_or_interrupt_other_rules():
    import asyncio

    db = _session()
    now = datetime(2026, 9, 23, 9, 30)
    db.add(User(id=7, email="owner@example.com", name="负责人", status=UserStatus.ACTIVE))
    db.add(UserTeam(user_id=7, team_id=101))
    db.add(Customer(id=1, team_id=101, account_name="客户", city="上海", owner_id="7", creator_id="7"))
    db.add_all(
        [
            ReminderRule(
                id=90,
                team_id=101,
                name="坏条件",
                object_type="customer",
                trigger="schedule",
                enabled=True,
                rule={
                    "version": 2,
                    "object_type": "customer",
                    "trigger": "schedule",
                    "trigger_time": "09:30",
                    "conditions": [{"field": "owner", "operator": "not_empty", "value": False}],
                    "recipients": ["owner"],
                    "message_template": "不应发",
                    "channels": ["feishu"],
                },
            ),
            ReminderRule(
                id=91,
                team_id=101,
                name="坏时间",
                object_type="customer",
                trigger="schedule",
                enabled=True,
                rule={
                    "version": 2,
                    "object_type": "customer",
                    "trigger": "schedule",
                    "trigger_time": ["09:30"],
                    "conditions": [{"field": "status", "operator": "in", "value": ["FOLLOWING"]}],
                    "recipients": ["owner"],
                    "message_template": "不应发",
                    "channels": ["feishu"],
                },
            ),
            ReminderRule(
                id=92,
                team_id=101,
                name="状态提醒",
                object_type="customer",
                trigger="schedule",
                enabled=True,
                rule={
                    "version": 2,
                    "object_type": "customer",
                    "trigger": "schedule",
                    "trigger_time": "09:30",
                    "conditions": [{"field": "status", "operator": "in", "value": ["FOLLOWING"]}],
                    "recipients": ["owner"],
                    "message_template": "应发送",
                    "channels": ["feishu"],
                },
            ),
        ]
    )
    db.commit()
    messages = []
    result = asyncio.run(
        execute_due_reminder_rules(
            db, now=now, deliver=lambda _team, _ids, content: messages.append(content) or {"sent": 1, "skipped": 0}
        )
    )
    assert result.sent_count == 1
    assert messages == ["应发送"]

"""Unit tests for ascending ordering and latest-limit truncation protection on follow-ups and customer activities."""

from datetime import datetime, timedelta

from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud.customer_activity import CustomerActivityCRUD
from app.crud.lead import LeadFollowUpCRUD
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.lead import FollowUpMethod, Lead, LeadFollowUp


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _make_session():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerActivity.__table__,
            Lead.__table__,
            LeadFollowUp.__table__,
        ],
    )
    return engine, sessionmaker(bind=engine)()


def test_customer_activity_get_by_customer_id_returns_asc_with_id_tiebreaker():
    engine, db = _make_session()
    try:
        customer = Customer(team_id=1, account_name="排序测试客户", city="上海", creator_id="u1")
        db.add(customer)
        db.flush()

        t_early = datetime(2026, 11, 1, 9, 0, 0)
        t_tie = datetime(2026, 11, 2, 10, 0, 0)
        t_late = datetime(2026, 11, 3, 11, 0, 0)

        # Insert out of chronological order to verify SQL ordering rather than insertion order
        a_late = CustomerActivity(
            team_id=1,
            customer_id=customer.id,
            activity_kind="PHONE_CALL",
            source_content="最晚",
            occurred_at=t_late,
            creator_id="u1",
            owner_id="u1",
        )
        a_tie_first = CustomerActivity(
            team_id=1,
            customer_id=customer.id,
            activity_kind="PHONE_CALL",
            source_content="同时间戳-1",
            occurred_at=t_tie,
            creator_id="u1",
            owner_id="u1",
        )
        a_tie_second = CustomerActivity(
            team_id=1,
            customer_id=customer.id,
            activity_kind="PHONE_CALL",
            source_content="同时间戳-2",
            occurred_at=t_tie,
            creator_id="u1",
            owner_id="u1",
        )
        a_early = CustomerActivity(
            team_id=1,
            customer_id=customer.id,
            activity_kind="PHONE_CALL",
            source_content="最早",
            occurred_at=t_early,
            creator_id="u1",
            owner_id="u1",
        )
        db.add_all([a_late, a_tie_first, a_tie_second, a_early])
        db.commit()

        crud = CustomerActivityCRUD()
        activities, total = crud.get_by_customer_id(db, customer_id=customer.id, team_id=1)

        assert total == 4
        assert [a.id for a in activities] == [a_early.id, a_tie_first.id, a_tie_second.id, a_late.id]
        assert [a.source_content for a in activities] == ["最早", "同时间戳-1", "同时间戳-2", "最晚"]

        latest = crud.get_latest_by_customer_id(db, customer_id=customer.id, team_id=1)
        assert latest is not None
        assert latest.id == a_late.id
    finally:
        db.close()
        engine.dispose()


def test_customer_activity_get_by_customer_id_keeps_newest_limit_in_asc_order():
    engine, db = _make_session()
    try:
        customer = Customer(team_id=1, account_name="截断保护客户", city="北京", creator_id="u1")
        db.add(customer)
        db.flush()

        base = datetime(2026, 1, 1, 8, 0, 0)
        created = []
        for idx in range(1, 106):
            act = CustomerActivity(
                team_id=1,
                customer_id=customer.id,
                activity_kind="PHONE_CALL",
                source_content=f"活动-{idx}",
                occurred_at=base + timedelta(minutes=idx),
                creator_id="u1",
                owner_id="u1",
            )
            db.add(act)
            created.append(act)
        db.commit()

        activities, total = CustomerActivityCRUD().get_by_customer_id(db, customer_id=customer.id, team_id=1)

        assert total == 105
        assert len(activities) == 100
        assert activities[0].source_content == "活动-6"
        assert activities[-1].source_content == "活动-105"
        assert [a.source_content for a in activities] == [f"活动-{i}" for i in range(6, 106)]
    finally:
        db.close()
        engine.dispose()


def test_lead_follow_up_get_by_lead_id_returns_asc_with_id_tiebreaker():
    engine, db = _make_session()
    try:
        lead = Lead(
            team_id=1,
            lead_name="排序测试线索",
            source="官网",
            city="上海",
            contact_name="张三",
            contact_phone="13800138000",
            creator_id="u1",
        )
        db.add(lead)
        db.flush()

        t_early = datetime(2026, 11, 1, 9, 0, 0)
        t_tie = datetime(2026, 11, 2, 10, 0, 0)
        t_late = datetime(2026, 11, 3, 11, 0, 0)

        f_late = LeadFollowUp(
            team_id=1,
            lead_id=lead.id,
            content="最晚",
            method=FollowUpMethod.PHONE,
            creator_id="u1",
            created_time=t_late,
        )
        f_tie_first = LeadFollowUp(
            team_id=1,
            lead_id=lead.id,
            content="同时间戳-1",
            method=FollowUpMethod.WECHAT,
            creator_id="u1",
            created_time=t_tie,
        )
        f_tie_second = LeadFollowUp(
            team_id=1,
            lead_id=lead.id,
            content="同时间戳-2",
            method=FollowUpMethod.WECHAT,
            creator_id="u1",
            created_time=t_tie,
        )
        f_early = LeadFollowUp(
            team_id=1,
            lead_id=lead.id,
            content="最早",
            method=FollowUpMethod.PHONE,
            creator_id="u1",
            created_time=t_early,
        )
        db.add_all([f_late, f_tie_first, f_tie_second, f_early])
        db.commit()

        follow_ups = LeadFollowUpCRUD().get_by_lead_id(db, lead_id=lead.id)

        assert [f.id for f in follow_ups] == [f_early.id, f_tie_first.id, f_tie_second.id, f_late.id]
        assert [f.content for f in follow_ups] == ["最早", "同时间戳-1", "同时间戳-2", "最晚"]
    finally:
        db.close()
        engine.dispose()


def test_lead_follow_up_get_by_lead_id_keeps_newest_limit_in_asc_order():
    engine, db = _make_session()
    try:
        lead = Lead(
            team_id=1,
            lead_name="截断保护线索",
            source="官网",
            city="上海",
            contact_name="李四",
            contact_phone="13900139000",
            creator_id="u1",
        )
        db.add(lead)
        db.flush()

        base = datetime(2026, 1, 1, 8, 0, 0)
        for idx in range(1, 106):
            db.add(
                LeadFollowUp(
                    team_id=1,
                    lead_id=lead.id,
                    content=f"跟进-{idx}",
                    method=FollowUpMethod.PHONE,
                    creator_id="u1",
                    created_time=base + timedelta(minutes=idx),
                )
            )
        db.commit()

        follow_ups = LeadFollowUpCRUD().get_by_lead_id(db, lead_id=lead.id)

        assert len(follow_ups) == 100
        assert follow_ups[0].content == "跟进-6"
        assert follow_ups[-1].content == "跟进-105"
        assert [f.content for f in follow_ups] == [f"跟进-{i}" for i in range(6, 106)]
    finally:
        db.close()
        engine.dispose()

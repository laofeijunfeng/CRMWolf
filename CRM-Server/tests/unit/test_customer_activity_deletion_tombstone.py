"""Regression tests for durable customer-activity deletion watermarks."""

from datetime import datetime

from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud.customer_activity import CustomerActivityCRUD
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def test_hard_delete_writes_tombstone_in_same_transaction():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(
        engine,
        tables=[Customer.__table__, CustomerActivity.__table__, CustomerActivityDeletionTombstone.__table__],
    )
    db = sessionmaker(bind=engine)()
    try:
        customer = Customer(team_id=2, account_name="删除测试客户", city="广州", creator_id="u1")
        db.add(customer)
        db.flush()
        activity = CustomerActivity(
            team_id=2,
            customer_id=customer.id,
            activity_kind="PHONE_CALL",
            source_content="已删除的跟进",
            occurred_at=datetime(2026, 8, 29, 10, 0),
            creator_id="u1",
            owner_id="u1",
            post_commit_revision=3,
        )
        db.add(activity)
        db.commit()
        activity_id = activity.id

        CustomerActivityCRUD().delete(db, activity, commit=False, deleted_by="u1")

        tombstone = (
            db.query(CustomerActivityDeletionTombstone)
            .filter(CustomerActivityDeletionTombstone.activity_id == activity_id)
            .one()
        )
        assert tombstone.customer_id == customer.id
        assert tombstone.team_id == 2
        assert tombstone.activity_revision == 3
        assert tombstone.deleted_by == "u1"
        assert db.query(CustomerActivity).filter(CustomerActivity.id == activity_id).one_or_none() is None

        db.commit()
        assert (
            db.query(CustomerActivityDeletionTombstone)
            .filter(CustomerActivityDeletionTombstone.activity_id == activity_id)
            .count()
            == 1
        )
    finally:
        db.close()
        engine.dispose()

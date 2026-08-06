from datetime import datetime, timedelta

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.crud.sales_commitment import follow_up_task_crud
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.sales_commitment import (
    DueAtGranularity,
    FollowUpTask,
    FollowUpTaskEvent,
    FollowUpTaskProjectionRun,
    FollowUpTaskReconciliationRun,
    FollowUpTaskSourceType,
    FollowUpTaskStatus,
    SalesCommitment,
)
from app.schemas.sales_commitment import FollowUpTaskInternalCreate
from app.services.task_reconciliation_service import task_reconciliation_service


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

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
            SalesCommitment.__table__,
            FollowUpTask.__table__,
            FollowUpTaskEvent.__table__,
            FollowUpTaskProjectionRun.__table__,
            FollowUpTaskReconciliationRun.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    _seed_customers_and_activity(session)
    session.commit()
    yield session
    session.close()
    engine.dispose()


def _seed_customers_and_activity(db_session) -> None:
    db_session.add_all([
        Customer(
            id=1,
            public_id="cus_11111111111111111111111111111111",
            team_id=1,
            account_name="测试客户",
            city="上海",
            owner_id="9",
            creator_id="9",
        ),
        Customer(
            id=2,
            public_id="cus_22222222222222222222222222222222",
            team_id=1,
            account_name="其它客户",
            city="北京",
            owner_id="9",
            creator_id="9",
        ),
        CustomerActivity(
            id=101,
            team_id=1,
            customer_id=1,
            activity_kind="PHONE_FOLLOW_UP",
            source_content="客户说预算已经通过。",
            summary="客户预算已通过。",
            occurred_at=datetime(2026, 8, 6, 10, 0, 0),
            owner_id="2",
            creator_id="2",
        ),
    ])


def _create_task(
    db_session,
    *,
    customer_id: int = 1,
    owner_id: str = "2",
    status: str = FollowUpTaskStatus.OPEN,
    due_at: datetime | None = None,
    task_hash: str = "task-hash",
) -> FollowUpTask:
    return follow_up_task_crud.create(
        db_session,
        FollowUpTaskInternalCreate(
            team_id=1,
            customer_id=customer_id,
            owner_id=owner_id,
            creator_id=owner_id,
            title="确认客户预算是否通过",
            description="客户说下周确认预算。",
            status=status,
            due_at=due_at or datetime(2026, 8, 5, 10, 0, 0),
            due_at_text="本周三",
            due_at_granularity=DueAtGranularity.DATETIME,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_activity_id=101,
            confidence=0.91,
            evidence_json={"quote": "客户说下周确认预算"},
            task_hash=task_hash,
        ),
    )


def test_reconciliation_candidates_return_same_owner_open_tasks_only_by_default(db_session):
    expected = _create_task(db_session, task_hash="expected")
    _create_task(db_session, owner_id="3", task_hash="cross-owner")
    _create_task(db_session, customer_id=2, task_hash="other-customer")
    completed = _create_task(db_session, task_hash="completed")
    follow_up_task_crud.complete(db_session, completed)
    _create_task(
        db_session,
        due_at=datetime(2026, 8, 6, 10, 0, 0) - timedelta(days=91),
        task_hash="too-old",
    )
    _create_task(
        db_session,
        due_at=datetime(2026, 8, 6, 10, 0, 0) + timedelta(days=31),
        task_hash="too-far",
    )

    result = task_reconciliation_service.list_candidates_for_activity(
        db_session,
        team_id=1,
        activity_id=101,
        anchor_at=datetime(2026, 8, 6, 10, 0, 0),
    )
    payload = result.to_dict()

    assert result.total == 1
    assert payload["items"][0]["public_id"] == expected.public_id
    assert payload["items"][0]["id"] == expected.public_id
    assert payload["items"][0]["auto_transition_eligible"] is True
    assert payload["items"][0]["candidate_reasons"] == ["same_customer", "open_task", "due_window", "same_owner"]
    assert "source_activity_id" not in payload["items"][0]
    assert payload["usage_policy"]["mutation"] == "forbidden"
    assert payload["run_public_id"].startswith("trr_")

    run = db_session.query(FollowUpTaskReconciliationRun).filter_by(public_id=payload["run_public_id"]).one()
    assert run.status == "SUCCESS"
    assert run.owner_id == "2"
    assert run.actor_id == "2"
    assert run.source_activity_id == 101
    assert run.candidate_public_ids_json == [expected.public_id]


def test_reconciliation_candidates_can_include_cross_owner_as_confirmation_only(db_session):
    same_owner = _create_task(db_session, task_hash="same-owner")
    cross_owner = _create_task(db_session, owner_id="3", task_hash="cross-owner")

    result = task_reconciliation_service.list_candidates_for_activity(
        db_session,
        team_id=1,
        activity_id=101,
        include_cross_owner=True,
        anchor_at=datetime(2026, 8, 6, 10, 0, 0),
    )
    items_by_id = {item.public_id: item for item in result.items}

    assert result.total == 2
    assert result.run_public_id is not None
    assert list(items_by_id) == [same_owner.public_id, cross_owner.public_id]
    assert items_by_id[same_owner.public_id].auto_transition_eligible is True
    assert items_by_id[cross_owner.public_id].auto_transition_eligible is False
    assert items_by_id[cross_owner.public_id].confirmation_required_reason == "CROSS_OWNER"
    assert "cross_owner_confirmation_only" in items_by_id[cross_owner.public_id].candidate_reasons

    run = db_session.query(FollowUpTaskReconciliationRun).filter_by(public_id=result.run_public_id).one()
    assert run.include_cross_owner is True
    assert run.filters_json["include_cross_owner"] is True
    assert run.candidate_public_ids_json == [same_owner.public_id, cross_owner.public_id]
    assert str(same_owner.id) not in run.candidate_public_ids_json
    assert str(cross_owner.id) not in run.candidate_public_ids_json


def test_reconciliation_candidate_retrieval_does_not_mutate_task_status(db_session):
    task = _create_task(db_session, task_hash="unchanged")

    task_reconciliation_service.list_candidates_for_activity(
        db_session,
        team_id=1,
        activity_id=101,
        anchor_at=datetime(2026, 8, 6, 10, 0, 0),
    )
    db_session.refresh(task)

    assert task.status == FollowUpTaskStatus.OPEN
    assert task.completed_at is None
    assert task.cancelled_at is None
    assert len(db_session.dirty) == 0


def test_reconciliation_candidate_retrieval_requires_existing_activity(db_session):
    with pytest.raises(ValueError, match="客户活动不存在"):
        task_reconciliation_service.list_candidates_for_activity(
            db_session,
            team_id=1,
            activity_id=999,
            anchor_at=datetime(2026, 8, 6, 10, 0, 0),
        )

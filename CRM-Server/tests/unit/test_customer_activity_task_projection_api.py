from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import customer_activities
from app.core import deps
from app.core.database import Base
from app.crud.customer_activity import customer_activity_crud
from app.crud.sales_commitment import (
    follow_up_task_crud,
    follow_up_task_event_crud,
    follow_up_task_projection_run_crud,
)
from app.models.customer import Customer, CustomerMember
from app.models.customer_activity import CustomerActivity
from app.models.customer_vector_document import CustomerVectorDocument
from app.models.sales_commitment import (
    FollowUpTask,
    FollowUpTaskConfirmationCase,
    FollowUpTaskEvent,
    FollowUpTaskEventType,
    FollowUpTaskProjectionRun,
    FollowUpTaskProjectionStatus,
    FollowUpTaskProjectionTrigger,
    FollowUpTaskStatus,
    SalesCommitment,
)
from app.services.follow_up_task_projection_service import (
    FollowUpTaskProjectionSkipReason,
    follow_up_task_projection_service,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerMember.__table__,
            CustomerActivity.__table__,
            CustomerVectorDocument.__table__,
            SalesCommitment.__table__,
            FollowUpTask.__table__,
            FollowUpTaskConfirmationCase.__table__,
            FollowUpTaskEvent.__table__,
            FollowUpTaskProjectionRun.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(
        Customer(
            id=1,
            public_id="cus_11111111111111111111111111111111",
            team_id=1,
            account_name="测试客户",
            city="上海",
            owner_id="1",
            creator_id="1",
        )
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session, monkeypatch):
    test_app = FastAPI()
    test_app.include_router(customer_activities.router, prefix="/api")
    customer = db_session.query(Customer).filter(Customer.id == 1).one()

    def _allow_customer_activity(customer_id, team_id, current_user, db):  # noqa: ARG001
        return customer

    async def _run_projection_now(*, activity_id, team_id, trigger_type, actor_id=None):
        follow_up_task_projection_service.run_activity_projection(
            db_session,
            activity_id=activity_id,
            team_id=team_id,
            trigger_type=trigger_type,
            actor_id=actor_id,
        )

    async def _noop_processing(activity_id, team_id):  # noqa: ARG001
        return None

    monkeypatch.setattr(customer_activities, "check_customer_activity_permission", _allow_customer_activity)
    monkeypatch.setattr(customer_activities, "_load_user_info", lambda db, user_id: None)  # noqa: ARG005
    monkeypatch.setattr(
        customer_activities.customer_activity_processing_service,
        "trigger_follow_up_task_projection",
        _run_projection_now,
    )
    monkeypatch.setattr(
        customer_activities.customer_activity_processing_service,
        "trigger_processing",
        _noop_processing,
    )
    monkeypatch.setattr(
        "app.crud.customer_activity._upsert_customer_activity_evidence",
        lambda db, activity: None,
    )
    monkeypatch.setattr(
        "app.crud.customer_activity._mark_customer_activity_evidence_deleted",
        lambda db, activity: None,
    )
    monkeypatch.setattr(
        "app.services.deal_journey_service.deal_journey_service.infer_for_customer",
        lambda db, customer_id, team_id: None,
    )
    monkeypatch.setattr(
        "app.services.deal_journey_service.deal_journey_service.record_event",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.operation_log_service.operation_log_service.log_customer_activity",
        lambda *args, **kwargs: None,
    )

    test_app.dependency_overrides[deps.get_db] = lambda: db_session
    test_app.dependency_overrides[deps.get_current_user_team] = lambda: 1
    test_app.dependency_overrides[deps.get_current_active_user] = lambda: SimpleNamespace(id=1, name="销售一", status="active")
    with TestClient(test_app) as test_client:
        yield test_client
    test_app.dependency_overrides.clear()


def _list_open_tasks(db_session, *, owner_id: str = "1"):
    rows, total = follow_up_task_crud.list_for_owner(
        db_session,
        team_id=1,
        owner_id=owner_id,
        statuses=[FollowUpTaskStatus.OPEN],
    )
    return rows, total


def _projection_runs(db_session, *, activity_id: int):
    rows, total = follow_up_task_projection_run_crud.list_by_source(
        db_session,
        team_id=1,
        source_type="CUSTOMER_ACTIVITY",
        source_activity_id=activity_id,
    )
    assert total == len(rows)
    return rows


def test_page_activity_create_with_explicit_next_step_creates_task_event_and_projection_run(client, db_session):
    response = client.post(
        "/api/v1/customer-activities/cus_11111111111111111111111111111111",
        json={
            "activity_kind": "PHONE_FOLLOW_UP",
            "source_content": "客户说下周看预算。",
            "next_action": "下周三回访预算进展",
            "next_follow_time": "2026-08-12T10:00:00",
            "occurred_at": "2026-08-06T09:00:00",
        },
    )

    assert response.status_code == 201
    activity_id = response.json()["id"]
    rows, total = _list_open_tasks(db_session)
    assert total == 1
    assert rows[0].title == "下周三回访预算进展"
    assert rows[0].owner_id == "1"
    assert rows[0].creator_id == "1"
    assert rows[0].source_activity_id == activity_id

    events, event_total = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=rows[0].id)
    runs = _projection_runs(db_session, activity_id=activity_id)
    assert event_total == 1
    assert events[0].event_type == FollowUpTaskEventType.CREATED
    assert len(runs) == 1
    assert runs[0].trigger_type == FollowUpTaskProjectionTrigger.ACTIVITY_CREATED_DETERMINISTIC
    assert runs[0].status == FollowUpTaskProjectionStatus.SUCCESS
    assert runs[0].created_task_ids_json == [rows[0].id]


def test_page_activity_create_without_structured_next_step_waits_for_ai_persistence(client, db_session):
    response = client.post(
        "/api/v1/customer-activities/cus_11111111111111111111111111111111",
        json={
            "activity_kind": "OTHER_FOLLOW_UP",
            "source_content": "客户说下周三可以电话聊预算，但页面没有单独填写下一步。",
            "occurred_at": "2026-08-06T09:30:00",
        },
    )

    assert response.status_code == 201
    activity_id = response.json()["id"]
    rows, total = _list_open_tasks(db_session)
    assert rows == []
    assert total == 0
    assert _projection_runs(db_session, activity_id=activity_id) == []

    customer_activity_crud.update_processed_content(
        db_session,
        activity_id,
        title="电话跟进",
        content_json={"content": "客户说下周三可以电话聊预算。"},
        summary="客户下周三可以电话聊预算。",
        next_action="下周三电话确认预算",
        next_follow_time=datetime(2026, 8, 12, 10, 0, 0),
        next_follow_time_source="AI_EXTRACTED",
    )
    result = follow_up_task_projection_service.run_activity_projection(
        db_session,
        activity_id=activity_id,
        team_id=1,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_STRUCTURED_COMPLETED,
        actor_id="1",
    )

    rows, total = _list_open_tasks(db_session)
    assert result.projection_run_status == FollowUpTaskProjectionStatus.SUCCESS
    assert total == 1
    assert rows[0].title == "下周三电话确认预算"
    assert rows[0].source_activity_id == activity_id
    runs = _projection_runs(db_session, activity_id=activity_id)
    assert len(runs) == 1
    assert runs[0].trigger_type == FollowUpTaskProjectionTrigger.ACTIVITY_STRUCTURED_COMPLETED
    assert runs[0].created_task_ids_json == [rows[0].id]


def test_agent_activity_creation_uses_same_customer_activity_api_projection_path(client, db_session):
    response = client.post(
        "/api/v1/customer-activities/cus_11111111111111111111111111111111",
        json={
            "activity_kind": "OTHER_FOLLOW_UP",
            "source_content": "Agent 记录：客户要求周五发试用账号。",
            "next_action": "周五发送试用账号",
            "next_follow_time": "2026-08-07T15:00:00",
            "next_follow_time_source": "AGENT",
            "occurred_at": "2026-08-06T10:00:00",
        },
    )

    assert response.status_code == 201
    rows, total = _list_open_tasks(db_session)
    assert total == 1
    assert rows[0].title == "周五发送试用账号"
    assert rows[0].due_at == datetime(2026, 8, 7, 15, 0, 0)
    assert _projection_runs(db_session, activity_id=response.json()["id"])[0].status == FollowUpTaskProjectionStatus.SUCCESS


def test_activity_update_clears_next_step_and_delete_cancel_open_task_with_runs(client, db_session):
    create_response = client.post(
        "/api/v1/customer-activities/cus_11111111111111111111111111111111",
        json={
            "activity_kind": "PHONE_FOLLOW_UP",
            "source_content": "客户让下周三继续跟进预算。",
            "next_action": "下周三继续跟进预算",
            "next_follow_time": "2026-08-12T10:00:00",
            "occurred_at": "2026-08-06T09:00:00",
        },
    )
    activity_id = create_response.json()["id"]
    task_id = _list_open_tasks(db_session)[0][0].id

    update_response = client.put(
        f"/api/v1/customer-activities/{activity_id}",
        json={"next_action": None, "next_follow_time": None},
    )

    assert update_response.status_code == 200
    task = follow_up_task_crud.get_by_id(db_session, task_id, team_id=1)
    assert task.status == FollowUpTaskStatus.CANCELLED
    runs = _projection_runs(db_session, activity_id=activity_id)
    assert runs[0].trigger_type == FollowUpTaskProjectionTrigger.ACTIVITY_UPDATED
    assert runs[0].status == FollowUpTaskProjectionStatus.SKIPPED
    assert runs[0].skip_reason == FollowUpTaskProjectionSkipReason.SOURCE_NEXT_STEP_REMOVED
    events, event_total = follow_up_task_event_crud.list_by_task(db_session, team_id=1, task_id=task_id)
    assert event_total == 2
    assert events[-1].event_type == FollowUpTaskEventType.CANCELLED

    second_create = client.post(
        "/api/v1/customer-activities/cus_11111111111111111111111111111111",
        json={
            "activity_kind": "PHONE_FOLLOW_UP",
            "source_content": "客户让周五确认采购流程。",
            "next_action": "周五确认采购流程",
            "next_follow_time": "2026-08-14T16:00:00",
            "occurred_at": "2026-08-06T11:00:00",
        },
    )
    second_activity_id = second_create.json()["id"]
    second_task_id = _list_open_tasks(db_session)[0][0].id

    delete_response = client.delete(f"/api/v1/customer-activities/{second_activity_id}")

    assert delete_response.status_code == 200
    deleted_task = follow_up_task_crud.get_by_id(db_session, second_task_id, team_id=1)
    assert deleted_task.status == FollowUpTaskStatus.CANCELLED
    assert customer_activity_crud.get_by_id(db_session, second_activity_id, team_id=1) is None
    delete_runs = _projection_runs(db_session, activity_id=second_activity_id)
    assert delete_runs[0].trigger_type == FollowUpTaskProjectionTrigger.ACTIVITY_DELETED
    assert delete_runs[0].status == FollowUpTaskProjectionStatus.SKIPPED
    assert delete_runs[0].skip_reason == FollowUpTaskProjectionSkipReason.SOURCE_ACTIVITY_DELETED

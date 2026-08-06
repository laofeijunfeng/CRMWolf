from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import follow_up_tasks
from app.core.database import Base
from app.crud.sales_commitment import (
    follow_up_task_crud,
    follow_up_task_projection_run_crud,
    sales_commitment_crud,
)
from app.models.customer import Customer, CustomerMember
from app.models.customer_activity import CustomerActivity
from app.models.customer_vector_document import CustomerVectorDocument
from app.models.sales_commitment import (
    DueAtGranularity,
    FollowUpTask,
    FollowUpTaskConfirmationCase,
    FollowUpTaskConfirmationPromptDelivery,
    FollowUpTaskEvent,
    FollowUpTaskEventType,
    FollowUpTaskLLMMatcherRun,
    FollowUpTaskProjectionRun,
    FollowUpTaskProjectionStatus,
    FollowUpTaskProjectionTrigger,
    FollowUpTaskReconciliationEvaluationRun,
    FollowUpTaskReconciliationRun,
    FollowUpTaskSourceType,
    FollowUpTaskStatus,
    FollowUpTaskTransitionPolicyDecisionLog,
    SalesCommitment,
)
from app.schemas.sales_commitment import (
    FollowUpTaskInternalCreate,
    FollowUpTaskProjectionRunInternalCreate,
    SalesCommitmentInternalCreate,
)
from app.services import follow_up_task_query_service


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
            FollowUpTaskEvent.__table__,
            FollowUpTaskProjectionRun.__table__,
            FollowUpTaskConfirmationCase.__table__,
            FollowUpTaskConfirmationPromptDelivery.__table__,
            FollowUpTaskTransitionPolicyDecisionLog.__table__,
            FollowUpTaskReconciliationRun.__table__,
            FollowUpTaskLLMMatcherRun.__table__,
            FollowUpTaskReconciliationEvaluationRun.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    _seed_customer_and_activity(session)
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def permission_codes(monkeypatch):
    codes: list[str] = ["customer:view:own"]

    def _fake_get_user_permissions(db, user_id, team_id=None):  # noqa: ARG001
        return [SimpleNamespace(code=code) for code in codes]

    monkeypatch.setattr(follow_up_tasks.permission_crud, "get_user_permissions", _fake_get_user_permissions)
    monkeypatch.setattr(
        follow_up_task_query_service.permission_crud,
        "get_user_permissions",
        _fake_get_user_permissions,
    )
    return codes


@pytest.fixture
def client(db_session, permission_codes):  # noqa: ARG001
    app = FastAPI()
    app.include_router(follow_up_tasks.router)
    app.include_router(follow_up_tasks.projection_router)
    app.include_router(follow_up_tasks.observability_router)
    app.dependency_overrides[follow_up_tasks.get_db] = lambda: db_session
    app.dependency_overrides[follow_up_tasks.get_current_user_team] = lambda: 1
    app.dependency_overrides[follow_up_tasks.get_current_active_user] = lambda: SimpleNamespace(
        id=2,
        name="售前",
        status="active",
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _seed_customer_and_activity(db):
    db.add(
        Customer(
            id=1,
            public_id="cus_11111111111111111111111111111111",
            team_id=1,
            account_name="测试客户",
            city="上海",
            owner_id="9",
            creator_id="9",
        )
    )
    db.add(
        CustomerMember(
            id=11,
            team_id=1,
            customer_id=1,
            user_id="2",
            member_role="PRESALES",
            access_level="FOLLOW_UP",
            created_by="9",
            is_active=True,
        )
    )
    db.add(
        CustomerActivity(
            id=101,
            team_id=1,
            customer_id=1,
            activity_kind="PHONE_FOLLOW_UP",
            title="电话确认预算",
            source_content="客户说下周三看预算。",
            summary="客户还在确认预算。",
            next_action="下周三回访预算进展",
            next_follow_time=datetime(2026, 8, 12, 10, 0, 0),
            occurred_at=datetime(2026, 8, 6, 9, 0, 0),
            owner_id="2",
            creator_id="2",
        )
    )


def _create_commitment(db):
    return sales_commitment_crud.create(
        db,
        SalesCommitmentInternalCreate(
            team_id=1,
            customer_id=1,
            owner_id="2",
            creator_id="2",
            title="跟进预算",
            content="下周三回访预算进展",
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_activity_id=101,
            due_at=datetime(2026, 8, 12, 10, 0, 0),
            due_at_text="下周三",
            due_at_granularity=DueAtGranularity.DATETIME,
            evidence_json={"activity_id": 101},
            commitment_hash="commitment-hash",
        ),
    )


def _create_task(db, *, task_id: int = 201, owner_id: str = "2", status: str = FollowUpTaskStatus.OPEN):
    commitment = _create_commitment(db)
    return follow_up_task_crud.create(
        db,
        FollowUpTaskInternalCreate(
            team_id=1,
            customer_id=1,
            commitment_id=commitment.id,
            owner_id=owner_id,
            creator_id=owner_id,
            title="下周三回访预算进展",
            description="客户还在确认预算。",
            status=status,
            due_at=datetime(2026, 8, 12, 10, 0, 0),
            due_at_text="下周三",
            due_at_granularity=DueAtGranularity.DATETIME,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_activity_id=101,
            confidence=0.92,
            evidence_json={"activity_id": 101, "quote": "客户说下周三看预算"},
            task_hash=f"task-hash-{task_id}",
        ),
    )


def _create_failed_projection_run(db):
    run = follow_up_task_projection_run_crud.create_running(
        db,
        FollowUpTaskProjectionRunInternalCreate(
            team_id=1,
            trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_STRUCTURED_COMPLETED,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_activity_id=101,
            actor_id="2",
            input_snapshot_hash="failed-input-hash",
        ),
    )
    return follow_up_task_projection_run_crud.mark_failed(
        db,
        run,
        error_message="LLM structured persistence timeout",
    )


def _create_transition_event(db, task, *, created_time: datetime):
    event = FollowUpTaskEvent(
        team_id=task.team_id,
        task_id=task.id,
        event_type=FollowUpTaskEventType.COMPLETED,
        actor_id=task.owner_id,
        source_type=task.source_type,
        source_activity_id=task.source_activity_id,
        source_public_id=task.source_public_id,
        previous_status=FollowUpTaskStatus.OPEN,
        new_status=FollowUpTaskStatus.COMPLETED,
        payload_json={
            "reason": "RECONCILIATION_TRANSITION_PLAN_EXECUTED",
            "plan_source": "unit_test_plan",
            "execution_kind": "automatic",
            "action": "COMPLETE",
            "task_public_id": task.public_id,
            "confidence": 0.94,
            "decision": "COMPLETE",
        },
        created_time=created_time,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def test_list_follow_up_tasks_returns_public_ids_and_customer_summary(client, db_session):
    task = _create_task(db_session)

    response = client.get("/v1/follow-up-tasks")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == task.public_id
    assert payload["items"][0]["public_id"] == task.public_id
    assert payload["items"][0]["customer"]["id"] == "cus_11111111111111111111111111111111"
    assert payload["items"][0]["customer"]["name"] == "测试客户"
    assert payload["items"][0]["owner_id"] == "2"
    assert "source_activity_id" not in payload["items"][0]
    assert len(payload["customer_summary"]) == 1
    assert payload["customer_summary"][0]["customer"]["id"] == "cus_11111111111111111111111111111111"
    assert payload["usage_policy"]["task_state_source"] == "mysql"


def test_customer_arrangement_returns_readonly_customer_scope_without_internal_ids(client, db_session):
    task = _create_task(db_session, owner_id="9")

    response = client.get("/v1/follow-up-tasks/customer-arrangements/cus_11111111111111111111111111111111")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == task.public_id
    assert payload["items"][0]["owner_id"] == "9"
    assert "source_activity_id" not in payload["items"][0]
    assert payload["filters"]["owner_scope"] == "customer"
    assert payload["display_policy"]["mode"] == "readonly"
    assert "public_id" in payload["display_policy"]["id_policy"]


def test_projection_runs_by_activity_requires_debug_permission_and_returns_public_ids(
    client,
    db_session,
    permission_codes,
):
    task = _create_task(db_session)
    run = follow_up_task_projection_run_crud.create_running(
        db_session,
        FollowUpTaskProjectionRunInternalCreate(
            team_id=1,
            trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_CREATED_DETERMINISTIC,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_activity_id=101,
            actor_id="2",
            input_snapshot_hash="input-hash",
        ),
    )
    follow_up_task_projection_run_crud.mark_success(
        db_session,
        run,
        created_task_ids=[task.id],
        projection_hash="projection-hash",
    )

    denied = client.get("/v1/follow-up-task-projection-runs/by-activity/101")
    assert denied.status_code == 403

    permission_codes[:] = ["follow_up_task:view:team"]
    response = client.get("/v1/follow-up-task-projection-runs/by-activity/101")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["id"] == run.public_id
    assert payload[0]["created_task_ids"] == [task.public_id]
    assert payload[0]["status"] == FollowUpTaskProjectionStatus.SUCCESS
    assert "created_task_ids_json" not in payload[0]
    assert "source_activity_id" not in payload[0]


def test_failed_projection_runs_can_be_listed_and_retried_by_public_id(client, db_session, permission_codes):
    permission_codes[:] = ["follow_up_task:view:team"]
    failed_run = _create_failed_projection_run(db_session)

    failed_response = client.get("/v1/follow-up-task-projection-runs/failed")

    assert failed_response.status_code == 200
    failed_payload = failed_response.json()
    assert failed_payload[0]["id"] == failed_run.public_id
    assert failed_payload[0]["status"] == FollowUpTaskProjectionStatus.FAILED
    assert failed_payload[0]["error_message"] == "LLM structured persistence timeout"

    retry_response = client.post(f"/v1/follow-up-task-projection-runs/{failed_run.public_id}/retry")

    assert retry_response.status_code == 200
    retry_payload = retry_response.json()
    assert retry_payload["id"] != failed_run.public_id
    assert retry_payload["status"] == FollowUpTaskProjectionStatus.SUCCESS
    assert retry_payload["attempt_count"] == 2
    assert len(retry_payload["created_task_ids"]) == 1

    rows, total = follow_up_task_crud.list_for_owner(
        db_session,
        team_id=1,
        owner_id="2",
        statuses=[FollowUpTaskStatus.OPEN],
    )
    assert total == 1
    assert rows[0].public_id == retry_payload["created_task_ids"][0]


def test_transition_observability_summary_requires_debug_permission_and_returns_aggregates(
    client,
    db_session,
    permission_codes,
):
    task = _create_task(db_session)
    _create_transition_event(db_session, task, created_time=datetime(2026, 8, 6, 10, 0, 0))

    denied = client.get(
        "/v1/follow-up-task-transition-observability/summary",
        params={
            "start_at": "2026-08-06T00:00:00",
            "end_at": "2026-08-07T00:00:00",
            "owner_scope": "mine",
        },
    )
    assert denied.status_code == 403

    permission_codes[:] = ["follow_up_task:view:team"]
    response = client.get(
        "/v1/follow-up-task-transition-observability/summary",
        params={
            "start_at": "2026-08-06T00:00:00",
            "end_at": "2026-08-07T00:00:00",
            "owner_scope": "mine",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filters"]["owner_scope"] == "mine"
    assert payload["owner_id"] == "2"
    assert payload["transition_events"]["automatic_transition_events"] == 1
    assert payload["transition_events"]["automatic_by_action"] == {"COMPLETE": 1}
    assert payload["confirmation_cases"]["created_cases"] == 0
    assert payload["prompt_deliveries"]["total_deliveries"] == 0
    assert payload["policy_decisions"]["total_decisions"] == 0
    assert payload["reconciliation_runs"]["total_runs"] == 0
    assert payload["llm_matcher_runs"]["total_runs"] == 0
    assert payload["evaluation_runs"]["total_runs"] == 0
    assert payload["evaluation_runs"]["latest_run"] is None
    assert payload["metric_gaps"] == []
    assert "task_id" not in str(payload)

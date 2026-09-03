"""HTTP contract tests for durable page-form customer-activity submission."""

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
from app.models.customer import Customer, CustomerMember
from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_ai_job import CustomerActivityAIJob
from app.services.customer_activity_contracts import (
    CustomerActivityAIJobStatus,
    CustomerActivityEffectivenessStatus,
    CustomerActivityProcessingStatus,
    CustomerActivitySubmissionSource,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def form_submission_context(monkeypatch):
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
            CustomerMember.__table__,
            CustomerActivity.__table__,
            CustomerActivityAIJob.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    customer = Customer(
        id=1,
        public_id="cus_11111111111111111111111111111111",
        team_id=1,
        account_name="测试客户",
        city="上海",
        owner_id="1",
        creator_id="1",
    )
    session.add(customer)
    session.commit()

    app = FastAPI()
    app.include_router(customer_activities.router, prefix="/api")
    monkeypatch.setattr(customer_activities, "check_customer_activity_permission", lambda *args: customer)
    monkeypatch.setattr(customer_activities, "_load_user_info", lambda db, user_id: None)
    monkeypatch.setattr(
        customer_activities.customer_activity_write_service.ai_job_service,
        "kick",
        lambda request: None,
    )
    monkeypatch.setattr(
        "app.crud.customer_activity._upsert_customer_activity_evidence",
        lambda db, activity, **kwargs: None,
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
    app.dependency_overrides[deps.get_db] = lambda: session
    app.dependency_overrides[deps.get_current_user_team] = lambda: 1
    app.dependency_overrides[deps.get_current_active_user] = lambda: SimpleNamespace(
        id=1,
        name="销售一",
        status="active",
    )

    with TestClient(app) as client:
        yield client, session

    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def test_page_form_submission_returns_pending_activity_and_durable_ai_job(form_submission_context):
    client, session = form_submission_context

    response = client.post(
        "/api/v1/customer-activities/cus_11111111111111111111111111111111",
        json={
            "activity_kind": "PHONE_FOLLOW_UP",
            "source_content": "客户确认下周安排产品测试。",
            "submission_source": "AGENT",
            "submission_id": "form-submit-001",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["submission_source"] == CustomerActivitySubmissionSource.FORM.value
    assert payload["processing_status"] == CustomerActivityProcessingStatus.PENDING.value
    assert payload["effectiveness_status"] == CustomerActivityEffectivenessStatus.PENDING.value
    assert payload["effectiveness_score"] is None
    assert payload["durable_work"] == {
        "activity_revision": 1,
        "ai_job_public_id": payload["durable_work"]["ai_job_public_id"],
        "post_commit_job_public_id": None,
        "customer_intelligence_request_id": None,
        "opportunity_suggestion_job_public_id": None,
        "customer_intelligence_scope": None,
        "customer_intelligence_schedule_error": None,
        "customer_intelligence_event": None,
    }
    assert payload["durable_work"]["ai_job_public_id"].startswith("caij_")

    activity = session.query(CustomerActivity).one()
    job = session.query(CustomerActivityAIJob).one()
    assert job.activity_id == activity.id
    assert job.activity_revision == 1
    assert job.submission_source == CustomerActivitySubmissionSource.FORM.value
    assert job.status == CustomerActivityAIJobStatus.QUEUED.value


def test_page_form_submission_replays_same_submission_without_duplicate_activity_or_job(form_submission_context):
    client, session = form_submission_context
    payload = {
        "activity_kind": "PHONE_FOLLOW_UP",
        "source_content": "客户确认下周安排产品测试。",
        "submission_id": "form-submit-replay-001",
    }

    first = client.post(
        "/api/v1/customer-activities/cus_11111111111111111111111111111111",
        json=payload,
    )
    second = client.post(
        "/api/v1/customer-activities/cus_11111111111111111111111111111111",
        json=payload,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["durable_work"]["ai_job_public_id"] == first.json()["durable_work"]["ai_job_public_id"]
    assert session.query(CustomerActivity).count() == 1
    assert session.query(CustomerActivityAIJob).count() == 1


def test_page_form_submission_rejects_same_submission_with_changed_payload(form_submission_context):
    client, session = form_submission_context
    endpoint = "/api/v1/customer-activities/cus_11111111111111111111111111111111"

    first = client.post(
        endpoint,
        json={
            "activity_kind": "PHONE_FOLLOW_UP",
            "source_content": "第一次内容",
            "submission_id": "form-submit-conflict-001",
        },
    )
    conflict = client.post(
        endpoint,
        json={
            "activity_kind": "PHONE_FOLLOW_UP",
            "source_content": "第二次不同内容",
            "submission_id": "form-submit-conflict-001",
        },
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert "submission_id" in conflict.text
    assert session.query(CustomerActivity).count() == 1
    assert session.query(CustomerActivityAIJob).count() == 1


def test_agent_finalized_endpoint_rejects_low_or_invalid_final_score(form_submission_context):
    client, session = form_submission_context
    endpoint = "/api/v1/customer-activities/cus_11111111111111111111111111111111/agent-finalized"
    base_payload = {
        "activity_kind": "PHONE_FOLLOW_UP",
        "source_content": "客户确认下周安排产品测试。",
        "effectiveness_score": 59,
        "effectiveness_is_valid": True,
        "effectiveness_reason": "信息不足",
    }

    low_score_response = client.post(endpoint, json=base_payload)
    assert low_score_response.status_code == 422
    assert "Agent 最终评分未通过" in low_score_response.text

    invalid_score_payload = {**base_payload, "effectiveness_score": 80, "effectiveness_is_valid": False}
    invalid_score_response = client.post(endpoint, json=invalid_score_payload)
    assert invalid_score_response.status_code == 422
    assert "Agent 最终评分未通过" in invalid_score_response.text
    assert session.query(CustomerActivity).count() == 0


def test_legacy_activity_mutation_and_processing_routes_are_not_registered():
    routes = {(route.path, tuple(sorted(route.methods or ()))) for route in customer_activities.router.routes}

    assert ("/v1/customer-activities/{activity_id}", ("PUT",)) not in routes
    assert ("/v1/customer-activities/{activity_id}/next-time", ("PATCH",)) not in routes
    assert ("/v1/customer-activities/{activity_id}/process", ("POST",)) not in routes
    assert ("/v1/customer-activities/{activity_id}/evaluate", ("POST",)) not in routes

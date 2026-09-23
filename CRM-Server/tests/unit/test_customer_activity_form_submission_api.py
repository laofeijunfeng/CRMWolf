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
from app.models.agent import AgentIdempotencyKey, AgentIdempotencyStatus, AgentSession
from app.models.customer_activity_ai_job import CustomerActivityAIJob
from app.models.customer_activity_post_commit_job import CustomerActivityPostCommitJob
from app.models.customer_intelligence_run import CustomerIntelligenceRun
from app.models.customer_opportunity_suggestion_job import CustomerOpportunitySuggestionJob
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
            AgentSession.__table__,
            AgentIdempotencyKey.__table__,
            CustomerActivityPostCommitJob.__table__,
            CustomerIntelligenceRun.__table__,
            CustomerOpportunitySuggestionJob.__table__,
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


def test_exact_agent_submission_receipt_uses_original_revision_evidence(form_submission_context):
    client, db = form_submission_context
    from app.services.agent.tools.service import CRMAgentToolService

    submission_id = "create_customer_activity:3:outside-first-page"
    request_hash = CRMAgentToolService._hash_json({"customer_id": "cus_11111111111111111111111111111111"})
    db.add(AgentSession(id=3, session_key="session-3", team_id=1, user_id=1))
    db.add(AgentIdempotencyKey(team_id=1, user_id=1, session_id=3, action_key=submission_id,
                               status=AgentIdempotencyStatus.DISPATCHED, request_hash=request_hash))
    activity = CustomerActivity(team_id=1, customer_id=1, creator_id="1", owner_id="1",
                                activity_kind="PHONE_FOLLOW_UP", source_content="original",
                                submission_source="AGENT", submission_id=submission_id,
                                activity_revision=2, title="edited later")
    db.add(activity)
    db.flush()
    db.add(CustomerActivityPostCommitJob(team_id=1, activity_id=activity.id, activity_revision=1,
                                         trigger_type="ACTIVITY_CREATED_DETERMINISTIC", actor_id="1",
                                         public_id="pcj-original", run_id="post-run", graph_thread_id="thread"))
    from app.services.customer_intelligence_event_service import customer_intelligence_event_service
    event_key = customer_intelligence_event_service._event_key(
        team_id=1, trigger_type="customer_activity_created", source_type="customer_activity",
        source_object_id=f"{activity.id}:revision:1",
    )
    event = {"event_key": event_key, "trigger_type": "customer_activity_created",
             "team_id": 1, "tenant_id": 1, "customer_id": 1, "actor_id": "1",
             "source": {"source_type": "customer_activity", "source_object_id": str(activity.id),
                        "source_version": 1}, "payload": {"activity_revision": 1}}
    db.add(CustomerIntelligenceRun(team_id=1, tenant_id=1, customer_id=1, actor_id="1",
                                   run_key="run-original", request_id="business-event-original",
                                   event_key=event_key, event_json=event,
                                   trigger_type="customer_activity_created", scope="partial"))
    db.add(CustomerOpportunitySuggestionJob(team_id=1, activity_id=activity.id,
                                             activity_revision=1, submission_source="AGENT",
                                             public_id="cosj-original", run_id="suggestion-run", graph_thread_id="thread"))
    db.commit()
    endpoint = f"/api/v1/customer-activities/cus_11111111111111111111111111111111/agent-submissions/{submission_id}"
    response = client.get(endpoint, params={"agent_session_id": 3, "request_hash": request_hash})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == activity.id
    assert data["durable_work"]["activity_revision"] == 1
    assert data["durable_work"]["post_commit_job_public_id"] == "pcj-original"
    assert data["durable_work"]["customer_intelligence_request_id"] == "business-event-original"
    assert data["durable_work"]["opportunity_suggestion_job_public_id"] == "cosj-original"
    assert "title" not in data  # mutable revision-2 state cannot masquerade as the original snapshot
    assert client.get(endpoint, params={"agent_session_id": 4, "request_hash": request_hash}).status_code == 404
    assert client.get(endpoint, params={"agent_session_id": 3, "request_hash": "0" * 64}).status_code == 404

    db.query(CustomerIntelligenceRun).delete()
    db.commit()
    missing = client.get(endpoint, params={"agent_session_id": 3, "request_hash": request_hash})
    assert missing.status_code == 409
    assert "durable_work" not in missing.json()

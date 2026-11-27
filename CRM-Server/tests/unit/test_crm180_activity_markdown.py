from __future__ import annotations

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
from app.crud.customer_activity_ai_job import customer_activity_ai_job_crud
from app.models.customer import Customer, CustomerMember
from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_ai_job import CustomerActivityAIJob
from app.models.customer_activity_post_commit_job import CustomerActivityPostCommitJob
from app.models.customer_opportunity_suggestion_job import CustomerOpportunitySuggestionJob
from app.models.customer_vector_document import CustomerVectorDocument
from app.models.lead import FollowUpMethod, LeadFollowUp
from app.models.sales_commitment import FollowUpTaskConfirmationCase
from app.services.assistant.ui_projection import _activity_facts
from app.services.customer_activity_ai_job_service import customer_activity_ai_job_service
from app.services.customer_activity_contracts import (
    CustomerActivityAIJobStatus,
    CustomerActivityEffectivenessStatus,
    CustomerActivityProcessingStatus,
    CustomerActivitySubmissionSource,
)
from app.services.customer_activity_write_service import (
    CustomerActivityFinalization,
    customer_activity_write_service,
)


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
            CustomerMember.__table__,
            CustomerActivity.__table__,
            CustomerActivityAIJob.__table__,
            CustomerActivityPostCommitJob.__table__,
            CustomerOpportunitySuggestionJob.__table__,
            CustomerVectorDocument.__table__,
            LeadFollowUp.__table__,
            FollowUpTaskConfirmationCase.__table__,
        ],
    )
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = session_local()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_customer(db, *, team_id: int = 1, owner_id: int = 10) -> Customer:
    customer = Customer(
        team_id=team_id,
        public_id=f"cus_{team_id:032d}",
        account_name="星辰科技",
        city="上海",
        owner_id=str(owner_id),
        creator_id=str(owner_id),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def test_ui_projection_preserves_markdown_in_activity_summary():
    markdown_summary = "## 沟通要点\n- **预算确认**：50 万\n- 下周安排技术演示"
    preview = SimpleNamespace(
        activity_kind="PHONE_FOLLOW_UP",
        customer_name="星辰科技",
        title=None,
        summary=markdown_summary,
        content_json={},
        next_action="下周安排技术演示",
        next_follow_time=None,
        next_follow_time_text=None,
        channel_status_label="已识别",
        channel_status="detected",
        channel_source_text=None,
        channel_options=[],
        comparison=None,
        context_evidence=[],
        opportunity_name=None,
        opportunity_stage=None,
        context_status=None,
        change_summary=None,
        context_notices=[],
        ignored_noise_summary=None,
        score=85,
        score_reason="要点清晰",
    )
    facts = _activity_facts(preview, editable=False)
    summary_fact = next(item for item in facts if item.key == "summary")
    assert summary_fact.value == markdown_summary
def test_retry_ai_processing_increments_revision_skips_stale_job_and_is_idempotent(db_session):
    customer = _seed_customer(db_session)
    activity = CustomerActivity(
        team_id=customer.team_id,
        customer_id=customer.id,
        activity_kind="PHONE_FOLLOW_UP",
        source_content="客户反馈预算已批复，下周三约技术评审",
        summary="客户反馈预算已批复",
        occurred_at=datetime(2026, 11, 20, 10, 0, 0),
        creator_id="10",
        owner_id="10",
        submission_source=CustomerActivitySubmissionSource.FORM.value,
        processing_status=CustomerActivityProcessingStatus.FAILED.value,
        processing_error="LLM timeout",
        effectiveness_status=CustomerActivityEffectivenessStatus.FAILED.value,
        effectiveness_error_message="LLM timeout",
        activity_revision=1,
    )
    db_session.add(activity)
    db_session.commit()
    db_session.refresh(activity)

    stale_job = customer_activity_ai_job_crud.enqueue(
        db_session,
        team_id=customer.team_id,
        activity_id=activity.id,
        activity_revision=1,
        submission_source=CustomerActivitySubmissionSource.FORM.value,
        commit=True,
    )

    result = customer_activity_write_service.retry_ai_processing(
        db_session,
        activity_id=activity.id,
        team_id=customer.team_id,
    )
    db_session.refresh(activity)
    db_session.refresh(stale_job)

    assert result.activity.activity_revision == 2
    assert result.activity.processing_status == CustomerActivityProcessingStatus.PENDING.value
    assert result.activity.processing_error is None
    assert result.activity.effectiveness_status == CustomerActivityEffectivenessStatus.PENDING.value
    assert result.activity.effectiveness_error_message is None
    assert result.ai_job is not None
    assert stale_job.status == CustomerActivityAIJobStatus.SKIPPED.value

    # Idempotent retry while PENDING does not bump revision or create another job
    idempotent = customer_activity_write_service.retry_ai_processing(
        db_session,
        activity_id=activity.id,
        team_id=customer.team_id,
    )
    assert idempotent.activity.activity_revision == 2
    assert idempotent.ai_job is None


def test_retry_ai_endpoint_enforces_team_isolation_and_returns_pending(db_session, monkeypatch):
    customer = _seed_customer(db_session, team_id=1, owner_id=10)
    activity = CustomerActivity(
        team_id=1,
        customer_id=customer.id,
        activity_kind="PHONE_FOLLOW_UP",
        source_content="原始跟进内容",
        summary="原始跟进内容",
        occurred_at=datetime(2026, 11, 20, 10, 0, 0),
        creator_id="10",
        owner_id="10",
        submission_source=CustomerActivitySubmissionSource.FORM.value,
        processing_status=CustomerActivityProcessingStatus.FAILED.value,
        processing_error="upstream 502",
        effectiveness_status=CustomerActivityEffectivenessStatus.FAILED.value,
        activity_revision=1,
    )
    db_session.add(activity)
    db_session.commit()
    db_session.refresh(activity)

    kicked: list[object] = []
    monkeypatch.setattr(customer_activity_write_service, "kick", lambda res: kicked.append(res))
    monkeypatch.setattr(customer_activities, "_load_user_info", lambda db, user_id: None)
    monkeypatch.setattr(
        customer_activities,
        "check_customer_activity_permission",
        lambda customer_id, team_id, current_user, db: None,
    )

    app = FastAPI()
    app.include_router(customer_activities.router, prefix="/api")
    current_user = SimpleNamespace(id=10, team_id=1, role="MEMBER", is_admin=False)
    app.dependency_overrides[deps.get_db] = lambda: db_session
    app.dependency_overrides[deps.get_current_active_user] = lambda: current_user
    app.dependency_overrides[deps.get_current_user_team] = lambda: current_user.team_id

    client = TestClient(app)
    resp = client.post(f"/api/v1/customer-activities/{activity.id}/retry-ai")
    assert resp.status_code == 200
    body = resp.json()
    assert body["processing_status"] == "PENDING"
    assert body["processing_error"] is None
    assert len(kicked) == 1

    # Different team cannot retry
    current_user.team_id = 2
    forbidden_resp = client.post(f"/api/v1/customer-activities/{activity.id}/retry-ai")
    assert forbidden_resp.status_code == 404
def test_cutover_migration_enqueues_pending_ai_job_and_enforces_6a_and_q3a(db_session):
    customer = _seed_customer(db_session, team_id=1, owner_id=10)
    occurred = datetime(2026, 10, 1, 9, 30, 0)
    lead_follow_up = LeadFollowUp(
        team_id=1,
        lead_id=77,
        method=FollowUpMethod.PHONE,
        content="客户反馈需要私有化部署方案，关注数据合规。",
        creator_id="10",
        created_time=occurred,
    )
    db_session.add(lead_follow_up)
    db_session.commit()

    migrated = customer_activity_crud.migrate_from_lead(
        db_session,
        lead_id=77,
        new_customer_id=customer.id,
        team_id=1,
        commit=True,
    )
    assert len(migrated) == 1
    activity = migrated[0]
    assert activity.submission_source == CustomerActivitySubmissionSource.CUTOVER_MIGRATION.value
    assert activity.processing_status == CustomerActivityProcessingStatus.PENDING.value
    assert activity.effectiveness_status == CustomerActivityEffectivenessStatus.PENDING.value

    requests = customer_activity_ai_job_service.enqueue_pending_migrated_for_customer(
        db_session,
        team_id=1,
        customer_id=customer.id,
    )
    db_session.commit()
    assert len(requests) == 1

    ai_job = db_session.query(CustomerActivityAIJob).filter_by(public_id=requests[0].job_public_id).one()
    ai_job.status = CustomerActivityAIJobStatus.RUNNING.value
    ai_job.lease_token = "lease-test-token"
    db_session.commit()

    # Finalize from AI with attempted next_action / next_follow_time backfill — 6A MUST lock them
    finalized = customer_activity_write_service.finalize_pending_from_ai(
        db_session,
        activity_id=activity.id,
        team_id=1,
        expected_activity_revision=activity.activity_revision,
        ai_job_public_id=requests[0].job_public_id,
        lease_token="lease-test-token",
        finalization=CustomerActivityFinalization(
            title="私有化部署沟通",
            content_json={"content": "### 核心需求\n- 私有化部署\n- 数据合规"},
            summary="### 核心需求\n- 私有化部署\n- 数据合规",
            next_action="AI试图回填的下一步",
            next_action_source="AI_EXTRACTED",
            next_follow_time=datetime(2026, 12, 1, 10, 0, 0),
            next_follow_time_source="AI_EXTRACTED",
            effectiveness_score=85,
            effectiveness_is_valid=True,
            effectiveness_reason="关键需求清晰",
            effectiveness_detail_json=None,
        ),
        post_commit_trigger_type="ACTIVITY_CREATED",
        actor_id="10",
    )
    updated = finalized.activity
    assert updated.processing_status == CustomerActivityProcessingStatus.COMPLETED.value
    assert updated.summary == "### 核心需求\n- 私有化部署\n- 数据合规"
    # Boundary 6A: historical fields untouched / locked
    assert updated.occurred_at == occurred
    assert updated.creator_id == "10"
    assert updated.owner_id == "10"
    assert updated.activity_kind == "PHONE_FOLLOW_UP"
    assert updated.next_action is None
    assert updated.next_action_source is None
    assert updated.next_follow_time is None
    assert updated.next_follow_time_source is None
    # Q3-A: no post-commit follow-up task projection job or opportunity suggestion job
    assert finalized.post_commit_job is None
    assert finalized.opportunity_suggestion_job is None
    assert db_session.query(CustomerActivityPostCommitJob).count() == 0
    assert db_session.query(CustomerOpportunitySuggestionJob).count() == 0

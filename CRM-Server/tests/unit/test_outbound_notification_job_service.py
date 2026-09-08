"""Behavior tests for durable outbound approval / Feishu notifications."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.approval import ApprovalStatus
from app.models.outbound_notification_job import (
    OutboundNotificationEventType,
    OutboundNotificationJob,
    OutboundNotificationJobStatus,
)
from app.services.outbound_notification_job_service import (
    OutboundNotificationJobRequest,
    OutboundNotificationJobService,
)
from app.utils.time import business_now


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def job_session_factory(monkeypatch):
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[OutboundNotificationJob.__table__])
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr("app.services.outbound_notification_job_service.SessionLocal", Session)
    monkeypatch.setattr(
        "app.services.outbound_notification_job_service.get_settings",
        lambda: SimpleNamespace(
            OUTBOUND_NOTIFICATION_LEASE_SECONDS=60,
            OUTBOUND_NOTIFICATION_MAX_ATTEMPTS=2,
            OUTBOUND_NOTIFICATION_RETRY_BASE_SECONDS=1,
        ),
    )
    yield Session
    engine.dispose()


def _approval(*, status=ApprovalStatus.PENDING, current_node_id=4, approval_id=10, business_id=9):
    return SimpleNamespace(
        id=approval_id,
        status=status,
        current_node_id=current_node_id,
        current_node=SimpleNamespace(
            node_name="财务审批",
            approve_role="FINANCE",
            notify_user_ids=None,
        ),
        flow=SimpleNamespace(flow_name="回款审批"),
        submitter_id="11",
        submitter_name="张三",
        business_type="PAYMENT",
        business_id=business_id,
    )


def test_enqueue_in_transaction_does_not_commit(job_session_factory):
    """The outbox write joins the caller's transaction and must not commit it.

    SQLite treats RELEASE of an outermost SAVEPOINT as COMMIT, so this test
    spies ``Session.commit`` instead of asserting rollback isolation.
    """
    session = job_session_factory()
    commit_calls = 0
    original_commit = session.commit

    def tracking_commit(*args, **kwargs):
        nonlocal commit_calls
        commit_calls += 1
        return original_commit(*args, **kwargs)

    session.commit = tracking_commit
    request = OutboundNotificationJobService().enqueue_in_transaction(
        session,
        team_id=1,
        event_type=OutboundNotificationEventType.APPROVAL_PENDING,
        idempotency_key="1:pending:10:4",
        recipient_user_ids=[11],
        business_type="PAYMENT",
        business_id=9,
        approval_id=10,
        node_id=4,
    )

    assert request is not None
    assert commit_calls == 0
    job = session.query(OutboundNotificationJob).one()
    assert job.public_id == request.job_public_id
    assert job.event_type == OutboundNotificationEventType.APPROVAL_PENDING
    session.close()


def test_duplicate_pending_enqueue_is_idempotent(job_session_factory):
    session = job_session_factory()
    service = OutboundNotificationJobService()
    first = service.enqueue_in_transaction(
        session,
        team_id=1,
        event_type=OutboundNotificationEventType.APPROVAL_PENDING,
        idempotency_key="1:pending:10:4",
        recipient_user_ids=[11],
        business_type="PAYMENT",
        business_id=9,
        approval_id=10,
        node_id=4,
    )
    second = service.enqueue_in_transaction(
        session,
        team_id=1,
        event_type=OutboundNotificationEventType.APPROVAL_PENDING,
        idempotency_key="1:pending:10:4",
        recipient_user_ids=[12],
        business_type="PAYMENT",
        business_id=9,
        approval_id=10,
        node_id=4,
    )
    session.commit()

    assert first is not None
    assert second is not None
    assert first.job_public_id == second.job_public_id
    assert session.query(OutboundNotificationJob).count() == 1
    session.close()


def test_empty_recipients_do_not_write_a_job(job_session_factory):
    session = job_session_factory()
    request = OutboundNotificationJobService().enqueue_in_transaction(
        session,
        team_id=1,
        event_type=OutboundNotificationEventType.APPROVAL_PENDING,
        idempotency_key="1:pending:10:4",
        recipient_user_ids=[],
        business_type="PAYMENT",
        business_id=9,
        approval_id=10,
        node_id=4,
    )
    session.commit()

    assert request is None
    assert session.query(OutboundNotificationJob).count() == 0
    session.close()


def test_enqueue_after_commit_persists_outside_caller_session(job_session_factory):
    session = job_session_factory()
    request = OutboundNotificationJobService().enqueue_after_commit(
        session,
        team_id=1,
        event_type=OutboundNotificationEventType.APPROVAL_ISSUED,
        idempotency_key="1:issued:INVOICE:7",
        recipient_user_ids=[11],
        business_type="INVOICE",
        business_id=7,
        approval_id=3,
    )
    session.close()

    other = job_session_factory()
    job = other.query(OutboundNotificationJob).filter_by(public_id=request.job_public_id).one()
    assert job.event_type == OutboundNotificationEventType.APPROVAL_ISSUED
    other.close()


def test_kick_without_running_event_loop_is_best_effort(job_session_factory):
    OutboundNotificationJobService().kick(
        OutboundNotificationJobRequest(job_public_id="onj_sync_endpoint", team_id=1)
    )


def test_reminder_jobs_use_unique_idempotency_keys(job_session_factory):
    session = job_session_factory()
    service = OutboundNotificationJobService()
    approval = _approval()
    first = service.enqueue_reminder(session, approval=approval, team_id=1, recipient_user_ids=[11])
    second = service.enqueue_reminder(session, approval=approval, team_id=1, recipient_user_ids=[11])
    session.commit()

    assert first is not None
    assert second is not None
    assert first.job_public_id != second.job_public_id
    assert session.query(OutboundNotificationJob).count() == 2
    session.close()


def test_requeue_resets_failed_and_exhausted_jobs(job_session_factory, monkeypatch):
    session = job_session_factory()
    service = OutboundNotificationJobService()
    approval = _approval()
    monkeypatch.setattr(
        "app.services.outbound_notification_job_service.role_crud.get_by_code",
        lambda db, code: SimpleNamespace(id=8),
    )
    monkeypatch.setattr(
        "app.services.outbound_notification_job_service.role_crud.get_role_users",
        lambda db, role_id, team_id: [SimpleNamespace(id=11)],
    )
    request = service.enqueue_pending_for_approval(session, approval=approval, team_id=1)
    job = session.query(OutboundNotificationJob).filter_by(public_id=request.job_public_id).one()
    job.status = OutboundNotificationJobStatus.EXHAUSTED
    job.attempt_count = 5
    session.commit()

    requeued = service.requeue_pending(session, approval=approval, team_id=1)
    session.commit()
    persisted = session.query(OutboundNotificationJob).filter_by(public_id=requeued.job_public_id).one()

    assert requeued.job_public_id == request.job_public_id
    assert persisted.status == OutboundNotificationJobStatus.QUEUED
    assert persisted.attempt_count == 0
    session.close()


@pytest.mark.asyncio
async def test_run_sends_pending_notification_through_feishu_service(job_session_factory, monkeypatch):
    session = job_session_factory()
    request = OutboundNotificationJobService().enqueue_in_transaction(
        session,
        team_id=1,
        event_type=OutboundNotificationEventType.APPROVAL_PENDING,
        idempotency_key="1:pending:10:4",
        recipient_user_ids=[11],
        business_type="PAYMENT",
        business_id=9,
        approval_id=10,
        node_id=4,
        actor_id="11",
    )
    session.commit()
    session.close()

    captured = {}

    class FakeAdapter:
        def get_entity(self, db, business_id, team_id):
            return SimpleNamespace(id=business_id)

        def get_name(self, entity):
            return "回款#9"

    async def fake_notify(**kwargs):
        captured.update(kwargs)
        return {"success": 1, "failed": 0, "skipped": 0}

    monkeypatch.setattr(
        "app.services.outbound_notification_job_service.approval_crud.get_by_id",
        lambda db, approval_id, team_id: _approval(),
    )
    monkeypatch.setattr("app.services.outbound_notification_job_service.get_adapter", lambda business_type: FakeAdapter())
    monkeypatch.setattr("app.services.outbound_notification_job_service.get_approval_action_path", lambda business_type: "/payments")
    monkeypatch.setattr(
        "app.services.outbound_notification_job_service.get_approval_card_fields",
        lambda db, business_type, entity: {"金额": "100"},
    )
    monkeypatch.setattr(
        "app.services.outbound_notification_job_service.get_approval_customer_name",
        lambda db, business_type, entity: "客户A",
    )
    monkeypatch.setattr("app.services.outbound_notification_job_service.get_approval_type_name", lambda business_type: "回款")
    monkeypatch.setattr(
        "app.services.outbound_notification_job_service.feishu_notification_service.notify_approval_pending",
        fake_notify,
    )

    result = await OutboundNotificationJobService().run(request)

    assert result["execution_status"] == "COMPLETED"
    assert result["success"] is True
    assert captured["user_ids"] == [11]
    assert captured["entity_name"] == "回款#9"
    assert captured["node_name"] == "财务审批"
    session = job_session_factory()
    persisted = session.query(OutboundNotificationJob).filter_by(public_id=request.job_public_id).one()
    assert persisted.status == OutboundNotificationJobStatus.COMPLETED
    session.close()


@pytest.mark.asyncio
async def test_pending_job_skips_when_approval_node_changed(job_session_factory, monkeypatch):
    session = job_session_factory()
    request = OutboundNotificationJobService().enqueue_in_transaction(
        session,
        team_id=1,
        event_type=OutboundNotificationEventType.APPROVAL_PENDING,
        idempotency_key="1:pending:10:4",
        recipient_user_ids=[11],
        business_type="PAYMENT",
        business_id=9,
        approval_id=10,
        node_id=4,
    )
    session.commit()
    session.close()

    monkeypatch.setattr(
        "app.services.outbound_notification_job_service.approval_crud.get_by_id",
        lambda db, approval_id, team_id: _approval(current_node_id=99),
    )

    result = await OutboundNotificationJobService().run(request)

    assert result["execution_status"] == "SKIPPED"
    assert result["skip_reason"] == "NODE_CHANGED"
    session = job_session_factory()
    persisted = session.query(OutboundNotificationJob).filter_by(public_id=request.job_public_id).one()
    assert persisted.status == OutboundNotificationJobStatus.SKIPPED
    session.close()


@pytest.mark.asyncio
async def test_pending_job_skips_when_approval_is_no_longer_pending(job_session_factory, monkeypatch):
    session = job_session_factory()
    request = OutboundNotificationJobService().enqueue_in_transaction(
        session,
        team_id=1,
        event_type=OutboundNotificationEventType.APPROVAL_REMINDER,
        idempotency_key="1:reminder:10:4:abc",
        recipient_user_ids=[11],
        business_type="PAYMENT",
        business_id=9,
        approval_id=10,
        node_id=4,
    )
    session.commit()
    session.close()

    monkeypatch.setattr(
        "app.services.outbound_notification_job_service.approval_crud.get_by_id",
        lambda db, approval_id, team_id: _approval(status=ApprovalStatus.APPROVED),
    )

    result = await OutboundNotificationJobService().run(request)

    assert result["execution_status"] == "SKIPPED"
    assert result["skip_reason"] == "APPROVAL_NOT_PENDING"


@pytest.mark.asyncio
async def test_failed_delivery_retries_then_exhausts(job_session_factory, monkeypatch):
    session = job_session_factory()
    request = OutboundNotificationJobService().enqueue_in_transaction(
        session,
        team_id=1,
        event_type=OutboundNotificationEventType.APPROVAL_APPROVED,
        idempotency_key="1:approval_approved:10",
        recipient_user_ids=[11],
        business_type="PAYMENT",
        business_id=9,
        approval_id=10,
    )
    session.commit()
    session.close()

    class FakeAdapter:
        def get_entity(self, db, business_id, team_id):
            return SimpleNamespace(id=business_id)

        def get_name(self, entity):
            return "回款#9"

    async def boom(**kwargs):
        raise RuntimeError("feishu unavailable")

    monkeypatch.setattr("app.services.outbound_notification_job_service.get_adapter", lambda business_type: FakeAdapter())
    monkeypatch.setattr("app.services.outbound_notification_job_service.get_approval_action_path", lambda business_type: "/payments")
    monkeypatch.setattr(
        "app.services.outbound_notification_job_service.get_approval_card_fields",
        lambda db, business_type, entity: {},
    )
    monkeypatch.setattr(
        "app.services.outbound_notification_job_service.get_approval_customer_name",
        lambda db, business_type, entity: None,
    )
    monkeypatch.setattr("app.services.outbound_notification_job_service.get_approval_type_name", lambda business_type: "回款")
    monkeypatch.setattr(
        "app.services.outbound_notification_job_service.approval_crud.get_by_id",
        lambda db, approval_id, team_id: _approval(status=ApprovalStatus.APPROVED),
    )
    monkeypatch.setattr(
        "app.services.outbound_notification_job_service.feishu_notification_service.notify_approval_approved",
        boom,
    )

    first = await OutboundNotificationJobService().run(request)
    assert first["execution_status"] == "FAILED"
    assert first["retryable"] is True

    session = job_session_factory()
    persisted = session.query(OutboundNotificationJob).filter_by(public_id=request.job_public_id).one()
    persisted.next_attempt_at = business_now() - timedelta(seconds=1)
    session.commit()
    session.close()

    second = await OutboundNotificationJobService().run(request)
    assert second["execution_status"] == "RETRIES_EXHAUSTED"
    session = job_session_factory()
    persisted = session.query(OutboundNotificationJob).filter_by(public_id=request.job_public_id).one()
    assert persisted.status == OutboundNotificationJobStatus.EXHAUSTED
    session.close()


def test_queue_committed_enqueues_and_kicks(job_session_factory, monkeypatch):
    session = job_session_factory()
    kicked = []
    monkeypatch.setattr(
        OutboundNotificationJobService,
        "kick",
        lambda self, request: kicked.append(request),
    )

    request = OutboundNotificationJobService().queue_committed(
        session,
        team_id=1,
        event_type=OutboundNotificationEventType.ACCOUNT_CREATED,
        business_type="CUSTOMER",
        business_id=9,
        recipient_user_ids=[11],
        payload_json={"account_name": "客户A", "contact_name": "张三"},
    )
    session.close()

    assert request is not None
    assert kicked == [request]
    other = job_session_factory()
    job = other.query(OutboundNotificationJob).filter_by(public_id=request.job_public_id).one()
    assert job.event_type == OutboundNotificationEventType.ACCOUNT_CREATED
    assert job.recipient_user_ids == [11]
    other.close()


def test_queue_committed_does_not_raise_without_recipients(job_session_factory, monkeypatch):
    session = job_session_factory()
    kicked = []
    monkeypatch.setattr(
        OutboundNotificationJobService,
        "kick",
        lambda self, request: kicked.append(request),
    )

    request = OutboundNotificationJobService().queue_committed(
        session,
        team_id=1,
        event_type=OutboundNotificationEventType.LEAD_CLAIMED,
        business_type="LEAD",
        business_id=3,
        recipient_user_ids=[],
        payload_json={"lead_name": "线索A"},
    )
    session.commit()

    assert request is None
    assert kicked == [None]
    assert session.query(OutboundNotificationJob).count() == 0
    session.close()


@pytest.mark.asyncio
async def test_run_delivers_business_event_without_adapter(job_session_factory, monkeypatch):
    session = job_session_factory()
    request = OutboundNotificationJobService().enqueue_in_transaction(
        session,
        team_id=1,
        event_type=OutboundNotificationEventType.OPPORTUNITY_WON,
        idempotency_key="1:opportunity_won:9",
        recipient_user_ids=[11],
        business_type="OPPORTUNITY",
        business_id=9,
        payload_json={
            "opportunity_name": "商机A",
            "customer_name": "客户A",
            "actual_amount": 120000,
        },
    )
    session.commit()
    session.close()

    captured = {}

    async def fake_notify(db, team_id, user_ids, **kwargs):
        captured.update({"team_id": team_id, "user_ids": list(user_ids), **kwargs})
        return {"success": 1, "failed": 0, "skipped": 0}

    def boom(business_type):
        raise AssertionError("business events must not rebuild approval cards")

    monkeypatch.setattr(
        "app.services.outbound_notification_job_service.feishu_notification_service.notify_opportunity_won",
        fake_notify,
    )
    monkeypatch.setattr("app.services.outbound_notification_job_service.get_adapter", boom)

    result = await OutboundNotificationJobService().run(request)

    assert result["execution_status"] == "COMPLETED"
    assert result["success"] is True
    assert captured["user_ids"] == [11]
    assert captured["opportunity_name"] == "商机A"
    assert captured["customer_name"] == "客户A"
    session = job_session_factory()
    persisted = session.query(OutboundNotificationJob).filter_by(public_id=request.job_public_id).one()
    assert persisted.status == OutboundNotificationJobStatus.COMPLETED
    session.close()


@pytest.mark.asyncio
async def test_unknown_business_event_is_skipped(job_session_factory, monkeypatch):
    monkeypatch.setattr(
        OutboundNotificationEventType,
        "BUSINESS",
        frozenset({*OutboundNotificationEventType.BUSINESS, "not_a_real_event"}),
    )
    session = job_session_factory()
    result = await OutboundNotificationJobService()._deliver(
        session,
        {
            "event_type": "not_a_real_event",
            "team_id": 1,
            "recipient_user_ids": [11],
            "payload_json": {},
        },
    )
    session.close()
    assert result["execution_status"] == "SKIPPED"
    assert result["skip_reason"] == "UNKNOWN_EVENT_TYPE"

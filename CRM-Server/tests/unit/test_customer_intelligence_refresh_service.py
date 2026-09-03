from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine, text, true
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.agent_async_operation import (
    AgentAsyncOperation,
    AgentAsyncOperationEvent,
    AgentAsyncOperationStatus,
)
from app.models.customer import Customer
from app.models.customer_intelligence_run import CustomerIntelligenceRun, CustomerIntelligenceRunStatus
from app.models.customer_profile_projection import CustomerProfileCurrent, CustomerProfileProjectionVersion
from app.services.agent.async_operation_service import AgentAsyncOperationService
from app.services.agent.customer_intelligence_graph import build_customer_intelligence_graph_config
from app.services.customer_intelligence_event_service import (
    CustomerIntelligenceEvent,
    CustomerIntelligenceEventService,
    CustomerIntelligenceSource,
)
from app.services.customer_intelligence_refresh_service import (
    AgentAsyncOperationBinding,
    CustomerIntelligenceCommittedEventRequest,
    CustomerIntelligenceRefreshRequest,
    CustomerIntelligenceRefreshService,
)
from app.services.customer_profile_projection_service import CustomerProfileProjectionService
from app.services.customer_intelligence_run_service import (
    CustomerIntelligenceRunClaim,
    CustomerIntelligenceRunClaimStatus,
    CustomerIntelligenceRunInput,
    CustomerIntelligenceRunLeaseMutation,
    CustomerIntelligenceRunLeaseMutationStatus,
    CustomerIntelligenceRunService,
)
from app.utils.time import business_now


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


class FakeBackgroundTask:
    def __init__(self):
        self.callbacks = []

    def add_done_callback(self, callback):
        self.callbacks.append(callback)


class FakeGraphService:
    def __init__(self, *, should_fail=False):
        self.calls = []
        self.should_fail = should_fail

    async def stream_events(self, input_state):
        self.calls.append(input_state)
        if self.should_fail:
            raise RuntimeError("graph failed")
        event = input_state["event"]
        route = (
            "refresh_profile"
            if event.trigger_type in {"customer_created", "customer_converted_from_lead"}
            else "refresh_profile"
        )
        yield {
            "kind": "result",
            "result": {
                "route": route,
                "profile_projection_result": {"success": True},
            },
        }


class FakeEventService:
    def __init__(self):
        self.calls = []
        self._durable_event_codec = CustomerIntelligenceEventService()

    def from_dict(self, payload):
        return self._durable_event_codec.from_dict(payload)

    def manual_refresh_requested(self, **kwargs):
        self.calls.append(kwargs)
        return CustomerIntelligenceEvent(
            event_key="manual-event-1",
            trigger_type="manual_refresh_requested",
            tenant_id=kwargs["team_id"],
            team_id=kwargs["team_id"],
            customer_id=kwargs["customer_id"],
            occurred_at=kwargs["occurred_at"],
            source=CustomerIntelligenceSource(
                source_type="manual_refresh",
                source_object_id=kwargs["request_id"],
                business_object_type="customer",
                business_object_id=str(kwargs["customer_id"]),
            ),
            summary="用户手动刷新客户智能档案",
            payload={"refresh_scope": kwargs["refresh_scope"]},
            actor_id=kwargs["actor_id"],
        )

    def batch_rebuild_requested(self, **kwargs):
        self.calls.append(kwargs)
        return CustomerIntelligenceEvent(
            event_key=f"batch-event-{kwargs['customer_id']}",
            trigger_type="customer_intelligence_batch_rebuild_requested",
            tenant_id=kwargs["team_id"],
            team_id=kwargs["team_id"],
            customer_id=kwargs["customer_id"],
            occurred_at=kwargs["occurred_at"],
            source=CustomerIntelligenceSource(
                source_type="batch_rebuild",
                source_object_id=kwargs["request_id"],
                business_object_type="customer",
                business_object_id=str(kwargs["customer_id"]),
            ),
            summary="批量重建客户智能档案",
            payload={
                "refresh_scope": kwargs["refresh_scope"],
                "request_id": kwargs["request_id"],
            },
            actor_id=kwargs["actor_id"],
        )

    def historical_backfill_requested(self, **kwargs):
        self.calls.append(kwargs)
        return CustomerIntelligenceEvent(
            event_key=f"historical-backfill-event-{kwargs['customer_id']}",
            trigger_type="customer_intelligence_historical_backfill_requested",
            tenant_id=kwargs["team_id"],
            team_id=kwargs["team_id"],
            customer_id=kwargs["customer_id"],
            occurred_at=kwargs["occurred_at"],
            source=CustomerIntelligenceSource(
                source_type="historical_backfill",
                source_object_id=kwargs["request_id"],
                business_object_type="customer",
                business_object_id=str(kwargs["customer_id"]),
            ),
            summary="系统自动补齐历史客户智能档案",
            payload={
                "refresh_scope": kwargs["refresh_scope"],
                "request_id": kwargs["request_id"],
            },
            actor_id=None,
        )

    def customer_lifecycle_refresh_requested(self, **kwargs):
        self.calls.append(kwargs)
        return CustomerIntelligenceEvent(
            event_key="lifecycle-event-1",
            trigger_type=kwargs["trigger_type"],
            tenant_id=kwargs["team_id"],
            team_id=kwargs["team_id"],
            customer_id=kwargs["customer_id"],
            occurred_at=kwargs["occurred_at"],
            source=CustomerIntelligenceSource(
                source_type="customer",
                source_object_id=str(kwargs["customer_id"]),
                business_object_type="customer",
                business_object_id=str(kwargs["customer_id"]),
            ),
            summary="客户已创建，刷新客户智能档案",  # noqa: RUF001
            payload={
                "refresh_scope": "full",
                "source_lead_id": kwargs["source_lead_id"],
                "request_id": kwargs["request_id"],
            },
            actor_id=kwargs["actor_id"],
        )

    def business_object_changed(self, **kwargs):
        self.calls.append(kwargs)
        return CustomerIntelligenceEvent(
            event_key="business-object-change-1",
            trigger_type=kwargs["trigger_type"],
            tenant_id=kwargs["team_id"],
            team_id=kwargs["team_id"],
            customer_id=kwargs["customer_id"],
            occurred_at=kwargs["occurred_at"],
            source=CustomerIntelligenceSource(
                source_type=kwargs["source_type"],
                source_object_id=str(kwargs["source_id"]),
                business_object_type=kwargs["source_type"],
                business_object_id=str(kwargs["source_id"]),
            ),
            summary=kwargs["summary"],
            payload=kwargs["payload"] or {},
            actor_id=kwargs["actor_id"],
        )


def _business_event() -> CustomerIntelligenceEvent:
    return CustomerIntelligenceEvent(
        event_key="contact-event-1",
        trigger_type="customer_contact_updated",
        tenant_id=2,
        team_id=2,
        customer_id=101,
        occurred_at=None,
        source=CustomerIntelligenceSource(
            source_type="customer_contact",
            source_object_id="601",
            business_object_type="contact",
            business_object_id="601",
        ),
        summary="客户联系人已更新: 张总",
        payload={"name": "张总", "is_primary": True},
        actor_id="9",
    )


def _add_published_profile(db, *, customer_id: int, team_id: int = 2, profile_version: int = 1) -> None:
    version = CustomerProfileProjectionVersion(
        id=400 + customer_id,
        team_id=team_id,
        customer_id=customer_id,
        schema_version="v2",
        profile_version=profile_version,
        publication_status="PUBLISHED",
        current_situation_json={"summary": "已有结构化档案"},
        current_journeys_json=[],
        important_changes_json=[],
        long_term_context_json={},
        follow_up_process_json=[],
        recorded_follow_ups_json=[],
        evidence_refs_json=[],
        source_watermark_json={},
        source_watermark_hash="a" * 64,
        fact_watermark=0,
        journey_watermark=0,
        task_watermark=0,
        commitment_watermark=0,
        graph_version="customer-profile-v2",
        content_hash="b" * 64,
    )
    db.add(version)
    db.flush()
    db.add(
        CustomerProfileCurrent(
            id=500 + customer_id,
            team_id=team_id,
            customer_id=customer_id,
            current_profile_version_id=version.id,
            last_successful_version=profile_version,
        )
    )


class FakeProfileProjectionService:
    def __init__(self):
        self.stale_calls = []
        self.updating_calls = []
        self.failed_calls = []
        self.current = SimpleNamespace(profile_status="NOT_READY", stale_reason=None, active_run_id=None)

    def ensure_current(self, db, *, team_id, customer_id):
        return self.current

    def mark_stale(self, db, **kwargs):
        self.stale_calls.append({"db": db, **kwargs})
        self.current.profile_status = "STALE"
        self.current.stale_reason = kwargs.get("reason")
        return self.current

    def mark_updating(self, db, **kwargs):
        self.updating_calls.append({"db": db, **kwargs})
        self.current.profile_status = "UPDATING"
        self.current.active_run_id = kwargs.get("run_id")
        return self.current

    def mark_failed(self, db, **kwargs):
        self.failed_calls.append({"db": db, **kwargs})
        self.current.profile_status = "FAILED"
        self.current.active_run_id = None
        self.current.stale_reason = kwargs.get("reason")
        return self.current


@pytest.fixture(autouse=True)
def _fake_default_profile_projection_service(monkeypatch):
    projection_service = FakeProfileProjectionService()
    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.customer_profile_projection_service",
        projection_service,
    )
    return projection_service


class FakeSession:
    def __init__(self):
        self.closed = False
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True

    class _NestedTransaction:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    def begin_nested(self):
        return self._NestedTransaction()


class FakeOperationProjector:
    def project_run(self, db, *, run, operation_public_id=None):
        return None

    def reconcile(self, db, *, team_id, limit=200):
        return SimpleNamespace(candidates=0, projected=0)


class FakeRunService:
    def __init__(self):
        self.pending = []
        self.running = []
        self.succeeded = []
        self.failed = []
        self.retryable = []
        self._runs = {}

    @staticmethod
    def _new_run(run_input, *, status=CustomerIntelligenceRunStatus.PENDING):
        return SimpleNamespace(
            id=len(run_input.request_id),
            request_id=run_input.request_id,
            event_key=run_input.event.event_key,
            event_json=run_input.event.to_dict(),
            tenant_id=run_input.event.tenant_id,
            team_id=run_input.event.team_id,
            customer_id=run_input.event.customer_id,
            actor_id=run_input.event.actor_id,
            trigger_type=run_input.event.trigger_type,
            scope=run_input.scope,
            status=status,
            attempt_count=0,
            max_attempts=run_input.max_attempts,
            lease_token=None,
            lease_expires_at=None,
            route=None,
            result_json={},
            visible_trace_json=[],
            error_message=None,
            next_retry_at=None,
            created_time=datetime.now(),
            started_time=None,
            finished_time=None,
        )

    def ensure_pending(self, db, run_input):
        self.pending.append({"db": db, "run_input": run_input})
        return self._runs.setdefault(run_input.request_id, self._new_run(run_input))

    def claim_for_execution(self, db, run_input, *, lease_seconds=300, now=None):
        run = self.ensure_pending(db, run_input)
        run.status = CustomerIntelligenceRunStatus.RUNNING
        run.attempt_count += 1
        run.lease_token = f"lease-{run_input.request_id}"
        self.running.append({"db": db, "run_input": run_input})
        return CustomerIntelligenceRunClaim(
            CustomerIntelligenceRunClaimStatus.CLAIMED,
            run,
            run.lease_token,
        )

    def mark_succeeded_if_lease_owner(self, db, run_input, *, lease_token, result):
        run = self._runs[run_input.request_id]
        run.status = CustomerIntelligenceRunStatus.SUCCESS
        run.route = result.get("route")
        run.result_json = dict(result)
        run.visible_trace_json = list(result.get("visible_trace") or [])
        run.lease_token = None
        self.succeeded.append({"db": db, "run_input": run_input, "result": result})
        return CustomerIntelligenceRunLeaseMutation(
            CustomerIntelligenceRunLeaseMutationStatus.APPLIED,
            run,
        )


    def record_visible_progress_if_lease_owner(self, db, run_input, *, lease_token, progress):
        run = self._runs[run_input.request_id]
        if run.lease_token != lease_token or run.status != CustomerIntelligenceRunStatus.RUNNING:
            return CustomerIntelligenceRunLeaseMutation(
                CustomerIntelligenceRunLeaseMutationStatus.STALE_LEASE,
                run,
            )
        trace = list(run.visible_trace_json or [])
        if progress not in trace:
            trace.append(dict(progress))
        run.visible_trace_json = trace
        return CustomerIntelligenceRunLeaseMutation(
            CustomerIntelligenceRunLeaseMutationStatus.APPLIED,
            run,
        )

    def mark_failed_if_lease_owner(self, db, run_input, *, lease_token, error_message):
        run = self._runs[run_input.request_id]
        run.status = CustomerIntelligenceRunStatus.FAILED
        run.error_message = error_message
        run.lease_token = None
        self.failed.append({"db": db, "run_input": run_input, "error_message": error_message})
        return CustomerIntelligenceRunLeaseMutation(
            CustomerIntelligenceRunLeaseMutationStatus.APPLIED,
            run,
        )

    def list_retryable(self, db, *, now=None, team_id=None, limit=50):
        return [
            run
            for run in self.retryable
            if team_id is None or run.team_id == team_id
        ][:limit]

    def list_due(self, db, *, now=None, team_id=None, limit=50):
        return self.list_retryable(db, now=now, team_id=team_id, limit=limit)


class FailingRunService(FakeRunService):
    def ensure_pending(self, db, run_input):
        super().ensure_pending(db, run_input)
        raise RuntimeError("customer intelligence run table unavailable")


class FakeIdentityResolutionService:
    def __init__(self):
        self.customer_calls = []
        self.team_calls = []

    def rebuild_customer_identity_terms(self, db, *, team_id: int, customer_id: int) -> int:
        self.customer_calls.append({"db": db, "team_id": team_id, "customer_id": customer_id})
        return 0

    def rebuild_team_identity_terms(
        self,
        db,
        *,
        team_id: int | None = None,
        customer_ids=None,
        limit: int = 100,
    ) -> tuple[int, ...]:
        self.team_calls.append({
            "db": db,
            "team_id": team_id,
            "customer_ids": customer_ids,
            "limit": limit,
        })
        return ()


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_schedules_manual_full_refresh_and_marks_pending(monkeypatch):
    scheduled = []
    status_calls = []
    fake_session = FakeSession()

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return FakeBackgroundTask()

    def fake_update_profile_status(db, customer_id, status, error_message=None, *, commit=True):
        status_calls.append(("profile", db, customer_id, status, error_message))

    monkeypatch.setattr("app.services.customer_intelligence_refresh_service.asyncio.create_task", fake_create_task)
    service = CustomerIntelligenceRefreshService(
        profile_workflow=FakeGraphService(),
        event_service=FakeEventService(),
        run_service=FakeRunService(),
    )

    request = await service.trigger_manual_refresh(
        fake_session,
        team_id=2,
        customer_id=101,
        actor_id="9",
        scope="full",
    )

    assert request.team_id == 2
    assert request.customer_id == 101
    assert request.scope == "full"
    assert request.request_id.startswith("manual-refresh-")
    assert fake_session.committed is True
    assert len(scheduled) == 1


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_runs_manual_refresh_through_graph(monkeypatch):
    fake_session = FakeSession()
    graph_service = FakeGraphService()
    event_service = FakeEventService()
    run_service = FakeRunService()
    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.SessionLocal",
        lambda: fake_session,
    )
    service = CustomerIntelligenceRefreshService(
        profile_workflow=graph_service,
        event_service=event_service,
        run_service=run_service,
    )

    result = await service.run_refresh(
        CustomerIntelligenceRefreshRequest(
            team_id=2,
            customer_id=101,
            actor_id="9",
            scope="partial",
            request_id="manual-refresh-test",
        )
    )

    assert result == {
        "success": True,
        "request_id": "manual-refresh-test",
        "event_key": "manual-event-1",
        "route": "refresh_profile",
    }
    assert event_service.calls == [{
        "team_id": 2,
        "customer_id": 101,
        "actor_id": "9",
        "request_id": "manual-refresh-test",
        "refresh_scope": "partial",
        "occurred_at": event_service.calls[0]["occurred_at"],
    }]
    assert "db" not in graph_service.calls[0]
    assert graph_service.calls[0]["team_id"] == 2
    assert graph_service.calls[0]["user_id"] == 9
    assert graph_service.calls[0]["session_id"] == 0
    assert graph_service.calls[0]["event"].event_key == "manual-event-1"
    assert run_service.running[0]["run_input"].request_id == "manual-refresh-test"
    assert run_service.succeeded[0]["result"]["route"] == "refresh_profile"
    assert run_service.failed == []
    assert fake_session.closed is True


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_schedules_customer_lifecycle_refresh(monkeypatch):
    scheduled = []
    status_calls = []
    fake_session = FakeSession()

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return FakeBackgroundTask()

    def fake_update_profile_status(db, customer_id, status, error_message=None, *, commit=True):
        status_calls.append(("profile", customer_id, status, error_message))

    monkeypatch.setattr("app.services.customer_intelligence_refresh_service.asyncio.create_task", fake_create_task)
    service = CustomerIntelligenceRefreshService(
        profile_workflow=FakeGraphService(),
        event_service=FakeEventService(),
        run_service=FakeRunService(),
        identity_resolution_service=FakeIdentityResolutionService(),
    )

    request = await service.trigger_customer_created_refresh(
        fake_session,
        team_id=2,
        customer_id=101,
        actor_id="9",
        source_lead_id=501,
    )

    assert request.scope == "full"
    assert request.trigger_type == "customer_converted_from_lead"
    assert request.source_lead_id == 501
    assert fake_session.committed is True
    assert len(scheduled) == 1


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_schedules_committed_business_event(monkeypatch):
    scheduled = []
    status_calls = []
    fake_session = FakeSession()
    run_service = FakeRunService()
    event = _business_event()

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return FakeBackgroundTask()

    def fake_update_profile_status(db, customer_id, status, error_message=None, *, commit=True):
        status_calls.append(("profile", customer_id, status, error_message))

    monkeypatch.setattr("app.services.customer_intelligence_refresh_service.asyncio.create_task", fake_create_task)
    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.SessionLocal",
        lambda: fake_session,
    )
    service = CustomerIntelligenceRefreshService(
        profile_workflow=FakeGraphService(),
        event_service=FakeEventService(),
        run_service=run_service,
    )

    request = await service.trigger_committed_event_refresh(
        object(),
        event=event,
        scope="partial",
    )

    assert isinstance(request, CustomerIntelligenceCommittedEventRequest)
    assert request.request_id.startswith("business-event-customer_contact_updated-")
    assert request.event is event
    assert request.scheduled is True
    assert request.schedule_error is None
    assert fake_session.committed is True
    assert run_service.pending[0]["run_input"].event is event
    assert len(scheduled) == 1


def test_customer_intelligence_refresh_service_isolates_after_commit_enqueue_failure(monkeypatch):
    fake_session = FakeSession()
    event = _business_event()

    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.SessionLocal",
        lambda: fake_session,
    )
    service = CustomerIntelligenceRefreshService(
        profile_workflow=FakeGraphService(),
        event_service=FakeEventService(),
        run_service=FailingRunService(),
    )

    request = service.enqueue_committed_event_refresh_after_commit(
        event=event,
        scope="partial",
    )

    assert request.request_id == "business-event-customer_contact_updated-contact-event-1"
    assert request.event is event
    assert request.scheduled is False
    assert request.kick_required is False
    assert request.schedule_error == "customer intelligence run table unavailable"
    assert fake_session.rolled_back is True
    assert fake_session.closed is True


def test_customer_intelligence_refresh_service_does_not_kick_unscheduled_request(monkeypatch):
    service = CustomerIntelligenceRefreshService()
    started = []
    monkeypatch.setattr(service, "_start_background_task", started.append)
    event = _business_event()
    request = CustomerIntelligenceCommittedEventRequest(
        request_id="failed-request",
        event=event,
        scope="partial",
        scheduled=False,
        kick_required=False,
        schedule_error="queue unavailable",
    )

    service.kick_committed_event_refresh(request)

    assert started == []


def test_customer_intelligence_refresh_service_enqueues_committed_business_event_without_scheduling(monkeypatch):
    scheduled = []
    status_calls = []
    run_service = FakeRunService()
    event = _business_event()

    def fake_update_profile_status(db, customer_id, status, error_message=None, *, commit=True):
        status_calls.append(("profile", customer_id, status, error_message))

    monkeypatch.setattr("app.services.customer_intelligence_refresh_service.asyncio.create_task", scheduled.append)
    service = CustomerIntelligenceRefreshService(
        profile_workflow=FakeGraphService(),
        event_service=FakeEventService(),
        run_service=run_service,
    )

    request = service.enqueue_committed_event_refresh(
        object(),
        event=event,
        scope="partial",
    )

    assert isinstance(request, CustomerIntelligenceCommittedEventRequest)
    assert request.request_id == "business-event-customer_contact_updated-contact-event-1"
    assert request.event is event
    assert request.scheduled is True
    assert request.schedule_error is None
    assert run_service.pending[0]["run_input"].event is event
    assert scheduled == []


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_isolates_committed_event_schedule_failure(monkeypatch):
    scheduled = []
    fake_session = FakeSession()
    event = _business_event()

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return FakeBackgroundTask()

    monkeypatch.setattr("app.services.customer_intelligence_refresh_service.asyncio.create_task", fake_create_task)
    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.SessionLocal",
        lambda: fake_session,
    )
    service = CustomerIntelligenceRefreshService(
        profile_workflow=FakeGraphService(),
        event_service=FakeEventService(),
        run_service=FailingRunService(),
    )

    request = await service.trigger_committed_event_refresh(
        object(),
        event=event,
        scope="partial",
    )

    assert request.request_id.startswith("business-event-customer_contact_updated-")
    assert request.event is event
    assert request.scheduled is False
    assert request.schedule_error == "customer intelligence run table unavailable"
    assert fake_session.rolled_back is True
    assert fake_session.closed is True
    assert scheduled == []


def test_customer_intelligence_refresh_service_detects_customer_business_inputs():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[Customer.__table__])
    Session = sessionmaker(bind=engine)
    db = Session()
    for ddl in [
        "CREATE TABLE crm_contacts (id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL, "
        "customer_id INTEGER, name VARCHAR(100) NOT NULL, gender INTEGER, mobile VARCHAR(20) NOT NULL)",
        "CREATE TABLE crm_customer_activities (id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL, customer_id INTEGER)",
        "CREATE TABLE crm_opportunities (id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL, customer_id INTEGER)",
        "CREATE TABLE crm_contracts (id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL, "
        "customer_id INTEGER, deleted_at DATETIME)",
        "CREATE TABLE crm_invoice_titles (id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL, customer_id INTEGER)",
        "CREATE TABLE crm_invoice_applications (id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL, customer_id INTEGER)",
        "CREATE TABLE crm_deployment_infos (id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL, customer_id INTEGER)",
        "CREATE TABLE crm_license_applications (id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL, customer_id INTEGER)",
    ]:
        db.execute(text(ddl))
    db.add_all([
        Customer(id=101, team_id=2, account_name="有输入客户", city="广州", creator_id="9"),
        Customer(id=102, team_id=2, account_name="空客户", city="上海", creator_id="9"),
    ])
    db.execute(text(
        "INSERT INTO crm_contacts (id, team_id, customer_id, name, gender, mobile) "
        "VALUES (201, 2, 101, '张总', 1, '13800000000')"
    ))
    db.commit()
    service = CustomerIntelligenceRefreshService(
        profile_workflow=FakeGraphService(),
        event_service=FakeEventService(),
        run_service=FakeRunService(),
    )
    try:
        assert service.has_customer_business_data(db, customer_id=101, team_id=2) is True
        assert service.has_customer_business_data(db, customer_id=102, team_id=2) is False
        assert service.has_customer_business_data(db, customer_id=101, team_id=3) is False
    finally:
        db.close()
        engine.dispose()


def test_customer_intelligence_refresh_service_recovers_expired_lease_without_stealing_execution():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerProfileProjectionVersion.__table__,
            CustomerProfileCurrent.__table__,
            CustomerIntelligenceRun.__table__,
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    operation_service = AgentAsyncOperationService()
    run_service = CustomerIntelligenceRunService()
    event = _business_event()
    run_input = CustomerIntelligenceRunInput(
        request_id="stale-request-101",
        event=event,
        scope="full",
        max_attempts=3,
    )
    expired_at = business_now() - timedelta(minutes=5)
    original_lease_token = "expired-lease-owner"
    db.add(
        Customer(
            id=101,
            team_id=2,
            account_name="卡住的客户",
            city="广州",
            creator_id="9",
        )
    )
    db.add(
        CustomerIntelligenceRun(
            id=301,
            run_key=run_service.run_key(run_input),
            request_id=run_input.request_id,
            event_key=event.event_key,
            event_json=event.to_dict(),
            tenant_id=2,
            team_id=2,
            customer_id=101,
            actor_id=event.actor_id,
            trigger_type=event.trigger_type,
            scope="full",
            status=CustomerIntelligenceRunStatus.RUNNING,
            attempt_count=1,
            max_attempts=3,
            lease_token=original_lease_token,
            lease_expires_at=expired_at,
            started_time=business_now() - timedelta(minutes=15),
        )
    )
    db.commit()
    operation = operation_service.ensure_scheduled(
        db,
        operation_key="customer-intelligence:stale-request-101",
        request_id="stale-request-101",
        team_id=2,
        user_id=9,
        session_id=None,
        source_user_message_id=None,
        operation_type="customer_intelligence_refresh",
        resource_type="customer",
        resource_id=101,
    )
    operation_service.mark_running(db, operation)
    db.commit()
    service = CustomerIntelligenceRefreshService(
        profile_workflow=FakeGraphService(),
        event_service=FakeEventService(),
        run_service=run_service,
        async_operation_service=operation_service,
        profile_projection_service=CustomerProfileProjectionService(),
    )
    try:
        result = service.recover_stale_runtime_state(db, team_id=2)
        db.commit()
        customer = db.query(Customer).filter(Customer.id == 101).one()
        recovered_run = db.query(CustomerIntelligenceRun).filter(CustomerIntelligenceRun.id == 301).one()
        operation_projection = operation_service.get_projection(
            db,
            team_id=2,
            user_id=9,
            public_id=str(operation.public_id),
        )

        assert result == {
            "obsolete_historical_runs": 0,
            "reconciled_operations": 0,
            "stale_runs": 1,
            "pending_customers": 0,
            "failed_customers": 0,
        }
        profile_current = db.query(CustomerProfileCurrent).filter(
            CustomerProfileCurrent.team_id == 2, CustomerProfileCurrent.customer_id == 101
        ).one()
        assert profile_current.profile_status == "UPDATING"
        assert profile_current.active_run_id == 301
        assert recovered_run.status == CustomerIntelligenceRunStatus.RUNNING
        assert recovered_run.next_retry_at is None
        assert recovered_run.lease_token == original_lease_token
        assert recovered_run.lease_expires_at == expired_at
        assert operation_projection is not None
        assert operation_projection.status == AgentAsyncOperationStatus.RUNNING

        claim = run_service.claim_for_execution(
            db,
            run_input,
            now=business_now(),
            lease_seconds=300,
        )
        db.commit()
        assert claim.status == CustomerIntelligenceRunClaimStatus.CLAIMED
        assert claim.run.status == CustomerIntelligenceRunStatus.RUNNING
        assert claim.run.attempt_count == 2
        assert claim.lease_token is not None
        assert claim.lease_token != original_lease_token
        assert claim.run.lease_expires_at is not None
        assert claim.run.lease_expires_at > business_now()
    finally:
        db.close()
        engine.dispose()



def test_customer_intelligence_refresh_service_ignores_failed_run_behind_newer_success():
    """A historical failed run must not break recovery or overwrite a newer success."""
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerProfileProjectionVersion.__table__,
            CustomerProfileCurrent.__table__,
            CustomerIntelligenceRun.__table__,
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    run_service = CustomerIntelligenceRunService()
    old_event = _business_event()
    new_event = CustomerIntelligenceEvent(
        event_key="newer-event-101",
        trigger_type=old_event.trigger_type,
        tenant_id=old_event.tenant_id,
        team_id=old_event.team_id,
        customer_id=old_event.customer_id,
        occurred_at=business_now() + timedelta(minutes=1),
        source=old_event.source,
        summary="更新后的客户事件",
        payload=old_event.payload,
        actor_id=old_event.actor_id,
    )
    db.add(Customer(id=101, team_id=2, account_name="有更新的客户", city="广州", creator_id="9"))
    db.add_all(
        [
            CustomerIntelligenceRun(
                id=300,
                run_key="failed-old-run-101",
                request_id="failed-old-request-101",
                event_key=old_event.event_key,
                event_json=old_event.to_dict(),
                tenant_id=2,
                team_id=2,
                customer_id=101,
                actor_id="9",
                trigger_type=old_event.trigger_type,
                scope="partial",
                status=CustomerIntelligenceRunStatus.FAILED,
                attempt_count=3,
                max_attempts=3,
                error_message="旧运行失败",
            ),
            CustomerIntelligenceRun(
                id=301,
                run_key="success-new-run-101",
                request_id="success-new-request-101",
                event_key=new_event.event_key,
                event_json=new_event.to_dict(),
                tenant_id=2,
                team_id=2,
                customer_id=101,
                actor_id="9",
                trigger_type=new_event.trigger_type,
                scope="partial",
                status=CustomerIntelligenceRunStatus.SUCCESS,
                attempt_count=1,
                max_attempts=3,
                route="refresh_profile",
            ),
        ]
    )
    db.add(CustomerProfileCurrent(team_id=2, customer_id=101, profile_status="READY", active_run_id=None))
    db.commit()

    service = CustomerIntelligenceRefreshService(
        profile_workflow=FakeGraphService(),
        event_service=FakeEventService(),
        run_service=run_service,
        profile_projection_service=CustomerProfileProjectionService(),
    )
    try:
        result = service.recover_stale_runtime_state(db, team_id=2)
        db.commit()
        current = db.query(CustomerProfileCurrent).filter(
            CustomerProfileCurrent.team_id == 2,
            CustomerProfileCurrent.customer_id == 101,
        ).one()
        assert result["failed_customers"] == 0
        assert current.profile_status == "READY"
        assert current.active_run_id is None
    finally:
        db.close()
        engine.dispose()

def test_customer_intelligence_refresh_service_does_not_recover_live_lease():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerProfileProjectionVersion.__table__,
            CustomerProfileCurrent.__table__,
            CustomerIntelligenceRun.__table__,
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    run_service = CustomerIntelligenceRunService()
    event = _business_event()
    run_input = CustomerIntelligenceRunInput(
        request_id="live-request-101",
        event=event,
        scope="full",
        max_attempts=3,
    )
    live_until = business_now() + timedelta(minutes=5)
    db.add(
        Customer(
            id=101,
            team_id=2,
            account_name="正在更新的客户",
            city="广州",
            creator_id="9",
        )
    )
    db.add(
        CustomerIntelligenceRun(
            id=301,
            run_key=run_service.run_key(run_input),
            request_id=run_input.request_id,
            event_key=event.event_key,
            event_json=event.to_dict(),
            tenant_id=2,
            team_id=2,
            customer_id=101,
            actor_id=event.actor_id,
            trigger_type=event.trigger_type,
            scope="full",
            status=CustomerIntelligenceRunStatus.RUNNING,
            attempt_count=1,
            max_attempts=3,
            lease_token="live-lease-owner",
            lease_expires_at=live_until,
            started_time=business_now(),
        )
    )
    db.commit()
    service = CustomerIntelligenceRefreshService(
        profile_workflow=FakeGraphService(),
        event_service=FakeEventService(),
        run_service=run_service,
    )
    try:
        result = service.recover_stale_runtime_state(db, team_id=2)
        db.commit()
        customer = db.query(Customer).filter(Customer.id == 101).one()
        run = db.query(CustomerIntelligenceRun).filter(CustomerIntelligenceRun.id == 301).one()
    finally:
        db.close()
        engine.dispose()

    assert result == {
        "obsolete_historical_runs": 0,
        "reconciled_operations": 0,
        "stale_runs": 0,
        "pending_customers": 0,
        "failed_customers": 0,
    }
    assert run.status == CustomerIntelligenceRunStatus.RUNNING
    assert run.lease_token == "live-lease-owner"
    assert run.lease_expires_at == live_until


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_exhausts_attempts_only_at_claim(
    monkeypatch,
):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerProfileProjectionVersion.__table__,
            CustomerProfileCurrent.__table__,
            CustomerIntelligenceRun.__table__,
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    operation_service = AgentAsyncOperationService()
    run_service = CustomerIntelligenceRunService()
    graph_service = FakeGraphService()
    event = _business_event()
    run_input = CustomerIntelligenceRunInput(
        request_id="exhausted-stale-request-101",
        event=event,
        scope="full",
        max_attempts=3,
    )
    db.add(
        Customer(
            id=101,
            team_id=2,
            account_name="重试耗尽的客户",
            city="广州",
            creator_id="9",
        )
    )
    db.add(
        CustomerIntelligenceRun(
            id=301,
            run_key=run_service.run_key(run_input),
            request_id=run_input.request_id,
            event_key=event.event_key,
            event_json=event.to_dict(),
            tenant_id=2,
            team_id=2,
            customer_id=101,
            actor_id=event.actor_id,
            trigger_type=event.trigger_type,
            scope="full",
            status=CustomerIntelligenceRunStatus.RUNNING,
            attempt_count=3,
            max_attempts=3,
            lease_token="expired-final-lease",
            lease_expires_at=business_now() - timedelta(minutes=5),
            started_time=business_now() - timedelta(minutes=15),
        )
    )
    db.commit()
    operation = operation_service.ensure_scheduled(
        db,
        operation_key="customer-intelligence:exhausted-stale-request-101",
        request_id=run_input.request_id,
        team_id=2,
        user_id=9,
        session_id=None,
        source_user_message_id=None,
        operation_type="customer_intelligence_refresh",
        resource_type="customer",
        resource_id=101,
    )
    operation_service.mark_running(db, operation)
    db.commit()
    service = CustomerIntelligenceRefreshService(
        profile_workflow=graph_service,
        event_service=FakeEventService(),
        run_service=run_service,
        async_operation_service=operation_service,
    )
    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.SessionLocal",
        Session,
    )
    try:
        recovery = service.recover_stale_runtime_state(db, team_id=2)
        db.commit()
        run_after_recovery = db.query(CustomerIntelligenceRun).filter(CustomerIntelligenceRun.id == 301).one()
        assert recovery["stale_runs"] == 1
        assert run_after_recovery.status == CustomerIntelligenceRunStatus.RUNNING

        execution = await service.run_committed_event_refresh(
            CustomerIntelligenceCommittedEventRequest(
                request_id=run_input.request_id,
                event=event,
                scope="full",
                operation_public_id=str(operation.public_id),
            )
        )
        db.expire_all()
        exhausted_run = db.query(CustomerIntelligenceRun).filter(CustomerIntelligenceRun.id == 301).one()
        operation_projection = operation_service.get_projection(
            db,
            team_id=2,
            user_id=9,
            public_id=str(operation.public_id),
        )
    finally:
        db.close()
        engine.dispose()

    assert execution["success"] is False
    assert execution["terminal"] is True
    assert execution["run_status"] == CustomerIntelligenceRunStatus.FAILED
    assert exhausted_run.status == CustomerIntelligenceRunStatus.FAILED
    assert exhausted_run.lease_token is None
    assert exhausted_run.lease_expires_at is None
    assert graph_service.calls == []
    assert operation_projection is not None
    assert operation_projection.status == AgentAsyncOperationStatus.FAILED
    assert operation_projection.finished_time is not None
    assert operation_projection.events[-1].event_type == "FAILED"

def test_customer_intelligence_refresh_service_closes_obsolete_historical_runs():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerProfileProjectionVersion.__table__,
            CustomerProfileCurrent.__table__,
            CustomerIntelligenceRun.__table__,
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    operation_service = AgentAsyncOperationService()
    db.add(
        Customer(
            id=101,
            team_id=2,
            account_name="已有智能档案客户",
            city="广州",
            creator_id="9",
        )
    )
    db.add(
        CustomerIntelligenceRun(
            id=301,
            run_key="obsolete-historical-run-101",
            request_id="historical-request-101",
            event_key="historical-event-101",
            tenant_id=2,
            team_id=2,
            customer_id=101,
            trigger_type="customer_intelligence_historical_backfill_requested",
            scope="full",
            status=CustomerIntelligenceRunStatus.RUNNING,
            attempt_count=1,
            max_attempts=3,
            started_time=datetime.now() - timedelta(minutes=15),
        )
    )
    _add_published_profile(db, customer_id=101)
    db.commit()
    operation = operation_service.ensure_scheduled(
        db,
        operation_key="customer-intelligence:historical-request-101",
        request_id="historical-request-101",
        team_id=2,
        user_id=9,
        session_id=None,
        source_user_message_id=None,
        operation_type="customer_intelligence_refresh",
        resource_type="customer",
        resource_id=101,
    )
    operation_service.mark_running(db, operation)
    db.commit()
    service = CustomerIntelligenceRefreshService(
        profile_workflow=FakeGraphService(),
        event_service=FakeEventService(),
        run_service=FakeRunService(),
        async_operation_service=operation_service,
    )
    try:
        result = service.recover_stale_runtime_state(db, team_id=2)
        db.commit()
        run = db.query(CustomerIntelligenceRun).filter(CustomerIntelligenceRun.id == 301).one()
        run_status = run.status
        route = run.route
        result_json = run.result_json
        operation_projection = operation_service.get_projection(
            db,
            team_id=2,
            user_id=9,
            public_id=str(operation.public_id),
        )
    finally:
        db.close()
        engine.dispose()

    assert result["obsolete_historical_runs"] == 1
    assert result["stale_runs"] == 0
    assert run_status == CustomerIntelligenceRunStatus.CANCELLED
    assert route == "historical_backfill_satisfied"
    assert result_json["reason"] == "customer_profile_projection_already_available"
    assert operation_projection is not None
    assert operation_projection.status == AgentAsyncOperationStatus.CANCELLED
    assert operation_projection.result["reason"] == "customer_profile_projection_already_available"
    assert operation_projection.events[-1].event_type == "CANCELLED"


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_runs_committed_business_event_through_graph(monkeypatch):
    fake_session = FakeSession()
    graph_service = FakeGraphService()
    run_service = FakeRunService()
    event = _business_event()
    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.SessionLocal",
        lambda: fake_session,
    )
    service = CustomerIntelligenceRefreshService(
        profile_workflow=graph_service,
        event_service=FakeEventService(),
        run_service=run_service,
    )

    result = await service.run_committed_event_refresh(
        CustomerIntelligenceCommittedEventRequest(
            request_id="business-event-test",
            event=event,
            scope="partial",
        )
    )

    assert result == {
        "success": True,
        "request_id": "business-event-test",
        "event_key": "contact-event-1",
        "route": "refresh_profile",
    }
    assert graph_service.calls[0]["event"] is event
    assert graph_service.calls[0]["team_id"] == 2
    assert graph_service.calls[0]["user_id"] == 9
    assert run_service.succeeded[0]["run_input"].event is event
    assert fake_session.closed is True


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_reclaims_pending_graph_execution(monkeypatch):
    graph_service = FakeGraphService()
    run_service = FakeRunService()
    event = _business_event()
    run_input = CustomerIntelligenceRunInput(
        request_id="business-event-running-reclaim",
        event=event,
        scope="partial",
    )
    run = run_service.ensure_pending(FakeSession(), run_input)
    run.status = CustomerIntelligenceRunStatus.RUNNING
    run.attempt_count = 1
    run.lease_token = "expired-lease"
    run.lease_expires_at = business_now() - timedelta(minutes=5)
    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.SessionLocal",
        FakeSession,
    )
    service = CustomerIntelligenceRefreshService(
        profile_workflow=graph_service,
        event_service=FakeEventService(),
        run_service=run_service,
        operation_projector=FakeOperationProjector(),
    )

    result = await service.run_committed_event_refresh(
        CustomerIntelligenceCommittedEventRequest(
            request_id=run_input.request_id,
            event=event,
            scope="partial",
        )
    )

    assert result["success"] is True
    assert run.attempt_count == 2
    assert graph_service.calls == [{
        "team_id": 2,
        "user_id": 9,
        "session_id": 0,
        "event": event,
        "run_id": 30,
        "resume_existing_execution": True,
    }]


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_schedules_batch_rebuild_through_same_graph_entry(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[Customer.__table__])
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        Customer(id=101, team_id=2, account_name="越秀金融", city="广州", creator_id="9"),
        Customer(id=102, team_id=2, account_name="广发证券", city="广州", creator_id="9"),
        Customer(id=201, team_id=3, account_name="其他团队客户", city="深圳", creator_id="9"),
    ])
    db.commit()
    scheduled = []
    status_calls = []
    run_service = FakeRunService()

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return FakeBackgroundTask()

    def fake_update_profile_status(db_arg, customer_id, status, error_message=None, *, commit=True):
        status_calls.append(("profile", db_arg, customer_id, status, error_message))

    monkeypatch.setattr("app.services.customer_intelligence_refresh_service.asyncio.create_task", fake_create_task)
    service = CustomerIntelligenceRefreshService(
        profile_workflow=FakeGraphService(),
        event_service=FakeEventService(),
        run_service=run_service,
    )
    try:
        result = await service.trigger_batch_rebuild(
            db,
            team_id=2,
            actor_id="9",
            scope="full",
            customer_ids=[102, 201, 101],
            limit=20,
        )
    finally:
        db.close()
        engine.dispose()

    assert result.success is True
    assert result.request_id.startswith("batch-rebuild-")
    assert result.customer_ids == [101, 102]
    assert result.total == 2
    assert result.scheduled == 2
    assert len(scheduled) == 2
    assert [item["run_input"].request_id for item in run_service.pending] == [
        result.request_id,
        result.request_id,
    ]
    assert [
        item["run_input"].event.trigger_type
        for item in run_service.pending
    ] == [
        "customer_intelligence_batch_rebuild_requested",
        "customer_intelligence_batch_rebuild_requested",
    ]


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_schedules_missing_historical_backfill(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerProfileProjectionVersion.__table__,
            CustomerProfileCurrent.__table__,
            CustomerIntelligenceRun.__table__,
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        Customer(id=101, team_id=2, account_name="缺档且有业务数据", city="广州", creator_id="9"),
        Customer(
            id=102,
            team_id=2,
            account_name="已有档案",
            city="广州",
            creator_id="9",
        ),
        Customer(id=104, team_id=2, account_name="已有运行", city="广州", creator_id="9"),
    ])
    db.add_all([
        CustomerIntelligenceRun(
            id=301,
            run_key="active-run-104",
            request_id="active-request-104",
            event_key="active-event-104",
            tenant_id=2,
            team_id=2,
            customer_id=104,
            trigger_type="manual_refresh_requested",
            scope="full",
            status=CustomerIntelligenceRunStatus.PENDING,
        ),
    ])
    db.commit()
    scheduled = []
    status_calls = []
    run_service = FakeRunService()

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return FakeBackgroundTask()

    def fake_update_profile_status(db_arg, customer_id, status, error_message=None, *, commit=True):
        status_calls.append(("profile", customer_id, status, error_message))

    monkeypatch.setattr("app.services.customer_intelligence_refresh_service.asyncio.create_task", fake_create_task)
    service = CustomerIntelligenceRefreshService(
        profile_workflow=FakeGraphService(),
        event_service=FakeEventService(),
        run_service=run_service,
    )
    monkeypatch.setattr(
        service,
        "_has_customer_business_data_filter",
        lambda: true(),
    )
    try:
        result = await service.trigger_missing_historical_backfill(db, team_id=2, limit=20)
    finally:
        db.close()
        engine.dispose()

    assert result.success is True
    assert result.request_id.startswith("historical-backfill-")
    assert result.scope == "full"
    assert result.customer_ids == [101, 102]
    assert result.total == 2
    assert result.scheduled == 2
    assert len(scheduled) == 2
    assert run_service.pending[0]["run_input"].event.trigger_type == (
        "customer_intelligence_historical_backfill_requested"
    )


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_recovers_before_historical_backfill(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerProfileProjectionVersion.__table__,
            CustomerProfileCurrent.__table__,
            CustomerIntelligenceRun.__table__,
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        Customer(
            id=101,
            team_id=2,
            account_name="已有档案但旧补档未收口",
            city="广州",
            creator_id="9",
        ),
        Customer(id=102, team_id=2, account_name="缺档客户", city="广州", creator_id="9"),
    ])
    _add_published_profile(db, customer_id=101)
    db.add(
        CustomerIntelligenceRun(
            id=301,
            run_key="old-running-historical-101",
            request_id="historical-request-101",
            event_key="historical-event-101",
            tenant_id=2,
            team_id=2,
            customer_id=101,
            trigger_type="customer_intelligence_historical_backfill_requested",
            scope="full",
            status=CustomerIntelligenceRunStatus.RUNNING,
            attempt_count=1,
            max_attempts=3,
            started_time=datetime.now() - timedelta(minutes=15),
        )
    )
    db.commit()
    scheduled = []
    status_calls = []
    run_service = FakeRunService()

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return FakeBackgroundTask()

    monkeypatch.setattr("app.services.customer_intelligence_refresh_service.asyncio.create_task", fake_create_task)
    service = CustomerIntelligenceRefreshService(
        profile_workflow=FakeGraphService(),
        event_service=FakeEventService(),
        run_service=run_service,
        identity_resolution_service=FakeIdentityResolutionService(),
    )
    monkeypatch.setattr(
        service,
        "_has_customer_business_data_filter",
        lambda: true(),
    )
    try:
        result = await service.trigger_missing_historical_backfill(db, team_id=2, limit=20)
        old_run = db.query(CustomerIntelligenceRun).filter(CustomerIntelligenceRun.id == 301).one()
        old_run_status = old_run.status
    finally:
        db.close()
        engine.dispose()

    assert old_run_status == CustomerIntelligenceRunStatus.CANCELLED
    assert result.customer_ids == [102]
    assert result.scheduled == 1
    assert len(scheduled) == 1


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_runs_customer_lifecycle_refresh_through_graph(monkeypatch):
    fake_session = FakeSession()
    graph_service = FakeGraphService()
    event_service = FakeEventService()
    run_service = FakeRunService()
    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.SessionLocal",
        lambda: fake_session,
    )
    service = CustomerIntelligenceRefreshService(
        profile_workflow=graph_service,
        event_service=event_service,
        run_service=run_service,
    )

    result = await service.run_refresh(
        CustomerIntelligenceRefreshRequest(
            team_id=2,
            customer_id=101,
            actor_id="9",
            scope="full",
            request_id="customer-created-test",
            trigger_type="customer_created",
        )
    )

    assert result == {
        "success": True,
        "request_id": "customer-created-test",
        "event_key": "lifecycle-event-1",
        "route": "refresh_profile",
    }
    assert event_service.calls == [{
        "team_id": 2,
        "customer_id": 101,
        "actor_id": "9",
        "request_id": "customer-created-test",
        "trigger_type": "customer_created",
        "source_lead_id": None,
        "occurred_at": event_service.calls[0]["occurred_at"],
    }]
    assert graph_service.calls[0]["event"].event_key == "lifecycle-event-1"
    assert run_service.succeeded[0]["run_input"].scope == "full"
    assert fake_session.closed is True


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_does_not_mark_structured_profile_failure_success(monkeypatch):
    fake_session = FakeSession()
    event_service = FakeEventService()
    run_service = FakeRunService()
    status_calls = []

    def fake_update_profile_status(db, customer_id, status, error_message=None, *, commit=True):
        status_calls.append(("profile", customer_id, status, error_message))

    class StructuredFailureGraph(FakeGraphService):
        async def stream_events(self, input_state):
            self.calls.append(input_state)
            yield {
                "kind": "result",
                "result": {
                    "route": "refresh_profile",
                    "profile_projection_result": {
                        "success": False,
                        "error_code": "PROFILE_PUBLISH_FAILED",
                    },
                },
            }

    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.SessionLocal",
        lambda: fake_session,
    )
    service = CustomerIntelligenceRefreshService(
        profile_workflow=StructuredFailureGraph(),
        event_service=event_service,
        run_service=run_service,
    )

    result = await service.run_refresh(
        CustomerIntelligenceRefreshRequest(
            team_id=2,
            customer_id=101,
            actor_id="9",
            scope="full",
            request_id="structured-profile-failure",
        )
    )

    assert result["success"] is False
    assert run_service.succeeded == []
    assert run_service.failed[0]["error_message"] == (
        "客户档案工作流发布失败: PROFILE_PUBLISH_FAILED"
    )


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_records_failed_run_and_marks_customer_failed(monkeypatch):
    fake_session = FakeSession()
    event_service = FakeEventService()
    run_service = FakeRunService()
    status_calls = []

    def fake_update_profile_status(db, customer_id, status, error_message=None, *, commit=True):
        status_calls.append(("profile", customer_id, status, error_message))

    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.SessionLocal",
        lambda: fake_session,
    )
    service = CustomerIntelligenceRefreshService(
        profile_workflow=FakeGraphService(should_fail=True),
        event_service=event_service,
        run_service=run_service,
    )

    result = await service.run_refresh(
        CustomerIntelligenceRefreshRequest(
            team_id=2,
            customer_id=101,
            actor_id="9",
            scope="full",
            request_id="manual-refresh-failed",
        )
    )

    assert result["success"] is False
    assert result["request_id"] == "manual-refresh-failed"
    assert run_service.running[0]["run_input"].request_id == "manual-refresh-failed"
    assert run_service.failed[0]["error_message"] == "graph failed"
    assert fake_session.closed is True


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_runs_due_retries(monkeypatch):
    sessions = [FakeSession() for _ in range(6)]
    graph_service = FakeGraphService()
    event_service = FakeEventService()
    run_service = FakeRunService()
    run_service.retryable = [
        SimpleNamespace(
            team_id=2,
            customer_id=101,
            actor_id="9",
            scope="partial",
            request_id="manual-refresh-retry",
            trigger_type="manual_refresh_requested",
            event_json={"payload": {"refresh_scope": "partial"}},
        )
    ]

    def fake_session_local():
        return sessions.pop(0)

    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.SessionLocal",
        fake_session_local,
    )
    service = CustomerIntelligenceRefreshService(
        profile_workflow=graph_service,
        event_service=event_service,
        run_service=run_service,
        operation_projector=FakeOperationProjector(),
    )

    result = await service.run_due_retries(team_id=2, limit=10)

    assert result["success"] is True
    assert result["total"] == 1
    assert result["succeeded"] == 1
    assert run_service.running[0]["run_input"].request_id == "manual-refresh-retry"
    assert graph_service.calls[0]["event"].event_key == "manual-event-1"
    assert len(sessions) == 1


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_filters_due_retries_by_team(monkeypatch):
    sessions = [FakeSession() for _ in range(6)]
    graph_service = FakeGraphService()
    event_service = FakeEventService()
    run_service = FakeRunService()
    run_service.retryable = [
        SimpleNamespace(
            team_id=2,
            customer_id=101,
            actor_id="9",
            scope="partial",
            request_id="team-2-retry",
            trigger_type="manual_refresh_requested",
            event_json={"payload": {"refresh_scope": "partial"}},
        ),
        SimpleNamespace(
            team_id=3,
            customer_id=201,
            actor_id="10",
            scope="partial",
            request_id="team-3-retry",
            trigger_type="manual_refresh_requested",
            event_json={"payload": {"refresh_scope": "partial"}},
        ),
    ]

    def fake_session_local():
        return sessions.pop(0)

    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.SessionLocal",
        fake_session_local,
    )
    service = CustomerIntelligenceRefreshService(
        profile_workflow=graph_service,
        event_service=event_service,
        run_service=run_service,
        operation_projector=FakeOperationProjector(),
    )

    result = await service.run_due_retries(team_id=2, limit=10)

    assert result["total"] == 1
    assert run_service.running[0]["run_input"].request_id == "team-2-retry"
    assert graph_service.calls[0]["team_id"] == 2


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_retries_committed_business_event_from_persisted_event_json(
    monkeypatch,
):
    sessions = [FakeSession() for _ in range(6)]
    graph_service = FakeGraphService()
    run_service = FakeRunService()
    event = _business_event()
    run_service.retryable = [
        SimpleNamespace(
            team_id=2,
            customer_id=101,
            actor_id="9",
            scope="partial",
            request_id="business-event-retry",
            trigger_type="customer_contact_updated",
            event_json=event.to_dict(),
        )
    ]

    def fake_session_local():
        return sessions.pop(0)

    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.SessionLocal",
        fake_session_local,
    )
    service = CustomerIntelligenceRefreshService(
        profile_workflow=graph_service,
        event_service=FakeEventService(),
        run_service=run_service,
        operation_projector=FakeOperationProjector(),
    )

    result = await service.run_due_retries(team_id=2, limit=10)

    assert result["total"] == 1
    assert run_service.running[0]["run_input"].request_id == "business-event-retry"
    assert run_service.running[0]["run_input"].event.trigger_type == "customer_contact_updated"
    assert graph_service.calls[0]["event"].event_key == "contact-event-1"


@pytest.mark.asyncio
@pytest.mark.asyncio
@pytest.mark.asyncio
class _LateBindingGraphService:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.progress_consumed = asyncio.Event()
        self.release = asyncio.Event()
        self.inputs: list[dict[str, object]] = []

    async def stream_events(self, input_state):
        self.inputs.append(input_state)
        self.started.set()
        yield {
            "kind": "event",
            "event": {"title": "提炼客户事实", "content": "正在提炼客户事实"},
        }
        self.progress_consumed.set()
        await self.release.wait()
        yield {
            "kind": "result",
            "result": {
                "route": "refresh_profile",
                "degraded": False,
                "profile_projection_result": {"success": True},
                "visible_trace": [
                    {"title": "提炼客户事实", "content": "提炼出 2 条可沉淀事实"},
                ],
            },
        }


def test_customer_intelligence_graph_thread_identity_does_not_depend_on_late_agent_binding() -> None:
    background_config = build_customer_intelligence_graph_config(
        team_id=2,
        user_id=9,
        session_id=0,
        event_key="contact-event-1",
    )
    bound_config = build_customer_intelligence_graph_config(
        team_id=2,
        user_id=9,
        session_id=554,
        event_key="contact-event-1",
    )

    assert background_config["configurable"]["thread_id"] == bound_config["configurable"]["thread_id"]
    assert background_config["metadata"]["session_id"] == 0
    assert bound_config["metadata"]["session_id"] == 554


@pytest.mark.asyncio
async def test_committed_event_late_agent_binding_converges_to_terminal_operation(monkeypatch) -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerProfileProjectionVersion.__table__,
            CustomerProfileCurrent.__table__,
            CustomerIntelligenceRun.__table__,
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    graph_service = _LateBindingGraphService()
    run_service = CustomerIntelligenceRunService()
    operation_service = AgentAsyncOperationService()
    service = CustomerIntelligenceRefreshService(
        profile_workflow=graph_service,
        event_service=CustomerIntelligenceEventService(),
        run_service=run_service,
        async_operation_service=operation_service,
    )
    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.SessionLocal",
        Session,
    )
    event = _business_event()
    request_id = "business-event-late-binding"

    setup_db = Session()
    try:
        setup_db.add(
            Customer(
                id=101,
                team_id=2,
                account_name="晚绑定客户",
                city="广州",
                creator_id="9",
            )
        )
        request = CustomerIntelligenceCommittedEventRequest(
            request_id=request_id,
            event=event,
            scope="partial",
        )
        service._ensure_pending_event_run(setup_db, request)
        setup_db.commit()
    finally:
        setup_db.close()

    execution = asyncio.create_task(service.run_committed_event_refresh(request))
    await graph_service.started.wait()
    await graph_service.progress_consumed.wait()

    binding_db = Session()
    try:
        bound = service.bind_committed_event_to_agent(
            binding_db,
            team_id=2,
            request_id=request_id,
            binding=AgentAsyncOperationBinding(
                team_id=2,
                user_id=9,
                session_id=554,
                source_user_message_id=1001,
                source_assistant_message_id=1002,
            ),
        )
        binding_db.commit()
        running_projection = operation_service.get_projection(
            binding_db,
            team_id=2,
            user_id=9,
            public_id=str(bound.operation_public_id),
        )
        assert running_projection is not None
        assert running_projection.status == AgentAsyncOperationStatus.RUNNING
        assert [event.message for event in running_projection.events if event.event_type == "PROGRESS"] == [
            "正在提炼客户事实",
        ]
    finally:
        binding_db.close()

    graph_service.release.set()
    result = await execution

    assertion_db = Session()
    try:
        terminal_projection = operation_service.get_projection(
            assertion_db,
            team_id=2,
            user_id=9,
            public_id=str(bound.operation_public_id),
        )
        durable_run = run_service.get_by_request_id(
            assertion_db,
            team_id=2,
            request_id=request_id,
        )
        assert result["success"] is True
        assert durable_run is not None
        assert durable_run.status == CustomerIntelligenceRunStatus.SUCCESS
        assert terminal_projection is not None
        assert terminal_projection.status == AgentAsyncOperationStatus.SUCCEEDED
        assert terminal_projection.finished_time is not None
    finally:
        assertion_db.close()
        engine.dispose()



def test_recover_stale_runtime_state_reconciles_terminal_run_projection(monkeypatch) -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerProfileProjectionVersion.__table__,
            CustomerProfileCurrent.__table__,
            CustomerIntelligenceRun.__table__,
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    run_service = CustomerIntelligenceRunService()
    operation_service = AgentAsyncOperationService()
    event = _business_event()
    request_id = "terminal-run-stale-operation"
    run_input = CustomerIntelligenceRunInput(
        request_id=request_id,
        event=event,
        scope="partial",
    )
    completed_at = business_now()
    db.add(
        Customer(
            id=101,
            team_id=2,
            account_name="终态投影修复客户",
            city="广州",
            creator_id="9",
        )
    )
    db.add(
        CustomerIntelligenceRun(
            run_key=run_service.run_key(run_input),
            request_id=request_id,
            event_key=event.event_key,
            event_json=event.to_dict(),
            tenant_id=2,
            team_id=2,
            customer_id=101,
            actor_id=event.actor_id,
            trigger_type=event.trigger_type,
            scope="partial",
            status=CustomerIntelligenceRunStatus.SUCCESS,
            attempt_count=1,
            max_attempts=3,
            started_time=completed_at - timedelta(seconds=10),
            finished_time=completed_at,
            route="refresh_profile",
            result_json={"route": "refresh_profile", "degraded": False},
            visible_trace_json=[
                {"title": "提炼客户事实", "content": "提炼出 2 条可沉淀事实"},
            ],
        )
    )
    db.commit()
    operation = operation_service.ensure_scheduled(
        db,
        operation_key=f"customer-intelligence:{request_id}",
        request_id=request_id,
        team_id=2,
        user_id=9,
        session_id=None,
        source_user_message_id=None,
        operation_type="customer_intelligence_refresh",
        resource_type="customer",
        resource_id=101,
    )
    operation_service.mark_running(db, operation)
    db.commit()
    service = CustomerIntelligenceRefreshService(
        profile_workflow=FakeGraphService(),
        event_service=CustomerIntelligenceEventService(),
        run_service=run_service,
        async_operation_service=operation_service,
    )

    try:
        monkeypatch.setattr(
            "app.services.customer_intelligence_refresh_service.team_crud.get_all_teams",
            lambda db_arg: [SimpleNamespace(id=2)],
        )
        recovery = service.recover_stale_runtime_state(db)
        db.commit()
        projection = operation_service.get_projection(
            db,
            team_id=2,
            user_id=9,
            public_id=str(operation.public_id),
        )

        assert recovery["reconciled_operations"] == 1
        assert projection is not None
        assert projection.status == AgentAsyncOperationStatus.SUCCEEDED
        assert projection.finished_time == completed_at
        assert [event.event_type for event in projection.events][-1] == "SUCCEEDED"
    finally:
        db.close()
        engine.dispose()


def test_customer_intelligence_refresh_failure_updates_only_new_projection(monkeypatch):
    fake_session = FakeSession()
    projection = FakeProfileProjectionService()
    run = SimpleNamespace(
        id=77,
        status=CustomerIntelligenceRunStatus.FAILED,
        error_message="graph failed",
        request_id="failed-request-1",
    )
    monkeypatch.setattr(
        "app.services.customer_intelligence_refresh_service.SessionLocal",
        lambda: fake_session,
    )
    service = CustomerIntelligenceRefreshService(profile_projection_service=projection)

    service._project_customer_failure(event=_business_event(), run=run)

    assert projection.failed_calls == [{
        "db": fake_session,
        "team_id": 2,
        "customer_id": 101,
        "run_id": 77,
        "reason": "graph failed",
    }]
    assert fake_session.committed is True
    assert fake_session.closed is True


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_routes_profile_run_through_explicit_workflow():
    run_service = FakeRunService()

    class FakeProfileWorkflow:
        def __init__(self):
            self.calls = []

        async def stream_events(self, input_state):
            self.calls.append(input_state)
            yield {
                "kind": "result",
                "result": {
                    "route": "refresh_profile",
                    "profile_projection_result": {"success": True},
                },
            }

    profile_workflow = FakeProfileWorkflow()
    service = CustomerIntelligenceRefreshService(
        profile_workflow=profile_workflow,
        event_service=FakeEventService(),
        run_service=run_service,
    )

    event = _business_event()
    result = await service.run_committed_event_refresh(
        CustomerIntelligenceCommittedEventRequest(
            request_id="profile-workflow-route",
            event=event,
            scope="partial",
        )
    )

    assert result["success"] is True
    assert len(profile_workflow.calls) == 1
    assert profile_workflow.calls[0]["event"] is event
    assert profile_workflow.calls[0]["run_id"] == len("profile-workflow-route")


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_uses_default_profile_workflow_namespace(monkeypatch):
    profile_graph = FakeGraphService()
    monkeypatch.setattr(
        "app.services.agent.customer_profile_projection_workflow.customer_profile_projection_graph_service",
        profile_graph,
    )
    service = CustomerIntelligenceRefreshService(
        event_service=FakeEventService(),
        run_service=FakeRunService(),
    )

    event = _business_event()
    result = await service.run_committed_event_refresh(
        CustomerIntelligenceCommittedEventRequest(
            request_id="profile-workflow-default",
            event=event,
            scope="partial",
        )
    )

    assert result["success"] is True
    assert len(profile_graph.calls) == 1
    assert profile_graph.calls[0]["run_id"] == len("profile-workflow-default")


@pytest.mark.parametrize("scope", ["brief", "light", "profile", "dynamic_brief"])
def test_customer_intelligence_refresh_contract_rejects_retired_scopes(scope):
    with pytest.raises(ValueError, match="刷新范围无效"):
        CustomerIntelligenceRefreshRequest(
            team_id=1,
            customer_id=1,
            actor_id=None,
            scope=scope,
            request_id="retired-scope",
        )

    with pytest.raises(ValueError, match="刷新范围无效"):
        CustomerIntelligenceCommittedEventRequest(
            request_id="retired-scope",
            event=CustomerIntelligenceEvent(
                event_key="retired-scope-event",
                trigger_type="manual_refresh_requested",
                tenant_id=1,
                team_id=1,
                customer_id=1,
                occurred_at=None,
                source=CustomerIntelligenceSource(
                    source_type="manual_refresh",
                    source_object_id="retired-scope",
                    business_object_type="customer",
                    business_object_id="1",
                ),
                summary="测试事件",
                payload={},
                actor_id=None,
            ),
            scope=scope,
        )

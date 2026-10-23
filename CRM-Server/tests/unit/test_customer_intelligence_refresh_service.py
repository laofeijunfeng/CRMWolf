"""Current durable scheduling, lease and Agent-operation projection contracts."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine, text
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
from app.services.agent.async_operation_service import AgentAsyncOperationService
from app.services.agent.customer_intelligence_graph import build_customer_intelligence_graph_config
from app.services.customer_intelligence_event_service import (
    CustomerIntelligenceEvent,
    CustomerIntelligenceEventService,
    CustomerIntelligenceSource,
)
from app.services.customer_intelligence_operation_projector import CustomerIntelligenceOperationProjector
from app.services.customer_intelligence_refresh_service import (
    AgentAsyncOperationBinding,
    CustomerIntelligenceCommittedEventRequest,
    CustomerIntelligenceRefreshRequest,
    CustomerIntelligenceRefreshService,
)
from app.services.customer_intelligence_run_service import (
    CustomerIntelligenceRunClaimStatus,
    CustomerIntelligenceRunInput,
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


class FakeRunService:
    def __init__(self):
        self.pending = []

    def ensure_pending(self, db, run_input):
        self.pending.append({"db": db, "run_input": run_input})
        return SimpleNamespace(status=CustomerIntelligenceRunStatus.PENDING)


class FailingRunService(FakeRunService):
    def ensure_pending(self, db, run_input):
        super().ensure_pending(db, run_input)
        raise RuntimeError("customer intelligence run table unavailable")


@pytest.mark.asyncio
async def test_customer_intelligence_refresh_service_schedules_committed_business_event(monkeypatch):
    scheduled = []
    fake_session = FakeSession()
    run_service = FakeRunService()
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
    run_service = FakeRunService()
    event = _business_event()

    monkeypatch.setattr("app.services.customer_intelligence_refresh_service.asyncio.create_task", scheduled.append)
    service = CustomerIntelligenceRefreshService(
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
        run_service=FakeRunService(),
    )
    try:
        assert service.has_customer_business_data(db, customer_id=101, team_id=2) is True
        assert service.has_customer_business_data(db, customer_id=102, team_id=2) is False
        assert service.has_customer_business_data(db, customer_id=101, team_id=3) is False
    finally:
        db.close()
        engine.dispose()


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


@pytest.fixture
def runtime_sessions():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[
        Customer.__table__, CustomerIntelligenceRun.__table__,
        AgentAsyncOperation.__table__, AgentAsyncOperationEvent.__table__,
    ])
    sessions = sessionmaker(bind=engine)
    try:
        yield sessions
    finally:
        engine.dispose()


@pytest.mark.parametrize("expired", [False, True], ids=["live", "expired"])
@pytest.mark.parametrize("max_attempts", [1, 3], ids=["last-attempt", "retryable"])
def test_run_projection_preserves_lease_until_claim(runtime_sessions, expired, max_attempts):
    run_service = CustomerIntelligenceRunService()
    operation_service = AgentAsyncOperationService()
    projector = CustomerIntelligenceOperationProjector(
        run_service=run_service, operation_service=operation_service,
    )
    now = business_now()
    run_input = CustomerIntelligenceRunInput(
        request_id="leased-run", event=_business_event(), scope="partial", max_attempts=max_attempts,
    )
    with runtime_sessions() as db:
        first = run_service.claim_for_execution(db, run_input, now=now, lease_seconds=30)
        assert first.status == CustomerIntelligenceRunClaimStatus.CLAIMED
        token = first.lease_token
        assert token is not None
        expires_at = first.run.lease_expires_at
        operation = operation_service.ensure_scheduled(
            db, operation_key="customer-intelligence:leased-run", request_id=run_input.request_id,
            team_id=2, user_id=9, session_id=None, source_user_message_id=None,
            operation_type="customer_intelligence_refresh", resource_type="customer", resource_id=101,
        )
        check_time = now + timedelta(seconds=31 if expired else 10)
        due = run_service.list_due(db, team_id=2, now=check_time)
        assert [run.id for run in due] == ([first.run.id] if expired else [])
        assert run_service.list_due(db, team_id=3, now=check_time) == []
        projected = projector.project_run(db, run=first.run)
        assert projected is not None
        assert projected.status == AgentAsyncOperationStatus.RUNNING
        assert first.run.status == CustomerIntelligenceRunStatus.RUNNING
        assert first.run.attempt_count == 1
        assert first.run.lease_token == token
        assert first.run.lease_expires_at == expires_at

        claim = run_service.claim_for_execution(db, run_input, now=check_time, lease_seconds=30)
        if not expired:
            assert claim.status == CustomerIntelligenceRunClaimStatus.BUSY
            assert claim.run.lease_token == token
            assert claim.run.lease_expires_at == expires_at
            assert claim.run.attempt_count == 1
        elif max_attempts == 1:
            assert claim.status == CustomerIntelligenceRunClaimStatus.ATTEMPTS_EXHAUSTED
            assert claim.run.status == CustomerIntelligenceRunStatus.FAILED
            assert claim.run.lease_token is None
            assert claim.run.lease_expires_at is None
            assert claim.run.attempt_count == 1
            projector.project_run(db, run=claim.run)
            projection = operation_service.get_projection(db, team_id=2, user_id=9, public_id=str(operation.public_id))
            assert projection is not None
            assert projection.status == AgentAsyncOperationStatus.FAILED
            assert projection.finished_time is not None
            assert projection.events[-1].event_type == "FAILED"
        else:
            assert claim.status == CustomerIntelligenceRunClaimStatus.CLAIMED
            assert claim.run.status == CustomerIntelligenceRunStatus.RUNNING
            assert claim.run.attempt_count == 2
            assert claim.lease_token is not None
            assert claim.lease_token != token
            assert claim.run.lease_expires_at > check_time


def test_committed_event_late_agent_binding_converges_to_terminal_operation(runtime_sessions):
    run_service = CustomerIntelligenceRunService()
    operation_service = AgentAsyncOperationService()
    projector = CustomerIntelligenceOperationProjector(
        run_service=run_service, operation_service=operation_service,
    )
    service = CustomerIntelligenceRefreshService(
        run_service=run_service, async_operation_service=operation_service, operation_projector=projector,
    )
    run_input = CustomerIntelligenceRunInput(
        request_id="business-event-late-binding", event=_business_event(), scope="partial",
    )
    with runtime_sessions() as db:
        db.add(Customer(id=101, team_id=2, account_name="晚绑定客户", city="广州", creator_id="9"))
        claim = run_service.claim_for_execution(db, run_input)
        token = claim.lease_token
        assert token is not None
        progress = run_service.record_visible_progress_if_lease_owner(
            db, run_input, lease_token=token,
            progress={"title": "提炼客户事实", "content": "正在提炼客户事实"},
        )
        assert progress.status == CustomerIntelligenceRunLeaseMutationStatus.APPLIED
        db.commit()

    with runtime_sessions() as db:
        bound = service.bind_committed_event_to_agent(
            db, team_id=2, request_id=run_input.request_id,
            binding=AgentAsyncOperationBinding(
                team_id=2, user_id=9, session_id=554,
                source_user_message_id=1001, source_assistant_message_id=1002,
            ),
        )
        db.commit()
        assert bound.kick_required is False
        running = operation_service.get_projection(db, team_id=2, user_id=9, public_id=str(bound.operation_public_id))
        assert running is not None
        assert running.status == AgentAsyncOperationStatus.RUNNING
        assert [event.message for event in running.events if event.event_type == "PROGRESS"] == ["正在提炼客户事实"]

    with runtime_sessions() as db:
        completed = run_service.mark_succeeded_if_lease_owner(
            db, run_input, lease_token=token, result={"route": "answer_context", "degraded": False},
        )
        assert completed.status == CustomerIntelligenceRunLeaseMutationStatus.APPLIED
        projector.project_run(db, run=completed.run)
        db.commit()

    with runtime_sessions() as db:
        durable_run = run_service.get_by_request_id(db, team_id=2, request_id=run_input.request_id)
        terminal = operation_service.get_projection(db, team_id=2, user_id=9, public_id=str(bound.operation_public_id))
        assert durable_run is not None
        assert durable_run.status == CustomerIntelligenceRunStatus.SUCCESS
        assert terminal is not None
        assert terminal.status == AgentAsyncOperationStatus.SUCCEEDED
        assert terminal.finished_time is not None


def test_committed_event_snapshot_round_trips_without_cross_team_lookup(runtime_sessions):
    run_service = CustomerIntelligenceRunService()
    event_service = CustomerIntelligenceEventService()
    event = _business_event()
    request_id = "persisted-business-event"
    with runtime_sessions() as db:
        run_service.ensure_pending(
            db, CustomerIntelligenceRunInput(request_id=request_id, event=event, scope="partial"),
        )
        db.commit()
    with runtime_sessions() as db:
        assert run_service.get_by_request_id(db, team_id=3, request_id=request_id) is None
        run = run_service.get_by_request_id(db, team_id=2, request_id=request_id)
        assert run is not None
        restored = event_service.from_dict(run.event_json)
        assert restored is not None
        assert restored.to_dict() == event.to_dict()
        assert restored.trigger_type == "customer_contact_updated"
        assert restored.team_id == 2
        assert restored.event_key == "contact-event-1"


def test_terminal_run_projection_is_reconciled() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
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
    projector = CustomerIntelligenceOperationProjector(
        run_service=run_service,
        operation_service=operation_service,
    )

    try:
        recovery = projector.reconcile(db, team_id=2)
        db.commit()
        projection = operation_service.get_projection(
            db,
            team_id=2,
            user_id=9,
            public_id=str(operation.public_id),
        )

        assert recovery.projected == 1
        assert projection is not None
        assert projection.status == AgentAsyncOperationStatus.SUCCEEDED
        assert projection.finished_time == completed_at
        assert [event.event_type for event in projection.events][-1] == "SUCCEEDED"
    finally:
        db.close()
        engine.dispose()


class MemoryEventGraph:
    def __init__(self, *, outcome="success", before_result=None):
        self.outcome = outcome
        self.before_result = before_result
        self.inputs = []

    async def stream_events(self, graph_input):
        self.inputs.append(graph_input)
        yield {"kind": "event", "event": {"title": "更新客户记忆", "content": "已沉淀客户摘要和证据索引"}}
        if self.before_result is not None:
            self.before_result()
        if self.outcome == "exception":
            raise RuntimeError("memory unavailable")
        if self.outcome == "empty":
            return
        result = {
            "route": "write_memory", "event": graph_input["event"].to_dict(), "errors": [],
            "events": [{"event": "customer_intelligence_memory_written", "customer_id": 101}],
        }
        if self.outcome == "handled-error":
            result["errors"] = [{"event": "customer_intelligence_memory_write_failed"}]
        elif self.outcome == "skip":
            result["route"] = "skip"
        elif self.outcome == "no-write":
            result["events"] = []
        elif self.outcome == "missing-errors":
            result.pop("errors")
        elif self.outcome == "wrong-event":
            result["event"]["event_key"] = "another-event"
        elif self.outcome == "interrupted":
            result["__interrupt__"] = [{"value": "not-completed"}]
        yield {"kind": "result", "result": result}


def _registered_memory_event(service, runtime_sessions, *, bind=False):
    with runtime_sessions() as db:
        db.add(Customer(id=101, team_id=2, account_name="现行业务客户", city="广州", creator_id="9"))
        request = service.enqueue_committed_event_refresh(db, event=_business_event(), scope="partial")
        if bind:
            request = service.bind_committed_event_to_agent(
                db, team_id=2, request_id=request.request_id,
                binding=AgentAsyncOperationBinding(team_id=2, user_id=9, session_id=554),
            )
        db.commit()
        return request


@pytest.mark.asyncio
async def test_committed_event_executes_memory_graph_and_replays_terminal_operation(monkeypatch, runtime_sessions):
    monkeypatch.setattr("app.services.customer_intelligence_refresh_service.SessionLocal", runtime_sessions)
    graph = MemoryEventGraph()
    service = CustomerIntelligenceRefreshService(graph_service=graph)
    request = _registered_memory_event(service, runtime_sessions, bind=True)
    result = await service.run_committed_event_refresh(request)
    assert result["success"] is True
    assert result["route"] == "write_memory"
    assert graph.inputs[0]["event"] is request.event
    assert graph.inputs[0]["user_id"] == 9
    assert graph.inputs[0]["session_id"] == 554
    with runtime_sessions() as db:
        run = service.run_service.get_by_request_id(db, team_id=2, request_id=request.request_id)
        operation = service.async_operation_service.get_projection(
            db, team_id=2, user_id=9, public_id=request.operation_public_id,
        )
        assert run.status == CustomerIntelligenceRunStatus.SUCCESS
        assert run.result_json["error_count"] == 0
        assert run.lease_token is None
        assert operation.status == AgentAsyncOperationStatus.SUCCEEDED
        assert any(event.event_type == "PROGRESS" for event in operation.events)
        assert db.query(Customer).filter_by(id=101, team_id=2).one().account_name == "现行业务客户"
    assert (await service.run_committed_event_refresh(request))["success"] is True
    assert len(graph.inputs) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [
    "handled-error", "exception", "empty", "skip", "no-write", "missing-errors", "wrong-event", "interrupted",
])
async def test_committed_event_never_infers_success_from_stream_completion(monkeypatch, runtime_sessions, outcome):
    monkeypatch.setattr("app.services.customer_intelligence_refresh_service.SessionLocal", runtime_sessions)
    service = CustomerIntelligenceRefreshService(graph_service=MemoryEventGraph(outcome=outcome))
    request = _registered_memory_event(service, runtime_sessions, bind=True)
    result = await service.run_committed_event_refresh(request)
    assert result["success"] is False
    with runtime_sessions() as db:
        run = service.run_service.get_by_request_id(db, team_id=2, request_id=request.request_id)
        assert run.status == CustomerIntelligenceRunStatus.RETRY_PENDING
        assert run.next_retry_at is not None
        assert run.lease_token is None
        operation = service.async_operation_service.get_projection(
            db, team_id=2, user_id=9, public_id=request.operation_public_id,
        )
        assert operation.status == AgentAsyncOperationStatus.RETRY_SCHEDULED
        assert db.query(Customer).filter_by(id=101, team_id=2).one().account_name == "现行业务客户"


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "handled-error"])
async def test_committed_event_stale_executor_cannot_overwrite_new_lease(monkeypatch, runtime_sessions, outcome):
    monkeypatch.setattr("app.services.customer_intelligence_refresh_service.SessionLocal", runtime_sessions)
    reclaimed = []
    service = CustomerIntelligenceRefreshService()
    request = _registered_memory_event(service, runtime_sessions)

    def reclaim():
        with runtime_sessions() as db:
            run = service.run_service.get_by_request_id(db, team_id=2, request_id=request.request_id)
            run.lease_expires_at = business_now() - timedelta(seconds=1)
            claim = service.run_service.claim_for_execution(
                db, CustomerIntelligenceRunInput(request_id=request.request_id, event=request.event, scope="partial"),
            )
            assert claim.status == CustomerIntelligenceRunClaimStatus.CLAIMED
            reclaimed.append(claim.lease_token)
            db.commit()

    graph = MemoryEventGraph(outcome=outcome, before_result=reclaim)
    service.graph_service = graph
    result = await service.run_committed_event_refresh(request)
    assert result["success"] is False
    assert result["superseded"] is True
    with runtime_sessions() as db:
        run = service.run_service.get_by_request_id(db, team_id=2, request_id=request.request_id)
        assert run.status == CustomerIntelligenceRunStatus.RUNNING
        assert run.attempt_count == 2
        assert run.lease_token == reclaimed[0]


@pytest.mark.asyncio
async def test_committed_event_runs_existing_graph_without_profile_tables_or_storage(monkeypatch, runtime_sessions):
    from langgraph.checkpoint.memory import InMemorySaver

    from app.services.agent.customer_intelligence_graph import CustomerIntelligenceGraphService
    from tests.unit.test_customer_intelligence_graph import (
        FakeCustomerContextService,
        FakeCustomerMemoryStoreService,
        FakeDB,
    )

    monkeypatch.setattr("app.services.customer_intelligence_refresh_service.SessionLocal", runtime_sessions)
    memory = FakeCustomerMemoryStoreService()
    graph = CustomerIntelligenceGraphService(
        context_service=FakeCustomerContextService(), memory_store_service=memory,
        checkpointer=InMemorySaver(), session_factory=FakeDB,
    )
    service = CustomerIntelligenceRefreshService(graph_service=graph)
    request = _registered_memory_event(service, runtime_sessions)
    result = await service.run_committed_event_refresh(request)
    assert result["success"] is True
    assert result["route"] == "write_memory"
    assert len(memory.summary_writes) == 1
    assert memory.summary_writes[0]["tenant_id"] == 2
    assert memory.summary_writes[0]["customer_id"] == 101


def test_committed_event_recovery_does_not_read_profile_tables_or_steal_live_lease(runtime_sessions):
    service = CustomerIntelligenceRefreshService()
    run_input = CustomerIntelligenceRunInput(request_id="live-event", event=_business_event(), scope="partial")
    with runtime_sessions() as db:
        claim = service.run_service.claim_for_execution(db, run_input)
        token = claim.lease_token
        db.commit()
        recovered = service.recover_stale_runtime_state(db, team_id=2)
        assert recovered["pending_customers"] == recovered["failed_customers"] == 0
        assert recovered["stale_runs"] == 0
        db.commit()
        run = service.run_service.get_by_request_id(db, team_id=2, request_id="live-event")
        assert run.lease_token == token
        assert run.status == CustomerIntelligenceRunStatus.RUNNING
        assert run.attempt_count == 1


@pytest.mark.asyncio
async def test_committed_event_retry_uses_current_graph_and_preserves_agent_owner(monkeypatch, runtime_sessions):
    monkeypatch.setattr("app.services.customer_intelligence_refresh_service.SessionLocal", runtime_sessions)
    graph = MemoryEventGraph(outcome="handled-error")
    service = CustomerIntelligenceRefreshService(graph_service=graph)
    request = _registered_memory_event(service, runtime_sessions, bind=True)
    assert (await service.run_committed_event_refresh(request))["success"] is False
    with runtime_sessions() as db:
        run = service.run_service.get_by_request_id(db, team_id=2, request_id=request.request_id)
        run.next_retry_at = business_now() - timedelta(seconds=1)
        db.commit()
    graph.outcome = "success"
    result = await service.run_due_retries(team_id=2)
    assert result["succeeded"] == result["total"] == 1
    assert result["failed"] == 0
    assert len(graph.inputs) == 2
    assert graph.inputs[1]["resume_existing_execution"] is True
    assert graph.inputs[1]["session_id"] == 554
    assert graph.inputs[1]["user_id"] == 9


@pytest.mark.asyncio
async def test_retired_profile_request_is_rejected_without_registering_or_executing(monkeypatch, runtime_sessions):
    from dataclasses import replace

    monkeypatch.setattr("app.services.customer_intelligence_refresh_service.SessionLocal", runtime_sessions)
    graph = MemoryEventGraph()
    service = CustomerIntelligenceRefreshService(graph_service=graph)
    with runtime_sessions() as db:
        with pytest.raises(ValueError, match="不支持的客户智能业务事件"):
            service.enqueue_committed_event_refresh(
                db, event=replace(_business_event(), trigger_type="manual_refresh_requested"),
            )
        with pytest.raises(ValueError, match="客户档案能力已移除"):
            await service.trigger_manual_refresh(db, team_id=2, customer_id=101, actor_id="9", scope="full")
        assert db.query(CustomerIntelligenceRun).count() == 0
    assert graph.inputs == []


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["team_id", "customer_id", "event_key", "trigger_type", "retired"])
async def test_retry_rejects_foreign_or_retired_persisted_intent(monkeypatch, runtime_sessions, corruption):
    monkeypatch.setattr("app.services.customer_intelligence_refresh_service.SessionLocal", runtime_sessions)
    graph = MemoryEventGraph()
    service = CustomerIntelligenceRefreshService(graph_service=graph)
    request = _registered_memory_event(service, runtime_sessions)
    with runtime_sessions() as db:
        run = service.run_service.get_by_request_id(db, team_id=2, request_id=request.request_id)
        snapshot = dict(run.event_json)
        if corruption == "retired":
            run.trigger_type = snapshot["trigger_type"] = "manual_refresh_requested"
        else:
            snapshot[corruption] = 999 if corruption in {"team_id", "customer_id"} else "agent_customer_question"
        run.event_json = snapshot
        db.commit()
    result = await service.run_due_retries(team_id=2)
    assert result["total"] == 0
    assert graph.inputs == []
    with runtime_sessions() as db:
        run = service.run_service.get_by_request_id(db, team_id=2, request_id=request.request_id)
        assert run.status == CustomerIntelligenceRunStatus.FAILED
        assert run.attempt_count == 0


@pytest.mark.asyncio
async def test_current_graph_retry_clears_only_previous_invocation_errors(monkeypatch, runtime_sessions):
    from langgraph.checkpoint.memory import InMemorySaver

    from app.services.agent.customer_intelligence_graph import CustomerIntelligenceGraphService
    from tests.unit.test_customer_intelligence_graph import (
        FakeCustomerContextService,
        FakeCustomerMemoryStoreService,
        FakeDB,
    )

    class RecoverableMemory(FakeCustomerMemoryStoreService):
        unavailable = True

        def upsert_summary(self, *args, **kwargs):
            if self.unavailable:
                raise RuntimeError("temporarily unavailable")
            super().upsert_summary(*args, **kwargs)

    monkeypatch.setattr("app.services.customer_intelligence_refresh_service.SessionLocal", runtime_sessions)
    memory = RecoverableMemory()
    graph = CustomerIntelligenceGraphService(
        context_service=FakeCustomerContextService(), memory_store_service=memory,
        checkpointer=InMemorySaver(), session_factory=FakeDB,
    )
    service = CustomerIntelligenceRefreshService(graph_service=graph)
    request = _registered_memory_event(service, runtime_sessions)
    assert (await service.run_committed_event_refresh(request))["success"] is False
    with runtime_sessions() as db:
        run = service.run_service.get_by_request_id(db, team_id=2, request_id=request.request_id)
        assert run.status == CustomerIntelligenceRunStatus.RETRY_PENDING
        run.next_retry_at = business_now() - timedelta(seconds=1)
        db.commit()
    memory.unavailable = False
    result = await service.run_committed_event_refresh(request)
    assert result["success"] is True
    with runtime_sessions() as db:
        run = service.run_service.get_by_request_id(db, team_id=2, request_id=request.request_id)
        assert run.status == CustomerIntelligenceRunStatus.SUCCESS
        assert run.attempt_count == 2
        assert run.result_json["error_count"] == 0
    assert len(memory.summary_writes) == 1

from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.customer import Customer
from app.models.customer_intelligence_run import CustomerIntelligenceRun, CustomerIntelligenceRunStatus
from app.services.customer_intelligence_event_service import CustomerIntelligenceEventService
from app.services.customer_intelligence_reconciliation_service import (
    CustomerIntelligenceReconciliationService,
)
from app.services.customer_profile_watermark_service import CustomerProfileWatermarkService


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


class FakeContextService:
    def __init__(self, watermarks):
        self.watermarks = watermarks
        self.calls = []

    def build_context(self, db, *, team_id, customer_id, evidence_limit):
        self.calls.append((team_id, customer_id, evidence_limit))
        return SimpleNamespace(source_watermark=self.watermarks[customer_id])


class FakeProjectionService:
    def __init__(self):
        self.stale_calls = []

    def mark_stale(self, db, **kwargs):
        self.stale_calls.append(kwargs)


class FakeRefreshService:
    def __init__(self):
        self.calls = []

    def enqueue_committed_event_refresh(self, db, *, event, scope):
        self.calls.append((event, scope))
        return SimpleNamespace(scheduled=True)


class FakeRunService:
    def __init__(self, active_customer_ids=()):
        self.active_customer_ids = set(active_customer_ids)
        self.calls = []

    def has_active_for_customer(self, db, *, team_id, customer_id, scopes=("full", "partial")):
        self.calls.append(
            {
                "team_id": team_id,
                "customer_id": customer_id,
                "scopes": scopes,
            }
        )
        return customer_id in self.active_customer_ids


class FakeEventService(CustomerIntelligenceEventService):
    def __init__(self):
        self.calls = []

    def reconciliation_requested(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(event_key="event-key", customer_id=kwargs["customer_id"])


@pytest.fixture
def customer_db():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[Customer.__table__, CustomerIntelligenceRun.__table__])
    db = sessionmaker(bind=engine)()
    db.add_all(
        [
            Customer(id=1, public_id="cus_1", team_id=10, account_name="客户一", city="广州", creator_id="u"),
            Customer(id=2, public_id="cus_2", team_id=10, account_name="客户二", city="广州", creator_id="u"),
            Customer(id=3, public_id="cus_3", team_id=20, account_name="客户三", city="深圳", creator_id="u"),
        ]
    )
    db.commit()
    yield db
    db.close()
    engine.dispose()


def test_reconcile_schedules_missing_and_changed_profiles(monkeypatch, customer_db):
    context = FakeContextService(
        {
            1: {"activity_id": 2},
            2: {"activity_id": 1},
            3: {"activity_id": 4},
        }
    )
    projection = FakeProjectionService()
    refresh = FakeRefreshService()
    events = FakeEventService()
    current = {
        1: SimpleNamespace(current_profile_version_id=11),
        2: None,
        3: SimpleNamespace(current_profile_version_id=33),
    }
    versions = {
        1: SimpleNamespace(source_watermark_json={"activity_id": 1}),
        3: SimpleNamespace(source_watermark_json={"activity_id": 4}),
    }

    monkeypatch.setattr(
        "app.services.customer_intelligence_reconciliation_service.customer_profile_projection_crud.get_current",
        lambda db, *, team_id, customer_id, for_update=False: current.get(customer_id),
    )
    monkeypatch.setattr(
        "app.services.customer_intelligence_reconciliation_service.customer_profile_projection_crud.get_current_version",
        lambda db, *, team_id, customer_id, current: versions.get(customer_id),
    )

    service = CustomerIntelligenceReconciliationService(
        context_service=context,
        event_service=events,
        refresh_service=refresh,
        run_service=FakeRunService(),
        projection_service=projection,
        watermark_service=CustomerProfileWatermarkService(),
    )
    result = service.reconcile_once(customer_db, team_id=10, limit=10)

    assert result.success is True
    assert result.scanned == 2
    assert result.stale == 2
    assert result.scheduled == 2
    assert result.skipped == 0
    assert result.customer_ids == [1, 2]
    assert [call["customer_id"] for call in events.calls] == [1, 2]
    assert all(scope == "full" for _, scope in refresh.calls)
    assert [call["customer_id"] for call in projection.stale_calls] == [1, 2]
    assert all(call[2] == 0 for call in context.calls)


def test_reconcile_does_not_enqueue_duplicate_profile_run_when_customer_is_already_active(
    monkeypatch, customer_db
):
    context = FakeContextService({1: {"activity_id": 2}, 2: {"activity_id": 2}})
    projection = FakeProjectionService()
    refresh = FakeRefreshService()
    events = FakeEventService()
    run_service = FakeRunService(active_customer_ids={1})
    current = {
        1: SimpleNamespace(current_profile_version_id=11),
        2: SimpleNamespace(current_profile_version_id=22),
    }
    versions = {
        1: SimpleNamespace(source_watermark_json={"activity_id": 1}),
        2: SimpleNamespace(source_watermark_json={"activity_id": 1}),
    }

    monkeypatch.setattr(
        "app.services.customer_intelligence_reconciliation_service.customer_profile_projection_crud.get_current",
        lambda db, *, team_id, customer_id, for_update=False: current.get(customer_id),
    )
    monkeypatch.setattr(
        "app.services.customer_intelligence_reconciliation_service.customer_profile_projection_crud.get_current_version",
        lambda db, *, team_id, customer_id, current: versions.get(customer_id),
    )

    service = CustomerIntelligenceReconciliationService(
        context_service=context,
        event_service=events,
        refresh_service=refresh,
        run_service=run_service,
        projection_service=projection,
        watermark_service=CustomerProfileWatermarkService(),
    )
    result = service.reconcile_once(customer_db, team_id=10, limit=10)

    assert result.success is True
    assert result.stale == 2
    assert result.scheduled == 1
    assert result.skipped == 1
    assert result.scheduled_customer_ids == [2]
    assert [call["customer_id"] for call in events.calls] == [2]
    assert run_service.calls[0]["customer_id"] == 1
    assert run_service.calls[1]["customer_id"] == 2


def test_reconcile_is_idempotent_for_equal_watermark_and_supports_cursor(monkeypatch, customer_db):
    context = FakeContextService({1: {"activity_id": 1}, 2: {"activity_id": 1}, 3: {"activity_id": 1}})
    current = {
        1: SimpleNamespace(current_profile_version_id=11),
        2: SimpleNamespace(current_profile_version_id=22),
        3: SimpleNamespace(current_profile_version_id=33),
    }
    versions = {key: SimpleNamespace(source_watermark_json={"activity_id": 1}) for key in current}
    monkeypatch.setattr(
        "app.services.customer_intelligence_reconciliation_service.customer_profile_projection_crud.get_current",
        lambda db, *, team_id, customer_id, for_update=False: current.get(customer_id),
    )
    monkeypatch.setattr(
        "app.services.customer_intelligence_reconciliation_service.customer_profile_projection_crud.get_current_version",
        lambda db, *, team_id, customer_id, current: versions.get(customer_id),
    )

    service = CustomerIntelligenceReconciliationService(context_service=context)
    result = service.reconcile_once(customer_db, limit=5, after_customer_id=1, dry_run=True)

    assert result.success is True
    assert result.customer_ids == [2, 3]
    assert result.stale == 0
    assert result.scheduled == 0
    assert result.next_customer_id is None
    assert result.dry_run is True

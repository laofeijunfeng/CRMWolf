from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.customer import Customer, CustomerProduct
from app.models.customer_intelligence_run import CustomerIntelligenceRun, CustomerIntelligenceRunStatus
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.product import Product
from app.services.customer_intelligence_context_service import CustomerIntelligenceContextService
from app.services.customer_intelligence_event_service import CustomerIntelligenceEventService
from app.services.customer_intelligence_reconciliation_service import (
    CustomerIntelligenceReconciliationService,
)
from app.services.customer_profile_watermark_service import CustomerProfileWatermarkService

from tests.unit.test_customer_intelligence_context_service import _session


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
    metadata = {"source_snapshot_hash": "a" * 64,
                "source_policy_version": "LEGACY_PROFILE_ELIGIBLE_V1",
                "source_provenance_status": "VERIFIED"}
    context = FakeContextService({key: {"activity_id": 1, **metadata} for key in (1, 2, 3)})
    current = {
        1: SimpleNamespace(current_profile_version_id=11),
        2: SimpleNamespace(current_profile_version_id=22),
        3: SimpleNamespace(current_profile_version_id=33),
    }
    versions = {key: SimpleNamespace(source_watermark_json={"activity_id": 1, **metadata}) for key in current}
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

def test_reconcile_pages_past_two_hundred_without_skipping_team_customers(monkeypatch, customer_db):
    customer_db.add_all([
        Customer(id=customer_id, team_id=10, account_name=f"客户{customer_id}", city="广州", creator_id="u")
        for customer_id in range(4, 205)
    ])
    customer_db.commit()
    watermark = {"activity_id": 1, "source_snapshot_hash": "a" * 64,
                 "source_policy_version": "LEGACY_PROFILE_ELIGIBLE_V1",
                 "source_provenance_status": "VERIFIED"}
    context = FakeContextService({customer_id: watermark for customer_id in [1, 2, *range(4, 205)]})
    monkeypatch.setattr(
        "app.services.customer_intelligence_reconciliation_service.customer_profile_projection_crud.get_current",
        lambda db, *, team_id, customer_id, for_update=False: SimpleNamespace(current_profile_version_id=11),
    )
    monkeypatch.setattr(
        "app.services.customer_intelligence_reconciliation_service.customer_profile_projection_crud.get_current_version",
        lambda db, *, team_id, customer_id, current: SimpleNamespace(source_watermark_json={
            **watermark, "source_snapshot_hash": "b" * 64,
        }),
    )
    service = CustomerIntelligenceReconciliationService(context_service=context)

    first = service.reconcile_once(customer_db, team_id=10, limit=500, dry_run=True)
    second = service.reconcile_once(customer_db, team_id=10, limit=500,
                                    after_customer_id=first.next_customer_id, dry_run=True)

    assert (first.scanned, first.stale, first.next_customer_id) == (200, 200, 201)
    assert (second.scanned, second.stale, second.next_customer_id) == (3, 3, None)
    assert first.customer_ids + second.customer_ids == [1, 2, *range(4, 205)]
    assert len(context.calls) == 203


@pytest.mark.parametrize("unknown_key,unknown_value", [
    ("source_snapshot_hash", None),
    ("source_policy_version", None),
    ("source_provenance_status", "UNVERIFIED"),
])
def test_reconcile_refreshes_unknown_source_metadata_even_when_equal(
    monkeypatch, customer_db, unknown_key, unknown_value,
):
    watermark = {"activity_id": 1, "source_snapshot_hash": "a" * 64,
                 "source_policy_version": "LEGACY_PROFILE_ELIGIBLE_V1",
                 "source_provenance_status": "VERIFIED"}
    watermark[unknown_key] = unknown_value
    context = FakeContextService({1: watermark})
    monkeypatch.setattr(
        "app.services.customer_intelligence_reconciliation_service.customer_profile_projection_crud.get_current",
        lambda db, *, team_id, customer_id, for_update=False: SimpleNamespace(current_profile_version_id=11),
    )
    monkeypatch.setattr(
        "app.services.customer_intelligence_reconciliation_service.customer_profile_projection_crud.get_current_version",
        lambda db, *, team_id, customer_id, current: SimpleNamespace(source_watermark_json=watermark),
    )
    service = CustomerIntelligenceReconciliationService(context_service=context)

    result = service.reconcile_once(customer_db, team_id=10, limit=1, dry_run=True)

    assert result.customer_ids == [1]
    assert (result.stale, result.skipped) == (1, 0)


@pytest.mark.parametrize("catalog_change", ["rename", "deactivate"])
def test_reconcile_refreshes_published_profile_on_catalog_hash_change(monkeypatch, catalog_change):
    engine, db = _session()
    try:
        customers = [
            Customer(id=101, team_id=2, account_name="产品客户", city="广州", creator_id="u"),
            Customer(id=102, team_id=2, account_name="同产品客户", city="广州", creator_id="u"),
        ]
        product = Product(
            id=801, public_id="prd_catalog", team_id=2, code="CATALOG", name="旧名称",
            is_active=True, created_by="u",
        )
        db.add_all([
            *customers,
            product,
            *[CustomerProduct(customer_id=item.id, product_id=801, team_id=2) for item in customers],
            *[CustomerLegacySourceProgress(
                team_id=2, customer_id=item.id, provenance_status="VERIFIED",
                eligible_revision=4, deletion_revision=0,
            ) for item in customers],
        ])
        db.commit()

        context_service = CustomerIntelligenceContextService()
        baseline = {
            item.id: context_service.build_context(db, team_id=2, customer_id=item.id, evidence_limit=0)
            for item in customers
        }
        published = {
            item.id: SimpleNamespace(source_watermark_json=dict(baseline[item.id].source_watermark))
            for item in customers
        }
        assert all(version.source_watermark_json["source_snapshot_hash"] for version in published.values())
        assert all(version.source_watermark_json["source_policy_version"] for version in published.values())
        monkeypatch.setattr(
            "app.services.customer_intelligence_reconciliation_service.customer_profile_projection_crud.get_current",
            lambda db, *, team_id, customer_id, for_update=False: SimpleNamespace(current_profile_version_id=11),
        )
        monkeypatch.setattr(
            "app.services.customer_intelligence_reconciliation_service.customer_profile_projection_crud.get_current_version",
            lambda db, *, team_id, customer_id, current: published[customer_id],
        )
        refresh = FakeRefreshService()
        events = FakeEventService()
        service = CustomerIntelligenceReconciliationService(
            context_service=context_service,
            event_service=events,
            refresh_service=refresh,
            run_service=FakeRunService(),
            projection_service=FakeProjectionService(),
        )

        equal = service.reconcile_once(db, team_id=2)
        assert (equal.stale, equal.scheduled, equal.skipped) == (0, 0, 2)

        if catalog_change == "rename":
            product.name = "新名称"
        else:
            product.is_active = False
        db.flush()
        changed = {
            item.id: context_service.build_context(db, team_id=2, customer_id=item.id, evidence_limit=0)
            for item in customers
        }
        for item in customers:
            before = baseline[item.id].source_watermark
            after = changed[item.id].source_watermark
            assert after["eligible_revision"] == before["eligible_revision"]
            assert after["deletion_revision"] == before["deletion_revision"]
            assert after["source_snapshot_hash"] != before["source_snapshot_hash"]

        result = service.reconcile_once(db, team_id=2)
        assert result.success is True
        assert (result.stale, result.scheduled, result.scheduled_customer_ids) == (2, 2, [101, 102])
        assert [event[1] for event in refresh.calls] == ["full", "full"]
        assert [call["payload"]["source_watermark"] for call in events.calls] == [
            changed[item.id].source_watermark for item in customers
        ]

        for item in customers:
            published[item.id].source_watermark_json = dict(changed[item.id].source_watermark)
        equal_again = service.reconcile_once(db, team_id=2)
        assert (equal_again.stale, equal_again.scheduled, equal_again.skipped) == (0, 0, 2)
    finally:
        db.close()
        engine.dispose()


def test_customer_version_only_update_does_not_change_legacy_profile_source(monkeypatch):
    engine, db = _session()
    try:
        customer = Customer(
            id=101, team_id=2, account_name="档案客户", city="广州", creator_id="u",
            last_modified_time=datetime(2026, 1, 1),
        )
        db.add_all([
            customer,
            CustomerLegacySourceProgress(
                team_id=2, customer_id=101, provenance_status="VERIFIED",
            ),
        ])
        db.commit()

        context_service = CustomerIntelligenceContextService()
        before = context_service.build_context(db, team_id=2, customer_id=101, evidence_limit=0)
        published = SimpleNamespace(source_watermark_json={
            **before.source_watermark, "customer_updated_at": datetime(2026, 1, 1).isoformat(),
        })
        monkeypatch.setattr(
            "app.services.customer_intelligence_reconciliation_service.customer_profile_projection_crud.get_current",
            lambda db, *, team_id, customer_id, for_update=False: SimpleNamespace(current_profile_version_id=11),
        )
        monkeypatch.setattr(
            "app.services.customer_intelligence_reconciliation_service.customer_profile_projection_crud.get_current_version",
            lambda db, *, team_id, customer_id, current: published,
        )
        service = CustomerIntelligenceReconciliationService(context_service=context_service)

        customer.version += 1
        db.flush()
        after = context_service.build_context(db, team_id=2, customer_id=101, evidence_limit=0)
        assert customer.last_modified_time > datetime(2026, 1, 1)
        assert before.strong_context.customer == after.strong_context.customer
        assert before.source_watermark["source_snapshot_hash"] == after.source_watermark["source_snapshot_hash"]
        assert before.source_watermark == after.source_watermark
        comparison, needs_refresh, _ = service._inspect_customer(db, team_id=2, customer_id=101)
        assert comparison.advanced_keys == ()
        assert needs_refresh is False
    finally:
        db.close()
        engine.dispose()


def test_customer_business_field_change_updates_eligible_snapshot_and_progress():
    engine, db = _session()
    try:
        customer = Customer(id=101, team_id=2, account_name="档案客户", city="广州", creator_id="u")
        db.add(customer)
        db.commit()
        context_service = CustomerIntelligenceContextService()
        before = context_service.build_context(db, team_id=2, customer_id=101, evidence_limit=0)

        from app.crud.customer import customer_crud
        from app.schemas.customer import CustomerUpdate

        customer_crud.update(db, customer, CustomerUpdate(city="上海", expected_version=customer.version))
        after = context_service.build_context(db, team_id=2, customer_id=101, evidence_limit=0)
        assert after.strong_context.customer.city == "上海"
        assert after.source_watermark["source_snapshot_hash"] != before.source_watermark["source_snapshot_hash"]
        assert after.source_watermark["eligible_revision"] == before.source_watermark["eligible_revision"] + 1
    finally:
        db.close()
        engine.dispose()


@pytest.mark.parametrize(
    ("metadata_key", "mismatched_value"),
    [
        ("source_snapshot_hash", "b" * 64),
        ("source_policy_version", "LEGACY_PROFILE_ELIGIBLE_V2"),
        ("source_provenance_status", "UNVERIFIED"),
    ],
)
def test_reconcile_refreshes_missing_or_changed_source_metadata(monkeypatch, metadata_key, mismatched_value):
    engine, db = _session()
    try:
        db.add(Customer(id=101, team_id=2, account_name="档案客户", city="广州", creator_id="u"))
        db.add(CustomerLegacySourceProgress(
            team_id=2, customer_id=101, provenance_status="VERIFIED", eligible_revision=4,
        ))
        db.commit()
        context_service = CustomerIntelligenceContextService()
        watermark = context_service.build_context(db, team_id=2, customer_id=101, evidence_limit=0).source_watermark
        assert watermark[metadata_key] != mismatched_value
        published_watermark = dict(watermark)
        published_watermark.pop(metadata_key)
        published = SimpleNamespace(source_watermark_json=published_watermark)
        monkeypatch.setattr(
            "app.services.customer_intelligence_reconciliation_service.customer_profile_projection_crud.get_current",
            lambda db, *, team_id, customer_id, for_update=False: SimpleNamespace(current_profile_version_id=11),
        )
        monkeypatch.setattr(
            "app.services.customer_intelligence_reconciliation_service.customer_profile_projection_crud.get_current_version",
            lambda db, *, team_id, customer_id, current: published,
        )
        events = FakeEventService()
        service = CustomerIntelligenceReconciliationService(
            context_service=context_service,
            event_service=events,
            refresh_service=FakeRefreshService(),
            run_service=FakeRunService(),
            projection_service=FakeProjectionService(),
        )

        upgrade = service.reconcile_once(db, team_id=2)
        assert upgrade.success is True
        assert upgrade.scheduled_customer_ids == [101]
        assert events.calls[0]["payload"]["source_watermark"] == watermark

        published.source_watermark_json[metadata_key] = mismatched_value
        mismatch = service.reconcile_once(db, team_id=2)
        assert mismatch.success is True
        assert mismatch.scheduled_customer_ids == [101]
        assert events.calls[-1]["payload"]["source_watermark"] == watermark

        published.source_watermark_json[metadata_key] = watermark[metadata_key]
        matched = service.reconcile_once(db, team_id=2)
        assert (matched.stale, matched.scheduled, matched.skipped) == (0, 0, 1)
    finally:
        db.close()
        engine.dispose()

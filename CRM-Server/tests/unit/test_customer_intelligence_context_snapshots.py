"""Business context snapshots ignore concurrency metadata, not business changes."""

from datetime import datetime

from app.models.customer import Customer
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.services.customer_intelligence_context_service import CustomerIntelligenceContextService
from tests.unit.test_customer_intelligence_context_service import _session


def test_customer_version_only_update_does_not_change_source_snapshot():
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
        customer.version += 1
        db.flush()
        after = context_service.build_context(db, team_id=2, customer_id=101, evidence_limit=0)
        assert customer.last_modified_time > datetime(2026, 1, 1)
        assert before.strong_context.customer == after.strong_context.customer
        assert before.source_watermark["source_snapshot_hash"] == after.source_watermark["source_snapshot_hash"]
        assert before.source_watermark == after.source_watermark
    finally:
        db.close()
        engine.dispose()


def test_customer_business_field_change_updates_source_snapshot():
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
    finally:
        db.close()
        engine.dispose()

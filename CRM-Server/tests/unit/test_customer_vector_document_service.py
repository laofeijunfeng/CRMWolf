from datetime import datetime

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_intelligence_run import CustomerIntelligenceRun, CustomerIntelligenceRunStatus
from app.models.customer_vector_document import CustomerVectorDocument, CustomerVectorDocumentSyncStatus
from app.models.deal_journey import (
    CustomerDealJourney,
    CustomerDealJourneyEvent,
    DealJourneyEventType,
    DealJourneyStatus,
)
from app.models.industry import Industry
from app.services.customer_activity_kinds import CustomerActivityKind
from app.services.customer_evidence_builder import customer_evidence_builder
from app.services.industry_display_service import industry_display_service
from app.services.customer_qdrant_index_service import CustomerEvidenceDocument, SourceType
from app.services.customer_vector_document_service import customer_vector_document_service
from app.services.customer_vector_sync_service import CustomerVectorSyncService
from app.services.deal_journey_service import deal_journey_service


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[
        Customer.__table__,
        CustomerActivity.__table__,
        CustomerDealJourney.__table__,
        CustomerDealJourneyEvent.__table__,
        CustomerVectorDocument.__table__,
        CustomerIntelligenceRun.__table__,
        Industry.__table__,
    ])
    Session = sessionmaker(bind=engine)
    return Session()


def _customer_activity(
    db,
    *,
    source_content: str = "张总说今天可以开始签合同了",
    account_name: str = "测试客户",
) -> CustomerActivity:
    customer = Customer(
        team_id=2,
        account_name=account_name,
        city="上海",
        creator_id="9",
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    activity = CustomerActivity(
        team_id=2,
        customer_id=customer.id,
        activity_kind=CustomerActivityKind.PHONE_FOLLOW_UP,
        title="电话跟进",
        source_content=source_content,
        content_json='{"content":"张总确认进入合同阶段","risks":[]}',
        summary="张总确认进入合同阶段",
        occurred_at=datetime(2026, 8, 2, 10, 30, 0),
        creator_id="9",
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


def test_builder_creates_follow_up_evidence_from_customer_activity():
    db = _session()
    activity = _customer_activity(db)

    evidence = customer_evidence_builder.from_customer_activity(activity)

    assert evidence is not None
    assert evidence.tenant_id == 2
    assert evidence.team_id == 2
    assert evidence.customer_id == activity.customer_id
    assert evidence.source_type == "follow_up"
    assert evidence.source_object_id == str(activity.id)
    assert evidence.business_object_type == "customer_activity"
    assert "张总说今天可以开始签合同了" in evidence.text
    assert "张总确认进入合同阶段" in evidence.text
    assert len(evidence.text_hash) == 64
    assert evidence.qdrant_point_id == evidence.document_key


def test_service_upserts_customer_activity_metadata_idempotently():
    db = _session()
    activity = _customer_activity(db)

    first = customer_vector_document_service.upsert_customer_activity(db, activity)
    activity.source_content = "张总说合同审批已经启动"
    activity.summary = "合同审批已经启动"
    db.commit()
    db.refresh(activity)
    second = customer_vector_document_service.upsert_customer_activity(db, activity)

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert second.sync_status == CustomerVectorDocumentSyncStatus.PENDING
    assert "合同审批已经启动" in second.text
    assert db.query(CustomerVectorDocument).count() == 1


def test_service_upserts_customer_profile_metadata():
    db = _session()
    government = Industry(id=1, level=1, code="government", name="政府", sort_order=1, is_active=1)
    public = Industry(
        id=2,
        level=2,
        parent_id=1,
        code="government_public",
        name="公共机构",
        sort_order=1,
        is_active=1,
    )
    customer = Customer(
        team_id=2,
        account_name="越秀金融",
        industry="government_public",
        city="广州",
        company_background="地方金融控股集团。",
        main_business="金融控股与投资管理。",
        project_background="希望规范采购流程。",
        creator_id="9",
        profile_generated_time=datetime(2026, 8, 2, 11, 0, 0),
    )
    db.add_all([government, public, customer])
    db.commit()
    db.refresh(customer)

    document = customer_vector_document_service.upsert_customer_profile(db, customer)

    assert document is not None
    assert document.source_type == "customer_profile"
    assert document.business_object_type == "customer_profile"
    assert "行业: 政府/公共机构" in document.text
    assert "government_public" not in document.text
    assert "地方金融控股集团" in document.text
    assert document.sync_status == CustomerVectorDocumentSyncStatus.PENDING


def test_service_rebuilds_stale_customer_profile_metadata_for_alias_aware_evidence():
    db = _session()
    stale_customer = Customer(
        id=101,
        team_id=2,
        account_name="中国科学院信息工程研究所",
        city="北京",
        creator_id="9",
    )
    fresh_customer = Customer(
        id=102,
        team_id=2,
        account_name="越秀金融控股集团",
        city="广州",
        creator_id="9",
    )
    missing_document_customer = Customer(
        id=103,
        team_id=2,
        account_name="上海数据交易所",
        city="上海",
        creator_id="9",
    )
    db.add_all([stale_customer, fresh_customer, missing_document_customer])
    db.commit()
    stale_document = customer_vector_document_service.upsert_customer_profile(db, stale_customer)
    fresh_document = customer_vector_document_service.upsert_customer_profile(db, fresh_customer)
    assert stale_document is not None
    assert fresh_document is not None
    stale_document.metadata_version = 1
    stale_document.sync_status = CustomerVectorDocumentSyncStatus.SYNCED
    fresh_document.metadata_version = customer_evidence_builder.metadata_version
    fresh_document.sync_status = CustomerVectorDocumentSyncStatus.SYNCED
    db.commit()

    rebuilt_customer_ids = customer_vector_document_service.rebuild_stale_customer_profiles(
        db,
        team_id=2,
        limit=10,
        commit=False,
    )

    assert rebuilt_customer_ids == [101, 103]
    rebuilt_documents = {
        int(document.customer_id): document
        for document in db.query(CustomerVectorDocument).order_by(CustomerVectorDocument.customer_id.asc()).all()
    }
    assert rebuilt_documents[101].metadata_version == customer_evidence_builder.metadata_version
    assert rebuilt_documents[101].sync_status == CustomerVectorDocumentSyncStatus.PENDING
    assert "常用简称候选" in rebuilt_documents[101].text
    assert rebuilt_documents[102].sync_status == CustomerVectorDocumentSyncStatus.SYNCED
    assert rebuilt_documents[103].metadata_version == customer_evidence_builder.metadata_version
    assert rebuilt_documents[103].sync_status == CustomerVectorDocumentSyncStatus.PENDING


def test_industry_display_service_sanitizes_legacy_customer_brief_markdown():
    db = _session()
    government = Industry(id=1, level=1, code="government", name="政府", sort_order=1, is_active=1)
    public = Industry(
        id=2,
        level=2,
        parent_id=1,
        code="government_public",
        name="公共机构",
        sort_order=1,
        is_active=1,
    )
    db.add_all([government, public])
    db.commit()

    markdown = "### 行业与同行客户\ngovernment_public"
    sanitized = industry_display_service.sanitize_markdown(db, markdown, industry_code="government_public")

    assert sanitized == "### 同行业客户\n政府/公共机构"


def test_service_upserts_customer_brief_metadata_idempotently():
    db = _session()
    customer = Customer(
        team_id=2,
        account_name="越秀金融",
        city="广州",
        creator_id="9",
        customer_brief_markdown="## 客户概况\n客户已进入 POC。",
        customer_brief_json='{"overview":{"procurement_progress":{"content":"客户已进入 POC。"}}}',
        customer_brief_generated_time=datetime(2026, 8, 2, 11, 30, 0),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    first = customer_vector_document_service.upsert_customer_brief(db, customer)
    customer.customer_brief_markdown = "## 客户概况\n客户计划签合同。"
    db.commit()
    db.refresh(customer)
    second = customer_vector_document_service.upsert_customer_brief(db, customer)

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert second.source_type == "customer_brief"
    assert "客户计划签合同" in second.text
    assert db.query(CustomerVectorDocument).count() == 1


def test_service_upserts_deal_journey_event_metadata():
    db = _session()
    customer = Customer(team_id=2, account_name="越秀金融", city="广州", creator_id="9")
    db.add(customer)
    db.commit()
    db.refresh(customer)
    journey = CustomerDealJourney(
        team_id=2,
        customer_id=customer.id,
        name="越秀金融采购项目",
        status=DealJourneyStatus.ACTIVE,
    )
    db.add(journey)
    db.commit()
    db.refresh(journey)
    event = CustomerDealJourneyEvent(
        team_id=2,
        deal_journey_id=journey.id,
        customer_id=customer.id,
        event_type=DealJourneyEventType.OPPORTUNITY_STAGE_CHANGED,
        event_time=datetime(2026, 8, 2, 12, 0, 0),
        source_type="opportunity_stage_snapshot",
        source_id=301,
        summary="商机阶段推进到 POC",
        metadata_json='{"stage_name":"POC","win_probability":60}',
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    document = customer_vector_document_service.upsert_deal_journey_event(db, event)

    assert document is not None
    assert document.source_type == "business_flow"
    assert document.business_object_type == "deal_journey_event"
    assert "商机阶段推进到 POC" in document.text
    assert "stage_name" in document.text


def test_deal_journey_record_event_stages_business_flow_evidence_without_committing():
    db = _session()
    customer = Customer(team_id=2, account_name="越秀金融", city="广州", creator_id="9")
    db.add(customer)
    db.commit()
    db.refresh(customer)
    journey = CustomerDealJourney(
        team_id=2,
        customer_id=customer.id,
        name="越秀金融采购项目",
        status=DealJourneyStatus.ACTIVE,
    )
    db.add(journey)
    db.commit()
    db.refresh(journey)

    event = deal_journey_service.record_event(
        db,
        deal_journey_id=journey.id,
        team_id=2,
        customer_id=customer.id,
        event_type=DealJourneyEventType.OPPORTUNITY_STAGE_CHANGED,
        source_type="opportunity_stage_snapshot",
        source_id=301,
        event_time=datetime(2026, 8, 2, 12, 0, 0),
        summary="商机阶段推进到 POC",
        metadata={"stage_name": "POC", "win_probability": 60},
    )

    assert event is not None
    assert event.id is not None
    document = db.query(CustomerVectorDocument).one()
    assert document.source_type == "business_flow"
    assert document.source_object_id == str(event.id)
    assert document.sync_status == CustomerVectorDocumentSyncStatus.PENDING
    run = db.query(CustomerIntelligenceRun).one()
    assert run.status == CustomerIntelligenceRunStatus.PENDING
    assert run.trigger_type == "deal_journey_event_recorded"
    assert run.customer_id == customer.id
    assert run.scope == "brief"
    assert run.event_json["source"]["source_type"] == "deal_journey_event"


def test_deal_journey_record_event_does_not_enqueue_duplicate_customer_intelligence_run():
    db = _session()
    customer = Customer(team_id=2, account_name="越秀金融", city="广州", creator_id="9")
    db.add(customer)
    db.commit()
    db.refresh(customer)
    journey = CustomerDealJourney(
        team_id=2,
        customer_id=customer.id,
        name="越秀金融采购项目",
        status=DealJourneyStatus.ACTIVE,
    )
    db.add(journey)
    db.commit()
    db.refresh(journey)

    first = deal_journey_service.record_event(
        db,
        deal_journey_id=journey.id,
        team_id=2,
        customer_id=customer.id,
        event_type=DealJourneyEventType.OPPORTUNITY_STAGE_CHANGED,
        source_type="opportunity_stage_snapshot",
        source_id=301,
        event_time=datetime(2026, 8, 2, 12, 0, 0),
        summary="商机阶段推进到 POC",
        metadata={"stage_name": "POC", "win_probability": 60},
    )
    second = deal_journey_service.record_event(
        db,
        deal_journey_id=journey.id,
        team_id=2,
        customer_id=customer.id,
        event_type=DealJourneyEventType.OPPORTUNITY_STAGE_CHANGED,
        source_type="opportunity_stage_snapshot",
        source_id=301,
        event_time=datetime(2026, 8, 2, 12, 0, 0),
        summary="商机阶段推进到 POC",
        metadata={"stage_name": "POC", "win_probability": 60},
    )

    assert first is not None
    assert second is not None
    assert second.id == first.id
    assert db.query(CustomerDealJourneyEvent).count() == 1
    assert db.query(CustomerVectorDocument).count() == 1
    assert db.query(CustomerIntelligenceRun).count() == 1


def test_service_marks_customer_activity_evidence_deleted():
    db = _session()
    activity = _customer_activity(db)
    customer_vector_document_service.upsert_customer_activity(db, activity)

    count = customer_vector_document_service.mark_customer_activity_deleted(db, activity)
    document = db.query(CustomerVectorDocument).one()

    assert count == 1
    assert document.sync_status == CustomerVectorDocumentSyncStatus.DELETE_PENDING
    assert document.sync_error is None


class FakeEmbeddingService:
    def embed_query(self, db, team_id: int, text: str) -> list[float]:
        assert team_id == 2
        assert text
        return [0.1, 0.2, 0.3]


class FailingEmbeddingService:
    def embed_query(self, db, team_id: int, text: str) -> list[float]:
        raise RuntimeError("embedding failed")


class FakeIndexWriter:
    def __init__(self, *, collection_created: bool = False) -> None:
        self.collection_created = collection_created
        self.ensure_collection_calls = 0
        self.upserted: list[CustomerEvidenceDocument] = []
        self.deleted_sources: list[tuple[int, int, SourceType, str]] = []

    def ensure_collection(self) -> bool:
        self.ensure_collection_calls += 1
        return self.collection_created

    def upsert_evidence(self, document: CustomerEvidenceDocument) -> None:
        self.upserted.append(document)

    def delete_by_source(
        self,
        tenant_id: int,
        team_id: int,
        source_type: SourceType,
        source_object_id: str,
    ) -> None:
        self.deleted_sources.append((tenant_id, team_id, source_type, source_object_id))


def test_vector_sync_upserts_pending_metadata_to_qdrant_and_marks_synced():
    db = _session()
    activity = _customer_activity(db)
    metadata = customer_vector_document_service.upsert_customer_activity(db, activity)
    index_writer = FakeIndexWriter()
    sync_service = CustomerVectorSyncService(
        embedding_service=FakeEmbeddingService(),
        index_writer=index_writer,
    )

    stats = sync_service.sync_once(db, limit=10)

    assert metadata is not None
    assert stats.scanned == 1
    assert stats.upserted == 1
    assert stats.failed == 0
    assert index_writer.upserted[0].id == metadata.qdrant_point_id
    assert index_writer.upserted[0].vector == [0.1, 0.2, 0.3]
    document = db.query(CustomerVectorDocument).one()
    assert document.sync_status == CustomerVectorDocumentSyncStatus.SYNCED
    assert document.synced_at is not None


def test_vector_sync_deletes_delete_pending_metadata_from_qdrant():
    db = _session()
    activity = _customer_activity(db)
    customer_vector_document_service.upsert_customer_activity(db, activity)
    customer_vector_document_service.mark_customer_activity_deleted(db, activity)
    index_writer = FakeIndexWriter()
    sync_service = CustomerVectorSyncService(
        embedding_service=FakeEmbeddingService(),
        index_writer=index_writer,
    )

    stats = sync_service.sync_once(db, limit=10)

    assert stats.scanned == 1
    assert stats.deleted == 1
    assert index_writer.deleted_sources == [(2, 2, "follow_up", str(activity.id))]
    document = db.query(CustomerVectorDocument).one()
    assert document.sync_status == CustomerVectorDocumentSyncStatus.DELETED
    assert document.synced_at is not None


def test_vector_sync_marks_failed_without_blocking_metadata():
    db = _session()
    activity = _customer_activity(db)
    customer_vector_document_service.upsert_customer_activity(db, activity)
    sync_service = CustomerVectorSyncService(
        embedding_service=FailingEmbeddingService(),
        index_writer=FakeIndexWriter(),
    )

    stats = sync_service.sync_once(db, limit=10)

    assert stats.scanned == 1
    assert stats.failed == 1
    document = db.query(CustomerVectorDocument).one()
    assert document.sync_status == CustomerVectorDocumentSyncStatus.FAILED
    assert document.sync_error == "embedding failed"


def test_vector_sync_retries_failed_metadata_when_provider_recovers():
    db = _session()
    activity = _customer_activity(db)
    customer_vector_document_service.upsert_customer_activity(db, activity)
    failing_sync_service = CustomerVectorSyncService(
        embedding_service=FailingEmbeddingService(),
        index_writer=FakeIndexWriter(),
    )
    failing_sync_service.sync_once(db, limit=10)
    failed_document = db.query(CustomerVectorDocument).one()
    assert failed_document.sync_status == CustomerVectorDocumentSyncStatus.FAILED

    index_writer = FakeIndexWriter()
    recovered_sync_service = CustomerVectorSyncService(
        embedding_service=FakeEmbeddingService(),
        index_writer=index_writer,
    )
    stats = recovered_sync_service.sync_once(db, limit=10)

    assert stats.scanned == 1
    assert stats.upserted == 1
    assert stats.failed == 0
    assert len(index_writer.upserted) == 1
    recovered_document = db.query(CustomerVectorDocument).one()
    assert recovered_document.sync_status == CustomerVectorDocumentSyncStatus.SYNCED
    assert recovered_document.sync_error is None


def test_service_requeues_synced_and_failed_documents_for_rebuilt_vector_index():
    db = _session()
    synced_activity = _customer_activity(db, account_name="测试客户1")
    synced_document = customer_vector_document_service.upsert_customer_activity(db, synced_activity)
    failed_activity = _customer_activity(db, source_content="客户准备启动 POC", account_name="测试客户2")
    failed_document = customer_vector_document_service.upsert_customer_activity(db, failed_activity)
    delete_pending_activity = _customer_activity(db, source_content="客户记录需要删除", account_name="测试客户3")
    delete_pending_document = customer_vector_document_service.upsert_customer_activity(db, delete_pending_activity)
    deleted_activity = _customer_activity(db, source_content="客户记录已经删除", account_name="测试客户4")
    deleted_document = customer_vector_document_service.upsert_customer_activity(db, deleted_activity)

    assert synced_document is not None
    assert failed_document is not None
    assert delete_pending_document is not None
    assert deleted_document is not None
    synced_document.sync_status = CustomerVectorDocumentSyncStatus.SYNCED
    synced_document.synced_at = datetime(2026, 8, 2, 12, 0, 0)
    failed_document.sync_status = CustomerVectorDocumentSyncStatus.FAILED
    failed_document.sync_error = "old vector schema mismatch"
    delete_pending_document.sync_status = CustomerVectorDocumentSyncStatus.DELETE_PENDING
    deleted_document.sync_status = CustomerVectorDocumentSyncStatus.DELETED
    db.commit()

    requeued = customer_vector_document_service.requeue_indexable_documents(db)

    assert requeued == 2
    refreshed = {
        document.id: document
        for document in db.query(CustomerVectorDocument).order_by(CustomerVectorDocument.id.asc()).all()
    }
    assert refreshed[synced_document.id].sync_status == CustomerVectorDocumentSyncStatus.PENDING
    assert refreshed[synced_document.id].synced_at is None
    assert refreshed[failed_document.id].sync_status == CustomerVectorDocumentSyncStatus.PENDING
    assert refreshed[failed_document.id].sync_error is None
    assert refreshed[delete_pending_document.id].sync_status == CustomerVectorDocumentSyncStatus.DELETE_PENDING
    assert refreshed[deleted_document.id].sync_status == CustomerVectorDocumentSyncStatus.DELETED


def test_vector_sync_requeues_history_when_collection_is_rebuilt():
    db = _session()
    activity = _customer_activity(db)
    document = customer_vector_document_service.upsert_customer_activity(db, activity)
    assert document is not None
    document.sync_status = CustomerVectorDocumentSyncStatus.SYNCED
    document.synced_at = datetime(2026, 8, 2, 12, 0, 0)
    db.commit()
    index_writer = FakeIndexWriter(collection_created=True)
    sync_service = CustomerVectorSyncService(
        embedding_service=FakeEmbeddingService(),
        index_writer=index_writer,
    )

    stats = sync_service.sync_once(db, limit=10)

    assert index_writer.ensure_collection_calls == 1
    assert stats.scanned == 1
    assert stats.upserted == 1
    assert index_writer.upserted[0].id == document.qdrant_point_id
    refreshed = db.query(CustomerVectorDocument).one()
    assert refreshed.sync_status == CustomerVectorDocumentSyncStatus.SYNCED
    assert refreshed.synced_at is not None

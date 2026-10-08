"""The publication boundary certifies a particular legacy-source version, not a customer flag."""

from dataclasses import replace
from datetime import datetime

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.orm import sessionmaker

from app.models.agent import AgentMemoryEntry
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_fact import CustomerFact, CustomerFactSource
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.customer_profile_projection import CustomerProfileCurrent, CustomerProfileProjectionVersion
from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent
from app.models.sales_commitment import FollowUpTask, FollowUpTaskEvent
from app.models.team import Team
from app.services.agent.customer_profile_projection_graph import CustomerProfileProjectionGraphService
from app.services.customer_fact_extraction_service import CustomerFactExtractionResult, ExtractedCustomerFact
from app.services.customer_intelligence_context_service import CustomerIntelligenceContextService
from app.services.customer_intelligence_event_service import CustomerIntelligenceEvent, CustomerIntelligenceSource
from app.services.customer_profile_projection_service import (
    CustomerProfileProjectionError,
    CustomerProfileProjectionService,
)
from app.services.customer_profile_version_certification import certify_profile_version, is_certified_profile_version
from tests.unit.test_customer_intelligence_context_service import _seed_customer_context, _session


@pytest.fixture
def source_db(tmp_path):
    engine, db = _session(database_url=f"sqlite:///{tmp_path / 'profile-source.db'}")
    Team.__table__.create(engine, checkfirst=True)
    CustomerProfileProjectionVersion.__table__.create(engine, checkfirst=True)
    CustomerProfileCurrent.__table__.create(engine, checkfirst=True)
    AgentMemoryEntry.__table__.create(engine, checkfirst=True)
    db.add(Team(id=2, name="来源验收团队", code="SRC-2", owner_id=9))
    db.commit()
    _seed_customer_context(db)
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _fresh_draft(db, *, target_sections=()):
    service = CustomerProfileProjectionService()
    context = CustomerIntelligenceContextService().build_context(
        db,
        team_id=2,
        customer_id=101,
        query_text="",
        evidence_limit=0,
    )
    return service.draft_from_context(
        context=context.to_dict(),
        source_event_key=None,
        target_sections=target_sections,
    )


def test_verified_source_publication_keeps_superseded_version_certified(source_db):
    service = CustomerProfileProjectionService()
    first = service.publish(source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db))
    source_db.commit()
    assert is_certified_profile_version(first.version)
    assert first.version.current_situation_json["headline"] == "越秀金融"

    # A source writer advances the eligible revision in the same transaction.
    from app.crud.customer import customer_crud
    from app.schemas.customer import CustomerUpdate

    customer = source_db.query(Customer).filter_by(team_id=2, id=101).one()
    customer_crud.update(source_db, customer, CustomerUpdate(city="深圳"))
    source_db.commit()
    second = service.publish(source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db))
    source_db.commit()
    assert second.version.id != first.version.id
    assert second.version.current_situation_json["customer_basics"]["city"] == "深圳"
    assert first.version.publication_status == "SUPERSEDED"
    assert is_certified_profile_version(first.version)
    assert is_certified_profile_version(second.version)


def test_pausing_publication_keeps_certified_current_pointer_and_source_writes(source_db, monkeypatch):
    from app.core.config import get_settings
    from app.crud.customer import customer_crud
    from app.schemas.customer import CustomerUpdate

    service = CustomerProfileProjectionService()
    prior = service.publish(source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db))
    source_db.commit()
    monkeypatch.setattr(get_settings(), "LEGACY_PROFILE_PUBLICATION_ENABLED", False)
    customer = source_db.query(Customer).filter_by(team_id=2, id=101).one()
    customer_crud.update(source_db, customer, CustomerUpdate(city="深圳"))
    source_db.commit()

    with pytest.raises(CustomerProfileProjectionError) as exc:
        service.publish(source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db))
    assert exc.value.code == "PROFILE_PUBLICATION_DISABLED"
    source_db.rollback()
    assert source_db.query(CustomerProfileProjectionVersion).count() == 1
    current = source_db.query(CustomerProfileCurrent).filter_by(team_id=2, customer_id=101).one()
    assert current.current_profile_version_id == prior.version.id
    assert is_certified_profile_version(prior.version)
    assert source_db.query(Customer).filter_by(team_id=2, id=101).one().city == "深圳"


def test_unverified_legacy_progress_is_traced_and_certified_on_publish(source_db):
    progress = source_db.query(CustomerLegacySourceProgress).filter_by(team_id=2, customer_id=101).one()
    assert progress.provenance_status == "UNVERIFIED"
    publication = CustomerProfileProjectionService().publish(
        source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db)
    )
    source_db.commit()
    assert progress.provenance_status == "VERIFIED"
    assert publication.version.source_watermark_json["source_provenance_status"] == "VERIFIED"
    assert is_certified_profile_version(publication.version)


@pytest.mark.parametrize("branch", ["full", "partial", "duplicate"])
def test_unknown_event_origin_blocks_only_this_customer_and_keeps_certified_pointer(source_db, branch):
    service = CustomerProfileProjectionService()
    original = service.publish(source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db))
    source_db.commit()
    source_db.add(CustomerDealJourney(id=920, team_id=2, customer_id=101, name="来源不明的旅程"))
    source_db.add(
        CustomerDealJourneyEvent(
            id=921,
            team_id=2,
            customer_id=101,
            deal_journey_id=920,
            event_type="activity_added",
            source_type="customer_activity",
            source_id=99999,
            event_time=datetime(2026, 8, 3, 10, 0, 0),
        )
    )
    source_db.commit()
    draft = _fresh_draft(source_db, target_sections=("current_situation",) if branch == "partial" else ())
    with pytest.raises(CustomerProfileProjectionError) as exc:
        service.publish(source_db, team_id=2, customer_id=101, draft=draft)
    assert exc.value.code == "PROFILE_SOURCE_FENCE_UNVERIFIED"
    source_db.rollback()
    current = source_db.query(CustomerProfileCurrent).filter_by(team_id=2, customer_id=101).one()
    assert current.current_profile_version_id == original.version.id
    assert is_certified_profile_version(original.version)
    assert source_db.query(CustomerProfileProjectionVersion).count() == 1


def test_unknown_indirect_fact_source_cannot_certify_profile(source_db):
    fact = CustomerFact(
        fact_key="missing-indirect-origin",
        tenant_id=2,
        team_id=2,
        customer_id=101,
        fact_type="risk",
        content="无法核证的间接事实",
        confidence=0.8,
    )
    source_db.add(fact)
    source_db.flush()
    source_db.add(
        CustomerFactSource(
            fact_id=fact.id,
            source_type="business_flow",
            source_object_id="99999",
        )
    )
    source_db.commit()

    with pytest.raises(CustomerProfileProjectionError) as exc:
        CustomerProfileProjectionService().publish(source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db))
    assert exc.value.code == "PROFILE_SOURCE_FENCE_UNVERIFIED"
    assert source_db.query(CustomerProfileProjectionVersion).count() == 0


def test_task_event_from_different_legacy_activity_cannot_certify_profile(source_db):
    source_db.add(
        CustomerActivity(
            id=703,
            team_id=2,
            customer_id=101,
            activity_kind="PHONE_FOLLOW_UP",
            source_content="另一个旧活动",
            creator_id="9",
            owner_id="9",
            submission_source="FORM",
        )
    )
    source_db.add(
        FollowUpTask(
            id=930,
            team_id=2,
            customer_id=101,
            creator_id="9",
            owner_id="9",
            title="原活动的任务",
            due_at=datetime(2026, 10, 1),
            source_type="customer_activity",
            source_key="activity:701",
            source_activity_id=701,
            task_hash="task-930",
        )
    )
    source_db.flush()
    source_db.add(
        FollowUpTaskEvent(
            id=931,
            team_id=2,
            task_id=930,
            event_type="UPDATED",
            source_type="customer_activity",
            source_activity_id=703,
            payload_json={"content": "借其他旧活动伪造的任务更新"},
        )
    )
    source_db.commit()
    context = CustomerIntelligenceContextService().build_context(
        source_db, team_id=2, customer_id=101, evidence_limit=0
    )
    assert context.strong_context.follow_up_task_events == []
    with pytest.raises(CustomerProfileProjectionError) as exc:
        CustomerProfileProjectionService().publish(source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db))
    assert exc.value.code == "PROFILE_SOURCE_FENCE_UNVERIFIED"
    assert source_db.query(CustomerProfileProjectionVersion).count() == 0


def test_indirect_fact_conflicting_excluded_activity_hint_blocks_publication(source_db):
    source_db.add(CustomerDealJourney(id=920, team_id=2, customer_id=101, name="混合来源旅程"))
    source_db.add_all(
        [
            CustomerActivity(
                id=921,
                team_id=2,
                customer_id=101,
                activity_kind="PHONE_FOLLOW_UP",
                source_content="第一条私有活动",
                creator_id="9",
                owner_id="9",
                submission_source="ASSISTANT_2",
                submission_id="turn-921",
                submission_fingerprint="a" * 64,
            ),
            CustomerActivity(
                id=922,
                team_id=2,
                customer_id=101,
                activity_kind="PHONE_FOLLOW_UP",
                source_content="第二条私有活动",
                creator_id="9",
                owner_id="9",
                submission_source="ASSISTANT_2",
                submission_id="turn-922",
                submission_fingerprint="b" * 64,
            ),
        ]
    )
    source_db.flush()
    source_db.add(
        CustomerDealJourneyEvent(
            id=923,
            team_id=2,
            customer_id=101,
            deal_journey_id=920,
            event_type="activity_added",
            source_type="customer_activity",
            source_id=921,
            event_time=datetime(2026, 8, 3, 10),
        )
    )
    fact = CustomerFact(
        fact_key="conflicting-indirect-hint",
        tenant_id=2,
        team_id=2,
        customer_id=101,
        fact_type="risk",
        content="伪造的间接关联",
        confidence=0.8,
    )
    source_db.add(fact)
    source_db.flush()
    source_db.add(
        CustomerFactSource(
            fact_id=fact.id,
            source_type="deal_journey_event",
            source_object_id="923",
            business_object_type="customer_activity",
            business_object_id="922",
        )
    )
    source_db.commit()

    with pytest.raises(CustomerProfileProjectionError) as exc:
        CustomerProfileProjectionService().publish(source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db))
    assert exc.value.code == "PROFILE_SOURCE_FENCE_UNVERIFIED"
    assert source_db.query(CustomerProfileProjectionVersion).count() == 0


def test_actual_task_event_fact_with_parent_hint_is_certifiable(source_db):
    task = FollowUpTask(
        id=930,
        team_id=2,
        customer_id=101,
        creator_id="9",
        owner_id="9",
        title="旧活动任务",
        due_at=datetime(2026, 10, 1),
        source_type="customer_activity",
        source_key="activity:701",
        source_activity_id=701,
        task_hash="task-930",
    )
    source_db.add(task)
    source_db.flush()
    source_db.add(
        FollowUpTaskEvent(
            id=931,
            team_id=2,
            task_id=930,
            event_type="COMPLETED",
            source_type="customer_activity",
            source_activity_id=701,
        )
    )
    fact = CustomerFact(
        fact_key="real-task-event",
        tenant_id=2,
        team_id=2,
        customer_id=101,
        fact_type="risk",
        content="已完成客户任务",
        confidence=0.8,
    )
    source_db.add(fact)
    source_db.flush()
    source_db.add(
        CustomerFactSource(
            fact_id=fact.id,
            source_type="follow_up_task_event",
            source_object_id="931",
            business_object_type="follow_up_task",
            business_object_id="930",
        )
    )
    source_db.commit()

    result = CustomerProfileProjectionService().publish(
        source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db)
    )
    source_db.commit()
    assert is_certified_profile_version(result.version)
    assert any(
        item["id"] == fact.id
        for item in CustomerIntelligenceContextService()
        .build_context(
            source_db,
            team_id=2,
            customer_id=101,
            evidence_limit=0,
        )
        .strong_context.customer_facts
    )


def test_deleted_activity_task_event_with_null_fk_remains_eligible(source_db):
    from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone

    task = FollowUpTask(
        id=930,
        team_id=2,
        customer_id=101,
        creator_id="9",
        owner_id="9",
        title="删除后独立任务",
        due_at=datetime(2026, 10, 1),
        source_type="customer_activity",
        source_key="activity:701",
        source_activity_id=701,
        task_hash="task-930",
    )
    source_db.add(task)
    source_db.flush()
    source_db.add(
        CustomerActivityDeletionTombstone(
            team_id=2,
            customer_id=101,
            activity_id=701,
            submission_source="FORM",
        )
    )
    source_db.query(CustomerActivity).filter_by(id=701).delete()
    task.source_activity_id = None
    source_db.commit()

    from app.crud.sales_commitment import follow_up_task_event_crud

    before = source_db.query(CustomerLegacySourceProgress).filter_by(team_id=2, customer_id=101).one().eligible_revision
    event = follow_up_task_event_crud.record_status_change(
        source_db, task=task, event_type="COMPLETED", actor_id="9", previous_status="OPEN"
    )
    source_db.commit()
    after = source_db.query(CustomerLegacySourceProgress).filter_by(team_id=2, customer_id=101).one().eligible_revision
    assert any(
        item["id"] == event.id
        for item in CustomerIntelligenceContextService()
        .build_context(
            source_db,
            team_id=2,
            customer_id=101,
            evidence_limit=0,
        )
        .strong_context.follow_up_task_events
    )
    assert after == before + 1
    assert event.source_activity_id is None
    result = CustomerProfileProjectionService().publish(
        source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db)
    )
    source_db.commit()
    assert is_certified_profile_version(result.version)


def test_explicit_assistant_event_is_excluded_without_blocking_legacy_publication(source_db):
    source_db.add(CustomerDealJourney(id=920, team_id=2, customer_id=101, name="混合来源旅程"))
    source_db.add(
        CustomerActivity(
            id=921,
            team_id=2,
            customer_id=101,
            activity_kind="PHONE_FOLLOW_UP",
            source_content="2.0 独占内容",
            creator_id="9",
            owner_id="9",
            submission_source="ASSISTANT_2",
            submission_id="turn-921",
            submission_fingerprint="a" * 64,
        )
    )
    source_db.flush()
    source_db.add(
        CustomerDealJourneyEvent(
            id=922,
            team_id=2,
            customer_id=101,
            deal_journey_id=920,
            event_type="activity_added",
            source_type="customer_activity",
            source_id=921,
            event_time=datetime(2026, 8, 3, 10, 0, 0),
            summary="2.0 独占内容",
        )
    )
    source_db.commit()
    result = CustomerProfileProjectionService().publish(
        source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db)
    )
    source_db.commit()
    assert is_certified_profile_version(result.version)
    assert "2.0 独占内容" not in str(result.version.follow_up_process_json)


def test_rejects_draft_after_eligible_source_changed_without_moving_pointer(source_db):
    service = CustomerProfileProjectionService()
    before = service.publish(source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db))
    source_db.commit()
    stale_draft = _fresh_draft(source_db)

    from app.crud.customer import customer_crud
    from app.schemas.customer import CustomerUpdate

    customer = source_db.query(Customer).filter_by(team_id=2, id=101).one()
    customer_crud.update(source_db, customer, CustomerUpdate(city="深圳"))
    source_db.commit()
    with pytest.raises(CustomerProfileProjectionError) as exc:
        service.publish(source_db, team_id=2, customer_id=101, draft=stale_draft)
    assert exc.value.code == "PROFILE_PUBLISH_REJECTED_STALE"
    current = source_db.query(CustomerProfileCurrent).filter_by(team_id=2, customer_id=101).one()
    assert current.current_profile_version_id == before.version.id
    assert source_db.query(CustomerProfileProjectionVersion).count() == 1


def test_rejects_ungrounded_text_even_with_a_real_source_watermark(source_db):
    service = CustomerProfileProjectionService()
    draft = _fresh_draft(source_db)
    poisoned = replace(
        draft,
        sections=draft.sections.model_copy(
            update={"current_situation": {**draft.sections.current_situation, "summary": "2.0 未授权秘密"}}
        ),
    )
    with pytest.raises(CustomerProfileProjectionError) as exc:
        service.publish(source_db, team_id=2, customer_id=101, draft=poisoned)
    assert exc.value.code == "PROFILE_SOURCE_FENCE_UNVERIFIED"
    assert source_db.query(CustomerProfileProjectionVersion).count() == 0


def test_partial_cannot_inherit_uncertified_predecessor(source_db):
    service = CustomerProfileProjectionService()
    prior = service.publish(source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db))
    source_db.commit()
    # Simulate an immutable legacy row with no publisher source attestation.
    prior.version.source_attestation_json = None
    source_db.commit()
    assert not is_certified_profile_version(prior.version)
    with pytest.raises(CustomerProfileProjectionError) as exc:
        service.publish(
            source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db, target_sections=("current_situation",))
        )
    assert exc.value.code == "PROFILE_SOURCE_FENCE_UNVERIFIED"
    assert source_db.query(CustomerProfileProjectionVersion).count() == 1


def test_duplicate_cannot_reactivate_uncertified_version(source_db):
    service = CustomerProfileProjectionService()
    draft = _fresh_draft(source_db)
    first = service.publish(source_db, team_id=2, customer_id=101, draft=draft)
    source_db.commit()
    first.version.source_attestation_json = None
    source_db.commit()
    with pytest.raises(CustomerProfileProjectionError) as exc:
        service.publish(source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db))
    assert exc.value.code == "PROFILE_SOURCE_FENCE_UNVERIFIED"
    assert source_db.query(CustomerProfileProjectionVersion).count() == 1


def test_certificate_detects_mutated_body_and_citations(source_db):
    service = CustomerProfileProjectionService()
    version = service.publish(source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db)).version
    source_db.commit()
    assert is_certified_profile_version(version)
    original = version.current_situation_json
    version.current_situation_json = {**original, "summary": "篡改正文"}
    assert not is_certified_profile_version(version)
    version.current_situation_json = original
    version.evidence_refs_json = [{"evidence_key": "activity:999", "source_type": "customer_activity"}]
    assert not is_certified_profile_version(version)


def test_unverified_version_cannot_be_signed_or_read(source_db):
    version = (
        CustomerProfileProjectionService()
        .publish(source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db))
        .version
    )
    version.source_watermark_json = {**version.source_watermark_json, "source_provenance_status": "UNVERIFIED"}
    assert not is_certified_profile_version(version)
    with pytest.raises(ValueError, match="provenance"):
        certify_profile_version(version)


def test_stale_event_retains_complete_certified_watermark(source_db):
    service = CustomerProfileProjectionService()
    publication = service.publish(source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db))
    source_db.commit()
    certified_watermark = publication.version.source_watermark_json

    stale = service.mark_stale(
        source_db,
        team_id=2,
        customer_id=101,
        source_watermark={"event_key": "activity:2:updated", "trigger_type": "customer_activity_updated"},
        reason="待刷新",
    )

    assert stale.latest_source_watermark_json["eligible_revision"] == certified_watermark["eligible_revision"]
    assert stale.latest_source_watermark_json["source_snapshot_hash"] == certified_watermark["source_snapshot_hash"]
    assert stale.latest_source_watermark_json["event_key"] == "activity:2:updated"


class WorkflowFactExtractor:
    def __init__(self, *, extract_fact=False):
        self.extract_fact = extract_fact
        self.calls = 0

    async def extract(self, db, **kwargs):
        self.calls += 1
        return CustomerFactExtractionResult(
            summary="客户事实更新",
            facts=[
                ExtractedCustomerFact(
                    fact_type="need",
                    subject="CRM 项目",
                    content="客户需要先完成 POC 验证。",
                    confidence=0.9,
                    evidence_quote="本周开始 POC",
                    evidence_keys=["activity:701"],
                )
            ]
            if self.extract_fact
            else [],
        )


def _profile_workflow(db, *, extractor, projection_service=None):
    return CustomerProfileProjectionGraphService(
        fact_extraction_service=extractor,
        projection_service=projection_service,
        checkpointer=InMemorySaver(),
        session_factory=sessionmaker(bind=db.get_bind()),
    )


async def _refresh_profile(workflow, *, resume=False, event=None):
    event = event or CustomerIntelligenceEvent(
        event_key="activity:701:updated",
        trigger_type="customer_activity_updated",
        tenant_id=2,
        team_id=2,
        customer_id=101,
        occurred_at=datetime(2026, 8, 3, 10),
        source=CustomerIntelligenceSource("customer_activity", "701"),
        summary="客户确认进入 POC",
    )
    chunks = [
        chunk
        async for chunk in workflow.stream_events(
            {
                "team_id": 2,
                "user_id": 9,
                "session_id": 10,
                "run_id": 88,
                "event": event,
                "resume_existing_execution": resume,
            }
        )
    ]
    return next(chunk["result"] for chunk in chunks if chunk.get("kind") == "result")


@pytest.mark.asyncio
async def test_workflow_certifies_newly_extracted_fact_in_same_refresh(source_db):
    workflow = _profile_workflow(source_db, extractor=WorkflowFactExtractor(extract_fact=True))
    result = await _refresh_profile(workflow)
    source_db.expire_all()
    current = source_db.query(CustomerProfileCurrent).filter_by(team_id=2, customer_id=101).one()
    version = source_db.get(CustomerProfileProjectionVersion, current.current_profile_version_id)
    assert result["profile_projection_result"]["published"]
    assert is_certified_profile_version(version)
    assert any(fact["content"] == "客户需要先完成 POC 验证。" for fact in version.long_term_context_json["facts"])


@pytest.mark.asyncio
async def test_workflow_rebuilds_changed_sections_without_inheriting_legacy_profile(source_db):
    from app.crud.customer import customer_crud
    from app.schemas.customer import CustomerUpdate

    service = CustomerProfileProjectionService()
    prior = service.publish(source_db, team_id=2, customer_id=101, draft=_fresh_draft(source_db))
    prior.version.source_attestation_json = None
    source_db.commit()
    customer = source_db.query(Customer).filter_by(team_id=2, id=101).one()
    customer_crud.update(source_db, customer, CustomerUpdate(city="深圳"))
    source_db.commit()
    result = await _refresh_profile(
        _profile_workflow(source_db, extractor=WorkflowFactExtractor()),
        event=CustomerIntelligenceEvent(
            event_key="customer:101:updated",
            trigger_type="customer_business_object_updated",
            tenant_id=2,
            team_id=2,
            customer_id=101,
            occurred_at=datetime(2026, 8, 3, 10),
            source=CustomerIntelligenceSource("customer", "101"),
            summary="客户城市已更新",
        ),
    )
    source_db.expire_all()
    current = source_db.query(CustomerProfileCurrent).filter_by(team_id=2, customer_id=101).one()
    version = source_db.get(CustomerProfileProjectionVersion, current.current_profile_version_id)
    assert result["profile_projection_result"]["published"]
    assert is_certified_profile_version(version)
    assert version.current_situation_json["customer_basics"]["city"] == "深圳"
    assert version.long_term_context_json["customer"]["city"] == "深圳"


@pytest.mark.asyncio
async def test_workflow_resume_recomposes_after_source_changed_at_failed_publication(source_db):
    from app.crud.customer import customer_crud
    from app.schemas.customer import CustomerUpdate

    class InterruptedPublisher(CustomerProfileProjectionService):
        def __init__(self):
            super().__init__()
            self.interrupted = False

        def publish(self, db, **kwargs):
            if not self.interrupted:
                self.interrupted = True
                raise RuntimeError("publication interrupted")
            return super().publish(db, **kwargs)

    extractor = WorkflowFactExtractor(extract_fact=True)
    workflow = _profile_workflow(
        source_db,
        extractor=extractor,
        projection_service=InterruptedPublisher(),
    )
    with pytest.raises(RuntimeError, match="publication interrupted"):
        await _refresh_profile(workflow)
    source_db.expire_all()
    persisted_fact_ids = {row.id for row in source_db.query(CustomerFact).all()}
    persisted_source_count = source_db.query(CustomerFactSource).count()
    customer = source_db.query(Customer).filter_by(team_id=2, id=101).one()
    customer_crud.update(source_db, customer, CustomerUpdate(city="深圳"))
    source_db.commit()
    result = await _refresh_profile(workflow, resume=True)
    source_db.expire_all()
    current = source_db.query(CustomerProfileCurrent).filter_by(team_id=2, customer_id=101).one()
    version = source_db.get(CustomerProfileProjectionVersion, current.current_profile_version_id)
    assert result["profile_projection_result"]["published"]
    assert is_certified_profile_version(version)
    assert version.long_term_context_json["customer"]["city"] == "深圳"
    assert extractor.calls == 1
    assert {row.id for row in source_db.query(CustomerFact).all()} == persisted_fact_ids
    assert source_db.query(CustomerFactSource).count() == persisted_source_count

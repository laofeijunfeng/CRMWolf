from datetime import datetime
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.schemas.customer_profile import CustomerProfileSections
from app.services.agent.customer_profile_projection_graph import (
    CustomerProfileProjectionGraphService,
    build_customer_profile_graph_config,
    build_customer_profile_thread_id,
)
from app.services.customer_fact_extraction_service import (
    CustomerFactExtractionResult,
    ExtractedCustomerFact,
)
from app.services.customer_fact_service import CustomerFactCandidateAssessment
from app.services.customer_intelligence_event_service import (
    CustomerIntelligenceEvent,
    CustomerIntelligenceSource,
)
from app.services.customer_profile_projection_quality import CustomerProfileQualityReport
from app.services.customer_profile_projection_service import CustomerProfileProjectionDraft


class FakeDB:
    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class FakeContext:
    def to_agent_payload(self):
        return {
            "strong_context": {
                "customer": {"id": 101, "account_name": "示例客户"},
                "customer_facts": [],
                "deal_journeys": [{"id": 11, "name": "CRM 项目", "status": "ACTIVE"}],
                "recorded_follow_ups": [],
                "sales_commitments": [],
            },
            "semantic_evidence": [
                {
                    "evidence_id": "activity:1",
                    "source_type": "customer_activity",
                    "source_id": "1",
                    "title": "跟进记录",
                }
            ],
            "source_watermark": {"activity_id": 1, "journey_event_id": 2},
        }


class FakeContextService:
    def build_context(self, db, **kwargs):
        return FakeContext()


class FakeMemoryService:
    def build_context_payload(self, db, **kwargs):
        return {"summaries": [{"key": "latest", "value": "客户进入 POC"}]}


class FakeFactExtractor:
    async def extract(self, db, **kwargs):
        return CustomerFactExtractionResult(
            summary="提炼一条需求事实",
            facts=[
                ExtractedCustomerFact(
                    fact_type="need",
                    subject="CRM 项目",
                    content="客户需要先完成 POC 验证。",
                    confidence=0.9,
                    evidence_quote="先完成 POC 验证",
                    evidence_keys=["activity:1"],
                )
            ],
        )


class FakeFactService:
    def __init__(self, assessment=None):
        self.calls = []
        self.assessment = assessment or CustomerFactCandidateAssessment(action="upsert", reason="test-approved")

    def assess_candidate_against_context(self, *, candidate, existing_facts):
        return self.assessment

    def upsert_fact(self, db, fact_input):
        self.calls.append(fact_input)
        return SimpleNamespace(id=501, version=1)


class FakeProjectionService:
    def __init__(self, *, publication_status="PUBLISHED", quality_report=None):
        self.publish_calls = []
        self.legacy_calls = []
        self.assessment_calls = 0
        self.publication_status = publication_status
        self.quality_report = quality_report

    def draft_from_context(self, *, context, source_event_key, source_watermark, target_sections):
        return CustomerProfileProjectionDraft(
            sections=CustomerProfileSections(
                current_situation={"summary": "客户正在推进 CRM 项目，当前进入 POC 验证。"},  # noqa: RUF001
                current_journeys=[{"id": "11", "title": "CRM 项目", "status": "ACTIVE"}],
                important_changes=[{"summary": "本次跟进确认进入 POC。"}],
                long_term_context={"customer": "示例客户"},
                follow_up_process=[{"summary": "销售已记录 POC 验证过程。"}],
                recorded_follow_ups=[],
            ),
            evidence_refs=[{"evidence_key": "activity:1", "source_type": "customer_activity"}],
            source_watermark=source_watermark,
            source_event_key=source_event_key,
            target_sections=target_sections,
        )

    def assess_draft(self, draft):
        self.assessment_calls += 1
        return SimpleNamespace(
            sections=draft.sections,
            quality_report=CustomerProfileQualityReport(),
        )

    def validate_draft(self, draft):
        return draft.sections

    def lint_draft(self, draft):
        return CustomerProfileQualityReport()

    def publish(self, db, **kwargs):
        self.publish_calls.append(kwargs)
        return SimpleNamespace(
            deduplicated=False,
            publication_status=self.publication_status,
            quality_report=self.quality_report,
            version=SimpleNamespace(profile_version=3, public_id="cpv_3"),
        )


def _event() -> CustomerIntelligenceEvent:
    return CustomerIntelligenceEvent(
        event_key="activity:1:updated",
        trigger_type="customer_activity_updated",
        tenant_id=7,
        team_id=7,
        customer_id=101,
        occurred_at=datetime(2026, 8, 30, 10, 0),
        source=CustomerIntelligenceSource("customer_activity", "1"),
        summary="客户确认进入 POC",
    )


@pytest.mark.asyncio
async def test_profile_workflow_publishes_projection_without_legacy_services():
    projection = FakeProjectionService()
    fact_service = FakeFactService()
    service = CustomerProfileProjectionGraphService(
        context_service=FakeContextService(),
        memory_store_service=FakeMemoryService(),
        fact_extraction_service=FakeFactExtractor(),
        fact_service=fact_service,
        projection_service=projection,
        checkpointer=InMemorySaver(),
        session_factory=FakeDB,
    )

    chunks = [
        chunk
        async for chunk in service.stream_events(
            {
                "team_id": 7,
                "user_id": 9,
                "session_id": 10,
                "run_id": 88,
                "event": _event(),
            }
        )
    ]
    result = next(chunk["result"] for chunk in chunks if chunk.get("kind") == "result")

    assert result["route"] == "refresh_profile"
    assert result["profile_projection_result"]["profile_version"] == 3
    assert len(projection.publish_calls) == 1
    assert len(fact_service.calls) == 1
    assert fact_service.calls[0].source.evidence_id == "activity:1"
    assert fact_service.calls[0].source.source_type == "customer_activity"
    assert fact_service.calls[0].source.source_object_id == "1"


def test_profile_workflow_uses_dedicated_checkpoint_identity_and_metadata():
    assert build_customer_profile_thread_id(team_id=7, customer_id=101, run_id=88) == "customer-profile:7:101:run:88"
    config = build_customer_profile_graph_config(
        team_id=7,
        user_id=9,
        session_id=10,
        customer_id=101,
        run_id=88,
    )
    assert config["configurable"]["thread_id"] == "customer-profile:7:101:run:88"
    assert config["metadata"]["workflow"] == "customer_profile_projection"
    assert config["metadata"]["checkpoint_namespace"] == "crm_agent_customer_profile_projection"
    assert config["metadata"]["workflow_state_version"] == "v1"


def test_profile_workflow_wrapper_keeps_graph_as_private_execution_detail():
    from app.services.agent.customer_profile_projection_workflow import CustomerProfileProjectionWorkflow

    graph = object()
    workflow = CustomerProfileProjectionWorkflow(graph_service=graph)

    assert workflow.graph_service is graph


@pytest.mark.asyncio
async def test_profile_workflow_uses_authoritative_warning_publication_result():
    quality_report = CustomerProfileQualityReport(
        issues=[
            {
                "code": "PROFILE_NARRATIVE_SALES_GUIDANCE_SUSPECTED",
                "path": "sections.current_situation.summary",
                "message": "该段叙事可能包含面向销售的指导表达",
            }
        ]
    )
    projection_service = FakeProjectionService(
        publication_status="PUBLISHED_WITH_WARNINGS",
        quality_report=quality_report,
    )
    service = CustomerProfileProjectionGraphService(
        context_service=FakeContextService(),
        memory_store_service=FakeMemoryService(),
        fact_extraction_service=FakeFactExtractor(),
        fact_service=FakeFactService(),
        projection_service=projection_service,
        checkpointer=InMemorySaver(),
        session_factory=FakeDB,
    )

    chunks = [
        chunk
        async for chunk in service.stream_events(
            {
                "team_id": 7,
                "user_id": 9,
                "session_id": 10,
                "run_id": 42,
                "event": _event(),
            }
        )
    ]
    result = next(chunk["result"] for chunk in chunks if chunk.get("kind") == "result")

    publication_result = result["profile_projection_result"]
    assert publication_result["publication_status"] == "PUBLISHED_WITH_WARNINGS"
    assert publication_result["quality_report"]["issues"][0]["code"] == (
        "PROFILE_NARRATIVE_SALES_GUIDANCE_SUSPECTED"
    )


@pytest.mark.asyncio
async def test_profile_workflow_rejects_cross_team_event():
    service = CustomerProfileProjectionGraphService(
        context_service=FakeContextService(),
        memory_store_service=FakeMemoryService(),
        fact_extraction_service=FakeFactExtractor(),
        fact_service=FakeFactService(),
        projection_service=FakeProjectionService(),
        checkpointer=InMemorySaver(),
        session_factory=FakeDB,
    )

    with pytest.raises(ValueError, match="team_id does not match event"):
        [
            chunk
            async for chunk in service.stream_events(
                {
                    "team_id": 8,
                    "user_id": 9,
                    "session_id": 10,
                    "run_id": 88,
                    "event": _event(),
                }
            )
        ]


@pytest.mark.asyncio
async def test_profile_workflow_rejects_fact_with_unknown_evidence():
    fact_service = FakeFactService()
    extractor = FakeFactExtractor()
    original_extract = extractor.extract

    async def extract_with_unknown_evidence(db, **kwargs):
        result = await original_extract(db, **kwargs)
        result.facts[0].evidence_keys = ["activity:missing"]
        return result

    extractor.extract = extract_with_unknown_evidence
    service = CustomerProfileProjectionGraphService(
        context_service=FakeContextService(),
        memory_store_service=FakeMemoryService(),
        fact_extraction_service=extractor,
        fact_service=fact_service,
        projection_service=FakeProjectionService(),
        checkpointer=InMemorySaver(),
        session_factory=FakeDB,
    )

    chunks = [
        chunk
        async for chunk in service.stream_events(
            {"team_id": 7, "user_id": 9, "session_id": 10, "run_id": 89, "event": _event()}
        )
    ]
    result = next(chunk["result"] for chunk in chunks if chunk.get("kind") == "result")

    assert fact_service.calls == []
    assert result["errors"][0]["event"] == "customer_profile_fact_evidence_rejected"


@pytest.mark.asyncio
async def test_profile_workflow_applies_deterministic_fact_gate_before_persisting():
    fact_service = FakeFactService(
        assessment=CustomerFactCandidateAssessment(
            action="ignore",
            reason="low_confidence_ignored",
        )
    )
    service = CustomerProfileProjectionGraphService(
        context_service=FakeContextService(),
        memory_store_service=FakeMemoryService(),
        fact_extraction_service=FakeFactExtractor(),
        fact_service=fact_service,
        projection_service=FakeProjectionService(),
        checkpointer=InMemorySaver(),
        session_factory=FakeDB,
    )

    chunks = [
        chunk
        async for chunk in service.stream_events(
            {"team_id": 7, "user_id": 9, "session_id": 10, "run_id": 90, "event": _event()}
        )
    ]
    result = next(chunk["result"] for chunk in chunks if chunk.get("kind") == "result")

    assert fact_service.calls == []
    assert any(
        error["event"] == "customer_profile_fact_candidate_ignored"
        and error["reason"] == "low_confidence_ignored"
        for error in result["errors"]
    )


@pytest.mark.asyncio
async def test_profile_workflow_deduplicates_fact_candidates_before_persisting():
    class DuplicateFactExtractor(FakeFactExtractor):
        async def extract(self, db, **kwargs):
            result = await super().extract(db, **kwargs)
            result.facts.append(
                ExtractedCustomerFact(
                    fact_type="need",
                    subject="  CRM   项目 ",
                    content="客户需要完成 POC 后再评估采购。",
                    confidence=0.95,
                    evidence_quote="完成 POC 后再评估采购",
                    evidence_keys=["activity:1"],
                )
            )
            return result

    fact_service = FakeFactService()
    service = CustomerProfileProjectionGraphService(
        context_service=FakeContextService(),
        memory_store_service=FakeMemoryService(),
        fact_extraction_service=DuplicateFactExtractor(),
        fact_service=fact_service,
        projection_service=FakeProjectionService(),
        checkpointer=InMemorySaver(),
        session_factory=FakeDB,
    )

    chunks = [
        chunk
        async for chunk in service.stream_events(
            {"team_id": 7, "user_id": 9, "session_id": 10, "run_id": 91, "event": _event()}
        )
    ]
    result = next(chunk["result"] for chunk in chunks if chunk.get("kind") == "result")

    assert len(fact_service.calls) == 1
    assert any(
        error["event"] == "customer_profile_fact_candidate_ignored"
        and error["reason"] == "duplicate_candidate"
        for error in result["errors"]
    )


@pytest.mark.asyncio
async def test_profile_workflow_validates_request_before_running_graph():
    service = CustomerProfileProjectionGraphService(
        context_service=FakeContextService(),
        memory_store_service=FakeMemoryService(),
        fact_extraction_service=FakeFactExtractor(),
        fact_service=FakeFactService(),
        projection_service=FakeProjectionService(),
        checkpointer=InMemorySaver(),
        session_factory=FakeDB,
    )

    with pytest.raises(ValueError, match="invalid customer profile projection input"):
        [
            chunk
            async for chunk in service.stream_events(
                {"team_id": 7, "event": _event(), "unexpected": True}  # type: ignore[typeddict-item]
            )
        ]

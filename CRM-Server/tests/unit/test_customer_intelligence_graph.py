from datetime import datetime
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.services.agent.customer_intelligence_graph import (
    CustomerIntelligenceGraphService,
    build_customer_intelligence_graph_config,
    build_customer_intelligence_thread_id,
)
from app.services.agent.schemas import CustomerContextAnswerResult
from app.services.customer_context_answer_service import CustomerContextAnswerEnvelope
from app.services.customer_fact_extraction_service import CustomerFactExtractionResult, ExtractedCustomerFact
from app.services.customer_intelligence_event_service import (
    CustomerIntelligenceEvent,
    CustomerIntelligenceSource,
    customer_intelligence_event_service,
)


class FakePersistedFact:
    def __init__(self, fact_id, version=1):
        self.id = fact_id
        self.version = version


class FakeCustomerContext:
    def to_agent_payload(self):
        return {
            "strong_context": {
                "customer": {"id": 101, "account_name": "越秀金融"},
                "customer_facts": [{
                    "id": 501,
                    "fact_type": "need",
                    "subject": "试用",
                    "content": "客户已经进入 POC。",
                    "confidence": 0.91,
                }],
                "contacts": [],
                "opportunities": [{"id": 301, "name": "CRM 项目", "stage": "POC"}],
                "contracts": [],
                "payment_plans": [],
                "payment_records": [],
                "recent_activities": [],
                "same_industry_customers": [],
            },
            "semantic_evidence": [{
                "evidence_id": "ev-1",
                "score": 0.91,
                "source_type": "follow_up",
                "title": "电话跟进",
                "text": "张总说本周开始 POC。",
            }],
            "retrieval": {"status": "ok", "enabled": True, "error_message": None},
            "usage_policy": {
                "strong_facts_source": "mysql",
                "semantic_evidence_source": "qdrant",
                "rule": "强业务事实以 strong_context 为准。",
            },
        }


class FakeCustomerContextService:
    def __init__(self):
        self.calls = []

    def build_context(self, db, *, team_id, customer_id, query_text=None, evidence_limit=8, source_types=None):
        self.calls.append({
            "db": db,
            "team_id": team_id,
            "customer_id": customer_id,
            "query_text": query_text,
            "evidence_limit": evidence_limit,
            "source_types": source_types,
        })
        return FakeCustomerContext()


class FakeCustomerMemoryStoreService:
    def __init__(self):
        self.reads = []
        self.summary_writes = []
        self.retrieval_writes = []
        self.fact_writes = []

    def build_context_payload(self, db, *, tenant_id, customer_id, limit=20):
        self.reads.append({
            "db": db,
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "limit": limit,
        })
        return {
            "namespace_prefix": [str(tenant_id), "customer", str(customer_id)],
            "facts": [],
            "summaries": [{"key": "latest", "value": {"summary": "客户正在 POC"}, "updated_at": "2026-08-02T12:00:00"}],
            "preferences": [],
            "retrieval": [],
        }

    def upsert_summary(self, db, *, tenant_id, customer_id, key, value):
        self.summary_writes.append({
            "db": db,
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "key": key,
            "value": value,
        })

    def upsert_retrieval_index(self, db, *, tenant_id, customer_id, key, value):
        self.retrieval_writes.append({
            "db": db,
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "key": key,
            "value": value,
        })

    def upsert_fact_index(self, db, *, tenant_id, customer_id, key, value):
        self.fact_writes.append({
            "db": db,
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "key": key,
            "value": value,
        })


class FakeDB:
    def __init__(self):
        self.flush_count = 0

    def flush(self):
        self.flush_count += 1


class FakeCustomerFactExtractionService:
    def __init__(self, facts=None):
        self.calls = []
        self.facts = facts or []

    async def extract(self, db, *, team_id, event, customer_context, customer_memory=None, current_date=None):
        self.calls.append({
            "db": db,
            "team_id": team_id,
            "event": event,
            "customer_context": customer_context,
            "customer_memory": customer_memory,
            "current_date": current_date,
        })
        return CustomerFactExtractionResult(summary="提炼客户最新动态", facts=self.facts)


class FakeCustomerFactService:
    def __init__(self):
        self.calls = []
        self.review_audits = []

    def assess_candidate_against_context(self, *, candidate, existing_facts):
        from app.services.customer_fact_service import customer_fact_service

        return customer_fact_service.assess_candidate_against_context(
            candidate=candidate,
            existing_facts=existing_facts,
        )

    def upsert_fact(self, db, fact_input):
        self.calls.append({"db": db, "fact_input": fact_input})
        return FakePersistedFact(901, version=len(self.calls) + 1)

    def record_review_decision(self, db, audit_input):
        self.review_audits.append({"db": db, "audit_input": audit_input})


class FakeCustomerProfileRefreshService:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or {"success": True, "customer_id": 101}

    async def generate_profile(
        self,
        customer_id,
        account_name,
        source_lead_id=None,
        team_id=None,
    ):
        self.calls.append({
            "customer_id": customer_id,
            "account_name": account_name,
            "source_lead_id": source_lead_id,
            "team_id": team_id,
        })
        return self.result


class FakeCustomerBriefRefreshService:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or {"success": True, "customer_id": 101}

    async def generate_brief(self, customer_id, team_id):
        self.calls.append({
            "customer_id": customer_id,
            "team_id": team_id,
        })
        return self.result


class FakeCustomerContextAnswerService:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or CustomerContextAnswerEnvelope(
            result=CustomerContextAnswerResult(
                answer="越秀金融当前正在推进 CRM 项目，已进入 POC。",
                confidence=0.91,
                used_sections=["customer", "opportunities", "evidence"],
                missing_context=[],
                answer_mode="grounded",
                citations=[{"evidence_id": "ev-1", "score": 0.91}],
            ),
            answer_source="fake_answer_service",
            model="fake-model",
        )

    async def answer_with_metadata(self, db, *, team_id, question, customer_context, customer_memory):
        self.calls.append({
            "db": db,
            "team_id": team_id,
            "question": question,
            "customer_context": customer_context,
            "customer_memory": customer_memory,
        })
        return self.result


@pytest.mark.asyncio
async def test_customer_intelligence_graph_loads_context_plans_refresh_and_checkpoints():
    context_service = FakeCustomerContextService()
    memory_store_service = FakeCustomerMemoryStoreService()
    fact_extraction_service = FakeCustomerFactExtractionService(facts=[
        ExtractedCustomerFact(
            fact_type="stage",
            subject="POC",
            content="客户已经进入 POC，需准备试用环境。",
            confidence=0.88,
            action="upsert",
            evidence_quote="张总说本周开始 POC",
            reason="跟进记录明确表达客户进入 POC",
        )
    ])
    fact_service = FakeCustomerFactService()
    profile_refresh_service = FakeCustomerProfileRefreshService()
    brief_refresh_service = FakeCustomerBriefRefreshService()
    db = FakeDB()
    service = CustomerIntelligenceGraphService(
        context_service=context_service,
        memory_store_service=memory_store_service,
        fact_extraction_service=fact_extraction_service,
        fact_service=fact_service,
        profile_refresh_service=profile_refresh_service,
        brief_refresh_service=brief_refresh_service,
        checkpointer=InMemorySaver(),
    )
    event = customer_intelligence_event_service.manual_refresh_requested(
        team_id=2,
        customer_id=101,
        actor_id="9",
        request_id="refresh-1",
        refresh_scope="full",
        occurred_at=datetime(2026, 8, 2, 13, 0, 0),
    )

    result = await service.run({
        "db": db,
        "team_id": 2,
        "user_id": 9,
        "session_id": 77,
        "event": event,
    })
    snapshot = await service._graph.aget_state(build_customer_intelligence_graph_config(
        team_id=2,
        user_id=9,
        session_id=77,
        event_key=event.event_key,
    ))

    assert build_customer_intelligence_thread_id(
        team_id=2,
        user_id=9,
        session_id=77,
        event_key=event.event_key,
    ) == f"crm_agent_customer_intelligence:2:9:77:{event.event_key}"
    assert context_service.calls[0]["customer_id"] == 101
    assert context_service.calls[0]["team_id"] == 2
    assert memory_store_service.reads[0]["customer_id"] == 101
    assert memory_store_service.summary_writes[0]["key"] == "latest_customer_intelligence_event"
    assert memory_store_service.retrieval_writes[0]["key"] == "latest_evidence_refs"
    assert memory_store_service.fact_writes[0]["value"]["fact_refs"][0]["fact_id"] == 501
    assert memory_store_service.fact_writes[0]["value"]["fact_refs"][1]["fact_id"] == 901
    assert fact_extraction_service.calls[0]["team_id"] == 2
    assert fact_service.calls[0]["fact_input"].source.quote == "张总说本周开始 POC"
    assert profile_refresh_service.calls == [{
        "customer_id": 101,
        "account_name": "越秀金融",
        "source_lead_id": None,
        "team_id": 2,
    }]
    assert brief_refresh_service.calls == [{"customer_id": 101, "team_id": 2}]
    assert db.flush_count == 1
    assert result["route"] == "refresh_profile"
    assert result["refresh_plan"]["target_sections"] == ["base_profile", "dynamic_brief", "memory"]
    assert result["customer_context"]["strong_context"]["customer"]["account_name"] == "越秀金融"
    assert [step["title"] for step in result["visible_trace"]] == [
        "理解触发来源",
        "读取客户上下文",
        "读取客户记忆",
        "制定更新计划",
        "提炼客户事实",
        "沉淀客户事实",
        "刷新客户档案",
        "刷新客户概况",
        "更新客户记忆",
    ]
    assert snapshot.values["refresh_plan"]["route"] == "refresh_profile"


@pytest.mark.asyncio
async def test_customer_intelligence_graph_streams_visible_trace_before_final_result():
    service = CustomerIntelligenceGraphService(
        context_service=FakeCustomerContextService(),
        memory_store_service=FakeCustomerMemoryStoreService(),
        fact_extraction_service=FakeCustomerFactExtractionService(facts=[
            ExtractedCustomerFact(
                fact_type="stage",
                subject="POC",
                content="客户已经进入 POC，需准备试用环境。",
                confidence=0.88,
                action="upsert",
                evidence_quote="张总说本周开始 POC",
                reason="跟进记录明确表达客户进入 POC",
            )
        ]),
        fact_service=FakeCustomerFactService(),
        profile_refresh_service=FakeCustomerProfileRefreshService(),
        brief_refresh_service=FakeCustomerBriefRefreshService(),
        checkpointer=InMemorySaver(),
    )
    event = customer_intelligence_event_service.manual_refresh_requested(
        team_id=2,
        customer_id=101,
        actor_id="9",
        request_id="refresh-stream-1",
        refresh_scope="full",
        occurred_at=datetime(2026, 8, 2, 13, 0, 0),
    )

    chunks = [
        chunk async for chunk in service.stream_run({
            "db": FakeDB(),
            "team_id": 2,
            "user_id": 9,
            "session_id": 77,
            "event": event,
        })
    ]

    assert chunks[0]["kind"] == "event"
    assert chunks[0]["event"]["event"] == "agent_step"
    assert chunks[0]["event"]["step"] == "customer_intelligence"
    assert "理解触发来源" in chunks[0]["event"]["content"]
    assert chunks[-1]["kind"] == "result"
    assert chunks[-1]["result"]["route"] == "refresh_profile"
    assert [step["title"] for step in chunks[-1]["result"]["visible_trace"]] == [
        "理解触发来源",
        "读取客户上下文",
        "读取客户记忆",
        "制定更新计划",
        "提炼客户事实",
        "沉淀客户事实",
        "刷新客户档案",
        "刷新客户概况",
        "更新客户记忆",
    ]


@pytest.mark.asyncio
async def test_customer_intelligence_graph_stream_result_preserves_answer_from_updates_when_snapshot_lags():
    class SnapshotLagGraph:
        async def astream(self, checkpoint_state, config, *, context=None, stream_mode=None):
            yield {
                "answer_context": {
                    "route": "answer_context",
                    "customer_context_answer": {
                        "answer": "中国科学院信息工程研究所目前已有客户档案和业务上下文。",
                        "confidence": 0.93,
                    },
                    "assistant_content": "中国科学院信息工程研究所目前已有客户档案和业务上下文。",
                    "visible_trace": [{
                        "title": "生成客户回答",
                        "content": "已基于客户档案、业务上下文和检索证据整理回答，置信度 93%",
                    }],
                    "events": [{
                        "event": "customer_context_answer_generated",
                        "confidence": 0.93,
                    }],
                }
            }

        async def aget_state(self, config):
            return SimpleNamespace(
                values={
                    "route": "answer_context",
                    "visible_trace": [{
                        "title": "生成客户回答",
                        "content": "已基于客户档案、业务上下文和检索证据整理回答，置信度 93%",
                    }],
                    "events": [],
                },
                interrupts=(),
            )

    service = CustomerIntelligenceGraphService(checkpointer=InMemorySaver())
    service._graph = SnapshotLagGraph()
    event = customer_intelligence_event_service.agent_customer_question(
        team_id=2,
        customer_id=101,
        actor_id="9",
        session_id=77,
        message_id=88,
        question="中科院现在是什么情况",
    )

    chunks = [
        chunk async for chunk in service.stream_run({
            "team_id": 2,
            "user_id": 9,
            "session_id": 77,
            "event": event,
        })
    ]

    assert chunks[-1]["kind"] == "result"
    assert chunks[-1]["result"]["assistant_content"] == "中国科学院信息工程研究所目前已有客户档案和业务上下文。"
    assert chunks[-1]["result"]["customer_context_answer"]["answer"] == (
        "中国科学院信息工程研究所目前已有客户档案和业务上下文。"
    )
    assert chunks[-1]["result"]["events"][0]["event"] == "customer_context_answer_generated"


@pytest.mark.asyncio
async def test_customer_intelligence_graph_refreshes_profile_for_customer_lifecycle_events():
    profile_refresh_service = FakeCustomerProfileRefreshService()
    brief_refresh_service = FakeCustomerBriefRefreshService()
    service = CustomerIntelligenceGraphService(
        context_service=FakeCustomerContextService(),
        memory_store_service=FakeCustomerMemoryStoreService(),
        fact_extraction_service=FakeCustomerFactExtractionService(),
        fact_service=FakeCustomerFactService(),
        profile_refresh_service=profile_refresh_service,
        brief_refresh_service=brief_refresh_service,
        checkpointer=InMemorySaver(),
    )
    event = customer_intelligence_event_service.customer_lifecycle_refresh_requested(
        team_id=2,
        customer_id=101,
        actor_id="9",
        request_id="customer-created-1",
        trigger_type="customer_created",
        occurred_at=datetime(2026, 8, 2, 13, 0, 0),
    )

    result = await service.run({
        "db": FakeDB(),
        "team_id": 2,
        "user_id": 9,
        "session_id": 77,
        "event": event,
    })

    assert result["route"] == "refresh_profile"
    assert result["refresh_plan"]["target_sections"] == ["base_profile", "dynamic_brief", "memory"]
    assert profile_refresh_service.calls == [{
        "customer_id": 101,
        "account_name": "越秀金融",
        "source_lead_id": None,
        "team_id": 2,
    }]
    assert brief_refresh_service.calls == [{"customer_id": 101, "team_id": 2}]


@pytest.mark.asyncio
async def test_customer_intelligence_graph_refreshes_brief_for_business_updates_without_profile_refresh():
    context_service = FakeCustomerContextService()
    profile_refresh_service = FakeCustomerProfileRefreshService()
    brief_refresh_service = FakeCustomerBriefRefreshService()
    service = CustomerIntelligenceGraphService(
        context_service=context_service,
        memory_store_service=FakeCustomerMemoryStoreService(),
        fact_extraction_service=FakeCustomerFactExtractionService(),
        fact_service=FakeCustomerFactService(),
        profile_refresh_service=profile_refresh_service,
        brief_refresh_service=brief_refresh_service,
        checkpointer=InMemorySaver(),
    )
    event = CustomerIntelligenceEvent(
        event_key="deal-event-7001",
        trigger_type="deal_journey_event_recorded",
        tenant_id=2,
        team_id=2,
        customer_id=101,
        occurred_at=datetime(2026, 8, 2, 13, 0, 0),
        source=CustomerIntelligenceSource(
            source_type="deal_journey_event",
            source_object_id="7001",
            business_object_type="opportunity",
            business_object_id="301",
        ),
        actor_id="9",
        summary="商机推进到 POC",
        payload={"event_type": "OPPORTUNITY_STAGE_CHANGED"},
    )

    result = await service.run({
        "db": FakeDB(),
        "team_id": 2,
        "user_id": 9,
        "session_id": 77,
        "event": event,
    })

    assert result["route"] == "refresh_brief"
    assert profile_refresh_service.calls == []
    assert brief_refresh_service.calls == [{"customer_id": 101, "team_id": 2}]
    assert "刷新客户概况" in [step["title"] for step in result["visible_trace"]]


@pytest.mark.asyncio
async def test_customer_intelligence_graph_refreshes_brief_for_contact_updates_without_profile_refresh():
    profile_refresh_service = FakeCustomerProfileRefreshService()
    brief_refresh_service = FakeCustomerBriefRefreshService()
    service = CustomerIntelligenceGraphService(
        context_service=FakeCustomerContextService(),
        memory_store_service=FakeCustomerMemoryStoreService(),
        fact_extraction_service=FakeCustomerFactExtractionService(),
        fact_service=FakeCustomerFactService(),
        profile_refresh_service=profile_refresh_service,
        brief_refresh_service=brief_refresh_service,
        checkpointer=InMemorySaver(),
    )
    event = CustomerIntelligenceEvent(
        event_key="contact-event-601",
        trigger_type="customer_contact_updated",
        tenant_id=2,
        team_id=2,
        customer_id=101,
        occurred_at=datetime(2026, 8, 2, 13, 0, 0),
        source=CustomerIntelligenceSource(
            source_type="customer_contact",
            source_object_id="601",
            business_object_type="contact",
            business_object_id="601",
        ),
        actor_id="9",
        summary="客户联系人已更新: 张总",
        payload={"name": "张总", "position": "总经理", "is_decision_maker": True},
    )

    result = await service.run({
        "db": FakeDB(),
        "team_id": 2,
        "user_id": 9,
        "session_id": 77,
        "event": event,
    })

    assert result["route"] == "refresh_brief"
    assert result["refresh_plan"]["target_sections"] == ["dynamic_brief", "memory"]
    assert profile_refresh_service.calls == []
    assert brief_refresh_service.calls == [{"customer_id": 101, "team_id": 2}]


@pytest.mark.asyncio
async def test_customer_intelligence_graph_refreshes_brief_for_generic_business_object_changes():
    profile_refresh_service = FakeCustomerProfileRefreshService()
    brief_refresh_service = FakeCustomerBriefRefreshService()
    service = CustomerIntelligenceGraphService(
        context_service=FakeCustomerContextService(),
        memory_store_service=FakeCustomerMemoryStoreService(),
        fact_extraction_service=FakeCustomerFactExtractionService(),
        fact_service=FakeCustomerFactService(),
        profile_refresh_service=profile_refresh_service,
        brief_refresh_service=brief_refresh_service,
        checkpointer=InMemorySaver(),
    )
    event = CustomerIntelligenceEvent(
        event_key="business-object-change-1",
        trigger_type="customer_business_object_deleted",
        tenant_id=2,
        team_id=2,
        customer_id=101,
        occurred_at=datetime(2026, 8, 2, 13, 0, 0),
        source=CustomerIntelligenceSource(
            source_type="contract",
            source_object_id="401",
            business_object_type="contract",
            business_object_id="401",
        ),
        actor_id="9",
        summary="合同已删除: 企业版采购合同",
        payload={"object_name": "企业版采购合同"},
    )

    result = await service.run({
        "db": FakeDB(),
        "team_id": 2,
        "user_id": 9,
        "session_id": 77,
        "event": event,
    })

    assert result["route"] == "refresh_brief"
    assert result["refresh_plan"]["target_sections"] == ["dynamic_brief", "memory"]
    assert profile_refresh_service.calls == []
    assert brief_refresh_service.calls == [{"customer_id": 101, "team_id": 2}]


@pytest.mark.asyncio
async def test_customer_intelligence_graph_routes_manual_brief_refresh_without_profile_refresh():
    profile_refresh_service = FakeCustomerProfileRefreshService()
    brief_refresh_service = FakeCustomerBriefRefreshService()
    service = CustomerIntelligenceGraphService(
        context_service=FakeCustomerContextService(),
        memory_store_service=FakeCustomerMemoryStoreService(),
        fact_extraction_service=FakeCustomerFactExtractionService(),
        fact_service=FakeCustomerFactService(),
        profile_refresh_service=profile_refresh_service,
        brief_refresh_service=brief_refresh_service,
        checkpointer=InMemorySaver(),
    )
    event = customer_intelligence_event_service.manual_refresh_requested(
        team_id=2,
        customer_id=101,
        actor_id="9",
        request_id="refresh-brief-1",
        refresh_scope="brief",
        occurred_at=datetime(2026, 8, 2, 13, 0, 0),
    )

    result = await service.run({
        "db": FakeDB(),
        "team_id": 2,
        "user_id": 9,
        "session_id": 77,
        "event": event,
    })

    assert result["route"] == "refresh_brief"
    assert result["refresh_plan"]["target_sections"] == ["dynamic_brief", "memory"]
    assert profile_refresh_service.calls == []
    assert brief_refresh_service.calls == [{"customer_id": 101, "team_id": 2}]


@pytest.mark.asyncio
async def test_customer_intelligence_graph_answers_agent_question_without_refreshing_profile():
    context_service = FakeCustomerContextService()
    fact_extraction_service = FakeCustomerFactExtractionService(facts=[
        ExtractedCustomerFact(fact_type="summary", content="不应提炼", confidence=0.9)
    ])
    answer_service = FakeCustomerContextAnswerService()
    service = CustomerIntelligenceGraphService(
        context_service=context_service,
        memory_store_service=FakeCustomerMemoryStoreService(),
        fact_extraction_service=fact_extraction_service,
        answer_service=answer_service,
        checkpointer=InMemorySaver(),
    )
    event = customer_intelligence_event_service.agent_customer_question(
        team_id=2,
        customer_id=101,
        actor_id="9",
        session_id=77,
        message_id=88,
        question="总结一下这个客户现在什么情况",
    )

    result = await service.run({
        "db": FakeDB(),
        "team_id": 2,
        "user_id": 9,
        "session_id": 77,
        "event": event,
    })

    assert result["route"] == "answer_context"
    assert result["refresh_plan"]["requires_llm_extraction"] is False
    assert result["refresh_plan"]["target_sections"] == ["customer_context"]
    assert context_service.calls[0]["query_text"] == "总结一下这个客户现在什么情况"
    assert answer_service.calls[0]["question"] == "总结一下这个客户现在什么情况"
    assert answer_service.calls[0]["customer_context"]["strong_context"]["customer"]["account_name"] == "越秀金融"
    assert result["customer_context_answer"]["answer"] == "越秀金融当前正在推进 CRM 项目，已进入 POC。"
    assert result["assistant_content"] == "越秀金融当前正在推进 CRM 项目，已进入 POC。"
    assert result["events"][-2]["event"] == "customer_context_answer_generated"
    assert result["events"][-2]["answer_mode"] == "grounded"
    assert result["events"][-2]["citations_count"] == 1
    assert result["events"][-2]["retrieval_status"] == "ok"
    assert result["events"][-2]["semantic_evidence_count"] == 1
    assert result["customer_context_answer"]["citations"][0]["evidence_id"] == "ev-1"
    assert fact_extraction_service.calls == []
    assert "生成客户回答" in [step["title"] for step in result["visible_trace"]]


@pytest.mark.asyncio
async def test_customer_intelligence_graph_interrupts_for_reviewable_facts_and_resumes_to_persist():
    context_service = FakeCustomerContextService()
    memory_store_service = FakeCustomerMemoryStoreService()
    fact_extraction_service = FakeCustomerFactExtractionService(facts=[
        ExtractedCustomerFact(
            fact_type="risk",
            subject="审批",
            content="客户内部审批链可能较长。",
            confidence=0.62,
            action="review",
            evidence_quote="张总提到需要再走内部流程",
            reason="有风险信号，但表达不够确定",
        )
    ])
    fact_service = FakeCustomerFactService()
    db = FakeDB()
    service = CustomerIntelligenceGraphService(
        context_service=context_service,
        memory_store_service=memory_store_service,
        fact_extraction_service=fact_extraction_service,
        fact_service=fact_service,
        profile_refresh_service=FakeCustomerProfileRefreshService(),
        brief_refresh_service=FakeCustomerBriefRefreshService(),
        checkpointer=InMemorySaver(),
    )
    event = customer_intelligence_event_service.manual_refresh_requested(
        team_id=2,
        customer_id=101,
        actor_id="9",
        request_id="refresh-review-1",
        refresh_scope="full",
        occurred_at=datetime(2026, 8, 2, 13, 0, 0),
    )

    interrupted = await service.run({
        "db": db,
        "team_id": 2,
        "user_id": 9,
        "session_id": 77,
        "event": event,
    })

    interrupt_payload = interrupted["__interrupt__"][0].value
    assert interrupt_payload["type"] == "confirm"
    assert interrupt_payload["business_action"] == "review_customer_facts"
    assert interrupt_payload["interaction"]["title"] == "确认是否沉淀客户事实"
    assert "审批" in interrupt_payload["interaction"]["prompt"]
    assert fact_service.calls == []
    assert memory_store_service.summary_writes == []

    resumed = await service.resume_review({
        "db": db,
        "team_id": 2,
        "user_id": 9,
        "session_id": 77,
        "event_key": event.event_key,
        "resume_payload": {"action": "approve", "source": "web"},
    })

    assert fact_service.calls[0]["fact_input"].fact_type == "risk"
    assert fact_service.calls[0]["fact_input"].source.quote == "张总提到需要再走内部流程"
    assert fact_service.review_audits[0]["audit_input"].decision == "APPROVED"
    assert fact_service.review_audits[0]["audit_input"].fact_id == 901
    assert memory_store_service.fact_writes[0]["value"]["fact_refs"][1]["fact_id"] == 901
    assert resumed["customer_fact_review"]["status"] == "resolved"
    assert [step["title"] for step in resumed["visible_trace"]] == [
        "理解触发来源",
        "读取客户上下文",
        "读取客户记忆",
        "制定更新计划",
        "提炼客户事实",
        "复核客户事实",
        "复核客户事实",
        "沉淀客户事实",
        "刷新客户档案",
        "刷新客户概况",
        "更新客户记忆",
    ]


@pytest.mark.asyncio
async def test_customer_intelligence_graph_routes_conflicting_upsert_candidate_to_review():
    context_service = FakeCustomerContextService()
    fact_extraction_service = FakeCustomerFactExtractionService(facts=[
        ExtractedCustomerFact(
            fact_type="need",
            subject="试用",
            content="客户已经完成 POC，准备进入合同审批。",
            confidence=0.76,
            action="upsert",
            evidence_quote="POC 已完成",
            reason="跟进记录提到 POC 已完成",
        )
    ])
    fact_service = FakeCustomerFactService()
    service = CustomerIntelligenceGraphService(
        context_service=context_service,
        memory_store_service=FakeCustomerMemoryStoreService(),
        fact_extraction_service=fact_extraction_service,
        fact_service=fact_service,
        profile_refresh_service=FakeCustomerProfileRefreshService(),
        brief_refresh_service=FakeCustomerBriefRefreshService(),
        checkpointer=InMemorySaver(),
    )
    event = customer_intelligence_event_service.manual_refresh_requested(
        team_id=2,
        customer_id=101,
        actor_id="9",
        request_id="refresh-conflict-1",
        refresh_scope="full",
        occurred_at=datetime(2026, 8, 2, 13, 0, 0),
    )

    interrupted = await service.run({
        "db": FakeDB(),
        "team_id": 2,
        "user_id": 9,
        "session_id": 77,
        "event": event,
    })

    interrupt_payload = interrupted["__interrupt__"][0].value
    candidate = interrupt_payload["draft_payload"]["candidates"][0]
    assert interrupt_payload["business_action"] == "review_customer_facts"
    assert candidate["existing_content"] == "客户已经进入 POC。"
    assert candidate["conflict_reason"] == "候选事实与客户智能档案中的既有事实内容不同"
    assert fact_service.calls == []


@pytest.mark.asyncio
async def test_customer_intelligence_graph_records_rejected_fact_review_without_persisting():
    fact_extraction_service = FakeCustomerFactExtractionService(facts=[
        ExtractedCustomerFact(
            fact_type="risk",
            subject="审批",
            content="客户内部审批链可能较长。",
            confidence=0.62,
            action="review",
            evidence_quote="张总提到需要再走内部流程",
            reason="有风险信号，但表达不够确定",
        )
    ])
    fact_service = FakeCustomerFactService()
    service = CustomerIntelligenceGraphService(
        context_service=FakeCustomerContextService(),
        memory_store_service=FakeCustomerMemoryStoreService(),
        fact_extraction_service=fact_extraction_service,
        fact_service=fact_service,
        profile_refresh_service=FakeCustomerProfileRefreshService(),
        brief_refresh_service=FakeCustomerBriefRefreshService(),
        checkpointer=InMemorySaver(),
    )
    event = customer_intelligence_event_service.manual_refresh_requested(
        team_id=2,
        customer_id=101,
        actor_id="9",
        request_id="refresh-reject-1",
        refresh_scope="full",
        occurred_at=datetime(2026, 8, 2, 13, 0, 0),
    )
    await service.run({
        "db": FakeDB(),
        "team_id": 2,
        "user_id": 9,
        "session_id": 77,
        "event": event,
    })

    await service.resume_review({
        "db": FakeDB(),
        "team_id": 2,
        "user_id": 9,
        "session_id": 77,
        "event_key": event.event_key,
        "resume_payload": {"action": "reject", "source": "web"},
    })

    assert fact_service.calls == []
    assert fact_service.review_audits[0]["audit_input"].decision == "REJECTED"
    assert fact_service.review_audits[0]["audit_input"].fact_id is None


@pytest.mark.asyncio
async def test_customer_intelligence_graph_records_error_when_db_missing():
    def unavailable_session():
        raise RuntimeError("db unavailable")

    service = CustomerIntelligenceGraphService(
        context_service=FakeCustomerContextService(),
        memory_store_service=FakeCustomerMemoryStoreService(),
        checkpointer=InMemorySaver(),
        session_factory=unavailable_session,
    )
    event = customer_intelligence_event_service.manual_refresh_requested(
        team_id=2,
        customer_id=101,
        actor_id="9",
        request_id="refresh-1",
        refresh_scope="full",
    )

    result = await service.run({
        "team_id": 2,
        "user_id": 9,
        "session_id": 77,
        "event": event,
    })

    assert result["errors"][0]["event"] == "customer_intelligence_context_failed"
    assert result["refresh_plan"]["route"] == "refresh_profile"
    assert result["visible_trace"][1]["content"] == "未能读取客户上下文"

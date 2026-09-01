from datetime import datetime
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph
from sqlalchemy import Column, DateTime, Integer, LargeBinary, MetaData, String, Table, create_engine, text
from sqlalchemy.pool import StaticPool

from app.services.agent.customer_intelligence_graph import (
    CustomerIntelligenceGraphService,
    build_customer_intelligence_graph_config,
    build_customer_intelligence_thread_id,
)
from app.services.agent.schemas import CustomerContextAnswerResult
from app.services.customer_activity_ai.checkpointer import SQLAlchemyCheckpointSaver
from app.services.customer_context_answer_service import CustomerContextAnswerEnvelope
from app.services.customer_fact_extraction_service import CustomerFactExtractionResult, ExtractedCustomerFact
from app.services.customer_intelligence_event_service import (
    CustomerIntelligenceEvent,
    CustomerIntelligenceSource,
    customer_intelligence_event_service,
)


def _sql_checkpoint_saver() -> SQLAlchemyCheckpointSaver:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata = MetaData()
    Table(
        "crm_langgraph_checkpoints",
        metadata,
        Column("thread_id", String(191), primary_key=True),
        Column("checkpoint_ns", String(191), primary_key=True, default=""),
        Column("checkpoint_id", String(191), primary_key=True),
        Column("parent_checkpoint_id", String(191)),
        Column("checkpoint_type", String(100), nullable=False),
        Column("checkpoint_blob", LargeBinary, nullable=False),
        Column("metadata_type", String(100), nullable=False),
        Column("metadata_blob", LargeBinary, nullable=False),
        Column("created_time", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    Table(
        "crm_langgraph_checkpoint_blobs",
        metadata,
        Column("thread_id", String(191), primary_key=True),
        Column("checkpoint_ns", String(191), primary_key=True),
        Column("channel", String(191), primary_key=True),
        Column("version", String(191), primary_key=True),
        Column("serde_type", String(100), nullable=False),
        Column("blob", LargeBinary, nullable=False),
        Column("created_time", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    Table(
        "crm_langgraph_checkpoint_writes",
        metadata,
        Column("thread_id", String(191), primary_key=True),
        Column("checkpoint_ns", String(191), primary_key=True),
        Column("checkpoint_id", String(191), primary_key=True),
        Column("task_id", String(191), primary_key=True),
        Column("write_idx", Integer, primary_key=True),
        Column("task_path", String(255), nullable=False, default=""),
        Column("channel", String(191), nullable=False),
        Column("serde_type", String(100), nullable=False),
        Column("blob", LargeBinary, nullable=False),
        Column("created_time", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    metadata.create_all(engine)
    return SQLAlchemyCheckpointSaver(engine)


class FakePersistedFact:
    def __init__(self, fact_id, version=1):
        self.id = fact_id
        self.version = version


class FakeCustomerContext:
    def to_agent_payload(self):
        return {
            "strong_context": {
                "customer": {"id": 101, "account_name": "越秀金融"},
                "customer_facts": [
                    {
                        "id": 501,
                        "fact_type": "need",
                        "subject": "试用",
                        "content": "客户已经进入 POC。",
                        "confidence": 0.91,
                    }
                ],
                "contacts": [],
                "opportunities": [{"id": 301, "name": "CRM 项目", "stage": "POC"}],
                "contracts": [],
                "payment_plans": [],
                "payment_records": [],
                "recent_activities": [],
                "same_industry_customers": [],
            },
            "semantic_evidence": [
                {
                    "evidence_id": "ev-1",
                    "score": 0.91,
                    "source_type": "follow_up",
                    "title": "电话跟进",
                    "text": "张总说本周开始 POC。",
                }
            ],
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
        self.calls.append(
            {
                "team_id": team_id,
                "customer_id": customer_id,
                "query_text": query_text,
                "evidence_limit": evidence_limit,
                "source_types": source_types,
            }
        )
        return FakeCustomerContext()


class FakeCustomerMemoryStoreService:
    def __init__(self):
        self.reads = []
        self.summary_writes = []
        self.retrieval_writes = []
        self.fact_writes = []

    def build_context_payload(self, db, *, tenant_id, customer_id, limit=20):
        self.reads.append(
            {
                "tenant_id": tenant_id,
                "customer_id": customer_id,
                "limit": limit,
            }
        )
        return {
            "namespace_prefix": [str(tenant_id), "customer", str(customer_id)],
            "facts": [],
            "summaries": [{"key": "latest", "value": {"summary": "客户正在 POC"}, "updated_at": "2026-08-02T12:00:00"}],
            "preferences": [],
            "retrieval": [],
        }

    def upsert_summary(self, db, *, tenant_id, customer_id, key, value):
        self.summary_writes.append(
            {
                "tenant_id": tenant_id,
                "customer_id": customer_id,
                "key": key,
                "value": value,
            }
        )

    def upsert_retrieval_index(self, db, *, tenant_id, customer_id, key, value):
        self.retrieval_writes.append(
            {
                "tenant_id": tenant_id,
                "customer_id": customer_id,
                "key": key,
                "value": value,
            }
        )

    def upsert_fact_index(self, db, *, tenant_id, customer_id, key, value):
        self.fact_writes.append(
            {
                "tenant_id": tenant_id,
                "customer_id": customer_id,
                "key": key,
                "value": value,
            }
        )


class FakeDB:
    def __init__(self):
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0
        self.closed = False

    def flush(self):
        self.flush_count += 1

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.close_count += 1
        self.closed = True


class FakeReviewWorkflow:
    def __init__(self, public_id: str = "rc_review_1"):
        self.public_id = public_id
        self.calls = []

    def create_case(self, db, **kwargs):
        self.calls.append({"db": db, **kwargs})
        return SimpleNamespace(public_id=self.public_id)


async def _invoke(service, input_state):
    result = {}
    async for chunk in service.stream_events(input_state):
        if chunk.get("kind") == "result":
            result = chunk.get("result") or {}
    return result


class FakeCustomerFactExtractionService:
    def __init__(self, facts=None):
        self.calls = []
        self.facts = facts or []

    async def extract(self, db, *, team_id, event, customer_context, customer_memory=None, current_date=None):
        self.calls.append(
            {
                "team_id": team_id,
                "event": event,
                "customer_context": customer_context,
                "customer_memory": customer_memory,
                "current_date": current_date,
            }
        )
        return CustomerFactExtractionResult(summary="提炼客户最新动态", facts=self.facts)


class FailingCustomerFactExtractionService:
    async def extract(self, db, **kwargs):
        raise RuntimeError("fact extraction unavailable")


class FakeCustomerFactService:
    def __init__(self):
        self.calls = []

    def assess_candidate_against_context(self, *, candidate, existing_facts):
        from app.services.customer_fact_service import customer_fact_service

        return customer_fact_service.assess_candidate_against_context(
            candidate=candidate,
            existing_facts=existing_facts,
        )

    def upsert_fact(self, db, fact_input):
        self.calls.append({"db": db, "fact_input": fact_input})
        return FakePersistedFact(901, version=len(self.calls) + 1)


class FailingCustomerFactService(FakeCustomerFactService):
    def upsert_fact(self, db, fact_input):
        raise RuntimeError("fact persistence unavailable")

def _business_event(*, event_key: str, occurred_at: datetime | None = None) -> CustomerIntelligenceEvent:
    return CustomerIntelligenceEvent(
        event_key=event_key,
        trigger_type="deal_journey_event_recorded",
        tenant_id=2,
        team_id=2,
        customer_id=101,
        occurred_at=occurred_at,
        source=CustomerIntelligenceSource(source_type="deal_journey_event", source_object_id=event_key),
        actor_id="9",
        summary="商机推进到 POC",
    )


class FakeCustomerContextAnswerService:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or CustomerContextAnswerEnvelope(
            result=CustomerContextAnswerResult(
                answer="越秀金融当前正在推进 CRM 项目，已进入 POC。",  # noqa: RUF001
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
        self.calls.append(
            {
                "team_id": team_id,
                "question": question,
                "customer_context": customer_context,
                "customer_memory": customer_memory,
            }
        )
        return self.result


@pytest.mark.asyncio
async def test_customer_intelligence_graph_rejects_profile_refresh_at_its_boundary():
    service = CustomerIntelligenceGraphService(
        checkpointer=InMemorySaver(),
        session_factory=FakeDB,
    )
    event = customer_intelligence_event_service.manual_refresh_requested(
        team_id=2,
        customer_id=101,
        actor_id="9",
        request_id="profile-hard-cut-1",
        refresh_scope="full",
        occurred_at=datetime(2026, 8, 23, 9, 0, 0),
    )

    with pytest.raises(ValueError, match="CustomerProfileProjectionWorkflow"):
        _ = [
            chunk
            async for chunk in service.stream_events(
                {
                    "team_id": 2,
                    "user_id": 9,
                    "session_id": 77,
                    "event": event,
                }
            )
        ]


@pytest.mark.asyncio
async def test_customer_intelligence_graph_loads_context_plans_refresh_and_checkpoints():
    context_service = FakeCustomerContextService()
    memory_store_service = FakeCustomerMemoryStoreService()
    fact_extraction_service = FakeCustomerFactExtractionService(
        facts=[
            ExtractedCustomerFact(
                fact_type="stage",
                subject="POC",
                content="客户已经进入 POC，需准备试用环境。",  # noqa: RUF001
                confidence=0.88,
                action="upsert",
                evidence_quote="张总说本周开始 POC",
                reason="跟进记录明确表达客户进入 POC",
            )
        ]
    )
    fact_service = FakeCustomerFactService()
    db = FakeDB()
    service = CustomerIntelligenceGraphService(
        context_service=context_service,
        memory_store_service=memory_store_service,
        fact_extraction_service=fact_extraction_service,
        fact_service=fact_service,
        checkpointer=InMemorySaver(),
        session_factory=lambda: db,
    )
    event = CustomerIntelligenceEvent(
        event_key="refresh-1",
        trigger_type="deal_journey_event_recorded",
        tenant_id=2,
        team_id=2,
        customer_id=101,
        occurred_at=datetime(2026, 8, 2, 13, 0, 0),
        source=CustomerIntelligenceSource(source_type="deal_journey_event", source_object_id="7001"),
        actor_id="9",
        summary="商机推进到 POC",
    )

    result = await _invoke(
        service,
        {
            "team_id": 2,
            "user_id": 9,
            "session_id": 77,
            "event": event,
        },
    )
    snapshot = await service._graph.aget_state(
        build_customer_intelligence_graph_config(
            team_id=2,
            user_id=9,
            session_id=77,
            event_key=event.event_key,
        )
    )

    assert (
        build_customer_intelligence_thread_id(
            team_id=2,
            event_key=event.event_key,
        )
        == f"crm_agent_customer_intelligence:2:{event.event_key}"
    )
    assert context_service.calls[0]["customer_id"] == 101
    assert context_service.calls[0]["team_id"] == 2
    assert memory_store_service.reads[0]["customer_id"] == 101
    assert memory_store_service.summary_writes[0]["key"] == "latest_customer_intelligence_event"
    assert memory_store_service.retrieval_writes[0]["key"] == "latest_evidence_refs"
    assert memory_store_service.fact_writes[0]["value"]["fact_refs"][0]["fact_id"] == 501
    assert memory_store_service.fact_writes[0]["value"]["fact_refs"][1]["fact_id"] == 901
    assert fact_extraction_service.calls[0]["team_id"] == 2
    assert fact_service.calls[0]["fact_input"].source.quote == "张总说本周开始 POC"
    assert db.flush_count == 1
    assert result["route"] == "write_memory"
    assert result["refresh_plan"]["target_sections"] == ["memory"]
    assert result["customer_context"]["strong_context"]["customer"]["account_name"] == "越秀金融"
    trace_titles = [step["title"] for step in result["visible_trace"]]
    assert trace_titles[0] == "理解触发来源"
    assert "读取客户上下文" in trace_titles
    assert "读取客户记忆" in trace_titles
    assert trace_titles.index("制定更新计划") > trace_titles.index("读取客户上下文")
    assert trace_titles.index("制定更新计划") > trace_titles.index("读取客户记忆")
    assert trace_titles[-3:] == [
        "制定更新计划",
        "沉淀客户事实",
        "更新客户记忆",
    ]
    assert snapshot.values["refresh_plan"]["route"] == "write_memory"


@pytest.mark.asyncio
async def test_customer_intelligence_graph_streams_visible_trace_before_final_result():
    service = CustomerIntelligenceGraphService(
        context_service=FakeCustomerContextService(),
        memory_store_service=FakeCustomerMemoryStoreService(),
        fact_extraction_service=FakeCustomerFactExtractionService(
            facts=[
                ExtractedCustomerFact(
                    fact_type="stage",
                    subject="POC",
                    content="客户已经进入 POC，需准备试用环境。",  # noqa: RUF001
                    confidence=0.88,
                    action="upsert",
                    evidence_quote="张总说本周开始 POC",
                    reason="跟进记录明确表达客户进入 POC",
                )
            ]
        ),
        fact_service=FakeCustomerFactService(),
        checkpointer=InMemorySaver(),
        session_factory=FakeDB,
    )
    event = _business_event(event_key="refresh-stream-1", occurred_at=datetime(2026, 8, 2, 13, 0, 0))

    chunks = [
        chunk
        async for chunk in service.stream_events(
            {
                "team_id": 2,
                "user_id": 9,
                "session_id": 77,
                "event": event,
            }
        )
    ]

    assert chunks[0]["kind"] == "event"
    assert chunks[0]["event"]["event"] == "agent_step"
    assert chunks[0]["event"]["step"] == "customer_intelligence"
    assert "理解触发来源" in chunks[0]["event"]["content"]
    assert chunks[-1]["kind"] == "result"
    assert chunks[-1]["result"]["route"] == "write_memory"
    trace_titles = [step["title"] for step in chunks[-1]["result"]["visible_trace"]]
    assert trace_titles[0] == "理解触发来源"
    assert "读取客户上下文" in trace_titles
    assert "读取客户记忆" in trace_titles
    assert trace_titles.index("制定更新计划") > trace_titles.index("读取客户上下文")
    assert trace_titles.index("制定更新计划") > trace_titles.index("读取客户记忆")
    assert trace_titles[-3:] == [
        "制定更新计划",
        "沉淀客户事实",
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
                    "visible_trace": [
                        {
                            "title": "生成客户回答",
                            "content": "已基于客户档案、业务上下文和检索证据整理回答，置信度 93%",  # noqa: RUF001
                        }
                    ],
                    "events": [
                        {
                            "event": "customer_context_answer_generated",
                            "confidence": 0.93,
                        }
                    ],
                }
            }

        async def aget_state(self, config):
            return SimpleNamespace(
                values={
                    "route": "answer_context",
                    "visible_trace": [
                        {
                            "title": "生成客户回答",
                            "content": "已基于客户档案、业务上下文和检索证据整理回答，置信度 93%",  # noqa: RUF001
                        }
                    ],
                    "events": [],
                },
                interrupts=(),
            )

    service = CustomerIntelligenceGraphService(checkpointer=InMemorySaver(), session_factory=FakeDB)
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
        chunk
        async for chunk in service.stream_events(
            {
                "team_id": 2,
                "user_id": 9,
                "session_id": 77,
                "event": event,
            }
        )
    ]

    assert chunks[-1]["kind"] == "result"
    assert chunks[-1]["result"]["assistant_content"] == "中国科学院信息工程研究所目前已有客户档案和业务上下文。"
    assert chunks[-1]["result"]["customer_context_answer"]["answer"] == (
        "中国科学院信息工程研究所目前已有客户档案和业务上下文。"
    )
    assert chunks[-1]["result"]["events"][0]["event"] == "customer_context_answer_generated"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_mode", ["read_error", "invalid_snapshot"])
async def test_customer_intelligence_graph_fails_closed_when_final_checkpoint_state_is_unavailable(
    failure_mode: str,
):
    class UnavailableCheckpointGraph:
        async def astream(self, checkpoint_state, config, *, context=None, stream_mode=None):
            yield {
                "emit_trace": {
                    "route": "refresh_profile",
                    "assistant_content": "不应作为成功结果返回",
                }
            }

        async def aget_state(self, config):
            if failure_mode == "read_error":
                raise RuntimeError("checkpoint read failed")
            return SimpleNamespace(values=None, interrupts=())

    service = CustomerIntelligenceGraphService(checkpointer=InMemorySaver(), session_factory=FakeDB)
    service._graph = UnavailableCheckpointGraph()
    event = _business_event(event_key="legacy-test-event", occurred_at=datetime(2026, 8, 23, 9, 0, 0))

    with pytest.raises(RuntimeError, match="checkpoint"):
        _ = [
            chunk
            async for chunk in service.stream_events(
                {
                    "team_id": 2,
                    "user_id": 9,
                    "session_id": 77,
                    "event": event,
                }
            )
        ]


@pytest.mark.asyncio
async def test_customer_intelligence_graph_answers_agent_question_without_refreshing_profile():
    context_service = FakeCustomerContextService()
    fact_extraction_service = FakeCustomerFactExtractionService(
        facts=[ExtractedCustomerFact(fact_type="summary", content="不应提炼", confidence=0.9)]
    )
    answer_service = FakeCustomerContextAnswerService()
    service = CustomerIntelligenceGraphService(
        context_service=context_service,
        memory_store_service=FakeCustomerMemoryStoreService(),
        fact_extraction_service=fact_extraction_service,
        answer_service=answer_service,
        checkpointer=InMemorySaver(),
        session_factory=FakeDB,
    )
    event = customer_intelligence_event_service.agent_customer_question(
        team_id=2,
        customer_id=101,
        actor_id="9",
        session_id=77,
        message_id=88,
        question="总结一下这个客户现在什么情况",
    )

    result = await _invoke(
        service,
        {
            "team_id": 2,
            "user_id": 9,
            "session_id": 77,
            "event": event,
        },
    )

    assert result["route"] == "answer_context"
    assert result["refresh_plan"]["requires_llm_extraction"] is False
    assert result["refresh_plan"]["target_sections"] == ["customer_context"]
    assert context_service.calls[0]["query_text"] == "总结一下这个客户现在什么情况"
    assert answer_service.calls[0]["question"] == "总结一下这个客户现在什么情况"
    assert answer_service.calls[0]["customer_context"]["strong_context"]["customer"]["account_name"] == "越秀金融"
    assert result["customer_context_answer"]["answer"] == "越秀金融当前正在推进 CRM 项目，已进入 POC。"  # noqa: RUF001
    assert result["assistant_content"] == "越秀金融当前正在推进 CRM 项目，已进入 POC。"  # noqa: RUF001
    assert result["events"][-2]["event"] == "customer_context_answer_generated"
    assert result["events"][-2]["answer_mode"] == "grounded"
    assert result["events"][-2]["citations_count"] == 1
    assert result["events"][-2]["retrieval_status"] == "ok"
    assert result["events"][-2]["semantic_evidence_count"] == 1
    assert result["customer_context_answer"]["citations"][0]["evidence_id"] == "ev-1"
    assert fact_extraction_service.calls == []
    assert "生成客户回答" in [step["title"] for step in result["visible_trace"]]


def test_customer_intelligence_graph_has_single_non_blocking_fact_assessment_path():
    service = CustomerIntelligenceGraphService(
        context_service=FakeCustomerContextService(),
        memory_store_service=FakeCustomerMemoryStoreService(),
        checkpointer=InMemorySaver(),
        session_factory=FakeDB,
    )

    graph_nodes = set(service._graph.get_graph().nodes)

    assert "assess_facts" in graph_nodes
    assert "review_facts" not in graph_nodes
    assert "wait_fact_review" not in graph_nodes


@pytest.mark.asyncio
async def test_customer_intelligence_graph_ignores_low_confidence_facts_without_review_interaction():
    fact_extraction_service = FakeCustomerFactExtractionService(
        facts=[
            ExtractedCustomerFact(
                fact_type="risk",
                subject="审批",
                content="客户内部审批链可能较长。",
                confidence=0.62,
                action="upsert",
                evidence_quote="张总提到需要再走内部流程",
                reason="有风险信号，但表达不够确定",  # noqa: RUF001
            )
        ]
    )
    fact_service = FakeCustomerFactService()
    service = CustomerIntelligenceGraphService(
        context_service=FakeCustomerContextService(),
        memory_store_service=FakeCustomerMemoryStoreService(),
        fact_extraction_service=fact_extraction_service,
        fact_service=fact_service,
        checkpointer=InMemorySaver(),
        session_factory=FakeDB,
    )
    event = _business_event(event_key="refresh-low-confidence-1", occurred_at=datetime(2026, 8, 2, 13, 0, 0))

    result = await _invoke(
        service,
        {
            "team_id": 2,
            "user_id": 9,
            "session_id": 77,
            "event": event,
        },
    )

    assert "__interrupt__" not in result
    assert "customer_fact_review" not in result
    assert fact_service.calls == []
    assert "需要确认" not in str(result)
    assert any(event.get("ignored_count") == 1 for event in result["events"])
    visible_trace_titles = {step["title"] for step in result["visible_trace"]}
    assert "提炼客户事实" not in visible_trace_titles
    assert "沉淀客户事实" not in visible_trace_titles


@pytest.mark.asyncio
async def test_customer_intelligence_graph_keeps_fact_extraction_failure_internal():
    service = CustomerIntelligenceGraphService(
        context_service=FakeCustomerContextService(),
        memory_store_service=FakeCustomerMemoryStoreService(),
        fact_extraction_service=FailingCustomerFactExtractionService(),
        checkpointer=InMemorySaver(),
        session_factory=FakeDB,
    )
    event = _business_event(event_key="refresh-extraction-failure-1", occurred_at=datetime(2026, 8, 2, 13, 0, 0))

    result = await _invoke(
        service,
        {
            "team_id": 2,
            "user_id": 9,
            "session_id": 77,
            "event": event,
        },
    )

    assert any(error.get("event") == "customer_intelligence_fact_extraction_failed" for error in result["errors"])
    assert "提炼客户事实" not in {step["title"] for step in result["visible_trace"]}


@pytest.mark.asyncio
async def test_customer_intelligence_graph_keeps_fact_persistence_failure_internal():
    fact_extraction_service = FakeCustomerFactExtractionService(
        facts=[
            ExtractedCustomerFact(
                fact_type="next_step",
                subject="POC",
                content="周四跟进客户 POC 环境部署情况。",
                confidence=0.94,
                action="upsert",
                evidence_quote="周四跟进客户 POC 环境部署情况",
            )
        ]
    )
    service = CustomerIntelligenceGraphService(
        context_service=FakeCustomerContextService(),
        memory_store_service=FakeCustomerMemoryStoreService(),
        fact_extraction_service=fact_extraction_service,
        fact_service=FailingCustomerFactService(),
        checkpointer=InMemorySaver(),
        session_factory=FakeDB,
    )
    event = _business_event(event_key="refresh-persist-failure-1", occurred_at=datetime(2026, 8, 2, 13, 0, 0))

    result = await _invoke(
        service,
        {
            "team_id": 2,
            "user_id": 9,
            "session_id": 77,
            "event": event,
        },
    )

    assert any(error.get("event") == "customer_intelligence_fact_persist_failed" for error in result["errors"])
    assert "沉淀客户事实" not in {step["title"] for step in result["visible_trace"]}


@pytest.mark.asyncio
async def test_customer_intelligence_graph_auto_persists_high_confidence_fact_without_review():
    fact_extraction_service = FakeCustomerFactExtractionService(
        facts=[
            ExtractedCustomerFact(
                fact_type="next_step",
                subject="POC",
                content="周四跟进客户 POC 环境部署情况。",
                confidence=0.94,
                action="upsert",
                evidence_quote="周四跟进客户 POC 环境部署情况",
            )
        ]
    )
    fact_service = FakeCustomerFactService()
    memory_store = FakeCustomerMemoryStoreService()
    service = CustomerIntelligenceGraphService(
        context_service=FakeCustomerContextService(),
        memory_store_service=memory_store,
        fact_extraction_service=fact_extraction_service,
        fact_service=fact_service,
        checkpointer=InMemorySaver(),
        session_factory=FakeDB,
    )
    event = _business_event(event_key="refresh-high-confidence-1", occurred_at=datetime(2026, 8, 2, 13, 0, 0))

    result = await _invoke(
        service,
        {
            "team_id": 2,
            "user_id": 9,
            "session_id": 77,
            "event": event,
        },
    )

    assert "__interrupt__" not in result
    assert "customer_fact_review" not in result
    assert fact_service.calls[0]["fact_input"].fact_type == "next_step"
    assert memory_store.fact_writes
    assert "需要确认" not in str(result)


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
    event = _business_event(event_key="refresh-1", occurred_at=None)

    result = await _invoke(
        service,
        {
            "team_id": 2,
            "user_id": 9,
            "session_id": 77,
            "event": event,
        },
    )

    assert result["errors"][0]["event"] == "customer_intelligence_context_failed"
    assert result["refresh_plan"]["route"] == "write_memory"
    context_trace = next(step for step in result["visible_trace"] if step["title"] == "读取客户上下文")
    assert context_trace["content"] == "未能读取客户上下文"


@pytest.mark.asyncio
async def test_customer_intelligence_graph_restarts_running_checkpoint_without_repeating_fact_write(monkeypatch):
    saver = _sql_checkpoint_saver()
    first_fact_service = FakeCustomerFactService()
    production_compile = StateGraph.compile

    def compile_with_persist_interrupt(graph, *args, **kwargs):
        return production_compile(graph, *args, interrupt_after=["persist_facts"], **kwargs)

    monkeypatch.setattr(StateGraph, "compile", compile_with_persist_interrupt)
    first_service = CustomerIntelligenceGraphService(
        context_service=FakeCustomerContextService(),
        memory_store_service=FakeCustomerMemoryStoreService(),
        fact_extraction_service=FakeCustomerFactExtractionService(
            facts=[
                ExtractedCustomerFact(
                    fact_type="stage",
                    subject="POC",
                    content="客户已经进入 POC，需准备试用环境。",  # noqa: RUF001
                    confidence=0.88,
                    action="upsert",
                    evidence_quote="张总说本周开始 POC",
                    reason="跟进记录明确表达客户进入 POC",
                )
            ]
        ),
        fact_service=first_fact_service,
        checkpointer=saver,
        session_factory=FakeDB,
    )
    monkeypatch.setattr(StateGraph, "compile", production_compile)
    event = _business_event(event_key="refresh-running-sql-1", occurred_at=datetime(2026, 8, 22, 13, 0, 0))

    interrupted = await _invoke(
        first_service,
        {
            "team_id": 2,
            "user_id": 9,
            "session_id": 77,
            "event": event,
        },
    )

    assert len(first_fact_service.calls) == 1
    assert interrupted["persisted_customer_fact_refs"][0]["fact_id"] == 901
    crashed_snapshot = await first_service._graph.aget_state(
        build_customer_intelligence_graph_config(
            team_id=2,
            user_id=9,
            session_id=77,
            event_key=event.event_key,
        )
    )
    assert crashed_snapshot.next == ("write_memory",)

    restarted_extraction = FakeCustomerFactExtractionService(
        facts=[
            ExtractedCustomerFact(
                fact_type="stage",
                subject="POC",
                content="客户已经进入 POC，需准备试用环境。",  # noqa: RUF001
                confidence=0.88,
                action="upsert",
                evidence_quote="张总说本周开始 POC",
                reason="跟进记录明确表达客户进入 POC",
            )
        ]
    )
    restarted_fact_service = FakeCustomerFactService()
    restarted_memory_store = FakeCustomerMemoryStoreService()
    restarted_service = CustomerIntelligenceGraphService(
        context_service=FakeCustomerContextService(),
        memory_store_service=restarted_memory_store,
        fact_extraction_service=restarted_extraction,
        fact_service=restarted_fact_service,
        checkpointer=SQLAlchemyCheckpointSaver(saver.engine),
        session_factory=FakeDB,
    )

    resumed = await _invoke(
        restarted_service,
        {
            "team_id": 2,
            "user_id": 9,
            "session_id": 77,
            "event": event,
            "resume_existing_execution": True,
        },
    )

    assert restarted_extraction.calls == []
    assert restarted_fact_service.calls == []
    assert resumed["persisted_customer_fact_refs"][0]["fact_id"] == 901
    assert restarted_memory_store.fact_writes[0]["value"]["fact_refs"][1]["fact_id"] == 901

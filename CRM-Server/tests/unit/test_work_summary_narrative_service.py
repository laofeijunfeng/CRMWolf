import json

import pytest

from app.services.agent.schemas import WorkSummaryNarrativeItem, WorkSummaryNarrativeResult
from app.services.work_summary_narrative_service import WorkSummaryNarrativeService


def _work_facts(*, truncated=False):
    return {
        "items": [
            {
                "fact_id": "completed_follow_up_task:fut_test_001:2026-08-05T17:30:00",
                "fact_type": "completed_follow_up_task",
                "source_group": "task",
                "title": "确认预算进展",
                "occurred_at": "2026-08-05T17:30:00",
                "customer": {"id": "cus_test_101", "name": "测试客户"},
            },
            {
                "fact_id": "customer_activity:微信同步试用:2026-08-06T09:00:00",
                "fact_type": "customer_activity",
                "source_group": "activity",
                "title": "微信同步试用",
                "occurred_at": "2026-08-06T09:00:00",
                "customer": {"id": "cus_test_101", "name": "测试客户"},
            },
        ],
        "available_total": 2,
        "truncated": truncated,
        "pagination": {"truncated": truncated},
        "source_counts": {
            "completed_follow_up_task": 1,
            "customer_activity": 1,
        },
    }


class MissingConfigCrud:
    def get_config(self, db, team_id):  # noqa: ARG002
        return None

    def get_decrypted_api_key(self, db, team_id):  # noqa: ARG002
        return None


class Config:
    api_host = "https://api.example.test"
    model_name = "test-model"
    temperature = 0.1


class ConfigCrud:
    def get_config(self, db, team_id):  # noqa: ARG002
        return Config()

    def get_decrypted_api_key(self, db, team_id):  # noqa: ARG002
        return "secret"


class FakeRuntime:
    async def ainvoke_structured(self, **kwargs):  # noqa: ARG002
        return WorkSummaryNarrativeResult(
            answer="本周推进了预算确认，也同步了试用安排。",
            highlights=[
                WorkSummaryNarrativeItem(
                    category="completed_work",
                    title="预算确认",
                    summary="已完成预算进展确认。",
                    fact_ids=["completed_follow_up_task:fut_test_001:2026-08-05T17:30:00"],
                ),
                WorkSummaryNarrativeItem(
                    category="business_progress",
                    title="不存在的事实",
                    summary="这条应该被过滤。",
                    fact_ids=["hallucinated_fact"],
                ),
            ],
            customer_summaries=[
                WorkSummaryNarrativeItem(
                    category="process_record",
                    title="测试客户",
                    summary="同步了试用安排。",
                    fact_ids=["customer_activity:微信同步试用:2026-08-06T09:00:00"],
                )
            ],
            confidence=0.91,
            narrative_mode="langchain_structured_output",
        )


@pytest.mark.asyncio
async def test_work_summary_narrative_fallback_keeps_fact_citations_without_ai_config():
    envelope = await WorkSummaryNarrativeService(config_crud=MissingConfigCrud()).summarize_with_metadata(
        object(),
        team_id=1,
        question="本周我完成了什么",
        work_facts=_work_facts(),
    )

    assert envelope.summary_source == "deterministic_work_summary_fallback"
    assert envelope.fallback_reason == "ai_config_missing"
    assert envelope.result.highlights[0].fact_ids == [
        "completed_follow_up_task:fut_test_001:2026-08-05T17:30:00"
    ]
    assert envelope.result.highlights[1].category == "process_record"
    assert {citation["fact_id"] for citation in envelope.result.citations} == {
        "completed_follow_up_task:fut_test_001:2026-08-05T17:30:00",
        "customer_activity:微信同步试用:2026-08-06T09:00:00",
    }


@pytest.mark.asyncio
async def test_work_summary_narrative_filters_llm_fact_ids_to_structured_items():
    envelope = await WorkSummaryNarrativeService(
        runtime=FakeRuntime(),
        config_crud=ConfigCrud(),
    ).summarize_with_metadata(
        object(),
        team_id=1,
        question="本周我完成了什么",
        work_facts=_work_facts(truncated=True),
    )

    assert envelope.summary_source == "langchain_structured_output"
    assert [item.title for item in envelope.result.highlights] == ["预算确认"]
    assert envelope.result.customer_summaries[0].fact_ids == ["customer_activity:微信同步试用:2026-08-06T09:00:00"]
    assert envelope.result.confidence == 0.72
    assert "后续分页事实" in envelope.result.missing_context
    assert {citation["fact_id"] for citation in envelope.result.citations} == {
        "completed_follow_up_task:fut_test_001:2026-08-05T17:30:00",
        "customer_activity:微信同步试用:2026-08-06T09:00:00",
    }


@pytest.mark.asyncio
async def test_work_summary_narrative_fallback_enforces_reference_budget_for_50_facts():
    facts = {
        "items": [
            {
                "fact_id": f"customer_activity:{index}:2026-08-06T09:00:00",
                "fact_type": "customer_activity",
                "source_group": "activity",
                "title": f"客户沟通 {index}",
                "occurred_at": "2026-08-06T09:00:00",
                "customer": {"id": f"cus_{index % 8}", "name": f"客户 {index % 8}"},
            }
            for index in range(50)
        ],
        "available_total": 50,
        "truncated": False,
        "pagination": {"truncated": False},
        "source_counts": {"customer_activity": 50},
    }

    envelope = await WorkSummaryNarrativeService(config_crud=MissingConfigCrud()).summarize_with_metadata(
        object(),
        team_id=1,
        question="我上周做了什么",
        work_facts=facts,
    )

    referenced = {
        fact_id
        for item in [*envelope.result.highlights, *envelope.result.customer_summaries]
        for fact_id in item.fact_ids
    }
    citation_ids = {str(citation["fact_id"]) for citation in envelope.result.citations}
    assert referenced == citation_ids
    assert len(citation_ids) <= 30


class UngroundedRuntime:
    async def ainvoke_structured(self, **kwargs):  # noqa: ARG002
        return WorkSummaryNarrativeResult(
            answer="这段回答看起来完整，但没有任何可验证的事实引用。",
            highlights=[
                WorkSummaryNarrativeItem(
                    category="business_progress",
                    title="幻觉事实",
                    summary="这条内容没有来源。",
                    fact_ids=["hallucinated_fact"],
                )
            ],
            customer_summaries=[],
            confidence=0.95,
            narrative_mode="langchain_structured_output",
        )


@pytest.mark.asyncio
async def test_work_summary_narrative_rejects_answer_only_after_grounding_removes_all_items():
    envelope = await WorkSummaryNarrativeService(
        runtime=UngroundedRuntime(),
        config_crud=ConfigCrud(),
    ).summarize_with_metadata(
        object(),
        team_id=1,
        question="本周我完成了什么",
        work_facts=_work_facts(),
    )

    assert envelope.summary_source == "deterministic_work_summary_fallback"
    assert envelope.fallback_reason == "llm_summary_ungrounded"
    assert envelope.result.highlights
    assert "这段回答看起来完整" not in envelope.result.answer


@pytest.mark.asyncio
async def test_work_summary_synthesis_rejects_answer_only_after_grounding_removes_all_items():
    chunk_result = WorkSummaryNarrativeResult(
        answer="分块总结",
        highlights=[
            WorkSummaryNarrativeItem(
                category="completed_work",
                title="预算确认",
                summary="已完成预算进展确认。",
                fact_ids=["completed_follow_up_task:fut_test_001:2026-08-05T17:30:00"],
            )
        ],
        customer_summaries=[],
        confidence=0.8,
        narrative_mode="fallback",
    )
    envelope = await WorkSummaryNarrativeService(
        runtime=UngroundedRuntime(),
        config_crud=ConfigCrud(),
    ).synthesize_chunks_with_metadata(
        object(),
        team_id=1,
        question="本周我完成了什么",
        chunk_results=[chunk_result, chunk_result],
        work_facts=_work_facts(),
    )

    assert envelope.summary_source == "deterministic_work_summary_fallback"
    assert envelope.fallback_reason == "llm_synthesis_ungrounded"
    assert envelope.result.highlights
    assert "这段回答看起来完整" not in envelope.result.answer


def _large_snapshot_facts():
    specs = [
        ("customer_activity", "activity", "客户沟通", 25, "客户甲"),
        ("completed_follow_up_task", "task", "已完成跟进任务", 25, "客户乙"),
        ("license_application", "business_event", "License 申请", 21, "客户丙"),
    ]
    facts = []
    index = 0
    for fact_type, source_group, title, count, customer_name in specs:
        for local_index in range(count):
            facts.append({
                "fact_id": f"{fact_type}:{index}:2026-08-12T09:00:00",
                "fact_type": fact_type,
                "source_group": source_group,
                "title": f"{title} {local_index}",
                "occurred_at": "2026-08-12T09:00:00",
                "customer": {"id": f"cus_{customer_name}", "name": customer_name},
            })
            index += 1
    return facts


@pytest.mark.asyncio
async def test_work_summary_deterministic_synthesis_aggregates_the_complete_snapshot():
    facts = _large_snapshot_facts()
    noisy_chunk = WorkSummaryNarrativeResult(
        answer="分块结果",
        highlights=[
            WorkSummaryNarrativeItem(
                category="process_record",
                title=f"分块项 {index}",
                summary="只代表分块中的局部信息。",
                fact_ids=[facts[index]["fact_id"]],
            )
            for index in range(8)
        ],
        customer_summaries=[],
        confidence=0.75,
        narrative_mode="fallback",
    )
    envelope = await WorkSummaryNarrativeService(
        config_crud=MissingConfigCrud(),
    ).synthesize_chunks_with_metadata(
        object(),
        team_id=1,
        question="我上周做了什么",
        chunk_results=[noisy_chunk, noisy_chunk, noisy_chunk],
        work_facts={
            "items": facts,
            "available_total": 71,
            "truncated": False,
            "pagination": {"truncated": False},
        },
    )

    assert envelope.summary_source == "deterministic_work_summary_fallback"
    assert "71 条" in envelope.result.answer
    assert "客户活动 25 条" in envelope.result.answer
    assert "已完成跟进任务 25 条" in envelope.result.answer
    assert "License 申请 21 条" in envelope.result.answer
    assert {item.title for item in envelope.result.customer_summaries} == {"客户甲", "客户乙", "客户丙"}
    assert len(envelope.result.citations) <= 30


def test_work_summary_synthesis_prompt_has_a_hard_input_budget():
    item = WorkSummaryNarrativeItem(
        category="business_progress",
        title="标题" * 60,
        summary="总结" * 150,
        fact_ids=["fact:" + "x" * 300 for _ in range(8)],
    )
    chunk = WorkSummaryNarrativeResult(
        answer="分块结果",
        highlights=[item.model_copy(update={"title": f"重点 {index}"}) for index in range(12)],
        customer_summaries=[item.model_copy(update={"title": f"客户 {index}"}) for index in range(12)],
        confidence=0.8,
        narrative_mode="fallback",
    )

    prompt = WorkSummaryNarrativeService._build_synthesis_prompt(
        question="问题" * 2000,
        chunk_results=[chunk for _ in range(20)],
        work_facts={"items": _large_snapshot_facts(), "available_total": 71, "truncated": False},
    )
    payload = json.loads(prompt)

    assert len(payload["question"]) == 1000
    assert len(payload["chunks"]) == 20
    assert all(len(chunk_payload["highlights"]) == 2 for chunk_payload in payload["chunks"])
    assert all(len(chunk_payload["customer_summaries"]) == 1 for chunk_payload in payload["chunks"])
    assert all(
        len(item_payload["fact_ids"]) == 1
        for chunk_payload in payload["chunks"]
        for item_payload in [*chunk_payload["highlights"], *chunk_payload["customer_summaries"]]
    )
    assert all(
        len(item_payload["fact_ids"][0]) == 305
        for chunk_payload in payload["chunks"]
        for item_payload in [*chunk_payload["highlights"], *chunk_payload["customer_summaries"]]
    )
    assert len(prompt) < 60000


def test_work_summary_customer_fallback_skips_groups_without_fact_ids():
    summaries = WorkSummaryNarrativeService._customer_summary_items([
        {
            "fact_type": "customer_activity",
            "title": "缺少稳定事实标识的历史记录",
            "customer": {"id": "cus_legacy", "name": "历史客户"},
        }
    ])

    assert summaries == []


def test_work_summary_synthesis_prompt_rejects_chunk_count_over_budget():
    item = WorkSummaryNarrativeItem(
        category="business_progress",
        title="事项",
        summary="已完成事项。",
        fact_ids=["fact:stable-id"],
    )
    chunk = WorkSummaryNarrativeResult(
        answer="分块结果",
        highlights=[item],
        customer_summaries=[],
        confidence=0.8,
        narrative_mode="fallback",
    )

    with pytest.raises(ValueError, match="synthesis chunk budget"):
        WorkSummaryNarrativeService._build_synthesis_prompt(
            question="我上周做了什么",
            chunk_results=[chunk for _ in range(21)],
            work_facts={"items": _large_snapshot_facts(), "available_total": 71, "truncated": False},
        )

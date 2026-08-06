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

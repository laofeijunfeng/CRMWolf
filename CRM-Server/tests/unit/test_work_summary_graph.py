from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.services.agent.schemas import WorkSummaryNarrativeResult
from app.services.agent.work_summary_graph import (
    WorkSummaryGraphRequest,
    WorkSummaryGraphService,
)
from app.services.work_summary_grounding import CitationResolver
from app.services.work_summary_models import (
    WorkSummaryCoverage,
    WorkSummaryFactPage,
    WorkSummaryQuery,
)
from app.services.work_summary_narrative_service import WorkSummaryNarrativeService


class MissingConfigCrud:
    def get_config(self, db, team_id):
        return None

    def get_decrypted_api_key(self, db, team_id):
        return None


def _fact(index: int) -> dict[str, Any]:
    customer_index = (index % 5) + 1
    return {
        "fact_id": f"customer_activity:{index:03d}:2026-08-12T09:00:00",
        "fact_type": "customer_activity",
        "source_group": "activity",
        "title": f"客户沟通 {index}",
        "occurred_at": "2026-08-12T09:00:00",
        "customer": {
            "id": f"cus_test_{customer_index:03d}",
            "name": f"测试客户 {customer_index}",
        },
        "payload": {"summary": f"完成第 {index} 条客户沟通"},
    }


class FakePagedWorkSummaryService:
    def __init__(self, facts: list[dict[str, Any]]) -> None:
        self.facts = facts
        self.calls: list[str | None] = []

    def fetch_page(
        self,
        db: object,
        *,
        query: WorkSummaryQuery,
        cursor: str | None,
    ) -> WorkSummaryFactPage:
        self.calls.append(cursor)
        offset = int(cursor or "0")
        items = self.facts[offset : offset + query.page_size]
        next_offset = offset + len(items)
        next_cursor = str(next_offset) if next_offset < len(self.facts) else None
        return WorkSummaryFactPage(
            items=items,
            available_total=len(self.facts),
            next_cursor=next_cursor,
            source_counts={"customer_activity": len(items)},
            source_total_counts={"customer_activity": len(self.facts)},
            source_status={"customer_activities": "queried"},
        )


def _graph(facts: list[dict[str, Any]], **kwargs: Any) -> tuple[WorkSummaryGraphService, FakePagedWorkSummaryService]:
    fact_service = FakePagedWorkSummaryService(facts)
    graph = WorkSummaryGraphService(
        fact_service=fact_service,
        narrative_service=WorkSummaryNarrativeService(config_crud=MissingConfigCrud()),
        **kwargs,
    )
    return graph, fact_service


@pytest.mark.asyncio
async def test_work_summary_graph_summarizes_31_facts_without_citation_overflow():
    graph, _ = _graph([_fact(index) for index in range(31)])

    outcome = await graph.run(
        WorkSummaryGraphRequest(
            db=object(),
            team_id=1,
            user_id=2,
            session_id=3,
            question="我上周做了什么",
            window="last_week",
        )
    )

    assert outcome.coverage == WorkSummaryCoverage(
        available_total=31,
        retrieved_total=31,
        summarized_total=31,
        referenced_total=len(outcome.citations),
        pages_fetched=1,
        complete=True,
        stop_reason="all_facts_collected",
    )
    assert len(outcome.citations) <= 30
    assert {citation.fact_id for citation in outcome.citations} <= {
        f"customer_activity:{index:03d}:2026-08-12T09:00:00" for index in range(31)
    }


@pytest.mark.asyncio
async def test_work_summary_graph_fetches_all_71_facts_across_two_pages():
    graph, fact_service = _graph([_fact(index) for index in range(71)])

    outcome = await graph.run(
        WorkSummaryGraphRequest(
            db=object(),
            team_id=1,
            user_id=2,
            session_id=3,
            question="我上周做了什么",
            window="last_week",
        )
    )

    assert fact_service.calls == [None, "50"]
    assert outcome.coverage.available_total == 71
    assert outcome.coverage.retrieved_total == 71
    assert outcome.coverage.summarized_total == 71
    assert outcome.coverage.pages_fetched == 2
    assert outcome.coverage.complete is True
    assert outcome.coverage.stop_reason == "all_facts_collected"
    assert "71 条" in outcome.answer
    assert "截断" not in outcome.answer


@pytest.mark.asyncio
async def test_work_summary_graph_reports_partial_coverage_when_fact_budget_is_reached():
    graph, fact_service = _graph(
        [_fact(index) for index in range(120)],
        max_facts_per_summary=75,
    )

    outcome = await graph.run(
        WorkSummaryGraphRequest(
            db=object(),
            team_id=1,
            user_id=2,
            session_id=3,
            question="总结最近工作",
            window="this_month",
        )
    )

    assert fact_service.calls == [None, "50"]
    assert outcome.coverage.available_total == 120
    assert outcome.coverage.retrieved_total == 75
    assert outcome.coverage.summarized_total == 75
    assert outcome.coverage.complete is False
    assert outcome.coverage.stop_reason == "fact_budget_exceeded"
    assert "仅覆盖前 75 条" in outcome.answer
    assert "共 120 条" in outcome.answer


def test_citation_resolver_enforces_reference_snapshot_and_limit_invariants():
    facts = [_fact(index) for index in range(40)]
    resolver = CitationResolver(max_referenced_facts=30)

    resolved = resolver.resolve(
        highlights=[
            {
                "category": "completed_work",
                "title": f"本周工作 {chunk_index}",
                "summary": "已完成多项工作。",
                "fact_ids": [
                    fact["fact_id"]
                    for fact in facts[chunk_index * 8 : (chunk_index + 1) * 8]
                ] + (["hallucinated"] if chunk_index == 0 else []),
            }
            for chunk_index in range(5)
        ],
        customer_summaries=[],
        facts=facts,
    )

    assert len(resolved.citations) == 30
    assert len(resolved.highlights) == 5
    assert all(item.fact_ids for item in resolved.highlights)
    assert "hallucinated" not in resolved.highlights[0].fact_ids
    referenced = {
        fact_id
        for item in [*resolved.highlights, *resolved.customer_summaries]
        for fact_id in item.fact_ids
    }
    assert referenced == {citation.fact_id for citation in resolved.citations}
    assert referenced <= {fact["fact_id"] for fact in facts}


def test_work_summary_graph_rejects_configuration_that_exceeds_synthesis_budget():
    with pytest.raises(ValueError, match="synthesis chunk budget"):
        WorkSummaryGraphService(
            fact_service=FakePagedWorkSummaryService([]),
            narrative_service=WorkSummaryNarrativeService(config_crud=MissingConfigCrud()),
            max_facts_per_summary=501,
            chunk_size=25,
        )


@pytest.mark.asyncio
async def test_work_summary_graph_chunks_large_snapshots_before_synthesis():
    fact_service = FakePagedWorkSummaryService([_fact(index) for index in range(71)])

    class ChunkingNarrativeService:
        def __init__(self) -> None:
            self.chunk_sizes: list[int] = []
            self.synthesis_calls = 0

        async def summarize_with_metadata(self, db, *, team_id, question, work_facts):
            self.chunk_sizes.append(len(work_facts["items"]))
            first = work_facts["items"][0]
            result = WorkSummaryNarrativeResult(
                answer=f"分块包含 {len(work_facts['items'])} 条事实。",
                highlights=[{
                    "category": "process_record",
                    "title": str(first["title"]),
                    "summary": "已完成客户沟通。",
                    "fact_ids": [str(first["fact_id"])],
                }],
                customer_summaries=[],
                confidence=0.9,
                narrative_mode="langchain_structured_output",
            )
            return SimpleNamespace(
                result=result,
                summary_source="langchain_structured_output",
                model="test-model",
                fallback_reason=None,
                fallback_error=None,
            )

        async def synthesize_chunks_with_metadata(
            self,
            db,
            *,
            team_id,
            question,
            chunk_results,
            work_facts,
        ):
            self.synthesis_calls += 1
            fact_ids = [
                item.fact_ids[0]
                for result in chunk_results
                for item in result.highlights
            ]
            result = WorkSummaryNarrativeResult(
                answer=f"### 工作总结\n已汇总 {len(work_facts['items'])} 条工作事实。",
                highlights=[{
                    "category": "process_record",
                    "title": "客户沟通",
                    "summary": "完成多项客户沟通。",
                    "fact_ids": fact_ids,
                }],
                customer_summaries=[],
                confidence=0.88,
                narrative_mode="langchain_structured_output",
            )
            return SimpleNamespace(
                result=result,
                summary_source="langchain_structured_output",
                model="test-model",
                fallback_reason=None,
                fallback_error=None,
            )

    narrative_service = ChunkingNarrativeService()
    graph = WorkSummaryGraphService(
        fact_service=fact_service,
        narrative_service=narrative_service,
        chunk_size=25,
    )

    outcome = await graph.run(
        WorkSummaryGraphRequest(
            db=object(),
            team_id=1,
            user_id=2,
            session_id=3,
            question="我上周做了什么",
            window="last_week",
        )
    )

    assert narrative_service.chunk_sizes == [25, 25, 21]
    assert narrative_service.synthesis_calls == 1
    assert outcome.summary_source == "langchain_structured_output"
    assert outcome.coverage.summarized_total == 71

class SnapshotAwarePagedWorkSummaryService(FakePagedWorkSummaryService):
    def __init__(self, facts: list[dict[str, Any]]) -> None:
        super().__init__(facts)
        self.queries: list[WorkSummaryQuery] = []

    def fetch_page(
        self,
        db: object,
        *,
        query: WorkSummaryQuery,
        cursor: str | None,
    ) -> WorkSummaryFactPage:
        self.queries.append(query)
        page = super().fetch_page(db, query=query, cursor=cursor)
        if cursor is None:
            return page.model_copy(update={
                "filters": {
                    "starts_at": "2026-08-10T00:00:00",
                    "ends_at": "2026-08-17T00:00:00",
                    "timezone": "Asia/Shanghai",
                }
            })
        return page


@pytest.mark.asyncio
async def test_work_summary_graph_freezes_relative_window_after_first_page():
    fact_service = SnapshotAwarePagedWorkSummaryService([_fact(index) for index in range(71)])
    graph = WorkSummaryGraphService(
        fact_service=fact_service,
        narrative_service=WorkSummaryNarrativeService(config_crud=MissingConfigCrud()),
    )

    await graph.run(
        WorkSummaryGraphRequest(
            db=object(),
            team_id=1,
            user_id=2,
            session_id=3,
            question="我上周做了什么",
            window="last_week",
        )
    )

    assert fact_service.queries[0].window == "last_week"
    assert fact_service.queries[1].window == "custom"
    assert fact_service.queries[1].start_at == "2026-08-10T00:00:00"
    assert fact_service.queries[1].end_at == "2026-08-17T00:00:00"


class FailingSecondPageWorkSummaryService(FakePagedWorkSummaryService):
    def __init__(self, facts: list[dict[str, Any]]) -> None:
        super().__init__(facts)
        self.second_page_attempts = 0

    def fetch_page(
        self,
        db: object,
        *,
        query: WorkSummaryQuery,
        cursor: str | None,
    ) -> WorkSummaryFactPage:
        if cursor is not None:
            self.second_page_attempts += 1
            raise SQLAlchemyError("temporary source failure")
        return super().fetch_page(db, query=query, cursor=cursor)


@pytest.mark.asyncio
async def test_work_summary_graph_returns_explicit_partial_after_retried_later_page_failure():
    fact_service = FailingSecondPageWorkSummaryService([_fact(index) for index in range(71)])
    graph = WorkSummaryGraphService(
        fact_service=fact_service,
        narrative_service=WorkSummaryNarrativeService(config_crud=MissingConfigCrud()),
    )

    outcome = await graph.run(
        WorkSummaryGraphRequest(
            db=object(),
            team_id=1,
            user_id=2,
            session_id=3,
            question="我上周做了什么",
            window="last_week",
        )
    )

    assert fact_service.second_page_attempts == 3
    assert outcome.coverage.available_total == 71
    assert outcome.coverage.retrieved_total == 50
    assert outcome.coverage.complete is False
    assert outcome.coverage.stop_reason == "source_failed"
    assert "数据读取中断" in outcome.answer
    assert "50 条" in outcome.answer
    assert "71 条" in outcome.answer


@pytest.mark.asyncio
async def test_work_summary_graph_does_not_hide_first_page_source_failure():
    class AlwaysFailingWorkSummaryService:
        def fetch_page(self, db, *, query, cursor):
            raise SQLAlchemyError("source unavailable")

    graph = WorkSummaryGraphService(
        fact_service=AlwaysFailingWorkSummaryService(),
        narrative_service=WorkSummaryNarrativeService(config_crud=MissingConfigCrud()),
    )

    with pytest.raises(SQLAlchemyError, match="source unavailable"):
        await graph.run(
            WorkSummaryGraphRequest(
                db=object(),
                team_id=1,
                user_id=2,
                session_id=3,
                question="我上周做了什么",
                window="last_week",
            )
        )


@pytest.mark.asyncio
async def test_work_summary_graph_isolates_checkpoint_state_between_runs_in_same_session():
    from langgraph.checkpoint.memory import InMemorySaver

    fact_service = FakePagedWorkSummaryService([_fact(index) for index in range(71)])
    graph = WorkSummaryGraphService(
        fact_service=fact_service,
        narrative_service=WorkSummaryNarrativeService(config_crud=MissingConfigCrud()),
        checkpointer=InMemorySaver(),
    )
    first_request = WorkSummaryGraphRequest(
        db=object(),
        team_id=1,
        user_id=2,
        session_id=3,
        question="我上周做了什么",
        window="last_week",
    )

    first = await graph.run(first_request)
    fact_service.facts = [_fact(index) for index in range(3)]
    fact_service.calls.clear()
    second = await graph.run(
        WorkSummaryGraphRequest(
            db=object(),
            team_id=1,
            user_id=2,
            session_id=3,
            question="再总结一次",
            window="last_week",
        )
    )

    assert first.coverage.retrieved_total == 71
    assert second.coverage.retrieved_total == 3
    assert second.coverage.pages_fetched == 1
    assert fact_service.calls == [None]

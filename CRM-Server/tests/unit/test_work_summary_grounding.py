from app.services.agent.schemas import WorkSummaryNarrativeItem
from app.services.work_summary_grounding import CitationResolver


def test_citation_resolver_preserves_every_grounded_item_before_spending_extra_budget():
    facts = [
        {
            "fact_id": f"fact:{index}",
            "fact_type": "customer_activity",
            "source_group": "activity",
            "title": f"事实 {index}",
            "occurred_at": "2026-08-12T09:00:00",
            "customer": {"id": f"cus_{index % 4}", "name": f"客户 {index % 4}"},
        }
        for index in range(192)
    ]

    def narrative_item(index: int, *, customer: bool = False) -> WorkSummaryNarrativeItem:
        start = index * 8
        return WorkSummaryNarrativeItem(
            category="business_progress",
            title=("客户" if customer else "重点") + f" {index}",
            summary="聚合后的工作事实。",
            fact_ids=[f"fact:{fact_index}" for fact_index in range(start, start + 8)],
        )

    resolved = CitationResolver(max_referenced_facts=30).resolve(
        highlights=[narrative_item(index) for index in range(12)],
        customer_summaries=[narrative_item(index + 12, customer=True) for index in range(12)],
        facts=facts,
    )

    assert len(resolved.highlights) == 12
    assert len(resolved.customer_summaries) == 12
    assert all(item.fact_ids for item in [*resolved.highlights, *resolved.customer_summaries])
    assert len(resolved.citations) == 30
    referenced = {
        fact_id
        for item in [*resolved.highlights, *resolved.customer_summaries]
        for fact_id in item.fact_ids
    }
    assert referenced == {citation.fact_id for citation in resolved.citations}

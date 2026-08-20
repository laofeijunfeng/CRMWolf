"""Authoritative grounding and citation-budget enforcement for work summaries."""
from __future__ import annotations

from app.services.agent.schemas import WorkSummaryNarrativeItem
from app.services.agent.types import JSONDict, coerce_json_dict
from app.services.work_summary_models import (
    DEFAULT_WORK_SUMMARY_CITATION_BUDGET,
    ResolvedWorkSummaryNarrative,
    WorkSummaryCitation,
)


class CitationResolver:
    """Resolve narrative references against one retrieved fact snapshot."""

    def __init__(
        self,
        *,
        max_referenced_facts: int = DEFAULT_WORK_SUMMARY_CITATION_BUDGET,
    ) -> None:
        if max_referenced_facts < 1:
            raise ValueError("max_referenced_facts 必须大于 0")
        self.max_referenced_facts = max_referenced_facts

    def resolve(
        self,
        *,
        highlights: list[WorkSummaryNarrativeItem | JSONDict],
        customer_summaries: list[WorkSummaryNarrativeItem | JSONDict],
        facts: list[JSONDict],
    ) -> ResolvedWorkSummaryNarrative:
        facts_by_id = {
            str(fact.get("fact_id")): fact
            for fact in facts
            if str(fact.get("fact_id") or "").strip()
        }
        prepared = [
            *self._prepare_items("highlight", highlights, facts_by_id),
            *self._prepare_items("customer_summary", customer_summaries, facts_by_id),
        ]
        selected_ids: list[list[str]] = [[] for _ in prepared]
        referenced_ids: list[str] = []
        seen: set[str] = set()

        # Reserve one authoritative fact for every grounded narrative item before
        # spending the remaining citation budget on additional detail. This keeps
        # the global budget from allowing early highlights to starve later customer
        # summaries.
        for index, (_, _, candidate_ids) in enumerate(prepared):
            for fact_id in candidate_ids:
                if fact_id in seen:
                    selected_ids[index].append(fact_id)
                    break
                if len(referenced_ids) < self.max_referenced_facts:
                    seen.add(fact_id)
                    referenced_ids.append(fact_id)
                    selected_ids[index].append(fact_id)
                    break

        # Allocate remaining references round-robin so no single item can consume
        # the rest of the budget. WorkSummaryNarrativeItem itself caps references
        # at eight, so this loop is bounded.
        for candidate_position in range(1, 8):
            for index, (_, _, candidate_ids) in enumerate(prepared):
                if not selected_ids[index] or candidate_position >= len(candidate_ids):
                    continue
                fact_id = candidate_ids[candidate_position]
                if fact_id in selected_ids[index]:
                    continue
                if fact_id not in seen:
                    if len(referenced_ids) >= self.max_referenced_facts:
                        continue
                    seen.add(fact_id)
                    referenced_ids.append(fact_id)
                selected_ids[index].append(fact_id)

        grounded_highlights: list[WorkSummaryNarrativeItem] = []
        grounded_customer_summaries: list[WorkSummaryNarrativeItem] = []
        for (kind, item_data, _), item_ids in zip(prepared, selected_ids, strict=True):
            if not item_ids:
                continue
            grounded_item = WorkSummaryNarrativeItem.model_validate(
                {**item_data, "fact_ids": item_ids}
            )
            if kind == "highlight":
                grounded_highlights.append(grounded_item)
            else:
                grounded_customer_summaries.append(grounded_item)
        citations = [self._citation(facts_by_id[fact_id]) for fact_id in referenced_ids]
        return ResolvedWorkSummaryNarrative(
            highlights=grounded_highlights,
            customer_summaries=grounded_customer_summaries,
            citations=citations,
        )

    @staticmethod
    def _prepare_items(
        kind: str,
        items: list[WorkSummaryNarrativeItem | JSONDict],
        facts_by_id: dict[str, JSONDict],
    ) -> list[tuple[str, JSONDict, list[str]]]:
        prepared: list[tuple[str, JSONDict, list[str]]] = []
        for raw_item in items:
            item_data = (
                raw_item.model_dump()
                if isinstance(raw_item, WorkSummaryNarrativeItem)
                else dict(raw_item)
            )
            raw_fact_ids = item_data.get("fact_ids")
            candidate_fact_ids = raw_fact_ids if isinstance(raw_fact_ids, list) else []
            valid_ids: list[str] = []
            for raw_fact_id in candidate_fact_ids:
                fact_id = str(raw_fact_id).strip()
                if fact_id and fact_id in facts_by_id and fact_id not in valid_ids:
                    valid_ids.append(fact_id)
                if len(valid_ids) >= 8:
                    break
            if valid_ids:
                prepared.append((kind, item_data, valid_ids))
        return prepared

    @staticmethod
    def _citation(fact: JSONDict) -> WorkSummaryCitation:
        customer = fact.get("customer")
        return WorkSummaryCitation(
            fact_id=str(fact.get("fact_id")),
            fact_type=_optional_text(fact.get("fact_type")),
            source_group=_optional_text(fact.get("source_group")),
            title=_optional_text(fact.get("title")),
            occurred_at=_optional_text(fact.get("occurred_at")),
            customer=coerce_json_dict(customer),
        )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

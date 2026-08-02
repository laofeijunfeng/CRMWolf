"""Customer candidate recall from customer intelligence evidence."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.models.customer import Customer
from app.services.customer_embedding_service import (
    CustomerEmbeddingService,
    CustomerEmbeddingUnavailableError,
    customer_embedding_service,
)
from app.services.customer_qdrant_index_service import (
    CustomerEvidenceSearchResult,
    CustomerQdrantIndexService,
    SourceType,
    customer_qdrant_index_service,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

    from app.services.agent.types import JSONDict

logger = logging.getLogger(__name__)


class CustomerVisibilityPredicate(Protocol):
    def __call__(self, customer: Customer) -> bool:
        """Return whether the current Agent user can see this customer."""


@dataclass(frozen=True)
class CustomerKnowledgeCandidateResult:
    candidates: list[JSONDict]
    retrieval_event: JSONDict


class CustomerKnowledgeCandidateService:
    """Recall customer candidates by semantic evidence before customer resolution."""

    def __init__(
        self,
        *,
        embedding_service: CustomerEmbeddingService | None = None,
        qdrant_index_service: CustomerQdrantIndexService | None = None,
    ) -> None:
        self.embedding_service = embedding_service or customer_embedding_service
        self.qdrant_index_service = qdrant_index_service or customer_qdrant_index_service

    def recall(
        self,
        db: Session,
        *,
        team_id: int,
        query_text: str,
        limit: int = 8,
        source_types: Sequence[SourceType] | None = None,
        visibility_predicate: CustomerVisibilityPredicate | None = None,
    ) -> CustomerKnowledgeCandidateResult:
        if not self.qdrant_index_service.enabled:
            return CustomerKnowledgeCandidateResult(
                candidates=[],
                retrieval_event={
                    "event": "customer_knowledge_candidates",
                    "status": "disabled",
                    "candidate_count": 0,
                },
            )
        query = query_text.strip()
        if not query:
            return CustomerKnowledgeCandidateResult(
                candidates=[],
                retrieval_event={
                    "event": "customer_knowledge_candidates",
                    "status": "skipped_empty_query",
                    "candidate_count": 0,
                },
            )

        try:
            vector = self.embedding_service.embed_query(db, team_id, query)
            hits = self.qdrant_index_service.search_team_customer_evidence(
                query_vector=vector,
                tenant_id=team_id,
                team_id=team_id,
                limit=limit * 3,
                source_types=source_types,
            )
        except CustomerEmbeddingUnavailableError as exc:
            return CustomerKnowledgeCandidateResult(
                candidates=[],
                retrieval_event={
                    "event": "customer_knowledge_candidates",
                    "status": "embedding_unavailable",
                    "candidate_count": 0,
                    "reason": str(exc),
                },
            )
        except Exception as exc:
            logger.info("客户知识库候选召回失败: team_id=%s, reason=%s", team_id, exc.__class__.__name__)
            return CustomerKnowledgeCandidateResult(
                candidates=[],
                retrieval_event={
                    "event": "customer_knowledge_candidates",
                    "status": "failed",
                    "candidate_count": 0,
                    "reason": exc.__class__.__name__,
                },
            )

        candidates = self._build_candidates(
            db,
            team_id=team_id,
            hits=hits,
            limit=limit,
            visibility_predicate=visibility_predicate,
        )
        return CustomerKnowledgeCandidateResult(
            candidates=candidates,
            retrieval_event={
                "event": "customer_knowledge_candidates",
                "status": "ok",
                "candidate_count": len(candidates),
            },
        )

    def _build_candidates(
        self,
        db: Session,
        *,
        team_id: int,
        hits: list[CustomerEvidenceSearchResult],
        limit: int,
        visibility_predicate: CustomerVisibilityPredicate | None,
    ) -> list[JSONDict]:
        grouped = _group_hits_by_customer(hits)
        if not grouped:
            return []
        customer_ids = list(grouped.keys())
        customers = (
            db.query(Customer)
            .filter(Customer.team_id == team_id, Customer.id.in_(customer_ids))
            .all()
        )
        customer_by_id = {int(customer.id): customer for customer in customers}
        candidates: list[JSONDict] = []
        for customer_id, customer_hits in grouped.items():
            customer = customer_by_id.get(customer_id)
            if customer is None:
                continue
            if visibility_predicate is not None and not visibility_predicate(customer):
                continue
            best_score = max(_bounded_score(hit.score) for hit in customer_hits)
            candidates.append({
                "id": customer_id,
                "account_name": customer.account_name,
                "city": customer.city,
                "owner_info": None,
                "collaborator_infos": [],
                "match": {
                    "source": "customer_knowledge",
                    "score": best_score,
                    "reason": "客户知识库语义匹配",
                    "evidence": [_hit_evidence(hit) for hit in customer_hits[:3]],
                },
            })
        return sorted(
            candidates,
            key=lambda item: float(_match(item).get("score") or 0),
            reverse=True,
        )[:limit]


def _group_hits_by_customer(hits: list[CustomerEvidenceSearchResult]) -> dict[int, list[CustomerEvidenceSearchResult]]:
    grouped: dict[int, list[CustomerEvidenceSearchResult]] = {}
    for hit in hits:
        customer_id = hit.customer_id
        if customer_id is None or customer_id <= 0:
            continue
        grouped.setdefault(customer_id, []).append(hit)
    return grouped


def _hit_evidence(hit: CustomerEvidenceSearchResult) -> JSONDict:
    return {
        "title": hit.title or "客户知识库证据",
        "snippet": _snippet(hit.text),
        "score": _bounded_score(hit.score),
    }


def _snippet(text: str | None, limit: int = 120) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return f"{value[:limit]}..."


def _bounded_score(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def _match(candidate: JSONDict) -> JSONDict:
    match = candidate.get("match")
    return match if isinstance(match, dict) else {}


customer_knowledge_candidate_service = CustomerKnowledgeCandidateService()

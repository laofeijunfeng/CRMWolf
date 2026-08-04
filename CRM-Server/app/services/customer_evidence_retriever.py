"""Retrieval strategy boundary for customer semantic evidence."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

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

logger = logging.getLogger(__name__)

DEFAULT_MIN_SCORE = 0.45
DEFAULT_SOURCE_WEIGHTS: dict[str, float] = {
    "follow_up": 1.08,
    "business_flow": 1.06,
    "opportunity": 1.05,
    "contract": 1.04,
    "payment": 1.04,
    "customer_brief": 1.02,
    "customer_profile": 1.0,
    "customer": 0.98,
    "contact": 0.96,
    "agent_judgement": 0.94,
}


@dataclass(frozen=True)
class CustomerEvidenceHit:
    evidence_id: str
    score: float
    adjusted_score: float
    source_type: str | None
    source_object_id: str | None
    business_object_type: str | None
    business_object_id: str | None
    title: str | None
    text: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "score": round(self.score, 4),
            "adjusted_score": round(self.adjusted_score, 4),
            "source_type": self.source_type,
            "source_object_id": self.source_object_id,
            "business_object_type": self.business_object_type,
            "business_object_id": self.business_object_id,
            "title": self.title,
            "text": self.text,
        }

    def to_citation(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "score": round(self.score, 4),
            "adjusted_score": round(self.adjusted_score, 4),
            "source_type": self.source_type,
            "source_object_id": self.source_object_id,
            "business_object_type": self.business_object_type,
            "business_object_id": self.business_object_id,
            "title": self.title,
            "text": self.text,
        }


@dataclass(frozen=True)
class EvidenceRetrievalState:
    status: str
    enabled: bool
    error_message: str | None = None
    query_text_present: bool = False
    requested_limit: int = 0
    raw_count: int = 0
    returned_count: int = 0
    dropped_count: int = 0
    top_score: float | None = None
    min_score: float | None = None
    source_types: list[str] | None = None
    strategy: str = "customer_semantic_qdrant"
    source_weights: dict[str, float] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "enabled": self.enabled,
            "error_message": self.error_message,
            "query_text_present": self.query_text_present,
            "requested_limit": self.requested_limit,
            "raw_count": self.raw_count,
            "returned_count": self.returned_count,
            "dropped_count": self.dropped_count,
            "top_score": round(self.top_score, 4) if self.top_score is not None else None,
            "min_score": self.min_score,
            "source_types": self.source_types or [],
            "strategy": self.strategy,
            "source_weights": self.source_weights or {},
        }


@dataclass(frozen=True)
class CustomerEvidenceRetrievalResult:
    hits: list[CustomerEvidenceHit]
    state: EvidenceRetrievalState


class CustomerEvidenceRetriever:
    """Coordinates embedding, vector search, filtering, and retrieval telemetry."""

    def __init__(
        self,
        embedding_service: CustomerEmbeddingService | None = None,
        qdrant_index_service: CustomerQdrantIndexService | None = None,
        min_score: float = DEFAULT_MIN_SCORE,
        source_weights: dict[str, float] | None = None,
    ) -> None:
        self.embedding_service = embedding_service or customer_embedding_service
        self.qdrant_index_service = qdrant_index_service or customer_qdrant_index_service
        self.min_score = min_score
        self.source_weights = source_weights or DEFAULT_SOURCE_WEIGHTS

    def retrieve_customer_evidence(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        query_text: str | None,
        evidence_limit: int,
        source_types: Sequence[SourceType] | None = None,
    ) -> CustomerEvidenceRetrievalResult:
        requested_source_types = [str(item) for item in source_types] if source_types else []
        query_present = bool(query_text and query_text.strip())
        if not self.qdrant_index_service.enabled:
            return self._empty_state(
                status="disabled",
                enabled=False,
                query_present=query_present,
                evidence_limit=evidence_limit,
                source_types=requested_source_types,
            )
        if not query_present:
            return self._empty_state(
                status="skipped_empty_query",
                enabled=True,
                query_present=False,
                evidence_limit=evidence_limit,
                source_types=requested_source_types,
            )

        try:
            vector = self.embedding_service.embed_query(db, team_id, query_text or "")
            raw_results = self.qdrant_index_service.search_customer_evidence(
                query_vector=vector,
                tenant_id=team_id,
                team_id=team_id,
                customer_id=customer_id,
                limit=max(evidence_limit * 3, evidence_limit),
                source_types=source_types,
            )
        except CustomerEmbeddingUnavailableError as exc:
            logger.info("客户智能证据检索跳过: %s", exc)
            return self._empty_state(
                status="embedding_unavailable",
                enabled=True,
                query_present=True,
                evidence_limit=evidence_limit,
                source_types=requested_source_types,
                error_message=str(exc),
            )
        except Exception as exc:
            logger.exception("客户智能证据检索失败: customer_id=%s", customer_id)
            return self._empty_state(
                status="failed",
                enabled=True,
                query_present=True,
                evidence_limit=evidence_limit,
                source_types=requested_source_types,
                error_message=str(exc),
            )

        accepted = [self._evidence_hit(item) for item in raw_results if item.score >= self.min_score]
        hits = sorted(accepted, key=lambda item: item.adjusted_score, reverse=True)[:evidence_limit]
        top_score = max((item.score for item in raw_results), default=None)
        status = "ok" if hits else "low_confidence" if raw_results else "empty"
        state = EvidenceRetrievalState(
            status=status,
            enabled=True,
            query_text_present=True,
            requested_limit=evidence_limit,
            raw_count=len(raw_results),
            returned_count=len(hits),
            dropped_count=max(len(raw_results) - len(accepted), 0),
            top_score=top_score,
            min_score=self.min_score,
            source_types=requested_source_types,
            strategy="customer_semantic_qdrant_source_weighted",
            source_weights=self.source_weights,
        )
        return CustomerEvidenceRetrievalResult(hits=hits, state=state)

    def _empty_state(
        self,
        *,
        status: str,
        enabled: bool,
        query_present: bool,
        evidence_limit: int,
        source_types: list[str],
        error_message: str | None = None,
    ) -> CustomerEvidenceRetrievalResult:
        return CustomerEvidenceRetrievalResult(
            hits=[],
            state=EvidenceRetrievalState(
                status=status,
                enabled=enabled,
                error_message=error_message,
                query_text_present=query_present,
                requested_limit=evidence_limit,
                min_score=self.min_score,
                source_types=source_types,
                source_weights=self.source_weights,
            ),
        )

    def _evidence_hit(self, result: CustomerEvidenceSearchResult) -> CustomerEvidenceHit:
        score = float(result.score)
        return CustomerEvidenceHit(
            evidence_id=result.id,
            score=score,
            adjusted_score=score * self.source_weights.get(str(result.source_type or ""), 1.0),
            source_type=result.source_type,
            source_object_id=result.source_object_id,
            business_object_type=result.business_object_type,
            business_object_id=result.business_object_id,
            title=result.title,
            text=result.text,
        )


customer_evidence_retriever = CustomerEvidenceRetriever()

"""Retrieval strategy boundary for customer semantic evidence."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select

from app.models.deal_journey import CustomerDealJourneyEvent
from app.services.customer_activity_source_isolation import eligible_activity_source
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


@dataclass(frozen=True)
class CustomerEvidenceHit:
    evidence_id: str
    score: float
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
    ) -> None:
        self.embedding_service = embedding_service or customer_embedding_service
        self.qdrant_index_service = qdrant_index_service or customer_qdrant_index_service
        self.min_score = min_score

    def retrieve_customer_evidence(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        query_text: str | None,
        evidence_limit: int,
        source_types: Sequence[SourceType] | None = None,
        exclude_assistant2: bool = False,
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
            accepted: list[CustomerEvidenceHit] = []
            scanned = 0
            dropped = 0
            top_score: float | None = None
            window = max(evidence_limit * 3, evidence_limit)
            # Widen the window while ineligible (e.g. Assistant 2.0) hits crowd
            # it out; otherwise they would starve legitimate legacy evidence.
            while True:
                raw_results = self.qdrant_index_service.search_customer_evidence(
                    query_vector=vector,
                    tenant_id=team_id,
                    team_id=team_id,
                    customer_id=customer_id,
                    limit=window,
                    source_types=source_types,
                )
                top_score = max((item.score for item in raw_results), default=top_score)
                scanned += len(raw_results)
                for item in raw_results:
                    if item.score < self.min_score:
                        dropped += 1
                    elif not exclude_assistant2 or self._eligible_legacy_evidence(db, item, team_id, customer_id):
                        if all(hit.evidence_id != item.id for hit in accepted):
                            accepted.append(self._evidence_hit(item))
                    else:
                        dropped += 1
                if len(accepted) >= evidence_limit or len(raw_results) < window or window >= 96:
                    break
                window *= 2
            hits = sorted(accepted, key=lambda item: item.score, reverse=True)[:evidence_limit]
            retrieval_status = "ok" if hits else "low_confidence" if scanned else "empty"
            state = EvidenceRetrievalState(
                status=retrieval_status,
                enabled=True,
                query_text_present=True,
                requested_limit=evidence_limit,
                raw_count=scanned,
                returned_count=len(hits),
                dropped_count=dropped,
                top_score=top_score,
                min_score=self.min_score,
                source_types=requested_source_types,
                strategy="customer_semantic_qdrant",
            )
            return CustomerEvidenceRetrievalResult(hits=hits, state=state)
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

    @staticmethod
    def _eligible_legacy_evidence(
        db: Session, item: CustomerEvidenceSearchResult, team_id: int, customer_id: int,
    ) -> bool:
        from app.services.legacy_profile_source import source_origin

        return source_origin(
            db, team_id, customer_id, item.source_type, item.source_object_id,
            item.business_object_type, item.business_object_id,
        )

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
            ),
        )

    def _evidence_hit(self, result: CustomerEvidenceSearchResult) -> CustomerEvidenceHit:
        score = float(result.score)
        return CustomerEvidenceHit(
            evidence_id=result.id,
            score=score,
            source_type=result.source_type,
            source_object_id=result.source_object_id,
            business_object_type=result.business_object_type,
            business_object_id=result.business_object_id,
            title=result.title,
            text=result.text,
        )


customer_evidence_retriever = CustomerEvidenceRetriever()

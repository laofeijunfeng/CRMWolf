from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.sales_commitment import FollowUpTask, SalesCommitment
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

FOLLOW_UP_TASK_SEMANTIC_SOURCE_TYPES: tuple[SourceType, ...] = (
    "follow_up_task",
    "sales_commitment",
)


@dataclass(frozen=True)
class FollowUpTaskSemanticEvidenceResult:
    evidence_by_task_public_id: dict[str, list[dict[str, Any]]]
    retrieval_event: dict[str, Any]

    @property
    def task_public_ids(self) -> list[str]:
        return list(self.evidence_by_task_public_id.keys())


class FollowUpTaskSemanticEvidenceService:
    """Recall task-level semantic evidence, then map vector hits back to public task IDs."""

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
        limit: int = 50,
    ) -> FollowUpTaskSemanticEvidenceResult:
        if not self.qdrant_index_service.enabled:
            return FollowUpTaskSemanticEvidenceResult(
                evidence_by_task_public_id={},
                retrieval_event={
                    "event": "follow_up_task_semantic_evidence",
                    "status": "disabled",
                    "candidate_task_count": 0,
                },
            )

        query = query_text.strip()
        if not query:
            return FollowUpTaskSemanticEvidenceResult(
                evidence_by_task_public_id={},
                retrieval_event={
                    "event": "follow_up_task_semantic_evidence",
                    "status": "skipped_empty_query",
                    "candidate_task_count": 0,
                },
            )

        try:
            vector = self.embedding_service.embed_query(db, team_id, query)
            hits = self.qdrant_index_service.search_team_customer_evidence(
                query_vector=vector,
                tenant_id=team_id,
                team_id=team_id,
                limit=max(1, min(limit, 100)) * 4,
                source_types=FOLLOW_UP_TASK_SEMANTIC_SOURCE_TYPES,
            )
        except CustomerEmbeddingUnavailableError as exc:
            return FollowUpTaskSemanticEvidenceResult(
                evidence_by_task_public_id={},
                retrieval_event={
                    "event": "follow_up_task_semantic_evidence",
                    "status": "embedding_unavailable",
                    "candidate_task_count": 0,
                    "reason": str(exc),
                },
            )
        except Exception as exc:
            logger.info("跟进任务语义证据召回失败: team_id=%s, reason=%s", team_id, exc.__class__.__name__)
            return FollowUpTaskSemanticEvidenceResult(
                evidence_by_task_public_id={},
                retrieval_event={
                    "event": "follow_up_task_semantic_evidence",
                    "status": "failed",
                    "candidate_task_count": 0,
                    "reason": exc.__class__.__name__,
                },
            )

        evidence_by_task_public_id = self._map_hits_to_task_public_ids(db, team_id=team_id, hits=hits)
        return FollowUpTaskSemanticEvidenceResult(
            evidence_by_task_public_id=evidence_by_task_public_id,
            retrieval_event={
                "event": "follow_up_task_semantic_evidence",
                "status": "ok",
                "candidate_task_count": len(evidence_by_task_public_id),
                "hit_count": len(hits),
            },
        )

    def _map_hits_to_task_public_ids(
        self,
        db: Session,
        *,
        team_id: int,
        hits: list[CustomerEvidenceSearchResult],
    ) -> dict[str, list[dict[str, Any]]]:
        evidence_by_task_public_id: dict[str, list[dict[str, Any]]] = {}
        commitment_hits_by_public_id: dict[str, list[CustomerEvidenceSearchResult]] = {}

        for hit in hits:
            if hit.source_type == "follow_up_task":
                task_public_id = _public_id_from_hit(hit, metadata_key="task_public_id", expected_prefix="fut_")
                if task_public_id:
                    evidence_by_task_public_id.setdefault(task_public_id, []).append(_hit_evidence(hit, task_public_id))
            elif hit.source_type == "sales_commitment":
                commitment_public_id = _public_id_from_hit(
                    hit,
                    metadata_key="commitment_public_id",
                    expected_prefix="scm_",
                )
                if commitment_public_id:
                    commitment_hits_by_public_id.setdefault(commitment_public_id, []).append(hit)

        if commitment_hits_by_public_id:
            commitment_rows = (
                db.query(SalesCommitment.id, SalesCommitment.public_id)
                .filter(
                    SalesCommitment.team_id == team_id,
                    SalesCommitment.public_id.in_(list(commitment_hits_by_public_id.keys())),
                )
                .all()
            )
            commitment_public_id_by_id = {int(row.id): str(row.public_id) for row in commitment_rows}
            if commitment_public_id_by_id:
                task_rows = (
                    db.query(FollowUpTask.public_id, FollowUpTask.commitment_id)
                    .filter(
                        FollowUpTask.team_id == team_id,
                        FollowUpTask.commitment_id.in_(list(commitment_public_id_by_id.keys())),
                    )
                    .all()
                )
                for task_public_id, commitment_id in task_rows:
                    commitment_public_id = commitment_public_id_by_id.get(int(commitment_id))
                    if not commitment_public_id:
                        continue
                    for hit in commitment_hits_by_public_id.get(commitment_public_id, []):
                        evidence_by_task_public_id.setdefault(str(task_public_id), []).append(
                            _hit_evidence(hit, commitment_public_id)
                        )

        return {
            task_public_id: sorted(evidence, key=lambda item: float(item.get("score") or 0), reverse=True)[:3]
            for task_public_id, evidence in evidence_by_task_public_id.items()
        }


def _public_id_from_hit(
    hit: CustomerEvidenceSearchResult,
    *,
    metadata_key: str,
    expected_prefix: str,
) -> str | None:
    metadata = hit.metadata_json if isinstance(hit.metadata_json, dict) else {}
    for value in (
        metadata.get(metadata_key),
        hit.business_object_id,
        hit.source_object_id,
    ):
        if isinstance(value, str) and value.startswith(expected_prefix):
            return value
    return None


def _hit_evidence(hit: CustomerEvidenceSearchResult, object_public_id: str) -> dict[str, Any]:
    return {
        "source_type": hit.source_type,
        "object_public_id": object_public_id,
        "title": hit.title or "任务语义证据",
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


follow_up_task_semantic_evidence_service = FollowUpTaskSemanticEvidenceService()

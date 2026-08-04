"""Health diagnostics for the customer intelligence/RAG runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.customer_context_answer_telemetry import CustomerContextAnswerTelemetry
from app.models.customer_vector_document import CustomerVectorDocument
from app.services.customer_qdrant_index_service import customer_qdrant_index_service

QUALITY_MIN_SAMPLE_SIZE = 5
GROUNDED_RATE_DEGRADED_THRESHOLD = 0.55
GROUNDED_RATE_UNHEALTHY_THRESHOLD = 0.25
RETRIEVAL_OK_RATE_DEGRADED_THRESHOLD = 0.7
RETRIEVAL_OK_RATE_UNHEALTHY_THRESHOLD = 0.4
CITATION_COVERAGE_DEGRADED_THRESHOLD = 0.7
WEAK_ANSWER_RATE_DEGRADED_THRESHOLD = 0.45
WEAK_ANSWER_RATE_UNHEALTHY_THRESHOLD = 0.75

CRITICAL_ISSUES = {
    "embedding_api_key_missing",
    "embedding_base_url_missing",
    "embedding_qdrant_dimension_mismatch",
    "qdrant_unavailable",
    "qdrant_collection_dimension_mismatch",
}


@dataclass(frozen=True)
class CustomerIntelligenceHealthService:
    def check(self, db: Session) -> dict[str, object]:
        settings = get_settings()
        issues: list[str] = []

        api_key_configured = bool(settings.get_customer_evidence_embedding_api_key())
        base_url = settings.get_customer_evidence_embedding_base_url()
        dimensions = settings.get_customer_evidence_embedding_dimensions()
        if settings.QDRANT_ENABLED and not api_key_configured:
            issues.append("embedding_api_key_missing")
        if settings.QDRANT_ENABLED and not base_url:
            issues.append("embedding_base_url_missing")
        if dimensions != settings.QDRANT_VECTOR_SIZE:
            issues.append("embedding_qdrant_dimension_mismatch")

        qdrant_status = self._qdrant_status()
        if settings.QDRANT_ENABLED and qdrant_status.get("status") != "ok":
            issues.append("qdrant_unavailable")
        if qdrant_status.get("vector_size") not in {None, settings.QDRANT_VECTOR_SIZE}:
            issues.append("qdrant_collection_dimension_mismatch")

        sync_counts = {
            str(status): int(count)
            for status, count in db.query(
                CustomerVectorDocument.sync_status,
                func.count(CustomerVectorDocument.id),
            ).group_by(CustomerVectorDocument.sync_status).all()
        }
        if sync_counts.get("FAILED", 0) > 0:
            issues.append("vector_documents_failed")

        answer_quality = self._answer_quality_snapshot(db)
        status = _combined_status(
            _infrastructure_status(issues),
            str(answer_quality.get("status") or "insufficient_data"),
        )
        return {
            "status": status,
            "issues": issues,
            "qdrant": qdrant_status,
            "embedding": {
                "base_url": base_url,
                "model": settings.CUSTOMER_EVIDENCE_EMBEDDING_MODEL,
                "dimensions": dimensions,
                "api_key_configured": api_key_configured,
            },
            "vector_documents": {
                "sync_status_counts": sync_counts,
                "failed_count": sync_counts.get("FAILED", 0),
            },
            "answer_quality": answer_quality,
        }

    def _qdrant_status(self) -> dict[str, object]:
        settings = get_settings()
        if not settings.QDRANT_ENABLED:
            return {"status": "disabled", "enabled": False}
        try:
            collection_name = customer_qdrant_index_service.collection_name
            exists = customer_qdrant_index_service.client.collection_exists(collection_name)
            if not exists:
                return {
                    "status": "missing_collection",
                    "enabled": True,
                    "collection": collection_name,
                }
            collection = customer_qdrant_index_service.client.get_collection(collection_name)
            return {
                "status": "ok",
                "enabled": True,
                "collection": collection_name,
                "vector_size": customer_qdrant_index_service._collection_vector_size(collection),
                "points_count": customer_qdrant_index_service._collection_points_count(collection),
            }
        except Exception as exc:
            return {
                "status": "error",
                "enabled": True,
                "error_message": f"{exc.__class__.__name__}: {exc!s}",
            }

    def _answer_quality_snapshot(self, db: Session) -> dict[str, object]:
        since = datetime.utcnow() - timedelta(hours=24)
        rows = db.query(
            CustomerContextAnswerTelemetry.answer_mode,
            CustomerContextAnswerTelemetry.retrieval_status,
            func.count(CustomerContextAnswerTelemetry.id),
        ).filter(
            CustomerContextAnswerTelemetry.created_time >= since,
        ).group_by(
            CustomerContextAnswerTelemetry.answer_mode,
            CustomerContextAnswerTelemetry.retrieval_status,
        ).all()
        total = 0
        by_answer_mode: dict[str, int] = {}
        by_retrieval_status: dict[str, int] = {}
        for answer_mode, retrieval_status, count in rows:
            count_value = int(count)
            answer_mode_key = str(answer_mode or "unknown")
            retrieval_status_key = str(retrieval_status or "unknown")
            total += count_value
            by_answer_mode[answer_mode_key] = by_answer_mode.get(answer_mode_key, 0) + count_value
            by_retrieval_status[retrieval_status_key] = (
                by_retrieval_status.get(retrieval_status_key, 0) + count_value
            )
        grounded = by_answer_mode.get("grounded", 0)
        degraded = by_answer_mode.get("degraded", 0)
        fallback = by_answer_mode.get("fallback", 0)
        insufficient = by_answer_mode.get("insufficient", 0)
        weak_answers = degraded + fallback + insufficient
        retrieval_ok = by_retrieval_status.get("ok", 0)
        hard_retrieval_failures = sum(
            by_retrieval_status.get(status, 0)
            for status in ("embedding_unavailable", "failed")
        )
        grounded_with_citations = int(
            db.query(func.count(CustomerContextAnswerTelemetry.id)).filter(
                CustomerContextAnswerTelemetry.created_time >= since,
                CustomerContextAnswerTelemetry.answer_mode == "grounded",
                CustomerContextAnswerTelemetry.citation_count > 0,
            ).scalar()
            or 0
        )
        average_top_score = db.query(func.avg(CustomerContextAnswerTelemetry.top_score)).filter(
            CustomerContextAnswerTelemetry.created_time >= since,
            CustomerContextAnswerTelemetry.top_score.isnot(None),
        ).scalar()
        grounded_rate = round(grounded / total, 4) if total else None
        weak_answer_rate = round(weak_answers / total, 4) if total else None
        retrieval_ok_rate = round(retrieval_ok / total, 4) if total else None
        citation_coverage_rate = (
            round(grounded_with_citations / grounded, 4)
            if grounded
            else None
        )
        status, alerts = _answer_quality_status(
            total_answers=total,
            grounded_rate=grounded_rate,
            weak_answer_rate=weak_answer_rate,
            retrieval_ok_rate=retrieval_ok_rate,
            citation_coverage_rate=citation_coverage_rate,
            hard_retrieval_failures=hard_retrieval_failures,
        )
        return {
            "window_hours": 24,
            "total_answers": total,
            "status": status,
            "alerts": alerts,
            "by_answer_mode": by_answer_mode,
            "by_retrieval_status": by_retrieval_status,
            "grounded_rate": grounded_rate,
            "retrieval_ok_rate": retrieval_ok_rate,
            "weak_answer_rate": weak_answer_rate,
            "degraded_or_fallback_rate": weak_answer_rate,
            "citation_coverage_rate": citation_coverage_rate,
            "grounded_with_citations": grounded_with_citations,
            "average_top_score": round(float(average_top_score), 4) if average_top_score is not None else None,
        }


def _infrastructure_status(issues: list[str]) -> str:
    if any(issue in CRITICAL_ISSUES for issue in issues):
        return "unhealthy"
    if issues:
        return "degraded"
    return "healthy"


def _combined_status(*statuses: str) -> str:
    priority = {
        "unhealthy": 3,
        "degraded": 2,
        "healthy": 1,
        "insufficient_data": 0,
    }
    return max(statuses, key=lambda status: priority.get(status, 0))


def _answer_quality_status(
    *,
    total_answers: int,
    grounded_rate: float | None,
    weak_answer_rate: float | None,
    retrieval_ok_rate: float | None,
    citation_coverage_rate: float | None,
    hard_retrieval_failures: int,
) -> tuple[str, list[str]]:
    alerts: list[str] = []
    if hard_retrieval_failures:
        alerts.append("hard_retrieval_failures_observed")

    if total_answers < QUALITY_MIN_SAMPLE_SIZE:
        return "degraded" if alerts else "insufficient_data", alerts

    status = "healthy"
    if grounded_rate is not None:
        if grounded_rate < GROUNDED_RATE_UNHEALTHY_THRESHOLD:
            alerts.append("grounded_rate_critically_low")
            status = "unhealthy"
        elif grounded_rate < GROUNDED_RATE_DEGRADED_THRESHOLD:
            alerts.append("grounded_rate_low")
            status = _combined_status(status, "degraded")

    if retrieval_ok_rate is not None:
        if retrieval_ok_rate < RETRIEVAL_OK_RATE_UNHEALTHY_THRESHOLD:
            alerts.append("retrieval_ok_rate_critically_low")
            status = "unhealthy"
        elif retrieval_ok_rate < RETRIEVAL_OK_RATE_DEGRADED_THRESHOLD:
            alerts.append("retrieval_ok_rate_low")
            status = _combined_status(status, "degraded")

    if weak_answer_rate is not None:
        if weak_answer_rate > WEAK_ANSWER_RATE_UNHEALTHY_THRESHOLD:
            alerts.append("weak_answer_rate_critically_high")
            status = "unhealthy"
        elif weak_answer_rate > WEAK_ANSWER_RATE_DEGRADED_THRESHOLD:
            alerts.append("weak_answer_rate_high")
            status = _combined_status(status, "degraded")

    if (
        citation_coverage_rate is not None
        and citation_coverage_rate < CITATION_COVERAGE_DEGRADED_THRESHOLD
    ):
        alerts.append("grounded_citation_coverage_low")
        status = _combined_status(status, "degraded")

    return status, alerts


customer_intelligence_health_service = CustomerIntelligenceHealthService()

"""Persistence boundary for customer context answer quality telemetry."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.customer_context_answer_telemetry import CustomerContextAnswerTelemetry
from app.services.agent.schemas import CustomerContextAnswerResult
from app.services.agent.types import coerce_json_dict

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CustomerContextAnswerTelemetryService:
    """Records answer grounding and retrieval quality without affecting answers."""

    def record_answer(
        self,
        db: Session,
        *,
        team_id: int,
        question: str,
        customer_context: JsonObject,
        result: CustomerContextAnswerResult,
        answer_source: str,
        model: str | None = None,
        fallback_reason: str | None = None,
        fallback_error: str | None = None,
    ) -> CustomerContextAnswerTelemetry | None:
        try:
            if not callable(getattr(db, "add", None)):
                return None
            retrieval = coerce_json_dict(customer_context.get("retrieval"))
            strong_context = coerce_json_dict(customer_context.get("strong_context"))
            customer = coerce_json_dict(strong_context.get("customer"))
            telemetry = CustomerContextAnswerTelemetry(
                tenant_id=team_id,
                team_id=team_id,
                customer_id=_positive_int(customer.get("id")),
                question_text=question or None,
                answer_source=answer_source,
                answer_mode=result.answer_mode,
                model=model,
                fallback_reason=fallback_reason,
                fallback_error=fallback_error,
                retrieval_status=_optional_text(retrieval.get("status")),
                retrieval_strategy=_optional_text(retrieval.get("strategy")),
                semantic_evidence_count=_json_list_len(customer_context.get("semantic_evidence")),
                citation_count=len(result.citations or []),
                top_score=_optional_float(retrieval.get("top_score")),
                min_score=_optional_float(retrieval.get("min_score")),
                raw_count=_optional_int(retrieval.get("raw_count")),
                returned_count=_optional_int(retrieval.get("returned_count")),
                dropped_count=_optional_int(retrieval.get("dropped_count")),
                used_sections_json=list(result.used_sections or []),
                missing_context_json=list(result.missing_context or []),
                citations_json=list(result.citations or []),
                retrieval_json=retrieval,
            )
            db.add(telemetry)
            db.commit()
            db.refresh(telemetry)
            return telemetry
        except Exception as exc:
            rollback = getattr(db, "rollback", None)
            if callable(rollback):
                rollback()
            logger.warning("客户上下文回答质量遥测写入失败: %s", exc, exc_info=True)
            return None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value) if value is not None else 0
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_text(value: object) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _json_list_len(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


customer_context_answer_telemetry_service = CustomerContextAnswerTelemetryService()

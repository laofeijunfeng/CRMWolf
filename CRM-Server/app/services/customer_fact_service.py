"""Customer intelligence fact write/read boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Literal, TypeAlias

from sqlalchemy.orm import Session

from app.models.customer_fact import (
    CustomerFact,
    CustomerFactReviewAudit,
    CustomerFactRevision,
    CustomerFactRevisionType,
    CustomerFactSource,
    CustomerFactStatus,
)

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

CustomerFactType: TypeAlias = Literal[
    "alias",
    "need",
    "budget",
    "risk",
    "stage",
    "stakeholder_attitude",
    "competitor",
    "next_step",
    "preference",
    "summary",
]
CustomerFactCandidateAction: TypeAlias = Literal["upsert", "review", "ignore"]
CustomerFactReviewDecisionValue: TypeAlias = Literal["APPROVED", "REJECTED", "CANCELLED"]


@dataclass(frozen=True)
class CustomerFactSourceInput:
    source_type: str
    source_object_id: str
    business_object_type: str | None = None
    business_object_id: str | None = None
    evidence_id: str | None = None
    quote: str | None = None


@dataclass(frozen=True)
class CustomerFactInput:
    tenant_id: int
    team_id: int
    customer_id: int
    fact_type: CustomerFactType
    content: str
    subject: str | None = None
    confidence: float = 0.0
    occurred_at: datetime | None = None
    source: CustomerFactSourceInput | None = None


@dataclass(frozen=True)
class CustomerFactCandidateInput:
    fact_type: CustomerFactType
    content: str
    subject: str | None = None
    confidence: float = 0.0
    action: CustomerFactCandidateAction = "upsert"
    reason: str | None = None
    evidence_quote: str | None = None


@dataclass(frozen=True)
class CustomerFactCandidateAssessment:
    action: CustomerFactCandidateAction
    reason: str
    existing_fact_id: int | None = None
    existing_version: int | None = None
    existing_content: str | None = None
    existing_confidence: float | None = None
    conflict_reason: str | None = None


@dataclass(frozen=True)
class CustomerFactReviewAuditInput:
    tenant_id: int
    team_id: int
    customer_id: int
    event_key: str
    fact_type: CustomerFactType
    content: str
    decision: CustomerFactReviewDecisionValue
    subject: str | None = None
    confidence: float = 0.0
    reviewer_id: int | None = None
    decision_source: str | None = None
    reason: str | None = None
    conflict_reason: str | None = None
    evidence_quote: str | None = None
    fact_id: int | None = None
    existing_fact_id: int | None = None
    existing_version: int | None = None


class CustomerFactService:
    def assess_candidate_against_context(
        self,
        *,
        candidate: CustomerFactCandidateInput,
        existing_facts: list[JsonObject],
    ) -> CustomerFactCandidateAssessment:
        original_action = candidate.action
        if original_action == "ignore":
            return CustomerFactCandidateAssessment(action="ignore", reason="candidate_marked_ignore")

        content = candidate.content.strip()
        if not content:
            return CustomerFactCandidateAssessment(action="ignore", reason="empty_candidate_content")

        existing = self._matching_active_fact(candidate=candidate, existing_facts=existing_facts)
        if existing is None:
            return CustomerFactCandidateAssessment(action=original_action, reason="new_fact_candidate")

        existing_content = str(existing.get("content") or "").strip()
        existing_confidence = _json_float(existing.get("confidence"))
        existing_version = _json_int(existing.get("version")) or 1
        existing_fact_id = _json_int(existing.get("id"))
        if _normalize_content(existing_content) == _normalize_content(content):
            return CustomerFactCandidateAssessment(
                action=original_action,
                reason="same_fact_content",
                existing_fact_id=existing_fact_id,
                existing_version=existing_version,
                existing_content=existing_content,
                existing_confidence=existing_confidence,
            )

        conflict_reason = "候选事实与客户智能档案中的既有事实内容不同"
        candidate_confidence = _clamp_confidence(candidate.confidence)
        if original_action == "review":
            action: CustomerFactCandidateAction = "review"
            reason = "candidate_marked_review_with_existing_fact"
        elif candidate_confidence >= 0.88 and candidate_confidence >= existing_confidence:
            action = "upsert"
            reason = "high_confidence_replaces_existing_fact"
        else:
            action = "review"
            reason = "content_conflict_requires_review"

        return CustomerFactCandidateAssessment(
            action=action,
            reason=reason,
            existing_fact_id=existing_fact_id,
            existing_version=existing_version,
            existing_content=existing_content,
            existing_confidence=existing_confidence,
            conflict_reason=conflict_reason,
        )

    def upsert_fact(self, db: Session, fact_input: CustomerFactInput) -> CustomerFact:
        content = fact_input.content.strip()
        if not content:
            raise ValueError("客户事实内容不能为空")

        fact_key = self.fact_key(
            team_id=fact_input.team_id,
            customer_id=fact_input.customer_id,
            fact_type=fact_input.fact_type,
            subject=fact_input.subject,
        )
        fact = (
            db.query(CustomerFact)
            .filter(CustomerFact.fact_key == fact_key)
            .one_or_none()
        )
        if fact is None:
            fact = CustomerFact(
                fact_key=fact_key,
                tenant_id=fact_input.tenant_id,
                team_id=fact_input.team_id,
                customer_id=fact_input.customer_id,
                fact_type=fact_input.fact_type,
                subject=_clean_optional_text(fact_input.subject),
                content=content,
                confidence=_clamp_confidence(fact_input.confidence),
                status=CustomerFactStatus.ACTIVE,
                version=1,
                occurred_at=fact_input.occurred_at,
            )
            db.add(fact)
            db.flush()
            self._record_revision(
                db,
                fact=fact,
                change_type=CustomerFactRevisionType.CREATED,
                previous_content=None,
                previous_confidence=None,
                previous_status=None,
                previous_occurred_at=None,
                source=fact_input.source,
            )
        else:
            new_confidence = _clamp_confidence(fact_input.confidence)
            new_status = CustomerFactStatus.ACTIVE
            previous_content = str(fact.content)
            previous_confidence = float(fact.confidence or 0)
            previous_status = str(fact.status)
            previous_occurred_at = fact.occurred_at
            if _fact_changed(
                fact,
                content=content,
                confidence=new_confidence,
                status=new_status,
                occurred_at=fact_input.occurred_at,
            ):
                fact.content = content
                fact.confidence = new_confidence
                fact.status = new_status
                fact.occurred_at = fact_input.occurred_at
                fact.version = int(fact.version or 1) + 1
                db.flush()
                self._record_revision(
                    db,
                    fact=fact,
                    change_type=_revision_type(previous_status=previous_status, new_status=new_status),
                    previous_content=previous_content,
                    previous_confidence=previous_confidence,
                    previous_status=previous_status,
                    previous_occurred_at=previous_occurred_at,
                    source=fact_input.source,
                )
            else:
                db.flush()

        if fact_input.source is not None:
            self.attach_source(db, fact=fact, source=fact_input.source)
        return fact

    def record_review_decision(
        self,
        db: Session,
        audit_input: CustomerFactReviewAuditInput,
    ) -> CustomerFactReviewAudit:
        review_key = self.review_key(audit_input)
        existing = (
            db.query(CustomerFactReviewAudit)
            .filter(CustomerFactReviewAudit.review_key == review_key)
            .one_or_none()
        )
        if existing is None:
            existing = CustomerFactReviewAudit(
                review_key=review_key,
                tenant_id=audit_input.tenant_id,
                team_id=audit_input.team_id,
                customer_id=audit_input.customer_id,
                event_key=audit_input.event_key.strip(),
                fact_type=audit_input.fact_type,
                subject=_clean_optional_text(audit_input.subject),
                candidate_content=audit_input.content.strip(),
                candidate_confidence=_clamp_confidence(audit_input.confidence),
                decision=audit_input.decision,
            )
            db.add(existing)

        existing.fact_id = audit_input.fact_id
        existing.existing_fact_id = audit_input.existing_fact_id
        existing.existing_version = audit_input.existing_version
        existing.decision_source = _clean_optional_text(audit_input.decision_source)
        existing.reviewer_id = audit_input.reviewer_id
        existing.reason = _clean_optional_text(audit_input.reason)
        existing.conflict_reason = _clean_optional_text(audit_input.conflict_reason)
        existing.evidence_quote = _clean_optional_text(audit_input.evidence_quote)
        db.flush()
        return existing

    def _record_revision(
        self,
        db: Session,
        *,
        fact: CustomerFact,
        change_type: str,
        previous_content: str | None,
        previous_confidence: float | None,
        previous_status: str | None,
        previous_occurred_at: datetime | None,
        source: CustomerFactSourceInput | None,
    ) -> CustomerFactRevision:
        revision = CustomerFactRevision(
            fact_id=fact.id,
            version=int(fact.version or 1),
            change_type=change_type,
            previous_content=previous_content,
            new_content=str(fact.content),
            previous_confidence=previous_confidence,
            new_confidence=float(fact.confidence or 0),
            previous_status=previous_status,
            new_status=str(fact.status),
            previous_occurred_at=previous_occurred_at,
            new_occurred_at=fact.occurred_at,
            source_type=_clean_optional_text(source.source_type) if source is not None else None,
            source_object_id=_clean_optional_text(source.source_object_id) if source is not None else None,
            business_object_type=_clean_optional_text(source.business_object_type) if source is not None else None,
            business_object_id=_clean_optional_text(source.business_object_id) if source is not None else None,
            evidence_id=_clean_optional_text(source.evidence_id) if source is not None else None,
            quote=_clean_optional_text(source.quote) if source is not None else None,
        )
        db.add(revision)
        db.flush()
        return revision

    def attach_source(self, db: Session, *, fact: CustomerFact, source: CustomerFactSourceInput) -> CustomerFactSource:
        source_object_id = source.source_object_id.strip()
        if not source.source_type.strip() or not source_object_id:
            raise ValueError("客户事实来源缺少必要信息")
        existing = (
            db.query(CustomerFactSource)
            .filter(
                CustomerFactSource.fact_id == fact.id,
                CustomerFactSource.source_type == source.source_type,
                CustomerFactSource.source_object_id == source_object_id,
            )
            .one_or_none()
        )
        if existing is not None:
            existing.business_object_type = _clean_optional_text(source.business_object_type)
            existing.business_object_id = _clean_optional_text(source.business_object_id)
            existing.evidence_id = _clean_optional_text(source.evidence_id)
            existing.quote = _clean_optional_text(source.quote)
            db.flush()
            return existing

        fact_source = CustomerFactSource(
            fact_id=fact.id,
            source_type=source.source_type.strip(),
            source_object_id=source_object_id,
            business_object_type=_clean_optional_text(source.business_object_type),
            business_object_id=_clean_optional_text(source.business_object_id),
            evidence_id=_clean_optional_text(source.evidence_id),
            quote=_clean_optional_text(source.quote),
        )
        db.add(fact_source)
        db.flush()
        return fact_source

    def list_active_facts(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        limit: int = 50,
    ) -> list[CustomerFact]:
        return (
            db.query(CustomerFact)
            .filter(
                CustomerFact.team_id == team_id,
                CustomerFact.customer_id == customer_id,
                CustomerFact.status == CustomerFactStatus.ACTIVE,
            )
            .order_by(CustomerFact.confidence.desc(), CustomerFact.occurred_at.desc(), CustomerFact.updated_time.desc())
            .limit(limit)
            .all()
        )

    def list_sources(self, db: Session, *, fact_ids: list[int]) -> dict[int, list[CustomerFactSource]]:
        if not fact_ids:
            return {}
        sources = (
            db.query(CustomerFactSource)
            .filter(CustomerFactSource.fact_id.in_(fact_ids))
            .order_by(CustomerFactSource.created_time.asc())
            .all()
        )
        grouped: dict[int, list[CustomerFactSource]] = {}
        for source in sources:
            grouped.setdefault(int(source.fact_id), []).append(source)
        return grouped

    def to_context_payload(self, db: Session, *, team_id: int, customer_id: int, limit: int = 50) -> list[JsonObject]:
        facts = self.list_active_facts(db, team_id=team_id, customer_id=customer_id, limit=limit)
        sources_by_fact = self.list_sources(db, fact_ids=[int(fact.id) for fact in facts])
        return [
            _fact_payload(fact, sources_by_fact.get(int(fact.id), []))
            for fact in facts
        ]

    def fact_key(self, *, team_id: int, customer_id: int, fact_type: str, subject: str | None) -> str:
        raw = f"crmwolf/customer-fact/{team_id}/{customer_id}/{fact_type}/{_clean_optional_text(subject) or ''}"
        return sha256(raw.encode("utf-8")).hexdigest()

    def review_key(self, audit_input: CustomerFactReviewAuditInput) -> str:
        raw = (
            "crmwolf/customer-fact-review/"
            f"{audit_input.team_id}/{audit_input.customer_id}/{audit_input.event_key.strip()}/"
            f"{audit_input.fact_type}/{_clean_optional_text(audit_input.subject) or ''}/"
            f"{_normalize_content(audit_input.content)}/{audit_input.decision}"
        )
        return sha256(raw.encode("utf-8")).hexdigest()

    def _matching_active_fact(
        self,
        *,
        candidate: CustomerFactCandidateInput,
        existing_facts: list[JsonObject],
    ) -> JsonObject | None:
        candidate_subject = _normalize_subject(candidate.subject)
        for fact in existing_facts:
            if str(fact.get("status") or CustomerFactStatus.ACTIVE) != CustomerFactStatus.ACTIVE:
                continue
            if str(fact.get("fact_type") or "") != candidate.fact_type:
                continue
            if _normalize_subject(fact.get("subject")) == candidate_subject:
                return fact
        return None


def _fact_payload(fact: CustomerFact, sources: list[CustomerFactSource]) -> JsonObject:
    return {
        "id": int(fact.id),
        "fact_type": str(fact.fact_type),
        "subject": fact.subject,
        "content": str(fact.content),
        "confidence": float(fact.confidence or 0),
        "status": str(fact.status),
        "version": int(fact.version or 1),
        "occurred_at": fact.occurred_at.isoformat() if fact.occurred_at else None,
        "extracted_at": fact.extracted_at.isoformat() if fact.extracted_at else None,
        "sources": [_source_payload(source) for source in sources],
    }


def _source_payload(source: CustomerFactSource) -> JsonObject:
    return {
        "source_type": str(source.source_type),
        "source_object_id": str(source.source_object_id),
        "business_object_type": source.business_object_type,
        "business_object_id": source.business_object_id,
        "evidence_id": source.evidence_id,
        "quote": source.quote,
    }


def _clean_optional_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _normalize_subject(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _normalize_content(value: str) -> str:
    return "".join(value.strip().split()).lower()


def _json_float(value: JsonValue) -> float:
    if isinstance(value, int | float):
        return _clamp_confidence(float(value))
    if isinstance(value, str):
        try:
            return _clamp_confidence(float(value.strip()))
        except ValueError:
            return 0.0
    return 0.0


def _json_int(value: JsonValue) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _fact_changed(
    fact: CustomerFact,
    *,
    content: str,
    confidence: float,
    status: str,
    occurred_at: datetime | None,
) -> bool:
    return (
        str(fact.content) != content
        or float(fact.confidence or 0) != confidence
        or str(fact.status) != status
        or fact.occurred_at != occurred_at
    )


def _revision_type(*, previous_status: str, new_status: str) -> str:
    if previous_status != CustomerFactStatus.ACTIVE and new_status == CustomerFactStatus.ACTIVE:
        return CustomerFactRevisionType.REACTIVATED
    return CustomerFactRevisionType.UPDATED


customer_fact_service = CustomerFactService()

"""Resolve profile evidence references back to permission-scoped CRM records.

A published profile stores references, not a copy of every source record.  This
resolver is the read-time boundary that turns those references into safe,
clickable evidence.  Missing or no-longer-visible records are represented as
unavailable items instead of failing the whole profile response.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import quote

from app.models.customer_activity import CustomerActivity
from app.models.customer_fact import CustomerFact
from app.models.deal_journey import CustomerDealJourneyEvent
from app.models.sales_commitment import FollowUpTask, SalesCommitment

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class CustomerProfileResolvedEvidence:
    evidence_key: str
    source_type: str
    source_id: str | None
    source_version: int | str | None
    occurred_at: datetime | str | None
    title: str | None
    snippet: str | None
    visibility: str
    availability: str
    link: str | None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_key": self.evidence_key,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "source_version": self.source_version,
            "occurred_at": self.occurred_at,
            "title": self.title,
            "snippet": self.snippet,
            "visibility": self.visibility,
            "availability": self.availability,
            "link": self.link,
            "reason": self.reason,
        }


class CustomerProfileEvidenceResolver:
    """Resolve only records belonging to the requested team and customer."""

    def resolve_registry(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        customer_public_id: str,
        registry: Sequence[Mapping[str, object]],
    ) -> list[dict[str, object]]:
        return [
            self.resolve_one(
                db,
                team_id=team_id,
                customer_id=customer_id,
                customer_public_id=customer_public_id,
                reference=reference,
            ).to_dict()
            for reference in registry
            if isinstance(reference, Mapping)
        ]

    def resolve_one(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        customer_public_id: str,
        reference: Mapping[str, object],
    ) -> CustomerProfileResolvedEvidence:
        key = _text(reference.get("evidence_key") or reference.get("evidence_id") or reference.get("id"))
        source_type = _text(reference.get("source_type")) or "unknown"
        source_id = _string_id(reference.get("source_id"))
        source_version = _source_version(reference.get("source_version"))
        fallback = self._fallback(
            reference,
            key=key,
            source_type=source_type,
            source_id=source_id,
            source_version=source_version,
        )
        if not key:
            return fallback

        kind = source_type.lower()
        if kind in {"customer_activity", "activity"}:
            row = _query_by_id(db, CustomerActivity, team_id, customer_id, source_id)
            if row is None:
                return fallback
            return _available(
                key,
                source_type,
                source_id,
                source_version=source_version,
                occurred_at=row.occurred_at,
                title=row.title or row.activity_kind,
                snippet=row.source_content or row.summary,
                link=_link(customer_public_id, "activity", source_id),
            )
        if kind in {"deal_journey_event", "journey_event"}:
            row = _query_by_id(db, CustomerDealJourneyEvent, team_id, customer_id, source_id)
            if row is None:
                return fallback
            return _available(
                key,
                source_type,
                source_id,
                source_version=source_version,
                occurred_at=row.event_time,
                title=row.event_type,
                snippet=row.summary,
                link=_link(customer_public_id, "journey-event", source_id),
            )
        if kind in {"follow_up_task", "task"}:
            row = _query_by_id(db, FollowUpTask, team_id, customer_id, source_id)
            if row is None:
                return fallback
            return _available(
                key,
                source_type,
                source_id,
                source_version=source_version,
                occurred_at=row.updated_time or row.due_at,
                title=row.title,
                snippet=row.description,
                link=_link(customer_public_id, "follow-up-task", source_id),
            )
        if kind in {"sales_commitment", "commitment"}:
            row = _query_by_id(db, SalesCommitment, team_id, customer_id, source_id)
            if row is None:
                return fallback
            return _available(
                key,
                source_type,
                source_id,
                source_version=source_version,
                occurred_at=row.updated_time or row.due_at,
                title=row.title,
                snippet=row.content,
                link=_link(customer_public_id, "sales-commitment", source_id),
            )
        if kind in {"customer_fact", "fact"}:
            row = _query_by_id(db, CustomerFact, team_id, customer_id, source_id)
            if row is None:
                return fallback
            return _available(
                key,
                source_type,
                source_id,
                source_version=source_version,
                occurred_at=row.occurred_at or row.updated_time,
                title=row.fact_type,
                snippet=row.content,
                link=_link(customer_public_id, "fact", source_id),
            )
        return fallback

    def _fallback(
        self,
        reference: Mapping[str, object],
        *,
        key: str,
        source_type: str,
        source_id: str | None,
        source_version: int | str | None,
    ) -> CustomerProfileResolvedEvidence:
        return CustomerProfileResolvedEvidence(
            evidence_key=key,
            source_type=source_type,
            source_id=source_id,
            source_version=source_version,
            occurred_at=(
                reference.get("occurred_at")
                if isinstance(reference.get("occurred_at"), (str, datetime))
                else None
            ),
            title="原始记录不可用",
            snippet=None,
            visibility="UNAVAILABLE",
            availability="UNAVAILABLE",
            link=None,
            reason="原始记录已删除、撤回或当前用户无权访问。",
        )


customer_profile_evidence_resolver = CustomerProfileEvidenceResolver()


def _query_by_id(db: Session, model: type, team_id: int, customer_id: int, source_id: str | None) -> object | None:
    if source_id is None or not source_id.isdigit():
        return None
    return (
        db.query(model)
        .filter(model.id == int(source_id), model.team_id == team_id, model.customer_id == customer_id)
        .one_or_none()
    )


def _available(
    key: str,
    source_type: str,
    source_id: str | None,
    *,
    source_version: int | str | None = None,
    occurred_at: datetime | str | None,
    title: object,
    snippet: object,
    link: str,
) -> CustomerProfileResolvedEvidence:
    return CustomerProfileResolvedEvidence(
        evidence_key=key,
        source_type=source_type,
        source_id=source_id,
        source_version=source_version,
        occurred_at=occurred_at,
        title=_optional_text(title),
        snippet=_optional_text(snippet),
        visibility="VISIBLE",
        availability="AVAILABLE",
        link=link,
    )


def _link(customer_public_id: str, kind: str, source_id: str | None) -> str:
    encoded_customer = quote(customer_public_id, safe="")
    encoded_kind = quote(kind, safe="")
    encoded_source = quote(source_id or "", safe="")
    return (
        f"/customers/{encoded_customer}?profile_evidence_type={encoded_kind}"
        f"&profile_evidence_id={encoded_source}"
    )


def _source_version(value: object) -> int | str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    return text or None


def _string_id(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _text(value: object, *, limit: int = 160) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit].strip()


def _optional_text(value: object) -> str | None:
    text = _text(value, limit=800)
    return text or None

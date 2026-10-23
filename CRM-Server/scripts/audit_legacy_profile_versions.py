"""Offline, read-only inventory of immutable legacy profile bodies and citations.

The output is aggregate-only. A signed publication proves authenticity, not that a
historical body was free of private source text; bodies without a source-level
reconstruction remain unproven even when no direct copied text is detected.
Delete this migration inventory after the release gate is complete.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_fact import CustomerFact
from app.models.customer_profile_projection import CustomerProfileCurrent, CustomerProfileProjectionVersion
from app.models.deal_journey import CustomerDealJourneyEvent
from app.models.sales_commitment import FollowUpTask, SalesCommitment
from app.models.team import Team
from app.services.legacy_profile_source import activity_origin, event_origin, fact_origin, follow_up_origin

_BATCH = 200
_SECTIONS = (
    "current_situation_json", "current_journeys_json", "important_changes_json",
    "long_term_context_json", "follow_up_process_json", "recorded_follow_ups_json",
)


def _pages(db: Session, model: type) -> Iterator[object]:
    last_id = 0
    while True:
        rows = db.query(model).filter(model.id > last_id).order_by(model.id).limit(_BATCH).all()
        if not rows:
            return
        yield from rows
        last_id = int(rows[-1].id)
        db.expunge_all()


def _citation_available(db: Session, *, team_id: int, customer_id: int, reference: dict[str, object]) -> bool:
    """Recheck live, scoped records only; cached availability is not evidence."""
    key = reference.get("evidence_key") or reference.get("evidence_id") or reference.get("id")
    if not isinstance(key, str) or not key.strip():
        return False
    source_id = str(reference.get("source_id") or "")
    if not source_id.isdecimal() or int(source_id) <= 0 or str(int(source_id)) != source_id:
        return False
    kind = str(reference.get("source_type") or "").lower()
    models = {
        "customer_activity": CustomerActivity, "activity": CustomerActivity,
        "deal_journey_event": CustomerDealJourneyEvent, "journey_event": CustomerDealJourneyEvent,
        "follow_up_task": FollowUpTask, "task": FollowUpTask,
        "sales_commitment": SalesCommitment, "commitment": SalesCommitment,
        "customer_fact": CustomerFact, "fact": CustomerFact,
    }
    model = models.get(kind)
    if model is None:
        return False
    row = db.query(model).filter_by(id=int(source_id), team_id=team_id, customer_id=customer_id).one_or_none()
    if isinstance(row, CustomerActivity):
        return activity_origin(db, team_id, customer_id, row.id)
    if isinstance(row, CustomerDealJourneyEvent):
        return event_origin(db, row, team_id, customer_id)
    if isinstance(row, FollowUpTask | SalesCommitment):
        return follow_up_origin(db, row, team_id, customer_id)
    return isinstance(row, CustomerFact) and fact_origin(db, row, team_id, customer_id)


def audit_versions(db: Session) -> dict[str, int]:
    """Count evidence without exporting identifiers, profile text, or source snippets.

    The caller must supply a snapshot-bound, read-only session. The function
    performs no writes; unreadable ownership and references fail closed.
    """
    counts = {
        "versions": 0, "uncertified_versions": 0, "unowned_versions": 0,
        "body_matches_assistant2_source": 0, "body_unproven_versions": 0,
        "available_citations": 0, "unavailable_citations": 0,
        "current_pointers": 0, "invalid_current_pointers": 0, "blocking_versions": 0,
    }
    for version in _pages(db, CustomerProfileProjectionVersion):
        counts["versions"] += 1
        team_id, customer_id = int(version.team_id), int(version.customer_id)
        if (db.query(Team.id).filter_by(id=team_id).one_or_none() is None
                or db.query(Customer.id).filter_by(id=customer_id, team_id=team_id).one_or_none() is None):
            counts["unowned_versions"] += 1
            counts["blocking_versions"] += 1
            continue
        # The retired publication verifier is intentionally unavailable. This
        # inventory cannot authenticate historical attestations or bless bodies.
        counts["uncertified_versions"] += 1
        blocked = True
        sections = [getattr(version, name) for name in _SECTIONS]
        body = json.dumps(sections, ensure_ascii=False, sort_keys=True, default=str).casefold()
        # A current source snapshot cannot certify the *historical* body. Even
        # if no exact match is found, do not mark that text clean by absence.
        if any(sections):
            counts["body_unproven_versions"] += 1
            blocked = True
        sources = db.query(CustomerActivity.source_content).filter_by(
            team_id=team_id, customer_id=customer_id, submission_source="ASSISTANT_2",
        ).all()
        if any((text := str(row[0] or "").strip()) and len(text) >= 16
               and text.casefold() in body for row in sources):
            counts["body_matches_assistant2_source"] += 1
            blocked = True
        refs = version.evidence_refs_json
        if not isinstance(refs, list):
            counts["unavailable_citations"] += 1
            blocked = True
        else:
            for ref in refs:
                if not isinstance(ref, dict):
                    counts["unavailable_citations"] += 1
                    blocked = True
                    continue
                if _citation_available(db, team_id=team_id, customer_id=customer_id, reference=ref):
                    counts["available_citations"] += 1
                else:
                    counts["unavailable_citations"] += 1
                    blocked = True
        if blocked:
            counts["blocking_versions"] += 1
    for current in _pages(db, CustomerProfileCurrent):
        counts["current_pointers"] += 1
        team_id, customer_id = int(current.team_id), int(current.customer_id)
        if (db.query(Team.id).filter_by(id=team_id).one_or_none() is None
                or db.query(Customer.id).filter_by(id=customer_id, team_id=team_id).one_or_none() is None):
            counts["invalid_current_pointers"] += 1
            continue
        if current.current_profile_version_id is not None and db.query(CustomerProfileProjectionVersion.id).filter_by(
            id=current.current_profile_version_id, team_id=team_id, customer_id=customer_id,
        ).one_or_none() is None:
            counts["invalid_current_pointers"] += 1
    return counts


def main() -> int:
    # Production snapshots must use a SELECT-only account in addition to this
    # read-only, repeatable-read transaction. No API or runtime imports this CLI.
    if engine.dialect.name != "mysql":
        print(json.dumps({"status": "blocked", "reason": "mysql_required"}))
        return 2
    try:
        with SessionLocal() as db:
            db.connection().exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            db.connection().exec_driver_sql("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")
            try:
                counts = audit_versions(db)
            finally:
                db.rollback()
    except Exception:
        # DB exceptions can contain bound business values: never print them.
        print(json.dumps({"status": "blocked", "reason": "audit_error"}))
        return 2
    print(json.dumps(counts, sort_keys=True))
    return 2 if counts["blocking_versions"] or counts["invalid_current_pointers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

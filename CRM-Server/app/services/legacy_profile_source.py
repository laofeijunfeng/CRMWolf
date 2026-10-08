"""Fail-closed provenance tracing for the legacy customer intelligence read side."""

from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone
from app.models.customer_fact import CustomerFact, CustomerFactSource
from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent
from app.models.sales_commitment import FollowUpTask, FollowUpTaskEvent, SalesCommitment
from app.models.opportunity import Opportunity
from app.models.contract import Contract
from app.models.payment import PaymentPlan, PaymentRecord
from app.models.procurement import OpportunityStageSnapshot
from app.models.invoice import InvoiceApplication
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress

LEGACY_PROFILE_SOURCE_POLICY = "LEGACY_PROFILE_ELIGIBLE_V1"
LEGACY_ACTIVITY_SOURCES = frozenset({"FORM", "AGENT", "CUTOVER_MIGRATION"})


def _activity_source_status(db: Session, team_id: int, customer_id: int, activity_id: object) -> str:
    if activity_origin(db, team_id, customer_id, activity_id):
        return "VERIFIED"
    if not str(activity_id or "").isdecimal() or int(str(activity_id)) <= 0:
        return "UNKNOWN"
    identifier = int(str(activity_id))
    live = db.query(CustomerActivity.submission_source).filter_by(
        id=identifier, team_id=team_id, customer_id=customer_id,
    ).one_or_none()
    deleted = db.query(CustomerActivityDeletionTombstone.submission_source).filter_by(
        activity_id=identifier, team_id=team_id, customer_id=customer_id,
    ).one_or_none()
    origins = [row[0] for row in (live, deleted) if row is not None]
    return "EXCLUDED" if origins == ["ASSISTANT_2"] else "UNKNOWN"


def event_source_status(db: Session, event: CustomerDealJourneyEvent, team_id: int, customer_id: int) -> str:
    """Only an explicit Assistant 2.0 origin may be silently excluded."""
    if event_origin(db, event, team_id, customer_id):
        return "VERIFIED"
    if event.team_id != team_id or event.customer_id != customer_id:
        return "UNKNOWN"
    if event.source_type in {"customer_activity", "customer_follow_up"}:
        return _activity_source_status(db, team_id, customer_id, event.source_id)
    return "VERIFIED" if _business_origin(db, team_id, customer_id, event.source_type, event.source_id) else "UNKNOWN"


def follow_up_source_status(db: Session, row: FollowUpTask | SalesCommitment, team_id: int, customer_id: int) -> str:
    if follow_up_origin(db, row, team_id, customer_id):
        return "VERIFIED"
    if row.team_id != team_id or row.customer_id != customer_id or row.source_public_id is not None:
        return "UNKNOWN"
    kind, key = str(row.source_type or "").lower(), str(row.source_key or "")
    if kind == "sales_commitment" and isinstance(row, FollowUpTask) and key.startswith("commitment:"):
        identifier = key.removeprefix("commitment:")
        if not identifier.isdecimal() or int(identifier) <= 0 or str(int(identifier)) != identifier:
            return "UNKNOWN"
        if row.source_activity_id is not None or (row.commitment_id is not None and row.commitment_id != int(identifier)):
            return "UNKNOWN"
        commitment = db.query(SalesCommitment).filter_by(
            id=int(identifier), team_id=team_id, customer_id=customer_id,
        ).one_or_none()
        return follow_up_source_status(db, commitment, team_id, customer_id) if commitment is not None else "UNKNOWN"
    if kind != "customer_activity" or not key.startswith("activity:"):
        return "UNKNOWN"
    identifier = key.removeprefix("activity:")
    if not identifier.isdecimal() or int(identifier) <= 0 or str(int(identifier)) != identifier:
        return "UNKNOWN"
    if row.source_activity_id is not None and str(row.source_activity_id) != identifier:
        return "UNKNOWN"
    if isinstance(row, FollowUpTask) and row.commitment_id is not None:
        commitment = db.query(SalesCommitment).filter_by(
            id=row.commitment_id, team_id=team_id, customer_id=customer_id,
        ).one_or_none()
        if commitment is None or commitment.source_type.lower() != kind or commitment.source_key != key:
            return "UNKNOWN"
        if follow_up_source_status(db, commitment, team_id, customer_id) != "EXCLUDED":
            return "UNKNOWN"
    origin = _activity_source_status(db, team_id, customer_id, identifier)
    return "EXCLUDED" if origin == "EXCLUDED" else "UNKNOWN"


def task_event_source_status(
    db: Session, event: FollowUpTaskEvent, task: FollowUpTask, team_id: int, customer_id: int,
) -> str:
    """A task event cannot borrow a different activity's eligible origin."""
    if event.team_id != team_id or event.task_id != task.id or event.source_public_id != task.source_public_id:
        return "UNKNOWN"
    if event.source_type != task.source_type:
        return "UNKNOWN"
    kind, key = str(task.source_type or "").lower(), str(task.source_key or "")
    if kind == "customer_activity":
        if not key.startswith("activity:"):
            return "UNKNOWN"
        activity_id = key.removeprefix("activity:")
        if not activity_id.isdecimal() or int(activity_id) <= 0 or str(int(activity_id)) != activity_id:
            return "UNKNOWN"
        if str(event.source_activity_id) != activity_id:
            # Deleting an activity SET NULLs the task FK. The event records the
            # same NULL, while the old tombstone still authenticates source_key.
            if event.source_activity_id is not None or task.source_activity_id is not None:
                return "UNKNOWN"
            if db.query(CustomerActivityDeletionTombstone.id).filter_by(
                activity_id=int(activity_id), team_id=team_id, customer_id=customer_id,
            ).one_or_none() is None:
                return "UNKNOWN"
    elif kind == "sales_commitment":
        if event.source_activity_id is not None:
            return "UNKNOWN"
    else:
        return "UNKNOWN"
    return follow_up_source_status(db, task, team_id, customer_id)


def source_status(
    db: Session, team_id: int, customer_id: int, source_type: object, source_id: object,
    business_type: object = None, business_id: object = None,
) -> str:
    kind = str(source_type or "").lower()
    if kind in {"customer_activity", "follow_up", "customer_follow_up"}:
        origin = _activity_source_status(db, team_id, customer_id, source_id)
    elif kind in {"deal_journey_event", "business_flow"} and str(source_id or "").isdecimal():
        event = db.query(CustomerDealJourneyEvent).filter_by(
            id=int(source_id), team_id=team_id, customer_id=customer_id,
        ).one_or_none()
        origin = event_source_status(db, event, team_id, customer_id) if event is not None else "UNKNOWN"
    elif kind in {"follow_up_task", "task", "sales_commitment", "commitment"} and str(source_id or "").isdecimal():
        model = FollowUpTask if kind in {"follow_up_task", "task"} else SalesCommitment
        row = db.query(model).filter_by(id=int(source_id), team_id=team_id, customer_id=customer_id).one_or_none()
        origin = follow_up_source_status(db, row, team_id, customer_id) if row is not None else "UNKNOWN"
    elif kind == "follow_up_task_event" and str(source_id or "").isdecimal():
        event = db.query(FollowUpTaskEvent).filter_by(id=int(source_id), team_id=team_id).one_or_none()
        task = db.query(FollowUpTask).filter_by(id=event.task_id, team_id=team_id, customer_id=customer_id).one_or_none() if event is not None else None
        origin = task_event_source_status(db, event, task, team_id, customer_id) if task is not None else "UNKNOWN"
    else:
        origin = "VERIFIED" if _business_origin(db, team_id, customer_id, kind, source_id) else "UNKNOWN"
    if origin == "UNKNOWN":
        return origin
    if business_type is None and business_id is None:
        return origin
    if not _source_hint_matches(db, team_id, customer_id, kind, source_id, business_type, business_id):
        return "UNKNOWN"
    return origin


def _source_hint_matches(
    db: Session, team_id: int, customer_id: int, kind: str, source_id: object,
    business_type: object, business_id: object,
) -> bool:
    """Both hints must describe the *same* source, not merely two eligible rows."""
    business_kind = str(business_type or "").lower()
    if not business_kind or business_id is None:
        return False
    aliases = ({"customer_activity", "follow_up", "customer_follow_up"},
               {"deal_journey_event", "business_flow"}, {"follow_up_task", "task"},
               {"sales_commitment", "commitment"})
    if any(kind in group and business_kind in group for group in aliases):
        return str(source_id) == str(business_id)
    if kind == business_kind:
        return str(source_id) == str(business_id)
    if kind in {"deal_journey_event", "business_flow"} and str(source_id or "").isdecimal():
        event = db.query(CustomerDealJourneyEvent).filter_by(
            id=int(source_id), team_id=team_id, customer_id=customer_id,
        ).one_or_none()
        return (event is not None and business_kind == str(event.source_type or "").lower()
                and str(business_id) == str(event.source_id))
    if kind == "follow_up_task_event" and business_kind in {"follow_up_task", "task"}:
        event = db.query(FollowUpTaskEvent.task_id).filter_by(
            id=int(source_id), team_id=team_id,
        ).one_or_none() if str(source_id or "").isdecimal() else None
        return event is not None and str(business_id) == str(event[0])
    return False


def fact_source_status(db: Session, fact: CustomerFact, team_id: int, customer_id: int) -> str:
    if fact.team_id != team_id or fact.customer_id != customer_id:
        return "UNKNOWN"
    sources = db.query(CustomerFactSource).filter_by(fact_id=fact.id).all()
    if not sources:
        return "UNKNOWN"
    statuses = [source_status(db, team_id, customer_id, source.source_type, source.source_object_id,
                              source.business_object_type, source.business_object_id) for source in sources]
    if "UNKNOWN" in statuses:
        return "UNKNOWN"
    return statuses[0] if len(set(statuses)) == 1 else "UNKNOWN"


def trace_customer_source_provenance(db: Session, *, team_id: int, customer_id: int) -> bool:
    """Inspect every derived source, including rows excluded from the legacy view.

    Call under the Team -> Customer publication fence. Progress and a snapshot
    hash alone are not evidence that the underlying chains still exist.
    """
    activities = db.query(CustomerActivity).filter_by(team_id=team_id, customer_id=customer_id).all()
    deletions = db.query(CustomerActivityDeletionTombstone).filter_by(team_id=team_id, customer_id=customer_id).all()
    origins: dict[int, list[str]] = {}
    for row in activities:
        origins.setdefault(int(row.id), []).append(str(row.submission_source))
    for row in deletions:
        origins.setdefault(int(row.activity_id), []).append(str(row.submission_source))
    if any(len(values) != 1 or values[0] not in (*LEGACY_ACTIVITY_SOURCES, "ASSISTANT_2")
           for values in origins.values()):
        return False

    events = db.query(CustomerDealJourneyEvent).filter_by(team_id=team_id, customer_id=customer_id).all()
    for row in events:
        if event_source_status(db, row, team_id, customer_id) == "UNKNOWN":
            return False
    journeys = db.query(CustomerDealJourney.id).filter_by(team_id=team_id, customer_id=customer_id).all()
    journey_ids = {int(row[0]) for row in journeys}
    for row in events:
        if row.deal_journey_id not in journey_ids:
            return False

    commitments = db.query(SalesCommitment).filter_by(team_id=team_id, customer_id=customer_id).all()
    tasks = db.query(FollowUpTask).filter_by(team_id=team_id, customer_id=customer_id).all()
    if any(follow_up_source_status(db, row, team_id, customer_id) == "UNKNOWN" for row in [*commitments, *tasks]):
        return False
    task_by_id = {int(row.id): row for row in tasks}
    if tasks:
        events = db.query(FollowUpTaskEvent).filter(
            FollowUpTaskEvent.team_id == team_id,
            FollowUpTaskEvent.task_id.in_(task_by_id),
        ).all()
        for row in events:
            task = task_by_id.get(int(row.task_id))
            if task is None or task_event_source_status(db, row, task, team_id, customer_id) == "UNKNOWN":
                return False

    facts = db.query(CustomerFact).filter_by(team_id=team_id, customer_id=customer_id).all()
    return all(fact_source_status(db, fact, team_id, customer_id) != "UNKNOWN" for fact in facts)


def lock_source_customer(db: Session, *, team_id: int, customer_id: int) -> Customer:
    """Serialize an eligible source writer with publication on the customer row."""
    with db.no_autoflush:
        return db.query(Customer).filter_by(id=customer_id, team_id=team_id).with_for_update().one()


def advance_eligible_progress(
    db: Session, *, team_id: int, customer_id: int, deleted: bool = False, count: int = 1,
) -> None:
    """Advance progress while holding the customer's write lock in this transaction."""
    if count <= 0:
        return
    customer = lock_source_customer(db, team_id=team_id, customer_id=customer_id)
    with db.no_autoflush:
        existing = db.query(CustomerLegacySourceProgress.id).filter_by(
            customer_id=customer.id, team_id=team_id,
        ).one_or_none()
        if existing is None:
            # An absent SELECT FOR UPDATE takes a next-key gap lock. Two
            # unrelated customers inserting into that gap can deadlock.
            # Materialize the row first; the customer lock serializes same-key writers.
            if db.get_bind().dialect.name == "mysql":
                statement = mysql_insert(CustomerLegacySourceProgress).values(
                    team_id=team_id, customer_id=customer_id,
                ).on_duplicate_key_update(id=CustomerLegacySourceProgress.id)
                db.execute(statement)
            else:
                db.add(CustomerLegacySourceProgress(team_id=team_id, customer_id=customer_id))
                db.flush()
        progress = db.query(CustomerLegacySourceProgress).filter_by(
            customer_id=customer.id, team_id=team_id,
        ).populate_existing().with_for_update().one()
    progress.eligible_revision = int(progress.eligible_revision or 0) + count
    if deleted:
        progress.deletion_revision = int(progress.deletion_revision or 0) + count
    db.flush()


def advance_activity_progress(
    db: Session, *, team_id: int, customer_id: int, submission_source: str,
    deleted: bool = False, count: int = 1,
) -> None:
    """Advance an eligible activity in its source transaction; exclude ASSISTANT_2."""
    if submission_source in LEGACY_ACTIVITY_SOURCES:
        advance_eligible_progress(db, team_id=team_id, customer_id=customer_id, deleted=deleted, count=count)


def activity_origin(db: Session, team_id: int, customer_id: int, activity_id: object, *, current: bool = False) -> bool:
    """A missing or conflicting origin never grants access to legacy intelligence."""
    try:
        identifier = int(activity_id)
        if identifier <= 0 or str(identifier) != str(activity_id):
            return False
    except (TypeError, ValueError):
        return False
    live_query = db.query(CustomerActivity.submission_source).filter_by(
        id=identifier, team_id=team_id, customer_id=customer_id
    )
    deleted_query = db.query(CustomerActivityDeletionTombstone.submission_source).filter_by(
        activity_id=identifier, team_id=team_id, customer_id=customer_id
    )
    if current:
        live_query = live_query.with_for_update()
        deleted_query = deleted_query.with_for_update()
    live = live_query.one_or_none()
    deleted = deleted_query.one_or_none()
    origins = [row[0] for row in (live, deleted) if row is not None]
    return len(origins) == 1 and origins[0] in LEGACY_ACTIVITY_SOURCES


def event_origin(
    db: Session, event: CustomerDealJourneyEvent, team_id: int, customer_id: int, *, current: bool = False,
) -> bool:
    if event.team_id != team_id or event.customer_id != customer_id:
        return False
    if event.source_type in {"customer_activity", "customer_follow_up"}:
        return activity_origin(db, team_id, customer_id, event.source_id, current=current)
    return _business_origin(db, team_id, customer_id, event.source_type, event.source_id, current=current)


def follow_up_origin(db: Session, row: FollowUpTask | SalesCommitment, team_id: int, customer_id: int) -> bool:
    """Require every supplied source hint to identify the same eligible origin."""
    if row.team_id != team_id or row.customer_id != customer_id or row.source_public_id is not None:
        # Activities have no public ID; no producer binds this optional hint to an activity.
        return False

    source_type = str(row.source_type or "").lower()
    key = str(row.source_key or "")
    activity_id = row.source_activity_id
    commitment = None
    if isinstance(row, FollowUpTask) and row.commitment_id is not None:
        commitment = db.query(SalesCommitment).filter_by(
            id=row.commitment_id, team_id=team_id, customer_id=customer_id,
        ).one_or_none()
        if commitment is None or not follow_up_origin(db, commitment, team_id, customer_id):
            return False

    if source_type == "sales_commitment" and isinstance(row, FollowUpTask):
        if activity_id is not None or not key.startswith("commitment:"):
            return False
        identifier = key.removeprefix("commitment:")
        if not identifier.isdecimal() or str(int(identifier)) != identifier or int(identifier) <= 0:
            return False
        if commitment is None:
            commitment = db.query(SalesCommitment).filter_by(
                id=int(identifier), team_id=team_id, customer_id=customer_id,
            ).one_or_none()
        return (commitment is not None and commitment.id == int(identifier)
                and (row.commitment_id is not None or follow_up_origin(db, commitment, team_id, customer_id)))

    if source_type != "customer_activity" or not key.startswith("activity:"):
        return False
    identifier = key.removeprefix("activity:")
    if not identifier.isdecimal() or str(int(identifier)) != identifier or int(identifier) <= 0:
        return False
    if activity_id is not None and str(activity_id) != identifier:
        return False
    if commitment is not None:
        # A valid but *different* legacy commitment must not authorize this task.
        if commitment.source_type.lower() != "customer_activity":
            return False
        if commitment.source_key != key:
            return False
    return activity_origin(db, team_id, customer_id, identifier)


def fact_origin(db: Session, fact: CustomerFact, team_id: int, customer_id: int) -> bool:
    if fact.team_id != team_id or fact.customer_id != customer_id:
        return False
    sources = db.query(CustomerFactSource).filter_by(fact_id=fact.id).all()
    return bool(sources) and all(
        source_origin(db, team_id, customer_id, source.source_type, source.source_object_id,
                      source.business_object_type, source.business_object_id)
        for source in sources
    )


def source_origin(
    db: Session, team_id: int, customer_id: int, source_type: object, source_id: object,
    business_type: object = None, business_id: object = None,
) -> bool:
    return source_status(db, team_id, customer_id, source_type, source_id, business_type, business_id) == "VERIFIED"




def _business_origin(
    db: Session, team_id: int, customer_id: int, kind: object, source_id: object, *, current: bool = False,
) -> bool:
    if not str(source_id or "").isdecimal():
        return False
    identifier = int(str(source_id))
    if kind == "opportunity":
        query = db.query(Opportunity.id).filter_by(id=identifier, team_id=team_id, customer_id=customer_id)
    elif kind == "contract":
        query = db.query(Contract.id).filter_by(id=identifier, team_id=team_id, customer_id=customer_id)
    elif kind == "invoice_application":
        query = db.query(InvoiceApplication.id).filter_by(id=identifier, team_id=team_id, customer_id=customer_id)
    elif kind == "opportunity_stage_snapshot":
        query = db.query(OpportunityStageSnapshot.id).join(Opportunity, Opportunity.id == OpportunityStageSnapshot.opportunity_id).filter(
            OpportunityStageSnapshot.id == identifier, OpportunityStageSnapshot.team_id == team_id,
            Opportunity.team_id == team_id, Opportunity.customer_id == customer_id,
        )
    elif kind == "payment_plan":
        query = db.query(PaymentPlan.id).join(Contract, Contract.id == PaymentPlan.contract_id).filter(
            PaymentPlan.id == identifier, PaymentPlan.team_id == team_id,
            Contract.team_id == team_id, Contract.customer_id == customer_id,
        )
    elif kind == "payment_record":
        query = db.query(PaymentRecord.id).join(PaymentPlan, PaymentPlan.id == PaymentRecord.payment_plan_id).join(
            Contract, Contract.id == PaymentPlan.contract_id,
        ).filter(PaymentRecord.id == identifier, PaymentRecord.team_id == team_id,
                 PaymentPlan.team_id == team_id, Contract.team_id == team_id,
                 Contract.customer_id == customer_id)
    else:
        return False
    return (query.with_for_update() if current else query).first() is not None

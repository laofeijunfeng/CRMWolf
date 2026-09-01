import json
import logging
from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.deal_journey import (
    CustomerDealJourney,
    CustomerDealJourneyEvent,
    DealJourneyEventType,
    DealJourneySourceType,
    DealJourneyStatus,
)
from app.services.customer_intelligence_event_publication_service import (
    CustomerIntelligenceEventPublicationService,
    customer_intelligence_event_publication_service,
)
from app.services.customer_intelligence_event_service import JsonObject
from app.utils.time import business_now

logger = logging.getLogger(__name__)


class OpportunityDealJourneyConflictError(ValueError):
    """Raised when an opportunity changed before an association update committed."""

    def __init__(self, *, opportunity_id: int, expected_version: int, current_version: int):
        self.opportunity_id = opportunity_id
        self.expected_version = expected_version
        self.current_version = current_version
        super().__init__(
            f"商机已被其他操作更新，请刷新后重试（期望版本 {expected_version}，当前版本 {current_version}）"
        )


class DealJourneyService:
    def __init__(
        self,
        *,
        publication_service: CustomerIntelligenceEventPublicationService | None = None,
    ) -> None:
        self.publication_service = publication_service or customer_intelligence_event_publication_service

    def ensure_for_opportunity(
        self,
        db: Session,
        opportunity,
        actor_id: str | None = None,
    ) -> CustomerDealJourney:
        previous_deal_journey_id = self._positive_int(getattr(opportunity, "deal_journey_id", None))
        journey = None
        if previous_deal_journey_id:
            journey = (
                db.query(CustomerDealJourney)
                .filter(
                    CustomerDealJourney.id == previous_deal_journey_id,
                    CustomerDealJourney.team_id == opportunity.team_id,
                    CustomerDealJourney.customer_id == opportunity.customer_id,
                )
                .first()
            )

        if journey is None:
            journey = (
                db.query(CustomerDealJourney)
                .filter(
                    CustomerDealJourney.primary_opportunity_id == opportunity.id,
                    CustomerDealJourney.team_id == opportunity.team_id,
                    CustomerDealJourney.customer_id == opportunity.customer_id,
                )
                .first()
            )

        if journey is None:
            journey = CustomerDealJourney(
                team_id=opportunity.team_id,
                customer_id=opportunity.customer_id,
                primary_opportunity_id=opportunity.id,
                name=opportunity.opportunity_name,
                status=self._status_from_opportunity(opportunity),
                started_at=self._as_datetime(getattr(opportunity, "created_time", None)),
                closed_at=self._closing_time(opportunity) if getattr(opportunity, "status", None) in {1, 2} else None,
                last_event_at=self._as_datetime(getattr(opportunity, "created_time", None)),
            )
            db.add(journey)
            db.flush()

        opportunity.deal_journey_id = journey.id
        if previous_deal_journey_id != int(journey.id):
            self.record_event(
                db,
                deal_journey_id=journey.id,
                team_id=opportunity.team_id,
                customer_id=opportunity.customer_id,
                event_type=DealJourneyEventType.ASSOCIATION_CHANGED,
                source_type=DealJourneySourceType.OPPORTUNITY,
                source_id=opportunity.id,
                event_time=business_now(),
                actor_id=actor_id,
                summary=f"商机已关联业务旅程: {journey.name}",
                metadata={
                    "association_reason": "ENSURE_FOR_OPPORTUNITY",
                    "opportunity_id": opportunity.id,
                    "previous_deal_journey_id": previous_deal_journey_id,
                    "new_deal_journey_id": journey.id,
                },
            )
        return journey

    def associate_opportunity(
        self,
        db: Session,
        opportunity,
        *,
        deal_journey_id: int,
        actor_id: str | None = None,
        association_reason: str = "EXPLICIT_ASSOCIATION",
        expected_version: int | None = None,
    ) -> CustomerDealJourney:
        """Move an opportunity between journeys without rewriting history.

        The opportunity's association is the current routing state. Existing
        contracts, payments, activities, tasks, and commitments keep their
        original journey IDs so the profile can explain what happened before
        and after the move instead of silently changing historical evidence.
        Both sides receive an association event, allowing the old journey to
        be negatively re-projected and the new journey to be populated.
        """
        opportunity = self._lock_opportunity(db, opportunity)
        current_version = int(getattr(opportunity, "version", 1) or 1)
        if expected_version is not None and current_version != expected_version:
            raise OpportunityDealJourneyConflictError(
                opportunity_id=int(opportunity.id),
                expected_version=expected_version,
                current_version=current_version,
            )

        target = (
            db.query(CustomerDealJourney)
            .filter(
                CustomerDealJourney.id == deal_journey_id,
                CustomerDealJourney.team_id == opportunity.team_id,
                CustomerDealJourney.customer_id == opportunity.customer_id,
            )
            .first()
        )
        if target is None:
            raise ValueError("目标业务旅程不存在，或不属于当前客户")
        if target.status == DealJourneyStatus.ARCHIVED:
            raise ValueError("已归档的业务旅程不能关联商机")

        previous_id = self._positive_int(getattr(opportunity, "deal_journey_id", None))
        if previous_id == int(target.id):
            return target

        previous = None
        if previous_id is not None:
            previous = (
                db.query(CustomerDealJourney)
                .filter(
                    CustomerDealJourney.id == previous_id,
                    CustomerDealJourney.team_id == opportunity.team_id,
                    CustomerDealJourney.customer_id == opportunity.customer_id,
                )
                .first()
            )
            if previous is not None and previous.primary_opportunity_id == opportunity.id:
                previous.primary_opportunity_id = None
                # ``primary_opportunity_id`` is unique.  Flush the release
                # before assigning the target so databases that execute ORM
                # updates in a batch do not transiently see both journeys
                # pointing at the same opportunity during A -> B moves.
                db.flush()

        opportunity.deal_journey_id = target.id
        if target.primary_opportunity_id is None:
            target.primary_opportunity_id = opportunity.id
        opportunity.version = current_version + 1
        db.flush()

        transition = {
            "transition_id": self._transition_id(
                opportunity_id=int(opportunity.id),
                previous_deal_journey_id=previous_id,
                new_deal_journey_id=int(target.id),
                expected_version=expected_version if expected_version is not None else current_version,
            ),
            "association_reason": association_reason,
            "opportunity_id": int(opportunity.id),
            "previous_deal_journey_id": previous_id,
            "new_deal_journey_id": int(target.id),
        }
        if previous is not None:
            self.record_event(
                db,
                deal_journey_id=previous.id,
                team_id=opportunity.team_id,
                customer_id=opportunity.customer_id,
                event_type=DealJourneyEventType.ASSOCIATION_CHANGED,
                source_type=DealJourneySourceType.OPPORTUNITY,
                source_id=opportunity.id,
                event_time=business_now(),
                actor_id=actor_id,
                summary=f"商机已移出业务旅程：{previous.name}",
                metadata={**transition, "journey_side": "previous"},
            )
        self.record_event(
            db,
            deal_journey_id=target.id,
            team_id=opportunity.team_id,
            customer_id=opportunity.customer_id,
            event_type=DealJourneyEventType.ASSOCIATION_CHANGED,
            source_type=DealJourneySourceType.OPPORTUNITY,
            source_id=opportunity.id,
            event_time=business_now(),
            actor_id=actor_id,
            summary=f"商机已关联业务旅程：{target.name}",
            metadata={**transition, "journey_side": "new"},
        )
        return target

    def detach_opportunity(
        self,
        db: Session,
        opportunity,
        *,
        actor_id: str | None = None,
        association_reason: str = "EXPLICIT_DETACH",
        expected_version: int | None = None,
    ) -> CustomerDealJourney | None:
        """Remove the current journey association and retain all evidence."""
        opportunity = self._lock_opportunity(db, opportunity)
        current_version = int(getattr(opportunity, "version", 1) or 1)
        if expected_version is not None and current_version != expected_version:
            raise OpportunityDealJourneyConflictError(
                opportunity_id=int(opportunity.id),
                expected_version=expected_version,
                current_version=current_version,
            )

        previous_id = self._positive_int(getattr(opportunity, "deal_journey_id", None))
        if previous_id is None:
            return None

        previous = (
            db.query(CustomerDealJourney)
            .filter(
                CustomerDealJourney.id == previous_id,
                CustomerDealJourney.team_id == opportunity.team_id,
                CustomerDealJourney.customer_id == opportunity.customer_id,
            )
            .first()
        )
        if previous is not None and previous.primary_opportunity_id == opportunity.id:
            previous.primary_opportunity_id = None

        opportunity.deal_journey_id = None
        opportunity.version = current_version + 1
        db.flush()
        if previous is not None:
            self.record_event(
                db,
                deal_journey_id=previous.id,
                team_id=opportunity.team_id,
                customer_id=opportunity.customer_id,
                event_type=DealJourneyEventType.ASSOCIATION_CHANGED,
                source_type=DealJourneySourceType.OPPORTUNITY,
                source_id=opportunity.id,
                event_time=business_now(),
                actor_id=actor_id,
                summary=f"商机已解除业务旅程关联：{previous.name}",
                metadata={
                    "transition_id": self._transition_id(
                        opportunity_id=int(opportunity.id),
                        previous_deal_journey_id=previous_id,
                        new_deal_journey_id=None,
                        expected_version=expected_version if expected_version is not None else current_version,
                    ),
                    "association_reason": association_reason,
                    "opportunity_id": int(opportunity.id),
                    "previous_deal_journey_id": previous_id,
                    "new_deal_journey_id": None,
                    "journey_side": "previous",
                },
            )
        return previous

    @staticmethod
    def _transition_id(
        *,
        opportunity_id: int,
        previous_deal_journey_id: int | None,
        new_deal_journey_id: int | None,
        expected_version: int,
    ) -> str:
        return (
            f"journey-association:{opportunity_id}:"
            f"{previous_deal_journey_id or 0}:{new_deal_journey_id or 0}:{expected_version}"
        )

    @staticmethod
    def _lock_opportunity(db: Session, opportunity):
        """Lock a persisted opportunity when the caller passes an ORM entity.

        Service-level tests and import/replay callers may pass a lightweight
        object, so locking is intentionally best-effort for non-ORM inputs.
        On MySQL this becomes SELECT ... FOR UPDATE; on SQLite it remains a
        normal SELECT because SQLite does not implement row-level locks.
        """
        from app.models.opportunity import Opportunity

        if not isinstance(opportunity, Opportunity):
            return opportunity

        locked = (
            db.query(Opportunity)
            .filter(
                Opportunity.id == opportunity.id,
                Opportunity.team_id == opportunity.team_id,
                Opportunity.customer_id == opportunity.customer_id,
            )
            .with_for_update()
            .one_or_none()
        )
        return locked or opportunity

    def infer_for_customer(self, db: Session, customer_id: int, team_id: int) -> CustomerDealJourney | None:
        journeys = db.query(CustomerDealJourney).filter(
            CustomerDealJourney.customer_id == customer_id,
            CustomerDealJourney.team_id == team_id,
            CustomerDealJourney.status.notin_([DealJourneyStatus.LOST, DealJourneyStatus.COMPLETED]),
        ).limit(2).all()
        if len(journeys) == 1:
            return journeys[0]
        return None

    def record_event(
        self,
        db: Session,
        *,
        deal_journey_id: int | None,
        team_id: int,
        customer_id: int,
        event_type: str,
        source_type: str,
        source_id: Optional[int],
        event_time: date | datetime | None = None,
        actor_id: str | None = None,
        summary: Optional[str] = None,
        metadata: JsonObject | None = None,
        enqueue_customer_intelligence: bool = True,
    ) -> Optional[CustomerDealJourneyEvent]:
        if not deal_journey_id:
            return None

        normalized_event_time = self._as_datetime(event_time) or business_now()
        event_query = db.query(CustomerDealJourneyEvent).filter(
            CustomerDealJourneyEvent.deal_journey_id == deal_journey_id,
            CustomerDealJourneyEvent.event_type == event_type,
            CustomerDealJourneyEvent.source_type == source_type,
            CustomerDealJourneyEvent.source_id == source_id,
        )
        existing = event_query.first()
        if event_type == DealJourneyEventType.ASSOCIATION_CHANGED and metadata:
            # The same opportunity may move A -> B -> A.  Association history
            # must retain each distinct transition while retries of one
            # transition remain idempotent.
            desired_metadata = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
            existing = next(
                (
                    candidate
                    for candidate in event_query.order_by(CustomerDealJourneyEvent.id.desc()).all()
                    if candidate.metadata_json == desired_metadata
                ),
                None,
            )
        if existing:
            self._upsert_event_evidence(db, existing)
            if enqueue_customer_intelligence:
                self._enqueue_customer_intelligence_refresh(db, existing)
            return existing

        event = CustomerDealJourneyEvent(
            team_id=team_id,
            deal_journey_id=deal_journey_id,
            customer_id=customer_id,
            event_type=event_type,
            event_time=normalized_event_time,
            source_type=source_type,
            source_id=source_id,
            actor_id=actor_id,
            summary=summary,
            metadata_json=json.dumps(metadata, ensure_ascii=False, sort_keys=True) if metadata else None,
        )
        db.add(event)
        db.flush()
        self._upsert_event_evidence(db, event)
        if enqueue_customer_intelligence:
            self._enqueue_customer_intelligence_refresh(db, event)

        journey = db.query(CustomerDealJourney).filter(CustomerDealJourney.id == deal_journey_id).first()
        if journey and (journey.last_event_at is None or normalized_event_time > journey.last_event_at):
            journey.last_event_at = normalized_event_time
        return event

    def _upsert_event_evidence(self, db: Session, event: CustomerDealJourneyEvent) -> None:
        try:
            from app.services.customer_vector_document_service import customer_vector_document_service

            # Evidence is a projection-side read model. Isolate it from the
            # journey event transaction so vector indexing/schema drift cannot
            # invalidate the business-flow event itself.
            with db.begin_nested():
                customer_vector_document_service.upsert_deal_journey_event(db, event, commit=False)
        except Exception:
            logger.exception("成交旅程事件证据元数据写入失败: event_id=%s", event.id)

    def _enqueue_customer_intelligence_refresh(self, db: Session, event: CustomerDealJourneyEvent) -> None:
        try:
            from app.services.customer_intelligence_event_service import customer_intelligence_event_service

            intelligence_event = customer_intelligence_event_service.from_deal_journey_event(event)
            if intelligence_event is None:
                return
            # The journey event remains the source-of-truth business event.
            # Only the asynchronous profile-refresh enqueue is optional; a
            # failed enqueue is repaired by reconciliation from the journey
            # watermark and must not roll back the journey mutation.
            self.publication_service.persist_in_transaction(
                db,
                event=intelligence_event,
                scope="partial",
            )
        except Exception:
            logger.exception(
                "成交旅程事件客户智能刷新入队失败,将由对账机制补偿: event_id=%s team_id=%s customer_id=%s",
                getattr(event, "id", None),
                getattr(event, "team_id", None),
                getattr(event, "customer_id", None),
            )

    def record_opportunity_created(self, db: Session, opportunity, actor_id: Optional[str] = None) -> None:
        journey = self.ensure_for_opportunity(db, opportunity, actor_id)
        self.record_event(
            db,
            deal_journey_id=journey.id,
            team_id=opportunity.team_id,
            customer_id=opportunity.customer_id,
            event_type=DealJourneyEventType.OPPORTUNITY_CREATED,
            source_type=DealJourneySourceType.OPPORTUNITY,
            source_id=opportunity.id,
            event_time=opportunity.created_time,
            actor_id=actor_id,
            summary=f"创建商机：{opportunity.opportunity_name}",
        )

    def record_opportunity_approved(self, db: Session, opportunity, actor_id: Optional[str] = None) -> None:
        journey = self.ensure_for_opportunity(db, opportunity, actor_id)
        self.record_event(
            db,
            deal_journey_id=journey.id,
            team_id=opportunity.team_id,
            customer_id=opportunity.customer_id,
            event_type=DealJourneyEventType.OPPORTUNITY_APPROVED,
            source_type=DealJourneySourceType.OPPORTUNITY,
            source_id=opportunity.id,
            event_time=business_now(),
            actor_id=actor_id,
            summary=f"商机审批通过：{opportunity.opportunity_name}",
        )

    def record_opportunity_stage_changed(self, db: Session, opportunity, snapshot, actor_id: Optional[str] = None) -> None:
        journey = self.ensure_for_opportunity(db, opportunity, actor_id)
        self.record_event(
            db,
            deal_journey_id=journey.id,
            team_id=opportunity.team_id,
            customer_id=opportunity.customer_id,
            event_type=DealJourneyEventType.OPPORTUNITY_STAGE_CHANGED,
            source_type=DealJourneySourceType.OPPORTUNITY_STAGE_SNAPSHOT,
            source_id=snapshot.id,
            event_time=snapshot.entered_at,
            actor_id=actor_id,
            summary=f"商机阶段推进到：{snapshot.stage_name}",
            metadata={
                "stage_name": snapshot.stage_name,
                "win_probability": snapshot.win_probability,
                "template_code": snapshot.template_code,
            },
        )

    def mark_won(self, db: Session, opportunity, actor_id: Optional[str] = None) -> None:
        journey = self.ensure_for_opportunity(db, opportunity, actor_id)
        journey.status = DealJourneyStatus.WON
        journey.closed_at = None
        self.record_event(
            db,
            deal_journey_id=journey.id,
            team_id=opportunity.team_id,
            customer_id=opportunity.customer_id,
            event_type=DealJourneyEventType.OPPORTUNITY_WON,
            source_type=DealJourneySourceType.OPPORTUNITY,
            source_id=opportunity.id,
            event_time=self._closing_time(opportunity) or business_now(),
            actor_id=actor_id,
            summary=f"商机赢单：{opportunity.opportunity_name}",
            metadata={"actual_amount": float(opportunity.actual_amount) if opportunity.actual_amount else None},
        )

    def mark_lost(self, db: Session, opportunity, actor_id: Optional[str] = None) -> None:
        journey = self.ensure_for_opportunity(db, opportunity, actor_id)
        closed_at = business_now()
        journey.status = DealJourneyStatus.LOST
        journey.closed_at = closed_at
        self.record_event(
            db,
            deal_journey_id=journey.id,
            team_id=opportunity.team_id,
            customer_id=opportunity.customer_id,
            event_type=DealJourneyEventType.OPPORTUNITY_LOST,
            source_type=DealJourneySourceType.OPPORTUNITY,
            source_id=opportunity.id,
            event_time=closed_at,
            actor_id=actor_id,
            summary=f"商机输单：{opportunity.opportunity_name}",
            metadata={"loss_reason": opportunity.loss_reason},
        )

    def _status_from_opportunity(self, opportunity) -> str:
        status = getattr(opportunity, "status", None)
        if status == 1:
            return DealJourneyStatus.WON
        if status == 2:
            return DealJourneyStatus.LOST
        return DealJourneyStatus.ACTIVE

    def refresh_closure_status(self, db: Session, deal_journey_id: Optional[int]) -> Optional[CustomerDealJourney]:
        if not deal_journey_id:
            return None

        from app.models.contract import Contract, PaymentStatus
        from app.models.opportunity import Opportunity
        from app.models.payment import PaymentConfirmationStatus, PaymentRecord

        journey = db.query(CustomerDealJourney).filter(CustomerDealJourney.id == deal_journey_id).first()
        if not journey:
            return None

        opportunity = None
        if journey.primary_opportunity_id:
            opportunity = db.query(Opportunity).filter(Opportunity.id == journey.primary_opportunity_id).first()

        if opportunity and opportunity.status == 2:
            journey.status = DealJourneyStatus.LOST
            journey.closed_at = self._closing_time(opportunity) or business_now()
            return journey

        contracts = db.query(Contract).filter(
            Contract.deal_journey_id == journey.id,
            Contract.deleted_at.is_(None),
        ).all()
        if contracts and all(contract.payment_status == PaymentStatus.COMPLETED for contract in contracts):
            last_confirmed_at = db.query(func.max(PaymentRecord.confirmed_time)).filter(
                PaymentRecord.deal_journey_id == journey.id,
                PaymentRecord.confirmation_status == PaymentConfirmationStatus.CONFIRMED,
            ).scalar()
            if last_confirmed_at is None:
                last_payment_date = db.query(func.max(PaymentRecord.payment_date)).filter(
                    PaymentRecord.deal_journey_id == journey.id,
                    PaymentRecord.confirmation_status == PaymentConfirmationStatus.CONFIRMED,
                ).scalar()
                last_confirmed_at = self._as_datetime(last_payment_date)

            journey.status = DealJourneyStatus.COMPLETED
            journey.closed_at = self._as_datetime(last_confirmed_at) or business_now()
            return journey

        if opportunity and opportunity.status == 1:
            journey.status = DealJourneyStatus.WON
        else:
            journey.status = DealJourneyStatus.ACTIVE
        journey.closed_at = None
        return journey

    def _closing_time(self, opportunity) -> Optional[datetime]:
        return self._as_datetime(
            getattr(opportunity, "actual_closing_date", None)
            or getattr(opportunity, "last_modified_time", None)
        )

    def _positive_int(self, value: object) -> Optional[int]:
        try:
            parsed = int(value) if value is not None else 0
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def _as_datetime(self, value: date | datetime | None) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, time.min)
        return None


deal_journey_service = DealJourneyService()

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
from app.services.customer_intelligence_event_service import JsonObject
from app.utils.time import business_now

logger = logging.getLogger(__name__)


class DealJourneyService:
    def ensure_for_opportunity(
        self,
        db: Session,
        opportunity,
        actor_id: Optional[str] = None,
    ) -> CustomerDealJourney:
        journey = None
        if getattr(opportunity, "deal_journey_id", None):
            journey = db.query(CustomerDealJourney).filter(
                CustomerDealJourney.id == opportunity.deal_journey_id
            ).first()

        if journey is None:
            journey = db.query(CustomerDealJourney).filter(
                CustomerDealJourney.primary_opportunity_id == opportunity.id
            ).first()

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
        return journey

    def infer_for_customer(self, db: Session, customer_id: int, team_id: int) -> Optional[CustomerDealJourney]:
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
        deal_journey_id: Optional[int],
        team_id: int,
        customer_id: int,
        event_type: str,
        source_type: str,
        source_id: Optional[int],
        event_time: date | datetime | None = None,
        actor_id: Optional[str] = None,
        summary: Optional[str] = None,
        metadata: JsonObject | None = None,
    ) -> Optional[CustomerDealJourneyEvent]:
        if not deal_journey_id:
            return None

        normalized_event_time = self._as_datetime(event_time) or business_now()
        existing = db.query(CustomerDealJourneyEvent).filter(
            CustomerDealJourneyEvent.deal_journey_id == deal_journey_id,
            CustomerDealJourneyEvent.event_type == event_type,
            CustomerDealJourneyEvent.source_type == source_type,
            CustomerDealJourneyEvent.source_id == source_id,
        ).first()
        if existing:
            self._upsert_event_evidence(db, existing)
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
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
        )
        db.add(event)
        db.flush()
        self._upsert_event_evidence(db, event)
        self._enqueue_customer_intelligence_refresh(db, event)

        journey = db.query(CustomerDealJourney).filter(CustomerDealJourney.id == deal_journey_id).first()
        if journey and (journey.last_event_at is None or normalized_event_time > journey.last_event_at):
            journey.last_event_at = normalized_event_time
        return event

    def _upsert_event_evidence(self, db: Session, event: CustomerDealJourneyEvent) -> None:
        try:
            from app.services.customer_vector_document_service import customer_vector_document_service

            customer_vector_document_service.upsert_deal_journey_event(db, event, commit=False)
        except Exception:
            logger.exception("成交旅程事件证据元数据写入失败: event_id=%s", event.id)

    def _enqueue_customer_intelligence_refresh(self, db: Session, event: CustomerDealJourneyEvent) -> None:
        try:
            from app.services.customer_intelligence_event_service import customer_intelligence_event_service
            from app.services.customer_intelligence_refresh_service import customer_intelligence_refresh_service

            intelligence_event = customer_intelligence_event_service.from_deal_journey_event(event)
            if intelligence_event is None:
                return
            customer_intelligence_refresh_service.enqueue_committed_event_refresh(
                db,
                event=intelligence_event,
                scope="brief",
            )
        except Exception:
            logger.exception("成交旅程事件客户智能刷新入队失败: event_id=%s", event.id)

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

    def _as_datetime(self, value: date | datetime | None) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, time.min)
        return None


deal_journey_service = DealJourneyService()

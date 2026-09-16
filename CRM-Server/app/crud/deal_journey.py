from __future__ import annotations

from sqlalchemy import case
from sqlalchemy.orm import Session

from app.models.deal_journey import CustomerDealJourney, DealJourneyStatus


class DealJourneyCRUD:
    def get_by_public_id(
        self,
        db: Session,
        public_id: str,
        team_id: int,
        customer_id: int | None = None,
    ) -> CustomerDealJourney | None:
        query = db.query(CustomerDealJourney).filter(
            CustomerDealJourney.public_id == public_id,
            CustomerDealJourney.team_id == team_id,
        )
        if customer_id is not None:
            query = query.filter(CustomerDealJourney.customer_id == customer_id)
        return query.first()

    def get_by_id(
        self,
        db: Session,
        journey_id: int,
        team_id: int,
    ) -> CustomerDealJourney | None:
        return (
            db.query(CustomerDealJourney)
            .filter(
                CustomerDealJourney.id == journey_id,
                CustomerDealJourney.team_id == team_id,
            )
            .first()
        )

    def list_by_ids(
        self,
        db: Session,
        *,
        team_id: int,
        journey_ids: list[int],
    ) -> list[CustomerDealJourney]:
        if not journey_ids:
            return []
        return (
            db.query(CustomerDealJourney)
            .filter(
                CustomerDealJourney.team_id == team_id,
                CustomerDealJourney.id.in_(journey_ids),
            )
            .all()
        )

    def list_by_customer(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
    ) -> list[CustomerDealJourney]:
        return (
            db.query(CustomerDealJourney)
            .filter(
                CustomerDealJourney.team_id == team_id,
                CustomerDealJourney.customer_id == customer_id,
                CustomerDealJourney.status != DealJourneyStatus.ARCHIVED,
            )
            .order_by(
                case((CustomerDealJourney.last_event_at.is_(None), 1), else_=0).asc(),
                CustomerDealJourney.last_event_at.desc(),
                CustomerDealJourney.id.desc(),
            )
            .all()
        )


deal_journey_crud = DealJourneyCRUD()

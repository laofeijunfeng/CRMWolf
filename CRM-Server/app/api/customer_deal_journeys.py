from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import check_customer_view_permission, get_current_active_user, get_current_user_team
from app.crud.deal_journey import deal_journey_crud
from app.models.user import User
from app.schemas.deal_journey import CustomerDealJourneyResponse
from app.services.business_journey_presenter import customer_journey_responses
from app.utils.public_id import is_deal_journey_public_id

router = APIRouter(prefix="/v1/customers", tags=["客户业务旅程"])



@router.get("/{customer_public_id}/deal-journeys", response_model=list[CustomerDealJourneyResponse])
def list_customer_deal_journeys(
    customer_public_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[CustomerDealJourneyResponse]:
    customer = check_customer_view_permission(customer_public_id, team_id, current_user, db)
    journeys = deal_journey_crud.list_by_customer(db, team_id=team_id, customer_id=int(customer.id))
    return customer_journey_responses(db, team_id, journeys)


@router.get(
    "/{customer_public_id}/deal-journeys/{journey_public_id}",
    response_model=CustomerDealJourneyResponse,
)
def get_customer_deal_journey(
    customer_public_id: str,
    journey_public_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> CustomerDealJourneyResponse:
    if not is_deal_journey_public_id(journey_public_id):
        raise HTTPException(status_code=404, detail="业务旅程不存在")
    customer = check_customer_view_permission(customer_public_id, team_id, current_user, db)
    journey = deal_journey_crud.get_by_public_id(
        db, journey_public_id, team_id, customer_id=int(customer.id)
    )
    if journey is None:
        raise HTTPException(status_code=404, detail="业务旅程不存在")
    return customer_journey_responses(db, team_id, [journey])[0]

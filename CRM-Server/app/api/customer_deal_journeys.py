from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import check_customer_view_permission, get_current_active_user, get_current_user_team
from app.crud.deal_journey import deal_journey_crud
from app.models.opportunity import Opportunity
from app.models.user import User
from app.schemas.deal_journey import CustomerDealJourneyOpportunitySummary, CustomerDealJourneyResponse
from app.services.deal_journey_stage import (
    BOARD_STAGE_LABELS,
    BusinessJourneyContractSummary,
    BusinessJourneyInvoiceSummary,
    BusinessJourneyPaymentSummary,
    infer_board_stage,
    load_contract_summaries,
    load_invoice_summaries,
    load_payment_summaries,
)
from app.utils.public_id import is_deal_journey_public_id

router = APIRouter(prefix="/v1/customers", tags=["客户业务旅程"])

_EMPTY_CONTRACT = BusinessJourneyContractSummary(count=0, signed_count=0, amount=0)
_EMPTY_PAYMENT = BusinessJourneyPaymentSummary(
    plan_count=0,
    record_count=0,
    planned_amount=0,
    paid_amount=0,
    remaining_amount=0,
)
_EMPTY_INVOICE = BusinessJourneyInvoiceSummary(
    application_count=0,
    issued_count=0,
    applied_amount=0,
    issued_amount=0,
)


def _opportunity_amount(opportunity: Opportunity | None) -> float:
    if opportunity is None or opportunity.total_amount is None:
        return 0.0
    return float(opportunity.total_amount)


def _opportunity_summary(opportunity: Opportunity | None) -> CustomerDealJourneyOpportunitySummary | None:
    if opportunity is None:
        return None
    product = getattr(opportunity, "product", None)
    return CustomerDealJourneyOpportunitySummary(
        public_id=opportunity.public_id,
        opportunity_name=opportunity.opportunity_name,
        status=int(opportunity.status),
        approval_phase=opportunity.approval_phase,
        win_probability=opportunity.current_win_probability or opportunity.win_probability,
        expected_closing_date=opportunity.expected_closing_date,
        product_name=product.name if product is not None else None,
    )


def _to_response(
    db: Session,
    team_id: int,
    journey,
    *,
    opportunity: Opportunity | None,
    contract_summary: BusinessJourneyContractSummary,
    payment_summary: BusinessJourneyPaymentSummary,
    invoice_summary: BusinessJourneyInvoiceSummary,
) -> CustomerDealJourneyResponse:
    del db, team_id
    stage = infer_board_stage(journey, opportunity, contract_summary, payment_summary, invoice_summary)
    return CustomerDealJourneyResponse(
        id=journey.public_id,
        public_id=journey.public_id,
        name=journey.name,
        status=journey.status,
        current_board_stage=stage,
        current_board_stage_label=BOARD_STAGE_LABELS[stage],
        amount=_opportunity_amount(opportunity),
        purchase_type=opportunity.purchase_type if opportunity is not None else None,
        started_at=journey.started_at,
        closed_at=journey.closed_at,
        last_event_at=journey.last_event_at,
        primary_opportunity=_opportunity_summary(opportunity),
    )


def _to_responses(db: Session, team_id: int, journeys) -> list[CustomerDealJourneyResponse]:
    journey_ids = [int(journey.id) for journey in journeys]
    contract_map = load_contract_summaries(db, team_id, journey_ids)
    payment_map = load_payment_summaries(db, team_id, journey_ids)
    invoice_map = load_invoice_summaries(db, team_id, journey_ids)
    opportunity_ids = [
        int(journey.primary_opportunity_id)
        for journey in journeys
        if journey.primary_opportunity_id is not None
    ]
    opportunity_map: dict[int, Opportunity] = {}
    if opportunity_ids:
        opportunities = (
            db.query(Opportunity)
            .options(selectinload(Opportunity.product))
            .filter(Opportunity.id.in_(opportunity_ids), Opportunity.team_id == team_id)
            .all()
        )
        opportunity_map = {int(opportunity.id): opportunity for opportunity in opportunities}
    return [
        _to_response(
            db,
            team_id,
            journey,
            opportunity=(
                opportunity_map.get(int(journey.primary_opportunity_id))
                if journey.primary_opportunity_id is not None
                else None
            ),
            contract_summary=contract_map.get(int(journey.id), _EMPTY_CONTRACT),
            payment_summary=payment_map.get(int(journey.id), _EMPTY_PAYMENT),
            invoice_summary=invoice_map.get(int(journey.id), _EMPTY_INVOICE),
        )
        for journey in journeys
    ]


@router.get("/{customer_public_id}/deal-journeys", response_model=list[CustomerDealJourneyResponse])
def list_customer_deal_journeys(
    customer_public_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[CustomerDealJourneyResponse]:
    customer = check_customer_view_permission(customer_public_id, team_id, current_user, db)
    journeys = deal_journey_crud.list_by_customer(db, team_id=team_id, customer_id=int(customer.id))
    return _to_responses(db, team_id, journeys)


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
    return _to_responses(db, team_id, [journey])[0]

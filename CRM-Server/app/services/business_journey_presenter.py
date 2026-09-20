from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session, selectinload

from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent, DealJourneyStatus
from app.models.opportunity import Opportunity
from app.models.user import User
from app.schemas.deal_journey import (
    BusinessJourneyBoardCard,
    BusinessJourneyBoardColumn,
    BusinessJourneyBoardOpportunitySummary,
    BusinessJourneyBoardResponse,
    BusinessJourneyBoardSummary,
    BusinessJourneyListItem,
    BusinessJourneyOwner,
    CustomerDealJourneyOpportunitySummary,
    CustomerDealJourneyResponse,
)
from app.services.business_journey_query_service import BusinessJourneyQueryRow
from app.services.deal_journey_stage import (
    BOARD_COLUMNS,
    BOARD_STAGE_LABELS,
    BusinessJourneyContractSummary,
    BusinessJourneyInvoiceSummary,
    BusinessJourneyPaymentSummary,
    infer_board_stage,
    load_contract_summaries,
    load_invoice_summaries,
    load_payment_summaries,
)

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


def scalar_number(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def opportunity_amount(opportunity: Opportunity | None) -> float:
    if opportunity is None:
        return 0.0
    if opportunity.actual_amount is not None:
        return scalar_number(opportunity.actual_amount)
    return scalar_number(opportunity.total_amount)


def customer_opportunity_amount(opportunity: Opportunity | None) -> float:
    if opportunity is None:
        return 0.0
    return scalar_number(opportunity.total_amount)


def customer_opportunity_summary(
    opportunity: Opportunity | None,
) -> CustomerDealJourneyOpportunitySummary | None:
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


def legacy_board_opportunity_summary(opportunity: Opportunity | None) -> dict | None:
    if opportunity is None:
        return None
    return {
        "id": opportunity.id,
        "name": opportunity.opportunity_name,
        "amount": scalar_number(opportunity.total_amount),
        "actual_amount": (
            scalar_number(opportunity.actual_amount)
            if opportunity.actual_amount is not None
            else None
        ),
        "status": opportunity.status,
        "current_stage_name": opportunity.current_stage_name,
        "win_probability": opportunity.current_win_probability or opportunity.win_probability,
        "expected_closing_date": (
            opportunity.expected_closing_date.isoformat()
            if opportunity.expected_closing_date
            else None
        ),
    }


def legacy_board_owner_map(db: Session, rows) -> dict[str, dict]:
    owner_ids = {
        getattr(opportunity, "owner_id", None) or getattr(customer, "owner_id", None)
        for _journey, customer, opportunity in rows
    }
    numeric_ids = [int(owner_id) for owner_id in owner_ids if owner_id and str(owner_id).isdigit()]
    users = db.query(User).filter(User.id.in_(numeric_ids)).all() if numeric_ids else []
    return {
        str(user.id): {
            "id": str(user.id),
            "name": user.name,
            "avatar_url": user.avatar_url,
        }
        for user in users
    }


def customer_journey_response(
    journey: CustomerDealJourney,
    *,
    opportunity: Opportunity | None,
    contract_summary: BusinessJourneyContractSummary,
    payment_summary: BusinessJourneyPaymentSummary,
    invoice_summary: BusinessJourneyInvoiceSummary,
) -> CustomerDealJourneyResponse:
    stage = infer_board_stage(
        journey,
        opportunity,
        contract_summary,
        payment_summary,
        invoice_summary,
    )
    return CustomerDealJourneyResponse(
        id=journey.public_id,
        public_id=journey.public_id,
        name=journey.name,
        status=journey.status,
        current_board_stage=stage,
        current_board_stage_label=BOARD_STAGE_LABELS[stage],
        amount=customer_opportunity_amount(opportunity),
        purchase_type=opportunity.purchase_type if opportunity is not None else None,
        started_at=journey.started_at,
        closed_at=journey.closed_at,
        last_event_at=journey.last_event_at,
        primary_opportunity=customer_opportunity_summary(opportunity),
    )


def customer_journey_responses(
    db: Session,
    team_id: int,
    journeys: list[CustomerDealJourney],
) -> list[CustomerDealJourneyResponse]:
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
        customer_journey_response(
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


def _owner_map(db: Session, rows: list[BusinessJourneyQueryRow]) -> dict[str, BusinessJourneyOwner]:
    owner_ids = {str(row.owner_id) for row in rows if row.owner_id}
    numeric_ids = [int(owner_id) for owner_id in owner_ids if owner_id.isdigit()]
    users = db.query(User).filter(User.id.in_(numeric_ids)).all() if numeric_ids else []
    return {
        str(user.id): BusinessJourneyOwner(
            id=str(user.id),
            name=user.name,
            avatar_url=user.avatar_url,
        )
        for user in users
    }


def _latest_event_map(
    db: Session,
    *,
    team_id: int,
    rows: list[BusinessJourneyQueryRow],
) -> dict[int, str]:
    journey_ids = [int(row.journey.id) for row in rows]
    if not journey_ids:
        return {}
    events = (
        db.query(CustomerDealJourneyEvent)
        .filter(
            CustomerDealJourneyEvent.team_id == team_id,
            CustomerDealJourneyEvent.deal_journey_id.in_(journey_ids),
        )
        .order_by(
            CustomerDealJourneyEvent.deal_journey_id.asc(),
            CustomerDealJourneyEvent.event_time.desc(),
        )
        .all()
    )
    result: dict[int, str] = {}
    for event in events:
        journey_id = int(event.deal_journey_id)
        if journey_id not in result and event.summary:
            result[journey_id] = event.summary
    return result


def list_items(
    db: Session,
    rows: list[BusinessJourneyQueryRow],
) -> list[BusinessJourneyListItem]:
    owners = _owner_map(db, rows)
    items: list[BusinessJourneyListItem] = []
    for row in rows:
        base = customer_journey_response(
            row.journey,
            opportunity=row.opportunity,
            contract_summary=row.contract_summary,
            payment_summary=row.payment_summary,
            invoice_summary=row.invoice_summary,
        )
        base_data = base.model_dump()
        base_data["amount"] = opportunity_amount(row.opportunity)
        product = getattr(row.opportunity, "product", None) if row.opportunity is not None else None
        items.append(
            BusinessJourneyListItem(
                **base_data,
                customer_id=row.customer.public_id,
                customer_name=row.customer.account_name,
                owner=owners.get(str(row.owner_id)) if row.owner_id else None,
                primary_opportunity_name=(
                    row.opportunity.opportunity_name if row.opportunity is not None else None
                ),
                product_name=product.name if product is not None else None,
                created_time=row.opportunity.created_time if row.opportunity is not None else None,
                expected_closing_date=(
                    row.opportunity.expected_closing_date if row.opportunity is not None else None
                ),
            )
        )
    return items


def _board_opportunity_summary(
    opportunity: Opportunity | None,
) -> BusinessJourneyBoardOpportunitySummary | None:
    if opportunity is None:
        return None
    return BusinessJourneyBoardOpportunitySummary(
        public_id=opportunity.public_id,
        opportunity_name=opportunity.opportunity_name,
        amount=scalar_number(opportunity.total_amount),
        actual_amount=(
            scalar_number(opportunity.actual_amount)
            if opportunity.actual_amount is not None
            else None
        ),
        status=int(opportunity.status),
        current_stage_name=opportunity.current_stage_name,
        win_probability=opportunity.current_win_probability or opportunity.win_probability,
        expected_closing_date=opportunity.expected_closing_date,
    )


def board_response(
    db: Session,
    *,
    team_id: int,
    rows: list[BusinessJourneyQueryRow],
    total: int,
    truncated: bool,
) -> BusinessJourneyBoardResponse:
    owners = _owner_map(db, rows)
    latest_events = _latest_event_map(db, team_id=team_id, rows=rows)
    columns = {
        key: BusinessJourneyBoardColumn(
            key=key,
            title=title,
            description=description,
            count=0,
            amount=0,
            cards=[],
        )
        for key, title, description in BOARD_COLUMNS
    }
    total_amount = 0.0
    active_count = 0
    completed_count = 0
    lost_count = 0

    for row in rows:
        amount = opportunity_amount(row.opportunity)
        total_amount += amount
        if row.journey.status == DealJourneyStatus.COMPLETED:
            completed_count += 1
        elif row.journey.status == DealJourneyStatus.LOST:
            lost_count += 1
        else:
            active_count += 1

        card = BusinessJourneyBoardCard(
            public_id=row.journey.public_id,
            journey_name=row.journey.name,
            customer_id=row.customer.public_id,
            customer_name=row.customer.account_name,
            owner=owners.get(str(row.owner_id)) if row.owner_id else None,
            status=row.journey.status,
            current_board_stage=row.stage,
            started_at=row.journey.started_at,
            closed_at=row.journey.closed_at,
            last_event_at=row.journey.last_event_at,
            last_event_summary=latest_events.get(int(row.journey.id)),
            amount=amount,
            primary_opportunity=_board_opportunity_summary(row.opportunity),
            contract_summary=row.contract_summary,
            payment_summary=row.payment_summary,
            invoice_summary=row.invoice_summary,
        )
        column = columns[row.stage]
        column.cards.append(card)
        column.count += 1
        column.amount += amount

    return BusinessJourneyBoardResponse(
        columns=[columns[key] for key, _, _ in BOARD_COLUMNS],
        summary=BusinessJourneyBoardSummary(
            total_count=total,
            total_amount=total_amount,
            active_count=active_count,
            completed_count=completed_count,
            lost_count=lost_count,
        ),
        truncated=truncated,
    )


__all__ = [
    "board_response",
    "customer_journey_response",
    "customer_journey_responses",
    "customer_opportunity_amount",
    "customer_opportunity_summary",
    "legacy_board_opportunity_summary",
    "legacy_board_owner_map",
    "list_items",
    "opportunity_amount",
    "scalar_number",
]

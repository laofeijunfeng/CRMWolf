from datetime import date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.crud.permission import permission_crud
from app.models.customer import Customer
from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent, DealJourneyStatus
from app.models.opportunity import Opportunity
from app.services.business_journey_presenter import (
    legacy_board_amount,
    legacy_board_opportunity_summary,
    legacy_board_owner_map,
)
from app.services.deal_journey_stage import (
    BOARD_COLUMNS,
    BoardStageKey,
    BusinessJourneyContractSummary,
    BusinessJourneyInvoiceSummary,
    BusinessJourneyPaymentSummary,
    infer_active_opportunity_stage as _infer_active_opportunity_stage,
    infer_board_stage as _infer_stage,
    load_contract_summaries as _load_contract_summaries,
    load_invoice_summaries as _load_invoice_summaries,
    load_payment_summaries as _load_payment_summaries,
)


router = APIRouter(prefix="/v1/business-journey-board", tags=["业务旅程看板"])

DashboardScope = Literal["own", "team", "all"]


class BusinessJourneyBoardOwner(BaseModel):
    id: str
    name: str
    avatar_url: str | None = None


class BusinessJourneyOpportunitySummary(BaseModel):
    id: int | None = None
    name: str | None = None
    amount: float | None = None
    actual_amount: float | None = None
    status: int | None = None
    current_stage_name: str | None = None
    win_probability: int | None = None
    expected_closing_date: str | None = None


class BusinessJourneyBoardCard(BaseModel):
    journey_id: int
    journey_name: str
    customer_id: str
    customer_name: str | None = None
    owner: BusinessJourneyBoardOwner | None = None
    status: str
    current_board_stage: BoardStageKey
    started_at: datetime | None = None
    closed_at: datetime | None = None
    last_event_at: datetime | None = None
    last_event_summary: str | None = None
    amount: float
    primary_opportunity: BusinessJourneyOpportunitySummary | None = None
    contract_summary: BusinessJourneyContractSummary
    payment_summary: BusinessJourneyPaymentSummary
    invoice_summary: BusinessJourneyInvoiceSummary


class BusinessJourneyBoardColumn(BaseModel):
    key: BoardStageKey
    title: str
    description: str
    count: int
    amount: float
    cards: list[BusinessJourneyBoardCard]


class BusinessJourneyBoardSummary(BaseModel):
    total_count: int
    total_amount: float
    active_count: int
    completed_count: int
    lost_count: int


class BusinessJourneyBoardResponse(BaseModel):
    scope: DashboardScope
    period_start: str | None
    period_end: str | None
    columns: list[BusinessJourneyBoardColumn]
    summary: BusinessJourneyBoardSummary




def _date_range(start_date: date | None, end_date: date | None) -> tuple[datetime | None, datetime | None]:
    start = datetime.combine(start_date, time.min) if start_date else None
    end = datetime.combine(end_date + timedelta(days=1), time.min) if end_date else None
    return start, end


def _parse_owner_ids(owner_id: str | None) -> list[str]:
    if not owner_id:
        return []
    return [item.strip() for item in owner_id.split(",") if item.strip()]


def _resolve_scope(db: Session, user_id: int, team_id: int) -> DashboardScope:
    permission_codes = {
        permission.code
        for permission in permission_crud.get_user_permissions(db, user_id, team_id)
    }

    if "sales_dashboard:view:all" in permission_codes:
        return "all"
    if "sales_dashboard:view:team" in permission_codes:
        return "team"
    if "sales_dashboard:view:own" in permission_codes:
        return "own"

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="缺少权限: sales_dashboard:view:own 或 sales_dashboard:view:team"
    )


def _owner_id_for(journey, customer: Customer | None, opportunity: Opportunity | None) -> str | None:
    return getattr(opportunity, "owner_id", None) or getattr(customer, "owner_id", None)


@router.get("/", response_model=BusinessJourneyBoardResponse, summary="业务旅程看板")
def get_business_journey_board(
    start_date: date | None = Query(None, description="最近业务动态开始日期"),
    end_date: date | None = Query(None, description="最近业务动态结束日期"),
    created_time_start: date | None = Query(None, description="主商机创建开始日期"),
    created_time_end: date | None = Query(None, description="主商机创建结束日期"),
    expected_closing_date_start: date | None = Query(None, description="主商机预计成交开始日期"),
    expected_closing_date_end: date | None = Query(None, description="主商机预计成交结束日期"),
    owner_id: str | None = Query(None, description="负责人ID，多个用英文逗号分隔"),
    limit: int = Query(500, ge=1, le=1000, description="最多加载的旅程卡片数"),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    for range_start, range_end in (
        (start_date, end_date),
        (created_time_start, created_time_end),
        (expected_closing_date_start, expected_closing_date_end),
    ):
        if range_start and range_end and range_start > range_end:
            raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")

    scope = _resolve_scope(db, current_user.id, team_id)
    user_id = str(current_user.id)
    owner_ids = _parse_owner_ids(owner_id)
    filter_start, filter_end = _date_range(start_date, end_date)

    query = (
        db.query(CustomerDealJourney, Customer, Opportunity)
        .join(Customer, Customer.id == CustomerDealJourney.customer_id)
        .outerjoin(Opportunity, Opportunity.id == CustomerDealJourney.primary_opportunity_id)
        .filter(CustomerDealJourney.team_id == team_id)
    )

    if filter_start is not None:
        query = query.filter(CustomerDealJourney.last_event_at >= filter_start)
    if filter_end is not None:
        query = query.filter(CustomerDealJourney.last_event_at < filter_end)

    created_start, created_end = _date_range(created_time_start, created_time_end)
    if created_start is not None:
        query = query.filter(Opportunity.created_time >= created_start)
    if created_end is not None:
        query = query.filter(Opportunity.created_time < created_end)

    if expected_closing_date_start is not None:
        query = query.filter(Opportunity.expected_closing_date >= expected_closing_date_start)
    if expected_closing_date_end is not None:
        query = query.filter(Opportunity.expected_closing_date <= expected_closing_date_end)

    owner_expr = func.coalesce(Opportunity.owner_id, Customer.owner_id)
    if scope == "own":
        query = query.filter(owner_expr == user_id)
    elif owner_ids:
        query = query.filter(owner_expr.in_(owner_ids))

    rows = (
        query.order_by(
            case((CustomerDealJourney.last_event_at.is_(None), 1), else_=0).asc(),
            CustomerDealJourney.last_event_at.desc(),
            CustomerDealJourney.created_time.desc(),
        )
        .limit(limit)
        .all()
    )
    journey_ids = [journey.id for journey, _, _ in rows]

    contract_map = _load_contract_summaries(db, team_id, journey_ids)
    payment_map = _load_payment_summaries(db, team_id, journey_ids)
    invoice_map = _load_invoice_summaries(db, team_id, journey_ids)
    latest_event_map = _load_latest_event_summaries(db, team_id, journey_ids)
    owner_map = legacy_board_owner_map(db, rows)

    columns_by_key = {
        key: BusinessJourneyBoardColumn(key=key, title=title, description=description, count=0, amount=0, cards=[])
        for key, title, description in BOARD_COLUMNS
    }

    total_amount = 0.0
    active_count = 0
    completed_count = 0
    lost_count = 0

    for journey, customer, opportunity in rows:
        contract_summary = contract_map.get(journey.id, BusinessJourneyContractSummary(count=0, signed_count=0, amount=0))
        payment_summary = payment_map.get(journey.id, BusinessJourneyPaymentSummary(
            plan_count=0,
            record_count=0,
            planned_amount=0,
            paid_amount=0,
            remaining_amount=0,
        ))
        invoice_summary = invoice_map.get(journey.id, BusinessJourneyInvoiceSummary(
            application_count=0,
            issued_count=0,
            applied_amount=0,
            issued_amount=0,
        ))
        stage_key = _infer_stage(journey, opportunity, contract_summary, payment_summary, invoice_summary)
        amount = legacy_board_amount(opportunity, contract_summary)
        total_amount += amount
        if journey.status == DealJourneyStatus.COMPLETED:
            completed_count += 1
        elif journey.status == DealJourneyStatus.LOST:
            lost_count += 1
        else:
            active_count += 1

        owner_id_value = _owner_id_for(journey, customer, opportunity)
        owner = owner_map.get(owner_id_value) if owner_id_value else None
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="业务旅程关联客户数据异常",
            )
        card = BusinessJourneyBoardCard(
            journey_id=journey.id,
            journey_name=journey.name,
            customer_id=customer.public_id,
            customer_name=customer.account_name,
            owner=owner,
            status=journey.status,
            current_board_stage=stage_key,
            started_at=journey.started_at,
            closed_at=journey.closed_at,
            last_event_at=journey.last_event_at,
            last_event_summary=latest_event_map.get(journey.id),
            amount=amount,
            primary_opportunity=legacy_board_opportunity_summary(opportunity),
            contract_summary=contract_summary,
            payment_summary=payment_summary,
            invoice_summary=invoice_summary,
        )
        column = columns_by_key[stage_key]
        column.cards.append(card)
        column.count += 1
        column.amount += amount

    return BusinessJourneyBoardResponse(
        scope=scope,
        period_start=start_date.isoformat() if start_date else None,
        period_end=end_date.isoformat() if end_date else None,
        columns=[columns_by_key[key] for key, _, _ in BOARD_COLUMNS],
        summary=BusinessJourneyBoardSummary(
            total_count=len(rows),
            total_amount=total_amount,
            active_count=active_count,
            completed_count=completed_count,
            lost_count=lost_count,
        ),
    )




def _load_latest_event_summaries(db: Session, team_id: int, journey_ids: list[int]) -> dict[int, str]:
    if not journey_ids:
        return {}

    events = (
        db.query(CustomerDealJourneyEvent)
        .filter(
            CustomerDealJourneyEvent.team_id == team_id,
            CustomerDealJourneyEvent.deal_journey_id.in_(journey_ids),
        )
        .order_by(CustomerDealJourneyEvent.deal_journey_id.asc(), CustomerDealJourneyEvent.event_time.desc())
        .all()
    )
    result: dict[int, str] = {}
    for event in events:
        if event.deal_journey_id not in result and event.summary:
            result[event.deal_journey_id] = event.summary
    return result

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.crud.permission import permission_crud
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent, DealJourneyStatus
from app.models.invoice import InvoiceApplication, InvoiceApplicationStatus
from app.models.opportunity import Opportunity
from app.models.payment import PaymentConfirmationStatus, PaymentPlan, PaymentRecord
from app.models.user import User


router = APIRouter(prefix="/v1/business-journey-board", tags=["业务旅程看板"])

DashboardScope = Literal["own", "team", "all"]
BoardStageKey = Literal[
    "early_communication",
    "active_progress",
    "closing_soon",
    "won_pending_contract",
    "contract_processing",
    "payment_processing",
    "invoice_processing",
    "completed",
    "lost",
]


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


class BusinessJourneyContractSummary(BaseModel):
    count: int
    signed_count: int
    amount: float


class BusinessJourneyPaymentSummary(BaseModel):
    plan_count: int
    record_count: int
    planned_amount: float
    paid_amount: float
    remaining_amount: float


class BusinessJourneyInvoiceSummary(BaseModel):
    application_count: int
    issued_count: int
    applied_amount: float
    issued_amount: float


class BusinessJourneyBoardCard(BaseModel):
    journey_id: int
    journey_name: str
    customer_id: int
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


BOARD_COLUMNS: list[tuple[BoardStageKey, str, str]] = [
    ("early_communication", "初期交流", "赢率低于 50% 或尚未评估的成交旅程"),
    ("active_progress", "持续推进", "赢率 50%-80% 的成交旅程"),
    ("closing_soon", "即将赢单", "赢率 81%-99% 的成交旅程"),
    ("won_pending_contract", "已赢单", "商机已赢单但尚未进入合同处理"),
    ("contract_processing", "签约中", "已创建合同，正在签约或合同履约前置处理"),
    ("payment_processing", "回款中", "已有回款计划或回款记录，合同尚未完成回款"),
    ("invoice_processing", "开票中", "已有发票申请，仍有发票未完成开具"),
    ("completed", "已完成", "旅程已完成闭环"),
    ("lost", "已输单", "商机或旅程已输单"),
]


def _scalar_number(value) -> float:
    if value is None:
        return 0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


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


def _infer_stage(
    journey: CustomerDealJourney,
    opportunity: Opportunity | None,
    contract_summary: BusinessJourneyContractSummary,
    payment_summary: BusinessJourneyPaymentSummary,
    invoice_summary: BusinessJourneyInvoiceSummary,
) -> BoardStageKey:
    if journey.status == DealJourneyStatus.LOST:
        return "lost"
    if journey.status == DealJourneyStatus.COMPLETED:
        return "completed"
    if invoice_summary.application_count > invoice_summary.issued_count:
        return "invoice_processing"
    if payment_summary.plan_count > 0 or payment_summary.record_count > 0:
        return "payment_processing"
    if contract_summary.count > 0:
        return "contract_processing"
    if journey.status == DealJourneyStatus.WON:
        return "won_pending_contract"
    return _infer_active_opportunity_stage(opportunity)


def _infer_active_opportunity_stage(opportunity: Opportunity | None) -> BoardStageKey:
    if opportunity is None:
        return "early_communication"
    win_probability = opportunity.current_win_probability or opportunity.win_probability
    if win_probability is None:
        return "early_communication"
    if win_probability < 50:
        return "early_communication"
    if win_probability <= 80:
        return "active_progress"
    if win_probability < 100:
        return "closing_soon"
    return "won_pending_contract"


@router.get("/", response_model=BusinessJourneyBoardResponse, summary="业务旅程看板")
def get_business_journey_board(
    start_date: date | None = Query(None, description="最近业务动态开始日期"),
    end_date: date | None = Query(None, description="最近业务动态结束日期"),
    owner_id: str | None = Query(None, description="负责人ID，多个用英文逗号分隔"),
    limit: int = Query(500, ge=1, le=1000, description="最多加载的旅程卡片数"),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if start_date and end_date and start_date > end_date:
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
    owner_map = _load_owner_map(db, rows)

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
        amount = _journey_amount(opportunity, contract_summary)
        total_amount += amount
        if journey.status == DealJourneyStatus.COMPLETED:
            completed_count += 1
        elif journey.status == DealJourneyStatus.LOST:
            lost_count += 1
        else:
            active_count += 1

        owner_id_value = _owner_id_for(journey, customer, opportunity)
        owner = owner_map.get(owner_id_value) if owner_id_value else None
        card = BusinessJourneyBoardCard(
            journey_id=journey.id,
            journey_name=journey.name,
            customer_id=journey.customer_id,
            customer_name=customer.account_name if customer else None,
            owner=owner,
            status=journey.status,
            current_board_stage=stage_key,
            started_at=journey.started_at,
            closed_at=journey.closed_at,
            last_event_at=journey.last_event_at,
            last_event_summary=latest_event_map.get(journey.id),
            amount=amount,
            primary_opportunity=_opportunity_summary(opportunity),
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


def _load_contract_summaries(
    db: Session,
    team_id: int,
    journey_ids: list[int],
) -> dict[int, BusinessJourneyContractSummary]:
    if not journey_ids:
        return {}

    rows = (
        db.query(
            Contract.deal_journey_id,
            func.count(Contract.id),
            func.coalesce(func.sum(Contract.total_amount), 0),
            func.sum(case((Contract.signing_date.isnot(None), 1), else_=0)),
        )
        .filter(
            Contract.team_id == team_id,
            Contract.deleted_at.is_(None),
            Contract.deal_journey_id.in_(journey_ids),
        )
        .group_by(Contract.deal_journey_id)
        .all()
    )
    return {
        int(deal_journey_id): BusinessJourneyContractSummary(
            count=int(count or 0),
            signed_count=int(signed_count or 0),
            amount=_scalar_number(amount),
        )
        for deal_journey_id, count, amount, signed_count in rows
        if deal_journey_id is not None
    }


def _load_payment_summaries(
    db: Session,
    team_id: int,
    journey_ids: list[int],
) -> dict[int, BusinessJourneyPaymentSummary]:
    if not journey_ids:
        return {}

    plan_rows = (
        db.query(
            PaymentPlan.deal_journey_id,
            func.count(PaymentPlan.id),
            func.coalesce(func.sum(PaymentPlan.planned_amount), 0),
        )
        .filter(PaymentPlan.team_id == team_id, PaymentPlan.deal_journey_id.in_(journey_ids))
        .group_by(PaymentPlan.deal_journey_id)
        .all()
    )
    record_rows = (
        db.query(
            PaymentRecord.deal_journey_id,
            func.count(PaymentRecord.id),
            func.coalesce(func.sum(PaymentRecord.actual_amount), 0),
        )
        .filter(
            PaymentRecord.team_id == team_id,
            PaymentRecord.deal_journey_id.in_(journey_ids),
            PaymentRecord.confirmation_status == PaymentConfirmationStatus.CONFIRMED,
        )
        .group_by(PaymentRecord.deal_journey_id)
        .all()
    )

    summaries: dict[int, BusinessJourneyPaymentSummary] = {}
    for deal_journey_id, count, amount in plan_rows:
        if deal_journey_id is None:
            continue
        summaries[int(deal_journey_id)] = BusinessJourneyPaymentSummary(
            plan_count=int(count or 0),
            record_count=0,
            planned_amount=_scalar_number(amount),
            paid_amount=0,
            remaining_amount=_scalar_number(amount),
        )

    for deal_journey_id, count, amount in record_rows:
        if deal_journey_id is None:
            continue
        key = int(deal_journey_id)
        summary = summaries.get(key, BusinessJourneyPaymentSummary(
            plan_count=0,
            record_count=0,
            planned_amount=0,
            paid_amount=0,
            remaining_amount=0,
        ))
        paid_amount = _scalar_number(amount)
        summary.record_count = int(count or 0)
        summary.paid_amount = paid_amount
        summary.remaining_amount = max(summary.planned_amount - paid_amount, 0)
        summaries[key] = summary

    return summaries


def _load_invoice_summaries(
    db: Session,
    team_id: int,
    journey_ids: list[int],
) -> dict[int, BusinessJourneyInvoiceSummary]:
    if not journey_ids:
        return {}

    rows = (
        db.query(
            InvoiceApplication.deal_journey_id,
            func.count(InvoiceApplication.id),
            func.coalesce(func.sum(InvoiceApplication.invoice_amount), 0),
            func.sum(case((InvoiceApplication.status == InvoiceApplicationStatus.ISSUED, 1), else_=0)),
            func.coalesce(func.sum(case(
                (InvoiceApplication.status == InvoiceApplicationStatus.ISSUED, InvoiceApplication.invoice_amount),
                else_=0,
            )), 0),
        )
        .filter(InvoiceApplication.team_id == team_id, InvoiceApplication.deal_journey_id.in_(journey_ids))
        .group_by(InvoiceApplication.deal_journey_id)
        .all()
    )
    return {
        int(deal_journey_id): BusinessJourneyInvoiceSummary(
            application_count=int(count or 0),
            issued_count=int(issued_count or 0),
            applied_amount=_scalar_number(applied_amount),
            issued_amount=_scalar_number(issued_amount),
        )
        for deal_journey_id, count, applied_amount, issued_count, issued_amount in rows
        if deal_journey_id is not None
    }


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


def _load_owner_map(db: Session, rows) -> dict[str, BusinessJourneyBoardOwner]:
    owner_ids = {
        owner_id
        for journey, customer, opportunity in rows
        for owner_id in [_owner_id_for(journey, customer, opportunity)]
        if owner_id
    }
    if not owner_ids:
        return {}
    users = db.query(User).filter(User.id.in_([int(owner_id) for owner_id in owner_ids if str(owner_id).isdigit()])).all()
    return {
        str(user.id): BusinessJourneyBoardOwner(id=str(user.id), name=user.name, avatar_url=user.avatar_url)
        for user in users
    }


def _journey_amount(opportunity: Opportunity | None, contract_summary: BusinessJourneyContractSummary) -> float:
    if contract_summary.amount > 0:
        return contract_summary.amount
    if opportunity is None:
        return 0
    return _scalar_number(opportunity.actual_amount or opportunity.total_amount)


def _opportunity_summary(opportunity: Opportunity | None) -> BusinessJourneyOpportunitySummary | None:
    if opportunity is None:
        return None
    return BusinessJourneyOpportunitySummary(
        id=opportunity.id,
        name=opportunity.opportunity_name,
        amount=_scalar_number(opportunity.total_amount),
        actual_amount=_scalar_number(opportunity.actual_amount) if opportunity.actual_amount is not None else None,
        status=opportunity.status,
        current_stage_name=opportunity.current_stage_name,
        win_probability=opportunity.current_win_probability or opportunity.win_probability,
        expected_closing_date=opportunity.expected_closing_date.isoformat() if opportunity.expected_closing_date else None,
    )

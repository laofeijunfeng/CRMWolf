from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.crud.permission import permission_crud
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.invoice import InvoiceApplication, InvoiceApplicationStatus
from app.models.lead import Lead, LeadStatus
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.payment import PaymentConfirmationStatus, PaymentRecord


router = APIRouter(prefix="/v1/sales-dashboard", tags=["销售看板"])

DashboardScope = Literal["own", "team", "all"]


class SalesDashboardMetric(BaseModel):
    key: str
    label: str
    count: int
    amount: float | None = None
    secondary_label: str | None = None
    secondary_value: int | float | None = None
    secondary_type: Literal["count", "amount"] | None = None
    rate_label: str | None = None
    rate: float | None = None


class SalesDashboardFunnelResponse(BaseModel):
    scope: DashboardScope
    period_label: str
    period_start: str
    period_end: str
    metrics: list[SalesDashboardMetric]


def _scalar_number(value) -> float:
    if value is None:
        return 0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _safe_rate(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100, 1)


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


def _month_range() -> tuple[datetime, datetime, str]:
    now = datetime.now()
    start = datetime(now.year, now.month, 1)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1)
    else:
        end = datetime(now.year, now.month + 1, 1)
    return start, end, f"{now.year}年{now.month}月"


def _date_range(start_date: date | None, end_date: date | None) -> tuple[datetime | None, datetime | None]:
    start = datetime.combine(start_date, time.min) if start_date else None
    end = datetime.combine(end_date + timedelta(days=1), time.min) if end_date else None
    return start, end


def _parse_owner_ids(owner_id: str | None) -> list[str]:
    if not owner_id:
        return []
    return [item.strip() for item in owner_id.split(",") if item.strip()]


def _apply_created_time_filter(query, column, start: datetime | None, end: datetime | None):
    if start is not None:
        query = query.filter(column >= start)
    if end is not None:
        query = query.filter(column < end)
    return query


def _apply_owner_filter(query, column, owner_ids: list[str]):
    if owner_ids:
        return query.filter(column.in_(owner_ids))
    return query


@router.get("/funnel", response_model=SalesDashboardFunnelResponse, summary="销售链路看板")
def get_sales_dashboard_funnel(
    start_date: date | None = Query(None, description="统计开始日期"),
    end_date: date | None = Query(None, description="统计结束日期"),
    owner_id: str | None = Query(None, description="销售成员ID，多个用英文逗号分隔"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    scope = _resolve_scope(db, current_user.id, team_id)
    user_id = str(current_user.id)
    month_start, month_end, period_label = _month_range()
    filter_start, filter_end = _date_range(start_date, end_date)
    owner_ids = _parse_owner_ids(owner_id)

    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")

    lead_query = db.query(
        func.count(Lead.id).label("total"),
        func.sum(case((Lead.status == LeadStatus.CONVERTED, 1), else_=0)).label("converted"),
    ).filter(Lead.team_id == team_id)
    customer_query = db.query(
        func.count(Customer.id).label("total"),
        func.sum(case((
            (Customer.created_time >= month_start) & (Customer.created_time < month_end),
            1
        ), else_=0)).label("new_current_month"),
    ).filter(Customer.team_id == team_id)
    opportunity_query = db.query(
        func.count(Opportunity.id).label("total"),
        func.coalesce(func.sum(Opportunity.total_amount), 0).label("amount"),
        func.sum(case((Opportunity.status == OpportunityStatus.WON.value, 1), else_=0)).label("won"),
    ).filter(Opportunity.team_id == team_id)
    contract_query = db.query(
        func.count(Contract.id).label("total"),
        func.coalesce(func.sum(Contract.total_amount), 0).label("amount"),
    ).filter(Contract.team_id == team_id, Contract.deleted_at.is_(None))
    payment_query = db.query(
        func.count(PaymentRecord.id).label("total"),
        func.coalesce(func.sum(PaymentRecord.actual_amount), 0).label("amount"),
    ).filter(
        PaymentRecord.team_id == team_id,
        PaymentRecord.confirmation_status == PaymentConfirmationStatus.CONFIRMED,
    )
    invoice_query = db.query(
        func.count(InvoiceApplication.id).label("total"),
        func.coalesce(func.sum(InvoiceApplication.invoice_amount), 0).label("amount"),
    ).filter(
        InvoiceApplication.team_id == team_id,
        InvoiceApplication.status == InvoiceApplicationStatus.ISSUED,
    )

    lead_query = _apply_created_time_filter(lead_query, Lead.created_time, filter_start, filter_end)
    customer_query = _apply_created_time_filter(customer_query, Customer.created_time, filter_start, filter_end)
    opportunity_query = _apply_created_time_filter(opportunity_query, Opportunity.created_time, filter_start, filter_end)
    contract_query = _apply_created_time_filter(contract_query, Contract.created_time, filter_start, filter_end)
    payment_query = _apply_created_time_filter(payment_query, PaymentRecord.created_time, filter_start, filter_end)
    invoice_query = _apply_created_time_filter(invoice_query, InvoiceApplication.created_time, filter_start, filter_end)

    if scope == "own":
        lead_query = lead_query.filter(or_(Lead.owner_id == user_id, Lead.creator_id == user_id))
        customer_query = customer_query.filter(Customer.owner_id == user_id)
        opportunity_query = opportunity_query.filter(Opportunity.owner_id == user_id)
        contract_query = contract_query.filter(Contract.owner_id == user_id)
        payment_query = payment_query.filter(PaymentRecord.creator_id == user_id)
        invoice_query = invoice_query.filter(InvoiceApplication.applicant_id == user_id)
    else:
        lead_query = _apply_owner_filter(lead_query, Lead.owner_id, owner_ids)
        customer_query = _apply_owner_filter(customer_query, Customer.owner_id, owner_ids)
        opportunity_query = _apply_owner_filter(opportunity_query, Opportunity.owner_id, owner_ids)
        contract_query = _apply_owner_filter(contract_query, Contract.owner_id, owner_ids)
        payment_query = _apply_owner_filter(payment_query, PaymentRecord.creator_id, owner_ids)
        invoice_query = _apply_owner_filter(invoice_query, InvoiceApplication.applicant_id, owner_ids)

    lead_stats = lead_query.one()
    customer_stats = customer_query.one()
    opportunity_stats = opportunity_query.one()
    contract_stats = contract_query.one()
    payment_stats = payment_query.one()
    invoice_stats = invoice_query.one()

    lead_count = int(lead_stats.total or 0)
    converted_lead_count = int(lead_stats.converted or 0)
    customer_count = int(customer_stats.total or 0)
    new_customer_count = int(customer_stats.new_current_month or 0)
    opportunity_count = int(opportunity_stats.total or 0)
    opportunity_amount = _scalar_number(opportunity_stats.amount)
    won_opportunity_count = int(opportunity_stats.won or 0)
    contract_count = int(contract_stats.total or 0)
    contract_amount = _scalar_number(contract_stats.amount)
    payment_count = int(payment_stats.total or 0)
    payment_amount = _scalar_number(payment_stats.amount)
    invoice_count = int(invoice_stats.total or 0)
    invoice_amount = _scalar_number(invoice_stats.amount)

    has_date_filter = filter_start is not None or filter_end is not None

    return SalesDashboardFunnelResponse(
        scope=scope,
        period_label=period_label,
        period_start=month_start.date().isoformat(),
        period_end=month_end.date().isoformat(),
        metrics=[
            SalesDashboardMetric(
                key="leads",
                label="线索",
                count=lead_count,
                secondary_label="已转化",
                secondary_value=converted_lead_count,
                secondary_type="count",
            ),
            SalesDashboardMetric(
                key="customers",
                label="客户",
                count=customer_count,
                secondary_label="筛选期新增" if has_date_filter else "本月新增",
                secondary_value=customer_count if has_date_filter else new_customer_count,
                secondary_type="count",
                rate_label="线索转化率",
                rate=_safe_rate(converted_lead_count, lead_count),
            ),
            SalesDashboardMetric(
                key="opportunities",
                label="商机",
                count=opportunity_count,
                amount=opportunity_amount,
                secondary_label="总金额",
                secondary_value=opportunity_amount,
                secondary_type="amount",
                rate_label="客户转商机率",
                rate=_safe_rate(opportunity_count, customer_count),
            ),
            SalesDashboardMetric(
                key="contracts",
                label="合同",
                count=contract_count,
                amount=contract_amount,
                secondary_label="总金额",
                secondary_value=contract_amount,
                secondary_type="amount",
                rate_label="商机赢单率",
                rate=_safe_rate(won_opportunity_count, opportunity_count),
            ),
            SalesDashboardMetric(
                key="payments",
                label="回款",
                count=payment_count,
                amount=payment_amount,
                secondary_label="总金额",
                secondary_value=payment_amount,
                secondary_type="amount",
                rate_label="合同回款率",
                rate=_safe_rate(payment_amount, contract_amount),
            ),
            SalesDashboardMetric(
                key="invoices",
                label="发票",
                count=invoice_count,
                amount=invoice_amount,
                secondary_label="总金额",
                secondary_value=invoice_amount,
                secondary_type="amount",
                rate_label="合同开票率",
                rate=_safe_rate(invoice_amount, contract_amount),
            ),
        ],
    )

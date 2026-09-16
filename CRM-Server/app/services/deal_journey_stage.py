from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.contract import Contract
from app.models.deal_journey import CustomerDealJourney, DealJourneyStatus
from app.models.invoice import InvoiceApplication, InvoiceApplicationStatus
from app.models.opportunity import Opportunity
from app.models.payment import PaymentConfirmationStatus, PaymentPlan, PaymentRecord

BoardStageKey = Literal[
    "early_communication",
    "active_progress",
    "closing_soon",
    "contract_processing",
    "payment_processing",
    "invoice_processing",
    "completed",
    "lost",
]

BOARD_STAGE_LABELS: dict[BoardStageKey, str] = {
    "early_communication": "初期交流",
    "active_progress": "持续推进",
    "closing_soon": "即将签约",
    "contract_processing": "签约中",
    "payment_processing": "回款中",
    "invoice_processing": "开票中",
    "completed": "已完成",
    "lost": "已输单",
}


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


def _scalar_number(value) -> float:
    if value is None:
        return 0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def infer_board_stage(
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
        return "closing_soon"
    return infer_active_opportunity_stage(opportunity)


def infer_active_opportunity_stage(opportunity: Opportunity | None) -> BoardStageKey:
    if opportunity is None:
        return "early_communication"
    win_probability = opportunity.current_win_probability or opportunity.win_probability
    if win_probability is None:
        return "early_communication"
    if win_probability < 50:
        return "early_communication"
    if win_probability < 80:
        return "active_progress"
    return "closing_soon"


def load_contract_summaries(
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


def load_payment_summaries(
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


def load_invoice_summaries(
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

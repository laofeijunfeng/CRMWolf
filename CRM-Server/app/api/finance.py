from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.core.database import get_db
from app.core.deps import get_current_active_user, require_permission, get_current_user_team
from app.crud.permission import permission_crud
from app.models.user import User
from app.models.payment import PaymentPlan, PaymentRecord, PaymentPlanStatus, PaymentConfirmationStatus
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.invoice import InvoiceApplication
from app.schemas.payment import (
    PaymentRecordConfirm,
    PaymentRecordWithConfirmation,
    PaymentPlanResponse
)
from app.crud.payment import payment_record_crud, payment_plan_crud

router = APIRouter(prefix="/finance", tags=["财务管理"])


@router.post(
    "/payment-records/{record_id}/confirm",
    response_model=PaymentRecordWithConfirmation,
    summary="确认回款入账",
    description="财务角色确认销售登记的回款记录，支持关联发票申请"
)
def confirm_payment_record(
    record_id: int,
    confirm_data: PaymentRecordConfirm,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("payment:confirm")),
    db: Session = Depends(get_db)
):
    record = payment_record_crud.get_by_id(db, record_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回款记录不存在"
        )

    # 验证回款记录所属合同属于当前团队
    payment_plan = db.query(PaymentPlan).filter(
        PaymentPlan.id == record.payment_plan_id
    ).first()
    if payment_plan:
        contract = db.query(Contract).filter(
            Contract.id == payment_plan.contract_id
        ).first()
        if contract and contract.team_id != team_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="回款记录不存在或不属于当前团队"
            )
    
    if confirm_data.action not in ["confirm", "dispute"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="action 参数必须为 confirm 或 dispute"
        )
    
    if confirm_data.invoice_application_ids:
        total_invoice_amount = Decimal(0)
        for inv_id in confirm_data.invoice_application_ids:
            inv_app = db.query(InvoiceApplication).filter(
                InvoiceApplication.id == inv_id
            ).first()
            if not inv_app:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"发票申请 {inv_id} 不存在"
                )
            
            payment_plan = db.query(PaymentPlan).filter(
                PaymentPlan.id == record.payment_plan_id
            ).first()
            if not payment_plan or inv_app.contract_id != payment_plan.contract_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"发票申请 {inv_id} 不属于该回款记录关联合同"
                )
            
            total_invoice_amount += inv_app.invoice_amount
        
        if total_invoice_amount > record.actual_amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"关联发票总金额({total_invoice_amount})超过回款金额({record.actual_amount})"
            )
    
    try:
        confirmed_record = payment_record_crud.confirm_payment(
            db,
            record_id,
            str(current_user.id),
            current_user.name,
            confirm_data.action,
            confirm_data.notes,
            confirm_data.invoice_application_ids
        )
        
        if not confirmed_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="回款记录不存在"
            )
        
        return _populate_record_info(db, confirmed_record)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


def _populate_record_info(db: Session, record: PaymentRecord) -> dict:
    payment_plan = db.query(PaymentPlan).filter(
        PaymentPlan.id == record.payment_plan_id
    ).first()
    
    contract = None
    customer = None
    opportunity = None
    
    if payment_plan:
        contract = db.query(Contract).filter(
            Contract.id == payment_plan.contract_id
        ).first()
        
        if contract:
            if contract.customer_id:
                customer = db.query(Customer).filter(
                    Customer.id == contract.customer_id
                ).first()
            
            if contract.opportunity_id:
                opportunity = db.query(Opportunity).filter(
                    Opportunity.id == contract.opportunity_id
                ).first()
    
    return {
        "id": record.id,
        "payment_plan_id": record.payment_plan_id,
        "actual_amount": float(record.actual_amount),
        "payment_date": record.payment_date,
        "proof_attachment": record.proof_attachment,
        "notes": record.notes,
        "creator_id": record.creator_id,
        "creator_name": record.creator_name,
        "created_time": record.created_time,
        "confirmation_status": record.confirmation_status,
        "confirmed_by": record.confirmed_by,
        "confirmed_by_name": record.confirmed_by_name,
        "confirmed_time": record.confirmed_time,
        "confirmation_notes": record.confirmation_notes,
        "contract_id": contract.id if contract else None,
        "contract_name": contract.contract_name if contract else None,
        "stage_name": payment_plan.stage_name if payment_plan else None,
        "customer_id": customer.id if customer else None,
        "customer_name": customer.account_name if customer else None,
        "opportunity_id": opportunity.id if opportunity else None,
        "opportunity_name": opportunity.opportunity_name if opportunity else None
    }


@router.get(
    "/receivables/aging-analysis",
    summary="应收账款账龄分析",
    description="按时间区间统计逾期应收账款金额，帮助评估坏账风险"
)
def get_receivables_aging_analysis(
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("finance:receivables_view")),
    db: Session = Depends(get_db)
):
    today = date.today()

    aging_buckets = {
        "0-30天": {"days_start": 0, "days_end": 30, "amount": Decimal(0), "count": 0},
        "31-60天": {"days_start": 31, "days_end": 60, "amount": Decimal(0), "count": 0},
        "61-90天": {"days_start": 61, "days_end": 90, "amount": Decimal(0), "count": 0},
        "90天以上": {"days_start": 91, "days_end": 999999, "amount": Decimal(0), "count": 0}
    }

    query = db.query(PaymentPlan).join(Contract).filter(
        PaymentPlan.status.in_([PaymentPlanStatus.PENDING, PaymentPlanStatus.PARTIAL, PaymentPlanStatus.OVERDUE]),
        PaymentPlan.due_date < today,
        Contract.team_id == team_id
    )
    
    if start_date:
        query = query.filter(PaymentPlan.due_date >= start_date)
    
    if end_date:
        query = query.filter(PaymentPlan.due_date <= end_date)
    
    overdue_plans = query.all()
    
    total_overdue_amount = Decimal(0)
    details = []
    
    for plan in overdue_plans:
        paid_amount = sum(Decimal(str(r.actual_amount)) for r in plan.payment_records)
        remaining_amount = plan.planned_amount - paid_amount
        
        if remaining_amount <= 0:
            continue
        
        days_overdue = (today - plan.due_date).days
        
        total_overdue_amount += remaining_amount
        
        for bucket_name, bucket in aging_buckets.items():
            if bucket["days_start"] <= days_overdue <= bucket["days_end"]:
                bucket["amount"] += remaining_amount
                bucket["count"] += 1
                break
        
        contract = db.query(Contract).filter(Contract.id == plan.contract_id).first()
        customer = None
        if contract and contract.customer_id:
            customer = db.query(Customer).filter(Customer.id == contract.customer_id).first()
        
        details.append({
            "plan_id": plan.id,
            "stage_name": plan.stage_name,
            "planned_amount": float(plan.planned_amount),
            "paid_amount": float(paid_amount),
            "remaining_amount": float(remaining_amount),
            "due_date": plan.due_date.isoformat(),
            "days_overdue": days_overdue,
            "contract_id": contract.id if contract else None,
            "contract_name": contract.contract_name if contract else None,
            "customer_id": customer.id if customer else None,
            "customer_name": customer.account_name if customer else None
        })
    
    result_buckets = []
    for bucket_name, bucket in aging_buckets.items():
        result_buckets.append({
            "range": bucket_name,
            "amount": float(bucket["amount"]),
            "count": bucket["count"]
        })
    
    return {
        "summary": {
            "total_overdue_amount": float(total_overdue_amount),
            "total_overdue_plans": len(overdue_plans),
            "analysis_date": today.isoformat()
        },
        "aging_analysis": result_buckets,
        "details": sorted(details, key=lambda x: x["days_overdue"], reverse=True)
    }


@router.get(
    "/receivables/overdue-alerts",
    summary="逾期回款预警列表",
    description="获取所有逾期回款计划列表，用于催收管理"
)
def get_overdue_alerts(
    days_overdue_min: Optional[int] = Query(None, description="最小逾期天数"),
    days_overdue_max: Optional[int] = Query(None, description="最大逾期天数"),
    min_amount: Optional[float] = Query(None, description="最小欠款金额"),
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的记录数"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("finance:receivables_view")),
    db: Session = Depends(get_db)
):
    today = date.today()

    query = db.query(PaymentPlan).join(Contract).filter(
        PaymentPlan.status.in_([PaymentPlanStatus.PENDING, PaymentPlanStatus.PARTIAL, PaymentPlanStatus.OVERDUE]),
        PaymentPlan.due_date < today,
        Contract.team_id == team_id
    )
    
    overdue_plans = query.order_by(PaymentPlan.due_date.asc()).all()
    
    alerts = []
    for plan in overdue_plans:
        paid_amount = sum(Decimal(str(r.actual_amount)) for r in plan.payment_records)
        remaining_amount = plan.planned_amount - paid_amount
        
        if remaining_amount <= 0:
            continue
        
        days_overdue = (today - plan.due_date).days
        
        if days_overdue_min and days_overdue < days_overdue_min:
            continue
        
        if days_overdue_max and days_overdue > days_overdue_max:
            continue
        
        if min_amount and float(remaining_amount) < min_amount:
            continue
        
        contract = db.query(Contract).filter(Contract.id == plan.contract_id).first()
        customer = None
        opportunity = None
        
        if contract:
            if contract.customer_id:
                customer = db.query(Customer).filter(Customer.id == contract.customer_id).first()
            
            if contract.opportunity_id:
                opportunity = db.query(Opportunity).filter(
                    Opportunity.id == contract.opportunity_id
                ).first()
        
        alerts.append({
            "plan_id": plan.id,
            "contract_id": contract.id if contract else None,
            "contract_name": contract.contract_name if contract else None,
            "stage_name": plan.stage_name,
            "planned_amount": float(plan.planned_amount),
            "paid_amount": float(paid_amount),
            "remaining_amount": float(remaining_amount),
            "due_date": plan.due_date.isoformat(),
            "days_overdue": days_overdue,
            "customer_id": customer.id if customer else None,
            "customer_name": customer.account_name if customer else None,
            "opportunity_id": opportunity.id if opportunity else None,
            "opportunity_name": opportunity.opportunity_name if opportunity else None,
            "owner_id": contract.creator_id if contract else None,
            "owner_name": contract.creator_name if contract else None
        })
    
    total = len(alerts)
    paginated_alerts = alerts[skip:skip + limit]
    
    return {
        "items": paginated_alerts,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get(
    "/reports/contract-revenue",
    summary="合同收入统计报表",
    description="按时间、产品、客户维度统计合同收入、实收金额、欠款金额等"
)
def get_contract_revenue_report(
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    group_by: str = Query("month", description="分组方式: day(按天), week(按周), month(按月), customer(按客户)"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("finance:reports_view")),
    db: Session = Depends(get_db)
):
    query = db.query(Contract).filter(
        Contract.status != "DRAFT",
        Contract.team_id == team_id
    )
    
    if start_date:
        query = query.filter(Contract.created_time >= start_date)
    
    if end_date:
        query = query.filter(Contract.created_time <= end_date)
    
    contracts = query.all()
    
    if group_by == "customer":
        return _group_by_customer(contracts, db)
    else:
        return _group_by_time(contracts, group_by, db)


def _group_by_time(contracts: List[Contract], group_by: str, db: Session) -> dict:
    groups = {}
    
    for contract in contracts:
        if group_by == "day":
            key = contract.created_time.strftime("%Y-%m-%d")
        elif group_by == "week":
            key = contract.created_time.strftime("%Y-W%W")
        else:  # month
            key = contract.created_time.strftime("%Y-%m")
        
        if key not in groups:
            groups[key] = {
                "period": key,
                "contract_count": 0,
                "total_amount": Decimal(0),
                "total_paid": Decimal(0),
                "total_pending": Decimal(0)
            }
        
        groups[key]["contract_count"] += 1
        groups[key]["total_amount"] += Decimal(str(contract.total_amount or 0))
        groups[key]["total_paid"] += Decimal(str(contract.total_paid_amount or 0))
        groups[key]["total_pending"] += Decimal(str(contract.total_amount or 0)) - Decimal(str(contract.total_paid_amount or 0))
    
    result = sorted(groups.values(), key=lambda x: x["period"])
    
    return {
        "group_by": group_by,
        "data": [
            {
                **item,
                "total_amount": float(item["total_amount"]),
                "total_paid": float(item["total_paid"]),
                "total_pending": float(item["total_pending"])
            }
            for item in result
        ]
    }


def _group_by_customer(contracts: List[Contract], db: Session) -> dict:
    groups = {}
    
    for contract in contracts:
        customer = None
        if contract.customer_id:
            customer = db.query(Customer).filter(Customer.id == contract.customer_id).first()
        
        key = str(contract.customer_id) if contract.customer_id else "unknown"
        
        if key not in groups:
            groups[key] = {
                "customer_id": contract.customer_id,
                "customer_name": customer.account_name if customer else "未知客户",
                "contract_count": 0,
                "total_amount": Decimal(0),
                "total_paid": Decimal(0),
                "total_pending": Decimal(0)
            }
        
        groups[key]["contract_count"] += 1
        groups[key]["total_amount"] += Decimal(str(contract.total_amount or 0))
        groups[key]["total_paid"] += Decimal(str(contract.total_paid_amount or 0))
        groups[key]["total_pending"] += Decimal(str(contract.total_amount or 0)) - Decimal(str(contract.total_paid_amount or 0))
    
    result = sorted(groups.values(), key=lambda x: x["total_amount"], reverse=True)
    
    return {
        "group_by": "customer",
        "data": [
            {
                **item,
                "total_amount": float(item["total_amount"]),
                "total_paid": float(item["total_paid"]),
                "total_pending": float(item["total_pending"])
            }
            for item in result
        ]
    }


@router.get(
    "/pending-confirmations",
    summary="待确认回款列表",
    description="获取所有待财务确认的回款记录"
)
def get_pending_confirmations(
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的记录数"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("payment:confirm")),
    db: Session = Depends(get_db)
):
    # 通过 PaymentPlan -> Contract 关联过滤 team_id
    query = db.query(PaymentRecord).join(
        PaymentPlan, PaymentRecord.payment_plan_id == PaymentPlan.id
    ).join(
        Contract, PaymentPlan.contract_id == Contract.id
    ).filter(
        PaymentRecord.confirmation_status == PaymentConfirmationStatus.PENDING,
        Contract.team_id == team_id
    ).order_by(PaymentRecord.created_time.desc())
    
    total = query.count()
    records = query.offset(skip).limit(limit).all()
    
    items = []
    for record in records:
        items.append(_populate_record_info(db, record))
    
    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit
    }

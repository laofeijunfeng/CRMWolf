from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import date

from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.crud.payment import payment_plan_crud, payment_record_crud
from app.crud.contract import contract_crud
from app.models.payment import PaymentPlanStatus
from app.schemas.payment import (
    PaymentPlanCreate, PaymentPlanUpdate, PaymentPlanBatchCreate, PaymentPlanResponse,
    PaymentRecordCreate, PaymentRecordUpdate, PaymentRecordResponse,
    ContractPaymentSummary, PaymentReminder, PaginatedResponse
)


router = APIRouter(prefix="/api/v1/payments", tags=["回款管理"])


@router.post("/contracts/{contract_id}/payment-plans", response_model=List[PaymentPlanResponse], status_code=status.HTTP_201_CREATED, summary="创建回款计划", description="为指定合同创建回款计划，支持批量创建多个阶段。只有已签署或已生效的合同可以创建回款计划，所有阶段的计划金额之和不能超过合同总金额。返回创建成功的回款计划列表。")
def create_payment_plans(
    contract_id: int,
    plans_data: PaymentPlanBatchCreate,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    contract = contract_crud.get_by_id(db, contract_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合同不存在"
        )
    
    from app.models.contract import ContractStatus
    if contract.status not in [ContractStatus.SIGNED, ContractStatus.EFFECTIVE]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"只有已签署或已生效的合同可以创建回款计划，当前状态: {contract.status}"
        )
    
    try:
        plans = payment_plan_crud.batch_create(db, contract_id, plans_data.plans, current_user.feishu_open_id)
        return plans
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建回款计划失败: {str(e)}"
        )


@router.get("/contracts/{contract_id}/payment-plans", response_model=List[PaymentPlanResponse], summary="查询合同回款计划", description="获取指定合同下的所有回款计划，包括计划金额、已回款金额、待回款金额等信息。支持按回款状态筛选（PENDING待回款、OVERDUE已逾期、PARTIAL部分回款、COMPLETED已完成）。")
def get_payment_plans(
    contract_id: int,
    status: Optional[str] = Query(None, description="回款状态筛选"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    contract = contract_crud.get_by_id(db, contract_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合同不存在"
        )
    
    plans = payment_plan_crud.get_by_contract_id(db, contract_id, status)
    
    for plan in plans:
        paid_amount = sum(float(r.actual_amount) for r in plan.payment_records)
        plan.paid_amount = paid_amount
        plan.remaining_amount = float(plan.planned_amount) - paid_amount
    
    return plans


@router.get("/payment-plans", response_model=PaginatedResponse[PaymentPlanResponse], summary="查询回款计划列表", description="支持按状态、负责人、日期范围等条件筛选并分页查询回款计划。返回计划详情及关联的客户、商机、合同信息。可用于前端表格渲染和数据筛选。")
def list_payment_plans(
    status: Optional[str] = Query(None, description="回款状态筛选：PENDING, OVERDUE, PARTIAL, COMPLETED"),
    owner_id: Optional[str] = Query(None, description="负责人飞书ID（合同创建人）"),
    me: bool = Query(False, description="是否只查询当前用户的计划"),
    due_date_start: Optional[date] = Query(None, description="计划回款日期起始（YYYY-MM-DD）"),
    due_date_end: Optional[date] = Query(None, description="计划回款日期结束（YYYY-MM-DD）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * page_size
    
    current_user_id = current_user.feishu_open_id if me else None
    
    try:
        plans, total = payment_plan_crud.list_plans(
            db,
            skip=skip,
            limit=page_size,
            status=status,
            owner_id=owner_id,
            due_date_start=due_date_start,
            due_date_end=due_date_end,
            current_user_id=current_user_id
        )
        
        for plan in plans:
            paid_amount = sum(float(r.actual_amount) for r in plan.payment_records)
            plan.paid_amount = paid_amount
            plan.remaining_amount = float(plan.planned_amount) - paid_amount
            if hasattr(plan, 'contract') and plan.contract:
                plan.contract_name = plan.contract.contract_name
                plan.creator_id = plan.contract.creator_id
                if hasattr(plan.contract, 'customer') and plan.contract.customer:
                    plan.customer_id = plan.contract.customer.id
                    plan.customer_name = plan.contract.customer.account_name
                if hasattr(plan.contract, 'opportunity') and plan.contract.opportunity:
                    plan.opportunity_id = plan.contract.opportunity.id
                    plan.opportunity_name = plan.contract.opportunity.opportunity_name
        
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        
        return PaginatedResponse[PaymentPlanResponse](
            items=plans,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询回款计划失败: {str(e)}"
        )


@router.get("/contracts/{contract_id}/payment-summary", response_model=ContractPaymentSummary, summary="查询合同回款汇总", description="获取指定合同的回款汇总信息，包括合同金额、已回款金额、回款状态、计划完成情况等")
def get_payment_summary(
    contract_id: int,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.contract import Contract
    from app.models.customer import Customer
    from app.models.opportunity import Opportunity
    
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合同不存在"
        )
    
    plans = payment_plan_crud.get_by_contract_id(db, contract_id)
    
    completed_count = sum(1 for p in plans if p.status == PaymentPlanStatus.COMPLETED)
    overdue_count = sum(1 for p in plans if p.status == PaymentPlanStatus.OVERDUE)
    total_planned = sum(float(p.planned_amount) for p in plans)
    
    customer_id = None
    customer_name = None
    opportunity_id = None
    opportunity_name = None
    
    if contract.customer_id:
        customer = db.query(Customer).filter(Customer.id == contract.customer_id).first()
        if customer:
            customer_id = customer.id
            customer_name = customer.account_name
    
    if contract.opportunity_id:
        opportunity = db.query(Opportunity).filter(Opportunity.id == contract.opportunity_id).first()
        if opportunity:
            opportunity_id = opportunity.id
            opportunity_name = opportunity.opportunity_name
    
    return ContractPaymentSummary(
        contract_id=contract.id,
        contract_name=contract.contract_name,
        total_amount=float(contract.total_amount),
        total_paid_amount=float(contract.total_paid_amount),
        payment_status=contract.payment_status,
        payment_plans_count=len(plans),
        completed_plans_count=completed_count,
        overdue_plans_count=overdue_count,
        remaining_amount=total_planned - float(contract.total_paid_amount),
        customer_id=customer_id,
        customer_name=customer_name,
        opportunity_id=opportunity_id,
        opportunity_name=opportunity_name
    )


@router.put("/payment-plans/{plan_id}", response_model=PaymentPlanResponse, summary="修改回款计划", description="修改指定的回款计划。已完成的计划或已有回款记录的计划不能修改金额和日期，只能修改阶段名称和备注。")
def update_payment_plan(
    plan_id: int,
    plan_data: PaymentPlanUpdate,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    plan = payment_plan_crud.get_by_id(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回款计划不存在"
        )
    
    if plan.status in [PaymentPlanStatus.COMPLETED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="已完成的回款计划不能修改"
        )
    
    if plan.payment_records:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="存在关联的回款记录，不能修改金额和日期"
        )
    
    try:
        updated_plan = payment_plan_crud.update(db, plan, plan_data)
        paid_amount = sum(float(r.actual_amount) for r in updated_plan.payment_records)
        updated_plan.paid_amount = paid_amount
        updated_plan.remaining_amount = float(updated_plan.planned_amount) - paid_amount
        return updated_plan
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/payment-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除回款计划", description="删除指定的回款计划。存在关联回款记录的计划不能删除，删除后无法恢复。")
def delete_payment_plan(
    plan_id: int,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    try:
        success = payment_plan_crud.delete(db, plan_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="回款计划不存在"
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/payment-plans/{plan_id}/records", response_model=PaymentRecordResponse, status_code=status.HTTP_201_CREATED, summary="登记回款", description="为指定的回款计划登记回款记录。系统会自动校验回款金额，确保累计回款不超过计划金额。登记后自动更新计划状态和合同回款状态。返回创建成功的回款记录。")
def create_payment_record(
    plan_id: int,
    record_data: PaymentRecordCreate,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    plan = payment_plan_crud.get_by_id(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回款计划不存在"
        )
    
    if plan.status == PaymentPlanStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该回款计划已完成，无法继续登记回款"
        )
    
    try:
        record = payment_record_crud.create(
            db,
            plan_id,
            record_data,
            current_user.feishu_open_id,
            current_user.name
        )
        return record
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"登记回款失败: {str(e)}"
        )


@router.get("/payment-plans/{plan_id}/records", response_model=List[PaymentRecordResponse], summary="查询回款记录", description="获取指定回款计划下的所有回款记录，按回款日期倒序排列。包含每笔回款的详细信息，如回款金额、回款日期、登记人等。")
def get_payment_records(
    plan_id: int,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    plan = payment_plan_crud.get_by_id(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回款计划不存在"
        )
    
    return payment_record_crud.get_by_plan_id(db, plan_id)


@router.put("/payment-records/{record_id}", response_model=PaymentRecordResponse, summary="更新回款记录", description="更新指定的回款记录。更新后会自动重新计算相关金额、计划状态和合同回款状态。支持修改回款金额、回款日期、凭证附件和备注信息。")
def update_payment_record(
    record_id: int,
    record_data: PaymentRecordUpdate,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    record = payment_record_crud.get_by_id(db, record_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回款记录不存在"
        )
    
    try:
        updated_record = payment_record_crud.update(db, record, record_data)
        return updated_record
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/payment-records/{record_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除回款记录", description="删除指定的回款记录。删除后会自动重新计算相关金额、计划状态和合同回款状态。删除后无法恢复，请谨慎操作。")
def delete_payment_record(
    record_id: int,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    try:
        success = payment_record_crud.delete(db, record_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="回款记录不存在"
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/payment-records", response_model=PaginatedResponse[PaymentRecordResponse], summary="查询回款记录列表", description="支持按合同、计划、日期范围、金额等条件筛选并分页查询回款记录。返回记录详情及关联的客户、商机、合同、回款阶段信息。可用于前端表格渲染和回款历史查询。")
def list_payment_records(
    contract_id: Optional[int] = Query(None, description="合同ID筛选"),
    payment_plan_id: Optional[int] = Query(None, description="回款计划ID筛选"),
    payment_date_start: Optional[date] = Query(None, description="回款日期起始（YYYY-MM-DD）"),
    payment_date_end: Optional[date] = Query(None, description="回款日期结束（YYYY-MM-DD）"),
    min_amount: Optional[float] = Query(None, ge=0, description="最小回款金额"),
    creator_id: Optional[str] = Query(None, description="登记人飞书ID"),
    me: bool = Query(False, description="是否只查询当前用户登记的记录"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * page_size
    
    current_user_id = current_user.feishu_open_id if me else None
    
    try:
        records, total = payment_record_crud.list_records(
            db,
            skip=skip,
            limit=page_size,
            contract_id=contract_id,
            payment_plan_id=payment_plan_id,
            payment_date_start=payment_date_start,
            payment_date_end=payment_date_end,
            min_amount=min_amount,
            creator_id=creator_id,
            current_user_id=current_user_id
        )
        
        for record in records:
            if hasattr(record, 'payment_plan') and record.payment_plan:
                record.contract_id = record.payment_plan.contract_id
                if hasattr(record.payment_plan, 'contract') and record.payment_plan.contract:
                    record.contract_name = record.payment_plan.contract.contract_name
                    if hasattr(record.payment_plan.contract, 'customer') and record.payment_plan.contract.customer:
                        record.customer_id = record.payment_plan.contract.customer.id
                        record.customer_name = record.payment_plan.contract.customer.account_name
                    if hasattr(record.payment_plan.contract, 'opportunity') and record.payment_plan.contract.opportunity:
                        record.opportunity_id = record.payment_plan.contract.opportunity.id
                        record.opportunity_name = record.payment_plan.contract.opportunity.opportunity_name
                record.stage_name = record.payment_plan.stage_name
        
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        
        return PaginatedResponse[PaymentRecordResponse](
            items=records,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询回款记录失败: {str(e)}"
        )


@router.get("/reminders/upcoming", response_model=List[PaymentReminder], summary="查询即将到期的回款", description="获取指定天数内即将到期的回款计划，用于提醒。支持查询未来1-30天内的回款计划")
def get_upcoming_payments(
    days: int = Query(7, ge=1, le=30, description="查询天数范围，默认7天，可设置1-30天"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    plans = payment_plan_crud.get_upcoming_payments(db, days)
    
    reminders = []
    for plan in plans:
        days_until = (plan.due_date - date.today()).days
        
        customer_name = None
        opportunity_name = None
        
        if hasattr(plan, 'contract') and plan.contract:
            if hasattr(plan.contract, 'customer') and plan.contract.customer:
                customer_name = plan.contract.customer.account_name
            if hasattr(plan.contract, 'opportunity') and plan.contract.opportunity:
                opportunity_name = plan.contract.opportunity.opportunity_name
        
        reminders.append(PaymentReminder(
            plan_id=plan.id,
            contract_name=plan.contract.contract_name,
            stage_name=plan.stage_name,
            planned_amount=float(plan.planned_amount),
            due_date=plan.due_date,
            days_until_due=days_until,
            contract_owner_id=plan.contract.creator_id,
            customer_name=customer_name,
            opportunity_name=opportunity_name
        ))
    
    return reminders


@router.get("/reminders/overdue", response_model=List[PaymentReminder], summary="查询逾期回款", description="获取所有逾期的回款计划，用于催收提醒")
def get_overdue_payments(
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    plans = payment_plan_crud.get_overdue_payments(db)
    
    reminders = []
    for plan in plans:
        days_overdue = (date.today() - plan.due_date).days
        
        customer_name = None
        opportunity_name = None
        
        if hasattr(plan, 'contract') and plan.contract:
            if hasattr(plan.contract, 'customer') and plan.contract.customer:
                customer_name = plan.contract.customer.account_name
            if hasattr(plan.contract, 'opportunity') and plan.contract.opportunity:
                opportunity_name = plan.contract.opportunity.opportunity_name
        
        reminders.append(PaymentReminder(
            plan_id=plan.id,
            contract_name=plan.contract.contract_name,
            stage_name=plan.stage_name,
            planned_amount=float(plan.planned_amount),
            due_date=plan.due_date,
            days_until_due=-days_overdue,
            contract_owner_id=plan.contract.creator_id,
            customer_name=customer_name,
            opportunity_name=opportunity_name
        ))
    
    return reminders

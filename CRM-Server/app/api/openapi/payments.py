"""
回款开放接口路由
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Body
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.api.openapi.deps import require_api_permission, verify_api_key
from app.crud.payment import payment_plan_crud, payment_record_crud
from app.crud.contract import contract_crud
from app.models.api_key import ApiKey
from app.models.contract import ContractStatus
from app.models.payment import PaymentPlanStatus
from app.schemas.openapi.common import OpenApiResponse, success_response, paginated_response
from app.schemas.openapi.payment import (
    OpenApiPaymentPlanCreate, OpenApiPaymentRecordCreate,
    OpenApiPaymentPlanResponse, OpenApiPaymentRecordResponse,
    OpenApiPaymentRecordCreateResponse, OpenApiPaymentSummaryResponse,
    OpenApiOverdueReminder,
    PAYMENT_PLAN_STATUS_NAMES, PAYMENT_METHOD_NAMES
)

router = APIRouter()


@router.post("/contracts/{contract_id}/payment-plans", summary="创建回款计划", description="为合同创建回款计划")
async def create_payment_plans(
    contract_id: int = Path(..., description="合同ID"),
    data: OpenApiPaymentPlanCreate = Body(..., description="回款计划数据"),
    api_key: ApiKey = Depends(require_api_permission("payment:create")),
    db: Session = Depends(get_db)
):
    """创建回款计划接口"""
    contract = contract_crud.get_by_id(db, contract_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合同不存在"
        )

    if contract.status not in [ContractStatus.SIGNED, ContractStatus.EFFECTIVE]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有已签署或生效的合同可以创建回款计划"
        )

    # 创建回款计划
    created_plans = []
    for plan_item in data.plans:
        plan = payment_plan_crud.create(
            db=db,
            contract_id=contract_id,
            stage_name=plan_item.stage_name,
            planned_amount=plan_item.planned_amount,
            due_date=plan_item.due_date
        )
        created_plans.append({"plan_id": plan.id, "stage_name": plan.stage_name})

    return success_response({"plans": created_plans, "total": len(created_plans)}, message="回款计划创建成功")


@router.get("/payment-plans", summary="查询回款计划列表", description="查询回款计划列表")
async def get_payment_plans(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    status: Optional[str] = Query(None, description="回款计划状态筛选"),
    contract_id: Optional[int] = Query(None, description="合同ID筛选"),
    api_key: ApiKey = Depends(require_api_permission("payment:list")),
    db: Session = Depends(get_db)
):
    """查询回款计划列表接口"""
    skip = (page - 1) * page_size

    # get_multi 可能返回 list 或 (list, total)，需要处理
    result = payment_plan_crud.get_multi(db, skip=skip, limit=page_size)
    if isinstance(result, tuple):
        plans, total = result
    else:
        plans = result
        total = len(plans)

    # 转换为开放接口响应格式
    items = []
    for plan in plans:
        # 计算已回款金额
        paid_amount = 0
        records = payment_record_crud.get_by_plan(db, plan.id)
        for record in records:
            paid_amount += float(record.actual_amount)

        items.append(OpenApiPaymentPlanResponse(
            plan_id=plan.id,
            contract_id=plan.contract_id,
            contract_name=plan.contract.contract_name if plan.contract else "",
            stage_name=plan.stage_name,
            planned_amount=float(plan.planned_amount),
            paid_amount=paid_amount,
            remaining_amount=float(plan.planned_amount) - paid_amount,
            due_date=plan.due_date,
            status=plan.status or "PENDING",
            status_name=PAYMENT_PLAN_STATUS_NAMES.get(plan.status, "待回款") if plan.status else "待回款"
        ))

    return paginated_response(items, total, page, page_size)


@router.post("/payment-plans/{plan_id}/records", summary="登记回款", description="登记实际回款")
async def create_payment_record(
    plan_id: int = Path(..., description="回款计划ID"),
    data: OpenApiPaymentRecordCreate = Body(..., description="回款记录数据"),
    api_key: ApiKey = Depends(require_api_permission("payment:create")),
    db: Session = Depends(get_db)
):
    """登记回款接口"""
    plan = payment_plan_crud.get_by_id(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回款计划不存在"
        )

    # 校验合同状态
    contract = contract_crud.get_by_id(db, plan.contract_id)
    if not contract or contract.status not in [ContractStatus.SIGNED, ContractStatus.EFFECTIVE]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="合同状态不允许登记回款"
        )

    # 创建回款记录
    from app.models.payment import PaymentMethod
    method = PaymentMethod.TRANSFER if data.payment_method else None
    if data.payment_method:
        method = PaymentMethod(data.payment_method.value)

    record = payment_record_crud.create(
        db=db,
        payment_plan_id=plan_id,
        actual_amount=data.actual_amount,
        payment_date=data.payment_time,
        payment_method=method,
        notes=data.remark,
        creator_id="openapi_system",
        creator_name="开放接口"
    )

    # 更新回款计划状态
    paid_amount = 0
    records = payment_record_crud.get_by_plan(db, plan_id)
    for r in records:
        paid_amount += float(r.actual_amount)

    if paid_amount >= float(plan.planned_amount):
        plan.status = PaymentPlanStatus.COMPLETED
    elif paid_amount > 0:
        plan.status = PaymentPlanStatus.PARTIAL
    elif data.payment_time > plan.due_date:
        plan.status = PaymentPlanStatus.OVERDUE

    db.commit()

    response = OpenApiPaymentRecordCreateResponse(
        record_id=record.id,
        plan_id=plan_id,
        plan_status=plan.status or "PENDING"
    )

    return success_response(response, message="回款登记成功")


@router.get("/contracts/{contract_id}/payment-summary", summary="查询合同回款汇总", description="查询合同回款汇总信息")
async def get_payment_summary(
    contract_id: int = Path(..., description="合同ID"),
    api_key: ApiKey = Depends(require_api_permission("payment:read")),
    db: Session = Depends(get_db)
):
    """查询合同回款汇总接口"""
    contract = contract_crud.get_by_id(db, contract_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合同不存在"
        )

    # 获取回款计划
    plans = payment_plan_crud.get_by_contract(db, contract_id)

    total_planned = sum(float(p.planned_amount) for p in plans)
    total_paid = 0
    completed_count = 0
    overdue_count = 0

    for plan in plans:
        records = payment_record_crud.get_by_plan(db, plan.id)
        for record in records:
            total_paid += float(record.actual_amount)

        if plan.status == PaymentPlanStatus.COMPLETED:
            completed_count += 1
        elif plan.status == PaymentPlanStatus.OVERDUE:
            overdue_count += 1

    completion_rate = (total_paid / total_planned * 100) if total_planned > 0 else 0

    response = OpenApiPaymentSummaryResponse(
        contract_id=contract_id,
        contract_name=contract.contract_name,
        total_amount=float(contract.total_amount) if contract.total_amount else 0,
        total_planned=total_planned,
        total_paid=total_paid,
        total_remaining=total_planned - total_paid,
        completion_rate=round(completion_rate, 2),
        plan_count=len(plans),
        completed_count=completed_count,
        overdue_count=overdue_count
    )

    return success_response(response)


@router.get("/reminders/overdue", summary="查询逾期回款提醒", description="查询逾期回款提醒列表")
async def get_overdue_reminders(
    api_key: ApiKey = Depends(require_api_permission("payment:list")),
    db: Session = Depends(get_db)
):
    """查询逾期回款提醒接口"""
    # 获取逾期的回款计划
    overdue_plans = payment_plan_crud.get_overdue(db)

    items = []
    for plan in overdue_plans:
        # 计算已回款金额和逾期天数
        paid_amount = 0
        records = payment_record_crud.get_by_plan(db, plan.id)
        for record in records:
            paid_amount += float(record.actual_amount)

        from datetime import date
        overdue_days = (date.today() - plan.due_date).days if plan.due_date else 0

        items.append(OpenApiOverdueReminder(
            plan_id=plan.id,
            contract_id=plan.contract_id,
            contract_name=plan.contract.contract_name if plan.contract else "",
            customer_name=plan.contract.customer.account_name if plan.contract and plan.contract.customer else "",
            stage_name=plan.stage_name,
            planned_amount=float(plan.planned_amount),
            paid_amount=paid_amount,
            due_date=plan.due_date,
            overdue_days=overdue_days
        ))

    return success_response({"list": items, "total": len(items)})
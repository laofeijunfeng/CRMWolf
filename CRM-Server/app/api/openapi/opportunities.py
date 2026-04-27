"""
商机开放接口路由
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Body
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.api.openapi.deps import require_api_permission, verify_api_key
from app.crud.opportunity import opportunity_crud
from app.crud.customer import customer_crud
from app.crud.user import user_crud
from app.models.api_key import ApiKey
from app.models.opportunity import OpportunityStatus
from app.schemas.openapi.common import OpenApiResponse, success_response, paginated_response
from app.schemas.openapi.opportunity import (
    OpenApiOpportunityCreate, OpenApiOpportunityWin, OpenApiOpportunityLose,
    OpenApiOpportunityResponse, OpenApiOpportunityStatusResponse,
    OpenApiOpportunityWinResponse, OpenApiOpportunityLoseResponse,
    OpenApiOpportunityStatus,
    OPPORTUNITY_STATUS_NAMES, PURCHASE_TYPE_NAMES, AUTHORIZATION_MODE_NAMES
)
from app.services.data_masker import data_masker

router = APIRouter()


@router.post("/", summary="创建商机", description="外部系统创建商机")
async def create_opportunity(
    data: OpenApiOpportunityCreate = Body(..., description="商机数据"),
    api_key: ApiKey = Depends(require_api_permission("opportunity:create")),
    db: Session = Depends(get_db)
):
    """创建商机接口"""
    # 校验客户存在
    customer = customer_crud.get_by_id(db, data.customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    # 创建商机
    from app.schemas.opportunity import OpportunityCreate
    from app.models.opportunity import PurchaseType, AuthorizationMode

    opportunity_data = OpportunityCreate(
        customer_id=data.customer_id,
        opportunity_name=data.opportunity_name,
        estimated_amount=data.estimated_amount,
        purchase_type=PurchaseType(data.purchase_type.value),
        authorization_mode=AuthorizationMode(data.authorization_mode.value),
        user_count=data.user_count,
        subscription_years=data.subscription_years
    )

    opportunity = opportunity_crud.create(db, opportunity_data, "openapi_system")

    return success_response({"opportunity_id": opportunity.id}, message="商机创建成功")


@router.get("/", summary="查询商机列表", description="查询商机列表，支持筛选")
async def get_opportunities(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    status: Optional[int] = Query(None, description="商机状态筛选"),
    customer_id: Optional[int] = Query(None, description="客户ID筛选"),
    api_key: ApiKey = Depends(require_api_permission("opportunity:list")),
    db: Session = Depends(get_db)
):
    """查询商机列表接口"""
    skip = (page - 1) * page_size

    # 构建查询 - get_multi 返回 (list, total)
    opportunities, total = opportunity_crud.get_multi(db, skip=skip, limit=page_size)

    # 转换为开放接口响应格式
    items = []
    for opp in opportunities:
        # 获取负责人信息
        owner_name = None
        if opp.owner_id:
            user = user_crud.get_by_feishu_open_id(db, opp.owner_id)
            if user:
                owner_name = user.name

        items.append(OpenApiOpportunityResponse(
            opportunity_id=opp.id,
            opportunity_name=opp.opportunity_name,
            customer_id=opp.customer_id,
            customer_name=opp.customer.account_name if opp.customer else "",
            estimated_amount=float(opp.estimated_amount) if opp.estimated_amount else 0,
            actual_amount=float(opp.actual_amount) if opp.actual_amount else None,
            status=opp.status,
            status_name=OPPORTUNITY_STATUS_NAMES.get(OpenApiOpportunityStatus(opp.status), "跟进中"),
            purchase_type=opp.purchase_type.name if opp.purchase_type else "NEW",
            authorization_mode=opp.authorization_mode.name if opp.authorization_mode else "SUBSCRIPTION",
            user_count=opp.user_count or 1,
            subscription_years=opp.subscription_years,
            current_stage=None,
            owner_id=None,
            owner_name=owner_name,
            create_time=opp.created_time
        ))

    return paginated_response(items, total, page, page_size)


@router.get("/{opportunity_id}", summary="获取商机详情", description="获取商机详细信息")
async def get_opportunity(
    opportunity_id: int = Path(..., description="商机ID"),
    api_key: ApiKey = Depends(require_api_permission("opportunity:read")),
    db: Session = Depends(get_db)
):
    """获取商机详情接口"""
    opportunity = opportunity_crud.get_by_id(db, opportunity_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商机不存在"
        )

    # 获取负责人信息
    owner_name = None
    if opportunity.owner_id:
        user = user_crud.get_by_feishu_open_id(db, opportunity.owner_id)
        if user:
            owner_name = user.name

    response = OpenApiOpportunityResponse(
        opportunity_id=opportunity.id,
        opportunity_name=opportunity.opportunity_name,
        customer_id=opportunity.customer_id,
        customer_name=opportunity.customer.account_name if opportunity.customer else "",
        estimated_amount=float(opportunity.estimated_amount) if opportunity.estimated_amount else 0,
        actual_amount=float(opportunity.actual_amount) if opportunity.actual_amount else None,
        status=opportunity.status,
        status_name=OPPORTUNITY_STATUS_NAMES.get(OpenApiOpportunityStatus(opportunity.status), "跟进中"),
        purchase_type=opportunity.purchase_type.name if opportunity.purchase_type else "NEW",
        authorization_mode=opportunity.authorization_mode.name if opportunity.authorization_mode else "SUBSCRIPTION",
        user_count=opportunity.user_count or 1,
        subscription_years=opportunity.subscription_years,
        current_stage=None,
        owner_id=None,
        owner_name=owner_name,
        create_time=opportunity.created_time
    )

    return success_response(response)


@router.get("/{opportunity_id}/status", summary="查询商机状态", description="查询商机当前状态")
async def get_opportunity_status(
    opportunity_id: int = Path(..., description="商机ID"),
    api_key: ApiKey = Depends(require_api_permission("opportunity:read")),
    db: Session = Depends(get_db)
):
    """查询商机状态接口"""
    opportunity = opportunity_crud.get_by_id(db, opportunity_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商机不存在"
        )

    response = OpenApiOpportunityStatusResponse(
        opportunity_id=opportunity.id,
        status=opportunity.status,
        status_name=OPPORTUNITY_STATUS_NAMES.get(OpenApiOpportunityStatus(opportunity.status), "跟进中")
    )

    return success_response(response)


@router.patch("/{opportunity_id}/win", summary="标记商机赢单", description="外部系统触发商机赢单")
async def mark_opportunity_win(
    opportunity_id: int = Path(..., description="商机ID"),
    data: OpenApiOpportunityWin = Body(..., description="赢单数据"),
    api_key: ApiKey = Depends(require_api_permission("opportunity:win")),
    db: Session = Depends(get_db)
):
    """标记商机赢单接口"""
    opportunity = opportunity_crud.get_by_id(db, opportunity_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商机不存在"
        )

    if opportunity.status != OpportunityStatus.FOLLOWING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有跟进中的商机可以标记赢单"
        )

    # 更新商机状态
    opportunity.status = OpportunityStatus.WON
    opportunity.actual_amount = data.actual_amount
    opportunity.actual_closing_date = data.actual_closing_date
    db.commit()

    # 同步更新客户状态（可选）
    customer_status_updated = False
    if data.sync_customer_status and opportunity.customer_id:
        customer = customer_crud.get_by_id(db, opportunity.customer_id)
        if customer:
            customer.status = 1  # 已成交
            db.commit()
            customer_status_updated = True

    response = OpenApiOpportunityWinResponse(
        opportunity_id=opportunity.id,
        status=1,
        customer_status_updated=customer_status_updated
    )

    return success_response(response, message="赢单标记成功")


@router.patch("/{opportunity_id}/lose", summary="标记商机输单", description="外部系统触发商机输单")
async def mark_opportunity_lose(
    opportunity_id: int = Path(..., description="商机ID"),
    data: OpenApiOpportunityLose = Body(..., description="输单数据"),
    api_key: ApiKey = Depends(require_api_permission("opportunity:lose")),
    db: Session = Depends(get_db)
):
    """标记商机输单接口"""
    opportunity = opportunity_crud.get_by_id(db, opportunity_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商机不存在"
        )

    if opportunity.status != OpportunityStatus.FOLLOWING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有跟进中的商机可以标记输单"
        )

    # 更新商机状态
    opportunity.status = OpportunityStatus.LOST
    opportunity.lose_reason = data.lose_reason
    db.commit()

    response = OpenApiOpportunityLoseResponse(
        opportunity_id=opportunity.id,
        status=2
    )

    return success_response(response, message="输单标记成功")
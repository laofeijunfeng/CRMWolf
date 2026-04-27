"""
客户开放接口路由
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Body
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.api.openapi.deps import require_api_permission, verify_api_key
from app.crud.customer import customer_crud
from app.crud.user import user_crud
from app.crud.opportunity import opportunity_crud
from app.crud.contract import contract_crud
from app.models.api_key import ApiKey
from app.models.customer import CustomerStatus
from app.schemas.openapi.common import OpenApiResponse, success_response, paginated_response
from app.schemas.openapi.customer import (
    OpenApiCustomerResponse, OpenApiCustomerStatusResponse,
    OpenApiCustomerStatusUpdate, OpenApiCustomerStatus,
    CUSTOMER_STATUS_NAMES, OpenApiContactResponse
)
from app.services.data_masker import data_masker

router = APIRouter()


@router.get("/", summary="查询客户列表", description="查询客户列表，支持筛选")
async def get_customers(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    status: Optional[int] = Query(None, description="客户状态筛选"),
    api_key: ApiKey = Depends(require_api_permission("customer:list")),
    db: Session = Depends(get_db)
):
    """查询客户列表接口"""
    skip = (page - 1) * page_size

    # 构建查询 - get_multi 返回 (list, total)
    customers, total = customer_crud.get_multi(db, skip=skip, limit=page_size)

    # 转换为开放接口响应格式
    items = []
    for customer in customers:
        # 获取负责人信息
        owner_name = None
        if customer.owner_id:
            user = user_crud.get_by_feishu_open_id(db, customer.owner_id)
            if user:
                owner_name = user.name

        # 获取主联系人
        primary_contact = None
        contacts = customer_crud.get_contacts(db, customer.id)
        for contact in contacts:
            if contact.is_primary_contact:
                primary_contact = OpenApiContactResponse(
                    contact_id=contact.id,
                    name=data_masker.mask_name(contact.name),
                    phone=data_masker.mask_phone(contact.mobile),
                    email=data_masker.mask_email(contact.email) if contact.email else None,
                    position=contact.position,
                    is_primary=True
                )
                break

        items.append(OpenApiCustomerResponse(
            customer_id=customer.id,
            account_name=customer.account_name,
            industry=customer.industry,
            status=customer.status,
            status_name=CUSTOMER_STATUS_NAMES.get(OpenApiCustomerStatus(customer.status), "跟进中"),
            primary_contact=primary_contact,
            source_lead_id=customer.source_lead_id,
            owner_id=None,
            owner_name=owner_name,
            create_time=customer.created_time
        ))

    return paginated_response(items, total, page, page_size)


@router.get("/{customer_id}", summary="获取客户详情", description="获取客户详细信息")
async def get_customer(
    customer_id: int = Path(..., description="客户ID"),
    api_key: ApiKey = Depends(require_api_permission("customer:read")),
    db: Session = Depends(get_db)
):
    """获取客户详情接口"""
    customer = customer_crud.get_by_id(db, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    # 获取负责人信息
    owner_name = None
    if customer.owner_id:
        user = user_crud.get_by_feishu_open_id(db, customer.owner_id)
        if user:
            owner_name = user.name

    # 获取主联系人
    primary_contact = None
    contacts = customer_crud.get_contacts(db, customer.id)
    for contact in contacts:
        if contact.is_primary_contact:
            primary_contact = OpenApiContactResponse(
                contact_id=contact.id,
                name=data_masker.mask_name(contact.name),
                phone=data_masker.mask_phone(contact.mobile),
                email=data_masker.mask_email(contact.email) if contact.email else None,
                position=contact.position,
                is_primary=True
            )
            break

    response = OpenApiCustomerResponse(
        customer_id=customer.id,
        account_name=customer.account_name,
        industry=customer.industry,
        status=customer.status,
        status_name=CUSTOMER_STATUS_NAMES.get(OpenApiCustomerStatus(customer.status), "跟进中"),
        primary_contact=primary_contact,
        source_lead_id=customer.source_lead_id,
        owner_id=None,
        owner_name=owner_name,
        create_time=customer.created_time
    )

    return success_response(response)


@router.get("/{customer_id}/status", summary="查询客户状态", description="查询客户当前状态")
async def get_customer_status(
    customer_id: int = Path(..., description="客户ID"),
    api_key: ApiKey = Depends(require_api_permission("customer:read")),
    db: Session = Depends(get_db)
):
    """查询客户状态接口"""
    customer = customer_crud.get_by_id(db, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    response = OpenApiCustomerStatusResponse(
        customer_id=customer.id,
        status=customer.status,
        status_name=CUSTOMER_STATUS_NAMES.get(OpenApiCustomerStatus(customer.status), "跟进中")
    )

    return success_response(response)


@router.get("/{customer_id}/opportunities", summary="查询客户商机", description="查询客户关联的商机列表")
async def get_customer_opportunities(
    customer_id: int = Path(..., description="客户ID"),
    api_key: ApiKey = Depends(require_api_permission("customer:read")),
    db: Session = Depends(get_db)
):
    """查询客户商机接口"""
    customer = customer_crud.get_by_id(db, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    opportunities = opportunity_crud.get_by_customer(db, customer_id)

    # 简化返回格式
    items = [{"opportunity_id": opp.id, "opportunity_name": opp.opportunity_name} for opp in opportunities]

    return success_response({"list": items, "total": len(items)})


@router.get("/{customer_id}/contracts", summary="查询客户合同", description="查询客户关联的合同列表")
async def get_customer_contracts(
    customer_id: int = Path(..., description="客户ID"),
    api_key: ApiKey = Depends(require_api_permission("customer:read")),
    db: Session = Depends(get_db)
):
    """查询客户合同接口"""
    customer = customer_crud.get_by_id(db, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    contracts = contract_crud.get_by_customer(db, customer_id)

    # 简化返回格式
    items = [{"contract_id": c.id, "contract_name": c.contract_name, "status": c.status} for c in contracts]

    return success_response({"list": items, "total": len(items)})


@router.patch("/{customer_id}/status", summary="更新客户状态", description="更新客户状态")
async def update_customer_status(
    customer_id: int = Path(..., description="客户ID"),
    data: OpenApiCustomerStatusUpdate = Body(..., description="状态更新数据"),
    api_key: ApiKey = Depends(require_api_permission("customer:update")),
    db: Session = Depends(get_db)
):
    """更新客户状态接口"""
    customer = customer_crud.get_by_id(db, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    # 更新状态
    customer.status = data.status.value
    db.commit()

    response = OpenApiCustomerStatusResponse(
        customer_id=customer.id,
        status=customer.status,
        status_name=CUSTOMER_STATUS_NAMES.get(data.status, "跟进中")
    )

    return success_response(response, message="状态更新成功")
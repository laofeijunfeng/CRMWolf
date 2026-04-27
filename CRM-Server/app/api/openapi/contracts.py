"""
合同开放接口路由
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Body
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.api.openapi.deps import require_api_permission, verify_api_key
from app.crud.contract import contract_crud
from app.crud.opportunity import opportunity_crud
from app.crud.customer import customer_crud
from app.crud.user import user_crud
from app.models.api_key import ApiKey
from app.models.opportunity import OpportunityStatus
from app.models.contract import ContractStatus
from app.schemas.openapi.common import OpenApiResponse, success_response, paginated_response
from app.schemas.openapi.contract import (
    OpenApiContractCreate, OpenApiContractResponse,
    OpenApiContractStatusResponse, OpenApiContractCreateResponse,
    OpenApiContractStatus, CONTRACT_STATUS_NAMES
)
from app.services.data_masker import data_masker

router = APIRouter()


@router.post("/from-opportunity/{opportunity_id}", summary="从商机创建合同", description="基于赢单商机创建合同")
async def create_contract_from_opportunity(
    opportunity_id: int = Path(..., description="商机ID"),
    data: OpenApiContractCreate = Body(..., description="合同数据"),
    api_key: ApiKey = Depends(require_api_permission("contract:create")),
    db: Session = Depends(get_db)
):
    """从商机创建合同接口"""
    opportunity = opportunity_crud.get_by_id(db, opportunity_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商机不存在"
        )

    if opportunity.status != OpportunityStatus.WON:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有赢单商机可以创建合同"
        )

    # 创建合同
    contract = contract_crud.create_from_opportunity(
        db=db,
        opportunity_id=opportunity_id,
        contract_name=data.contract_name,
        signing_contact_id=data.signing_contact_id,
        creator_id="openapi_system"
    )

    response = OpenApiContractCreateResponse(
        contract_id=contract.id,
        contract_no=contract.contract_no,
        status="DRAFT"
    )

    return success_response(response, message="合同创建成功")


@router.get("/", summary="查询合同列表", description="查询合同列表，支持筛选")
async def get_contracts(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    status: Optional[str] = Query(None, description="合同状态筛选"),
    customer_id: Optional[int] = Query(None, description="客户ID筛选"),
    api_key: ApiKey = Depends(require_api_permission("contract:list")),
    db: Session = Depends(get_db)
):
    """查询合同列表接口"""
    skip = (page - 1) * page_size

    # 构建查询 - get_multi 返回 (list, total)
    contracts, total = contract_crud.get_multi(db, skip=skip, limit=page_size)

    # 转换为开放接口响应格式
    items = []
    for c in contracts:
        # 获取负责人信息
        owner_name = None
        if c.owner_id:
            user = user_crud.get_by_feishu_open_id(db, c.owner_id)
            if user:
                owner_name = user.name

        items.append(OpenApiContractResponse(
            contract_id=c.id,
            contract_no=c.contract_no,
            contract_name=c.contract_name,
            customer_id=c.customer_id,
            customer_name=c.customer.account_name if c.customer else "",
            opportunity_id=c.opportunity_id,
            total_amount=float(c.total_amount) if c.total_amount else 0,
            status=c.status or "DRAFT",
            status_name=CONTRACT_STATUS_NAMES.get(OpenApiContractStatus(c.status), "草稿") if c.status else "草稿",
            signing_date=c.signing_date,
            effective_date=c.effective_date,
            expiry_date=c.expiry_date,
            owner_id=None,
            owner_name=owner_name,
            create_time=c.created_time
        ))

    return paginated_response(items, total, page, page_size)


@router.get("/{contract_id}", summary="获取合同详情", description="获取合同详细信息")
async def get_contract(
    contract_id: int = Path(..., description="合同ID"),
    api_key: ApiKey = Depends(require_api_permission("contract:read")),
    db: Session = Depends(get_db)
):
    """获取合同详情接口"""
    contract = contract_crud.get_by_id(db, contract_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合同不存在"
        )

    # 获取负责人信息
    owner_name = None
    if contract.owner_id:
        user = user_crud.get_by_feishu_open_id(db, contract.owner_id)
        if user:
            owner_name = user.name

    response = OpenApiContractResponse(
        contract_id=contract.id,
        contract_no=contract.contract_no,
        contract_name=contract.contract_name,
        customer_id=contract.customer_id,
        customer_name=contract.customer.account_name if contract.customer else "",
        opportunity_id=contract.opportunity_id,
        total_amount=float(contract.total_amount) if contract.total_amount else 0,
        status=contract.status or "DRAFT",
        status_name=CONTRACT_STATUS_NAMES.get(OpenApiContractStatus(contract.status), "草稿") if contract.status else "草稿",
        signing_date=contract.signing_date,
        effective_date=contract.effective_date,
        expiry_date=contract.expiry_date,
        owner_id=None,
        owner_name=owner_name,
        create_time=contract.created_time
    )

    return success_response(response)


@router.get("/{contract_id}/status", summary="查询合同状态", description="查询合同当前状态")
async def get_contract_status(
    contract_id: int = Path(..., description="合同ID"),
    api_key: ApiKey = Depends(require_api_permission("contract:read")),
    db: Session = Depends(get_db)
):
    """查询合同状态接口"""
    contract = contract_crud.get_by_id(db, contract_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合同不存在"
        )

    response = OpenApiContractStatusResponse(
        contract_id=contract.id,
        status=contract.status or "DRAFT",
        status_name=CONTRACT_STATUS_NAMES.get(OpenApiContractStatus(contract.status), "草稿") if contract.status else "草稿"
    )

    return success_response(response)
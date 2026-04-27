"""
ApiKey 管理接口（内部接口）
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Body
from sqlalchemy.orm import Session
from typing import Optional, List

from app.core.database import get_db
from app.core.deps import require_permission
from app.crud.api_key import api_key_crud
from app.models.api_key import ApiKeyStatus
from app.schemas.api_key import (
    ApiKeyCreate, ApiKeyUpdate, ApiKeyStatusUpdate,
    ApiKeyResponse, ApiKeyCreateResponse, ApiKeyListResponse
)

router = APIRouter(prefix="/api-keys", tags=["ApiKey管理"])


@router.post("/", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED, summary="创建 ApiKey", description="创建新的 API Key")
def create_api_key(
    data: ApiKeyCreate,
    current_user = Depends(require_permission("apikey:manage")),
    db: Session = Depends(get_db)
):
    """创建 ApiKey"""
    # 创建并获取原始 Key
    api_key = api_key_crud.create(db, data, created_by=current_user.id)

    return ApiKeyCreateResponse(
        id=api_key.id,
        key_id=api_key.key_id,
        api_key=api_key._raw_api_key,  # 原始 Key，仅此一次返回
        app_name=api_key.app_name,
        permissions=api_key.permissions,
        rate_limit_tps=api_key.rate_limit_tps,
        expires_at=api_key.expires_at,
        created_at=api_key.created_at
    )


@router.get("/", response_model=List[ApiKeyListResponse], summary="查询 ApiKey 列表", description="查询 ApiKey 列表")
def get_api_keys(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="返回记录数"),
    status: Optional[ApiKeyStatus] = Query(None, description="状态筛选"),
    current_user = Depends(require_permission("apikey:manage")),
    db: Session = Depends(get_db)
):
    """查询 ApiKey 列表"""
    return api_key_crud.get_multi(db, skip=skip, limit=limit, status=status)


@router.get("/{api_key_id}", response_model=ApiKeyResponse, summary="获取 ApiKey 详情", description="获取 ApiKey 详细信息")
def get_api_key(
    api_key_id: int = Path(..., description="ApiKey ID"),
    current_user = Depends(require_permission("apikey:manage")),
    db: Session = Depends(get_db)
):
    """获取 ApiKey 详情"""
    api_key = api_key_crud.get_by_id(db, api_key_id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ApiKey 不存在"
        )
    return api_key


@router.put("/{api_key_id}", response_model=ApiKeyResponse, summary="更新 ApiKey", description="更新 ApiKey 信息")
def update_api_key(
    api_key_id: int = Path(..., description="ApiKey ID"),
    data: ApiKeyUpdate = Body(..., description="更新数据"),
    current_user = Depends(require_permission("apikey:manage")),
    db: Session = Depends(get_db)
):
    """更新 ApiKey"""
    api_key = api_key_crud.get_by_id(db, api_key_id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ApiKey 不存在"
        )
    return api_key_crud.update(db, api_key, data)


@router.patch("/{api_key_id}/status", response_model=ApiKeyResponse, summary="更新 ApiKey 状态", description="启用/禁用/撤销 ApiKey")
def update_api_key_status(
    api_key_id: int = Path(..., description="ApiKey ID"),
    data: ApiKeyStatusUpdate = Body(..., description="状态更新数据"),
    current_user = Depends(require_permission("apikey:manage")),
    db: Session = Depends(get_db)
):
    """更新 ApiKey 状态"""
    api_key = api_key_crud.update_status(db, api_key_id, data.status)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ApiKey 不存在"
        )
    return api_key


@router.delete("/{api_key_id}", summary="删除 ApiKey", description="删除 ApiKey")
def delete_api_key(
    api_key_id: int = Path(..., description="ApiKey ID"),
    current_user = Depends(require_permission("apikey:manage")),
    db: Session = Depends(get_db)
):
    """删除 ApiKey"""
    api_key = api_key_crud.delete(db, api_key_id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ApiKey 不存在"
        )
    return {"message": "ApiKey 已删除"}
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.core.deps import require_permission
from app.crud.permission import permission_crud
from app.schemas.permission import PermissionCreate, PermissionUpdate, PermissionResponse, RolePermissionCreate
from app.services.permission_service import permission_service

router = APIRouter(prefix="/permissions", tags=["权限管理"])


@router.get("/", response_model=List[PermissionResponse], summary="获取权限列表", description="获取系统中的所有权限列表，支持按资源和操作类型筛选")
def get_permissions(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="返回记录数"),
    resource: Optional[str] = Query(None, description="资源类型"),
    action: Optional[str] = Query(None, description="操作类型"),
    current_user = Depends(require_permission("permission:manage")),
    db: Session = Depends(get_db)
):
    permissions = permission_crud.get_multi(db, skip=skip, limit=limit, resource=resource, action=action)
    return permissions


@router.get("/{permission_id}", response_model=PermissionResponse, summary="获取权限详情", description="根据权限ID获取权限的详细信息")
def get_permission(
    permission_id: int,
    current_user = Depends(require_permission("permission:manage")),
    db: Session = Depends(get_db)
):
    permission = permission_crud.get_by_id(db, permission_id)
    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="权限不存在"
        )
    return permission


@router.post("/", response_model=PermissionResponse, status_code=status.HTTP_201_CREATED, summary="创建权限", description="创建新的权限，需要提供权限名称、代码、资源和操作类型")
def create_permission(
    permission: PermissionCreate,
    current_user = Depends(require_permission("permission:manage")),
    db: Session = Depends(get_db)
):
    existing_permission = permission_crud.get_by_code(db, permission.code)
    if existing_permission:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="权限代码已存在"
        )
    
    return permission_crud.create(db, permission)


@router.put("/{permission_id}", response_model=PermissionResponse, summary="更新权限", description="更新指定权限的信息")
def update_permission(
    permission_id: int,
    permission: PermissionUpdate,
    current_user = Depends(require_permission("permission:manage")),
    db: Session = Depends(get_db)
):
    db_permission = permission_crud.get_by_id(db, permission_id)
    if not db_permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="权限不存在"
        )
    
    return permission_crud.update(db, db_permission, permission)


@router.delete("/{permission_id}", response_model=PermissionResponse, summary="删除权限", description="删除指定的权限")
def delete_permission(
    permission_id: int,
    current_user = Depends(require_permission("permission:manage")),
    db: Session = Depends(get_db)
):
    permission = permission_crud.delete(db, permission_id)
    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="权限不存在"
        )
    return permission


@router.post("/{permission_id}/roles", status_code=status.HTTP_201_CREATED, summary="为角色分配权限", description="为指定角色分配权限，并清除相关用户权限缓存")
def assign_permission_to_role(
    permission_id: int,
    role_permission: RolePermissionCreate,
    current_user = Depends(require_permission("permission:manage")),
    db: Session = Depends(get_db)
):
    permission = permission_crud.get_by_id(db, permission_id)
    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="权限不存在"
        )
    
    if role_permission.permission_id != permission_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="权限ID不匹配"
        )
    
    result = permission_crud.assign_to_role(db, role_permission.role_id, role_permission.permission_id)
    
    permission_service.invalidate_cache_on_role_permission_change(role_permission.role_id)
    
    return result


@router.delete("/{permission_id}/roles/{role_id}", summary="移除角色权限", description="移除指定角色的权限，并清除相关用户权限缓存")
def remove_permission_from_role(
    permission_id: int,
    role_id: int,
    current_user = Depends(require_permission("permission:manage")),
    db: Session = Depends(get_db)
):
    permission = permission_crud.get_by_id(db, permission_id)
    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="权限不存在"
        )
    
    success = permission_crud.remove_from_role(db, role_id, permission_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色权限关联不存在"
        )
    
    permission_service.invalidate_cache_on_role_permission_change(role_id)
    
    return {"message": "权限已移除"}

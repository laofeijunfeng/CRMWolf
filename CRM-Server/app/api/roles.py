from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.core.deps import require_permission
from app.crud.role import role_crud
from app.crud.permission import permission_crud
from app.schemas.role import RoleCreate, RoleUpdate, RoleResponse, RoleWithPermissions, UserRoleCreate, RolePermissionsUpdate
from app.schemas.permission import PermissionResponse
from app.services.permission_service import permission_service

router = APIRouter(prefix="/roles", tags=["角色管理"])


@router.get("", response_model=List[RoleResponse], summary="获取角色列表", description="获取系统中的所有角色列表")
def get_roles(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="返回记录数"),
    current_user = Depends(require_permission("role:manage")),
    db: Session = Depends(get_db)
):
    roles = role_crud.get_multi(db, skip=skip, limit=limit)
    return roles


@router.get("/{role_id}", response_model=RoleWithPermissions, summary="获取角色详情", description="获取指定角色的详细信息，包括该角色拥有的所有权限")
def get_role(
    role_id: int,
    current_user = Depends(require_permission("role:manage")),
    db: Session = Depends(get_db)
):
    role = role_crud.get_by_id(db, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色不存在"
        )
    
    permissions = permission_crud.get_role_permissions(db, role_id)
    return RoleWithPermissions(
        id=role.id,
        name=role.name,
        code=role.code,
        description=role.description,
        created_at=role.created_at,
        updated_at=role.updated_at,
        permissions=permissions
    )


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED, summary="创建角色", description="创建新的角色，需要提供角色名称和代码")
def create_role(
    role: RoleCreate,
    current_user = Depends(require_permission("role:manage")),
    db: Session = Depends(get_db)
):
    existing_role = role_crud.get_by_code(db, role.code)
    if existing_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="角色代码已存在"
        )
    
    return role_crud.create(db, role)


@router.put("/{role_id}", response_model=RoleResponse, summary="更新角色", description="更新指定角色的信息")
def update_role(
    role_id: int,
    role: RoleUpdate,
    current_user = Depends(require_permission("role:manage")),
    db: Session = Depends(get_db)
):
    db_role = role_crud.get_by_id(db, role_id)
    if not db_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色不存在"
        )
    
    return role_crud.update(db, db_role, role)


@router.delete("/{role_id}", response_model=RoleResponse, summary="删除角色", description="删除指定的角色")
def delete_role(
    role_id: int,
    current_user = Depends(require_permission("role:manage")),
    db: Session = Depends(get_db)
):
    role = role_crud.delete(db, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色不存在"
        )
    return role


@router.post("/{role_id}/users", status_code=status.HTTP_201_CREATED, summary="为用户分配角色", description="为指定用户分配角色")
def assign_role_to_user(
    role_id: int,
    user_role: UserRoleCreate,
    current_user = Depends(require_permission("role:manage")),
    db: Session = Depends(get_db)
):
    role = role_crud.get_by_id(db, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色不存在"
        )
    
    if user_role.role_id != role_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="角色ID不匹配"
        )

    result = role_crud.assign_to_user(db, user_role.user_id, user_role.role_id, user_role.team_id)
    # 清除用户权限缓存
    permission_service.clear_user_permissions_cache(user_role.user_id, user_role.team_id)
    return result


@router.delete("/{role_id}/users/{user_id}", summary="移除用户角色", description="移除指定用户在指定团队的角色")
def remove_role_from_user(
    role_id: int,
    user_id: int,
    team_id: int = Query(..., description="团队ID"),
    current_user = Depends(require_permission("role:manage")),
    db: Session = Depends(get_db)
):
    role = role_crud.get_by_id(db, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色不存在"
        )

    success = role_crud.remove_from_user(db, user_id, role_id, team_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户角色关联不存在"
        )

    # 清除用户权限缓存
    permission_service.clear_user_permissions_cache(user_id, team_id)
    return {"message": "角色已移除"}


@router.put("/{role_id}/permissions", response_model=List[PermissionResponse], summary="更新角色权限", description="批量更新角色的权限列表")
def update_role_permissions(
    role_id: int,
    data: RolePermissionsUpdate = Body(..., description="权限ID列表"),
    current_user = Depends(require_permission("permission:manage")),
    db: Session = Depends(get_db)
):
    """批量更新角色权限

    - permission_ids: 新的权限ID列表，会替换原有权限
    """
    role = role_crud.get_by_id(db, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色不存在"
        )

    # 验证权限ID是否都存在
    for permission_id in data.permission_ids:
        permission = permission_crud.get_by_id(db, permission_id)
        if not permission:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"权限 {permission_id} 不存在"
            )

    # 更新权限
    permissions = role_crud.update_permissions(db, role_id, data.permission_ids)

    # 清除相关用户的权限缓存
    permission_service.invalidate_cache_on_role_permission_change(role_id)

    return permissions

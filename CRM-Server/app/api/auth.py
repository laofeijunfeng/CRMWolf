from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.core.security import create_access_token
from app.core.deps import get_current_user
from app.services.feishu import feishu_service
from app.services.permission_service import permission_service
from app.crud.user import user_crud
from app.crud.role import role_crud
from app.crud.permission import permission_crud
from app.schemas.user import LoginResponse, UserResponse
from app.schemas.role import RoleResponse
from app.schemas.permission import UserPermissionResponse, UserPermissionsListResponse

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=LoginResponse, summary="飞书登录", description="使用飞书授权码进行登录，返回访问令牌和用户信息")
async def login(code: str = Query(..., description="飞书登录授权码"), db: Session = Depends(get_db)):
    try:
        token_response = await feishu_service.get_user_access_token(code)
        user_info = await feishu_service.get_user_info(token_response.access_token)
        
        user = user_crud.get_or_create_from_feishu(db, user_info)
        
        access_token = create_access_token(data={"sub": str(user.id)})
        
        user_roles = role_crud.get_user_roles(db, user.id)
        
        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserResponse.model_validate(user)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"登录失败: {str(e)}"
        )


@router.get("/me", response_model=UserResponse, summary="获取当前用户信息", description="获取当前登录用户的详细信息")
async def get_current_user_info(
    current_user = Depends(get_current_user)
):
    return current_user


@router.get("/me/roles", response_model=List[RoleResponse], summary="获取当前用户角色", description="获取当前登录用户拥有的所有角色")
async def get_current_user_roles(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    roles = role_crud.get_user_roles(db, current_user.id)
    return roles


@router.get("/me/permissions", response_model=UserPermissionsListResponse, summary="获取当前用户合并权限", description="获取当前登录用户所有角色的权限集合，自动合并去重。支持Redis缓存优化性能。")
async def get_current_user_permissions(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
    use_cache: bool = Query(True, description="是否使用缓存")
):
    """
    获取当前用户的所有权限（合并去重）
    
    权限合并策略：
    1. 取并集（Union）：用户获得其所有角色权限的集合
    2. 自动去重：相同的权限只保留一份
    
    性能优化：
    - 使用Redis缓存，默认TTL为1小时
    - 可通过use_cache参数控制是否使用缓存
    
    安全性：
    - 只能获取当前登录用户自身的权限
    - 前端使用权限进行UI控制，后端仍需再次校验
    """
    try:
        permissions, cached = permission_service.get_user_permissions_with_cache(
            db, 
            current_user.id,
            use_cache=use_cache
        )
        
        permissions_data = [
            UserPermissionResponse(
                id=p.id,
                code=p.code,
                name=p.name,
                resource=p.resource,
                action=p.action,
                scope=p.scope,
                description=p.description
            )
            for p in permissions
        ]
        
        return UserPermissionsListResponse(
            permissions=permissions_data,
            total=len(permissions_data),
            cached=cached
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取用户权限失败: {str(e)}"
        )

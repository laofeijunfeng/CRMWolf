from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.core.deps import get_current_user, get_current_user_team_optional, get_current_active_user
from app.core.config import get_settings
from app.services.permission_service import permission_service
from app.services.email_service import email_service
from app.crud.user import user_crud
from app.crud.role import role_crud
from app.crud.permission import permission_crud
from app.crud.email_verification_code import email_verification_code_crud
from app.models.email_verification_code import VerificationPurpose
from app.models.user import User
from app.schemas.user import UserResponse
from app.schemas.role import RoleResponse
from app.schemas.permission import UserPermissionResponse, UserPermissionsListResponse
from app.schemas.auth import (
    SendCodeRequest,
    RegisterRequest,
    RegisterPasswordRequest,
    LoginCodeRequest,
    LoginPasswordRequest,
    LoginResponse,
    ChangePasswordRequest
)

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/send-code", summary="发送验证码", description="发送邮箱验证码用于注册、登录或重置密码")
async def send_verification_code(
    request: SendCodeRequest,
    db: Session = Depends(get_db)
):
    """发送邮箱验证码"""
    purpose_map = {
        "register": VerificationPurpose.REGISTER,
        "login": VerificationPurpose.LOGIN,
        "reset_password": VerificationPurpose.RESET_PASSWORD
    }
    purpose = purpose_map.get(request.purpose)
    if not purpose:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的验证码用途"
        )

    # 检查邮箱是否已注册（注册时需要检查）
    if purpose == VerificationPurpose.REGISTER:
        existing_user = user_crud.get_by_email(db, request.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该邮箱已注册"
            )

    # 创建验证码
    verification_code = email_verification_code_crud.create(
        db, request.email, purpose
    )

    # 发送邮件
    success = await email_service.send_verification_code(
        request.email,
        verification_code.code,
        request.purpose
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="验证码发送失败"
        )

    # 开发模式：返回验证码方便调试
    if settings.SMTP_PROVIDER == "console":
        return {"message": "验证码已发送", "code": verification_code.code}
    return {"message": "验证码已发送，请查收邮件"}


@router.post("/register", response_model=LoginResponse, summary="邮箱注册", description="使用邮箱验证码注册新用户")
async def register(
    request: RegisterRequest,
    db: Session = Depends(get_db)
):
    """邮箱注册"""
    # 验证验证码
    verification_code = email_verification_code_crud.get_valid_code(
        db,
        request.email,
        request.code,
        VerificationPurpose.REGISTER
    )
    if not verification_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码无效或已过期"
        )

    # 检查邮箱是否已注册
    existing_user = user_crud.get_by_email(db, request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱已注册"
        )

    # 创建用户
    user = user_crud.create_from_email(
        db,
        email=request.email,
        name=request.name,
        password=request.password
    )

    # 标记验证码已使用
    email_verification_code_crud.mark_used(db, verification_code)

    # 生成访问令牌
    access_token = create_access_token(data={"sub": str(user.id)})

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )


@router.post("/register-password", response_model=LoginResponse, summary="密码注册", description="使用邮箱和密码直接注册新用户")
async def register_with_password(
    request: RegisterPasswordRequest,
    db: Session = Depends(get_db)
):
    """邮箱密码注册"""
    # 检查邮箱是否已注册
    existing_user = user_crud.get_by_email(db, request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱已注册"
        )

    # 创建用户
    user = user_crud.create_from_email(
        db,
        email=request.email,
        name=request.name,
        password=request.password
    )

    # 生成访问令牌
    access_token = create_access_token(data={"sub": str(user.id)})

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )


@router.post("/login", response_model=LoginResponse, summary="验证码登录", description="使用邮箱验证码登录")
async def login_with_code(
    request: LoginCodeRequest,
    db: Session = Depends(get_db)
):
    """邮箱验证码登录"""
    # 验证验证码
    verification_code = email_verification_code_crud.get_valid_code(
        db,
        request.email,
        request.code,
        VerificationPurpose.LOGIN
    )
    if not verification_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码无效或已过期"
        )

    # 获取用户
    user = user_crud.get_by_email(db, request.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户不存在"
        )

    # 标记验证码已使用
    email_verification_code_crud.mark_used(db, verification_code)

    # 生成访问令牌
    access_token = create_access_token(data={"sub": str(user.id)})

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )


@router.post("/login-password", response_model=LoginResponse, summary="密码登录", description="使用邮箱密码登录")
async def login_with_password(
    request: LoginPasswordRequest,
    db: Session = Depends(get_db)
):
    """邮箱密码登录"""
    # 获取用户
    user = user_crud.get_by_email(db, request.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误"
        )

    # 验证密码
    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="该用户未设置密码，请使用验证码登录"
        )

    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误"
        )

    # 生成访问令牌
    access_token = create_access_token(data={"sub": str(user.id)})

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )


@router.get("/me", response_model=UserResponse, summary="获取当前用户信息", description="获取当前登录用户的详细信息")
async def get_current_user_info(
    current_user = Depends(get_current_user)
):
    return current_user


@router.get("/me/roles", response_model=List[RoleResponse], summary="获取当前用户角色", description="获取当前登录用户在当前团队的拥有角色")
async def get_current_user_roles(
    team_id: int = Depends(get_current_user_team_optional),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取当前用户的角色

    Args:
        team_id: 可选，传入时只返回该团队的角色
    """
    roles = role_crud.get_user_roles(db, current_user.id, team_id)
    return roles


@router.get("/me/permissions", response_model=UserPermissionsListResponse, summary="获取当前用户合并权限", description="获取当前登录用户所有角色的权限集合，自动合并去重。支持Redis缓存优化性能。")
async def get_current_user_permissions(
    team_id: int = Depends(get_current_user_team_optional),
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
            team_id=team_id,
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


@router.post("/me/change-password", summary="修改密码", description="修改当前用户密码")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    修改密码

    验证旧密码后更新为新密码
    """
    # 验证用户是否设置了密码
    if not current_user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户未设置密码，请通过其他方式设置密码"
        )

    # 验证旧密码
    if not verify_password(request.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码不正确"
        )

    # 新密码不能与旧密码相同
    if verify_password(request.new_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码不能与旧密码相同"
        )

    # 更新密码（复用现有 CRUD 方法）
    user_crud.set_password(db, current_user, request.new_password)

    return {"message": "密码修改成功"}
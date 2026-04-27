from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import create_access_token
from app.crud.user import user_crud
from app.crud.role import role_crud
from app.schemas.user import LoginResponse, UserResponse
from app.schemas.role import RoleResponse
from app.schemas.dev import MockLoginRequest, CreateAdminRequest, CreateSalesDirectorRequest, CreateSalesMemberRequest
from typing import List

router = APIRouter(prefix="/dev", tags=["开发工具"])


@router.post("/mock-login", response_model=LoginResponse, summary="模拟登录", description="开发环境模拟登录，跳过飞书OAuth流程")
async def mock_login(
    request: MockLoginRequest,
    db: Session = Depends(get_db)
):
    try:
        from app.schemas.user import UserCreate, FeishuUserInfo
        
        feishu_info = FeishuUserInfo(
            name=request.name,
            en_name=request.name,
            avatar_url="https://avatar.exlb.net/avatar/150.png",
            avatar_thumb="https://avatar.exlb.net/avatar/150.png",
            avatar_middle="https://avatar.exlb.net/avatar/150.png",
            avatar_big="https://avatar.exlb.net/avatar/150.png",
            open_id=f"mock_open_id_{request.name}",
            union_id=f"mock_union_id_{request.name}",
            email=request.email,
            enterprise_email=request.email,
            user_id=f"mock_user_id_{request.name}",
            mobile=request.mobile,
            tenant_key="mock_tenant",
            employee_no="MOCK001"
        )
        
        user = user_crud.get_or_create_from_feishu(db, feishu_info, region=request.region)
        
        access_token = create_access_token(data={"sub": str(user.id)})
        
        user_roles = role_crud.get_user_roles(db, user.id)
        
        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserResponse.model_validate(user)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"模拟登录失败: {str(e)}"
        )


@router.post("/create-admin", response_model=LoginResponse, summary="创建管理员", description="创建一个系统管理员用户并自动登录")
async def create_admin(
    request: CreateAdminRequest,
    db: Session = Depends(get_db)
):
    try:
        from app.schemas.user import UserCreate, FeishuUserInfo
        from app.crud.role import role_crud
        from app.crud.permission import permission_crud
        
        feishu_info = FeishuUserInfo(
            name=request.name,
            en_name="Admin",
            avatar_url="https://avatar.exlb.net/avatar/150.png",
            avatar_thumb="https://avatar.exlb.net/avatar/150.png",
            avatar_middle="https://avatar.exlb.net/avatar/150.png",
            avatar_big="https://avatar.exlb.net/avatar/150.png",
            open_id="admin_open_id",
            union_id="admin_union_id",
            email=request.email,
            enterprise_email=request.email,
            user_id="admin_user_id",
            mobile="+8613800138000",
            tenant_key="admin_tenant",
            employee_no="ADMIN001"
        )
        
        user = user_crud.get_or_create_from_feishu(db, feishu_info, region="北京")
        
        admin_role = role_crud.get_by_code(db, "SYSTEM_ADMIN")
        if admin_role:
            role_crud.assign_to_user(db, user.id, admin_role.id)
        
        access_token = create_access_token(data={"sub": str(user.id)})
        
        user_roles = role_crud.get_user_roles(db, user.id)
        
        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserResponse.model_validate(user)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建管理员失败: {str(e)}"
        )


@router.post("/create-sales-director", response_model=LoginResponse, summary="创建销售总监", description="创建一个销售总监用户并自动登录")
async def create_sales_director(
    request: CreateSalesDirectorRequest,
    db: Session = Depends(get_db)
):
    try:
        from app.schemas.user import FeishuUserInfo
        
        feishu_info = FeishuUserInfo(
            name=request.name,
            en_name="Director",
            avatar_url="https://avatar.exlb.net/avatar/150.png",
            avatar_thumb="https://avatar.exlb.net/avatar/150.png",
            avatar_middle="https://avatar.exlb.net/avatar/150.png",
            avatar_big="https://avatar.exlb.net/avatar/150.png",
            open_id="director_open_id",
            union_id="director_union_id",
            email=request.email,
            enterprise_email=request.email,
            user_id="director_user_id",
            mobile="+8613800138001",
            tenant_key="director_tenant",
            employee_no="DIR001"
        )
        
        user = user_crud.get_or_create_from_feishu(db, feishu_info, region=request.region)
        
        director_role = role_crud.get_by_code(db, "SALES_DIRECTOR")
        if director_role:
            role_crud.assign_to_user(db, user.id, director_role.id)
        
        access_token = create_access_token(data={"sub": str(user.id)})
        
        user_roles = role_crud.get_user_roles(db, user.id)
        
        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserResponse.model_validate(user)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建销售总监失败: {str(e)}"
        )


@router.post("/create-sales-member", response_model=LoginResponse, summary="创建销售成员", description="创建一个销售成员用户并自动登录")
async def create_sales_member(
    request: CreateSalesMemberRequest,
    db: Session = Depends(get_db)
):
    try:
        from app.schemas.user import FeishuUserInfo
        
        feishu_info = FeishuUserInfo(
            name=request.name,
            en_name="Member",
            avatar_url="https://avatar.exlb.net/avatar/150.png",
            avatar_thumb="https://avatar.exlb.net/avatar/150.png",
            avatar_middle="https://avatar.exlb.net/avatar/150.png",
            avatar_big="https://avatar.exlb.net/avatar/150.png",
            open_id="member_open_id",
            union_id="member_union_id",
            email=request.email,
            enterprise_email=request.email,
            user_id="member_user_id",
            mobile="+8613800138002",
            tenant_key="member_tenant",
            employee_no="MEM001"
        )
        
        user = user_crud.get_or_create_from_feishu(db, feishu_info, region=request.region)
        
        member_role = role_crud.get_by_code(db, "SALES_MEMBER")
        if member_role:
            role_crud.assign_to_user(db, user.id, member_role.id)
        
        access_token = create_access_token(data={"sub": str(user.id)})
        
        user_roles = role_crud.get_user_roles(db, user.id)
        
        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserResponse.model_validate(user)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建销售成员失败: {str(e)}"
        )

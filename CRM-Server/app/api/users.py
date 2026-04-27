from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.crud.user import user_crud
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserWithRolesResponse
from app.models.user import UserStatus

router = APIRouter(prefix="/users", tags=["用户管理"])


@router.get("/", response_model=List[UserWithRolesResponse], summary="获取用户列表", description="获取系统中的用户列表，支持按状态和地区筛选，包含用户角色信息")
def get_users(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="返回记录数"),
    status: Optional[UserStatus] = Query(None, description="用户状态"),
    region: Optional[str] = Query(None, description="地区"),
    current_user = Depends(require_permission("user:manage")),
    db: Session = Depends(get_db)
):
    from sqlalchemy import text
    
    users = user_crud.get_multi(db, skip=skip, limit=limit, status=status, region=region)
    
    result = []
    for user in users:
        roles = db.execute(text("""
            SELECT DISTINCT r.id, r.name, r.code
            FROM roles r
            JOIN user_roles ur ON r.id = ur.role_id
            WHERE ur.user_id = :user_id
        """), {"user_id": user.id}).fetchall()
        
        role_list = [{"id": r[0], "name": r[1], "code": r[2]} for r in roles]
        
        user_dict = {
            "id": user.id,
            "name": user.name,
            "en_name": user.en_name,
            "email": user.email,
            "mobile": user.mobile,
            "avatar_url": user.avatar_url,
            "employee_no": user.employee_no,
            "region": user.region,
            "feishu_open_id": user.feishu_open_id,
            "feishu_union_id": user.feishu_union_id,
            "feishu_user_id": user.feishu_user_id,
            "tenant_key": user.tenant_key,
            "status": user.status.value.lower() if user.status else None,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "roles": role_list
        }
        result.append(UserWithRolesResponse(**user_dict))
    
    return result


@router.get("/{user_id}", response_model=UserWithRolesResponse, summary="获取用户详情", description="根据用户ID获取用户的详细信息，包含用户角色信息")
def get_user(
    user_id: int,
    current_user = Depends(require_permission("user:manage")),
    db: Session = Depends(get_db)
):
    from sqlalchemy import text
    
    user = user_crud.get_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    roles = db.execute(text("""
        SELECT DISTINCT r.id, r.name, r.code
        FROM roles r
        JOIN user_roles ur ON r.id = ur.role_id
        WHERE ur.user_id = :user_id
    """), {"user_id": user_id}).fetchall()
    
    role_list = [{"id": r[0], "name": r[1], "code": r[2]} for r in roles]
    
    user_dict = {
        "id": user.id,
        "name": user.name,
        "en_name": user.en_name,
        "email": user.email,
        "mobile": user.mobile,
        "avatar_url": user.avatar_url,
        "employee_no": user.employee_no,
        "region": user.region,
        "feishu_open_id": user.feishu_open_id,
        "feishu_union_id": user.feishu_union_id,
        "feishu_user_id": user.feishu_user_id,
        "tenant_key": user.tenant_key,
        "status": user.status.value.lower() if user.status else None,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "roles": role_list
    }
    
    return UserWithRolesResponse(**user_dict)


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED, summary="创建用户", description="创建新的用户，需要提供飞书open_id等基本信息")
def create_user(
    user: UserCreate,
    current_user = Depends(require_permission("user:manage")),
    db: Session = Depends(get_db)
):
    existing_user = user_crud.get_by_feishu_open_id(db, user.feishu_open_id)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该飞书用户已存在"
        )
    
    return user_crud.create(db, user)


@router.put("/{user_id}", response_model=UserResponse, summary="更新用户", description="更新指定用户的信息")
def update_user(
    user_id: int,
    user: UserUpdate,
    current_user = Depends(require_permission("user:manage")),
    db: Session = Depends(get_db)
):
    db_user = user_crud.get_by_id(db, user_id)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    return user_crud.update(db, db_user, user)


@router.delete("/{user_id}", response_model=UserResponse, summary="删除用户", description="删除指定的用户")
def delete_user(
    user_id: int,
    current_user = Depends(require_permission("user:manage")),
    db: Session = Depends(get_db)
):
    user = user_crud.delete(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    return user

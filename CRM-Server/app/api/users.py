from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission, get_current_user_team
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
    team_id: int = Depends(get_current_user_team),
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
            WHERE ur.user_id = :user_id AND ur.team_id = :team_id
        """), {"user_id": user.id, "team_id": team_id}).fetchall()

        role_list = [{"id": r[0], "name": r[1], "code": r[2]} for r in roles]

        user_dict = {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "mobile": user.mobile,
            "avatar_url": user.avatar_url,
            "employee_no": user.employee_no,
            "region": user.region,
            "status": user.status.value.lower() if user.status else None,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "roles": role_list
        }
        result.append(UserWithRolesResponse(**user_dict))

    return result


@router.get("/search", response_model=List[UserResponse], summary="搜索用户", description="按邮箱模糊搜索用户，可排除已在指定团队的用户")
def search_users(
    email: str = Query(..., min_length=1, description="邮箱搜索关键词"),
    exclude_team_id: Optional[int] = Query(None, description="排除已在该团队的用户"),
    limit: int = Query(10, ge=1, le=50, description="返回数量限制"),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """搜索用户邮箱"""
    from sqlalchemy import text

    if exclude_team_id:
        result = db.execute(text("""
            SELECT id, name, email, mobile, avatar_url, employee_no, region, status, created_at, updated_at
            FROM users
            WHERE email LIKE :email_pattern
            AND status = 'active'
            AND id NOT IN (SELECT user_id FROM user_teams WHERE team_id = :team_id)
            ORDER BY email
            LIMIT :limit
        """), {"email_pattern": f"%{email}%", "team_id": exclude_team_id, "limit": limit})
    else:
        result = db.execute(text("""
            SELECT id, name, email, mobile, avatar_url, employee_no, region, status, created_at, updated_at
            FROM users
            WHERE email LIKE :email_pattern
            AND status = 'active'
            ORDER BY email
            LIMIT :limit
        """), {"email_pattern": f"%{email}%", "limit": limit})

    users = []
    for row in result:
        users.append(UserResponse(
            id=row[0],
            name=row[1],
            email=row[2],
            mobile=row[3],
            avatar_url=row[4],
            employee_no=row[5],
            region=row[6],
            status=row[7],
            created_at=row[8],
            updated_at=row[9]
        ))

    return users


@router.get("/{user_id}", response_model=UserWithRolesResponse, summary="获取用户详情", description="根据用户ID获取用户的详细信息，包含用户角色信息")
def get_user(
    user_id: int,
    team_id: int = Depends(get_current_user_team),
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
        WHERE ur.user_id = :user_id AND ur.team_id = :team_id
    """), {"user_id": user_id, "team_id": team_id}).fetchall()

    role_list = [{"id": r[0], "name": r[1], "code": r[2]} for r in roles]

    user_dict = {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "mobile": user.mobile,
        "avatar_url": user.avatar_url,
        "employee_no": user.employee_no,
        "region": user.region,
        "status": user.status.value.lower() if user.status else None,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "roles": role_list
    }

    return UserWithRolesResponse(**user_dict)


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED, summary="创建用户", description="创建新的用户")
def create_user(
    user: UserCreate,
    current_user = Depends(require_permission("user:manage")),
    db: Session = Depends(get_db)
):
    existing_user = user_crud.get_by_email(db, user.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱已被使用"
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


# 搜索接口已移到 /{user_id} 之前，避免路由冲突
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_access_token
from app.crud.user import user_crud
from app.crud.permission import permission_crud

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    payload = decode_access_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = user_crud.get_by_id(db, int(user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


async def get_current_active_user(
    current_user = Depends(get_current_user)
):
    if current_user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用"
        )
    return current_user


async def check_permission(
    required_permission: str,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    user_permissions = permission_crud.get_user_permissions(db, current_user.id)
    permission_codes = {p.code for p in user_permissions}
    
    if required_permission not in permission_codes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"缺少权限: {required_permission}"
        )
    
    return current_user


def require_permission(permission_code: str):
    def permission_checker(
        current_user = Depends(get_current_active_user),
        db: Session = Depends(get_db)
    ):
        user_permissions = permission_crud.get_user_permissions(db, current_user.id)
        permission_codes = {p.code for p in user_permissions}
        
        if permission_code not in permission_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少权限: {permission_code}"
            )
        
        return current_user
    
    return permission_checker


def require_role(role_code: str):
    def role_checker(
        current_user = Depends(get_current_active_user),
        db: Session = Depends(get_db)
    ):
        from app.crud.role import role_crud
        user_roles = role_crud.get_user_roles(db, current_user.id)
        role_codes = {r.code for r in user_roles}
        
        if role_code not in role_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少角色: {role_code}"
            )
        
        return current_user
    
    return role_checker


def check_lead_access(
    lead_id: int,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.crud.lead import lead_crud
    from app.crud.role import role_crud
    
    lead = lead_crud.get_by_id(db, lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="线索不存在"
        )
    
    user_roles = role_crud.get_user_roles(db, current_user.id)
    role_codes = {r.code for r in user_roles}
    
    is_admin = "SYSTEM_ADMIN" in role_codes
    is_director = "SALES_DIRECTOR" in role_codes
    is_owner = lead.owner_id == current_user.feishu_open_id
    is_creator = lead.creator_id == current_user.feishu_open_id
    
    if not (is_admin or is_director or is_owner or is_creator):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该线索"
        )
    
    return lead


def check_lead_owner(
    lead_id: int,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.crud.lead import lead_crud
    from app.crud.role import role_crud
    
    lead = lead_crud.get_by_id(db, lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="线索不存在"
        )
    
    user_roles = role_crud.get_user_roles(db, current_user.id)
    role_codes = {r.code for r in user_roles}
    
    is_admin = "SYSTEM_ADMIN" in role_codes
    is_director = "SALES_DIRECTOR" in role_codes
    is_owner = lead.owner_id == current_user.feishu_open_id
    
    if not (is_admin or is_director or is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有线索负责人或管理员可以操作"
        )
    
    return lead

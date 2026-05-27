from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.schemas.permission import PermissionResponse


class RoleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="角色名称")
    code: str = Field(..., min_length=1, max_length=50, description="角色代码")
    description: Optional[str] = Field(None, description="角色描述")


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50, description="角色名称")
    description: Optional[str] = Field(None, description="角色描述")


class RoleResponse(RoleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RoleWithPermissions(RoleResponse):
    permissions: List[PermissionResponse] = []


class UserRoleCreate(BaseModel):
    user_id: int = Field(..., description="用户ID")
    role_id: int = Field(..., description="角色ID")
    team_id: int = Field(..., description="团队ID")


class UserRoleResponse(BaseModel):
    id: int
    user_id: int
    role_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class RolePermissionsUpdate(BaseModel):
    """批量更新角色权限的请求"""
    permission_ids: List[int] = Field(..., description="权限ID列表")

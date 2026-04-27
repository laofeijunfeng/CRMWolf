from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class PermissionBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="权限名称")
    code: str = Field(..., min_length=1, max_length=100, description="权限代码")
    resource: str = Field(..., min_length=1, max_length=50, description="资源类型")
    action: str = Field(..., min_length=1, max_length=50, description="操作类型")
    scope: Optional[str] = Field(None, max_length=50, description="权限范围")
    description: Optional[str] = Field(None, description="权限描述")


class PermissionCreate(PermissionBase):
    pass


class PermissionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="权限名称")
    description: Optional[str] = Field(None, description="权限描述")


class PermissionResponse(PermissionBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RolePermissionCreate(BaseModel):
    role_id: int = Field(..., description="角色ID")
    permission_id: int = Field(..., description="权限ID")


class RolePermissionResponse(BaseModel):
    id: int
    role_id: int
    permission_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class UserPermissionResponse(BaseModel):
    id: int = Field(..., description="权限ID")
    code: str = Field(..., description="权限编码")
    name: str = Field(..., description="权限名称")
    resource: str = Field(..., description="资源类型")
    action: str = Field(..., description="操作类型")
    scope: Optional[str] = Field(None, description="权限范围")
    description: Optional[str] = Field(None, description="权限描述")

    class Config:
        from_attributes = True


class UserPermissionsListResponse(BaseModel):
    permissions: List[UserPermissionResponse] = Field(..., description="权限列表")
    total: int = Field(..., description="权限总数")
    cached: bool = Field(False, description="是否来自缓存")

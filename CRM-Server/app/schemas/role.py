from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.permission import PermissionResponse


class RoleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="角色名称")
    code: str = Field(..., min_length=1, max_length=50, description="角色代码")
    description: str | None = Field(None, description="角色描述")


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50, description="角色名称")
    description: str | None = Field(None, description="角色描述")


class RoleResponse(RoleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RoleWithPermissions(RoleResponse):
    permissions: list[PermissionResponse] = []


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


class RoleUserResponse(BaseModel):
    id: int
    name: str
    email: str
    avatar_url: str | None = None
    status: str

    class Config:
        from_attributes = True


class RolePermissionsUpdate(BaseModel):
    """批量更新角色权限的请求"""
    permission_ids: list[int] = Field(..., description="权限ID列表")

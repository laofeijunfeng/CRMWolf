from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class RoleSimpleResponse(BaseModel):
    """角色简要信息"""
    id: int = Field(..., description="角色ID")
    name: str = Field(..., description="角色名称")
    code: str = Field(..., description="角色代码")


class AssignRolesRequest(BaseModel):
    """分配角色请求"""
    role_ids: List[int] = Field(..., description="角色ID列表")


class TeamBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="团队名称")


class TeamCreate(TeamBase):
    pass


class TeamUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="团队名称")


class TeamResponse(TeamBase):
    id: int
    code: str = Field(..., description="邀请码")
    owner_id: int = Field(..., description="创建者ID")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TeamJoinRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=20, description="团队邀请码")


class TeamSwitchRequest(BaseModel):
    team_id: int = Field(..., description="要切换的团队ID")


class TeamInviteRequest(BaseModel):
    email: str = Field(..., description="被邀请用户邮箱")


class AddMemberRequest(BaseModel):
    user_id: int = Field(..., description="要添加的用户ID")


class UserTeamResponse(BaseModel):
    id: int
    user_id: int
    team_id: int
    current_team: bool = Field(..., description="是否为当前活跃团队")
    joined_at: datetime

    class Config:
        from_attributes = True


class TeamMemberResponse(BaseModel):
    id: int = Field(..., description="用户ID")
    name: str = Field(..., description="用户姓名")
    email: str = Field(..., description="用户邮箱")
    avatar_url: Optional[str] = Field(None, description="用户头像")
    current_team: bool = Field(..., description="是否为当前活跃团队")
    joined_at: datetime = Field(..., description="加入时间")
    roles: List[RoleSimpleResponse] = Field(default=[], description="用户角色列表")


class TeamWithMembersResponse(TeamResponse):
    members: List[TeamMemberResponse] = []


class UserTeamsListResponse(BaseModel):
    teams: List[TeamResponse]
    current_team_id: Optional[int] = Field(None, description="当前活跃团队ID")


class ResetPasswordRequest(BaseModel):
    """重置成员密码请求"""
    new_password: str = Field(
        ...,
        min_length=6,
        max_length=50,
        description="新密码（6-50位）"
    )
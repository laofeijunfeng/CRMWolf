from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from app.models.user import UserStatus


class RoleInfo(BaseModel):
    id: int = Field(..., description="角色ID（主键）")
    name: str = Field(..., description="角色名称（如：销售成员、销售经理等）")
    code: str = Field(..., description="角色代码（唯一标识符）")

    class Config:
        from_attributes = True


class UserBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="用户姓名（必填）")
    email: EmailStr = Field(..., description="用户邮箱（主登录标识）")
    mobile: Optional[str] = Field(None, max_length=20, description="用户手机号")
    avatar_url: Optional[str] = Field(None, max_length=500, description="用户头像URL")
    employee_no: Optional[str] = Field(None, max_length=50, description="用户工号（企业编号）")
    region: Optional[str] = Field(None, max_length=50, description="所属地区（如：华北、华东、华南等）")


class UserCreate(UserBase):
    """用户创建 Schema（内部使用）"""
    password: Optional[str] = Field(None, min_length=6, max_length=50, description="密码（可选）")


class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="用户姓名")
    email: Optional[EmailStr] = Field(None, description="用户邮箱")
    mobile: Optional[str] = Field(None, max_length=20, description="用户手机号")
    avatar_url: Optional[str] = Field(None, max_length=500, description="用户头像URL")
    employee_no: Optional[str] = Field(None, max_length=50, description="用户工号")
    region: Optional[str] = Field(None, max_length=50, description="所属地区")
    status: Optional[UserStatus] = Field(None, description="用户状态：active:激活, inactive:未激活, suspended:已停用")


class UserResponse(UserBase):
    id: int = Field(..., description="用户ID（主键）")
    status: UserStatus = Field(..., description="用户状态：active:激活, inactive:未激活, suspended:已停用")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config:
        from_attributes = True


class UserWithRolesResponse(UserResponse):
    roles: List[RoleInfo] = Field(default_factory=list, description="用户角色列表（决定用户权限）")

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field(..., description="令牌类型")
    user: UserResponse = Field(..., description="用户信息")


# 废弃：飞书相关 Schema（仅用于通知服务兼容）
class FeishuUserInfo(BaseModel):
    """飞书用户信息（已废弃，仅用于通知服务）"""
    name: str = Field(..., description="用户姓名")
    en_name: str = Field(..., description="用户英文名")
    avatar_url: str = Field(..., description="用户头像URL")
    avatar_thumb: str = Field(..., description="用户头像缩略图URL")
    avatar_middle: str = Field(..., description="用户头像中等图URL")
    avatar_big: str = Field(..., description="用户头像大图URL")
    open_id: str = Field(..., description="飞书Open ID")
    union_id: str = Field(..., description="飞书Union ID")
    email: Optional[str] = Field(None, description="用户邮箱")
    enterprise_email: Optional[str] = Field(None, description="企业邮箱")
    user_id: Optional[str] = Field(None, description="飞书User ID（已废弃，当前通知使用 Open ID）")
    mobile: Optional[str] = Field(None, description="用户手机号")
    tenant_key: str = Field(..., description="企业标识")
    employee_no: Optional[str] = Field(None, description="用户工号")


class FeishuTokenResponse(BaseModel):
    """飞书令牌响应（已废弃）"""
    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field(..., description="令牌类型")
    expires_in: int = Field(..., description="过期时间（秒）")
    name: str = Field(..., description="用户姓名")
    en_name: str = Field(..., description="用户英文名")
    avatar_url: str = Field(..., description="用户头像URL")
    avatar_thumb: str = Field(..., description="用户头像缩略图URL")
    avatar_middle: str = Field(..., description="用户头像中等图URL")
    avatar_big: str = Field(..., description="用户头像大图URL")
    open_id: str = Field(..., description="飞书Open ID")
    union_id: str = Field(..., description="飞书Union ID")
    email: Optional[str] = Field(None, description="用户邮箱")
    enterprise_email: Optional[str] = Field(None, description="企业邮箱")
    user_id: Optional[str] = Field(None, description="飞书User ID（已废弃，当前通知使用 Open ID）")
    mobile: Optional[str] = Field(None, description="用户手机号")
    tenant_key: str = Field(..., description="企业标识")
    refresh_expires_in: int = Field(..., description="刷新令牌过期时间（秒）")
    refresh_token: str = Field(..., description="刷新令牌")
    sid: Optional[str] = Field(None, description="会话ID")

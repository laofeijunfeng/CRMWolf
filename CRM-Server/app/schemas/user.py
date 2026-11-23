from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserStatus


class RoleInfo(BaseModel):
    id: int = Field(..., description="角色ID\uff08主键\uff09")
    name: str = Field(..., description="角色名称\uff08如\uff1a销售成员、销售经理等\uff09")
    code: str = Field(..., description="角色代码\uff08唯一标识符\uff09")

    class Config:
        from_attributes = True


class UserBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="用户姓名\uff08必填\uff09")
    email: EmailStr = Field(..., description="用户邮箱\uff08主登录标识\uff09")
    mobile: str | None = Field(None, max_length=20, description="用户手机号")
    avatar_url: str | None = Field(None, max_length=500, description="用户头像URL")
    employee_no: str | None = Field(None, max_length=50, description="用户工号\uff08企业编号\uff09")
    region: str | None = Field(None, max_length=50, description="所属地区\uff08如\uff1a华北、华东、华南等\uff09")


class UserCreate(UserBase):
    """用户创建 Schema\uff08内部使用\uff09"""
    password: str | None = Field(None, min_length=6, max_length=50, description="密码\uff08可选\uff09")


class UserUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100, description="用户姓名")
    email: EmailStr | None = Field(None, description="用户邮箱")
    mobile: str | None = Field(None, max_length=20, description="用户手机号")
    avatar_url: str | None = Field(None, max_length=500, description="用户头像URL")
    employee_no: str | None = Field(None, max_length=50, description="用户工号")
    region: str | None = Field(None, max_length=50, description="所属地区")
    status: UserStatus | None = Field(None, description="用户状态\uff1aactive:激活, inactive:未激活, suspended:已停用")


class UserResponse(UserBase):
    id: int = Field(..., description="用户ID\uff08主键\uff09")
    status: UserStatus = Field(..., description="用户状态\uff1aactive:激活, inactive:未激活, suspended:已停用")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config:
        from_attributes = True


class UserWithRolesResponse(UserResponse):
    roles: list[RoleInfo] = Field(default_factory=list, description="用户角色列表\uff08决定用户权限\uff09")

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field(..., description="令牌类型")
    user: UserResponse = Field(..., description="用户信息")


# 废弃:飞书相关 Schema(仅用于通知服务兼容)
class FeishuUserInfo(BaseModel):
    """飞书用户信息\uff08已废弃\uff0c仅用于通知服务\uff09"""
    name: str = Field(..., description="用户姓名")
    en_name: str = Field(..., description="用户英文名")
    avatar_url: str = Field(..., description="用户头像URL")
    avatar_thumb: str = Field(..., description="用户头像缩略图URL")
    avatar_middle: str = Field(..., description="用户头像中等图URL")
    avatar_big: str = Field(..., description="用户头像大图URL")
    open_id: str = Field(..., description="飞书Open ID")
    union_id: str = Field(..., description="飞书Union ID")
    email: str | None = Field(None, description="用户邮箱")
    enterprise_email: str | None = Field(None, description="企业邮箱")
    user_id: str | None = Field(None, description="飞书User ID\uff08已废弃\uff0c当前通知使用 Open ID\uff09")
    mobile: str | None = Field(None, description="用户手机号")
    tenant_key: str = Field(..., description="企业标识")
    employee_no: str | None = Field(None, description="用户工号")


class FeishuTokenResponse(BaseModel):
    """飞书令牌响应\uff08已废弃\uff09"""
    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field(..., description="令牌类型")
    expires_in: int = Field(..., description="过期时间\uff08秒\uff09")
    name: str = Field(..., description="用户姓名")
    en_name: str = Field(..., description="用户英文名")
    avatar_url: str = Field(..., description="用户头像URL")
    avatar_thumb: str = Field(..., description="用户头像缩略图URL")
    avatar_middle: str = Field(..., description="用户头像中等图URL")
    avatar_big: str = Field(..., description="用户头像大图URL")
    open_id: str = Field(..., description="飞书Open ID")
    union_id: str = Field(..., description="飞书Union ID")
    email: str | None = Field(None, description="用户邮箱")
    enterprise_email: str | None = Field(None, description="企业邮箱")
    user_id: str | None = Field(None, description="飞书User ID\uff08已废弃\uff0c当前通知使用 Open ID\uff09")
    mobile: str | None = Field(None, description="用户手机号")
    tenant_key: str = Field(..., description="企业标识")
    refresh_expires_in: int = Field(..., description="刷新令牌过期时间\uff08秒\uff09")
    refresh_token: str = Field(..., description="刷新令牌")
    sid: str | None = Field(None, description="会话ID")

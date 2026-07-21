from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.auth import LoginResponse


class OAuthProviderConfigUpdate(BaseModel):
    app_id: str = Field(..., min_length=1, max_length=128, description="飞书 App ID")
    app_secret: Optional[str] = Field(None, max_length=255, description="飞书 App Secret，不填写则保留原值")
    redirect_uri: str = Field(..., min_length=1, max_length=500, description="飞书授权回调地址")
    enabled: bool = Field(False, description="是否启用飞书登录")

    @field_validator("app_id", "redirect_uri")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("app_secret")
    @classmethod
    def normalize_secret(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class OAuthProviderConfigResponse(BaseModel):
    id: Optional[int] = None
    team_id: int
    provider: str = "feishu"
    app_id: Optional[str] = None
    redirect_uri: Optional[str] = None
    enabled: bool = False
    app_secret_configured: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class InviteLoginOptionsResponse(BaseModel):
    team_name: str
    code: str
    feishu_login_enabled: bool


class OAuthLoginUrlResponse(BaseModel):
    auth_url: str


class FeishuCallbackRequest(BaseModel):
    code: str = Field(..., min_length=1)
    state: str = Field(..., min_length=1)


class OAuthBindingStatusResponse(BaseModel):
    provider: str = "feishu"
    enabled: bool
    bound: bool
    name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    updated_at: Optional[datetime] = None


class FeishuCallbackResponse(BaseModel):
    mode: Literal["invite", "bind"]
    message: str
    login: Optional[LoginResponse] = None


class FeishuUserProfile(BaseModel):
    open_id: str
    union_id: Optional[str] = None
    user_id: Optional[str] = None
    tenant_key: Optional[str] = None
    email: Optional[str] = None
    enterprise_email: Optional[str] = None
    mobile: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    raw: Dict[str, Any] = Field(default_factory=dict)

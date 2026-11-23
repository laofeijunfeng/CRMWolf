from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.auth import LoginResponse


class OAuthProviderConfigUpdate(BaseModel):
    app_id: str = Field(..., min_length=1, max_length=128, description="飞书 App ID")
    app_secret: str | None = Field(None, max_length=255, description="飞书 App Secret，不填写则保留原值")
    redirect_uri: str = Field(..., min_length=1, max_length=500, description="飞书授权回调地址")
    enabled: bool = Field(False, description="是否启用飞书登录")
    bot_enabled: bool = Field(False, description="是否启用飞书AI Agent机器人")
    bot_verification_token: str | None = Field(None, max_length=255, description="飞书事件订阅校验Token")
    bot_encrypt_key: str | None = Field(None, max_length=255, description="飞书事件订阅加密Key")
    bot_open_id: str | None = Field(None, max_length=128, description="飞书机器人Open ID")

    @field_validator("app_id", "redirect_uri")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("app_secret", "bot_verification_token", "bot_encrypt_key", "bot_open_id")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class OAuthProviderConfigResponse(BaseModel):
    id: int | None = None
    team_id: int
    provider: str = "feishu"
    app_id: str | None = None
    redirect_uri: str | None = None
    enabled: bool = False
    app_secret_configured: bool = False
    bot_enabled: bool = False
    bot_verification_token: str | None = None
    bot_encrypt_key: str | None = None
    bot_open_id: str | None = None
    bot_callback_path: str | None = None
    bot_callback_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


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
    name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    updated_at: datetime | None = None


class FeishuCallbackResponse(BaseModel):
    mode: Literal["invite", "bind"]
    message: str
    login: LoginResponse | None = None


class FeishuUserProfile(BaseModel):
    open_id: str
    union_id: str | None = None
    user_id: str | None = None
    tenant_key: str | None = None
    email: str | None = None
    enterprise_email: str | None = None
    mobile: str | None = None
    name: str | None = None
    avatar_url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

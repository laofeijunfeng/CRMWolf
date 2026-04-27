from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.models.api_key import ApiKeyStatus


class ApiKeyCreate(BaseModel):
    app_name: str = Field(..., min_length=1, max_length=100, description="应用名称")
    description: Optional[str] = Field(None, description="应用描述")
    permissions: Optional[List[str]] = Field(default_factory=list, description="权限列表")
    ip_whitelist: Optional[List[str]] = Field(default_factory=list, description="IP白名单")
    rate_limit_tps: int = Field(default=100, ge=1, le=500, description="每秒请求限制（TPS）")
    expires_at: Optional[datetime] = Field(None, description="过期时间（NULL表示永不过期）")


class ApiKeyUpdate(BaseModel):
    app_name: Optional[str] = Field(None, min_length=1, max_length=100, description="应用名称")
    description: Optional[str] = Field(None, description="应用描述")
    permissions: Optional[List[str]] = Field(None, description="权限列表")
    ip_whitelist: Optional[List[str]] = Field(None, description="IP白名单")
    rate_limit_tps: Optional[int] = Field(None, ge=1, le=500, description="每秒请求限制（TPS）")
    expires_at: Optional[datetime] = Field(None, description="过期时间")


class ApiKeyStatusUpdate(BaseModel):
    status: ApiKeyStatus = Field(..., description="新状态")


class ApiKeyResponse(BaseModel):
    id: int = Field(..., description="主键")
    key_id: str = Field(..., description="API Key ID（对外展示）")
    app_name: str = Field(..., description="应用名称")
    description: Optional[str] = Field(None, description="应用描述")
    permissions: Optional[List[str]] = Field(None, description="权限列表")
    ip_whitelist: Optional[List[str]] = Field(None, description="IP白名单")
    rate_limit_tps: int = Field(..., description="每秒请求限制（TPS）")
    status: ApiKeyStatus = Field(..., description="状态")
    expires_at: Optional[datetime] = Field(None, description="过期时间")
    last_used_at: Optional[datetime] = Field(None, description="最后使用时间")
    created_by: Optional[int] = Field(None, description="创建人ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config:
        from_attributes = True


class ApiKeyCreateResponse(BaseModel):
    """创建 ApiKey 的响应，包含原始 Key（仅此一次返回）"""
    id: int = Field(..., description="主键")
    key_id: str = Field(..., description="API Key ID（对外展示）")
    api_key: str = Field(..., description="原始 API Key（仅创建时返回，请妥善保管）")
    app_name: str = Field(..., description="应用名称")
    permissions: Optional[List[str]] = Field(None, description="权限列表")
    rate_limit_tps: int = Field(..., description="每秒请求限制（TPS）")
    expires_at: Optional[datetime] = Field(None, description="过期时间")
    created_at: datetime = Field(..., description="创建时间")


class ApiKeyListResponse(BaseModel):
    """ApiKey 列表响应，不包含敏感信息"""
    id: int = Field(..., description="主键")
    key_id: str = Field(..., description="API Key ID（对外展示）")
    app_name: str = Field(..., description="应用名称")
    description: Optional[str] = Field(None, description="应用描述")
    status: ApiKeyStatus = Field(..., description="状态")
    rate_limit_tps: int = Field(..., description="每秒请求限制（TPS）")
    expires_at: Optional[datetime] = Field(None, description="过期时间")
    last_used_at: Optional[datetime] = Field(None, description="最后使用时间")
    created_at: datetime = Field(..., description="创建时间")

    class Config:
        from_attributes = True
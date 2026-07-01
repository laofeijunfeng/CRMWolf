from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class NotificationConfigBase(BaseModel):
    """通知配置基础模型"""
    notification_method: str = Field(
        ...,
        description="通知方式：webhook（Webhook方式）或 api（API方式）"
    )
    feishu_webhook_url: Optional[str] = Field(
        None,
        description="飞书Webhook地址，当notification_method为webhook时使用"
    )
    feishu_webhook_enabled: Optional[bool] = Field(
        None,
        description="飞书Webhook是否启用，True启用，False禁用"
    )
    notification_group_name: Optional[str] = Field(
        None,
        description="通知群名称，飞书群名称标识"
    )
    feishu_app_id: Optional[str] = Field(
        None,
        description="飞书应用ID，当notification_method为api时使用（预留）"
    )
    feishu_app_secret: Optional[str] = Field(
        None,
        description="飞书应用密钥，当notification_method为api时使用（预留）"
    )
    feishu_api_enabled: Optional[bool] = Field(
        None,
        description="飞书API是否启用，True启用，False禁用（预留）"
    )


class NotificationConfigUpdate(NotificationConfigBase):
    """通知配置更新请求模型"""
    notification_method: Optional[str] = Field(
        None,
        description="通知方式：webhook或api"
    )
    # 继承时所有字段都保持Optional，由父类定义决定


class NotificationConfigResponse(NotificationConfigBase):
    """通知配置响应模型"""
    id: int = Field(..., description="配置ID，自增主键")
    team_id: int = Field(..., description="团队ID，租户隔离标识")
    created_time: datetime = Field(..., description="创建时间，记录创建时间")
    updated_time: datetime = Field(..., description="更新时间，最后修改时间")

    class Config:
        from_attributes = True


class SystemConfigResponse(BaseModel):
    """通用系统配置响应模型"""
    id: int = Field(..., description="配置ID，自增主键")
    team_id: int = Field(..., description="团队ID，租户隔离标识")
    config_key: str = Field(..., description="配置键，配置项唯一标识")
    config_value: Optional[str] = Field(None, description="配置值，配置项的值")
    config_type: Optional[str] = Field(None, description="配置类型，如：string、json、boolean等")
    description: Optional[str] = Field(None, description="配置描述，说明配置项用途")
    created_time: datetime = Field(..., description="创建时间，记录创建时间")
    updated_time: datetime = Field(..., description="更新时间，最后修改时间")

    class Config:
        from_attributes = True
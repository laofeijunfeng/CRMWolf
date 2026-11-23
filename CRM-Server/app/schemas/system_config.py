from datetime import datetime

from pydantic import BaseModel, Field


class NotificationConfigBase(BaseModel):
    """通知配置基础模型"""
    notification_method: str = Field(
        ...,
        description="通知方式\uff1awebhook\uff08Webhook方式\uff09或 api\uff08API方式\uff09"
    )
    feishu_webhook_url: str | None = Field(
        None,
        description="飞书Webhook地址\uff0c当notification_method为webhook时使用"
    )
    feishu_webhook_enabled: bool | None = Field(
        None,
        description="飞书Webhook是否启用\uff0cTrue启用\uff0cFalse禁用"
    )
    notification_group_name: str | None = Field(
        None,
        description="通知群名称\uff0c飞书群名称标识"
    )
    feishu_app_id: str | None = Field(
        None,
        description="飞书应用ID\uff0c当notification_method为api时使用\uff08预留\uff09"
    )
    feishu_app_secret: str | None = Field(
        None,
        description="飞书应用密钥\uff0c当notification_method为api时使用\uff08预留\uff09"
    )
    feishu_api_enabled: bool | None = Field(
        None,
        description="飞书API是否启用\uff0cTrue启用\uff0cFalse禁用\uff08预留\uff09"
    )


class NotificationConfigUpdate(NotificationConfigBase):
    """通知配置更新请求模型"""
    notification_method: str | None = Field(
        None,
        description="通知方式\uff1awebhook或api"
    )
    # 继承时所有字段都保持Optional,由父类定义决定


class NotificationConfigResponse(NotificationConfigBase):
    """通知配置响应模型"""
    id: int = Field(..., description="配置ID\uff0c自增主键")
    team_id: int = Field(..., description="团队ID\uff0c租户隔离标识")
    created_time: datetime = Field(..., description="创建时间\uff0c记录创建时间")
    updated_time: datetime = Field(..., description="更新时间\uff0c最后修改时间")

    class Config:
        from_attributes = True


class SystemConfigResponse(BaseModel):
    """通用系统配置响应模型"""
    id: int = Field(..., description="配置ID\uff0c自增主键")
    team_id: int = Field(..., description="团队ID\uff0c租户隔离标识")
    config_key: str = Field(..., description="配置键\uff0c配置项唯一标识")
    config_value: str | None = Field(None, description="配置值\uff0c配置项的值")
    config_type: str | None = Field(None, description="配置类型\uff0c如\uff1astring、json、boolean等")
    description: str | None = Field(None, description="配置描述\uff0c说明配置项用途")
    created_time: datetime = Field(..., description="创建时间\uff0c记录创建时间")
    updated_time: datetime = Field(..., description="更新时间\uff0c最后修改时间")

    class Config:
        from_attributes = True
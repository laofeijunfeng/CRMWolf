"""
商机开放接口 Schema
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime, date
import enum


class OpenApiOpportunityStatus(int, enum.Enum):
    """商机状态枚举（开放接口）"""
    FOLLOWING = 0     # 跟进中
    WON = 1           # 赢单
    LOST = 2          # 输单


class OpenApiPurchaseType(str, enum.Enum):
    """采购类型枚举"""
    NEW = "NEW"           # 新购
    RENEWAL = "RENEWAL"   # 续购
    EXPANSION = "EXPANSION"  # 增购


class OpenApiAuthorizationMode(str, enum.Enum):
    """授权模式枚举"""
    SUBSCRIPTION = "SUBSCRIPTION"  # 订阅制
    PERPETUAL = "PERPETUAL"        # 买断制


# ============== 创建请求 ==============

class OpenApiOpportunityCreate(BaseModel):
    """创建商机请求"""
    customer_id: int = Field(..., description="客户ID")
    opportunity_name: str = Field(..., min_length=1, max_length=255, description="商机名称")
    estimated_amount: float = Field(..., ge=0, description="预计成交金额")
    purchase_type: OpenApiPurchaseType = Field(..., description="采购类型")
    authorization_mode: OpenApiAuthorizationMode = Field(..., description="授权模式")
    user_count: int = Field(..., ge=1, description="用户数量")
    subscription_years: Optional[int] = Field(None, ge=1, description="订阅年限（订阅制时必填）")


class OpenApiOpportunityWin(BaseModel):
    """商机赢单请求"""
    actual_amount: float = Field(..., ge=0, description="实际成交金额")
    actual_closing_date: date = Field(..., description="成交日期")
    sync_customer_status: bool = Field(default=False, description="是否同步更新客户状态为已成交")


class OpenApiOpportunityLose(BaseModel):
    """商机输单请求"""
    lose_reason: str = Field(..., min_length=1, max_length=255, description="输单原因")


# ============== 响应 ==============

class OpenApiOpportunityResponse(BaseModel):
    """商机响应"""
    opportunity_id: int = Field(..., description="商机ID")
    opportunity_name: str = Field(..., description="商机名称")
    customer_id: int = Field(..., description="客户ID")
    customer_name: str = Field(..., description="客户名称")
    estimated_amount: float = Field(..., description="预计成交金额")
    actual_amount: Optional[float] = Field(None, description="实际成交金额")
    status: int = Field(..., description="商机状态编码")
    status_name: str = Field(..., description="商机状态名称")
    purchase_type: str = Field(..., description="采购类型")
    authorization_mode: str = Field(..., description="授权模式")
    user_count: int = Field(..., description="用户数量")
    subscription_years: Optional[int] = Field(None, description="订阅年限")
    current_stage: Optional[str] = Field(None, description="当前阶段名称")
    owner_id: Optional[int] = Field(None, description="负责人ID")
    owner_name: Optional[str] = Field(None, description="负责人姓名")
    create_time: datetime = Field(..., description="创建时间")

    class Config:
        from_attributes = True


class OpenApiOpportunityStatusResponse(BaseModel):
    """商机状态响应"""
    opportunity_id: int = Field(..., description="商机ID")
    status: int = Field(..., description="商机状态编码")
    status_name: str = Field(..., description="商机状态名称")


class OpenApiOpportunityWinResponse(BaseModel):
    """商机赢单响应"""
    opportunity_id: int = Field(..., description="商机ID")
    status: int = Field(default=1, description="商机状态（1=赢单）")
    customer_status_updated: bool = Field(..., description="客户状态是否更新")


class OpenApiOpportunityLoseResponse(BaseModel):
    """商机输单响应"""
    opportunity_id: int = Field(..., description="商机ID")
    status: int = Field(default=2, description="商机状态（2=输单）")


# ============== 状态名称映射 ==============

OPPORTUNITY_STATUS_NAMES = {
    OpenApiOpportunityStatus.FOLLOWING: "跟进中",
    OpenApiOpportunityStatus.WON: "赢单",
    OpenApiOpportunityStatus.LOST: "输单"
}

PURCHASE_TYPE_NAMES = {
    OpenApiPurchaseType.NEW: "新购",
    OpenApiPurchaseType.RENEWAL: "续购",
    OpenApiPurchaseType.EXPANSION: "增购"
}

AUTHORIZATION_MODE_NAMES = {
    OpenApiAuthorizationMode.SUBSCRIPTION: "订阅制",
    OpenApiAuthorizationMode.PERPETUAL: "买断制"
}
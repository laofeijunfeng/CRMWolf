"""
客户开放接口 Schema
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import enum


class OpenApiCustomerStatus(int, enum.Enum):
    """客户状态枚举（开放接口）"""
    FOLLOWING = 0     # 跟进中
    WON = 1           # 已成交
    LOST = 2          # 已流失
    INACTIVE = 3      # 非激活


# ============== 响应 ==============

class OpenApiContactResponse(BaseModel):
    """联系人响应（脱敏版）"""
    contact_id: int = Field(..., description="联系人ID")
    name: str = Field(..., description="联系人姓名（脱敏）")
    phone: str = Field(..., description="联系电话（脱敏）")
    email: Optional[str] = Field(None, description="邮箱（脱敏）")
    position: Optional[str] = Field(None, description="职务")
    is_primary: bool = Field(default=False, description="是否主联系人")

    class Config:
        from_attributes = True


class OpenApiCustomerResponse(BaseModel):
    """客户响应（脱敏版）"""
    customer_id: int = Field(..., description="客户ID")
    account_name: str = Field(..., description="客户名称")
    industry: Optional[str] = Field(None, description="行业")
    status: int = Field(..., description="客户状态编码")
    status_name: str = Field(..., description="客户状态名称")
    primary_contact: Optional[OpenApiContactResponse] = Field(None, description="主联系人信息")
    source_lead_id: Optional[int] = Field(None, description="来源线索ID")
    owner_id: Optional[int] = Field(None, description="负责人ID")
    owner_name: Optional[str] = Field(None, description="负责人姓名")
    create_time: datetime = Field(..., description="创建时间")

    class Config:
        from_attributes = True


class OpenApiCustomerStatusResponse(BaseModel):
    """客户状态响应"""
    customer_id: int = Field(..., description="客户ID")
    status: int = Field(..., description="客户状态编码")
    status_name: str = Field(..., description="客户状态名称")


class OpenApiCustomerStatusUpdate(BaseModel):
    """更新客户状态请求"""
    status: OpenApiCustomerStatus = Field(..., description="新状态")
    reason: Optional[str] = Field(None, max_length=255, description="状态变更原因")


# ============== 状态名称映射 ==============

CUSTOMER_STATUS_NAMES = {
    OpenApiCustomerStatus.FOLLOWING: "跟进中",
    OpenApiCustomerStatus.WON: "已成交",
    OpenApiCustomerStatus.LOST: "已流失",
    OpenApiCustomerStatus.INACTIVE: "非激活"
}
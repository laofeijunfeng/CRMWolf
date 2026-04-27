"""
线索开放接口 Schema
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
import enum


class OpenApiLeadSource(str, enum.Enum):
    """线索来源枚举（开放接口）"""
    WEBSITE = "WEBSITE"
    REFERRAL = "REFERRAL"
    EVENT = "EVENT"
    COLD_CALL = "COLD_CALL"


class OpenApiLeadStatus(str, enum.Enum):
    """线索状态枚举（开放接口）"""
    NEW = "NEW"
    CONTACTED = "CONTACTED"
    QUALIFIED = "QUALIFIED"
    CONVERTED = "CONVERTED"
    INVALID = "INVALID"


# ============== 创建请求 ==============

class OpenApiLeadCreate(BaseModel):
    """创建线索请求"""
    lead_name: str = Field(..., min_length=1, max_length=255, description="线索名称（联系人姓名）")
    phone: str = Field(..., min_length=11, max_length=20, description="联系电话")
    source: OpenApiLeadSource = Field(..., description="线索来源（WEBSITE/REFERRAL/EVENT/COLD_CALL）")
    company: Optional[str] = Field(None, max_length=255, description="所属企业")
    industry: Optional[str] = Field(None, max_length=100, description="行业")
    assign_user_id: Optional[int] = Field(None, description="指定负责人ID（不填则进入公海池）")

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v):
        if not v or len(v) < 11:
            raise ValueError('手机号格式不正确')
        return v


class OpenApiLeadConvert(BaseModel):
    """线索转化请求"""
    account_name: str = Field(..., min_length=1, max_length=255, description="客户名称")
    industry: str = Field(..., min_length=1, max_length=100, description="客户行业")
    default_procurement_method_id: int = Field(..., description="默认采购方式ID")


# ============== 响应 ==============

class OpenApiLeadResponse(BaseModel):
    """线索响应（脱敏版）"""
    lead_id: int = Field(..., description="线索ID")
    lead_name: str = Field(..., description="线索名称")
    phone: str = Field(..., description="联系电话（脱敏）")
    source: str = Field(..., description="线索来源")
    source_name: str = Field(..., description="线索来源名称")
    company: Optional[str] = Field(None, description="所属企业")
    industry: Optional[str] = Field(None, description="行业")
    status: str = Field(..., description="线索状态编码")
    status_name: str = Field(..., description="线索状态名称")
    owner_id: Optional[int] = Field(None, description="负责人ID")
    owner_name: Optional[str] = Field(None, description="负责人姓名")
    create_time: datetime = Field(..., description="创建时间")

    class Config:
        from_attributes = True


class OpenApiLeadStatusResponse(BaseModel):
    """线索状态响应"""
    lead_id: int = Field(..., description="线索ID")
    status: str = Field(..., description="线索状态编码")
    status_name: str = Field(..., description="线索状态名称")


class OpenApiLeadCreateResponse(BaseModel):
    """创建线索响应"""
    lead_id: int = Field(..., description="线索ID")
    status: str = Field(default="NEW", description="初始状态为新线索")


class OpenApiLeadConvertResponse(BaseModel):
    """线索转化响应"""
    customer_id: int = Field(..., description="客户ID")
    contact_id: int = Field(..., description="联系人ID")
    lead_id: int = Field(..., description="线索ID")


# ============== 状态名称映射 ==============

LEAD_STATUS_NAMES = {
    OpenApiLeadStatus.NEW: "新线索",
    OpenApiLeadStatus.CONTACTED: "已联系",
    OpenApiLeadStatus.QUALIFIED: "已确认",
    OpenApiLeadStatus.CONVERTED: "已转化",
    OpenApiLeadStatus.INVALID: "无效"
}

LEAD_SOURCE_NAMES = {
    OpenApiLeadSource.WEBSITE: "官网",
    OpenApiLeadSource.REFERRAL: "转介绍",
    OpenApiLeadSource.EVENT: "活动",
    OpenApiLeadSource.COLD_CALL: "电话营销"
}
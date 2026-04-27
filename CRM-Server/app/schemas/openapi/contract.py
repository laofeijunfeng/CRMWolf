"""
合同开放接口 Schema
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date
import enum


class OpenApiContractStatus(str, enum.Enum):
    """合同状态枚举（开放接口）"""
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    SIGNED = "SIGNED"
    EFFECTIVE = "EFFECTIVE"
    EXPIRED = "EXPIRED"
    TERMINATED = "TERMINATED"


# ============== 创建请求 ==============

class OpenApiContractCreate(BaseModel):
    """从商机创建合同请求"""
    contract_name: str = Field(..., min_length=1, max_length=255, description="合同名称")
    signing_contact_id: int = Field(..., description="签约联系人ID")


# ============== 响应 ==============

class OpenApiContractResponse(BaseModel):
    """合同响应"""
    contract_id: int = Field(..., description="合同ID")
    contract_no: str = Field(..., description="合同编号")
    contract_name: str = Field(..., description="合同名称")
    customer_id: int = Field(..., description="客户ID")
    customer_name: str = Field(..., description="客户名称")
    opportunity_id: Optional[int] = Field(None, description="关联商机ID")
    total_amount: float = Field(..., description="合同总金额")
    status: str = Field(..., description="合同状态编码")
    status_name: str = Field(..., description="合同状态名称")
    signing_date: Optional[date] = Field(None, description="签署日期")
    effective_date: Optional[date] = Field(None, description="生效日期")
    expiry_date: Optional[date] = Field(None, description="到期日期")
    owner_id: Optional[int] = Field(None, description="负责人ID")
    owner_name: Optional[str] = Field(None, description="负责人姓名")
    create_time: datetime = Field(..., description="创建时间")

    class Config:
        from_attributes = True


class OpenApiContractStatusResponse(BaseModel):
    """合同状态响应"""
    contract_id: int = Field(..., description="合同ID")
    status: str = Field(..., description="合同状态编码")
    status_name: str = Field(..., description="合同状态名称")


class OpenApiContractCreateResponse(BaseModel):
    """创建合同响应"""
    contract_id: int = Field(..., description="合同ID")
    contract_no: str = Field(..., description="自动生成的合同编号")
    status: str = Field(default="DRAFT", description="初始状态为草稿")


# ============== 状态名称映射 ==============

CONTRACT_STATUS_NAMES = {
    OpenApiContractStatus.DRAFT: "草稿",
    OpenApiContractStatus.PENDING_REVIEW: "待审核",
    OpenApiContractStatus.SIGNED: "已签署",
    OpenApiContractStatus.EFFECTIVE: "已生效",
    OpenApiContractStatus.EXPIRED: "已到期",
    OpenApiContractStatus.TERMINATED: "已终止"
}
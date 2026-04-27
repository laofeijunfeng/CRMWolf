"""
发票开放接口 Schema
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date
import enum


class OpenApiInvoiceType(str, enum.Enum):
    """发票类型枚举"""
    VAT_SPECIAL = "VAT_SPECIAL"   # 增值税专用发票
    VAT_NORMAL = "VAT_NORMAL"     # 增值税普通发票


class OpenApiInvoiceApplicationStatus(str, enum.Enum):
    """发票申请状态枚举"""
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ISSUED = "ISSUED"


# ============== 创建请求 ==============

class OpenApiInvoiceTitleCreate(BaseModel):
    """添加发票抬头请求"""
    customer_id: int = Field(..., description="客户ID")
    title_name: str = Field(..., min_length=1, max_length=255, description="发票抬头名称")
    tax_number: str = Field(..., min_length=1, max_length=50, description="纳税人识别号")
    bank_name: Optional[str] = Field(None, max_length=100, description="开户银行")
    bank_account: Optional[str] = Field(None, max_length=50, description="银行账号")
    address: Optional[str] = Field(None, max_length=255, description="地址")
    phone: Optional[str] = Field(None, max_length=50, description="电话")
    is_default: bool = Field(default=False, description="是否默认抬头")


class OpenApiInvoiceApplicationCreate(BaseModel):
    """创建发票申请请求"""
    payment_plan_id: int = Field(..., description="回款计划ID")
    invoice_title_id: int = Field(..., description="发票抬头ID")
    invoice_amount: float = Field(..., ge=0, description="开票金额")
    invoice_type: OpenApiInvoiceType = Field(..., description="发票类型")


class OpenApiInvoiceMarkIssued(BaseModel):
    """标记发票已开具请求"""
    invoice_no: str = Field(..., min_length=1, max_length=50, description="发票号码")
    issue_date: date = Field(..., description="开票日期")


# ============== 响应 ==============

class OpenApiInvoiceTitleResponse(BaseModel):
    """发票抬头响应"""
    title_id: int = Field(..., description="发票抬头ID")
    customer_id: int = Field(..., description="客户ID")
    title_name: str = Field(..., description="发票抬头名称")
    tax_number: str = Field(..., description="纳税人识别号")
    bank_name: Optional[str] = Field(None, description="开户银行")
    bank_account: Optional[str] = Field(None, description="银行账号（脱敏）")
    address: Optional[str] = Field(None, description="地址")
    phone: Optional[str] = Field(None, description="电话（脱敏）")
    is_default: bool = Field(..., description="是否默认抬头")

    class Config:
        from_attributes = True


class OpenApiInvoiceApplicationResponse(BaseModel):
    """发票申请响应"""
    application_id: int = Field(..., description="发票申请ID")
    payment_plan_id: int = Field(..., description="回款计划ID")
    customer_id: int = Field(..., description="客户ID")
    customer_name: str = Field(..., description="客户名称")
    contract_id: int = Field(..., description="合同ID")
    contract_name: str = Field(..., description="合同名称")
    invoice_title_name: str = Field(..., description="发票抬头名称")
    tax_number: str = Field(..., description="纳税人识别号")
    invoice_amount: float = Field(..., description="开票金额")
    invoice_type: str = Field(..., description="发票类型")
    invoice_type_name: str = Field(..., description="发票类型名称")
    status: str = Field(..., description="申请状态编码")
    status_name: str = Field(..., description="申请状态名称")
    invoice_no: Optional[str] = Field(None, description="发票号码（已开具时）")
    issue_date: Optional[date] = Field(None, description="开票日期（已开具时）")
    create_time: datetime = Field(..., description="创建时间")

    class Config:
        from_attributes = True


class OpenApiInvoiceApplicationCreateResponse(BaseModel):
    """创建发票申请响应"""
    application_id: int = Field(..., description="发票申请ID")
    status: str = Field(default="DRAFT", description="初始状态为草稿")


class OpenApiInvoiceApplicationStatusResponse(BaseModel):
    """发票申请状态响应"""
    application_id: int = Field(..., description="发票申请ID")
    status: str = Field(..., description="申请状态编码")
    status_name: str = Field(..., description="申请状态名称")


# ============== 状态名称映射 ==============

INVOICE_TYPE_NAMES = {
    OpenApiInvoiceType.VAT_SPECIAL: "增值税专用发票",
    OpenApiInvoiceType.VAT_NORMAL: "增值税普通发票"
}

INVOICE_APPLICATION_STATUS_NAMES = {
    OpenApiInvoiceApplicationStatus.DRAFT: "草稿",
    OpenApiInvoiceApplicationStatus.PENDING_REVIEW: "待审批",
    OpenApiInvoiceApplicationStatus.APPROVED: "已批准",
    OpenApiInvoiceApplicationStatus.REJECTED: "已拒绝",
    OpenApiInvoiceApplicationStatus.ISSUED: "已开票"
}
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from enum import Enum


class TitleTypeEnum(str, Enum):
    COMPANY = "COMPANY"
    PERSONAL = "PERSONAL"

    @property
    def description(self):
        descriptions = {
            "COMPANY": "单位",
            "PERSONAL": "个人"
        }
        return descriptions.get(self.value, self.value)


class InvoiceApplicationStatusEnum(str, Enum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ISSUED = "ISSUED"

    @property
    def description(self):
        descriptions = {
            "DRAFT": "草稿",
            "PENDING_REVIEW": "待审批",
            "APPROVED": "已批准",
            "REJECTED": "已拒绝",
            "ISSUED": "已开票"
        }
        return descriptions.get(self.value, self.value)


class InvoiceTypeEnum(str, Enum):
    VAT_SPECIAL = "VAT_SPECIAL"
    VAT_NORMAL = "VAT_NORMAL"

    @property
    def description(self):
        descriptions = {
            "VAT_SPECIAL": "增值税专用发票",
            "VAT_NORMAL": "普通发票"
        }
        return descriptions.get(self.value, self.value)


class InvoiceTitleBase(BaseModel):
    title_type: TitleTypeEnum = Field(..., description="抬头类型：COMPANY(单位), PERSONAL(个人)")
    title: str = Field(..., min_length=1, max_length=255, description="开票抬头")
    taxpayer_id: str = Field(..., min_length=1, max_length=100, description="纳税人识别号")
    bank_name: Optional[str] = Field(None, max_length=255, description="开户行")
    bank_account: Optional[str] = Field(None, max_length=100, description="开户账号")
    address: Optional[str] = Field(None, max_length=500, description="开票地址")
    phone: Optional[str] = Field(None, max_length=50, description="电话")


class InvoiceTitleCreate(InvoiceTitleBase):
    pass


class InvoiceTitleUpdate(BaseModel):
    title_type: Optional[TitleTypeEnum] = Field(None, description="抬头类型")
    title: Optional[str] = Field(None, min_length=1, max_length=255, description="开票抬头")
    taxpayer_id: Optional[str] = Field(None, min_length=1, max_length=100, description="纳税人识别号")
    bank_name: Optional[str] = Field(None, max_length=255, description="开户行")
    bank_account: Optional[str] = Field(None, max_length=100, description="开户账号")
    address: Optional[str] = Field(None, max_length=500, description="开票地址")
    phone: Optional[str] = Field(None, max_length=50, description="电话")
    is_default: Optional[bool] = Field(None, description="是否默认抬头")


class InvoiceTitleResponse(InvoiceTitleBase):
    id: int = Field(..., description="开票抬头ID")
    customer_id: int = Field(..., description="关联客户ID")
    is_default: bool = Field(..., description="是否默认抬头")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")

    class Config:
        from_attributes = True


class InvoiceApplicationBase(BaseModel):
    payment_plan_id: int = Field(..., description="关联回款计划ID")
    invoice_title_id: int = Field(..., description="开票抬头ID")
    invoice_amount: Decimal = Field(..., gt=0, description="开票金额")
    invoice_type: InvoiceTypeEnum = Field(..., description="发票类型：VAT_SPECIAL(增值税专用发票), VAT_NORMAL(普通发票)")
    payment_record_id: Optional[int] = Field(None, description="关联回款记录ID")


class InvoiceApplicationCreate(InvoiceApplicationBase):
    pass


class InvoiceApplicationUpdate(BaseModel):
    invoice_title_id: Optional[int] = Field(None, description="开票抬头ID")
    invoice_amount: Optional[Decimal] = Field(None, gt=0, description="开票金额")
    invoice_type: Optional[InvoiceTypeEnum] = Field(None, description="发票类型")
    payment_record_id: Optional[int] = Field(None, description="关联回款记录ID")


class InvoiceApplicationResponse(InvoiceApplicationBase):
    id: int = Field(..., description="发票申请ID")
    application_number: str = Field(..., description="申请单号")
    customer_id: int = Field(..., description="关联客户ID")
    contract_id: int = Field(..., description="关联合同ID")
    opportunity_id: int = Field(..., description="关联商机ID")
    status: InvoiceApplicationStatusEnum = Field(..., description="申请状态")
    applicant_id: str = Field(..., description="申请人ID")
    reviewer_id: Optional[str] = Field(None, description="审批人ID")
    review_comment: Optional[str] = Field(None, description="审批意见")
    reviewed_time: Optional[datetime] = Field(None, description="审批时间")
    
    invoice_title_type: str = Field(..., description="抬头类型（开票快照）")
    invoice_title_text: str = Field(..., description="开票抬头（开票快照）")
    invoice_taxpayer_id: str = Field(..., description="纳税人识别号（开票快照）")
    invoice_bank_name: Optional[str] = Field(None, description="开户行（开票快照）")
    invoice_bank_account: Optional[str] = Field(None, description="开户账号（开票快照）")
    invoice_address: Optional[str] = Field(None, description="开票地址（开票快照）")
    invoice_phone: Optional[str] = Field(None, description="电话（开票快照）")
    
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")
    
    customer_name: Optional[str] = Field(None, description="客户名称")
    contract_name: Optional[str] = Field(None, description="合同名称")
    opportunity_name: Optional[str] = Field(None, description="商机名称")
    payment_plan_stage_name: Optional[str] = Field(None, description="回款计划阶段名称")
    invoice_title_title: Optional[str] = Field(None, description="开票抬头（已废弃，请使用 invoice_title_text）")
    applicant_name: Optional[str] = Field(None, description="申请人姓名")
    reviewer_name: Optional[str] = Field(None, description="审批人姓名")

    class Config:
        from_attributes = True


class InvoiceApplicationSubmit(BaseModel):
    pass


class InvoiceApplicationReview(BaseModel):
    action: str = Field(..., description="审批操作：approve(批准), reject(拒绝)")
    comment: Optional[str] = Field(None, max_length=500, description="审批意见")

    @field_validator('action')
    @classmethod
    def validate_action(cls, v):
        if v not in ['approve', 'reject']:
            raise ValueError('action必须是approve或reject')
        return v


class InvoiceTitleListResponse(BaseModel):
    invoice_titles: List[InvoiceTitleResponse] = Field(..., description="开票抬头列表")


class InvoiceApplicationListResponse(BaseModel):
    invoice_applications: List[InvoiceApplicationResponse] = Field(..., description="发票申请列表")


class PaymentPlanInvoiceSummary(BaseModel):
    payment_plan_id: int = Field(..., description="回款计划ID")
    stage_name: str = Field(..., description="阶段名称")
    planned_amount: float = Field(..., description="计划金额")
    total_invoiced_amount: float = Field(..., description="已开票总金额")
    invoice_count: int = Field(..., description="发票数量")
    invoices: List[InvoiceApplicationResponse] = Field(..., description="发票列表")


class MessageResponse(BaseModel):
    message: str = Field(..., description="响应消息")

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


class InvoiceReissueApplicationStatusEnum(str, Enum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"

    @property
    def description(self):
        descriptions = {
            "DRAFT": "草稿",
            "PENDING_REVIEW": "待审批",
            "APPROVED": "已批准",
            "REJECTED": "已拒绝",
            "COMPLETED": "已完成",
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
    customer_id: str = Field(..., description="关联客户对外ID")
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


class InvoiceReissueApplicationCreate(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500, description="重开原因")
    invoice_title_type: TitleTypeEnum = Field(..., description="新发票抬头类型")
    invoice_title_text: str = Field(..., min_length=1, max_length=255, description="新发票开票抬头")
    invoice_taxpayer_id: str = Field(..., min_length=1, max_length=100, description="新发票纳税人识别号")
    invoice_bank_name: Optional[str] = Field(None, max_length=255, description="新发票开户行")
    invoice_bank_account: Optional[str] = Field(None, max_length=100, description="新发票开户账号")
    invoice_address: Optional[str] = Field(None, max_length=500, description="新发票开票地址")
    invoice_phone: Optional[str] = Field(None, max_length=50, description="新发票电话")
    invoice_amount: Decimal = Field(..., gt=0, description="新发票金额")
    invoice_type: InvoiceTypeEnum = Field(..., description="新发票类型")

    @field_validator('reason', 'invoice_title_text', 'invoice_taxpayer_id')
    @classmethod
    def required_text_must_not_be_blank(cls, v: str):
        if not v or not v.strip():
            raise ValueError('必填文本字段不能为空')
        return v.strip()


class InvoiceReissueApplicationUpdate(BaseModel):
    reason: Optional[str] = Field(None, min_length=1, max_length=500, description="重开原因")
    invoice_title_type: Optional[TitleTypeEnum] = Field(None, description="新发票抬头类型")
    invoice_title_text: Optional[str] = Field(None, min_length=1, max_length=255, description="新发票开票抬头")
    invoice_taxpayer_id: Optional[str] = Field(None, min_length=1, max_length=100, description="新发票纳税人识别号")
    invoice_bank_name: Optional[str] = Field(None, max_length=255, description="新发票开户行")
    invoice_bank_account: Optional[str] = Field(None, max_length=100, description="新发票开户账号")
    invoice_address: Optional[str] = Field(None, max_length=500, description="新发票开票地址")
    invoice_phone: Optional[str] = Field(None, max_length=50, description="新发票电话")
    invoice_amount: Optional[Decimal] = Field(None, gt=0, description="新发票金额")
    invoice_type: Optional[InvoiceTypeEnum] = Field(None, description="新发票类型")

    @field_validator('reason', 'invoice_title_text', 'invoice_taxpayer_id')
    @classmethod
    def optional_text_must_not_be_blank(cls, v: Optional[str]):
        if v is None:
            return v
        if not v.strip():
            raise ValueError('必填文本字段不能为空')
        return v.strip()


class InvoiceReissueApplicationResponse(BaseModel):
    id: int = Field(..., description="重开申请ID")
    application_number: str = Field(..., description="重开申请单号")
    original_invoice_application_id: int = Field(..., description="原发票申请ID")
    applicant_id: str = Field(..., description="申请人ID")
    applicant_name: Optional[str] = Field(None, description="申请人姓名")
    reason: str = Field(..., description="重开原因")
    status: InvoiceReissueApplicationStatusEnum = Field(..., description="重开申请状态")
    approval_phase: Optional[str] = Field(None, description="审批流程状态")
    invoice_title_type: str = Field(..., description="新发票抬头类型")
    invoice_title_text: str = Field(..., description="新发票开票抬头")
    invoice_taxpayer_id: str = Field(..., description="新发票纳税人识别号")
    invoice_bank_name: Optional[str] = Field(None, description="新发票开户行")
    invoice_bank_account: Optional[str] = Field(None, description="新发票开户账号")
    invoice_address: Optional[str] = Field(None, description="新发票开票地址")
    invoice_phone: Optional[str] = Field(None, description="新发票电话")
    invoice_amount: Decimal = Field(..., description="新发票金额")
    invoice_type: InvoiceTypeEnum = Field(..., description="新发票类型")
    red_invoice_file_path: Optional[str] = Field(None, description="红字发票文件路径")
    red_invoice_number: Optional[str] = Field(None, description="红字发票号码")
    red_issued_time: Optional[datetime] = Field(None, description="红字发票开具时间")
    new_invoice_file_path: Optional[str] = Field(None, description="新蓝字发票文件路径")
    new_invoice_number: Optional[str] = Field(None, description="新蓝字发票号码")
    new_issued_time: Optional[datetime] = Field(None, description="新蓝字发票开具时间")
    completed_time: Optional[datetime] = Field(None, description="重开完成时间")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")

    class Config:
        from_attributes = True


class InvoiceApplicationResponse(InvoiceApplicationBase):
    id: int = Field(..., description="发票申请ID")
    application_number: str = Field(..., description="申请单号")
    customer_id: str = Field(..., description="关联客户对外ID")
    contract_id: int = Field(..., description="关联合同ID")
    opportunity_id: int = Field(..., description="关联商机ID")
    status: InvoiceApplicationStatusEnum = Field(..., description="申请状态")
    approval_phase: Optional[str] = Field(None, description="审批流程状态：draft/pending_review/approved/rejected")
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

    # Task 2: 发票文件上传字段
    invoice_file_path: Optional[str] = Field(None, description="发票文件路径（相对路径）")
    invoice_number: Optional[str] = Field(None, description="发票号码（可选，便于后续查询）")
    issued_time: Optional[datetime] = Field(None, description="开票时间（上传发票文件时间）")

    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")
    
    customer_name: Optional[str] = Field(None, description="客户名称")
    contract_name: Optional[str] = Field(None, description="合同名称")
    opportunity_name: Optional[str] = Field(None, description="商机名称")
    payment_plan_stage_name: Optional[str] = Field(None, description="回款计划阶段名称")
    invoice_title_title: Optional[str] = Field(None, description="开票抬头（已废弃，请使用 invoice_title_text）")
    applicant_name: Optional[str] = Field(None, description="申请人姓名")
    reviewer_name: Optional[str] = Field(None, description="审批人姓名")
    reissue_status: Optional[str] = Field(None, description="重开状态：NONE/REISSUE_PENDING/REISSUED")
    invoice_effective_status: Optional[str] = Field(None, description="发票有效状态：ACTIVE/REISSUE_PENDING/REISSUED")
    current_invoice_file_kind: Optional[str] = Field(None, description="当前有效发票文件来源：original/reissue_new")
    current_invoice_file_path: Optional[str] = Field(None, description="当前有效发票文件路径")
    current_invoice_number: Optional[str] = Field(None, description="当前有效发票号码")
    current_reissue_id: Optional[int] = Field(None, description="当前有效发票对应的重开申请ID")
    reissue_applications: List[InvoiceReissueApplicationResponse] = Field(default_factory=list, description="重开申请链路")

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
    items: List[InvoiceApplicationResponse] = Field(..., description="发票申请列表")
    total: int = Field(..., description="总数")
    page: int = Field(default=1, description="当前页码")
    page_size: int = Field(default=100, description="每页记录数")


class PaymentPlanInvoiceSummary(BaseModel):
    payment_plan_id: int = Field(..., description="回款计划ID")
    stage_name: str = Field(..., description="阶段名称")
    planned_amount: float = Field(..., description="计划金额")
    total_invoiced_amount: float = Field(..., description="已开票总金额")
    invoice_count: int = Field(..., description="发票数量")
    invoices: List[InvoiceApplicationResponse] = Field(..., description="发票列表")


class MessageResponse(BaseModel):
    message: str = Field(..., description="响应消息")

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class TitleTypeEnum(str, Enum):
    COMPANY = "COMPANY"
    PERSONAL = "PERSONAL"

    @property
    def description(self) -> str:
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
    def description(self) -> str:
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
    def description(self) -> str:
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
    def description(self) -> str:
        descriptions = {
            "VAT_SPECIAL": "增值税专用发票",
            "VAT_NORMAL": "普通发票"
        }
        return descriptions.get(self.value, self.value)


class InvoiceTitleBase(BaseModel):
    title_type: TitleTypeEnum = Field(..., description="抬头类型\uff1aCOMPANY(单位), PERSONAL(个人)")
    title: str = Field(..., min_length=1, max_length=255, description="开票抬头")
    taxpayer_id: str = Field(..., min_length=1, max_length=100, description="纳税人识别号")
    bank_name: str | None = Field(None, max_length=255, description="开户行")
    bank_account: str | None = Field(None, max_length=100, description="开户账号")
    address: str | None = Field(None, max_length=500, description="开票地址")
    phone: str | None = Field(None, max_length=50, description="电话")


class InvoiceTitleCreate(InvoiceTitleBase):
    pass


class InvoiceTitleUpdate(BaseModel):
    title_type: TitleTypeEnum | None = Field(None, description="抬头类型")
    title: str | None = Field(None, min_length=1, max_length=255, description="开票抬头")
    taxpayer_id: str | None = Field(None, min_length=1, max_length=100, description="纳税人识别号")
    bank_name: str | None = Field(None, max_length=255, description="开户行")
    bank_account: str | None = Field(None, max_length=100, description="开户账号")
    address: str | None = Field(None, max_length=500, description="开票地址")
    phone: str | None = Field(None, max_length=50, description="电话")
    is_default: bool | None = Field(None, description="是否默认抬头")


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
    invoice_type: InvoiceTypeEnum = Field(
        ...,
        description="发票类型\uff1aVAT_SPECIAL(增值税专用发票), VAT_NORMAL(普通发票)",
    )
    payment_record_id: int | None = Field(None, description="关联回款记录ID")





class InvoiceApplicationCreate(InvoiceApplicationBase):
    remark: str | None = Field(None, max_length=500, description="申请备注")

    @field_validator("remark")
    @classmethod
    def normalize_remark(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None



class InvoiceApplicationUpdate(BaseModel):
    invoice_title_id: int | None = Field(None, description="开票抬头ID")
    invoice_amount: Decimal | None = Field(None, gt=0, description="开票金额")
    invoice_type: InvoiceTypeEnum | None = Field(None, description="发票类型")
    payment_record_id: int | None = Field(None, description="关联回款记录ID")
    remark: str | None = Field(None, max_length=500, description="申请备注")

    @field_validator("remark")
    @classmethod
    def normalize_remark(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None



class InvoiceReissueApplicationCreate(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500, description="重开原因")
    invoice_title_type: TitleTypeEnum = Field(..., description="新发票抬头类型")
    invoice_title_text: str = Field(..., min_length=1, max_length=255, description="新发票开票抬头")
    invoice_taxpayer_id: str = Field(..., min_length=1, max_length=100, description="新发票纳税人识别号")
    invoice_bank_name: str | None = Field(None, max_length=255, description="新发票开户行")
    invoice_bank_account: str | None = Field(None, max_length=100, description="新发票开户账号")
    invoice_address: str | None = Field(None, max_length=500, description="新发票开票地址")
    invoice_phone: str | None = Field(None, max_length=50, description="新发票电话")
    invoice_amount: Decimal = Field(..., gt=0, description="新发票金额")
    invoice_type: InvoiceTypeEnum = Field(..., description="新发票类型")

    @field_validator('reason', 'invoice_title_text', 'invoice_taxpayer_id')
    @classmethod
    def required_text_must_not_be_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('必填文本字段不能为空')
        return v.strip()


class InvoiceReissueApplicationUpdate(BaseModel):
    reason: str | None = Field(None, min_length=1, max_length=500, description="重开原因")
    invoice_title_type: TitleTypeEnum | None = Field(None, description="新发票抬头类型")
    invoice_title_text: str | None = Field(None, min_length=1, max_length=255, description="新发票开票抬头")
    invoice_taxpayer_id: str | None = Field(None, min_length=1, max_length=100, description="新发票纳税人识别号")
    invoice_bank_name: str | None = Field(None, max_length=255, description="新发票开户行")
    invoice_bank_account: str | None = Field(None, max_length=100, description="新发票开户账号")
    invoice_address: str | None = Field(None, max_length=500, description="新发票开票地址")
    invoice_phone: str | None = Field(None, max_length=50, description="新发票电话")
    invoice_amount: Decimal | None = Field(None, gt=0, description="新发票金额")
    invoice_type: InvoiceTypeEnum | None = Field(None, description="新发票类型")

    @field_validator('reason', 'invoice_title_text', 'invoice_taxpayer_id')
    @classmethod
    def optional_text_must_not_be_blank(cls, v: str | None) -> str | None:
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
    applicant_name: str | None = Field(None, description="申请人姓名")
    reason: str = Field(..., description="重开原因")
    status: InvoiceReissueApplicationStatusEnum = Field(..., description="重开申请状态")
    approval_phase: str | None = Field(None, description="审批流程状态")
    invoice_title_type: str = Field(..., description="新发票抬头类型")
    invoice_title_text: str = Field(..., description="新发票开票抬头")
    invoice_taxpayer_id: str = Field(..., description="新发票纳税人识别号")
    invoice_bank_name: str | None = Field(None, description="新发票开户行")
    invoice_bank_account: str | None = Field(None, description="新发票开户账号")
    invoice_address: str | None = Field(None, description="新发票开票地址")
    invoice_phone: str | None = Field(None, description="新发票电话")
    invoice_amount: Decimal = Field(..., description="新发票金额")
    invoice_type: InvoiceTypeEnum = Field(..., description="新发票类型")
    red_invoice_file_path: str | None = Field(None, description="红字发票文件路径")
    red_invoice_number: str | None = Field(None, description="红字发票号码")
    red_issued_time: datetime | None = Field(None, description="红字发票开具时间")
    new_invoice_file_path: str | None = Field(None, description="新蓝字发票文件路径")
    new_invoice_number: str | None = Field(None, description="新蓝字发票号码")
    new_issued_time: datetime | None = Field(None, description="新蓝字发票开具时间")
    completed_time: datetime | None = Field(None, description="重开完成时间")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")

    class Config:
        from_attributes = True


class InvoiceRedOffsetResponse(BaseModel):
    id: int = Field(..., description="冲红记录ID")
    invoice_application_id: int = Field(..., description="被冲红的原发票申请ID")
    source_type: str = Field(..., description="冲红来源\uff1aMANUAL/REISSUE")
    reissue_application_id: int | None = Field(None, description="来源重开申请ID")
    red_invoice_file_path: str = Field(..., description="红字发票文件路径")
    red_invoice_number: str | None = Field(None, description="红字发票号码")
    reason: str | None = Field(None, description="冲红原因")
    created_by: str = Field(..., description="操作人ID")
    created_by_name: str | None = Field(None, description="操作人姓名")
    red_offset_time: datetime = Field(..., description="冲红时间")
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
    approval_phase: str | None = Field(None, description="审批流程状态\uff1adraft/pending_review/approved/rejected")
    applicant_id: str = Field(..., description="申请人ID")
    reviewer_id: str | None = Field(None, description="审批人ID")
    review_comment: str | None = Field(None, description="审批意见")
    reviewed_time: datetime | None = Field(None, description="审批时间")
    
    invoice_title_type: str = Field(..., description="抬头类型\uff08开票快照\uff09")
    invoice_title_text: str = Field(..., description="开票抬头\uff08开票快照\uff09")
    invoice_taxpayer_id: str = Field(..., description="纳税人识别号\uff08开票快照\uff09")
    invoice_bank_name: str | None = Field(None, description="开户行\uff08开票快照\uff09")
    invoice_bank_account: str | None = Field(None, description="开户账号\uff08开票快照\uff09")
    invoice_address: str | None = Field(None, description="开票地址\uff08开票快照\uff09")
    invoice_phone: str | None = Field(None, description="电话\uff08开票快照\uff09")
    remark: str | None = Field(None, description="申请备注")


    # Task 2: 发票文件上传字段
    invoice_file_path: str | None = Field(None, description="发票文件路径\uff08相对路径\uff09")
    invoice_number: str | None = Field(None, description="发票号码\uff08可选\uff0c便于后续查询\uff09")
    issued_time: datetime | None = Field(None, description="开票时间\uff08上传发票文件时间\uff09")

    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")
    
    customer_name: str | None = Field(None, description="客户名称")
    contract_name: str | None = Field(None, description="合同名称")
    opportunity_name: str | None = Field(None, description="商机名称")
    payment_plan_stage_name: str | None = Field(None, description="回款计划阶段名称")
    invoice_title_title: str | None = Field(
        None,
        description="开票抬头\uff08已废弃\uff0c请使用 invoice_title_text\uff09",
    )
    applicant_name: str | None = Field(None, description="申请人姓名")
    reviewer_name: str | None = Field(None, description="审批人姓名")
    reissue_status: str | None = Field(None, description="重开状态\uff1aNONE/REISSUE_PENDING/REISSUED")
    invoice_effective_status: str | None = Field(
        None,
        description="发票有效状态\uff1aACTIVE/REISSUE_PENDING/RED_OFFSET/REISSUED",
    )
    current_invoice_file_kind: str | None = Field(None, description="当前有效发票文件来源\uff1aoriginal/reissue_new")
    current_invoice_file_path: str | None = Field(None, description="当前有效发票文件路径")
    current_invoice_number: str | None = Field(None, description="当前有效发票号码")
    current_reissue_id: int | None = Field(None, description="当前有效发票对应的重开申请ID")
    red_offsets: list[InvoiceRedOffsetResponse] = Field(default_factory=list, description="冲红记录")
    reissue_applications: list[InvoiceReissueApplicationResponse] = Field(
        default_factory=list,
        description="重开申请链路",
    )

    class Config:
        from_attributes = True


class InvoiceApplicationSubmit(BaseModel):
    pass


class InvoiceApplicationReview(BaseModel):
    action: str = Field(..., description="审批操作\uff1aapprove(批准), reject(拒绝)")
    comment: str | None = Field(None, max_length=500, description="审批意见")

    @field_validator('action')
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v not in ['approve', 'reject']:
            raise ValueError('action必须是approve或reject')
        return v


class InvoiceTitleListResponse(BaseModel):
    invoice_titles: list[InvoiceTitleResponse] = Field(..., description="开票抬头列表")


class InvoiceApplicationListResponse(BaseModel):
    items: list[InvoiceApplicationResponse] = Field(..., description="发票申请列表")
    total: int = Field(..., description="总数")
    page: int = Field(default=1, description="当前页码")
    page_size: int = Field(default=100, description="每页记录数")


class PaymentPlanInvoiceSummary(BaseModel):
    payment_plan_id: int = Field(..., description="回款计划ID")
    stage_name: str = Field(..., description="阶段名称")
    planned_amount: float = Field(..., description="计划金额")
    total_invoiced_amount: float = Field(..., description="已开票总金额")
    invoice_count: int = Field(..., description="发票数量")
    invoices: list[InvoiceApplicationResponse] = Field(..., description="发票列表")


class MessageResponse(BaseModel):
    message: str = Field(..., description="响应消息")

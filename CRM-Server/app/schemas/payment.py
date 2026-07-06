from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Generic, TypeVar
from datetime import date, datetime
from enum import Enum

T = TypeVar('T')


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T] = Field(..., description="数据列表")
    total: int = Field(..., description="总数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页大小")
    total_pages: int = Field(..., description="总页数")


class PaymentPlanStatusEnum(str, Enum):
    PENDING = "PENDING"
    OVERDUE = "OVERDUE"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"
    
    @property
    def description(self):
        descriptions = {
            "PENDING": "待回款",
            "OVERDUE": "已逾期",
            "PARTIAL": "部分回款",
            "COMPLETED": "已完成"
        }
        return descriptions.get(self.value, self.value)


class PaymentStatusEnum(str, Enum):
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"
    OVERDUE = "OVERDUE"
    
    @property
    def description(self):
        descriptions = {
            "UNPAID": "未回款",
            "PARTIAL": "部分回款",
            "COMPLETED": "已回完",
            "OVERDUE": "有逾期"
        }
        return descriptions.get(self.value, self.value)


class PaymentPlanBase(BaseModel):
    stage_name: str = Field(..., max_length=100, description="回款阶段名")
    planned_amount: float = Field(..., gt=0, description="计划回款金额")
    due_date: date = Field(..., description="计划回款日期")
    notes: Optional[str] = Field(None, description="备注")


class PaymentPlanCreate(PaymentPlanBase):
    pass


class PaymentPlanUpdate(BaseModel):
    stage_name: Optional[str] = Field(None, max_length=100, description="回款阶段名")
    planned_amount: Optional[float] = Field(None, gt=0, description="计划回款金额")
    due_date: Optional[date] = Field(None, description="计划回款日期")
    notes: Optional[str] = Field(None, description="备注")


class PaymentRecordInfo(BaseModel):
    id: int
    actual_amount: float
    payment_date: date
    proof_attachment: Optional[str]
    creator_name: Optional[str]
    created_time: datetime

    class Config:
        from_attributes = True


class PaymentPlanResponse(PaymentPlanBase):
    id: int
    contract_id: int
    status: PaymentPlanStatusEnum
    status_name: Optional[str] = Field(None, description="状态名称")
    created_time: datetime
    last_modified_time: datetime
    paid_amount: Optional[float] = Field(None, description="已回款金额")
    remaining_amount: Optional[float] = Field(None, description="待回款金额")
    payment_records: List[PaymentRecordInfo] = Field(default_factory=list, description="回款记录列表")
    contract_name: Optional[str] = Field(None, description="合同名称")
    creator_id: Optional[str] = Field(None, description="合同创建人ID")
    customer_id: Optional[int] = Field(None, description="客户ID")
    customer_name: Optional[str] = Field(None, description="客户名称")
    opportunity_id: Optional[int] = Field(None, description="商机ID")
    opportunity_name: Optional[str] = Field(None, description="商机名称")
    owner_id: Optional[str] = Field(None, description="负责人ID（商机负责人）")
    owner_name: Optional[str] = Field(None, description="负责人姓名")
    is_invoiced: bool = Field(False, description="是否已开票")
    invoice_count: int = Field(0, description="开票数量")
    invoiced_amount: Optional[float] = Field(None, description="已开票金额")

    @field_validator('status_name', mode='before')
    def set_status_name(cls, v, info):
        if v is None and 'status' in info.data:
            status = info.data['status']
            if isinstance(status, PaymentPlanStatusEnum):
                return status.description
            elif isinstance(status, str):
                try:
                    return PaymentPlanStatusEnum(status).description
                except ValueError:
                    return status
        return v

    @field_validator('paid_amount', 'remaining_amount', mode='before')
    def parse_amount(cls, v):
        return float(v) if v is not None else None

    class Config:
        from_attributes = True


class PaymentPlanBatchCreate(BaseModel):
    plans: List[PaymentPlanCreate] = Field(..., min_length=1, description="回款计划列表")


class PaymentRecordBase(BaseModel):
    actual_amount: float = Field(..., gt=0, description="实际回款金额")
    payment_date: date = Field(..., description="实际回款日期")
    proof_attachment: Optional[str] = Field(None, max_length=500, description="回款凭证附件URL")
    notes: Optional[str] = Field(None, description="备注")


class PaymentRecordCreate(PaymentRecordBase):
    pass


class PaymentRecordUpdate(BaseModel):
    actual_amount: Optional[float] = Field(None, gt=0, description="实际回款金额")
    payment_date: Optional[date] = Field(None, description="实际回款日期")
    proof_attachment: Optional[str] = Field(None, max_length=500, description="回款凭证附件URL")
    notes: Optional[str] = Field(None, description="备注")


class PaymentRecordResponse(PaymentRecordBase):
    id: int
    payment_plan_id: int
    creator_id: str
    creator_name: Optional[str]
    created_time: datetime
    contract_id: Optional[int] = Field(None, description="合同ID")
    contract_name: Optional[str] = Field(None, description="合同名称")
    stage_name: Optional[str] = Field(None, description="回款阶段名称")
    customer_id: Optional[int] = Field(None, description="客户ID")
    customer_name: Optional[str] = Field(None, description="客户名称")
    opportunity_id: Optional[int] = Field(None, description="商机ID")
    opportunity_name: Optional[str] = Field(None, description="商机名称")

    class Config:
        from_attributes = True


class ContractPaymentSummary(BaseModel):
    contract_id: int
    contract_name: str
    total_amount: float
    total_paid_amount: float
    payment_status: PaymentStatusEnum
    payment_plans_count: int
    completed_plans_count: int
    overdue_plans_count: int
    remaining_amount: float
    customer_id: Optional[int] = Field(None, description="客户ID")
    customer_name: Optional[str] = Field(None, description="客户名称")
    opportunity_id: Optional[int] = Field(None, description="商机ID")
    opportunity_name: Optional[str] = Field(None, description="商机名称")


class PaymentReminder(BaseModel):
    plan_id: int
    contract_name: str
    stage_name: str
    planned_amount: float
    due_date: date
    days_until_due: int
    contract_owner_id: str
    customer_name: Optional[str] = Field(None, description="客户名称")
    opportunity_name: Optional[str] = Field(None, description="商机名称")


class PaymentConfirmationStatusEnum(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    DISPUTED = "DISPUTED"
    
    @property
    def description(self):
        descriptions = {
            "PENDING": "待确认",
            "CONFIRMED": "已确认",
            "DISPUTED": "有争议"
        }
        return descriptions.get(self.value, self.value)


class PaymentRecordConfirm(BaseModel):
    action: str = Field(..., description="确认操作：confirm(确认), dispute(争议)")
    notes: Optional[str] = Field(None, description="确认备注或争议说明")
    invoice_application_ids: Optional[List[int]] = Field(None, description="关联的发票申请ID列表")


class PaymentRecordWithConfirmation(PaymentRecordResponse):
    confirmation_status: PaymentConfirmationStatusEnum
    confirmed_by: Optional[str] = Field(None, description="确认人ID")
    confirmed_by_name: Optional[str] = Field(None, description="确认人姓名")
    confirmed_time: Optional[datetime] = Field(None, description="确认时间")
    confirmation_notes: Optional[str] = Field(None, description="确认备注")


# Task 1.4: PaymentRecord list response schemas

class ApprovalNodeInfo(BaseModel):
    """审批节点信息"""
    id: int
    node_order: int
    node_name: str
    approve_role: str
    status: str = "PENDING"
    approver_id: Optional[str] = None
    approver_name: Optional[str] = None
    comment: Optional[str] = None


class ApprovalInfo(BaseModel):
    """审批信息"""
    id: int
    status: str
    current_approver_name: Optional[str] = None
    nodes: List[ApprovalNodeInfo] = Field(default_factory=list)


class PaymentRecordListItem(PaymentRecordResponse):
    """回款记录列表项（含审批信息）"""
    confirmation_status: PaymentConfirmationStatusEnum = Field(..., description="确认状态")
    approval_id: Optional[int] = Field(None, description="审批ID")
    approval: Optional[ApprovalInfo] = Field(None, description="审批信息")


class PaymentRecordListResponse(BaseModel, Generic[T]):
    """回款记录列表响应（含待我审批数量）"""
    items: List[T] = Field(..., description="数据列表")
    total: int = Field(..., description="总数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页大小")
    total_pages: int = Field(..., description="总页数")
    pending_approval_me_count: int = Field(..., description="待我审批的回款记录数量")

"""
回款开放接口 Schema
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, date
import enum


class OpenApiPaymentPlanStatus(str, enum.Enum):
    """回款计划状态枚举"""
    PENDING = "PENDING"
    OVERDUE = "OVERDUE"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"


class OpenApiPaymentMethod(str, enum.Enum):
    """回款方式枚举"""
    TRANSFER = "TRANSFER"   # 转账
    CASH = "CASH"           # 现金
    CHECK = "CHECK"         # 支票
    OTHER = "OTHER"         # 其他


# ============== 创建请求 ==============

class OpenApiPaymentPlanItem(BaseModel):
    """单个回款计划"""
    stage_name: str = Field(..., min_length=1, max_length=100, description="回款阶段名（如：首付、尾款）")
    planned_amount: float = Field(..., ge=0, description="计划回款金额")
    due_date: date = Field(..., description="计划回款日期")


class OpenApiPaymentPlanCreate(BaseModel):
    """创建回款计划请求"""
    plans: List[OpenApiPaymentPlanItem] = Field(..., min_length=1, description="回款计划列表")


class OpenApiPaymentRecordCreate(BaseModel):
    """登记回款请求"""
    actual_amount: float = Field(..., ge=0, description="实际回款金额")
    payment_time: date = Field(..., description="回款时间")
    payment_method: Optional[OpenApiPaymentMethod] = Field(None, description="回款方式")
    remark: Optional[str] = Field(None, max_length=255, description="备注")


# ============== 响应 ==============

class OpenApiPaymentPlanResponse(BaseModel):
    """回款计划响应"""
    plan_id: int = Field(..., description="回款计划ID")
    contract_id: int = Field(..., description="合同ID")
    contract_name: str = Field(..., description="合同名称")
    stage_name: str = Field(..., description="回款阶段名")
    planned_amount: float = Field(..., description="计划回款金额")
    paid_amount: float = Field(default=0, description="已回款金额")
    remaining_amount: float = Field(..., description="剩余待回款金额")
    due_date: date = Field(..., description="计划回款日期")
    status: str = Field(..., description="回款计划状态编码")
    status_name: str = Field(..., description="回款计划状态名称")

    class Config:
        from_attributes = True


class OpenApiPaymentRecordResponse(BaseModel):
    """回款记录响应"""
    record_id: int = Field(..., description="回款记录ID")
    plan_id: int = Field(..., description="回款计划ID")
    actual_amount: float = Field(..., description="实际回款金额")
    payment_time: date = Field(..., description="回款时间")
    payment_method: Optional[str] = Field(None, description="回款方式")
    remark: Optional[str] = Field(None, description="备注")
    creator_name: Optional[str] = Field(None, description="登记人")
    create_time: datetime = Field(..., description="创建时间")

    class Config:
        from_attributes = True


class OpenApiPaymentRecordCreateResponse(BaseModel):
    """登记回款响应"""
    record_id: int = Field(..., description="回款记录ID")
    plan_id: int = Field(..., description="回款计划ID")
    plan_status: str = Field(..., description="回款计划状态")


class OpenApiPaymentSummaryResponse(BaseModel):
    """合同回款汇总响应"""
    contract_id: int = Field(..., description="合同ID")
    contract_name: str = Field(..., description="合同名称")
    total_amount: float = Field(..., description="合同总金额")
    total_planned: float = Field(..., description="计划回款总额")
    total_paid: float = Field(..., description="已回款总额")
    total_remaining: float = Field(..., description="剩余待回款")
    completion_rate: float = Field(..., description="回款完成率（百分比）")
    plan_count: int = Field(..., description="回款计划数量")
    completed_count: int = Field(..., description="已完成计划数量")
    overdue_count: int = Field(..., description="逾期计划数量")


class OpenApiOverdueReminder(BaseModel):
    """逾期回款提醒"""
    plan_id: int = Field(..., description="回款计划ID")
    contract_id: int = Field(..., description="合同ID")
    contract_name: str = Field(..., description="合同名称")
    customer_name: str = Field(..., description="客户名称")
    stage_name: str = Field(..., description="回款阶段名")
    planned_amount: float = Field(..., description="计划回款金额")
    paid_amount: float = Field(..., description="已回款金额")
    due_date: date = Field(..., description="计划回款日期")
    overdue_days: int = Field(..., description="逾期天数")

    class Config:
        from_attributes = True


# ============== 状态名称映射 ==============

PAYMENT_PLAN_STATUS_NAMES = {
    OpenApiPaymentPlanStatus.PENDING: "待回款",
    OpenApiPaymentPlanStatus.OVERDUE: "已逾期",
    OpenApiPaymentPlanStatus.PARTIAL: "部分回款",
    OpenApiPaymentPlanStatus.COMPLETED: "已完成"
}

PAYMENT_METHOD_NAMES = {
    OpenApiPaymentMethod.TRANSFER: "转账",
    OpenApiPaymentMethod.CASH: "现金",
    OpenApiPaymentMethod.CHECK: "支票",
    OpenApiPaymentMethod.OTHER: "其他"
}
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
import enum


class EventAction(str, enum.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    CANCEL = "CANCEL"
    CONVERT = "CONVERT"
    WIN = "WIN"
    LOSE = "LOSE"


class PrimaryResourceType(str, enum.Enum):
    LEAD = "LEAD"
    CUSTOMER = "CUSTOMER"
    OPPORTUNITY = "OPPORTUNITY"
    CONTRACT = "CONTRACT"
    INVOICE = "INVOICE"
    PAYMENT_PLAN = "PAYMENT_PLAN"
    PAYMENT_RECORD = "PAYMENT_RECORD"


class OperationLogCreate(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=50, description="事件类型")
    event_action: str = Field(..., min_length=1, max_length=20, description="事件动作")
    primary_resource_type: str = Field(..., min_length=1, max_length=20, description="主资源类型")
    primary_resource_id: int = Field(..., gt=0, description="主资源ID")
    secondary_resource_type: Optional[str] = Field(None, max_length=20, description="次资源类型")
    secondary_resource_id: Optional[int] = Field(None, gt=0, description="次资源ID")
    operator_id: str = Field(..., min_length=1, max_length=100, description="操作人ID")
    operator_name: Optional[str] = Field(None, max_length=100, description="操作人姓名")
    content: Dict[str, Any] = Field(..., description="事件内容")
    remark: Optional[str] = Field(None, max_length=500, description="备注")


class OperationLogResponse(BaseModel):
    id: int = Field(..., description="记录ID")
    event_id: str = Field(..., description="事件唯一ID")
    event_type: str = Field(..., description="事件类型")
    event_action: str = Field(..., description="事件动作")
    primary_resource_type: str = Field(..., description="主资源类型")
    primary_resource_id: int = Field(..., description="主资源ID")
    secondary_resource_type: Optional[str] = Field(None, description="次资源类型")
    secondary_resource_id: Optional[int] = Field(None, description="次资源ID")
    operator_id: str = Field(..., description="操作人ID")
    operator_name: Optional[str] = Field(None, description="操作人姓名")
    operated_at: datetime = Field(..., description="操作时间")
    content: Dict[str, Any] = Field(..., description="事件内容")
    remark: Optional[str] = Field(None, description="备注")
    
    model_config = ConfigDict(from_attributes=True)


class OperationLogListResponse(BaseModel):
    list: List[OperationLogResponse] = Field(..., description="操作记录列表")
    total: int = Field(..., description="总记录数")
    page_no: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")

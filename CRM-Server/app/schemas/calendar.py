from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime


class TodoCount(BaseModel):
    lead: int = 0
    customer: int = 0
    opportunity: int = 0
    payment: int = 0
    total: int = 0


class CalendarMonthResponse(BaseModel):
    year: int
    month: int
    todos: dict[str, TodoCount]


class LeadFollowUpTodo(BaseModel):
    id: int
    lead_id: int
    lead_name: str
    contact_name: str
    contact_phone: str
    next_action: Optional[str]
    next_follow_time: Optional[datetime]
    is_overdue: bool


class CustomerFollowUpTodo(BaseModel):
    id: int
    customer_id: int
    account_name: str
    next_action: Optional[str]
    next_follow_time: Optional[datetime]
    is_overdue: bool


class OpportunityTodo(BaseModel):
    id: int
    opportunity_name: str
    customer_name: str
    total_amount: float
    expected_closing_date: date
    current_stage_name: Optional[str]
    is_overdue: bool


class PaymentPlanTodo(BaseModel):
    id: int
    contract_id: int
    contract_name: str
    customer_name: str
    stage_name: str
    planned_amount: float
    due_date: date
    is_overdue: bool


class CalendarDateDetailResponse(BaseModel):
    date: str
    lead_follow_ups: List[LeadFollowUpTodo]
    customer_follow_ups: List[CustomerFollowUpTodo]
    opportunities: List[OpportunityTodo]
    payment_plans: List[PaymentPlanTodo]
    total_count: int


# FollowUp AI 跟进相关 Schema
from typing import Dict, Any


class FollowUpParseRequest(BaseModel):
    """跟进解析请求"""
    todo_type: str
    todo_id: int
    user_input: str


class FollowUpParseResponse(BaseModel):
    """跟进解析响应"""
    actions: List[Dict[str, Any]]
    reply_text: str
    context: Dict[str, Any]


class FollowUpExecuteRequest(BaseModel):
    """跟进执行请求"""
    actions: List[Dict[str, Any]]


class FollowUpExecuteResult(BaseModel):
    """单个 action 执行结果"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class FollowUpExecuteResponse(BaseModel):
    """跟进执行响应"""
    success: bool
    message: str
    results: List[FollowUpExecuteResult]


class TodoContextResponse(BaseModel):
    """待办上下文响应"""
    todo_type: str
    todo_id: int
    entity_type: str
    entity_id: int
    entity_info: Dict[str, Any]
    current_next_follow_time: Optional[str]
    current_next_action: Optional[str]
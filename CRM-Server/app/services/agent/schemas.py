"""Structured contracts for CRM AI Agent reasoning."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


AgentIntent = Literal[
    "CUSTOMER_FOLLOW_UP",
    "PAYMENT_RECORD",
    "CREATE_CONTACT",
    "CREATE_INVOICE_TITLE",
    "CREATE_DEPLOYMENT_INFO",
    "CUSTOMER_QUERY",
    "UNKNOWN",
]

AgentHITLDecisionType = Literal["approve", "edit", "reject", "respond"]
AgentTemporalKind = Literal["NONE", "EXPLICIT_DATE", "RELATIVE_DAY", "RELATIVE_WEEKDAY", "UNKNOWN"]
AgentTemporalDirection = Literal["past", "current", "next", "future"]
AgentTemporalUnit = Literal["day", "week", "month"]


class AgentCustomerEntity(BaseModel):
    name_text: Optional[str] = Field(None, description="用户原文中的客户名称或简称")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="客户名称识别置信度")


class AgentFollowUpEntity(BaseModel):
    content: Optional[str] = Field(None, description="可沉淀为客户跟进记录的业务事实")
    method: Optional[str] = Field(None, description="跟进方式，例如电话、微信、拜访、邮件、未指定")
    next_action: Optional[str] = Field(None, description="下一步动作")
    next_follow_time_text: Optional[str] = Field(None, description="用户表达中的下一步动作时间")
    next_follow_time: Optional["AgentTemporalExpression"] = Field(None, description="用户表达的结构化时间要素")
    next_follow_time_iso: Optional[str] = Field(None, description="系统计算字段，AI 必须返回 null")


class AgentTemporalExpression(BaseModel):
    raw_text: Optional[str] = Field(None, description="用户原文中的时间表达")
    kind: AgentTemporalKind = Field("NONE", description="时间表达类型")
    direction: Optional[AgentTemporalDirection] = Field(None, description="相对方向，例如下一个、当前、未来")
    amount: Optional[int] = Field(None, ge=0, description="相对数量")
    unit: Optional[AgentTemporalUnit] = Field(None, description="相对单位")
    weekday: Optional[int] = Field(None, ge=1, le=7, description="ISO 星期：1=周一，7=周日")
    date_text: Optional[str] = Field(None, description="用户明确表达的日期，YYYY-MM-DD")
    hour: Optional[int] = Field(None, ge=0, le=23, description="小时，未指定则为 null")
    minute: Optional[int] = Field(None, ge=0, le=59, description="分钟，未指定则为 null")
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class AgentBusinessSignal(BaseModel):
    type: str = Field(..., description="业务信号类型")
    summary: str = Field(..., description="业务信号摘要")
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class AgentRequestedAction(BaseModel):
    action: str = Field(..., description="候选动作名称")
    requires_confirmation: bool = Field(True, description="执行前是否需要用户确认")
    reason: Optional[str] = Field(None, description="动作触发原因")


class AgentSemanticParseResult(BaseModel):
    intent: AgentIntent = Field("UNKNOWN", description="归一化意图")
    intent_confidence: float = Field(0.0, ge=0.0, le=1.0)
    customer: AgentCustomerEntity = Field(default_factory=AgentCustomerEntity)
    follow_up: AgentFollowUpEntity = Field(default_factory=AgentFollowUpEntity)
    contact: Dict[str, Any] = Field(default_factory=dict)
    invoice_title: Dict[str, Any] = Field(default_factory=dict)
    deployment_info: Dict[str, Any] = Field(default_factory=dict)
    business_signals: List[AgentBusinessSignal] = Field(default_factory=list)
    requested_actions: List[AgentRequestedAction] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    need_clarification: bool = Field(False)
    clarification_question: Optional[str] = Field(None)
    evidence: List[str] = Field(default_factory=list, description="用于解释判断的原文依据")


class AgentMemorySnapshot(BaseModel):
    recent_messages: List[Dict[str, Any]] = Field(default_factory=list)
    pending_task: Optional[Dict[str, Any]] = None
    session_context: Dict[str, Any] = Field(default_factory=dict)


class AgentHITLPolicy(BaseModel):
    allowed_decisions: List[AgentHITLDecisionType] = Field(
        default_factory=lambda: ["approve", "edit", "reject", "respond"],
    )
    required_for_tools: List[str] = Field(default_factory=list)
    confirmation_summary: Optional[str] = None


class AgentHITLDecision(BaseModel):
    decision: AgentHITLDecisionType
    task_id: Optional[int] = None
    edited_payload: Optional[Dict[str, Any]] = None
    user_message: Optional[str] = None

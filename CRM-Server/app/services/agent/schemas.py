"""Structured contracts for CRM AI Agent reasoning."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


AgentIntent = Literal[
    "CUSTOMER_ACTIVITY",
    "PAYMENT_RECORD",
    "CREATE_LEAD",
    "CREATE_CUSTOMER",
    "CREATE_OPPORTUNITY",
    "CREATE_CONTACT",
    "CREATE_INVOICE_TITLE",
    "CREATE_DEPLOYMENT_INFO",
    "CREATE_CUSTOMER_MEMBER",
    "CUSTOMER_QUERY",
    "UNKNOWN",
]

AgentHITLDecisionType = Literal["approve", "edit", "reject", "respond"]
AgentPendingInterruptionDecisionType = Literal["CONTINUE_PENDING", "START_NEW_FLOW", "ASK_USER"]
AgentTurnRelationDecisionType = Literal[
    "CONTINUE_ACTIVE_TASK",
    "PATCH_ACTIVE_DRAFT",
    "RESUME_SUSPENDED_DRAFT",
    "START_NEW_FLOW",
    "ASK_USER",
    "CHITCHAT",
]
AgentConfirmationIntentType = Literal["confirm", "reject", "unknown"]
AgentSuggestionAction = Literal[
    "CREATE_OPPORTUNITY",
    "MOVE_OPPORTUNITY_STAGE",
    "CREATE_CONTACT",
    "CREATE_PAYMENT_PLAN",
    "CREATE_PAYMENT_RECORD",
    "CREATE_INVOICE_TITLE",
    "CREATE_DEPLOYMENT_INFO",
    "CREATE_LICENSE_APPLICATION",
    "CUSTOMER_QUERY_SUMMARY",
    "NO_ACTION",
]
AgentTemporalKind = Literal[
    "NONE",
    "EXPLICIT_DATE",
    "MONTH_DAY",
    "MONTH_END",
    "RELATIVE_DAY",
    "RELATIVE_WEEKDAY",
    "RELATIVE_MONTH_END",
    "UNKNOWN",
]
AgentTemporalDirection = Literal["past", "current", "next", "future"]
AgentTemporalUnit = Literal["day", "week", "month"]


class AgentCustomerEntity(BaseModel):
    name_text: Optional[str] = Field(None, description="用户原文中的客户名称或简称")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="客户名称识别置信度")
    resolution_source: Literal["EXPLICIT", "MEMORY", "NONE"] = Field("NONE", description="客户来源：用户明示、会话记忆或无")


class AgentFollowUpEntity(BaseModel):
    content: Optional[str] = Field(None, description="可沉淀为客户跟进记录的业务事实")
    method: Optional[str] = Field(None, description="活动方式，例如电话、微信、拜访、邮件、线上会议、线下会议、未指定")
    next_action: Optional[str] = Field(None, description="下一步动作")
    next_follow_time_text: Optional[str] = Field(None, description="用户表达中的下一步动作时间")
    next_follow_time: Optional["AgentTemporalExpression"] = Field(None, description="用户表达的结构化时间要素")
    next_follow_time_iso: Optional[str] = Field(None, description="系统计算字段，AI 必须返回 null")


class AgentPaymentEntity(BaseModel):
    actual_amount: Optional[float] = Field(None, gt=0, description="实际回款金额")
    actual_payer_name: Optional[str] = Field(None, description="实际付款方名称")
    payment_date_text: Optional[str] = Field(None, description="用户原文中的实际回款日期表达")
    payment_date: Optional["AgentTemporalExpression"] = Field(None, description="用户表达的结构化实际回款日期")
    payment_date_iso: Optional[str] = Field(None, description="系统计算字段，AI 必须返回 null")
    notes: Optional[str] = Field(None, description="回款备注")


class AgentOpportunityEntity(BaseModel):
    opportunity_name: Optional[str] = Field(None, description="废弃输入字段；创建时由后端 API 自动生成")
    procurement_method_id: Optional[int] = Field(None, ge=1, description="采购方式 ID；用户通过系统交互选择时提取")
    total_amount: Optional[float] = Field(None, gt=0, description="预计总金额（元）")
    user_count: Optional[int] = Field(None, gt=0, description="采购用户数")
    license_type: Optional[Literal["SUBSCRIPTION", "PERPETUAL"]] = Field(None, description="授权模式")
    subscription_years: Optional[int] = Field(None, gt=0, description="订阅年限")
    purchase_type: Optional[Literal["NEW", "RENEWAL", "EXPANSION"]] = Field(None, description="采购类型")
    decision_maker_count: Optional[int] = Field(None, ge=1, description="采购决策人数")
    expected_closing_date_text: Optional[str] = Field(None, description="用户原文中的预计成交日期表达")
    expected_closing_date: Optional["AgentTemporalExpression"] = Field(None, description="预计成交日期结构化时间")
    expected_closing_date_iso: Optional[str] = Field(None, description="系统计算字段，AI 必须返回 null")


class AgentLeadEntity(BaseModel):
    lead_name: Optional[str] = Field(None, description="线索名称、项目名称或公司名称")
    source: Optional[str] = Field(None, description="线索来源中文枚举值")
    city: Optional[str] = Field(None, description="所在城市")
    contact_name: Optional[str] = Field(None, description="联系人姓名")
    contact_phone: Optional[str] = Field(None, description="联系人手机号")
    company_scale: Optional[str] = Field(None, description="公司规模中文枚举值")
    follow_up_content: Optional[str] = Field(None, description="创建线索后可沉淀的线索跟进内容")
    follow_up_method: Optional[str] = Field(None, description="线索跟进方式")
    next_action: Optional[str] = Field(None, description="下一步动作")
    next_follow_time_text: Optional[str] = Field(None, description="用户表达中的线索下次跟进时间")
    next_follow_time: Optional["AgentTemporalExpression"] = Field(None, description="用户表达的结构化线索下次跟进时间")
    next_follow_time_iso: Optional[str] = Field(None, description="系统计算字段，AI 必须返回 null")


class AgentCustomerCreateEntity(BaseModel):
    account_name: Optional[str] = Field(None, description="客户公司名称")
    source: Optional[str] = Field(None, description="客户来源中文枚举值")
    city: Optional[str] = Field(None, description="所在城市")
    industry: Optional[str] = Field(None, description="所属行业")
    company_scale: Optional[str] = Field(None, description="公司规模中文枚举值")
    contact_name: Optional[str] = Field(None, description="主联系人姓名")
    contact_phone: Optional[str] = Field(None, description="主联系人手机号")
    contact_position: Optional[str] = Field(None, description="主联系人职务")
    contact_gender: Optional[str] = Field(None, description="主联系人性别：1=男,2=女,0=未知")
    contact_email: Optional[str] = Field(None, description="主联系人邮箱")
    follow_up_content: Optional[str] = Field(None, description="创建客户后可沉淀的客户跟进内容")
    follow_up_method: Optional[str] = Field(None, description="客户活动方式")
    next_action: Optional[str] = Field(None, description="下一步动作")
    next_follow_time_text: Optional[str] = Field(None, description="用户表达中的客户下次跟进时间")
    next_follow_time: Optional["AgentTemporalExpression"] = Field(None, description="用户表达的结构化客户下次跟进时间")
    next_follow_time_iso: Optional[str] = Field(None, description="系统计算字段，AI 必须返回 null")


class AgentTemporalExpression(BaseModel):
    raw_text: Optional[str] = Field(None, description="用户原文中的时间表达")
    kind: AgentTemporalKind = Field("NONE", description="时间表达类型")
    direction: Optional[AgentTemporalDirection] = Field(None, description="相对方向，例如下一个、当前、未来")
    amount: Optional[int] = Field(None, ge=0, description="相对数量")
    unit: Optional[AgentTemporalUnit] = Field(None, description="相对单位")
    weekday: Optional[int] = Field(None, ge=1, le=7, description="ISO 星期：1=周一，7=周日")
    year: Optional[int] = Field(None, ge=1970, le=2100, description="年份；用户未表达则为 null")
    month: Optional[int] = Field(None, ge=1, le=12, description="月份；用户未表达则为 null")
    day: Optional[int] = Field(None, ge=1, le=31, description="日期；用户未表达则为 null")
    date_text: Optional[str] = Field(None, description="用户明确表达的日期，YYYY-MM-DD")
    hour: Optional[int] = Field(None, ge=0, le=23, description="小时，未指定则为 null")
    minute: Optional[int] = Field(None, ge=0, le=59, description="分钟，未指定则为 null")
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class AgentBusinessSignal(BaseModel):
    type: str = Field(..., description="业务信号类型")
    summary: str = Field(..., description="业务信号摘要")
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class AgentFollowUpPrincipleScore(BaseModel):
    score: int = Field(0, ge=0, le=20, description="该原则得分")
    max_score: int = Field(0, ge=0, le=20, description="该原则满分")
    comment: str = Field("", description="一句话说明扣分或得分依据")


class AgentFollowUpQualityResult(BaseModel):
    score: int = Field(0, ge=0, le=100, description="跟进质量总分，满分 100")
    passed: bool = Field(False, description="是否达到创建跟进记录前的最低质量要求")
    reason: str = Field("", description="一句话质量结论")
    missing_aspects: List[str] = Field(default_factory=list, description="需要用户补充的关键信息点")
    supplement_question: Optional[str] = Field(None, description="低于阈值时，只问一个补充问题")
    suggested_revision: Optional[str] = Field(None, description="不编造事实前提下的建议优化版本")
    principle_scores: Dict[str, AgentFollowUpPrincipleScore] = Field(default_factory=dict)


class AgentRequestedAction(BaseModel):
    action: str = Field(..., description="候选动作名称")
    requires_confirmation: bool = Field(True, description="执行前是否需要用户确认")
    reason: Optional[str] = Field(None, description="动作触发原因")


class AgentSemanticParseResult(BaseModel):
    intent: AgentIntent = Field("UNKNOWN", description="归一化意图")
    intent_confidence: float = Field(0.0, ge=0.0, le=1.0)
    customer: AgentCustomerEntity = Field(default_factory=AgentCustomerEntity)
    follow_up: AgentFollowUpEntity = Field(default_factory=AgentFollowUpEntity)
    payment: AgentPaymentEntity = Field(default_factory=AgentPaymentEntity)
    lead: AgentLeadEntity = Field(default_factory=AgentLeadEntity)
    customer_create: AgentCustomerCreateEntity = Field(default_factory=AgentCustomerCreateEntity)
    opportunity: AgentOpportunityEntity = Field(default_factory=AgentOpportunityEntity)
    contact: Dict[str, object] = Field(default_factory=dict)
    invoice_title: Dict[str, object] = Field(default_factory=dict)
    deployment_info: Dict[str, object] = Field(default_factory=dict)
    customer_member: Dict[str, object] = Field(default_factory=dict)
    business_signals: List[AgentBusinessSignal] = Field(default_factory=list)
    requested_actions: List[AgentRequestedAction] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    need_clarification: bool = Field(False)
    clarification_question: Optional[str] = Field(None)
    evidence: List[str] = Field(default_factory=list, description="用于解释判断的原文依据")


class AgentBusinessSuggestion(BaseModel):
    action: AgentSuggestionAction = Field(..., description="建议动作")
    title: str = Field(..., description="面向用户展示的建议标题")
    reason: str = Field(..., description="建议原因，必须基于用户输入或客户上下文")
    priority: Literal["high", "medium", "low"] = Field("medium", description="建议优先级")
    requires_confirmation: bool = Field(True, description="执行前是否需要用户确认")
    missing_fields: List[str] = Field(default_factory=list, description="执行动作前仍需补充的字段")
    related_object_type: Optional[str] = Field(None, description="依赖对象类型，例如 contract/payment_plan/deployment_info")
    related_object_id: Optional[int] = Field(None, description="依赖对象 ID")
    execution_payload: Dict[str, object] = Field(default_factory=dict, description="建议执行所需的结构化参数，仍需代码校验和用户确认")
    risk_notes: List[str] = Field(default_factory=list, description="不确定性或风险提示")
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class AgentSuggestionResult(BaseModel):
    summary: str = Field(..., description="对客户当前上下文和用户输入的简要判断")
    suggestions: List[AgentBusinessSuggestion] = Field(default_factory=list, max_length=3)
    need_user_choice: bool = Field(False, description="是否需要用户选择下一步动作")
    clarification_question: Optional[str] = Field(None, description="建议生成阶段需要追问的问题")


class AgentResourceCandidateRank(BaseModel):
    resource_id: int = Field(..., ge=1, description="候选业务资源 ID")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="该资源与用户语义和目标动作的匹配置信度")
    evidence: List[str] = Field(default_factory=list, max_length=3, description="支持选择该资源的简短证据")
    risk_notes: List[str] = Field(default_factory=list, max_length=3, description="仍然不确定的点")


class AgentResourceResolutionResult(BaseModel):
    rankings: List[AgentResourceCandidateRank] = Field(default_factory=list, max_length=5)
    reason: str = Field("", description="整体判断依据")


class AgentMemorySnapshot(BaseModel):
    recent_messages: List[Dict[str, object]] = Field(default_factory=list)
    pending_task: Optional[Dict[str, object]] = None
    session_context: Dict[str, object] = Field(default_factory=dict)


class AgentPendingInterruptionDecision(BaseModel):
    decision: AgentPendingInterruptionDecisionType = Field(
        "CONTINUE_PENDING",
        description="用户本轮输入与当前挂起任务的关系",
    )
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    detected_customer_name: Optional[str] = Field(None, description="本轮明确提到的新客户名称")
    detected_intent: Optional[AgentIntent] = Field(None, description="本轮输入的业务意图")
    is_field_supplement: bool = Field(False, description="是否明显是在补充当前挂起任务缺失字段")
    reason: str = Field("", description="简短判断依据")
    question: Optional[str] = Field(None, description="需要用户确认时的问题")


class AgentTurnRelationDecision(BaseModel):
    relation: AgentTurnRelationDecisionType = Field(
        "START_NEW_FLOW",
        description="用户本轮输入与会话业务状态的关系",
    )
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    target_task_id: Optional[int] = Field(None, description="应继续、修改或恢复的任务 ID；无法确定则为 null")
    detected_customer_name: Optional[str] = Field(None, description="本轮明确提到的客户名称；没有则为 null")
    detected_intent: Optional[AgentIntent] = Field(None, description="本轮输入的业务意图；无法判断则为 null")
    reason: str = Field("", description="一句话说明判断依据")
    question: Optional[str] = Field(None, description="需要用户确认时的问题")


class AgentConfirmationIntentDecision(BaseModel):
    intent: AgentConfirmationIntentType = Field("unknown", description="用户是否确认或拒绝当前待确认动作")
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    reason: str = Field("", description="简短判断依据")


class AgentHITLPolicy(BaseModel):
    allowed_decisions: List[AgentHITLDecisionType] = Field(
        default_factory=lambda: ["approve", "edit", "reject", "respond"],
    )
    required_for_tools: List[str] = Field(default_factory=list)
    confirmation_summary: Optional[str] = None


class AgentHITLDecision(BaseModel):
    decision: AgentHITLDecisionType
    task_id: Optional[int] = None
    edited_payload: Optional[Dict[str, object]] = None
    user_message: Optional[str] = None

"""Tool registry for CRM AI Agent."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

try:
    from langchain_core.tools import StructuredTool
except Exception:  # pragma: no cover - keeps imports resilient in stripped test envs
    StructuredTool = None  # type: ignore[assignment]

from app.services.agent.guardrails import AgentToolExecutionPolicy, AgentToolGuardrails, agent_tool_guardrails
from app.services.agent.tools import CRMAgentToolService
from app.services.agent.tools.base import AgentToolContext, AgentToolResult
from app.services.follow_up_task_query_intent import normalize_follow_up_task_retrieval_mode


class AgentStrictPayload(BaseModel):
    """Strict payload boundary for model-authored write objects."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


CustomerIdentifier = Union[str, int]
LeadIdentifier = Union[str, int]


class AgentLeadCreatePayload(AgentStrictPayload):
    lead_name: str = Field(..., min_length=1, max_length=255)
    source: str = Field("其他", min_length=1, max_length=100)
    city: str = Field(..., min_length=1, max_length=100)
    contact_name: str = Field(..., min_length=1, max_length=100)
    contact_phone: str = Field(..., min_length=1, max_length=20)
    company_scale: Optional[str] = Field(None, max_length=50)


class AgentContactPayload(AgentStrictPayload):
    name: str = Field(..., min_length=1, max_length=100)
    gender: Literal["0", "1", "2"] = "0"
    position: str = Field(..., min_length=1, max_length=100)
    is_decision_maker: bool = False
    mobile: str = Field(..., min_length=1, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    wechat_id: Optional[str] = Field(None, max_length=100)
    remark: Optional[str] = None
    reports_to: Optional[int] = Field(None, ge=1)


class AgentCustomerCreatePayload(AgentStrictPayload):
    account_name: str = Field(..., min_length=1, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    city: str = Field(..., min_length=1, max_length=100)
    address: Optional[str] = Field(None, max_length=500)
    company_scale: Optional[str] = Field(None, max_length=50)
    source: Optional[str] = Field(None, max_length=100)
    default_procurement_method_id: Optional[int] = Field(None, ge=1)
    primary_contact: Optional[AgentContactPayload] = None


class AgentInvoiceTitlePayload(AgentStrictPayload):
    title_type: Literal["COMPANY", "PERSONAL"]
    title: str = Field(..., min_length=1, max_length=255)
    taxpayer_id: str = Field(..., min_length=1, max_length=100)
    bank_name: Optional[str] = Field(None, max_length=255)
    bank_account: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=50)


class AgentDeploymentInfoPayload(AgentStrictPayload):
    customer_id: CustomerIdentifier = Field(..., description="客户对外ID；兼容历史任务中的数据库ID")
    deployment_name: str = Field(..., min_length=1, max_length=100)
    server_address: str = Field(..., min_length=1, max_length=500)
    authorized_users: Optional[int] = Field(None, gt=0)
    is_default: bool = False


class AgentCustomerMemberPayload(AgentStrictPayload):
    user_id: str = Field(..., min_length=1)
    member_role: Literal["SALES", "PRESALES", "DELIVERY", "SUPPORT", "OTHER"] = "PRESALES"
    access_level: Literal["VIEW", "FOLLOW_UP", "EDIT"] = "VIEW"
    remark: Optional[str] = Field(None, max_length=500)


class AgentOpportunityPayload(AgentStrictPayload):
    customer_id: CustomerIdentifier = Field(..., description="客户对外ID；兼容历史任务中的数据库ID")
    total_amount: float = Field(..., gt=0)
    user_count: int = Field(..., gt=0)
    license_type: Literal["SUBSCRIPTION", "PERPETUAL"]
    subscription_years: Optional[int] = Field(None, gt=0)
    purchase_type: Literal["NEW", "RENEWAL", "EXPANSION"]
    decision_maker_count: Optional[int] = Field(None, ge=1)
    expected_closing_date: str = Field(..., min_length=10, max_length=10)
    procurement_method_id: Optional[int] = Field(None, ge=1)

    @model_validator(mode="after")
    def validate_subscription_years(self) -> "AgentOpportunityPayload":
        if self.license_type == "SUBSCRIPTION" and not self.subscription_years:
            raise ValueError("订阅制商机必须提供 subscription_years")
        return self


def _dump_payload(payload: BaseModel) -> Dict[str, object]:
    return payload.model_dump(exclude_none=True)


class SearchCustomersInput(BaseModel):
    keyword: str = Field(..., min_length=1)
    limit: int = Field(10, ge=1, le=20)


class SearchCreationDuplicatesInput(BaseModel):
    customer_keywords: List[str] = Field(default_factory=list)
    lead_keywords: List[str] = Field(default_factory=list)
    phone: Optional[str] = None
    limit: int = Field(10, ge=1, le=20)


class GetCustomerContextInput(BaseModel):
    customer_id: CustomerIdentifier = Field(..., description="客户对外ID；兼容历史任务中的数据库ID")
    query_text: Optional[str] = None


class ListFollowUpTasksInput(BaseModel):
    status: Literal["open", "completed", "cancelled", "all"] = "open"
    due_window: Optional[Literal["today", "this_week", "next_week", "overdue"]] = None
    customer_id: Optional[CustomerIdentifier] = Field(None, description="客户对外ID；兼容历史任务中的数据库ID")
    owner_scope: Literal["mine", "customer"] = "mine"
    query_text: Optional[str] = Field(None, min_length=1, description="可选语义条件，例如预算、试用反馈、合同卡点")
    retrieval_mode: Optional[Literal["structured", "semantic_filter"]] = Field(
        None,
        description="任务检索模式；structured 只查结构化任务表，semantic_filter 先用向量证据缩窄候选再查任务事实源",
    )
    limit: int = Field(50, ge=1, le=100)

    @model_validator(mode="after")
    def normalize_retrieval_mode(self) -> "ListFollowUpTasksInput":
        self.retrieval_mode = normalize_follow_up_task_retrieval_mode(self.retrieval_mode, self.query_text)
        return self


class GetFollowUpTaskDetailInput(BaseModel):
    task_id: str = Field(..., min_length=1)


class ListCompletedWorkInput(BaseModel):
    window: Literal["today", "this_week", "last_week", "this_month", "custom"] = "this_week"
    customer_id: Optional[CustomerIdentifier] = Field(None, description="客户对外ID；兼容历史任务中的数据库ID")
    include_tasks: bool = True
    include_activities: bool = True
    include_business_events: bool = True
    start_at: Optional[str] = Field(
        None,
        description="custom 窗口开始时间，ISO 日期或日期时间；日期按当天 00:00 处理",
    )
    end_at: Optional[str] = Field(
        None,
        description="custom 窗口结束时间，ISO 日期或日期时间；日期按包含当天处理",
    )
    cursor: Optional[str] = Field(None, min_length=1, description="上一页返回的 next_cursor")
    limit: int = Field(50, ge=1, le=100)


class SummarizeCompletedWorkInput(ListCompletedWorkInput):
    question: Optional[str] = Field(None, max_length=200, description="用户原始问题，例如 本周我完成了什么")


class ListFollowUpTaskConfirmationCasesInput(BaseModel):
    limit: int = Field(20, ge=1, le=50)


class ResolveFollowUpTaskConfirmationCaseInput(BaseModel):
    case_id: str = Field(..., min_length=1, description="跟进任务确认Case对外ID（fuc_...）")
    reply_text: str = Field(..., min_length=1, description="用户对确认问题的自然语言回复")
    idempotency_suffix: Optional[str] = None


class TransitionFollowUpTaskInput(BaseModel):
    task_id: str = Field(..., min_length=1, pattern=r"^fut_[A-Za-z0-9]+$", description="跟进任务对外ID（fut_...）")
    action: Literal["complete", "cancel", "delay", "keep_open"]
    proposed_due_at: Optional[str] = Field(None, description="延期到的新时间，ISO 日期时间")
    reason: Optional[str] = Field(None, max_length=500)
    idempotency_suffix: Optional[str] = None

    @model_validator(mode="after")
    def validate_delay_due_at(self) -> "TransitionFollowUpTaskInput":
        if self.action == "delay" and not self.proposed_due_at:
            raise ValueError("延期任务必须提供 proposed_due_at")
        return self


class CreateCustomerActivityInput(BaseModel):
    customer_id: CustomerIdentifier = Field(..., description="客户对外ID；兼容历史任务中的数据库ID")
    customer_name: Optional[str] = None
    activity_kind: str = "OTHER_FOLLOW_UP"
    source_content: str = Field(..., min_length=1)
    title: Optional[str] = None
    next_action: Optional[str] = None
    next_follow_time: Optional[str] = None
    idempotency_suffix: Optional[str] = None


class CreateLeadInput(BaseModel):
    lead: AgentLeadCreatePayload
    idempotency_suffix: Optional[str] = None


class CreateCustomerInput(BaseModel):
    customer: AgentCustomerCreatePayload
    idempotency_suffix: Optional[str] = None


class CreateLeadFollowUpInput(BaseModel):
    lead_id: LeadIdentifier = Field(..., description="线索对外ID；兼容历史任务中的数据库ID")
    content: str = Field(..., min_length=1)
    method: str = "其他"
    next_action: Optional[str] = None
    next_follow_time: Optional[str] = None
    idempotency_suffix: Optional[str] = None


class CreateContactInput(BaseModel):
    customer_id: CustomerIdentifier = Field(..., description="客户对外ID；兼容历史任务中的数据库ID")
    contact: AgentContactPayload
    idempotency_suffix: Optional[str] = None


class CreateInvoiceTitleInput(BaseModel):
    customer_id: CustomerIdentifier = Field(..., description="客户对外ID；兼容历史任务中的数据库ID")
    invoice_title: AgentInvoiceTitlePayload
    set_default: bool = False
    idempotency_suffix: Optional[str] = None


class CreateDeploymentInfoInput(BaseModel):
    deployment_info: AgentDeploymentInfoPayload
    idempotency_suffix: Optional[str] = None


class CreateCustomerMemberInput(BaseModel):
    customer_id: CustomerIdentifier = Field(..., description="客户对外ID；兼容历史任务中的数据库ID")
    member: AgentCustomerMemberPayload
    idempotency_suffix: Optional[str] = None


class CreateOpportunityInput(BaseModel):
    opportunity: AgentOpportunityPayload
    idempotency_suffix: Optional[str] = None


class ListCustomerOpportunitiesInput(BaseModel):
    customer_id: CustomerIdentifier = Field(..., description="客户对外ID；兼容历史任务中的数据库ID")
    status: Optional[str] = None
    limit: int = Field(20, ge=1, le=100)


class GetOpportunityDetailInput(BaseModel):
    opportunity_id: Union[str, int] = Field(..., description="商机对外ID（opp_...）；兼容内部任务中的数据库ID")


class GetOpportunityProcurementStagesInput(BaseModel):
    opportunity_id: Union[str, int] = Field(..., description="商机对外ID（opp_...）；兼容内部任务中的数据库ID")


class MoveOpportunityStageInput(BaseModel):
    opportunity_id: Union[str, int] = Field(..., description="商机对外ID（opp_...）；兼容内部任务中的数据库ID")
    stage_template_id: int = Field(..., ge=1)
    idempotency_suffix: Optional[str] = None


class CreatePaymentPlanInput(BaseModel):
    contract_id: int = Field(..., ge=1)
    stage_name: str = Field(..., min_length=1, max_length=100)
    planned_amount: float = Field(..., gt=0)
    due_date: str = Field(..., min_length=10, max_length=10)
    notes: Optional[str] = None
    idempotency_suffix: Optional[str] = None


class CreatePaymentRecordInput(BaseModel):
    payment_plan_id: int = Field(..., ge=1)
    actual_amount: float = Field(..., gt=0)
    payment_date: str = Field(..., min_length=10, max_length=10)
    commission_member_id: str = Field(..., min_length=1, max_length=100)
    actual_payer_name: Optional[str] = None
    proof_attachment: Optional[str] = None
    notes: Optional[str] = None
    idempotency_suffix: Optional[str] = None


@dataclass(frozen=True)
class AgentToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    is_write: bool
    requires_confirmation: bool
    runner: Callable[[CRMAgentToolService, AgentToolContext, BaseModel], Awaitable[AgentToolResult]]
    user_reply_confirms: bool = False


class AgentToolRegistry:
    """Central allowlist for Agent tools.

    The registry makes the callable surface explicit. It does not grant
    permissions; each tool still calls existing CRM APIs with the current user
    authorization header.
    """

    def __init__(
        self,
        tool_service: Optional[CRMAgentToolService] = None,
        guardrails: Optional[AgentToolGuardrails] = None,
    ) -> None:
        self.tool_service = tool_service or CRMAgentToolService()
        self.guardrails = guardrails or agent_tool_guardrails
        self._tools = self._build_tools()

    def get(self, name: str) -> AgentToolSpec:
        if name not in self._tools:
            raise KeyError(f"未注册的 Agent tool：{name}")
        return self._tools[name]

    def list_specs(self) -> Dict[str, AgentToolSpec]:
        return dict(self._tools)

    def to_langchain_tools(
        self,
        context: AgentToolContext,
        *,
        allowed_tool_names: Optional[List[str]] = None,
        include_write_tools: bool = True,
    ):
        """Expose selected registry tools as LangChain StructuredTool objects."""
        if StructuredTool is None:
            return []

        allowed = set(allowed_tool_names or [])
        tools = []
        for spec in self._tools.values():
            if allowed and spec.name not in allowed:
                continue
            if spec.is_write and not include_write_tools:
                continue

            async def _coroutine(_spec=spec, **kwargs):
                result = await self.execute(_spec.name, context, kwargs)
                return result.to_event()

            tools.append(StructuredTool.from_function(
                coroutine=_coroutine,
                name=spec.name,
                description=spec.description,
                args_schema=spec.input_model,
            ))
        return tools

    def to_readonly_langchain_tools(
        self,
        context: AgentToolContext,
        *,
        allowed_tool_names: Optional[List[str]] = None,
    ):
        """Expose read-only tools for controlled LangChain sub-agents."""
        return self.to_langchain_tools(
            context,
            allowed_tool_names=allowed_tool_names,
            include_write_tools=False,
        )

    async def execute(
        self,
        name: str,
        context: AgentToolContext,
        payload: Dict[str, object],
        *,
        policy: Optional[AgentToolExecutionPolicy] = None,
    ) -> AgentToolResult:
        spec = self.get(name)
        model = spec.input_model.model_validate(payload)
        normalized_payload = model.model_dump(exclude_none=True)
        self.guardrails.validate_before_execute(
            tool_name=name,
            is_write=spec.is_write,
            requires_confirmation=spec.requires_confirmation,
            user_reply_confirms=spec.user_reply_confirms,
            context=context,
            payload=normalized_payload,
            policy=policy,
        )
        return await spec.runner(self.tool_service, context, model)

    def _build_tools(self) -> Dict[str, AgentToolSpec]:
        async def search_customers(service, context, model):
            return await service.search_customers(context, model.keyword, limit=model.limit)

        async def search_creation_duplicates(service, context, model):
            return await service.search_creation_duplicates(
                context,
                customer_keywords=model.customer_keywords,
                lead_keywords=model.lead_keywords,
                phone=model.phone,
                limit=model.limit,
            )

        async def get_customer_context(service, context, model):
            return await service.get_customer_context(context, model.customer_id, query_text=model.query_text)

        async def list_follow_up_tasks(service, context, model):
            return await service.list_follow_up_tasks(
                context,
                status=model.status,
                due_window=model.due_window,
                customer_id=model.customer_id,
                owner_scope=model.owner_scope,
                query_text=model.query_text,
                retrieval_mode=model.retrieval_mode,
                limit=model.limit,
            )

        async def get_follow_up_task_detail(service, context, model):
            return await service.get_follow_up_task_detail(context, task_id=model.task_id)

        async def list_completed_work(service, context, model):
            return await service.list_completed_work(
                context,
                window=model.window,
                customer_id=model.customer_id,
                include_tasks=model.include_tasks,
                include_activities=model.include_activities,
                include_business_events=model.include_business_events,
                start_at=model.start_at,
                end_at=model.end_at,
                cursor=model.cursor,
                limit=model.limit,
            )

        async def summarize_completed_work(service, context, model):
            return await service.summarize_completed_work(
                context,
                window=model.window,
                customer_id=model.customer_id,
                include_tasks=model.include_tasks,
                include_activities=model.include_activities,
                include_business_events=model.include_business_events,
                start_at=model.start_at,
                end_at=model.end_at,
                cursor=model.cursor,
                limit=model.limit,
                question=model.question,
            )

        async def list_follow_up_task_confirmation_cases(service, context, model):
            return await service.list_follow_up_task_confirmation_cases(context, limit=model.limit)

        async def resolve_follow_up_task_confirmation_case(service, context, model):
            return await service.resolve_follow_up_task_confirmation_case(
                context,
                case_id=model.case_id,
                reply_text=model.reply_text,
                idempotency_suffix=model.idempotency_suffix,
            )

        async def transition_follow_up_task(service, context, model):
            return await service.transition_follow_up_task(
                context,
                task_id=model.task_id,
                action=model.action,
                proposed_due_at=model.proposed_due_at,
                reason=model.reason,
                idempotency_suffix=model.idempotency_suffix,
            )

        async def create_customer_activity(service, context, model):
            return await service.create_customer_activity(
                context,
                customer_id=model.customer_id,
                customer_name=model.customer_name,
                activity_kind=model.activity_kind,
                source_content=model.source_content,
                title=model.title,
                next_action=model.next_action,
                next_follow_time=model.next_follow_time,
                idempotency_suffix=model.idempotency_suffix,
            )

        async def create_lead(service, context, model):
            return await service.create_lead(
                context,
                lead=_dump_payload(model.lead),
                idempotency_suffix=model.idempotency_suffix,
            )

        async def create_customer(service, context, model):
            return await service.create_customer(
                context,
                customer=_dump_payload(model.customer),
                idempotency_suffix=model.idempotency_suffix,
            )

        async def create_lead_follow_up(service, context, model):
            return await service.create_lead_follow_up(
                context,
                lead_id=model.lead_id,
                content=model.content,
                method=model.method,
                next_action=model.next_action,
                next_follow_time=model.next_follow_time,
                idempotency_suffix=model.idempotency_suffix,
            )

        async def create_contact(service, context, model):
            return await service.create_contact(
                context,
                customer_id=model.customer_id,
                contact=_dump_payload(model.contact),
                idempotency_suffix=model.idempotency_suffix,
            )

        async def create_invoice_title(service, context, model):
            return await service.create_invoice_title(
                context,
                customer_id=model.customer_id,
                invoice_title=_dump_payload(model.invoice_title),
                set_default=model.set_default,
                idempotency_suffix=model.idempotency_suffix,
            )

        async def create_deployment_info(service, context, model):
            return await service.create_deployment_info(
                context,
                deployment_info=_dump_payload(model.deployment_info),
                idempotency_suffix=model.idempotency_suffix,
            )

        async def create_customer_member(service, context, model):
            return await service.create_customer_member(
                context,
                customer_id=model.customer_id,
                member=_dump_payload(model.member),
                idempotency_suffix=model.idempotency_suffix,
            )

        async def create_opportunity(service, context, model):
            return await service.create_opportunity(
                context,
                opportunity=_dump_payload(model.opportunity),
                idempotency_suffix=model.idempotency_suffix,
            )

        async def list_customer_opportunities(service, context, model):
            return await service.list_customer_opportunities(
                context,
                customer_id=model.customer_id,
                status=model.status,
                limit=model.limit,
            )

        async def get_opportunity_detail(service, context, model):
            return await service.get_opportunity_detail(
                context,
                opportunity_id=model.opportunity_id,
            )

        async def get_opportunity_procurement_stages(service, context, model):
            return await service.get_opportunity_procurement_stages(
                context,
                opportunity_id=model.opportunity_id,
            )

        async def move_opportunity_stage(service, context, model):
            return await service.move_opportunity_stage(
                context,
                opportunity_id=model.opportunity_id,
                stage_template_id=model.stage_template_id,
                idempotency_suffix=model.idempotency_suffix,
            )

        async def create_payment_plan(service, context, model):
            return await service.create_payment_plan(
                context,
                contract_id=model.contract_id,
                stage_name=model.stage_name,
                planned_amount=model.planned_amount,
                due_date=model.due_date,
                notes=model.notes,
                idempotency_suffix=model.idempotency_suffix,
            )

        async def create_payment_record(service, context, model):
            return await service.create_payment_record(
                context,
                payment_plan_id=model.payment_plan_id,
                actual_amount=model.actual_amount,
                payment_date=model.payment_date,
                commission_member_id=model.commission_member_id,
                actual_payer_name=model.actual_payer_name,
                proof_attachment=model.proof_attachment,
                notes=model.notes,
                idempotency_suffix=model.idempotency_suffix,
            )

        specs = [
            AgentToolSpec(
                "search_customers",
                "按当前用户权限混合检索客户；支持客户名称、简称、别称、跟进记录和客户知识库语义证据",
                SearchCustomersInput,
                False,
                False,
                search_customers,
            ),
            AgentToolSpec("search_creation_duplicates", "创建客户/线索前按团队范围检查重复", SearchCreationDuplicatesInput, False, False, search_creation_duplicates),
            AgentToolSpec("get_customer_context", "获取客户业务上下文", GetCustomerContextInput, False, False, get_customer_context),
            AgentToolSpec(
                "list_follow_up_tasks",
                "查询当前用户或指定客户范围内的跟进任务事实源；retrieval_mode=structured 用于列举任务，retrieval_mode=semantic_filter 用于预算、试用反馈、合同卡点等主题查询；任务状态仍以结构化表为准",
                ListFollowUpTasksInput,
                False,
                False,
                list_follow_up_tasks,
            ),
            AgentToolSpec("get_follow_up_task_detail", "按任务对外ID获取跟进任务详情和来源活动摘要", GetFollowUpTaskDetailInput, False, False, get_follow_up_task_detail),
            AgentToolSpec(
                "list_completed_work",
                "按时间窗口查询当前用户的结构化工作事实，覆盖已完成任务、客户活动和业务推进事件",
                ListCompletedWorkInput,
                False,
                False,
                list_completed_work,
            ),
            AgentToolSpec(
                "summarize_completed_work",
                "基于结构化工作事实生成带 fact_id 引用的工作总结；用于回答周报、月报、本周完成了什么",
                SummarizeCompletedWorkInput,
                False,
                False,
                summarize_completed_work,
            ),
            AgentToolSpec(
                "list_follow_up_task_confirmation_cases",
                "查询当前用户待确认的跟进任务处理Case",
                ListFollowUpTaskConfirmationCasesInput,
                False,
                False,
                list_follow_up_task_confirmation_cases,
            ),
            AgentToolSpec(
                "resolve_follow_up_task_confirmation_case",
                "应用用户对跟进任务确认Case的自然语言回复；只接受Case对外ID",
                ResolveFollowUpTaskConfirmationCaseInput,
                True,
                False,
                resolve_follow_up_task_confirmation_case,
                True,
            ),
            AgentToolSpec(
                "transition_follow_up_task",
                "按已确认的用户意图更新跟进任务状态；只接受跟进任务对外ID fut_...",
                TransitionFollowUpTaskInput,
                True,
                True,
                transition_follow_up_task,
            ),
            AgentToolSpec("create_customer_activity", "创建客户活动记录", CreateCustomerActivityInput, True, True, create_customer_activity),
            AgentToolSpec("create_lead", "通过现有线索 API 创建线索", CreateLeadInput, True, True, create_lead),
            AgentToolSpec("create_customer", "通过现有客户 API 创建客户", CreateCustomerInput, True, True, create_customer),
            AgentToolSpec("create_lead_follow_up", "通过现有线索 API 创建线索跟进记录", CreateLeadFollowUpInput, True, True, create_lead_follow_up),
            AgentToolSpec("create_contact", "创建客户联系人", CreateContactInput, True, True, create_contact),
            AgentToolSpec("create_invoice_title", "创建发票抬头", CreateInvoiceTitleInput, True, True, create_invoice_title),
            AgentToolSpec("create_deployment_info", "创建部署信息", CreateDeploymentInfoInput, True, True, create_deployment_info),
            AgentToolSpec("create_customer_member", "添加客户团队成员", CreateCustomerMemberInput, True, True, create_customer_member),
            AgentToolSpec("create_opportunity", "创建客户商机", CreateOpportunityInput, True, True, create_opportunity),
            AgentToolSpec("list_customer_opportunities", "按当前用户权限查询客户商机列表", ListCustomerOpportunitiesInput, False, False, list_customer_opportunities),
            AgentToolSpec("get_opportunity_detail", "按当前用户权限获取商机详情", GetOpportunityDetailInput, False, False, get_opportunity_detail),
            AgentToolSpec("get_opportunity_procurement_stages", "获取商机采购方式对应的动态阶段列表", GetOpportunityProcurementStagesInput, False, False, get_opportunity_procurement_stages),
            AgentToolSpec("move_opportunity_stage", "按用户确认推进商机到指定采购阶段", MoveOpportunityStageInput, True, True, move_opportunity_stage),
            AgentToolSpec("create_payment_plan", "基于已确认合同创建回款计划", CreatePaymentPlanInput, True, True, create_payment_plan),
            AgentToolSpec("create_payment_record", "基于已确认回款计划登记回款", CreatePaymentRecordInput, True, True, create_payment_record),
        ]
        return {spec.name: spec for spec in specs}


agent_tool_registry = AgentToolRegistry()

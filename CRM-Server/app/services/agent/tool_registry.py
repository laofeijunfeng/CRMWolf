"""Tool registry for CRM AI Agent."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from pydantic import BaseModel, Field

try:
    from langchain_core.tools import StructuredTool
except Exception:  # pragma: no cover - keeps imports resilient in stripped test envs
    StructuredTool = None  # type: ignore[assignment]

from app.services.agent.guardrails import AgentToolExecutionPolicy, AgentToolGuardrails, agent_tool_guardrails
from app.services.agent.tools import CRMAgentToolService
from app.services.agent.tools.base import AgentToolContext, AgentToolResult


class SearchCustomersInput(BaseModel):
    keyword: str = Field(..., min_length=1)
    limit: int = Field(10, ge=1, le=20)


class GetCustomerContextInput(BaseModel):
    customer_id: int = Field(..., ge=1)


class CreateCustomerFollowUpInput(BaseModel):
    customer_id: int = Field(..., ge=1)
    customer_name: Optional[str] = None
    content: str = Field(..., min_length=1)
    method: str = "AI录入"
    next_action: Optional[str] = None
    next_follow_time: Optional[str] = None
    idempotency_suffix: Optional[str] = None


class CreateContactInput(BaseModel):
    customer_id: int = Field(..., ge=1)
    contact: Dict[str, Any]


class CreateInvoiceTitleInput(BaseModel):
    customer_id: int = Field(..., ge=1)
    invoice_title: Dict[str, Any]
    set_default: bool = False


class CreateDeploymentInfoInput(BaseModel):
    deployment_info: Dict[str, Any]


@dataclass(frozen=True)
class AgentToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    is_write: bool
    requires_confirmation: bool
    runner: Callable[[CRMAgentToolService, AgentToolContext, BaseModel], Awaitable[AgentToolResult]]


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

    def to_langchain_tools(self, context: AgentToolContext):
        """Expose the allowlisted tools as LangChain StructuredTool objects."""
        if StructuredTool is None:
            return []

        tools = []
        for spec in self._tools.values():
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

    async def execute(
        self,
        name: str,
        context: AgentToolContext,
        payload: Dict[str, Any],
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
            context=context,
            payload=normalized_payload,
            policy=policy,
        )
        return await spec.runner(self.tool_service, context, model)

    def _build_tools(self) -> Dict[str, AgentToolSpec]:
        async def search_customers(service, context, model):
            return await service.search_customers(context, model.keyword, limit=model.limit)

        async def get_customer_context(service, context, model):
            return await service.get_customer_context(context, model.customer_id)

        async def create_customer_follow_up(service, context, model):
            return await service.create_customer_follow_up(
                context,
                customer_id=model.customer_id,
                customer_name=model.customer_name,
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
                contact=model.contact,
            )

        async def create_invoice_title(service, context, model):
            return await service.create_invoice_title(
                context,
                customer_id=model.customer_id,
                invoice_title=model.invoice_title,
                set_default=model.set_default,
            )

        async def create_deployment_info(service, context, model):
            return await service.create_deployment_info(
                context,
                deployment_info=model.deployment_info,
            )

        specs = [
            AgentToolSpec("search_customers", "按当前用户权限搜索可访问客户", SearchCustomersInput, False, False, search_customers),
            AgentToolSpec("get_customer_context", "获取客户业务上下文", GetCustomerContextInput, False, False, get_customer_context),
            AgentToolSpec("create_customer_follow_up", "创建客户跟进记录", CreateCustomerFollowUpInput, True, True, create_customer_follow_up),
            AgentToolSpec("create_contact", "创建客户联系人", CreateContactInput, True, True, create_contact),
            AgentToolSpec("create_invoice_title", "创建发票抬头", CreateInvoiceTitleInput, True, True, create_invoice_title),
            AgentToolSpec("create_deployment_info", "创建部署信息", CreateDeploymentInfoInput, True, True, create_deployment_info),
        ]
        return {spec.name: spec for spec in specs}


agent_tool_registry = AgentToolRegistry()

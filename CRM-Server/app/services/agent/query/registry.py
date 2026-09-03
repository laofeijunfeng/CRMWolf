"""Closed read-only tool surface exposed to the CRM Query Agent."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, Self, TypeAlias, cast

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, model_validator

from app.services.agent.query.catalog import CRMQueryCatalog, CRMQueryResourceDefinition
from app.services.agent.query.schemas import (
    CRMQueryResult,
    CRMQuerySpec,
    CRMResource,
    EntityRef,
    JsonDict,
    QueryContractModel,
)
from app.services.agent.tools.base import AgentToolContext

if TYPE_CHECKING:
    from app.services.agent.query.executor import CRMQueryExecutor

CustomerContextSection: TypeAlias = Literal[
    "profile",
    "contacts",
    "opportunities",
    "contracts",
    "payments",
    "activities",
    "evidence",
]


class CustomerContextRequest(QueryContractModel):
    """Permission-safe request for structured facts and customer intelligence evidence."""

    customer_ref: EntityRef
    sections: list[CustomerContextSection] = Field(min_length=1, max_length=8)
    question: str | None = Field(default=None, min_length=1, max_length=2000)
    evidence_limit: int = Field(default=6, ge=1, le=20)

    @model_validator(mode="after")
    def validate_customer_ref_and_sections(self) -> Self:
        if self.customer_ref.resource != "customer":
            raise ValueError("customer_ref must reference a customer")
        if len(set(self.sections)) != len(self.sections):
            raise ValueError("customer context sections must be unique")
        return self


class FollowUpTaskDetailRequest(QueryContractModel):
    """A detail lookup bound to a server-issued follow-up task reference."""

    task_ref: EntityRef

    @model_validator(mode="after")
    def validate_task_ref(self) -> Self:
        if self.task_ref.resource != "follow_up_task":
            raise ValueError("task_ref must reference a follow-up task")
        return self


class FollowUpTaskDetailReader(Protocol):
    async def read(
        self,
        request: FollowUpTaskDetailRequest,
        context: AgentToolContext,
    ) -> CRMQueryResult: ...


class CustomerContextCitation(QueryContractModel):
    """One evidence reference returned by Customer Intelligence."""

    citation_id: str = Field(min_length=1, max_length=128)
    source: Literal["CRM_API", "CUSTOMER_INTELLIGENCE", "QDRANT"]
    source_ref: str = Field(min_length=1, max_length=512)
    label: str = Field(min_length=1, max_length=200)


class CustomerContextCoverage(QueryContractModel):
    """Explicitly state which requested context sections were available."""

    requested: list[CustomerContextSection] = Field(min_length=1, max_length=8)
    returned: list[CustomerContextSection] = Field(default_factory=list, max_length=8)
    unavailable: list[CustomerContextSection] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_partition(self) -> Self:
        requested = set(self.requested)
        returned = set(self.returned)
        unavailable = set(self.unavailable)
        if returned & unavailable:
            raise ValueError("returned and unavailable coverage must not overlap")
        if returned | unavailable != requested:
            raise ValueError("coverage must account for every requested section")
        return self


class CustomerContextResult(QueryContractModel):
    """Normalized customer context without internal database identifiers."""

    customer_ref: EntityRef
    sections: JsonDict = Field(default_factory=dict)
    citations: list[CustomerContextCitation] = Field(default_factory=list, max_length=20)
    coverage: CustomerContextCoverage
    degraded_reasons: list[str] = Field(default_factory=list, max_length=10)


class CustomerContextReader(Protocol):
    async def read(
        self,
        request: CustomerContextRequest,
        context: AgentToolContext,
    ) -> CustomerContextResult: ...


CRMReadToolResult: TypeAlias = CRMQueryResult | CustomerContextResult
CRMReadToolRunner: TypeAlias = Callable[[AgentToolContext, BaseModel], Awaitable[CRMReadToolResult]]


@dataclass(frozen=True)
class CRMReadToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    is_write: Literal[False]
    resource: CRMResource | None
    runner: CRMReadToolRunner
    authority_kind: Literal["query", "customer_context", "task_detail"] = "query"


class CRMReadToolInputError(ValueError):
    """A model-supplied read-tool payload violates the registered tool contract."""


class CRMReadToolRegistry:
    """Query-only registry with no CRUD, SQL, arbitrary URL, or write-tool dependency."""

    def __init__(
        self,
        executor: CRMQueryExecutor,
        customer_context_reader: CustomerContextReader,
        follow_up_task_detail_reader: FollowUpTaskDetailReader | None = None,
    ) -> None:
        self._executor = executor
        self._customer_context_reader = customer_context_reader
        self._follow_up_task_detail_reader = follow_up_task_detail_reader
        self._catalog = CRMQueryCatalog()
        self._tools = self._build_tools()
        if self.write_tool_count != 0:
            raise RuntimeError("CRMReadToolRegistry must not expose write tools")

    @property
    def write_tool_count(self) -> int:
        return sum(1 for spec in self._tools.values() if spec.is_write)

    def list_specs(self) -> dict[str, CRMReadToolSpec]:
        return dict(self._tools)

    def get(self, name: str) -> CRMReadToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"unregistered CRM read tool: {name}") from exc

    async def execute(
        self,
        name: str,
        context: AgentToolContext,
        payload: dict[str, object],
    ) -> CRMReadToolResult:
        spec = self.get(name)
        model = spec.input_model.model_validate(payload)
        return await spec.runner(context, model)

    def to_langchain_tools(self, context: AgentToolContext) -> list[StructuredTool]:
        tools: list[StructuredTool] = []
        for spec in self._tools.values():

            async def _coroutine(_spec: CRMReadToolSpec = spec, **kwargs: object) -> JsonDict:
                result = await self.execute(_spec.name, context, kwargs)
                return cast("JsonDict", result.model_dump(mode="json"))

            tools.append(
                StructuredTool.from_function(
                    coroutine=_coroutine,
                    name=spec.name,
                    description=spec.description,
                    args_schema=spec.input_model,
                )
            )
        return tools

    def _build_tools(self) -> dict[str, CRMReadToolSpec]:
        resources: tuple[tuple[str, CRMResource, str], ...] = (
            (
                "query_customers",
                "customer",
                (
                    "查询权限范围内的客户列表。客户 status 仅表示 0=跟进中、1=已成交、"
                    "2=已输单、3=已沉寂，不表示客户重要程度；“重点客户”没有内置字段或默认判断标准。"  # noqa: RUF001
                ),
            ),
            ("query_customer_contacts", "contact", "查询单个客户的联系人。"),
            (
                "query_customer_activities",
                "customer_activity",
                (
                    "查询单个客户的活动记录。询问最近跟进、最新进展或最近沟通时，"  # noqa: RUF001
                    "使用 customer_id 精确过滤；得到 SUCCESS、PARTIAL 或 EMPTY 后直接回答，"  # noqa: RUF001
                    "不要再查询任务或客户上下文。"
                ),
            ),
            (
                "query_customer_deployment_infos",
                "deployment_info",
                "查询单个客户的部署信息。",
            ),
            (
                "query_follow_up_tasks",
                "follow_up_task",
                "查询客户跟进任务；该工具只允许 scope=mine，不得使用 accessible。",  # noqa: RUF001
            ),
            ("query_completed_work", "completed_work", "查询当前用户已完成的工作事实。"),
        )
        tools: dict[str, CRMReadToolSpec] = {}
        for name, resource, description in resources:

            async def _query_runner(
                context: AgentToolContext,
                model: BaseModel,
                *,
                expected_resource: CRMResource = resource,
                tool_name: str = name,
            ) -> CRMQueryResult:
                query = CRMQuerySpec.model_validate(model.model_dump(mode="json"))
                if query.resource != expected_resource:
                    raise CRMReadToolInputError(
                        f"{tool_name} is bound to resource {expected_resource}, got {query.resource}"
                    )
                return await self._executor.execute(query, context)

            definition = self._catalog.resolve(resource)
            tools[name] = CRMReadToolSpec(
                name=name,
                description=_query_tool_description(description, definition),
                input_model=CRMQuerySpec,
                is_write=False,
                resource=resource,
                runner=_query_runner,
            )

        if self._follow_up_task_detail_reader is not None:

            async def _follow_up_task_detail_runner(
                context: AgentToolContext,
                model: BaseModel,
            ) -> CRMQueryResult:
                request = FollowUpTaskDetailRequest.model_validate(model.model_dump(mode="json"))
                return await self._follow_up_task_detail_reader.read(request, context)

            tools["get_follow_up_task_detail"] = CRMReadToolSpec(
                name="get_follow_up_task_detail",
                description=(
                    "读取一个已由服务端确认的跟进任务详情，包括当前状态、完成时间和取消时间。"
                    "只能使用 query_follow_up_tasks 返回或 Root 传入的 task_ref；这是只读查询，不会改变任务状态。"
                ),
                input_model=FollowUpTaskDetailRequest,
                is_write=False,
                resource=None,
                authority_kind="task_detail",
                runner=_follow_up_task_detail_runner,
            )

        async def _customer_context_runner(
            context: AgentToolContext,
            model: BaseModel,
        ) -> CustomerContextResult:
            request = CustomerContextRequest.model_validate(model.model_dump(mode="json"))
            return await self._customer_context_reader.read(request, context)

        tools["get_customer_context"] = CRMReadToolSpec(
            name="get_customer_context",
            description="读取已授权客户的结构化上下文、档案与引用证据。",
            input_model=CustomerContextRequest,
            is_write=False,
            resource=None,
            authority_kind="customer_context",
            runner=_customer_context_runner,
        )
        return tools


def _query_tool_description(
    base_description: str,
    definition: CRMQueryResourceDefinition,
) -> str:
    """Expose the catalog contract to the planner instead of making it guess field names."""

    projections = ", ".join(sorted(definition.projection_fields))
    defaults = ", ".join(definition.default_projection)
    filters = ", ".join(
        f"{field}({'/'.join(sorted(operators))})"
        for field, operators in sorted(definition.filterable_fields.items())
    )
    sorts = ", ".join(sorted(definition.sortable_fields)) or "无"
    scopes = ", ".join(sorted(definition.allowed_scopes))
    exact_filters = ", ".join(sorted(definition.required_exact_filters)) or "无"
    naming_hint = ""
    if definition.resource == "customer":
        naming_hint = (
            " 客户名称字段是 account_name，不是 name；客户标识字段是 public_id，不是 id。"  # noqa: RUF001
            "列表查询 page_size 使用 50，以一次返回本轮允许的完整结果；不要自行改成 20。"  # noqa: RUF001
            "精确名称使用 account_name eq，模糊名称使用 account_name contains 或 keyword contains。"  # noqa: RUF001
            "空结果表示当前权限范围内没有匹配项；空结果后不得放宽条件或重复查询。"  # noqa: RUF001
        )
    return (
        f"{base_description} resource 固定为 {definition.resource}。"
        f"省略 projection 时默认返回: {defaults}。"
        f"projection 仅可使用: {projections}。"
        f"filters 可使用: {filters or '无'}。"
        f"sorts 可使用: {sorts}。"
        f"scope 可使用: {scopes}；默认 scope 为 {definition.default_scope}。"  # noqa: RUF001
        f"必须提供的精确过滤字段: {exact_filters}。"
        f"{naming_hint}"
    )

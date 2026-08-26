"""Ephemeral, read-only CRM Query Agent orchestration boundary."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Sequence
from threading import RLock
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, cast

from langchain.agents import create_agent
from langchain.agents.middleware import before_model
from langchain.agents.structured_output import StructuredOutputError, ToolStrategy
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import Field, ValidationError, model_validator

from app.services.agent.query.executor import CRMQueryExecutionError
from app.services.agent.query.registry import (
    CRMReadToolInputError,
    CustomerContextResult,
)
from app.services.agent.query.schemas import (
    CRMFilter,
    CRMQueryResult,
    CRMQuerySpec,
    EntityRef,
    QueryContractModel,
    QueryError,
)

if TYPE_CHECKING:
    from app.services.agent.query.registry import (
        CRMReadToolRegistry,
        CRMReadToolResult,
        CRMReadToolSpec,
    )
    from app.services.agent.tools.base import AgentToolContext


logger = logging.getLogger(__name__)


CRMQueryAgentStatus: TypeAlias = Literal["ANSWERED", "CLARIFICATION_REQUIRED"]
CRMQueryAgentStopReason: TypeAlias = Literal["COMPLETED", "CLARIFICATION_REQUIRED"]
CRMQueryAgentToolCallStatus: TypeAlias = Literal["SUCCESS", "ERROR"]


QUERY_AGENT_SYSTEM_PROMPT = """你是 CRM Query Agent, 只负责本轮只读查询与有依据的回答。

必须遵守:
1. 只能使用本轮提供的 CRM 只读工具; 不得构造或请求任意 HTTP、URL、SQL、ORM, 也不得执行写操作。
2. 不得依据记忆猜测 CRM 业务事实。所有业务事实必须来自本轮实际工具结果。
3. 查询参数必须严格符合工具公开的 CRMQuerySpec 或 CustomerContextRequest schema。
4. QuerySpec 无效时最多修正一次; 权限、超时、上限和内部错误不得解释为空结果。
5. 回答必须在 evidence_refs 中引用本轮真实返回的 query_id、ref_id、fact_id 或 citation_id。
6. 条件不足时返回 CLARIFICATION_REQUIRED, 不要猜测, 也不要调用无关工具。
7. 不输出 Markdown 客户表格; 只返回规定的 structured output, 由 Agent UI 负责渲染。
8. CRMQueryResult 为 SUCCESS、PARTIAL 或 EMPTY 时都表示工具调用成功。EMPTY 是当前权限范围内的权威空结果，必须立即回答，不得放宽条件、缩短关键词、替换字段或重复查询。
9. PARTIAL 表示服务端已经按本轮预算返回可展示结果和 total；除非用户明确要求下一页，否则不得自动翻页。
10. 客户列表的 answer 只概括查询条件、命中数量和必要提示，不得逐条复述客户；实体列表由 Agent UI 渲染。
11. get_customer_context 只能使用 server_authoritative_entity_refs 中的客户引用，或本轮 query_customers 返回的真实 EntityRef；不得根据用户文本自行构造 EntityRef。
12. server_authoritative_entity_refs 非空时，必须直接围绕这些实体查询；不得重新查询上一轮客户列表，也不得改选其他客户。
13. 每个工具只能使用自身 schema 和说明允许的 scope；不得把一个资源的 scope 复制到另一个资源。query_follow_up_tasks 必须使用 scope=mine。
14. 客户 status 仅表示 0=跟进中、1=已成交、2=已输单、3=已沉寂，不表示客户重要程度。用户只说“重点客户”而未给出可执行判断标准时，必须直接返回 CLARIFICATION_REQUIRED，不得猜测 status 或调用工具。
15. 使用最少工具完成回答。同一工具不得重复调用，除非第一次明确返回 QUERY_INVALID 且仍有一次纠正预算，或用户明确要求下一页。
16. 用户询问已选客户“最近跟进、最新进展、最近沟通”等活动事实时，只调用一次 query_customer_activities，以 customer_id 精确过滤；SUCCESS、PARTIAL 或 EMPTY 后立即回答。不要同时调用 get_customer_context、query_follow_up_tasks 或 query_completed_work。只有用户明确询问待办/跟进任务时才调用 query_follow_up_tasks。
"""


class CRMQueryAgentLimits(QueryContractModel):
    """Hard budgets enforced by code for one ephemeral Query Agent turn."""

    max_tool_calls: int = Field(default=4, ge=1, le=20)
    max_rows_per_tool: int = Field(default=50, ge=1, le=100)
    max_total_entities: int = Field(default=100, ge=1, le=500)
    max_query_corrections: int = Field(default=1, ge=0, le=3)
    max_structured_output_corrections: int = Field(default=1, ge=0, le=3)
    tool_timeout_seconds: float = Field(default=8, gt=0, le=60)
    # A query turn may require one model call to select a tool and another
    # model call to summarize its authoritative result. Twenty seconds was
    # shorter than that round trip for the configured provider.
    turn_timeout_seconds: float = Field(default=60, gt=0, le=120)


class CRMQueryAgentModelConfig(QueryContractModel):
    """Explicit model configuration supplied by the application boundary."""

    api_host: str = Field(min_length=1, max_length=2048)
    api_key: str = Field(min_length=1, max_length=4096)
    model: str = Field(min_length=1, max_length=200)
    temperature: float = Field(ge=0, le=2)
    enable_thinking: bool | None = None


class CRMQueryAgentRequest(QueryContractModel):
    """One stateless user query plus server-authoritative entity references."""

    user_message: str = Field(min_length=1, max_length=20_000)
    previous_query: CRMQuerySpec | None = None
    entity_refs: list[EntityRef] = Field(default_factory=list, max_length=100)
    allowed_tool_names: list[str] | None = Field(default=None, min_length=1, max_length=20)

    @model_validator(mode="after")
    def require_unique_references_and_tool_names(self) -> CRMQueryAgentRequest:
        entity_keys = {(ref.resource, ref.public_id) for ref in self.entity_refs}
        if len(entity_keys) != len(self.entity_refs):
            raise ValueError("entity_refs must be unique")
        if self.allowed_tool_names is not None and len(set(self.allowed_tool_names)) != len(self.allowed_tool_names):
            raise ValueError("allowed_tool_names must be unique")
        return self


def _query_agent_user_content(request: CRMQueryAgentRequest) -> str:
    if request.previous_query is None and not request.entity_refs:
        return request.user_message

    instructions: list[str] = []
    if request.previous_query is not None:
        instructions.append(
            "这是连续追问。默认继承 previous_query 的资源、过滤条件、排序、scope 和游标; "
            "只有用户明确修改或取消某个条件时才能改变。"
        )
    if request.entity_refs:
        instructions.append(
            "序号或指代已由服务端解析; 查询时必须使用这些实体引用, 不得改选其他实体。"
        )

    return json.dumps(
        {
            "user_message": request.user_message,
            "previous_query": (
                request.previous_query.model_dump(mode="json", exclude_none=True)
                if request.previous_query is not None
                else None
            ),
            "server_authoritative_entity_refs": [
                ref.model_dump(mode="json", exclude_none=True)
                for ref in request.entity_refs
            ],
            "instruction": " ".join(instructions),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


class CRMQueryAgentResponse(QueryContractModel):
    """Model-authored prose plus references to authoritative tool evidence."""

    status: CRMQueryAgentStatus
    answer: str | None = Field(default=None, min_length=1, max_length=20_000)
    clarification_question: str | None = Field(default=None, min_length=1, max_length=2000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=300)

    @model_validator(mode="after")
    def validate_status_payload(self) -> CRMQueryAgentResponse:
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("evidence_refs must be unique")
        if self.status == "ANSWERED":
            if self.answer is None:
                raise ValueError("ANSWERED requires answer")
            if self.clarification_question is not None:
                raise ValueError("ANSWERED must not include clarification_question")
            if not self.evidence_refs:
                raise ValueError("ANSWERED requires evidence_refs")
            return self
        if self.answer is not None:
            raise ValueError("CLARIFICATION_REQUIRED must not include answer")
        if self.clarification_question is None:
            raise ValueError("CLARIFICATION_REQUIRED requires clarification_question")
        if self.evidence_refs:
            raise ValueError("CLARIFICATION_REQUIRED must not include evidence_refs")
        return self


class CRMQueryAgentToolCallTrace(QueryContractModel):
    """Auditable summary of one attempted Query Agent tool call."""

    tool_name: str = Field(min_length=1, max_length=200)
    status: CRMQueryAgentToolCallStatus
    elapsed_ms: int = Field(ge=0)
    entity_count: int = Field(default=0, ge=0)
    result_ref: str | None = Field(default=None, min_length=1, max_length=128)
    error_code: str | None = Field(default=None, min_length=1, max_length=128)


class CRMQueryAgentTrace(QueryContractModel):
    """Bounded execution trace without prompts, credentials, or business payloads."""

    model: str = Field(min_length=1, max_length=200)
    tool_names: list[str] = Field(default_factory=list, max_length=20)
    tool_calls: list[CRMQueryAgentToolCallTrace] = Field(default_factory=list, max_length=21)
    tool_call_count: int = Field(ge=0)
    total_entity_count: int = Field(ge=0)
    elapsed_ms: int = Field(ge=0)
    stop_reason: CRMQueryAgentStopReason


class CRMQueryAgentResult(QueryContractModel):
    """Authoritative results and the model's grounded response for one turn."""

    response: CRMQueryAgentResponse
    query_results: list[CRMQueryResult] = Field(default_factory=list, max_length=20)
    customer_context_results: list[CustomerContextResult] = Field(default_factory=list, max_length=20)
    trace: CRMQueryAgentTrace


class CRMQueryAgentExecutionError(RuntimeError):
    """Typed Query Agent failure that cannot be hidden by model prose."""

    def __init__(self, error: QueryError, trace: CRMQueryAgentTrace | None = None) -> None:
        super().__init__(error.message)
        self.error = error
        self.trace = trace


AgentFactory: TypeAlias = Callable[..., Any]
ChatModelFactory: TypeAlias = Callable[..., Any]


class _TurnExecution:
    """Mutable state scoped to one invocation; never retained by CRMQueryAgent."""

    def __init__(
        self,
        *,
        model: str,
        tool_names: list[str],
        limits: CRMQueryAgentLimits,
        deadline_at: float | None = None,
    ) -> None:
        self.model = model
        self.tool_names = tool_names
        self.limits = limits
        self.deadline_at = deadline_at
        self.started_at = monotonic()
        self.execution_lock = asyncio.Lock()
        self._state_lock = RLock()
        self.tool_call_count = 0
        self.query_correction_count = 0
        self.query_results: list[CRMQueryResult] = []
        self.customer_context_results: list[CustomerContextResult] = []
        self.tool_calls: list[CRMQueryAgentToolCallTrace] = []
        self.entity_keys: set[tuple[str, str]] = set()
        self.terminal_error: QueryError | None = None
        self.authoritative_empty_result: CRMQueryResult | None = None

    def begin_call(self, tool_name: str) -> bool:
        with self._state_lock:
            if self.terminal_error is not None or self.authoritative_empty_result is not None:
                return False
            self.tool_call_count += 1
            if self.tool_call_count <= self.limits.max_tool_calls:
                return True
            self.record_error(
                tool_name,
                QueryError(
                    code="QUERY_LIMIT_EXCEEDED",
                    message="Query Agent tool call limit exceeded",
                    retryable=False,
                ),
                started_at=monotonic(),
            )
            return False

    def record_result(self, tool_name: str, result: CRMReadToolResult, *, started_at: float) -> dict[str, object]:
        with self._state_lock:
            if self.terminal_error is not None:
                return _error_payload(self.terminal_error)
            entity_keys = self._entity_keys(result)
            if isinstance(result, CRMQueryResult) and len(result.rows) > self.limits.max_rows_per_tool:
                error = QueryError(
                    code="QUERY_LIMIT_EXCEEDED",
                    message="CRM read tool row limit exceeded",
                    retryable=False,
                )
                self.record_error(tool_name, error, started_at=started_at)
                return _error_payload(error)

            combined_keys = self.entity_keys | entity_keys
            if len(combined_keys) > self.limits.max_total_entities:
                error = QueryError(
                    code="QUERY_LIMIT_EXCEEDED",
                    message="Query Agent entity limit exceeded",
                    retryable=False,
                )
                self.record_error(tool_name, error, started_at=started_at)
                return _error_payload(error)

            self.entity_keys = combined_keys
            if isinstance(result, CRMQueryResult):
                self.query_results.append(result)
                result_ref = result.query_id
            else:
                self.customer_context_results.append(result)
                result_ref = result.customer_ref.ref_id
            self._append_tool_call(
                CRMQueryAgentToolCallTrace(
                    tool_name=tool_name,
                    status="SUCCESS",
                    elapsed_ms=_elapsed_ms(started_at),
                    entity_count=len(entity_keys),
                    result_ref=result_ref,
                )
            )
            payload = cast("dict[str, object]", result.model_dump(mode="json"))
            if isinstance(result, CRMQueryResult) and result.status == "EMPTY":
                self.authoritative_empty_result = result
            return payload

    def blocked_call_payload(self) -> dict[str, object]:
        with self._state_lock:
            if self.terminal_error is not None:
                return _error_payload(self.terminal_error)
            if self.authoritative_empty_result is not None:
                return cast(
                    "dict[str, object]",
                    self.authoritative_empty_result.model_dump(mode="json"),
                )
            raise RuntimeError("blocked Query Agent tool call has no terminal outcome")

    def authoritative_empty_response(self) -> CRMQueryAgentResponse | None:
        with self._state_lock:
            result = self.authoritative_empty_result
            if result is None:
                return None
            return CRMQueryAgentResponse(
                status="ANSWERED",
                answer=f"当前权限范围内未找到符合条件的{_resource_display_name(result.resource)}。",
                evidence_refs=[result.query_id],
            )

    def timeout_fallback_response(self) -> CRMQueryAgentResponse | None:
        """Return a grounded answer when CRM data is ready but prose generation times out."""

        with self._state_lock:
            if self.terminal_error is not None:
                return None
            empty_response = self.authoritative_empty_response()
            if empty_response is not None:
                return empty_response
            if not self.query_results and not self.customer_context_results:
                return None

            evidence_refs = sorted(_evidence_refs(self.query_results, self.customer_context_results))
            total = sum(
                result.total if result.total is not None else len(result.rows)
                for result in self.query_results
            )
            if self.query_results:
                resource_names = {_resource_display_name(result.resource) for result in self.query_results}
                resource_label = "、".join(sorted(resource_names))
                answer = f"已查询到 {total} 条{resource_label}。智能摘要暂时超时，以下展示已查询到的结构化结果。"
            else:
                answer = "已查询到相关客户信息。智能摘要暂时超时，以下展示已查询到的结构化结果。"
            return CRMQueryAgentResponse(
                status="ANSWERED",
                answer=answer,
                evidence_refs=evidence_refs,
            )

    def remaining_timeout(self, stage_timeout: float) -> float:
        """Return the smaller of a stage budget and the request's remaining deadline."""

        if self.deadline_at is None:
            return stage_timeout
        return max(0.001, min(stage_timeout, self.deadline_at - monotonic()))

    def record_query_invalid(
        self,
        tool_name: str,
        error: QueryError,
        *,
        started_at: float,
    ) -> dict[str, object]:
        with self._state_lock:
            self.query_correction_count += 1
            if self.query_correction_count <= self.limits.max_query_corrections:
                self._append_tool_call(
                    CRMQueryAgentToolCallTrace(
                        tool_name=tool_name,
                        status="ERROR",
                        elapsed_ms=_elapsed_ms(started_at),
                        error_code=error.code,
                    )
                )
                return _error_payload(error)
            exceeded = QueryError(
                code="QUERY_INVALID",
                message="QuerySpec correction limit exceeded",
                retryable=False,
            )
            self.record_error(tool_name, exceeded, started_at=started_at)
            return _error_payload(exceeded)

    def record_error(self, tool_name: str, error: QueryError, *, started_at: float) -> None:
        with self._state_lock:
            if self.terminal_error is None:
                self.terminal_error = error
            self._append_tool_call(
                CRMQueryAgentToolCallTrace(
                    tool_name=tool_name,
                    status="ERROR",
                    elapsed_ms=_elapsed_ms(started_at),
                    error_code=error.code,
                )
            )

    def _append_tool_call(self, trace: CRMQueryAgentToolCallTrace) -> None:
        if len(self.tool_calls) < self.limits.max_tool_calls + 1:
            self.tool_calls.append(trace)

    def trace(self, stop_reason: CRMQueryAgentStopReason = "COMPLETED") -> CRMQueryAgentTrace:
        with self._state_lock:
            return CRMQueryAgentTrace(
                model=self.model,
                tool_names=list(self.tool_names),
                tool_calls=list(self.tool_calls),
                tool_call_count=self.tool_call_count,
                total_entity_count=len(self.entity_keys),
                elapsed_ms=_elapsed_ms(self.started_at),
                stop_reason=stop_reason,
            )

    @staticmethod
    def _entity_keys(result: CRMReadToolResult) -> set[tuple[str, str]]:
        if not isinstance(result, CRMQueryResult):
            return {(result.customer_ref.resource, result.customer_ref.public_id)}
        keys: set[tuple[str, str]] = {
            (ref.resource, ref.public_id) for ref in result.entity_refs
        }
        keys.update(
            (fact.entity_ref.resource, fact.entity_ref.public_id)
            for fact in result.facts
            if fact.entity_ref is not None
        )
        keys.update(
            (result.resource, public_id)
            for row in result.rows
            if isinstance((public_id := row.get("public_id")), str) and public_id
        )
        return keys


class CRMQueryAgent:
    """Run a bounded LangChain agent over a dynamically selected read-only tool set."""

    def __init__(
        self,
        registry: CRMReadToolRegistry,
        *,
        agent_factory: AgentFactory = create_agent,
        chat_model_factory: ChatModelFactory = ChatOpenAI,
        limits: CRMQueryAgentLimits | None = None,
    ) -> None:
        if registry.write_tool_count != 0:
            raise ValueError("CRMQueryAgent requires a read-only registry")
        self._registry = registry
        self._agent_factory = agent_factory
        self._chat_model_factory = chat_model_factory
        self._limits = limits or CRMQueryAgentLimits()

    async def run(
        self,
        request: CRMQueryAgentRequest,
        tool_context: AgentToolContext,
        model_config: CRMQueryAgentModelConfig,
    ) -> CRMQueryAgentResult:
        specs = self._select_tool_specs(request.allowed_tool_names)
        tool_names = [spec.name for spec in specs]
        turn = _TurnExecution(
            model=model_config.model,
            tool_names=tool_names,
            limits=self._limits,
            deadline_at=tool_context.deadline_at,
        )
        tools = [
            self._build_tool(
                spec,
                tool_context,
                turn,
                previous_query=request.previous_query,
            )
            for spec in specs
        ]
        structured_corrections = 0

        @before_model(can_jump_to=["end"], name="authoritative_empty_termination")
        def terminate_on_authoritative_empty(
            _state: object,
            _runtime: object,
        ) -> dict[str, object] | None:
            response = turn.authoritative_empty_response()
            if response is None:
                return None
            return {"structured_response": response, "jump_to": "end"}

        def handle_structured_output_error(error: Exception) -> str:
            nonlocal structured_corrections
            structured_corrections += 1
            if structured_corrections > self._limits.max_structured_output_corrections:
                raise error
            return "结构化输出无效。请严格按照 schema 修正一次, 且不得添加 schema 之外的字段。"

        def execution_error(error: QueryError) -> CRMQueryAgentExecutionError:
            return CRMQueryAgentExecutionError(turn.terminal_error or error, turn.trace())

        try:
            model_kwargs: dict[str, object] = {
                "model": model_config.model,
                "api_key": model_config.api_key,
                "base_url": model_config.api_host,
                "temperature": model_config.temperature,
                "max_retries": 0,
            }
            if model_config.enable_thinking is not None:
                model_kwargs["extra_body"] = {"enable_thinking": model_config.enable_thinking}
            model = self._chat_model_factory(**model_kwargs)
            agent = self._agent_factory(
                model=model,
                tools=tools,
                system_prompt=QUERY_AGENT_SYSTEM_PROMPT,
                response_format=ToolStrategy(
                    CRMQueryAgentResponse,
                    handle_errors=handle_structured_output_error,
                ),
                middleware=[terminate_on_authoritative_empty],
                checkpointer=None,
                store=None,
                name="crm_query_agent",
            )
            async with asyncio.timeout(turn.remaining_timeout(self._limits.turn_timeout_seconds)):
                state = await agent.ainvoke(
                    {
                        "messages": [
                            {
                                "role": "user",
                                "content": _query_agent_user_content(request),
                            }
                        ]
                    },
                    config={"recursion_limit": self._limits.max_tool_calls * 2 + 4},
                )
        except TimeoutError as exc:
            fallback_response = turn.timeout_fallback_response()
            if fallback_response is not None:
                logger.warning(
                    "Query Agent summary timed out after authoritative results; returning deterministic fallback"
                )
                return CRMQueryAgentResult(
                    response=fallback_response,
                    query_results=turn.query_results,
                    customer_context_results=turn.customer_context_results,
                    trace=turn.trace("COMPLETED"),
                )
            raise execution_error(
                QueryError(
                    code="UPSTREAM_TIMEOUT",
                    message="Query Agent turn timed out",
                    retryable=True,
                )
            ) from exc
        except CRMQueryAgentExecutionError:
            raise
        except (StructuredOutputError, ValidationError) as exc:
            raise execution_error(
                QueryError(
                    code="MODEL_OUTPUT_INVALID",
                    message="Query Agent structured output is invalid",
                    retryable=False,
                )
            ) from exc
        except Exception as exc:
            raise execution_error(
                QueryError(
                    code="INTERNAL_ERROR",
                    message="Query Agent execution failed",
                    retryable=False,
                )
            ) from exc

        if turn.terminal_error is not None:
            raise CRMQueryAgentExecutionError(turn.terminal_error, turn.trace())

        try:
            response = CRMQueryAgentResponse.model_validate(state.get("structured_response"))
        except (AttributeError, ValidationError) as exc:
            raise CRMQueryAgentExecutionError(
                QueryError(
                    code="MODEL_OUTPUT_INVALID",
                    message="Query Agent structured response is missing or invalid",
                    retryable=False,
                ),
                turn.trace(),
            ) from exc

        self._validate_grounding(response, turn)
        stop_reason: CRMQueryAgentStopReason = (
            "CLARIFICATION_REQUIRED" if response.status == "CLARIFICATION_REQUIRED" else "COMPLETED"
        )
        return CRMQueryAgentResult(
            response=response,
            query_results=turn.query_results,
            customer_context_results=turn.customer_context_results,
            trace=turn.trace(stop_reason),
        )

    def _select_tool_specs(self, allowed_tool_names: Sequence[str] | None) -> list[CRMReadToolSpec]:
        available = self._registry.list_specs()
        selected_names = list(allowed_tool_names) if allowed_tool_names is not None else list(available)
        unknown = [name for name in selected_names if name not in available]
        if unknown:
            names = ", ".join(sorted(unknown))
            raise CRMQueryAgentExecutionError(
                QueryError(
                    code="QUERY_INVALID",
                    message=f"Unregistered CRM read tools requested: {names}",
                    retryable=False,
                )
            )
        specs = [available[name] for name in selected_names]
        if any(spec.is_write for spec in specs):
            raise CRMQueryAgentExecutionError(
                QueryError(
                    code="INTERNAL_ERROR",
                    message="Query Agent tool surface contains a write tool",
                    retryable=False,
                )
            )
        return specs

    def _build_tool(
        self,
        spec: CRMReadToolSpec,
        context: AgentToolContext,
        turn: _TurnExecution,
        *,
        previous_query: CRMQuerySpec | None,
    ) -> StructuredTool:
        async def coroutine(**kwargs: object) -> dict[str, object]:
            async with turn.execution_lock:
                started_at = monotonic()
                kwargs = _inherit_previous_query_filters(
                    previous_query=previous_query,
                    resource=spec.resource,
                    tool_input=kwargs,
                )
                if not turn.begin_call(spec.name):
                    return turn.blocked_call_payload()
                if spec.resource is not None:
                    page_size = kwargs.get("page_size")
                    if isinstance(page_size, int) and page_size > self._limits.max_rows_per_tool:
                        error = QueryError(
                            code="QUERY_LIMIT_EXCEEDED",
                            message="Requested page_size exceeds the Query Agent row limit",
                            retryable=False,
                            field="page_size",
                        )
                        turn.record_error(spec.name, error, started_at=started_at)
                        return _error_payload(error)
                try:
                    async with asyncio.timeout(turn.remaining_timeout(self._limits.tool_timeout_seconds)):
                        result = await self._registry.execute(spec.name, context, kwargs)
                except TimeoutError:
                    error = QueryError(
                        code="UPSTREAM_TIMEOUT",
                        message=f"CRM read tool timed out: {spec.name}",
                        retryable=True,
                    )
                    turn.record_error(spec.name, error, started_at=started_at)
                    return _error_payload(error)
                except CRMQueryExecutionError as exc:
                    if exc.error.code == "QUERY_INVALID":
                        return turn.record_query_invalid(spec.name, exc.error, started_at=started_at)
                    turn.record_error(spec.name, exc.error, started_at=started_at)
                    return _error_payload(exc.error)
                except (CRMReadToolInputError, ValidationError) as exc:
                    error = QueryError(code="QUERY_INVALID", message=str(exc), retryable=False)
                    return turn.record_query_invalid(spec.name, error, started_at=started_at)
                except Exception:
                    error = QueryError(
                        code="INTERNAL_ERROR",
                        message=f"CRM read tool failed: {spec.name}",
                        retryable=False,
                    )
                    turn.record_error(spec.name, error, started_at=started_at)
                    return _error_payload(error)
                return turn.record_result(spec.name, result, started_at=started_at)

        def handle_validation_error(error: Exception) -> str:
            started_at = monotonic()
            if not turn.begin_call(spec.name):
                payload = turn.blocked_call_payload()
            else:
                query_error = QueryError(code="QUERY_INVALID", message=str(error), retryable=False)
                payload = turn.record_query_invalid(spec.name, query_error, started_at=started_at)
            return json.dumps(payload, ensure_ascii=False)

        return StructuredTool.from_function(
            coroutine=coroutine,
            name=spec.name,
            description=spec.description,
            args_schema=spec.input_model,
            handle_validation_error=handle_validation_error,
        )

    @staticmethod
    def _validate_grounding(response: CRMQueryAgentResponse, turn: _TurnExecution) -> None:
        if response.status == "CLARIFICATION_REQUIRED":
            return
        if not turn.query_results and not turn.customer_context_results:
            raise CRMQueryAgentExecutionError(
                QueryError(
                    code="MODEL_OUTPUT_INVALID",
                    message="ANSWERED requires authoritative CRM tool results",
                    retryable=False,
                ),
                turn.trace(),
            )
        allowed_refs = _evidence_refs(turn.query_results, turn.customer_context_results)
        unknown_refs = set(response.evidence_refs) - allowed_refs
        if unknown_refs:
            raise CRMQueryAgentExecutionError(
                QueryError(
                    code="MODEL_OUTPUT_INVALID",
                    message="Query Agent response references unknown evidence",
                    retryable=False,
                ),
                turn.trace(),
            )


def _resource_display_name(resource: str) -> str:
    return {
        "customer": "客户",
        "contact": "联系人",
        "customer_activity": "客户活动",
        "follow_up_task": "跟进任务",
        "completed_work": "已完成工作",
        "opportunity": "商机",
        "contract": "合同",
        "payment_plan": "回款计划",
        "payment": "回款记录",
        "invoice": "发票",
        "license": "许可证",
    }.get(resource, "数据")


def _inherit_previous_query_filters(
    *,
    previous_query: CRMQuerySpec | None,
    resource: str | None,
    tool_input: dict[str, object],
) -> dict[str, object]:
    if previous_query is None or resource != previous_query.resource:
        return tool_input

    current_filters = tool_input.get("filters")
    if not isinstance(current_filters, list):
        return tool_input
    current_fields = {
        field
        for item in current_filters
        if isinstance(
            (
                field := (
                    item.field
                    if isinstance(item, CRMFilter)
                    else item.get("field")
                    if isinstance(item, dict)
                    else None
                )
            ),
            str,
        )
    }
    inherited_filters = [
        item.model_dump(mode="json")
        for item in previous_query.filters
        if item.field not in current_fields
    ]
    if not inherited_filters:
        return tool_input
    return {
        **tool_input,
        "filters": [*inherited_filters, *current_filters],
    }


def _evidence_refs(
    query_results: Sequence[CRMQueryResult],
    context_results: Sequence[CustomerContextResult],
) -> set[str]:
    refs: set[str] = set()
    for result in query_results:
        refs.add(result.query_id)
        refs.update(ref.ref_id for ref in result.entity_refs)
        refs.update(fact.fact_id for fact in result.facts)
    for context_result in context_results:
        refs.add(context_result.customer_ref.ref_id)
        refs.update(citation.citation_id for citation in context_result.citations)
    return refs


def _error_payload(error: QueryError) -> dict[str, object]:
    return {"error": cast("dict[str, object]", error.model_dump(mode="json"))}


def _elapsed_ms(started_at: float) -> int:
    return max(0, int((monotonic() - started_at) * 1000))

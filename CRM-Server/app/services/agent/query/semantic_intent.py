"""LLM-backed semantic intent resolution for CRM Query turns.

The Root/Query boundary must not maintain a growing dictionary of Chinese
keywords.  This module translates a user's natural-language query into a small
closed contract.  The returned customer text is only a lookup hint; customer
identity and all dates are still validated by server-owned services.
"""

from __future__ import annotations

import json
from datetime import datetime
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo

from langchain_openai import ChatOpenAI
from pydantic import ConfigDict, Field, model_validator

from app.core.config import get_settings
from app.services.agent.query.schemas import QueryContractModel
from app.services.agent.structured_model_call import (
    StructuredModelCallError,
    ainvoke_structured_output,
)
from app.utils.time import BUSINESS_TIMEZONE, business_now

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.services.agent.orchestrator.contracts import RootRuntimeContext
    from app.services.agent.query.agent import CRMQueryAgentModelConfig


QueryIntentScope = Literal["global_work", "customer_scoped", "customer_list", "unknown"]
QueryIntentGoal = Literal["list", "search", "get_detail", "get_status", "summarize"]
QueryIntentResource = Literal[
    "follow_up_tasks",
    "completed_work",
    "customer_context",
    "customer_activities",
    "customer_contacts",
    "deployment_info",
    "customers",
]
TemporalKind = Literal[
    "today",
    "tomorrow",
    "this_week",
    "next_week",
    "last_week",
    "this_month",
    "overdue",
    "custom",
    "unspecified",
]


class QueryTemporalIntent(QueryContractModel):
    """A normalized temporal meaning, independent of the source language."""

    model_config = ConfigDict(extra="forbid", strict=True)

    kind: TemporalKind = "unspecified"
    start_at: str | None = Field(default=None, min_length=1, max_length=64)
    end_at: str | None = Field(default=None, min_length=1, max_length=64)
    timezone: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="before")
    @classmethod
    def discard_provider_derived_standard_bounds(cls, value: Any) -> Any:
        """Keep server-owned date semantics tolerant of provider over-specification.

        Some structured-output providers add an ``end_at`` (or both bounds)
        while returning a standard temporal kind such as ``this_week``. Those
        bounds are not authoritative and the query seam computes them from
        the request-time clock, so rejecting the whole turn would make a valid
        natural-language query fail spuriously. Custom ranges still retain
        both bounds and are validated strictly below.
        """
        if isinstance(value, dict) and value.get("kind") not in {None, "custom"}:
            normalized = dict(value)
            normalized.pop("start_at", None)
            normalized.pop("end_at", None)
            return normalized
        return value

    @model_validator(mode="after")
    def validate_custom_range(self) -> QueryTemporalIntent:
        has_range = self.start_at is not None or self.end_at is not None
        if self.kind == "custom" and (self.start_at is None or self.end_at is None):
            raise ValueError("custom temporal intent requires start_at and end_at")
        if self.kind != "custom" and has_range:
            raise ValueError("start_at and end_at are only allowed for custom temporal intent")
        if self.timezone is not None:
            try:
                ZoneInfo(self.timezone)
            except Exception as exc:
                raise ValueError("timezone must be a valid IANA timezone") from exc
        if self.kind == "custom":
            assert self.start_at is not None and self.end_at is not None
            try:
                start = datetime.fromisoformat(self.start_at)
                end = datetime.fromisoformat(self.end_at)
            except ValueError as exc:
                raise ValueError("custom temporal bounds must be ISO dates or datetimes") from exc
            if end <= start:
                raise ValueError("custom temporal end_at must be later than start_at")
        return self


class CRMQuerySemanticIntent(QueryContractModel):
    """Closed, model-authored intent consumed by the deterministic query seam."""

    model_config = ConfigDict(extra="forbid", strict=True)

    scope: QueryIntentScope
    resource: QueryIntentResource | None = None
    query_goal: QueryIntentGoal = "list"
    task_text: str | None = Field(default=None, min_length=1, max_length=1000)
    customer_text: str | None = Field(default=None, min_length=1, max_length=255)
    temporal: QueryTemporalIntent = Field(default_factory=QueryTemporalIntent)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_scope(self) -> CRMQuerySemanticIntent:
        if self.scope == "global_work" and self.resource not in {"follow_up_tasks", "completed_work"}:
            raise ValueError("global_work requires a work resource")
        if self.scope == "customer_scoped" and self.resource not in {
            "follow_up_tasks",
            "completed_work",
            "customer_context",
            "customer_activities",
            "customer_contacts",
            "deployment_info",
        }:
            raise ValueError("customer_scoped requires a customer resource")
        # Customer identity may come from the selected entity context rather
        # than the user's words. The identity binder remains authoritative
        # when customer_text is present; the query seam binds the selected
        # entity when it is absent.
        if self.scope != "customer_scoped" and self.customer_text is not None:
            raise ValueError("customer_text is only allowed for customer_scoped intent")
        if self.scope == "customer_list" and self.resource != "customers":
            raise ValueError("customer_list requires the customers resource")
        if self.scope == "unknown" and self.resource is not None:
            raise ValueError("unknown intent must not select a resource")
        if self.task_text is not None and self.resource != "follow_up_tasks":
            raise ValueError("task_text is only allowed for follow_up_tasks")
        if self.query_goal in {"get_detail", "get_status"} and self.resource != "follow_up_tasks":
            raise ValueError("task detail and status goals require follow_up_tasks")
        if self.query_goal == "summarize" and self.resource != "completed_work":
            raise ValueError("summarize goal requires completed_work")
        if self.task_text is not None and self.query_goal not in {"search", "get_detail", "get_status"}:
            raise ValueError("task_text requires a task search, detail, or status goal")
        return self


QUERY_SEMANTIC_INTENT_SYSTEM_PROMPT = """
你是 CRM Query 的语义解析器, 只输出结构化 JSON, 不调用工具, 不回答用户问题。

请把用户原话解析为以下闭合意图:
- global_work: 查询当前用户自己的待办/跟进安排, 或查询当前用户已经完成的工作;
- customer_scoped: 查询某一家明确客户的档案、联系人、部署信息、跟进记录、待办或完成情况;
- customer_list: 查询一组客户;
- unknown: 无法确定查询对象。

规则:
1. 先理解语义, 不要按固定关键词或固定句式匹配。口语、同义表达、倒装、省略都要按含义判断。
2. global_work 的 resource 只能是 follow_up_tasks 或 completed_work。
   未来/当前要做的事归 follow_up_tasks; 已经做过的事归 completed_work。
   query_goal 表示用户真正要做的查询：
   - list：列出一组记录；
   - search：按自然语言描述寻找记录；
   - get_detail：查看明确记录的详情；
   - get_status：确认明确待办的当前状态；
   - summarize：汇总一段时间内已完成的工作。
   “这个待办完成了吗/上次那个跟进现在怎样”属于 get_status 或 get_detail，
   不要因为“历史/上次”就只查 completed_work。task_text 只填写用户对待办的自然语言描述，
   不要填写数据库 ID；明确的服务端实体引用由系统提供。
3. temporal.kind 只能填写标准语义: today、tomorrow、this_week、next_week、last_week、this_month、
   overdue、custom、unspecified。
   “未来两周”“最近几天”“截至月底”“9月上旬”等表达, 若能从原话明确得到边界,
   填写 custom 并给出 ISO 日期时间的 [start_at, end_at); 无法可靠确定边界则填写 unspecified。
4. custom 的 end_at 是排他边界。日期范围必须给出完整 ISO 日期或 ISO 日期时间, 不要输出中文日期。
   日期计算必须以请求中提供的 reference_now 和 reference_timezone 为准, 不要使用模型自身的当前日期。
5. “某客户下周有哪些待办”是 customer_scoped, 不是 global_work; customer_text 填写客户名称或简称；如果用户没有在原话中说出客户，但上下文提供了当前客户，也可以省略 customer_text。
   不要把时间和问题一起放进去。
6. 不要根据公司名称、行业或上下文猜客户。没有明确客户提及时 customer_text 必须为空。
7. completed_work 只能表达已经发生的工作; 未来时间与 completed_work 冲突时,
   返回 unknown 或把语义改为 follow_up_tasks。
8. 如果用户没有给出时间范围，当前待办查询使用全部未完成待办；已完成工作查询使用安全的近期默认范围，
   不要仅因为时间省略就追问。回答中应明确告知实际采用的范围。
9. confidence 反映语义判断把握, 不是业务事实可信度。
"""


class QuerySemanticIntentUnavailableError(RuntimeError):
    """The semantic intent model could not be called."""


class QuerySemanticIntentInvalidError(ValueError):
    """The semantic intent model returned an invalid closed-contract result."""


class LLMQuerySemanticIntentResolver:
    """Resolve query scope/resource/time with one bounded structured LLM call."""

    def __init__(
        self,
        *,
        chat_model_factory: Callable[..., Any] = ChatOpenAI,
        timeout_seconds: float | None = None,
        now_factory: Callable[[], datetime] = business_now,
    ) -> None:
        timeout_seconds = (
            get_settings().AGENT_QUERY_SEMANTIC_TIMEOUT
            if timeout_seconds is None
            else timeout_seconds
        )
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._chat_model_factory = chat_model_factory
        self._timeout_seconds = timeout_seconds
        self._now_factory = now_factory

    async def resolve(
        self,
        text: str,
        *,
        model_config: CRMQueryAgentModelConfig,
        runtime: RootRuntimeContext,
    ) -> CRMQuerySemanticIntent:
        try:
            timeout_seconds = self._timeout_seconds
            if runtime.deadline_at is not None:
                timeout_seconds = max(0.001, min(timeout_seconds, runtime.deadline_at - monotonic()))
            result = await ainvoke_structured_output(
                CRMQuerySemanticIntent,
                [
                    {"role": "system", "content": QUERY_SEMANTIC_INTENT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "user_message": text,
                                "reference_now": self._now_factory().isoformat(),
                                "reference_timezone": BUSINESS_TIMEZONE,
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                chat_model_factory=self._chat_model_factory,
                model=model_config.model,
                api_key=model_config.api_key,
                base_url=model_config.api_host,
                temperature=0,
                enable_thinking=model_config.enable_thinking,
                max_tokens=model_config.max_tokens,
                timeout_seconds=timeout_seconds,
            )
        except StructuredModelCallError as exc:
            raise QuerySemanticIntentUnavailableError("query semantic intent model request failed") from exc
        try:
            return CRMQuerySemanticIntent.model_validate(result)
        except Exception as exc:
            raise QuerySemanticIntentInvalidError("query semantic intent model returned invalid output") from exc

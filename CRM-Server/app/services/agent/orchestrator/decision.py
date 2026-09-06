"""Structured model classification for ordinary Root text turns."""

# ruff: noqa: RUF001

from __future__ import annotations

import asyncio
import json
from time import monotonic
from typing import TYPE_CHECKING

from langchain_openai import ChatOpenAI
from openai import APIError, APITimeoutError
from pydantic import ValidationError

from app.core.config import get_settings

from app.services.agent.orchestrator.contracts import (
    RootContextSnapshot,
    RootDecision,
    RootRuntimeContext,
    RootTurnInput,
)
from app.services.ai_http_client import managed_ai_http_clients

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any


ROOT_DECISION_SYSTEM_PROMPT = """你是 CRM Agent 的 Root Orchestrator 决策器, 只输出结构化任务决策, 不调用工具。

你必须同时判断:
0. semantic_plan: 先判断用户本轮话语的真实业务语义, 再决定 route. 必须区分“陈述刚刚发生的事实”和“询问历史事实”。
1. task_relation: NEW_TASK、CONTINUE_TASK 或 SWITCH_TASK.
2. route: QUERY、WORKFLOW 或 CLARIFY.
3. risk: QUERY 必须为 READ_ONLY; WORKFLOW 必须为 WRITE.
4. context_policy: selected_entity、previous_query、result_set、active_workflow、conversation_memory 的逐项使用策略.

硬规则:
- 先输出 semantic_plan, 再基于 semantic_plan 选择 route；route 不能与 semantic_plan 冲突。
- 如果 route=QUERY 且能明确判断查询范围, semantic_plan.query_plan 必须同时填写完整的
  scope、resource、customer_text（仅 customer_scoped 时填写）和 temporal；时间标准化使用
  reference_now/reference_timezone，不要猜测。query_plan 不完整时才允许留空。
- “刚刚/今天/昨天 + 和客户沟通/联系/拜访/开会了……”是 ASSERT_EVENT；
  如果用户是在沉淀这次事实，通常是 CUSTOMER_ACTIVITY + CREATE + WORKFLOW。
- “查询/查一下/最近有哪些/历史记录显示什么”是在 ASK_FACT；
  只有明确读取已有事实时才是 CUSTOMER_ACTIVITY + READ + QUERY。
- 过去时间表达描述事件发生时间，不代表用户在查询历史；必须根据用户是在陈述事件还是提问来判断。
- ASSERT_EVENT + CUSTOMER_ACTIVITY + CREATE 必须是 WORKFLOW + WRITE；
  ASK_FACT + CUSTOMER_ACTIVITY + READ 必须是 QUERY + READ_ONLY。
- 如果 semantic_plan 与模型初步 route 不一致，以 semantic_plan 的业务语义为准，
  不要用当前会话的 previous_query、recent_messages 或 conversation_memory 改写本轮的读写性质。
- context_snapshot 中没有 active_workflow 时, context_policy.active_workflow 必须为 NONE, 不得输出 SUSPEND 或 RESUME。
- 用户明确指定新的城市、客户名称、对象或业务目标时, 不得让旧 selected entity、previous query 或 result set 覆盖新条件。
- 新的独立写入任务必须是 NEW_TASK + WORKFLOW + WRITE; 没有 active workflow 时将 active_workflow 设为 NONE。
- “已联系/沟通/拜访客户 + 业务反馈或后续跟进时间”属于创建客户跟进记录/任务的写入, 必须路由 WORKFLOW, 不是 CLARIFY。
- 先区分用户是在“询问事实”还是“要求改变状态”：
  - “历史待办完成了吗”“确认一下上次待办是否完成”是在查询当前状态, 必须是 QUERY + READ_ONLY；
  - “把这个待办标记为完成”“完成这个待办”才是 FOLLOW_UP_TASK_TRANSITION 对应的 WORKFLOW + WRITE。
  - 只有挂起的确认交互中, 用户用“是/确认/提交”等短回答, 才按当前 checkpoint 继续；普通文本不能仅凭一个关键词猜成写入。
- 存在 active workflow 不等于本轮一定继续. 无关的新查询或新写入必须是 SWITCH_TASK, 并将 active_workflow 设为 SUSPEND。
- 只有明确继续当前任务时才能 CONTINUE_TASK + WORKFLOW + RESUME。
- “继续”“好的”等低信息文本若无法唯一匹配当前任务, 必须 CLARIFY, 不得自动恢复。
- pending_case_relation: NONE、EXPLICIT_REFERENCE、RELATED_TO_CURRENT_ACTIVITY、UNRELATED 或 AMBIGUOUS。
- pending_case_reference 只填写用户原文中的待办引用, 不填写或猜测数据库 Case ID。
- 普通新跟进记录不能因为 pending_cases 存在而恢复历史待办, 只有用户明确引用待办且服务端唯一匹配时才恢复。
- “今天联系了客户……”是新的 Workflow Text Start, 历史待办是否自动完成由后续任务对账/语义匹配处理, 不由 Root 恢复旧 Case。
- 独立查询“上海有哪些客户”必须忽略页面中已选中的其他客户。
- “这周有哪些事情要做”“接下来有哪些待跟进事项”是当前用户的全局待办查询, 不要把“这周”“接下来”或“事情”当作客户名称。
- 时间范围、待办、跟进安排等查询语义由 Query Semantic Intent 解析器负责;
  Root 只负责任务关系和路由, 不要自行创造客户身份。
- recent_messages 是近期会话上下文, 只用于理解省略和承接, 不是绝对事实。
- conversation_memory 是此前已经确认过的短期会话记忆, 不是 CRM 权威事实。
  补充上一轮内容时默认复用它, 不要因为记忆中有客户就再次搜索。
- 如果本轮明确指定了新的客户、对象或业务目标, 覆盖旧记忆;
  如果只是补充当前任务, 保留旧客户绑定并合并语义。
- 只有无法判断是承接还是新任务时才 CLARIFY, 不要用关键词或固定短语抢路由。
- route=CLARIFY 时，clarification_question 必须给出一个面向用户、只针对当前缺失信息的简短问题；
  不要总是询问“继续当前任务还是开始新任务”。
- 澄清问题不得编造客户、待办、商机或数据库 ID，不得包含模型推理，不得直接要求执行动作。
- 如果是服务端校验发现上下文失效，服务端可能替换模型问题；因此问题必须是可安全降级的自然语言。
- reason_code 使用简短 UPPER_SNAKE_CASE; evidence 仅写本次判断依据, 不写业务事实。
- 只返回 schema, 不输出 Markdown 或额外文本。
"""


class RootDecisionModelUnavailableError(RuntimeError):
    """The configured Root decision model could not be reached."""

    def __init__(self, message: str, *, reason: str = "UNAVAILABLE") -> None:
        super().__init__(message)
        self.reason = reason


class RootDecisionInvalidOutputError(ValueError):
    """The Root decision model returned data outside the closed contract."""


class LangChainRootDecisionClassifier:
    """One bounded structured-output call for non-deterministic text decisions."""

    def __init__(
        self,
        *,
        chat_model_factory: Callable[..., Any] = ChatOpenAI,
        timeout_seconds: float | None = None,
    ) -> None:
        timeout_seconds = (
            get_settings().AGENT_ROOT_DECISION_TIMEOUT
            if timeout_seconds is None
            else timeout_seconds
        )
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._chat_model_factory = chat_model_factory
        self._timeout_seconds = timeout_seconds

    def _remaining_timeout(self, runtime: RootRuntimeContext) -> float:
        if runtime.deadline_at is None:
            return self._timeout_seconds
        return max(0.001, min(self._timeout_seconds, runtime.deadline_at - monotonic()))

    async def classify(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> RootDecision:
        model_config = runtime.root_model_config
        if model_config is None:
            raise RootDecisionModelUnavailableError("Root decision model config is missing")

        model_kwargs: dict[str, object] = {
            "model": model_config.model,
            "api_key": model_config.api_key,
            "base_url": model_config.api_host,
            "temperature": model_config.temperature,
            "max_retries": 0,
        }
        if model_config.enable_thinking is not None:
            model_kwargs["extra_body"] = {"enable_thinking": model_config.enable_thinking}
        context_payload = context.model_dump(
            mode="json",
            exclude_none=True,
            exclude={"resumable_workflows", "resumable_workflow_continuations"},
        )
        # Empty optional indexes add noise to the model boundary and make the
        # payload less stable.  A non-empty pending-case index is still sent so
        # the classifier can distinguish an explicit reference from a normal
        # activity; the server-side matcher remains authoritative for IDs.
        if not context.pending_cases:
            context_payload.pop("pending_cases", None)
        else:
            # Case IDs are internal binding material.  The deterministic
            # matcher receives the full server-side snapshot, while the LLM
            # only sees safe display context and the original reference.
            context_payload["pending_cases"] = [
                {
                    key: value
                    for key, value in pending_case.items()
                    if key != "case_public_id"
                }
                for pending_case in context_payload["pending_cases"]
            ]
        if context.conversation_memory == context.conversation_memory.__class__():
            context_payload.pop("conversation_memory", None)
        if not context.recent_messages:
            context_payload.pop("recent_messages", None)
        payload = json.dumps(
            {
                "input": turn.input.model_dump(mode="json"),
                "selected_entity_ref": (
                    turn.selected_entity_ref.model_dump(mode="json", exclude_none=True)
                    if turn.selected_entity_ref is not None
                    else None
                ),
                "context_snapshot": context_payload,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            timeout_seconds = self._remaining_timeout(runtime)
            async with asyncio.timeout(timeout_seconds):
                use_managed_transport = self._chat_model_factory is ChatOpenAI
                async with managed_ai_http_clients(enabled=use_managed_transport) as transport_kwargs:
                    model = self._chat_model_factory(**model_kwargs, **transport_kwargs)
                    structured_model = model.with_structured_output(
                        RootDecision,
                        method="function_calling",
                    )
                    result = await structured_model.ainvoke(
                        [
                            {"role": "system", "content": ROOT_DECISION_SYSTEM_PROMPT},
                            {"role": "user", "content": payload},
                        ]
                    )
        except (APITimeoutError, TimeoutError) as exc:
            raise RootDecisionModelUnavailableError(
                "Root decision model request timed out",
                reason="TIMEOUT",
            ) from exc
        except APIError as exc:
            raise RootDecisionModelUnavailableError(
                "Root decision model request failed",
                reason="UNAVAILABLE",
            ) from exc
        try:
            return RootDecision.model_validate(result)
        except ValidationError as exc:
            raise RootDecisionInvalidOutputError("Root decision model returned invalid structured output") from exc

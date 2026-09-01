"""Structured model classification for ordinary Root text turns."""

from __future__ import annotations

import asyncio
import json
from time import monotonic
from typing import TYPE_CHECKING

from langchain_openai import ChatOpenAI
from openai import APIError
from pydantic import ValidationError

from app.services.agent.orchestrator.contracts import (
    RootContextSnapshot,
    RootDecision,
    RootRuntimeContext,
    RootTurnInput,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any


ROOT_DECISION_SYSTEM_PROMPT = """你是 CRM Agent 的 Root Orchestrator 决策器, 只输出结构化任务决策, 不调用工具。

你必须同时判断:
1. task_relation: NEW_TASK、CONTINUE_TASK 或 SWITCH_TASK.
2. route: QUERY、WORKFLOW 或 CLARIFY.
3. risk: QUERY 必须为 READ_ONLY; WORKFLOW 必须为 WRITE.
4. context_policy: selected_entity、previous_query、result_set、active_workflow 的逐项使用策略.

硬规则:
- context_snapshot 中没有 active_workflow 时, context_policy.active_workflow 必须为 NONE, 不得输出 SUSPEND 或 RESUME。
- 用户明确指定新的城市、客户名称、对象或业务目标时, 不得让旧 selected entity、previous query 或 result set 覆盖新条件。
- 新的独立写入任务必须是 NEW_TASK + WORKFLOW + WRITE; 没有 active workflow 时将 active_workflow 设为 NONE。
- “已联系/沟通/拜访客户 + 业务反馈或后续跟进时间”属于创建客户跟进记录/任务的写入, 必须路由 WORKFLOW, 不是 CLARIFY。
- 存在 active workflow 不等于本轮一定继续. 无关的新查询或新写入必须是 SWITCH_TASK, 并将 active_workflow 设为 SUSPEND。
- 只有明确继续当前任务时才能 CONTINUE_TASK + WORKFLOW + RESUME。
- “继续”“好的”等低信息文本若无法唯一匹配当前任务, 必须 CLARIFY, 不得自动恢复。
- pending_case_relation: NONE、EXPLICIT_REFERENCE、RELATED_TO_CURRENT_ACTIVITY、UNRELATED 或 AMBIGUOUS。
- pending_case_reference 只填写用户原文中的待办引用, 不填写或猜测数据库 Case ID。
- 普通新跟进记录不能因为 pending_cases 存在而恢复历史待办, 只有用户明确引用待办且服务端唯一匹配时才恢复。
- “今天联系了客户……”是新的 Workflow Text Start, 历史待办是否自动完成由后续任务对账/语义匹配处理, 不由 Root 恢复旧 Case。
- 独立查询“上海有哪些客户”必须忽略页面中已选中的其他客户。
- “这周有哪些事情要做”“接下来有哪些待跟进事项”是当前用户的全局待办查询, 不要把“这周”“接下来”或“事情”当作客户名称。
- 时间范围、待办、跟进安排等查询语义由 Query Semantic Intent 解析器负责; Root 只负责任务关系和路由, 不要自行创造客户身份。
- reason_code 使用简短 UPPER_SNAKE_CASE; evidence 仅写本次判断依据, 不写业务事实。
- 只返回 schema, 不输出 Markdown 或额外文本。
"""


class RootDecisionModelUnavailableError(RuntimeError):
    """The configured Root decision model could not be reached."""


class RootDecisionInvalidOutputError(ValueError):
    """The Root decision model returned data outside the closed contract."""


class LangChainRootDecisionClassifier:
    """One bounded structured-output call for non-deterministic text decisions."""

    def __init__(
        self,
        *,
        chat_model_factory: Callable[..., Any] = ChatOpenAI,
        timeout_seconds: float = 20.0,
    ) -> None:
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
        model = self._chat_model_factory(**model_kwargs)
        structured_model = model.with_structured_output(
            RootDecision,
            method="function_calling",
        )
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
                result = await structured_model.ainvoke(
                    [
                        {"role": "system", "content": ROOT_DECISION_SYSTEM_PROMPT},
                        {"role": "user", "content": payload},
                    ]
                )
        except (APIError, TimeoutError) as exc:
            raise RootDecisionModelUnavailableError("Root decision model request failed") from exc
        try:
            return RootDecision.model_validate(result)
        except ValidationError as exc:
            raise RootDecisionInvalidOutputError("Root decision model returned invalid structured output") from exc

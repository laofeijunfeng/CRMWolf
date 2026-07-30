"""LangChain structured-output agent for customer activity evaluation."""
from __future__ import annotations

import json
from typing import Any

from app.crud.ai_config import ai_config_crud
from app.services.agent.langchain_runtime import AgentLangChainRuntime
from app.services.customer_activity_ai.rules import ActivityEvaluationRubric
from app.services.customer_activity_ai.schemas import ActivityEvaluationResult


class ActivityEvaluationError(Exception):
    """Raised when an activity cannot be evaluated reliably."""


class ActivityEvaluationAgent:
    def __init__(self, runtime: AgentLangChainRuntime | None = None) -> None:
        self.runtime = runtime or AgentLangChainRuntime()

    async def evaluate(
        self,
        db,
        *,
        team_id: int,
        context: dict[str, Any],
        rubric: ActivityEvaluationRubric,
    ) -> dict[str, Any]:
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            raise ActivityEvaluationError("AI 配置未设置")
        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            raise ActivityEvaluationError("无法获取 API Key")

        result = await self.runtime.ainvoke_structured(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            temperature=min(float(config.temperature or 0.1), 0.2),
            system_prompt=self._system_prompt(rubric),
            user_prompt="请评估以下客户活动是否有效：\n" + json.dumps(context, ensure_ascii=False, default=str),
            response_model=ActivityEvaluationResult,
            error_prefix="客户活动评分 structured output",
        )
        if result is None:
            raise ActivityEvaluationError("LangChain structured output 不可用")
        normalized = result.model_dump(mode="json")
        score = max(0, min(100, int(normalized.get("score") or 0)))
        normalized["score"] = score
        normalized["is_valid"] = score >= 60
        normalized["reason"] = (normalized.get("reason") or "缺少可接力的关键信息或明确下一步动作。")[:120]
        return normalized

    def _system_prompt(self, rubric: ActivityEvaluationRubric) -> str:
        return f"""你是 CRM 系统中的客户活动质检 Agent。

任务：判断一条客户活动记录是否对销售推进和团队接力有价值。

评分规则：{rubric.title}
{rubric.principles}

评估重点：
{rubric.emphasis}

硬性要求：
- 只基于输入内容和上下文评分，不要编造。
- score 必须是 0-100 的整数。
- is_valid 必须等于 score >= 60。
- reason 必须是一句话，最长 80 个中文字符。
- principle_scores 必须对应评分规则逐项给分和简短原因。
- 输出必须符合结构化 schema，不要输出 Markdown 或解释文字。"""


activity_evaluation_agent = ActivityEvaluationAgent()


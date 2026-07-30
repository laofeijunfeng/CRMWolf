"""LangChain structured-output agent for customer activity structuring."""
from __future__ import annotations

import re
from typing import Any

from app.crud.ai_config import ai_config_crud
from app.services.agent.langchain_runtime import AgentLangChainRuntime, AgentLangChainStructuredOutputError
from app.services.customer_activity_ai.schemas import (
    FollowUpStructuringResult,
    MeetingStructuringResult,
)


class ActivityStructuringError(Exception):
    """Raised when an activity cannot be structured reliably."""


class ActivityStructuringAgent:
    def __init__(self, runtime: AgentLangChainRuntime | None = None) -> None:
        self.runtime = runtime or AgentLangChainRuntime()

    async def structure(self, db, *, team_id: int, context: dict[str, Any]) -> dict[str, Any]:
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            raise ActivityStructuringError("AI 配置未设置")
        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            raise ActivityStructuringError("无法获取 API Key")

        category = context["current_activity"]["activity_category"]
        response_model = MeetingStructuringResult if category == "MEETING" else FollowUpStructuringResult
        result = await self.runtime.ainvoke_structured(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            temperature=min(float(config.temperature or 0.1), 0.2),
            system_prompt=self._system_prompt(category),
            user_prompt=self._user_prompt(context),
            response_model=response_model,
            error_prefix="客户活动整理 structured output",
        )
        if result is None:
            raise ActivityStructuringError("LangChain structured output 不可用")
        try:
            payload = result.model_dump(mode="json")
        except AgentLangChainStructuredOutputError as exc:
            raise ActivityStructuringError(str(exc)) from exc
        payload["summary"] = (payload.get("summary") or "")[:300] or None
        payload["title"] = (payload.get("title") or "").strip() or None
        payload["next_action"] = (payload.get("next_action") or "").strip() or None
        if category != "MEETING":
            self._clean_follow_up_content(payload)
        return payload

    def _system_prompt(self, category: str) -> str:
        if category == "MEETING":
            return """你是 CRM 系统中的会议纪要整理 Agent。

任务：把用户原始会议记录整理成固定结构化数据。

要求：
- 必须保留所有有效事实和细节，不要为了简洁删除信息。
- 可以去重、纠错、归类、补全字段名，但不能编造原文没有的信息。
- 不确定的信息用空字符串、空数组或 null。
- 输出必须符合结构化 schema，不要输出 Markdown 或解释文字。"""
        return """你是 CRM 系统中的客户活动整理 Agent。

任务：把用户原始客户活动内容整理成固定结构化数据。

要求：
- 忠于原意，不要编造。
- content 是给 CRM 列表展示的业务正文，只写客户活动本身，不要写“活动类型、发生时间、已有下一步”等系统元信息。
- content 要简洁但不能丢关键事实；不要只写“沟通了项目进展”这种空泛句子。
- 可以去重、纠错、归类、调整语序，但不能删除客户反馈、当前进展、风险、承诺、下一步和时间。
- 示例：原文“今天和睿狐科技的王总沟通了下项目进展，客户反馈还在立项评估阶段，先持续跟进，下周三再找王总确认进展”，content 应类似“客户反馈项目还在立项评估阶段，先持续跟进。”，next_action 应为“下周三找王总确认进展”。
- 不确定的信息用空字符串、空数组或 null。
- 输出必须符合结构化 schema，不要输出 Markdown 或解释文字。"""

    def _user_prompt(self, context: dict[str, Any]) -> str:
        activity = context["current_activity"]
        return (
            "请只整理 <raw_activity> 中的客户活动原文。<metadata> 仅用于理解上下文，禁止写入 content。\n\n"
            "<metadata>\n"
            f"活动类型：{activity.get('activity_label')} ({activity.get('activity_kind')})\n"
            f"发生时间：{activity.get('occurred_at')}\n"
            f"已有下一步：{activity.get('next_action') or ''}\n"
            "</metadata>\n\n"
            "<raw_activity>\n"
            f"{activity.get('source_content') or ''}\n"
            "</raw_activity>"
        )

    def _clean_follow_up_content(self, payload: dict[str, Any]) -> None:
        content_json = payload.get("content_json")
        if not isinstance(content_json, dict):
            payload["content_json"] = {"content": ""}
            return

        content = str(content_json.get("content") or "").strip()
        content = re.sub(r"活动类型：[^。；;\n]*[。；;\n]?", "", content)
        content = re.sub(r"发生时间：[^。；;\n]*[。；;\n]?", "", content)
        content = re.sub(r"已有下一步[^。；;\n]*[。；;\n]?", "", content)
        content_json["content"] = content.strip("；;。 \n\t")


activity_structuring_agent = ActivityStructuringAgent()

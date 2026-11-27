"""LangChain structured-output agent for customer activity structuring."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.crud.ai_config import ai_config_crud
from app.services.agent.langchain_runtime import (
    AgentLangChainRuntime,
    AgentLangChainStructuredOutputError,
    agent_model_enable_thinking,
)
from app.services.customer_activity_ai.schemas import (
    FollowUpStructuringResult,
    MeetingStructuringResult,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class ActivityStructuringError(Exception):
    """Raised when an activity cannot be structured reliably."""


class ActivityStructuringAgent:
    def __init__(self, runtime: AgentLangChainRuntime | None = None) -> None:
        self.runtime = runtime or AgentLangChainRuntime()

    async def structure(self, db: Session, *, team_id: int, context: dict[str, Any]) -> dict[str, Any]:
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            raise ActivityStructuringError("AI 配置未设置")
        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            raise ActivityStructuringError("无法获取 API Key")

        category = context["current_activity"]["activity_category"]
        source_content = str(context["current_activity"].get("source_content") or "").strip()
        response_model = MeetingStructuringResult if category == "MEETING" else FollowUpStructuringResult
        result = await self.runtime.ainvoke_structured(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            temperature=min(float(config.temperature or 0.1), 0.2),
            enable_thinking=agent_model_enable_thinking(config.model_name),
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
        payload["summary"] = (payload.get("summary") or "").replace("\r\n", "\n").strip()[:4000] or None
        payload["title"] = (payload.get("title") or "").strip() or None
        payload["next_action"] = (payload.get("next_action") or "").strip() or None
        if category != "MEETING":
            self._clean_follow_up_content(payload)
            if source_content:
                self._validate_follow_up_payload(payload)
        elif source_content:
            self._validate_meeting_payload(payload)
        return payload

    def _system_prompt(self, category: str) -> str:
        if category == "MEETING":
            return """你是 CRM 系统中的会议纪要整理 Agent。

任务：把用户原始会议记录整理成固定结构化数据（必须同时完整填写顶层 summary 与嵌套 content_json）。

要求：
- 必须保留所有有效事实和细节，不要为了简洁删除信息或把长纪要压平成一两句话。
- 可以去重、纠错、归类、补全字段名，但不能编造原文没有的信息。
- 必须同时填写 summary 与 content_json（meeting_subject、meeting_background、key_minutes、requirements、concerns_or_objections、risks、decisions_or_commitments、action_items、next_step_summary 等），绝不能只填 summary 而留空 content_json。
- summary 格式规范：
  - 当原文包含多个议题/要点或篇幅较长（如超过 80 字或包含多条进展/结论/风险/待办）时，必须使用清晰的结构化 Markdown（如 `### 会议要点`、`### 核心结论`、`- **主题**：详情`），使用真实换行符分段分点，禁止压平成一整段纯文本。
  - 若原文已经包含标题、编号或无序列表等 Markdown 结构，必须保留并优化其结构。
  - 若原文非常简短（1-2 句单一事实），保持简洁自然，不要强行拆成冗长模板。
  - 禁止输出原始 HTML 标签（如 <script>、<div> 等）。
- 不确定的单个子字段用空字符串、空数组或 null，但绝不能省略 content_json 对象本身。
- 整体输出必须严格符合结构化 JSON schema，不要在 JSON 外包裹代码块或解释文字。"""
        return """你是 CRM 系统中的客户活动整理 Agent。

任务：把用户原始客户活动内容整理成固定结构化数据（必须同时完整填写顶层 summary 与嵌套 content_json）。

要求：
- 忠于原意，不要编造。
- 必须同时填写顶层 summary 与嵌套 content_json（尤其是 content_json.content，以及原文提到的 customer_feedback、current_progress、risks、next_action、next_follow_time_text），绝不能只填 summary 而省略或留空 content_json。
- content_json.content 与 summary 是给 CRM 列表展示的业务正文，只写客户活动本身，不要写“活动类型、发生时间、已有下一步”等系统元信息。
- content_json.content 与 summary 的 Markdown 规范：
  - 当原文较长（如超过 80 字）或包含多个要点（如沟通进展、客户反馈、风险异议、承诺、下一步等 >= 2 个要点）时，必须使用清晰的结构化 Markdown（如 `###` 小标题、`-` 无序列表、`**加粗**` 重点）并使用真实换行符分点组织，禁止压平成一整段纯文本。
  - 若原文已经包含用户手写的 Markdown（如标题、列表、加粗、引用、代码块）或分条序号，必须保留并优化其 Markdown 结构，不要压平为纯文本。
  - 若原文简短（1-2 句单一事实），保持简洁自然，不要为了套用格式而过度拆分或扩写。
  - 禁止输出原始 HTML 标签（如 <script>、<div> 等）。
- content_json.content 必须覆盖原文所有关键事实，不能只写“沟通了项目进展”这种空泛句子，也不能删除客户反馈、当前进展、风险、承诺、下一步和时间。
- 简短示例：原文“今天和睿狐科技的王总沟通了下项目进展，客户反馈还在立项评估阶段，先持续跟进，下周三再找王总确认进展” ->
  summary 与 content_json.content 均为“客户反馈项目还在立项评估阶段，先持续跟进。”，customer_feedback 为“还在立项评估阶段”，current_progress 为“立项评估阶段”，next_action 为“下周三找王总确认进展”。
- 多要点示例：原文“和张总沟通了私有化部署方案：1）客户确认预算在50万以内；2）安全团队担心公网回调合规问题，需要提供内网方案；3）下周二前我们发架构文档并约安全评审” ->
  summary 与 content_json.content 均使用结构化 Markdown：
  "### 沟通进展\n- **预算范围**：客户确认预算在 50 万以内。\n- **合规关注**：安全团队担心公网回调合规问题，需提供内网部署方案。\n\n### 后续安排\n- 下周二前发送架构文档并预约安全评审。"
  同时 customer_feedback 填“确认预算在50万以内，安全团队担心公网回调合规问题”，current_progress 填“沟通私有化部署方案，待发架构文档并安全评审”，risks 填["安全团队担心公网回调合规问题，需提供内网方案"]，next_action 填“下周二前发送架构文档并约安全评审”。
- 不确定的单个子字段用空字符串、空数组或 null，但绝不能省略 content_json 对象本身。
- 整体输出必须严格符合结构化 JSON schema，不要在 JSON 外包裹代码块或解释文字。"""

    def _user_prompt(self, context: dict[str, Any]) -> str:
        activity = context["current_activity"]
        return (
            "请只整理 <raw_activity> 中的客户活动原文，并完整填充 summary 与 content_json 所有适用字段。"
            "<metadata> 仅用于理解上下文，禁止写入 content。\n\n"
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

        content = str(content_json.get("content") or "").replace("\r\n", "\n").strip()
        content = re.sub(r"活动类型：[^。\n]*[。\n]?", "", content)
        content = re.sub(r"发生时间：[^。\n]*[。\n]?", "", content)
        content = re.sub(r"。?已有下一步[^。\n]*[。\n]?", "", content)
        content_json["content"] = content.strip(" \n\t")

    @staticmethod
    def _validate_follow_up_payload(payload: dict[str, Any]) -> None:
        content_json = payload.get("content_json")
        content = str(content_json.get("content") or "").strip() if isinstance(content_json, dict) else ""
        summary = str(payload.get("summary") or "").strip()
        if not content:
            raise ActivityStructuringError("客户活动整理结果缺少有效 content_json.content")
        if not summary:
            payload["summary"] = content[:4000]

    @staticmethod
    def _has_meaningful_meeting_content(content_json: Any) -> bool:
        if not isinstance(content_json, dict):
            return False
        for key, value in content_json.items():
            if key == "participants" and isinstance(value, dict):
                if any(isinstance(v, list) and len(v) > 0 for v in value.values()):
                    return True
                continue
            if isinstance(value, str) and value.strip():
                return True
            if isinstance(value, list) and len(value) > 0:
                return True
        return False

    @classmethod
    def _validate_meeting_payload(cls, payload: dict[str, Any]) -> None:
        summary = str(payload.get("summary") or "").strip()
        if not summary:
            raise ActivityStructuringError("会议纪要整理结果缺少有效 summary")
        if not cls._has_meaningful_meeting_content(payload.get("content_json")):
            raise ActivityStructuringError("会议纪要整理结果缺少有效结构化 content_json")

activity_structuring_agent = ActivityStructuringAgent()

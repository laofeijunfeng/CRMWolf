"""Kind classification and canonical activity structuring for the sales assistant."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.services.assistant.model_transport import (
    AssistantLLMError,
    AssistantModelTransport,
    team_model_credentials,
)
from app.services.assistant.llm_contracts import (
    KindDecision,
    StructuredFollowUp,
    StructuredMeeting,
    StructureDraftResult,
)

from app.services.customer_activity_ai.schemas import FollowUpContent, MeetingActionItem, MeetingContent

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# ruff: noqa: RUF001




KIND_SYSTEM_PROMPT = """你是 CRM 销售助手的活动类型判断器。判断用户这段话描述的是哪种客户活动。

规则：
- FOLLOW_UP：普通跟进，电话、微信、邮件等日常沟通。
- ONLINE_MEETING：线上会议，出现会议主题、参会人、会议结论或行动项且是远程形式。
- OFFLINE_MEETING：线下会议或面谈拜访，且具备会议结构。
- UNCLEAR：线上还是线下无法区分，或同时出现会议和拜访信号。

只输出结构化结果，不要解释。"""

STRUCTURE_FOLLOW_UP_PROMPT = """你是 CRM 销售助手的跟进整理器。把用户的原话整理成一条跟进记录。

规则：
- content 覆盖原文全部事实点：客户反馈、进展、风险、承诺；可调整语序、去重，不得删减事实。
- customer_name 只填原文明确出现的客户名称，没有则留空。
- next_action 忠于原文，没有则留空。
- content_json 必须完整填写：content、customer_feedback、current_progress、risks、next_action、next_follow_time_text；所有事实均保留。
- 不确定的信息一律留空，禁止编造。
只输出结构化结果。"""

STRUCTURE_MEETING_PROMPT = """你是 CRM 销售助手的会议纪要整理器。把用户的原话整理成一条会议纪要。

规则：
- customer_name 只填原文明确出现的客户（公司）名称，没有则留空。
- meeting_subject 填会议主题；content 按发言人分组整理关键讨论、客户诉求、决策和承诺。
- content_json 必须完整填写 meeting_subject、meeting_background、communication_context、participants（internal/customer）、key_minutes、qa_items、requirements、concerns_or_objections、risks、decisions_or_commitments、action_items、next_step_summary。
- action_items 每项均包含 owner、action、due_date，保留原文的所有行动项，不可只保留首条。
- participants 区分我方与客户方成员及其角色，只有「双方参会」时保留原样。
- next_action 填首要行动项，尽量含负责人和时间；原文没有则留空。
- 不确定的信息一律留空，禁止编造。
只输出结构化结果。"""


def _require_complete_content(content: FollowUpContent | MeetingContent | None) -> None:
    if content is None:
        raise AssistantLLMError("活动整理：缺少完整类型化正文")
    expected = set(type(content).model_fields)
    if not expected.issubset(content.model_fields_set):
        raise AssistantLLMError("活动正文结构不完整")
    if isinstance(content, MeetingContent):
        if set(type(content.participants).model_fields) - content.participants.model_fields_set:
            raise AssistantLLMError("参会角色结构不完整")
        for item in (*content.qa_items, *content.action_items):
            missing = set(type(item).model_fields) - item.model_fields_set
            # item_id is assigned by the server when merging, never by the model.
            if isinstance(item, MeetingActionItem):
                missing.discard("item_id")
            if missing:
                raise AssistantLLMError("会议问答或行动项结构不完整")


class AssistantLLM:
    """Two bounded structured calls: kind classification and full draft."""

    def __init__(self, runtime: object | None = None) -> None:
        self.runtime = runtime or AssistantModelTransport()

    async def _invoke(self, db: Session, team_id: int, prompt: str, text: str, model: type, label: str, timeout_seconds: float = 120):
        host, key, name = team_model_credentials(db, team_id)
        try:
            result = await self.runtime.ainvoke_structured(
                api_host=host,
                api_key=key,
                model=name,
                temperature=0.0,
                system_prompt=prompt,
                user_prompt=text,
                response_model=model,
                error_prefix=label,
                timeout_seconds=timeout_seconds,
            )
            if result is None:
                raise AssistantLLMError(f"{label}：结构化输出不可用")
            return model.model_validate(result)
        except AssistantLLMError:
            raise
        except (RuntimeError, ValueError, TypeError, ValidationError) as exc:
            raise AssistantLLMError(f"{label}：结构化输出无效") from exc

    async def classify_kind(self, db: Session, *, team_id: int, user_text: str) -> KindDecision:
        decision = await self._invoke(db, team_id, KIND_SYSTEM_PROMPT, user_text, KindDecision, "活动类型判断", timeout_seconds=30)
        if "kind" not in decision.model_fields_set:
            raise AssistantLLMError("活动类型判断：缺少活动类型")
        return decision

    async def structure_draft(
        self,
        db: Session,
        *,
        team_id: int,
        kind: str,
        user_text: str,
    ) -> StructureDraftResult:
        if kind not in {"FOLLOW_UP", "ONLINE_MEETING", "OFFLINE_MEETING"}:
            raise AssistantLLMError("未知活动类型")
        meeting = kind != "FOLLOW_UP"
        _host, _key, model_name = team_model_credentials(db, team_id)
        response = await self._invoke(
            db,
            team_id,
            STRUCTURE_MEETING_PROMPT if meeting else STRUCTURE_FOLLOW_UP_PROMPT,
            user_text,
            StructuredMeeting if meeting else StructuredFollowUp,
            "会议纪要整理" if meeting else "跟进整理",
        )
        _require_complete_content(response.content_json)
        if meeting:
            return StructureDraftResult(
                kind_confirmed=kind,
                content=response.content or "\n".join(response.content_json.key_minutes),
                customer_name=response.customer_name,
                next_action=response.next_action,
                next_follow_time_text=response.next_follow_time_text,
                meeting_subject=response.meeting_subject or response.content_json.meeting_subject,
                participants=response.participants,
                content_json=response.content_json.model_dump(mode="json"),
                structuring_model=model_name,
            )
        return StructureDraftResult(
            kind_confirmed="FOLLOW_UP",
            content=response.content_json.content,
            customer_name=response.customer_name,
            next_action=response.content_json.next_action,
            next_follow_time_text=response.content_json.next_follow_time_text,
            content_json=response.content_json.model_dump(mode="json"),
            structuring_model=model_name,
        )

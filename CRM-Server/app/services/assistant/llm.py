"""Kind classification and canonical activity structuring for the sales assistant."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.services.assistant.llm_contracts import (
    ChangeJudgment,
    CustomerMention,
    KindDecision,
    OpportunityRank,
    StructuredFollowUp,
    StructuredMeeting,
    StructureDraftResult,
)
from app.services.assistant.model_transport import (
    AssistantLLMError,
    AssistantModelTransport,
    team_model_credentials,
)
from app.services.customer_activity_ai.schemas import FollowUpContent, MeetingActionItem, MeetingContent

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# ruff: noqa: RUF001




KIND_SYSTEM_PROMPT = """你是 CRM 销售助手的活动类型判断器。判断用户这段话要写入哪一种客户活动。

规则：
- 只输出一种 kind：PHONE_FOLLOW_UP、WECHAT_FOLLOW_UP、EMAIL_FOLLOW_UP、
  VISIT_FOLLOW_UP、OTHER_FOLLOW_UP、ONLINE_MEETING、OFFLINE_MEETING、UNCLEAR。
- 电话、微信、邮件、拜访各自对应前面的跟进类型。
  不要输出 FOLLOW_UP，也不要把明确渠道写成 OTHER_FOLLOW_UP。
- ONLINE_MEETING 是线上会议。OFFLINE_MEETING 是线下会议。
  普通拜访没有会议结构时用 VISIT_FOLLOW_UP。
- confidence 取 0 到 1。只有一种渠道且原文明确时才高于或等于 0.8。
- evidence_quote 必须是用户原文里的连续片段，不能改写。
- channels 列出原文里出现的全部渠道；同时有电话和微信时都要列出，不能只留一个。
- 没有渠道、多个渠道，或会议和跟进分不清时，kind 用 UNCLEAR，confidence 低于 0.8。

只输出结构化结果，不要解释。"""

STRUCTURE_FOLLOW_UP_PROMPT = """你是 CRM 销售助手的跟进整理器。把用户的原话整理成一条跟进记录。

规则：
- content 覆盖原文全部事实点：客户反馈、进展、风险、承诺；可调整语序、去重，不得删减事实。
- customer_name 只填原文明确出现的客户名称，没有则留空。
- next_action 忠于原文，没有则留空。
- content_json 必须完整填写：content、customer_feedback、current_progress、risks、next_action、next_action_absence_reason、next_follow_time_text；没有对应事实的字段也必须返回空值，不得省略。
- next_action_absence_reason 只记录用户明确暂无下一步的原因或复查条件；未明确表示暂无下一步时留空，不得把缺少行动推断成暂无行动。
- 不确定的信息一律留空，禁止编造。
- temporal_mentions 覆盖原文每一个时间表达，字段只有 raw_text、quote_start、quote_end、kind、role、owner、action_ref、confidence。kind 只能是 EXPLICIT_DATE、MONTH_DAY、DAY_OF_MONTH、MONTH_SEGMENT、RELATIVE_DAY、RELATIVE_WEEK、RELATIVE_MONTH、RELATIVE_WEEKDAY、UNKNOWN。月初、月中、月末、月底用 MONTH_SEGMENT，不要当成某一天。role 只能是 CUSTOMER_COMMITMENT、CUSTOMER_ACTION、SALES_FOLLOW_UP、INTERNAL_ACTION、OTHER。不要输出 ISO 日期或公历结果。
- actions 保留每一个动作，字段只有 action_ref、owner_role、owner_text、action_text、action_status、evidence_quote、quote_start、quote_end。owner_role 只能是 CUSTOMER、SALES、INTERNAL、OTHER。action_status 只能是 PLANNED、COMPLETED、COMMITTED、UNKNOWN。客户承诺和销售下次联系必须分成两条，不能并进一个 next_action。
- quote_start 与 quote_end 是这段用户原文里的字符位置，切片必须等于 raw_text 或 evidence_quote。
只输出结构化结果。"""

STRUCTURE_MEETING_PROMPT = """你是 CRM 销售助手的会议纪要整理器。把用户的原话整理成一条会议纪要。

规则：
- customer_name 只填原文明确出现的客户（公司）名称，没有则留空。
- meeting_subject 填会议主题；content 按发言人分组整理关键讨论、客户诉求、决策和承诺。
- content_json 必须完整填写 meeting_subject、meeting_background、communication_context、participants（internal/customer）、key_minutes、qa_items、requirements、concerns_or_objections、risks、decisions_or_commitments、action_items、next_step_summary、next_action_absence_reason；没有对应事实的字段也必须返回空值，不得省略。
- next_action_absence_reason 只记录用户明确暂无下一步的原因或复查条件；未明确表示暂无下一步时留空，不得把缺少行动推断成暂无行动。
- action_items 每项均包含 owner、action、due_date，保留原文的所有行动项，不可只保留首条。
- participants 区分我方与客户方成员及其角色，只有「双方参会」时保留原样。
- next_action 填首要行动项，尽量含负责人和时间；原文没有则留空。
- 不确定的信息一律留空，禁止编造。
- temporal_mentions 覆盖原文每一个时间表达，字段只有 raw_text、quote_start、quote_end、kind、role、owner、action_ref、confidence。kind 只能是 EXPLICIT_DATE、MONTH_DAY、DAY_OF_MONTH、MONTH_SEGMENT、RELATIVE_DAY、RELATIVE_WEEK、RELATIVE_MONTH、RELATIVE_WEEKDAY、UNKNOWN。月初、月中、月末、月底用 MONTH_SEGMENT，不要当成某一天。role 只能是 CUSTOMER_COMMITMENT、CUSTOMER_ACTION、SALES_FOLLOW_UP、INTERNAL_ACTION、OTHER。不要输出 ISO 日期或公历结果。
- actions 保留每一个动作，字段只有 action_ref、owner_role、owner_text、action_text、action_status、evidence_quote、quote_start、quote_end。owner_role 只能是 CUSTOMER、SALES、INTERNAL、OTHER。action_status 只能是 PLANNED、COMPLETED、COMMITTED、UNKNOWN。客户承诺和销售下次联系必须分成两条，不能并进一个 next_action。
- quote_start 与 quote_end 是这段用户原文里的字符位置，切片必须等于 raw_text 或 evidence_quote。
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
        from app.services.assistant.activity_channel import structuring_kind

        kind = structuring_kind(kind)
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
        from app.services.assistant.temporal_evidence import ensure_mentions_cover_source

        ensure_mentions_cover_source(user_text, response.temporal_mentions)
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
                temporal_mentions=response.temporal_mentions,
                actions=response.actions,
                structuring_model=model_name,
            )
        return StructureDraftResult(
            kind_confirmed="FOLLOW_UP",
            content=response.content_json.content,
            customer_name=response.customer_name,
            next_action=response.content_json.next_action,
            next_follow_time_text=response.content_json.next_follow_time_text,
            content_json=response.content_json.model_dump(mode="json"),
            temporal_mentions=response.temporal_mentions,
            actions=response.actions,
            structuring_model=model_name,
        )


    async def locate_customer(self, db: Session, *, team_id: int, user_text: str) -> CustomerMention:
        found = await self._invoke(
            db,
            team_id,
            "你只从用户原文摘录客户公司名称。没有明确写出公司或客户名称时返回空字符串。"
            "不要把“他”“客户”或某人的姓氏当成公司名称，不要根据常识补全。只输出结构化结果。",
            user_text,
            CustomerMention,
            "客户名称定位",
            timeout_seconds=30,
        )
        return found

    async def rank_opportunities(
        self,
        db: Session,
        *,
        team_id: int,
        user_text: str,
        candidates: list[dict[str, object]],
    ) -> OpportunityRank:
        import json

        return await self._invoke(
            db,
            team_id,
            "你只在给定序号里为这次跟进排序进行中商机。返回序号和 0 到 1 的置信度。"
            "不得输出商机编号或数据库标识。不确定时让置信度接近。只输出结构化结果。",
            json.dumps({"follow_up": user_text, "candidates": candidates}, ensure_ascii=False),
            OpportunityRank,
            "商机排序",
            timeout_seconds=30,
        )

    async def judge_change(
        self,
        db: Session,
        *,
        team_id: int,
        user_text: str,
        evidence: list[dict[str, object]],
        opportunity_name: str | None,
        opportunity_stage: str | None,
    ) -> ChangeJudgment:
        import json

        return await self._invoke(
            db,
            team_id,
            "你只判断这次跟进相对给定证据的变化信号：推进、持平、放缓或待确认。"
            "只能引用给定 ref。relation 只能是推进、持平、放缓、冲突或背景。"
            "“再考虑”本身不是放缓，不得判断输单、退步或商机回退。只输出结构化结果。",
            json.dumps(
                {
                    "follow_up": user_text,
                    "evidence": evidence,
                    "opportunity_name": opportunity_name,
                    "opportunity_stage": opportunity_stage,
                },
                ensure_ascii=False,
            ),
            ChangeJudgment,
            "变化判断",
            timeout_seconds=30,
        )

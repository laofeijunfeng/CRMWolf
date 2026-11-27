"""Structured output schemas for customer activity AI workflows."""
from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

from pydantic import BaseModel, Field, field_validator, model_validator


class MeetingParticipants(BaseModel):
    internal: list[str] = Field(default_factory=list)
    customer: list[str] = Field(default_factory=list)


class MeetingQAItem(BaseModel):
    question: str = ""
    answer: str = ""


class MeetingActionItem(BaseModel):
    owner: str = ""
    action: str = ""
    due_date: str | None = None
    item_id: str | None = Field(None, description="行动项稳定 ID\uff0c由服务端生成\uff0c模型不可指定")


class MeetingContent(BaseModel):
    meeting_subject: str = ""
    meeting_background: str = ""
    communication_context: str = ""
    participants: MeetingParticipants = Field(default_factory=MeetingParticipants)
    key_minutes: list[str] = Field(default_factory=list)
    qa_items: list[MeetingQAItem] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    concerns_or_objections: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    decisions_or_commitments: list[str] = Field(default_factory=list)
    action_items: list[MeetingActionItem] = Field(default_factory=list)
    next_step_summary: str = ""
    next_action_absence_reason: str = ""


class FollowUpContent(BaseModel):
    content: str = Field(
        ...,
        description="必填：完整整理后的结构化 Markdown 跟进正文，必须覆盖原文所有事实点（多要点或较长记录使用 ### 小标题、无序列表 - 和加粗 **重点** 组织，简短记录保持简洁自然），不要摘要化、压缩或删除客户反馈、进展、风险、承诺、下一步。",
    )
    customer_feedback: str = Field("", description="客户明确表达的反馈、态度、状态或限制条件。")
    current_progress: str = Field("", description="项目、机会或事项当前进展，例如立项评估、采购流程、测试验证等。")
    risks: list[str] = Field(default_factory=list, description="原文提到的风险、阻碍、异议或不确定性。")
    next_action: str = Field("", description="下一步动作，忠于原文，不要编造。")
    next_action_absence_reason: str = Field("", description="明确暂无下一步行动的用户原话原因，不是行动。")
    next_follow_time_text: str = Field("", description="原文中的下次跟进时间表达。")


class MeetingStructuringResult(BaseModel):
    title: str | None = Field(default=None, description="简短会议主题标题。")
    summary: str = Field(
        ...,
        description="必填：完整、清晰的结构化 Markdown 会议纪要正文（多要点或较长会议记录必须使用 ### 小标题、无序列表 -、加粗 **重点** 组织，保留原文层级与事实；简短记录保持简洁；禁止输出原始 HTML 标签）。",
    )
    next_action: str | None = Field(default=None, description="明确的下一步行动，忠于原文，无则 null。")
    content_json: MeetingContent = Field(
        ...,
        description="必填：完整的会议结构化字段对象，必须按原文填写 meeting_subject、key_minutes、requirements、risks、decisions_or_commitments、action_items 等字段，禁止省略或置空。",
    )


class FollowUpStructuringResult(BaseModel):
    title: str | None = Field(default=None, description="简短活动标题。")
    summary: str = Field(
        ...,
        description="必填：面向 CRM 列表展示的结构化 Markdown 正文/摘要（多要点或较长记录必须使用 ### 小标题、无序列表 -、加粗 **重点** 组织；1-2 句简短记录保持自然简洁；保留原文手写 Markdown；禁止输出原始 HTML 标签）。",
    )
    next_action: str | None = Field(default=None, description="明确的下一步行动，忠于原文，无则 null。")
    content_json: FollowUpContent = Field(
        ...,
        description="必填：完整的跟进结构化字段对象，必须填写 content 及原文包含的 customer_feedback、current_progress、risks、next_action、next_follow_time_text，禁止省略或整体置空。",
    )

class PrincipleScore(BaseModel):
    score: int = Field(0, ge=0)
    max_score: int = Field(0, ge=0)
    comment: str = ""


class ActivityEvaluationResult(BaseModel):
    score: int = Field(0, ge=0, le=100)
    is_valid: bool = False
    reason: str = ""
    principle_scores: dict[str, PrincipleScore] = Field(default_factory=dict)
    supplement_question: str | None = None

    @model_validator(mode="after")
    def enforce_validity_threshold(self) -> ActivityEvaluationResult:
        self.is_valid = self.score >= 60
        return self

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str) -> str:
        value = (value or "").strip()
        return value[:120] or "缺少可接力的关键信息或明确下一步动作。"


class CustomerActivityAIFinalResult(BaseModel):
    """Pure-computation output consumed by the atomic activity write seam."""

    title: str | None = None
    content_json: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    next_action: str | None = None
    next_action_source: str | None = None
    next_follow_time: datetime | None = None
    next_follow_time_source: str | None = None
    effectiveness_score: int = Field(ge=0, le=100)
    effectiveness_is_valid: bool
    effectiveness_reason: str
    effectiveness_detail: dict[str, Any] = Field(default_factory=dict)


class CustomerActivityAIState(TypedDict, total=False):
    activity_id: int
    team_id: int
    run_id: str
    expected_activity_revision: int | None
    original_context: dict[str, Any]
    context: dict[str, Any]
    structure_result: dict[str, Any]
    evaluation_result: dict[str, Any]
    events: list[dict[str, Any]]

"""Structured output schemas for customer activity AI workflows."""
from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict

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
    due_date: Optional[str] = None


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


class FollowUpContent(BaseModel):
    content: str = Field(
        "",
        description="完整整理后的跟进正文，必须覆盖原文所有事实点，不要摘要化、压缩或删除客户反馈、进展、风险、承诺、下一步。",
    )
    customer_feedback: str = Field("", description="客户明确表达的反馈、态度、状态或限制条件。")
    current_progress: str = Field("", description="项目、机会或事项当前进展，例如立项评估、采购流程、测试验证等。")
    risks: list[str] = Field(default_factory=list, description="原文提到的风险、阻碍、异议或不确定性。")
    next_action: str = Field("", description="下一步动作，忠于原文，不要编造。")
    next_follow_time_text: str = Field("", description="原文中的下次跟进时间表达。")


class MeetingStructuringResult(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    next_action: Optional[str] = None
    content_json: MeetingContent = Field(default_factory=MeetingContent)


class FollowUpStructuringResult(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    next_action: Optional[str] = None
    content_json: FollowUpContent = Field(default_factory=FollowUpContent)


class PrincipleScore(BaseModel):
    score: int = Field(0, ge=0)
    max_score: int = Field(0, ge=0)
    comment: str = ""


class ActivityEvaluationResult(BaseModel):
    score: int = Field(0, ge=0, le=100)
    is_valid: bool = False
    reason: str = ""
    principle_scores: dict[str, PrincipleScore] = Field(default_factory=dict)
    supplement_question: Optional[str] = None

    @model_validator(mode="after")
    def enforce_validity_threshold(self) -> "ActivityEvaluationResult":
        self.is_valid = self.score >= 60
        return self

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str) -> str:
        value = (value or "").strip()
        return value[:120] or "缺少可接力的关键信息或明确下一步动作。"


class CustomerActivityAIState(TypedDict, total=False):
    activity_id: int
    team_id: int
    run_id: str
    mode: Literal["process", "evaluate"]
    context: dict[str, Any]
    structure_result: dict[str, Any]
    evaluation_result: dict[str, Any]
    events: list[dict[str, Any]]

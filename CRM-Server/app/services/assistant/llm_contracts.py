"""Typed neutral LLM contracts for activity kind and canonical structuring."""

# ruff: noqa: RUF001

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from app.services.customer_activity_ai.schemas import FollowUpContent, MeetingContent

ActivityKind = Literal["FOLLOW_UP", "ONLINE_MEETING", "OFFLINE_MEETING"]
CanonicalActivityKind = Literal[
    "PHONE_FOLLOW_UP",
    "WECHAT_FOLLOW_UP",
    "EMAIL_FOLLOW_UP",
    "VISIT_FOLLOW_UP",
    "OTHER_FOLLOW_UP",
    "ONLINE_MEETING",
    "OFFLINE_MEETING",
]


class KindDecision(BaseModel):
    """Model nomination of one activity channel. The server decides whether it can be frozen."""

    model_config = ConfigDict(extra="forbid")

    kind: CanonicalActivityKind | ActivityKind | Literal["UNCLEAR"] = "UNCLEAR"
    reason: str = Field(default="", max_length=200)
    confidence: float = Field(default=0, ge=0, le=1)
    evidence_quote: str = Field(default="", max_length=200)
    channels: list[CanonicalActivityKind] = Field(default_factory=list, max_length=7)



TimeKind = Literal[
    "EXPLICIT_DATE", "MONTH_DAY", "DAY_OF_MONTH", "MONTH_SEGMENT", "FULL_MONTH", "RELATIVE_DAY",
    "RELATIVE_WEEK", "RELATIVE_MONTH", "RELATIVE_WEEKDAY", "UNKNOWN",
]
TimeRole = Literal["CUSTOMER_COMMITMENT", "CUSTOMER_ACTION", "SALES_FOLLOW_UP", "INTERNAL_ACTION", "OTHER"]


class ModelTemporalMention(BaseModel):
    """One quoted time. The server, not the model, owns the canonical date."""

    model_config = ConfigDict(extra="forbid")

    raw_text: str = Field(min_length=1, max_length=80)
    quote_start: int = Field(ge=0)
    quote_end: int = Field(ge=0)
    kind: TimeKind
    role: TimeRole
    owner: str = Field(default="", max_length=80)
    action_ref: str = Field(default="", max_length=64)
    confidence: float = Field(default=0, ge=0, le=1)


class ModelDraftAction(BaseModel):
    """One action bound to a quote. Multiple actions stay separate."""

    model_config = ConfigDict(extra="forbid")

    action_ref: str = Field(min_length=1, max_length=64)
    owner_role: Literal["CUSTOMER", "SALES", "INTERNAL", "OTHER"]
    owner_text: str = Field(default="", max_length=80)
    action_text: str = Field(min_length=1, max_length=500)
    action_status: Literal["PLANNED", "COMPLETED", "COMMITTED", "UNKNOWN"]
    evidence_quote: str = Field(min_length=1, max_length=500)
    quote_start: int = Field(ge=0)
    quote_end: int = Field(ge=0)


class StructuredFollowUp(BaseModel):
    """Follow-up structuring output mapped into the task draft."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(default="", max_length=20000, description="整理后的跟进正文，保留全部事实点")
    customer_name: str = Field(default="", max_length=500, description="客户名称文本，仅作查找线索")
    next_action: str = Field(default="", max_length=4000, description="下一步动作，忠于原文")
    next_follow_time_text: str = Field(default="", max_length=200, description="原文中的时间表达")
    temporal_mentions: list[ModelTemporalMention] = Field(default_factory=list)
    actions: list[ModelDraftAction] = Field(default_factory=list)
    content_json: FollowUpContent | None = None


class StructuredMeeting(BaseModel):
    """Meeting structuring output mapped into the task draft."""

    model_config = ConfigDict(extra="forbid")

    customer_name: str = Field(default="", max_length=500, description="客户名称文本，仅作查找线索")
    meeting_subject: str = Field(default="", max_length=500)
    content: str = Field(default="", max_length=20000, description="按发言人整理的关键讨论")
    participants: str = Field(default="", max_length=2000, description="我方与客户方参会角色")
    next_action: str = Field(default="", max_length=4000, description="首要行动项，含负责人与时间")
    next_follow_time_text: str = Field(default="", max_length=200)
    temporal_mentions: list[ModelTemporalMention] = Field(default_factory=list)
    actions: list[ModelDraftAction] = Field(default_factory=list)
    content_json: MeetingContent | None = None


class StructureDraftResult(BaseModel):
    """Normalized structuring result consumed by the coordinator."""

    model_config = ConfigDict(extra="forbid")

    kind_confirmed: ActivityKind
    content: str
    customer_name: str = ""
    next_action: str = ""
    next_follow_time_text: str = ""
    meeting_subject: str = ""
    participants: str = ""
    content_json: dict[str, Any] | None = None
    temporal_mentions: list[ModelTemporalMention] = Field(default_factory=list)
    actions: list[ModelDraftAction] = Field(default_factory=list)
    structuring_model: str = ""



class CustomerMention(BaseModel):
    """Customer name copied from the utterance. Empty means the user did not name one."""

    model_config = ConfigDict(extra="forbid")

    customer_name: str = Field(default="", max_length=500)


class OpportunityRankItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)


class OpportunityRank(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ranked: list[OpportunityRankItem] = Field(default_factory=list, max_length=5)


class EvidenceUse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(min_length=1, max_length=16)
    relation: Literal["推进", "持平", "放缓", "冲突", "背景"]


class ChangeJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal: Literal["推进", "持平", "放缓", "待确认"]
    uses: list[EvidenceUse] = Field(default_factory=list, max_length=8)
